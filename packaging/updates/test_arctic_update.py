"""Tests for arctic-update-helper (the file handling behind arctic-update) and a smoke test of
arctic-update itself with a fake dnf5.

The dnf5 texts and files below were captured from dnf5 5.4.5.0 on Fedora 44
(`dnf5 upgrade --offline -y` with two older packages installed, then `dnf5 offline status`
in each state).

Run: python3 -m unittest discover -s packaging/updates
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
loader = importlib.machinery.SourceFileLoader('arctic_update_helper', str(HERE / 'arctic-update-helper'))
spec = importlib.util.spec_from_loader('arctic_update_helper', loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)

STATE = textwrap.dedent('''\
    [offline-transaction-state]
    rpmdb_cookie = "302d4f791681b80728445fbf06c0221988a60c3131e5c24d3aeec8c5406fd54f"
    module_platform_id = ""
    poweroff_after = false
    verb = "upgrade"
    system_releasever = "44"
    target_releasever = "44"
    cachedir = "/var/cache/libdnf5"
    status = "download-complete"
    cmd_line = "dnf5 upgrade --offline -y --refresh"
    state_version = 2

    ''')

TRANSACTION = {
    "rpms": [
        {"nevra": "jq-1.8.1-3.fc44.x86_64", "action": "Upgrade", "reason": "User", "repo_id": "updates",
         "package_path": "/var/lib/dnf/offline/packages/jq-1.8.1-3.fc44.x86_64.rpm"},
        {"nevra": "tzdata-2026c-2.fc44.noarch", "action": "Upgrade", "reason": "User", "repo_id": "updates",
         "package_path": "/var/lib/dnf/offline/packages/tzdata-2026c-2.fc44.noarch.rpm"},
        {"nevra": "jq-1.8.1-2.fc44.x86_64", "action": "Replaced", "reason": "User", "repo_id": "@System"},
        {"nevra": "tzdata-2026a-1.fc44.noarch", "action": "Replaced", "reason": "User", "repo_id": "@System"},
    ],
    "version": "1.0",
}
SIZES = {"/var/lib/dnf/offline/packages/jq-1.8.1-3.fc44.x86_64.rpm": 220681,
         "/var/lib/dnf/offline/packages/tzdata-2026c-2.fc44.noarch.rpm": 729012}

OFFLINE_STATUS = {
    "none": "No offline transaction is stored.\n",
    "stored": ("An offline transaction was initiated by the following command:\n"
               "\tdnf5 upgrade --offline -y --refresh\n"
               "Run `dnf5 offline reboot` to reboot and perform the offline transaction.\n"),
    "stale": ("The system has been modified since the offline transaction was prepared. The offline "
              "transaction initiated by the following command is no longer valid:\n"
              "  dnf5 upgrade --offline -y --refresh\n"
              "To reschedule, run the command above. To clean up, run `dnf5 offline clean`.\n"),
    "incomplete": ("An offline transaction was started, but it did not finish. Run `dnf5 offline log` "
                   "for more information. The command that initiated the transaction was:\n"
                   "\tdnf5 upgrade --offline -y\n"),
    "unknown": 'Unknown offline transaction status: "download-incomplete"\n',
}

REPOS = json.dumps([
    {"id": "fedora", "name": "Fedora 44 - x86_64", "is_enabled": True},
    {"id": "updates", "name": "Fedora 44 - x86_64 - Updates", "is_enabled": True},
    {"id": "arctic", "name": "Arctic Linux 44 - x86_64", "is_enabled": True},
    {"id": "arctic-testing", "name": "Arctic Linux 44 - x86_64 - testing", "is_enabled": False},
    {"id": "arctic-source", "name": "Arctic Linux 44 - Source", "is_enabled": False},
])


def fixed_now():
    return "2026-09-27T21:37:00+00:00"


class ConfigTests(unittest.TestCase):
    def test_shipped_file_is_the_defaults(self):
        settings, warnings = helper.parse_config((HERE / 'update.conf').read_text())
        self.assertEqual(settings, {"AUTO": "download-and-install-on-reboot", "METERED": "skip"})
        self.assertEqual(warnings, [])

    def test_missing_file_means_defaults(self):
        self.assertEqual(helper.parse_config("")[0], helper.DEFAULTS)

    def test_values_quotes_comments_and_aliases(self):
        settings, warnings = helper.parse_config(textwrap.dedent('''\
            # AUTO=off (an example in a comment)
            export AUTO="download-only"
            metered = allow   # on my unlimited plan
            UNRELATED=1
            '''))
        self.assertEqual(settings, {"AUTO": "download-only", "METERED": "allow"})
        self.assertEqual(warnings, [])
        self.assertEqual(helper.parse_config("AUTO=no\nMETERED=yes\n")[0], {"AUTO": "off", "METERED": "allow"})
        self.assertEqual(helper.parse_config("AUTO='ON'\n")[0]["AUTO"], "download-and-install-on-reboot")

    def test_unknown_value_warns_and_uses_the_default(self):
        settings, warnings = helper.parse_config("AUTO=sometimes\nMETERED=skip\n")
        self.assertEqual(settings["AUTO"], "download-and-install-on-reboot")
        self.assertEqual(len(warnings), 1)
        self.assertIn("sometimes", warnings[0])

    def test_set_config_edits_the_active_line_only(self):
        text = (HERE / 'update.conf').read_text()
        new = helper.set_config(text, "AUTO", "off")
        self.assertEqual(helper.parse_config(new)[0]["AUTO"], "off")
        changed = [(a, b) for a, b in zip(text.splitlines(), new.splitlines()) if a != b]
        self.assertEqual(changed, [("AUTO=download-and-install-on-reboot", "AUTO=off")])
        self.assertEqual(len(new.splitlines()), len(text.splitlines()))
        # The comment explaining the values still names every mode.
        self.assertIn("#   download-only", new)

    def test_set_config_appends_when_missing(self):
        self.assertEqual(helper.set_config("# nothing yet", "metered", "allow"), "# nothing yet\nMETERED=allow\n")
        self.assertEqual(helper.set_config("", "AUTO", "off"), "AUTO=off\n")
        self.assertEqual(helper.set_config("export AUTO=off\n", "AUTO", "download-only"), "export AUTO=download-only\n")

    def test_set_config_command_rejects_unknown_values(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(io.StringIO()):
            conf = os.path.join(d, "update.conf")
            with self.assertRaises(SystemExit):
                helper.main(["set-config", conf, "AUTO", "sometimes"])
            self.assertFalse(os.path.exists(conf))
            helper.main(["set-config", conf, "AUTO", "off"])
            self.assertEqual(Path(conf).read_text(), "AUTO=off\n")
            self.assertEqual(stat.S_IMODE(os.stat(conf).st_mode), 0o644)


class OfflineStatusTests(unittest.TestCase):
    def test_classify_real_dnf5_output(self):
        for want, text in OFFLINE_STATUS.items():
            with self.subTest(want):
                self.assertEqual(helper.classify_offline_status(text), want)
        self.assertEqual(helper.classify_offline_status("Error reading state: bad TOML."), "unknown")
        self.assertEqual(helper.classify_offline_status(""), "unknown")


class ArmTests(unittest.TestCase):
    def test_only_the_status_line_changes(self):
        new = helper.arm_text(STATE)
        diff = [(a, b) for a, b in zip(STATE.splitlines(), new.splitlines()) if a != b]
        self.assertEqual(diff, [('status = "download-complete"', 'status = "ready"')])
        self.assertEqual(len(new), len(STATE) - len("download-complete") + len("ready"))
        self.assertEqual(helper.load_state(new)["status"], "ready")

    def test_keeps_a_trailing_comment(self):
        text = STATE.replace('status = "download-complete"', 'status   =   "download-complete"  # dnf5')
        self.assertIn('status   =   "ready"  # dnf5', helper.arm_text(text))

    def test_refuses_other_states(self):
        for status in ("ready", "download-incomplete", "transaction-incomplete"):
            with self.subTest(status), self.assertRaises(ValueError):
                helper.arm_text(STATE.replace("download-complete", status))
        with self.assertRaises(ValueError):
            helper.arm_text(STATE.replace("[offline-transaction-state]", "[something-else]"))
        with self.assertRaises(ValueError):
            helper.arm_text("not = [toml")

    def test_refuses_a_second_status_line(self):
        # e.g. a future state file with a nested table: never guess which line is meant
        text = STATE + '[offline-transaction-state.extra]\nstatus = "download-complete"\n'
        with self.assertRaises(ValueError):
            helper.arm_text(text)

    def test_arm_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "offline-transaction-state.toml")
            Path(path).write_text(STATE)
            os.chmod(path, 0o644)
            self.assertEqual(helper.arm(path), "ready")
            self.assertEqual(helper.state_status(path), "ready")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o644)
            self.assertEqual(helper.arm(path), "already ready")
            self.assertEqual(os.listdir(d), ["offline-transaction-state.toml"])   # no temporary files left
            with self.assertRaises(ValueError):
                helper.arm(os.path.join(d, "missing.toml"))

    def test_arm_command_exit_codes(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            path = os.path.join(d, "state.toml")
            self.assertEqual(helper.main(["arm", path]), 1)
            Path(path).write_text(STATE.replace("download-complete", "download-incomplete"))
            self.assertEqual(helper.main(["arm", path]), 1)
            self.assertEqual(helper.state_status(path), "download-incomplete")
            Path(path).write_text(STATE)
            self.assertEqual(helper.main(["arm", path]), 0)
            self.assertEqual(helper.state_status(path), "ready")

    def test_state_status(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.toml")
            self.assertEqual(helper.state_status(path), "none")
            Path(path).write_text("[broken")
            self.assertEqual(helper.state_status(path), "invalid")
            Path(path).write_text(STATE)
            self.assertEqual(helper.state_status(path), "download-complete")


class TransactionTests(unittest.TestCase):
    def test_summary_counts_incoming_packages(self):
        self.assertEqual(helper.summarize(TRANSACTION["rpms"], size=SIZES.__getitem__), (2, 949693))

    def test_missing_package_files_count_but_add_no_size(self):
        self.assertEqual(helper.summarize(TRANSACTION["rpms"], size=lambda p: (_ for _ in ()).throw(OSError())), (2, 0))

    def test_unreadable_transaction_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "transaction.json")
            self.assertEqual(helper.load_transaction(path), [])
            Path(path).write_text("{")
            self.assertEqual(helper.load_transaction(path), [])
            Path(path).write_text(json.dumps(TRANSACTION))
            self.assertEqual(len(helper.load_transaction(path)), 4)

    def test_prune_deletes_only_unused_rpms(self):
        with tempfile.TemporaryDirectory() as d:
            pkgs = os.path.join(d, "packages")
            os.mkdir(pkgs)
            rpms = [dict(r) for r in TRANSACTION["rpms"]]
            for r in rpms:
                if "package_path" in r:
                    r["package_path"] = os.path.join(pkgs, os.path.basename(r["package_path"]))
            transaction = os.path.join(d, "transaction.json")
            Path(transaction).write_text(json.dumps({"rpms": rpms, "version": "1.0"}))
            for name in ("jq-1.8.1-3.fc44.x86_64.rpm", "tzdata-2026c-2.fc44.noarch.rpm",
                         "firefox-150.0.1-1.fc44.x86_64.rpm", "notes.txt"):
                Path(pkgs, name).write_text("x")
            self.assertEqual(helper.prune(transaction, pkgs), ["firefox-150.0.1-1.fc44.x86_64.rpm"])
            self.assertEqual(sorted(os.listdir(pkgs)), ["jq-1.8.1-3.fc44.x86_64.rpm", "notes.txt",
                                                        "tzdata-2026c-2.fc44.noarch.rpm"])
            # No transaction: nothing is deleted.
            os.unlink(transaction)
            self.assertEqual(helper.prune(transaction, pkgs), [])
            self.assertEqual(len(os.listdir(pkgs)), 3)


class ChannelTests(unittest.TestCase):
    def test_channels(self):
        self.assertEqual(helper.channel_from_repos(REPOS), "stable")
        testing = json.loads(REPOS)
        testing[3]["is_enabled"] = True
        self.assertEqual(helper.channel_from_repos(json.dumps(testing)), "testing")
        self.assertEqual(helper.channel_from_repos(json.dumps(json.loads(REPOS)[:2])), "none")
        self.assertEqual(helper.channel_from_repos("error: no repos"), "none")


class StatusFileTests(unittest.TestCase):
    def test_typed_assignments(self):
        status = helper.merge_status({"channel": "stable", "state": "checking"},
                                     ["state=ready", "packages=2", "download_mb=0.9057", "armed=true",
                                      "staged_at=@now", "message=2 updates", "checked_at="], now=fixed_now)
        self.assertEqual(status, {"channel": "stable", "state": "ready", "packages": 2, "download_mb": 0.9,
                                  "armed": True, "staged_at": fixed_now(), "message": "2 updates",
                                  "checked_at": None, "updated_at": fixed_now()})

    def test_bad_assignments(self):
        for item in ("state=sleeping", "armed=yes", "packages=two", "no-equals", "Bad=1"):
            with self.subTest(item), self.assertRaises(ValueError):
                helper.merge_status({}, [item])

    def test_file_is_world_readable_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "lib", "arctic", "update-status.json")
            helper.write_status(path, ["state=checking", "message=Checking for updates…"])
            helper.write_status(path, ["state=idle"])
            data = json.loads(Path(path).read_text())
            self.assertEqual((data["state"], data["message"]), ("idle", "Checking for updates…"))
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o644)


class ReportTests(unittest.TestCase):
    SETTINGS = dict(helper.DEFAULTS)

    def report(self, status_file=None, state="none", armed=False, offline="", busy=False, settings=None):
        return helper.build_report(status_file or {}, settings or self.SETTINGS, state, armed,
                                   TRANSACTION["rpms"], "stable", offline, busy, size=SIZES.__getitem__)

    def test_armed_update(self):
        r = self.report({"state": "ready", "checked_at": fixed_now()}, state="ready", armed=True, offline="stored")
        self.assertEqual((r["state"], r["packages"], r["download_mb"], r["armed"], r["stored"]),
                         ("ready", 2, 0.9, True, True))
        self.assertIn("next time you restart", r["message"])
        text = helper.format_report(r)
        self.assertIn("2 updates (0.9 MB), installed the next time you restart", text)
        self.assertIn("stable", text)

    def test_download_only(self):
        r = self.report({"state": "ready"}, state="download-complete",
                        settings={"AUTO": "download-only", "METERED": "skip"})
        self.assertEqual((r["state"], r["armed"], r["auto"]), ("ready", False, "download-only"))
        self.assertIn("arctic-update apply", helper.format_report(r))

    def test_invalidated_by_a_dnf_transaction(self):
        # dnf5 removes /system-update and leaves status "ready": not armed any more.
        r = self.report({"state": "ready"}, state="ready", armed=False)
        self.assertEqual((r["state"], r["armed"], r["stored"]), ("idle", False, False))
        self.assertIn("downloaded again", r["message"])
        r = self.report({"state": "ready"}, state="download-complete", offline="stale")
        self.assertEqual(r["state"], "idle")

    def test_installed_at_the_last_restart(self):
        r = self.report({"state": "ready", "packages": 2}, state="none")
        self.assertEqual((r["state"], r["packages"], r["armed"]), ("idle", 0, False))

    def test_interrupted_check(self):
        self.assertEqual(self.report({"state": "downloading"}, busy=True)["state"], "downloading")
        r = self.report({"state": "downloading"}, busy=False)
        self.assertEqual(r["state"], "failed")
        self.assertIn("stopped", helper.format_report(r))

    def test_never_checked(self):
        r = self.report()
        self.assertEqual((r["state"], r["checked_at"]), ("idle", None))
        self.assertIn("Last check  never", helper.format_report(r))

    def test_report_command_reads_the_files(self):
        with tempfile.TemporaryDirectory() as d:
            datadir = os.path.join(d, "offline")
            os.mkdir(datadir)
            Path(datadir, "offline-transaction-state.toml").write_text(STATE.replace("download-complete", "ready"))
            Path(datadir, "transaction.json").write_text(json.dumps(TRANSACTION))
            magic = os.path.join(d, "system-update")
            os.symlink(datadir, magic)
            status = os.path.join(d, "update-status.json")
            helper.write_status(status, ["state=ready", "checked_at=@now"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                helper.main(["report", "--json", "--channel", "testing", "--status-file", status,
                             "--conf", os.path.join(d, "missing.conf"),
                             "--state", os.path.join(datadir, "offline-transaction-state.toml"),
                             "--transaction", os.path.join(datadir, "transaction.json"),
                             "--magic", magic, "--datadir", datadir])
            r = json.loads(out.getvalue())
            self.assertEqual((r["state"], r["packages"], r["armed"], r["channel"], r["auto"]),
                             ("ready", 2, True, "testing", "download-and-install-on-reboot"))


FAKE_DNF5 = '''#!/bin/sh
# dnf5 as arctic-update's status needs it
case "$*" in
  *"repo list"*) cat "$FAKE_REPOS" ;;
  *"offline status"*) echo "No offline transaction is stored." ;;
  *) echo "fake dnf5: $*" >&2; exit 1 ;;
esac
'''


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class CommandTests(unittest.TestCase):
    """arctic-update itself, with a fake dnf5 in PATH (nothing on this machine changes)."""

    def run_cli(self, *args):
        with tempfile.TemporaryDirectory() as d:
            bindir = os.path.join(d, "bin")
            os.mkdir(bindir)
            Path(bindir, "dnf5").write_text(FAKE_DNF5)
            os.chmod(os.path.join(bindir, "dnf5"), 0o755)
            Path(d, "repos.json").write_text(REPOS)
            env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""),
                       FAKE_REPOS=os.path.join(d, "repos.json"),
                       ARCTIC_UPDATE_HELPER=str(HERE / "arctic-update-helper"),
                       ARCTIC_UPDATE_CONF=os.path.join(d, "update.conf"),
                       ARCTIC_UPDATE_STATUS=os.path.join(d, "update-status.json"),
                       LC_ALL="C.UTF-8")
            return subprocess.run(["bash", str(ROOT / "dotfiles/.local/bin/arctic-update"), *args],
                                  env=env, capture_output=True, text=True, timeout=60)

    def test_status_json(self):
        p = self.run_cli("status", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        r = json.loads(p.stdout)
        self.assertEqual(r["channel"], "stable")
        self.assertIn(r["state"], ("idle", "ready"))   # "ready" only on a machine with a staged update

    def test_status_text(self):
        p = self.run_cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Channel", p.stdout)
        self.assertIn("stable (released builds)", p.stdout)

    def test_help_and_unknown_commands(self):
        p = self.run_cli("help")
        self.assertEqual(p.returncode, 0)
        for command in ("status", "now", "apply", "channel", "auto", "metered"):
            self.assertIn(command, p.stdout)
        p = self.run_cli("frobnicate")
        self.assertEqual(p.returncode, 2)
        p = self.run_cli("channel", "beta")
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
