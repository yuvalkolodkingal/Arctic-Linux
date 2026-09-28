"""Tests for arctic-update-helper (the file handling behind arctic-update), and scenario tests
of arctic-update itself: every system path under a scratch directory (ARCTIC_UPDATE_TEST_ROOT)
and a scripted dnf5, systemctl, rpm and journalctl in PATH (testdata/fake-dnf5). Nothing on
this machine changes. test-dnf5-offline.sh runs the same flow with the real dnf5 (CI).

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
import unittest.mock
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


class OfflineClassTests(unittest.TestCase):
    def test_from_the_state_file(self):
        self.assertEqual(helper.offline_class("none"), "none")
        self.assertEqual(helper.offline_class("download-incomplete"), "none")   # dnf5: nothing stored
        self.assertEqual(helper.offline_class("invalid"), "invalid")
        self.assertEqual(helper.offline_class("transaction-incomplete"), "incomplete")
        self.assertEqual(helper.offline_class("some-future-status"), "unknown")

    def test_pending_uses_dnf5_only_for_stale(self):
        for status in helper.PENDING:
            with self.subTest(status):
                self.assertEqual(helper.offline_class(status, OFFLINE_STATUS["stored"]), "stored")
                self.assertEqual(helper.offline_class(status, OFFLINE_STATUS["stale"]), "stale")
                # Reworded, empty or unexpected output: trust the state file (dnf5 checks the
                # rpmdb cookie again at the boot).
                self.assertEqual(helper.offline_class(status, "Eine Offline-Transaktion …"), "stored")
                self.assertEqual(helper.offline_class(status, ""), "stored")
                self.assertEqual(helper.offline_class(status, OFFLINE_STATUS["unknown"]), "stored")

    def test_command_reads_stdin_only_when_pending(self):
        for status, text, want in (("ready", OFFLINE_STATUS["stale"], "stale"), ("none", OFFLINE_STATUS["stale"], "none")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), unittest.mock.patch("sys.stdin", io.StringIO(text)):
                helper.main(["offline-class", status])
            self.assertEqual(out.getvalue().strip(), want)


class OwnerTests(unittest.TestCase):
    def table(self, **changes):
        return dict(helper.load_state(STATE), **changes)

    def test_ours(self):
        self.assertEqual(helper.owner("download-complete", self.table()), "ours")
        sync = self.table(verb="distro-sync", cmd_line="dnf5 distro-sync --offline -y --refresh")
        self.assertEqual(helper.owner("ready", sync), "ours")
        self.assertFalse(helper.held("ready", sync))

    def test_foreign(self):
        for changes in ({"cmd_line": "dnf5 -y install --offline --refresh arctic-other", "verb": "install"},
                        {"cmd_line": "dnf upgrade --offline -y --refresh"},            # not ours, even if similar
                        {"cmd_line": "/usr/bin/dnf5 upgrade --offline -y --refresh"},
                        {"cmd_line": "dnf5daemon-server"},                             # GNOME Software & co.
                        {"verb": "distro-sync"},                                       # cmd_line and verb disagree
                        {"target_releasever": "45"},                                   # a release upgrade
                        {"cmd_line": "dnf5 system-upgrade download --releasever=45", "verb": "system-upgrade download",
                         "target_releasever": "45"}):
            with self.subTest(changes):
                table = self.table(**changes)
                self.assertEqual(helper.owner("download-complete", table), "foreign")
                for status in ("download-complete", "ready", "transaction-incomplete", "some-future-status"):
                    self.assertTrue(helper.held(status, table), status)
                # dnf5 itself treats a half-written one as nothing stored
                self.assertFalse(helper.held("download-incomplete", table))

    def test_nothing_stored(self):
        self.assertEqual(helper.owner("none", {}), "none")
        self.assertEqual(helper.owner("invalid", {}), "none")
        self.assertFalse(helper.held("invalid", {}))

    def test_inspect(self):
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "offline-transaction-state.toml")
            magic = os.path.join(d, "system-update")
            self.assertEqual(helper.inspect(state, magic, d),
                             {"status": "none", "owner": "none", "hold": "no", "linked": "no", "cmd_line": ""})
            Path(state).write_text(STATE.replace("dnf5 upgrade --offline -y --refresh",
                                                 "dnf5 install --offline ./a\\nb.rpm").replace('"upgrade"', '"install"'))
            os.symlink(d, magic)
            r = helper.inspect(state, magic, d)
            self.assertEqual((r["status"], r["owner"], r["hold"], r["linked"]),
                             ("download-complete", "foreign", "yes", "yes"))
            self.assertEqual(r["cmd_line"], "dnf5 install --offline ./a b.rpm")   # one line


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

    def test_disarm_is_the_reverse(self):
        armed = helper.arm_text(STATE)
        self.assertEqual(helper.disarm_text(armed), STATE)
        with self.assertRaises(ValueError):
            helper.disarm_text(STATE)   # not ready
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.toml")
            Path(path).write_text(armed)
            self.assertEqual(helper.disarm(path), "download-complete")
            self.assertEqual(helper.disarm(path), "already download-complete")
            self.assertEqual(Path(path).read_text(), STATE)

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

    def test_transaction_key_follows_the_incoming_packages(self):
        key = helper.transaction_key(TRANSACTION["rpms"])
        self.assertEqual(len(key), 16)
        self.assertEqual(helper.transaction_key(list(reversed(TRANSACTION["rpms"]))), key)
        fewer = [r for r in TRANSACTION["rpms"] if not r["nevra"].startswith("jq-1.8.1-3")]
        self.assertNotEqual(helper.transaction_key(fewer), key)
        self.assertEqual(helper.transaction_key([]), "")

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


class ReadyTests(unittest.TestCase):
    def assignments(self, old, rpms=None, armed=True, message=None):
        return helper.merge_status(old, helper.ready_assignments(old, rpms or TRANSACTION["rpms"], armed, message,
                                                                 size=SIZES.__getitem__), now=fixed_now)

    def test_new_download(self):
        s = self.assignments({})
        self.assertEqual((s["state"], s["packages"], s["download_mb"], s["armed"], s["staged_at"]),
                         ("ready", 2, 0.9, True, fixed_now()))
        self.assertEqual(s["notify_key"], helper.transaction_key(TRANSACTION["rpms"]))
        self.assertEqual(s["message"], "2 updates will be installed the next time you restart.")
        self.assertIn("arctic-update apply", self.assignments({}, armed=False)["message"])

    def test_same_updates_keep_staged_at(self):
        first = dict(self.assignments({}), staged_at="2026-09-20T06:00:00+00:00")
        again = self.assignments(first, message="The last check failed; …")
        self.assertEqual(again["staged_at"], "2026-09-20T06:00:00+00:00")
        self.assertEqual(again["message"], "The last check failed; …")
        more = TRANSACTION["rpms"] + [{"nevra": "kernel-7.1.0-1.fc44.x86_64", "action": "Install"}]
        self.assertEqual(self.assignments(first, rpms=more)["staged_at"], fixed_now())


class BootCheckTests(unittest.TestCase):
    ARMED = {"armed": True, "armed_boot": "boot-1", "armed_at": "2026-09-27T21:37:00+00:00"}

    def test_same_boot_or_not_armed(self):
        self.assertEqual(helper.boot_check(self.ARMED, "ready", True, "boot-1"), ("none", 0))
        self.assertEqual(helper.boot_check(dict(self.ARMED, armed=False), "none", False, "boot-2"), ("none", 0))
        self.assertEqual(helper.boot_check({}, "transaction-incomplete", False, "boot-2"), ("none", 0))
        self.assertEqual(helper.boot_check(self.ARMED, "none", False, ""), ("none", 0))   # boot id unknown

    def test_after_a_restart(self):
        since = helper.epoch(self.ARMED["armed_at"])
        self.assertEqual(since, 1790545020)
        self.assertEqual(helper.boot_check(self.ARMED, "none", False, "boot-2"), ("installed", since))
        self.assertEqual(helper.boot_check(self.ARMED, "transaction-incomplete", False, "boot-2"), ("incomplete", since))
        self.assertEqual(helper.boot_check(self.ARMED, "ready", False, "boot-2"), ("not-started", since))
        # still scheduled (the boot didn't go through system-update.target): nothing yet
        self.assertEqual(helper.boot_check(self.ARMED, "ready", True, "boot-2"), ("none", 0))


class ReportTests(unittest.TestCase):
    SETTINGS = dict(helper.DEFAULTS)

    def report(self, status_file=None, state="none", armed=False, offline="", busy=False, settings=None, table=None):
        if table is None and state not in ("none", "invalid"):
            table = dict(helper.load_state(STATE), status=state)
        return helper.build_report(status_file or {}, settings or self.SETTINGS, state, armed,
                                   TRANSACTION["rpms"], "stable", offline, busy, size=SIZES.__getitem__, table=table)

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

    def test_someone_elses_transaction(self):
        table = dict(helper.load_state(STATE), cmd_line="dnf5 system-upgrade download --releasever=45",
                     verb="system-upgrade download", target_releasever="45")
        r = self.report({"state": "ready", "armed": True}, state="download-complete", armed=False, table=table)
        self.assertEqual((r["state"], r["armed"], r["stored"], r["packages"]), ("idle", False, False, 0))
        self.assertEqual(r["held"], "dnf5 system-upgrade download --releasever=45")
        self.assertIn("arctic-update leaves it alone", r["message"])
        self.assertIn("dnf5 offline reboot", helper.format_report(r))
        r = self.report({}, state="transaction-incomplete", table=dict(table, status="transaction-incomplete"))
        self.assertIn("didn't finish", r["message"])

    def test_failed_install_at_the_last_restart(self):
        r = self.report({"state": "ready", "boot_failures": 1, "install_error": "Transaction failed: rpm error",
                         "install_failed_at": fixed_now()}, state="ready", armed=True, offline="stored")
        self.assertEqual((r["state"], r["boot_failures"]), ("ready", 1))
        text = helper.format_report(r)
        self.assertIn("Last restart", text)
        self.assertIn("Transaction failed: rpm error", text)
        paused = self.report({"state": "failed", "boot_failures": 2, "message": "Installing updates failed …"},
                             state="transaction-incomplete")
        self.assertEqual((paused["state"], paused["message"]), ("failed", "Installing updates failed …"))

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


FAKE_TOOLS = {
    # systemctl: the offline unit is wanted; arctic-firstboot runs while fake/firstboot-running
    # counts down; everything else succeeds. Every call is logged.
    "systemctl": r'''#!/bin/sh
echo "$*" >> "$ARCTIC_UPDATE_TEST_ROOT/fake/systemctl.log"
case "$*" in
  *"Wants --value system-update.target"*) echo "dnf5-offline-transaction.service" ;;
  *"SubState --value arctic-firstboot.service"*)
    f="$ARCTIC_UPDATE_TEST_ROOT/fake/firstboot-running"
    n=$(cat "$f" 2>/dev/null || echo 0)
    if [ "$n" -gt 0 ]; then echo $((n - 1)) > "$f"; echo running; else echo dead; fi ;;
esac
exit 0
''',
    "rpm": '#!/bin/sh\ncat "$ARCTIC_UPDATE_TEST_ROOT/fake/rpmdb" 2>/dev/null\n',
    "journalctl": '#!/bin/sh\ncat "$ARCTIC_UPDATE_TEST_ROOT/fake/journal" 2>/dev/null\nexit 0\n',
    "nmcli": '#!/bin/sh\ncase "$*" in *METERED*) echo no ;; *CONNECTIVITY*) echo full ;; esac\n',
}
UPDATES = [["jq-1.8.1-3.fc44.x86_64", "Upgrade"], ["tzdata-2026c-2.fc44.noarch", "Upgrade"]]
NEWER = [["jq-1.8.1-4.fc44.x86_64", "Upgrade"], ["tzdata-2026c-2.fc44.noarch", "Upgrade"]]
OURS = "dnf5 upgrade --offline -y --refresh"
FOREIGN = "dnf5 -y install --offline --refresh arctic-other"


@unittest.skipUnless(shutil.which("bash") and shutil.which("flock"), "needs bash and flock")
class ScenarioTests(unittest.TestCase):
    """arctic-update with every path under a scratch root and a scripted dnf5 (testdata/fake-dnf5)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        bindir = self.path("fake/bin")
        os.makedirs(bindir)
        os.symlink(HERE / "testdata/fake-dnf5", os.path.join(bindir, "dnf5"))
        for name, text in FAKE_TOOLS.items():
            Path(bindir, name).write_text(text)
            os.chmod(os.path.join(bindir, name), 0o755)
        self.write("proc/sys/kernel/random/boot_id", "boot-1\n")
        self.write("proc/cmdline", "BOOT_IMAGE=/vmlinuz-7.1.0 root=UUID=1234 ro rhgb quiet\n")
        self.write("usr/lib/systemd/system/system-update.target.wants/dnf5-offline-transaction.service", "")
        self.write("fake/rpmdb", "jq-1.8.1-2.fc44.x86_64 1780000000\n")
        env = {k: v for k, v in os.environ.items()
               if k not in ("INVOCATION_ID", "ARCTIC_UPDATE_CONF", "ARCTIC_UPDATE_STATUS")}
        self.env = dict(env, PATH=bindir + os.pathsep + os.environ.get("PATH", ""),
                        ARCTIC_UPDATE_TEST_ROOT=self.root, ARCTIC_UPDATE_HELPER=str(HERE / "arctic-update-helper"),
                        LC_ALL="C.UTF-8")

    def tearDown(self):
        self.tmp.cleanup()

    # ---- the scratch root --------------------------------------------------------------------
    def path(self, rel):
        return os.path.join(self.root, rel)

    def write(self, rel, text):
        os.makedirs(os.path.dirname(self.path(rel)), exist_ok=True)
        Path(self.path(rel)).write_text(text)

    def scenario(self, **s):
        self.write("fake/dnf5.json", json.dumps(s))

    def cli(self, *args, rc=0):
        p = subprocess.run(["bash", str(ROOT / "dotfiles/.local/bin/arctic-update"), *args],
                           env=self.env, capture_output=True, text=True, timeout=120)
        if rc is not None:
            self.assertEqual(p.returncode, rc, f"arctic-update {' '.join(args)}\n{p.stdout}\n{p.stderr}")
        return p

    @property
    def state_file(self):
        return self.path("usr/lib/sysimage/libdnf5/offline/offline-transaction-state.toml")

    def state(self):
        return helper.read_state(self.state_file)

    def status(self):
        return helper.read_json(self.path("var/lib/arctic/update-status.json"))

    def linked(self):
        return helper.is_armed(self.path("system-update"), self.path("usr/lib/sysimage/libdnf5/offline"))

    def calls(self, tool="dnf5"):
        try:
            return Path(self.path(f"fake/{tool}.log")).read_text().splitlines()
        except FileNotFoundError:
            return []

    def packages(self):
        try:
            return sorted(os.listdir(self.path("var/lib/dnf/offline/packages")))
        except FileNotFoundError:
            return []

    def store_foreign(self, cmd=FOREIGN, verb="install", status="download-complete", target="44"):
        """What `dnf5 -y install --offline --refresh arctic-other` (or another command) leaves."""
        pkg = self.path("var/lib/dnf/offline/packages/arctic-other-1-2.noarch.rpm")
        self.write("var/lib/dnf/offline/packages/arctic-other-1-2.noarch.rpm", "x")
        self.write("usr/lib/sysimage/libdnf5/offline/transaction.json", json.dumps(
            {"rpms": [{"nevra": "arctic-other-1-2.noarch", "action": "Install", "package_path": pkg}], "version": "1.0"}))
        self.write("usr/lib/sysimage/libdnf5/offline/offline-transaction-state.toml",
                   STATE.replace(OURS, cmd).replace('verb = "upgrade"', f'verb = "{verb}"')
                   .replace('status = "download-complete"', f'status = "{status}"')
                   .replace('target_releasever = "44"', f'target_releasever = "{target}"'))

    def staged(self):
        """The daily check has downloaded UPDATES and scheduled them."""
        self.scenario(updates=UPDATES)
        self.cli("stage")
        self.assertEqual(self.state()[0], "ready")
        self.assertTrue(self.linked())

    def reboot(self, boot="boot-2"):
        self.write("proc/sys/kernel/random/boot_id", boot + "\n")

    # ---- the daily check -----------------------------------------------------------------
    def test_downloads_and_schedules(self):
        self.staged()
        s = self.status()
        self.assertEqual((s["state"], s["packages"], s["armed"], s["armed_boot"]), ("ready", 2, True, "boot-1"))
        self.assertEqual(s["message"], "2 updates will be installed the next time you restart.")
        self.assertEqual(self.state()[1]["cmd_line"], OURS)
        self.assertIn(OURS[len("dnf5 "):], self.calls())
        r = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual((r["state"], r["armed"], r["packages"]), ("ready", True, 2))

    def test_up_to_date(self):
        self.scenario(updates=None)
        self.cli("stage")
        self.assertEqual((self.state()[0], self.linked(), self.status()["state"]), ("none", False, "idle"))

    def test_nothing_to_do_keeps_its_own_update_scheduled(self):
        # An unreachable repository looks like "Nothing to do": what was downloaded stays.
        self.staged()
        self.scenario(updates=None)
        self.cli("stage")
        self.assertEqual((self.state()[0], self.linked(), self.status()["state"]), ("ready", True, "ready"))

    def test_nothing_to_do_drops_its_own_stale_update(self):
        self.staged()
        self.scenario(updates=None, stale=True)   # updated by hand since
        self.cli("stage")
        self.assertEqual((self.state()[0], self.linked(), self.status()["state"]), ("none", False, "idle"))
        self.assertIn("-q offline clean", self.calls())

    def test_stale_update_is_replaced(self):
        self.staged()
        os.unlink(self.path("system-update"))    # a dnf transaction invalidated it
        self.scenario(updates=NEWER, stale=True)
        self.cli("stage")
        self.assertEqual((self.state()[0], self.linked()), ("ready", True))
        self.assertEqual(self.status()["packages"], 2)
        # the package no longer needed is gone, the one still needed was reused
        self.assertEqual(self.packages(), ["jq-1.8.1-4.fc44.x86_64.rpm", "tzdata-2026c-2.fc44.noarch.rpm"])
        self.assertNotIn("-q offline clean", self.calls())

    def test_failed_check_keeps_the_update_scheduled(self):
        self.staged()
        before = self.status()
        self.scenario(updates=UPDATES, fail="Error: Failed to download metadata for repo 'updates'")
        p = self.cli("stage", rc=1)
        self.assertIn("Failed to download metadata", p.stderr)
        s = self.status()
        self.assertEqual((self.state()[0], self.linked(), s["state"], s["armed"]), ("ready", True, "ready", True))
        self.assertEqual(s["staged_at"], before["staged_at"])
        self.assertIn("last check failed", s["message"])

    def test_same_updates_are_announced_once(self):
        self.staged()
        first = self.status()
        self.cli("stage")                           # the next day: the same updates, stored again
        self.assertEqual((self.status()["staged_at"], self.status()["notify_key"]),
                         (first["staged_at"], first["notify_key"]))
        self.scenario(updates=NEWER)
        self.cli("stage")
        self.assertNotEqual(self.status()["notify_key"], first["notify_key"])

    def test_software_installed_during_the_check(self):
        self.scenario(updates=UPDATES, rpmdb_changes=1)
        p = self.cli("stage")
        self.assertIn("checking again", p.stdout)
        self.assertEqual(sum(c.startswith("upgrade --offline") for c in self.calls()), 2)
        self.assertEqual((self.state()[0], self.linked()), ("ready", True))

    def test_software_installed_during_every_check(self):
        self.staged()
        self.scenario(updates=NEWER, rpmdb_changes=5)
        self.cli("stage", rc=1)
        self.assertEqual(sum(c.startswith("upgrade --offline") for c in self.calls()), 4)   # 1 + 3
        self.assertEqual((self.state()[0], self.linked(), self.status()["state"]), ("none", False, "failed"))

    # ---- someone else's offline transaction ------------------------------------------------
    def test_someone_elses_transaction_is_left_alone(self):
        self.store_foreign()
        before = Path(self.state_file).read_text()
        for updates in (UPDATES, None):
            with self.subTest(updates=updates):
                self.scenario(updates=updates)
                self.cli("stage")
                self.assertEqual(Path(self.state_file).read_text(), before)
                self.assertFalse(os.path.lexists(self.path("system-update")))
                self.assertEqual(self.packages(), ["arctic-other-1-2.noarch.rpm"])
                self.assertFalse([c for c in self.calls() if "--offline" in c or "offline clean" in c])
                s = self.status()
                self.assertEqual((s["state"], s["armed"]), ("idle", False))
                self.assertIn(f"prepared with '{FOREIGN}'", s["message"])
        r = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual((r["state"], r["held"]), ("idle", FOREIGN))

    def test_release_upgrade_download_is_left_alone(self):
        self.store_foreign(cmd="dnf5 system-upgrade download --releasever=45 -y",
                           verb="system-upgrade download", target="45")
        self.scenario(updates=UPDATES)
        self.cli("stage")
        self.assertEqual((self.state()[0], self.state()[1]["target_releasever"]), ("download-complete", "45"))
        self.assertFalse(os.path.lexists(self.path("system-update")))
        # even an upgrade command line with another release is someone else's
        self.store_foreign(cmd=OURS, verb="upgrade", target="45")
        self.cli("stage")
        self.assertEqual(self.state()[1]["target_releasever"], "45")

    def test_failed_foreign_transaction_is_left_alone(self):
        self.store_foreign(status="transaction-incomplete")
        self.scenario(updates=UPDATES)
        self.cli("stage")
        self.assertEqual(self.state()[0], "transaction-incomplete")
        self.assertIn("didn't finish", self.status()["message"])

    def test_now_refuses_someone_elses_transaction_unless_replace(self):
        self.store_foreign()
        self.scenario(updates=UPDATES)
        p = self.cli("now", rc=1)
        self.assertIn(f"prepared with '{FOREIGN}'", p.stderr)
        self.assertIn("arctic-update now --replace", p.stderr)
        self.assertEqual(self.state()[1]["cmd_line"], FOREIGN)
        self.cli("now", "--replace")
        self.assertEqual((self.state()[1]["cmd_line"], self.state()[0], self.linked()), (OURS, "ready", True))
        self.assertEqual(self.packages(), ["jq-1.8.1-3.fc44.x86_64.rpm", "tzdata-2026c-2.fc44.noarch.rpm"])

    def test_now_replace_with_nothing_to_do_removes_it(self):
        self.store_foreign(status="ready")
        self.scenario(updates=None)
        self.cli("now", "--replace")
        self.assertEqual((self.state()[0], self.linked()), ("none", False))

    def test_apply_and_channel_refuse_someone_elses_transaction(self):
        self.store_foreign()
        p = self.cli("apply", "--yes", rc=1)
        self.assertIn("dnf5 offline reboot", p.stderr)
        self.assertNotIn("offline reboot -y", self.calls())
        p = self.cli("channel", "testing", rc=1)
        self.assertIn("arctic-update channel testing --replace", p.stderr)
        self.assertFalse([c for c in self.calls() if "config-manager" in c])
        self.assertEqual(self.state()[1]["cmd_line"], FOREIGN)
        self.cli("channel", "testing", "--replace")
        self.assertTrue([c for c in self.calls() if "config-manager setopt" in c])
        self.assertEqual(self.state()[0], "none")

    def test_arm_refused_when_the_link_belongs_to_another_tool(self):
        os.makedirs(self.path("var/lib/other-tool"))
        os.symlink(self.path("var/lib/other-tool"), self.path("system-update"))
        self.scenario(updates=UPDATES)
        p = self.cli("stage", rc=1)
        self.assertIn("belongs to another offline update tool", p.stderr)
        self.assertEqual(os.readlink(self.path("system-update")), self.path("var/lib/other-tool"))
        self.assertEqual((self.state()[0], self.status()["state"]), ("download-complete", "failed"))

    # ---- after a restart -------------------------------------------------------------------
    def test_installed_at_the_restart(self):
        self.staged()
        self.write("fake/dnf5.json", json.dumps({"updates": None}))
        # dnf5-offline-transaction.service installed it and cleaned up
        subprocess.run(["dnf5", "offline", "clean"], env=self.env, check=True)
        self.reboot()
        p = self.cli("stage")
        self.assertIn("were installed", p.stdout)
        s = self.status()
        self.assertEqual((s["state"], s["armed"], s["boot_failures"]), ("idle", False, 0))

    def fail_at_boot(self, boot):
        """dnf5 offline _execute started the transaction at the boot and it failed."""
        Path(self.state_file).write_text(Path(self.state_file).read_text().replace('"ready"', '"transaction-incomplete"'))
        os.unlink(self.path("system-update"))
        self.write("fake/journal", "Running transaction\nTransaction failed: Rpm transaction failed.\n"
                                   "  - package arctic-bad-1-2.noarch: %pre scriptlet failed, exit status 1\n")
        self.reboot(boot)

    def test_failed_install_is_recorded_and_tried_once_more(self):
        self.staged()
        self.fail_at_boot("boot-2")
        p = self.cli("stage")
        self.assertIn("weren't installed (attempt 1)", p.stderr)
        s = self.status()
        self.assertEqual((s["boot_failures"], s["state"], s["armed"]), (1, "ready", True))
        self.assertIn("%pre scriptlet failed", s["install_error"])
        self.assertTrue(s["install_failed_at"])
        self.assertIn("-q offline clean", self.calls())
        self.assertTrue(self.linked())
        self.assertIn("Last restart", self.cli("status").stdout)

        # The second restart fails too: automatic installs stop.
        self.fail_at_boot("boot-3")
        calls = len(self.calls())
        self.cli("stage")
        s = self.status()
        self.assertEqual((s["boot_failures"], s["state"], s["armed"]), (2, "failed", False))
        self.assertIn("aren't scheduled automatically", s["message"])
        self.assertFalse(os.path.lexists(self.path("system-update")))
        self.assertFalse([c for c in self.calls()[calls:] if "--offline" in c])
        self.assertEqual(json.loads(self.cli("status", "--json").stdout)["state"], "failed")
        self.cli("stage")                           # and the day after
        self.assertFalse(os.path.lexists(self.path("system-update")))

        # Until you check by hand.
        self.cli("now")
        s = self.status()
        self.assertEqual((s["boot_failures"], s["state"], s["armed"], s["install_error"]), (0, "ready", True, None))
        self.assertTrue(self.linked())

    def test_refused_at_the_boot_is_a_failure(self):
        # dnf5 found the system changed since the download: the link is gone, still "ready".
        self.staged()
        os.unlink(self.path("system-update"))
        self.write("fake/journal", "The system has been modified since the offline transaction was prepared.\n")
        self.reboot()
        self.scenario(updates=UPDATES, stale=True)
        self.cli("stage")
        self.assertEqual(self.status()["boot_failures"], 1)

    def test_invalidated_before_the_restart_is_not_a_failure(self):
        # A dnf transaction removed the link before the restart: nothing ran at the boot.
        self.staged()
        os.unlink(self.path("system-update"))
        self.reboot()
        self.scenario(updates=UPDATES, stale=True)
        self.cli("stage")
        s = self.status()
        self.assertEqual((s.get("boot_failures") or 0, s["state"], s["armed"]), (0, "ready", True))

    # ---- settings --------------------------------------------------------------------------
    def test_auto_off_unschedules_but_keeps_the_download(self):
        self.staged()
        p = self.cli("auto", "off")
        self.assertIn("arctic-update apply", p.stdout)
        self.assertEqual((self.state()[0], self.linked()), ("download-complete", False))
        self.assertEqual(self.packages(), ["jq-1.8.1-3.fc44.x86_64.rpm", "tzdata-2026c-2.fc44.noarch.rpm"])
        self.assertIn("disable --now arctic-update-stage.timer", self.calls("systemctl"))
        r = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual((r["state"], r["armed"], r["auto"]), ("ready", False, "off"))
        self.cli("auto", "on")
        self.assertEqual((self.state()[0], self.linked()), ("ready", True))

    def test_download_only(self):
        self.write("etc/arctic/update.conf", "AUTO=download-only\n")
        self.scenario(updates=UPDATES)
        self.cli("stage")
        self.assertEqual((self.state()[0], self.linked(), self.status()["armed"]), ("download-complete", False, False))
        # scheduled by hand: the next daily check keeps it scheduled
        self.cli("now")
        self.assertTrue(self.linked())
        self.cli("stage")
        self.assertEqual((self.state()[0], self.linked()), ("ready", True))

    def test_waits_for_firstboot(self):
        self.write("fake/firstboot-running", "3")
        self.scenario(updates=UPDATES)
        p = self.cli("stage")
        self.assertIn("Waiting for arctic-firstboot.service", p.stdout)
        self.assertTrue(self.linked())
        self.write("fake/firstboot-running", "1000")
        os.unlink(self.path("fake/dnf5.log"))
        p = self.cli("stage")
        self.assertIn("still installing apps", p.stdout)
        self.assertFalse([c for c in self.calls() if "--offline" in c])

    def test_live_session(self):
        self.write("proc/cmdline", "BOOT_IMAGE=/images/pxeboot/vmlinuz root=live:CDLABEL=Arctic rd.live.image quiet\n")
        self.scenario(updates=UPDATES)
        self.assertIn("Live session", self.cli("stage").stdout)
        self.assertIn("live session", self.cli("now", rc=1).stderr)
        self.assertFalse([c for c in self.calls() if "--offline" in c])

    # ---- dnf's post-transaction hook ----------------------------------------------------------
    def test_after_transaction_hook(self):
        p = self.cli("after-transaction")
        self.assertEqual((p.stdout, p.stderr), ("", ""))
        self.assertEqual(self.calls("systemctl"), [])
        self.staged()
        p = self.cli("after-transaction")
        self.assertEqual((p.stdout, p.stderr), ("", ""))
        self.assertIn("start --no-block arctic-update-restage.timer", self.calls("systemctl"))
        # the offline boot's own transaction, and someone else's: nothing
        for status in ("transaction-incomplete",):
            Path(self.state_file).write_text(Path(self.state_file).read_text().replace('"ready"', f'"{status}"'))
            os.unlink(self.path("fake/systemctl.log"))
            self.cli("after-transaction")
            self.assertNotIn("start --no-block arctic-update-restage.timer", self.calls("systemctl"))
        self.store_foreign()
        self.cli("after-transaction")
        self.assertNotIn("start --no-block arctic-update-restage.timer", self.calls("systemctl"))

    # ---- the plain commands ----------------------------------------------------------------
    def test_status_text_and_help(self):
        p = self.cli()
        self.assertIn("stable (released builds)", p.stdout)
        self.assertIn("Last check  never", p.stdout)
        p = self.cli("help")
        for command in ("status", "now", "apply", "channel", "auto", "metered", "--replace", "--sync"):
            self.assertIn(command, p.stdout)
        self.cli("frobnicate", rc=2)
        self.cli("channel", "beta", rc=2)
        self.cli("now", "--sideways", rc=2)

    @unittest.skipUnless(os.geteuid() == 0, "only root under systemd ignores the test root")
    def test_test_root_is_ignored_for_root_under_systemd(self):
        env = dict(self.env, INVOCATION_ID="0123456789abcdef")
        p = subprocess.run(["bash", str(ROOT / "dotfiles/.local/bin/arctic-update"), "help"],
                           env=env, capture_output=True, text=True, timeout=60)
        self.assertIn("ignoring ARCTIC_UPDATE_TEST_ROOT", p.stderr)

    # ---- Flatpak apps and firmware ------------------------------------------------------------
    def fake_flatpak(self, fail=False):
        """flatpak: `list` prints fake/flatpak-list; `update` bumps one app's commit (or fails)."""
        self.write("fake/flatpak-list", "org.gimp.GIMP\taaa111\ndev.zed.Zed\tbbb222\n")
        script = textwrap.dedent('''\
            #!/bin/sh
            echo "$*" >> "$ARCTIC_UPDATE_TEST_ROOT/fake/flatpak.log"
            case "$1" in
              list) cat "$ARCTIC_UPDATE_TEST_ROOT/fake/flatpak-list" ;;
              update)
                if [ -n "{fail}" ]; then echo "Looking for updates…"; echo "error: Unable to connect to dl.flathub.org"; exit 1; fi
                sed -i 's/aaa111/ccc333/' "$ARCTIC_UPDATE_TEST_ROOT/fake/flatpak-list" ;;
            esac
            exit 0
            ''').format(fail="yes" if fail else "")
        self.write("fake/bin/flatpak", script)
        os.chmod(self.path("fake/bin/flatpak"), 0o755)

    def test_flatpak_apps_update_daily(self):
        self.fake_flatpak()
        p = self.cli("flatpak", "--auto")
        self.assertIn("1 app updated.", p.stdout)
        self.assertIn("update --system --noninteractive -y", self.calls("flatpak"))
        self.assertIn("uninstall --system --unused --noninteractive -y", self.calls("flatpak"))
        status = helper.read_json(self.path("var/lib/arctic/flatpak-status.json"))
        self.assertEqual((status["state"], status["apps_updated"]), ("idle", 1))
        report = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual((report["apps"]["updated"], report["apps"]["state"]), (1, "idle"))
        self.assertIn("Flatpak apps", self.cli("status").stdout)
        # Nothing new the next day.
        self.assertIn("up to date", self.cli("flatpak", "--auto").stdout)

    def test_flatpak_follows_the_settings(self):
        self.fake_flatpak()
        for conf in ("AUTO=off\n", "AUTO=download-only\n"):
            self.write("etc/arctic/update.conf", conf)
            self.assertIn("when you run arctic-update flatpak", self.cli("flatpak", "--auto").stdout)
        self.write("etc/arctic/update.conf", "AUTO=download-and-install-on-reboot\n")
        self.write("fake/bin/nmcli", '#!/bin/sh\ncase "$*" in *METERED*) echo yes ;; *CONNECTIVITY*) echo full ;; esac\n')
        self.assertIn("Metered connection", self.cli("flatpak", "--auto").stdout)
        self.assertFalse([c for c in self.calls("flatpak") if c.startswith("update")])
        # By hand it updates anyway; on the live USB the timer's run does nothing.
        self.cli("flatpak")
        self.assertTrue([c for c in self.calls("flatpak") if c.startswith("update")])
        self.write("proc/cmdline", "BOOT_IMAGE=/images/pxeboot/vmlinuz rd.live.image quiet\n")
        self.assertEqual(self.cli("flatpak", "--auto").stdout, "")
        self.cli("flatpak", "--sideways", rc=2)

    def test_flatpak_user_installation(self):
        self.fake_flatpak()
        self.env["XDG_STATE_HOME"] = self.path("home-state")
        self.env["HOME"] = self.path("home")
        os.makedirs(self.path("home/.local/share/flatpak"))
        self.assertIn("1 app updated.", self.cli("flatpak", "--auto", "--user").stdout)
        self.assertIn("update --user --noninteractive -y", self.calls("flatpak"))
        self.assertFalse([c for c in self.calls("flatpak") if c.startswith("update --system")])
        status = helper.read_json(self.path("home-state/arctic/flatpak-update.json"))
        self.assertEqual(status["apps_updated"], 1)
        self.assertFalse(os.path.exists(self.path("var/lib/arctic/flatpak-status.json")))

    def test_flatpak_failure_is_recorded(self):
        self.fake_flatpak(fail=True)
        p = self.cli("flatpak", "--auto", rc=1)
        self.assertIn("Unable to connect to dl.flathub.org", p.stdout)
        status = helper.read_json(self.path("var/lib/arctic/flatpak-status.json"))
        self.assertEqual(status["state"], "failed")
        self.assertFalse([c for c in self.calls("flatpak") if c.startswith("uninstall")])

    def test_firmware(self):
        self.write("fake/bin/fwupdmgr", textwrap.dedent('''\
            #!/bin/sh
            echo "$*" >> "$ARCTIC_UPDATE_TEST_ROOT/fake/fwupdmgr.log"
            [ -e "$ARCTIC_UPDATE_TEST_ROOT/fake/fw-none" ] && exit 2
            echo '{"Devices": [{"Name": "System Firmware", "Vendor": "LENOVO", "Version": "0.1.40",
              "Flags": ["updatable", "needs-reboot"], "Releases": [{"Version": "0.1.42", "Summary": "Lenovo ThinkPad BIOS"}]}]}'
            '''))
        os.chmod(self.path("fake/bin/fwupdmgr"), 0o755)
        fw = json.loads(self.cli("firmware", "--json").stdout)
        self.assertEqual(fw["devices"], [{"name": "System Firmware", "vendor": "LENOVO", "version": "0.1.40",
                                          "update": "0.1.42", "summary": "Lenovo ThinkPad BIOS", "reboot": True}])
        self.assertIn("System Firmware: 0.1.40 → 0.1.42", self.cli("firmware").stdout)
        self.write("fake/fw-none", "")
        fw = json.loads(self.cli("firmware", "--json").stdout)
        self.assertEqual((fw["available"], fw["devices"]), (True, []))
        self.cli("firmware", "flash", rc=2)


class FirmwareParseTests(unittest.TestCase):
    def test_no_daemon(self):
        fw = helper.parse_firmware('{"Error": {"Domain": "g-io-error-quark", "Code": 1, "Message": "Failed to connect to daemon"}}')
        self.assertEqual((fw["available"], fw["error"]), (False, "Failed to connect to daemon"))

    def test_nothing_to_update(self):
        self.assertEqual(helper.parse_firmware('{"Devices": []}')["devices"], [])
        self.assertTrue(helper.parse_firmware("No updatable devices")["available"])
        self.assertFalse(helper.parse_firmware("")["available"])

    def test_devices_without_releases_are_skipped(self):
        fw = helper.parse_firmware(json.dumps({"Devices": [{"Name": "Keyboard", "Releases": []},
                                                           {"Name": "Dock\x1b[31m", "Version": "1", "Releases": [{"Version": "2"}]}]}))
        self.assertEqual([(d["name"], d["update"], d["reboot"]) for d in fw["devices"]], [("Dock [31m", "2", False)])

    def test_apps_report(self):
        self.assertIsNone(helper.apps_report({}))
        r = helper.apps_report({"checked_at": fixed_now(), "apps_updated": 3, "state": "idle"})
        self.assertEqual((r["updated"], r["state"]), (3, "idle"))


if __name__ == "__main__":
    unittest.main()
