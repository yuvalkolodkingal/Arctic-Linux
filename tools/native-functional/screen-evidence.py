#!/usr/bin/env python3
"""Copy only bounded, owned synthetic VM diagnostics, screening text for uploads."""
import argparse
from array import array
from bisect import bisect_left, bisect_right
import hashlib
import json
from pathlib import Path
import re
import tempfile

TEXT = {'.json', '.log', '.txt', '.tsv'}
BINARY = {'.png', '.rgb', '.wav'}
SENSITIVE = re.compile(r'(?i)(?:gh[pousr]_|github_pat_)[a-z0-9_]+'
                       r'|AKIA[A-Z0-9]{16}|authorization:\s*\S+(?:\s+\S+)?'
                       r'|[\w.+-]+@[\w.-]+\.[a-z]{2,}'
                       r'|https?://[^\s"<>]*\?[^\s"<>]*')

# These four literal tokens are attested in the original public calibration
# job 37971533836. This is deliberately not a Fedora host or .service allowlist.
FEDORA_METADATA = tuple('https://mirrors.fedoraproject.org/metalink?repo=' + repo + '&arch=x86_64'
                        for repo in ('fedora-44', 'updates-released-f44', 'fedora-cisco-openh264-44'))
ZRAM_UNIT = 'systemd-zram-setup@zram0.service'
# Ten public literal instances derived from package-verified Fedora 44 local
# image inventories (systemd/systemd-udev 259.9-1.fc44). The fixture records
# template/dependency hashes and provenance limits. This does not reconstruct
# historical tokens or prove exact target ISO versions/signatures/runtime.
CANONICAL_UNITS = (
    ('modprobe@configfs.service', 'Load Kernel Module configfs'),
    ('modprobe@fuse.service', 'Load Kernel Module fuse'),
    ('modprobe@drm.service', 'Load Kernel Module drm'),
    ('modprobe@loop.service', 'Load Kernel Module loop'),
    ('modprobe@dm_mod.service', 'Load Kernel Module dm_mod'),
    ('modprobe@efi_pstore.service', 'Load Kernel Module efi_pstore'),
    ('user@1000.service', 'User Manager for UID 1000'),
    ('user-runtime-dir@1000.service', 'User Runtime Directory /run/user/1000'),
    ('getty@tty1.service', 'Getty on tty1'),
    ('getty@tty6.service', 'Getty on tty6'),
    ('serial-getty@ttyS0.service', 'Serial Getty on ttyS0'),
)
# Cmd.String in internal/installer/runner.go replaces the secret argument with
# this fixed label. The exact synthetic benchmark command is also attested in
# original job 37971533836 line 441; it contains no password or password hash.
PASSWORD_MASK = '[secret: password hash]'
PASSPHRASE_MASK = '[secret: disk passphrase]'
BENCHMARK_USERADD = ("$ useradd --root /mnt --create-home --user-group --groups wheel "
    "--shell /usr/bin/fish --comment 'Arctic CI' --password " + PASSWORD_MASK + ' ci')
# The active GUI harness fixes this account and uses the same real installer
# Cmd.String renderer. This is source-derived, not observed target UART proof;
# no arbitrary account, command or secret-mask spelling receives an exception.
ACTIVE_USERADD = ("$ useradd --root /mnt --create-home --user-group --groups wheel "
    "--shell /usr/bin/fish --comment 'Arctic Qualification' --password " + PASSWORD_MASK + ' arcticqual')
SGR = re.compile(r'\x1b\[[0-9;:]*m')
TERMINAL = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]'
    r'|\x1b\][^\x1b\x07\r\n]*(?:\x07|\x1b\\)'
    r'|\x1b[PX^_][^\x1b\r\n]*\x1b\\'
    r'|\x1b(?![\[\]PX^_])[ -/]*[0-~]')
STRING_PAYLOADS = re.compile(r'\x1b(?:\]([^\x1b\x07\r\n]*)(?:\x07|\x1b\\)'
    r'|[PX^_]([^\x1b\r\n]*)\x1b\\)')
JOB_PREFIX = r'(?:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z )?'
DNF_PREFIX = JOB_PREFIX + r'(?:  \| )?'
KERNEL_PREFIX = JOB_PREFIX + r'\[ *\d+\.\d+\] systemd\[1\]: '
BENCHMARK_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
BENCHMARK_CRYPTSETUP = (
    re.escape('$ cryptsetup luksFormat --batch-mode --type luks2 --pbkdf argon2id '
        '--label arctic-root --key-file - /dev/vda4 < ' + PASSPHRASE_MASK),
    re.escape('$ cryptsetup open --allow-discards --key-file - /dev/vda4 luks-') +
        BENCHMARK_UUID + re.escape(' < ' + PASSPHRASE_MASK),
)
EXTERNAL_SENSITIVE = re.compile(SENSITIVE.pattern +
    r'|https?://[^\s"<>]*@[^\s"<>]+'
    r'|["\']?\b(?:password|passwd|token|access_token|refresh_token|api_key|client_secret|secret)["\']?\s*[:=]\s*[^\s,}]+'
    r'|--(?:password|token|api-key)\s+(?!\[secret: password hash\])\S+'
    r'|\bcryptsetup (?:luksFormat|open) [^\r\n]* < (?!\[secret: disk passphrase\])\S+'
    r'|(?:transcript|transcription|transcribed(?:\s+text)?|recognized\s+text|dictation\s+(?:text|result)'
    r'|תמלול|תמליל|טקסט\s+מזוהה)["\']?\s*[:=]')

# These are the original alternatives in their original order. Classification
# receives only the already rejected Match, never a second read of the member.
EXTERNAL_RULE_ALTERNATIVES = (
    ('github-credential', r'(?:gh[pousr]_|github_pat_)[a-z0-9_]+'),
    ('aws-credential', r'AKIA[A-Z0-9]{16}'),
    ('authorization', r'authorization:\s*\S+(?:\s+\S+)?'),
    ('email-shape', r'[\w.+-]+@[\w.-]+\.[a-z]{2,}'),
    ('queried-url', r'https?://[^\s"<>]*\?[^\s"<>]*'),
    ('credential-url', r'https?://[^\s"<>]*@[^\s"<>]+'),
    ('named-secret', r'["\']?\b(?:password|passwd|token|access_token|refresh_token|api_key|client_secret|secret)["\']?\s*[:=]\s*[^\s,}]+'),
    ('secret-option', r'--(?:password|token|api-key)\s+(?!\[secret: password hash\])\S+'),
    ('disk-secret-input', r'\bcryptsetup (?:luksFormat|open) [^\r\n]* < (?!\[secret: disk passphrase\])\S+'),
    ('transcription-label', r'(?:transcript|transcription|transcribed(?:\s+text)?|recognized\s+text|dictation\s+(?:text|result)|תמלול|תמליל|טקסט\s+מזוהה)["\']?\s*[:=]'),
)
EXTERNAL_RULES = tuple((label, re.compile('(?i)' + pattern)) for label, pattern in EXTERNAL_RULE_ALTERNATIVES)
EXTERNAL_RULE_PHASES = ('source-view', 'terminal-view', 'terminal-payload')
MAX_DIAGNOSTIC_MATCH_BYTES = 16 * 1024
EXTERNAL_EMAIL_CANDIDATES = tuple((literal, 'unit-' + format(index, '03d'))
    for index, literal in enumerate((*[unit for unit, _ in CANONICAL_UNITS], ZRAM_UNIT), 1))


def diagnose_sensitive_match(match, phase, original=None, boundaries=None, removed=None):
    """Only a closed category from the same rejected match; no value or path."""
    if type(phase) is not str or phase not in EXTERNAL_RULE_PHASES:
        return
    label = 'unknown-rule'
    if type(match) is re.Match and match.end(0) - match.start(0) <= MAX_DIAGNOSTIC_MATCH_BYTES:
        # Check offsets before copying. Even non-ASCII conversion is bounded by
        # four times this budget; overflow keeps the original rejection below.
        value = match.group(0)
        if len(value.encode('utf-8')) <= MAX_DIAGNOSTIC_MATCH_BYTES:
            for candidate, rule in EXTERNAL_RULES:
                if rule.fullmatch(value):
                    label = candidate
                    break
    print('ARCTIC-EVIDENCE-RULE=' + phase + '-' + label, flush=True)
    if label == 'email-shape':
        candidate = 'unknown-unit'
        # A regex may end at a public prefix inside a malformed private token.
        # Only delimiter-bounded, contiguous original public bytes get an ID;
        # this observation still leaves the original rejection in force.
        start, end = match.span()
        delimiters = ' \t\r\n:'
        bounded = ((start == 0 or match.string[start - 1] in delimiters)
            and (end == len(match.string) or match.string[end] in delimiters))
        if bounded and type(original) is str and type(boundaries) is array and type(removed) is array:
            first, last = original_span(start, end, boundaries, removed)
            if last - first == len(value) and original[first:last] == value:
                for literal, identifier in EXTERNAL_EMAIL_CANDIDATES:
                    if value == literal:
                        candidate = identifier
                        break
        print('ARCTIC-EVIDENCE-EMAIL-CANDIDATE=' + phase + '-' + candidate, flush=True)


def reject_sensitive_match(match, phase, original=None, boundaries=None, removed=None):
    error = RuntimeError('Sensitive text in external evidence')
    try:
        diagnose_sensitive_match(match, phase, original, boundaries, removed)
    except Exception:
        pass  # Optional observations cannot replace the original rejection.
    raise error


def classification_view(value, *, escapes=SGR):
    """Remove SGR for classification, mapping only escape boundaries compactly."""
    # A text member is at most 128 MiB: Unicode offsets fit unsigned 32-bit
    # integers. Store two integers per SGR, never an object per text character.
    # Other terminal escapes stay in the scanned view and confer no exemption.
    boundaries, removed = array('I'), array('I')
    count = 0
    for sgr in escapes.finditer(value):
        boundaries.append(sgr.start() - count)
        count += sgr.end() - sgr.start()
        removed.append(count)
    return escapes.sub('', value), boundaries, removed


def original_span(start, end, boundaries, removed):
    # Adjacent decorations at token start belong to the context; decorations
    # at token end do too. Any SGR strictly inside the token remains in its
    # original slice, causing the literal-contiguity check to reject it.
    first = bisect_right(boundaries, start)
    last = bisect_left(boundaries, end)
    return (start + (removed[first - 1] if first else 0),
            end + (removed[last - 1] if last else 0))


def public_token_spans(line):
    """Identify match and literal-proof spans in exact observed message forms."""
    spans = set()
    # BEGIN EXACT_PUBLIC_CONFIGFS_UNIT
    # Actual same-Match observation unit-001 attests this public unit only.
    # Preserve the existing delimiter and original-contiguity checks; no
    # substring, other unit, or complete-line exception is granted.
    for match in EXTERNAL_SENSITIVE.finditer(line):
        start, end = match.span()
        delimiters = ' \t\r\n:'
        if (end - start == len('modprobe@configfs.service')
                and match.group(0) == 'modprobe@configfs.service'
                and (start == 0 or line[start - 1] in delimiters)
                and (end == len(line) or line[end] in delimiters)):
            spans.add((start, end, start, end))
    # END EXACT_PUBLIC_CONFIGFS_UNIT
    for url in FEDORA_METADATA:
        quoted = re.escape(url)
        dns = ('Curl error \\(6\\): Could not resolve hostname for ' + quoted +
               r' \[Could not resolve host: mirrors\.fedoraproject\.org\]')
        messages = (
            DNF_PREFIX + r'>>> (?:Download failed: )?' + dns +
                r'(?: - ' + quoted + r'|,Cannot prepare internal mirrorlist: Parse error at line: 1 \(Document is empty)?',
            DNF_PREFIX + r'Failed to download metadata \(metalink: "' + quoted +
                r'"\) for repository "(?:fedora|updates|fedora-cisco-openh264)": Download failed: ' + dns,
            DNF_PREFIX + r'>>> Curl error \(7\): Could not connect to server for ' + quoted +
                # The observed 2 ms latency varies; only a bounded decimal
                # field varies, never the host, port, message or URL spelling.
                r' \[Failed to connect to mirrors\.fedoraproject\.org port 443 after (?:0|[1-9][0-9]{0,5}) ms: '
                r'Could not connect to server\] - ' + quoted,
        )
        if any(re.fullmatch(message, line) for message in messages):
            spans.update((match.start(), match.end(), match.start(), match.end())
                for match in re.finditer(quoted, line))
    unit = re.escape(ZRAM_UNIT)
    messages = (
        KERNEL_PREFIX + r'Stopping ' + unit + r' - Create swap on /dev/zram0\.\.\.',
        KERNEL_PREFIX + r'Stopped ' + unit + r' - Create swap on /dev/zram0\.',
        KERNEL_PREFIX + unit + r': Deactivated successfully\.',
        JOB_PREFIX + r'\[  OK  \] Stopped ' + unit + r' - Create swap on /dev/zram0\.',
    )
    if any(re.fullmatch(message, line) for message in messages):
        spans.update((match.start(), match.end(), match.start(), match.end())
            for match in re.finditer(unit, line))
    for literal, description in CANONICAL_UNITS:
        unit, description = re.escape(literal), re.escape(description)
        lifecycle = (r'(?:Starting|Stopping) ' + unit + ' - ' + description + r'\.\.\.'
            r'|(?:Started|Finished|Stopped) ' + unit + ' - ' + description + r'\.')
        messages = (
            KERNEL_PREFIX + '(?:' + lifecycle + ')',
            JOB_PREFIX + r'(?:\[  OK  \] | {9})(?:' + lifecycle + ')',
            KERNEL_PREFIX + unit + r': Deactivated successfully\.',
        )
        if any(re.fullmatch(message, line) for message in messages):
            spans.update((match.start(), match.end(), match.start(), match.end())
                for match in re.finditer(unit, line))
    if any(re.fullmatch(JOB_PREFIX + re.escape(command), line)
            for command in (BENCHMARK_USERADD, ACTIVE_USERADD)):
        proof = re.search(re.escape(PASSWORD_MASK), line)
        sensitive = re.search(re.escape('secret: password'), line)
        spans.add((sensitive.start(), sensitive.end(), proof.start(), proof.end()))
    if any(re.fullmatch(JOB_PREFIX + command, line) for command in BENCHMARK_CRYPTSETUP):
        proof = re.search(re.escape(PASSPHRASE_MASK), line)
        sensitive = re.search(re.escape('secret: disk'), line)
        spans.add((sensitive.start(), sensitive.end(), proof.start(), proof.end()))
    return spans


def external_text(content):
    """Reject sensitive evidence; return original bytes, never redacted bytes."""
    value = content.decode('utf-8')
    view, boundaries, removed = classification_view(value)
    allowed = set()
    # Iterate records without allocating a list/object for every empty UART
    # line. Bare CR progress updates cannot supply another record's context.
    for record in re.finditer(r'[^\r\n]+', view):
        for start, end, proof_start, proof_end in public_token_spans(record.group()):
            start, end = start + record.start(), end + record.start()
            proof_start, proof_end = proof_start + record.start(), proof_end + record.start()
            # ANSI inside a token is not an attested token. Only context may be
            # decorated; original token bytes must equal their literal spelling.
            original_start, original_end = original_span(start, end, boundaries, removed)
            original_proof_start, original_proof_end = original_span(proof_start, proof_end, boundaries, removed)
            if value[original_proof_start:original_proof_end] == view[proof_start:proof_end]:
                allowed.add((original_start, original_end))
    def require_safe(scanned, boundaries, removed, phase='source-view'):
        if any(original_span(*match.span(), boundaries, removed) not in allowed and (rejected := match)
                for match in EXTERNAL_SENSITIVE.finditer(scanned)):
            # Never include the matched private value in this error or upload.
            reject_sensitive_match(rejected, phase, value, boundaries, removed)
    # Scan OSC/DCS payloads before removing complete terminal bookkeeping.
    require_safe(view, boundaries, removed)
    if '\x1b' in view:
        for frame in STRING_PAYLOADS.finditer(view):
            payload = frame.group(1) if frame.group(1) is not None else frame.group(2)
            # DCS/SOS/APC introduce a word character (P/X/_) that must not
            # conceal a credential's leading word boundary. Payloads receive
            # no public-token exception, even if invisible on the terminal.
            if (rejected := EXTERNAL_SENSITIVE.search(payload)):
                reject_sensitive_match(rejected, 'terminal-payload')
        terminal_view, terminal_boundaries, terminal_removed = classification_view(value, escapes=TERMINAL)
        if '\x1b' in terminal_view:
            raise RuntimeError('Incomplete terminal escape in external evidence')
        # A second scan catches private labels/tokens split by CSI/OSC/DCS.
        # Public exceptions still originate only in the strict SGR view and
        # must map to the same contiguous original literal token bytes.
        require_safe(terminal_view, terminal_boundaries, terminal_removed, 'terminal-view')
    return content


EXTERNAL_MEMBER_DIAGNOSTICS = {
    'execution.json': 'execution',
    'provision.log': 'provision',
    'capture-build.log': 'capture-build',
    'installer-harness.log': 'installer-harness',
    'host/host-execution.json': 'installer-host-execution',
    'host/installer-host-transitions.json': 'installer-transitions',
    'host/serial.log': 'installer-live-uart',
    'host/serial-installed.log': 'installer-installed-uart',
    'host/installed-boot.json': 'installer-installed-proof',
    'installer/installer-report.json': 'installer-report',
    'installer/serial-installer-report.json': 'installer-serial-report',
    'installer/installer-state.json': 'installer-state',
    'installer/installer-provenance.json': 'installer-provenance',
    'installer/transport-manifest.json': 'installer-transport',
}


def diagnose_external_member(relative, error):
    """Source-closed member/rejection labels; never print any path or message."""
    role = EXTERNAL_MEMBER_DIAGNOSTICS.get(relative, 'other-text') if type(relative) is str else 'other-text'
    reason = 'other-error'
    if type(error) is RuntimeError and type(error.args) is tuple and len(error.args) == 1 and type(error.args[0]) is str:
        if error.args[0] == 'Sensitive text in external evidence':
            reason = 'sensitive-text'
        elif error.args[0] == 'Incomplete terminal escape in external evidence':
            reason = 'incomplete-terminal'
    print('ARCTIC-EVIDENCE-DIAGNOSTIC=external-text-' + role + '-rejection-' + reason, flush=True)


# Exact paths emitted by the Native runner; an unknown filename stays private.
# These labels only identify a strict decoding rejection, never its byte value,
# offset, exception text, or whether any Native acceptance record was complete.
UTF8_MEMBER_DIAGNOSTICS = {
    'execution.json': 'native-execution',
    'native-harness.log': 'native-harness',
    'provision.log': 'native-provision',
    'taskbar-build.log': 'native-taskbar-build',
    'harness/serial-install.log': 'native-live-uart',
    'harness/serial-boot.log': 'native-installed-uart',
    'harness/native-evidence-install.log': 'native-live-bulk',
    'harness/native-evidence-boot.log': 'native-installed-bulk',
    'harness/qemu-install.log': 'native-live-qemu',
    'harness/qemu-boot.log': 'native-installed-qemu',
    'harness/test.log': 'native-driver',
    'native-live/gui-trace.log': 'native-live-gui-trace',
    'native-installed/gui-trace.log': 'native-installed-gui-trace',
}

# BEGIN NATIVE_UTF8_MEMBER_INVENTORY
# Additional fixed writers in runner.py, test-install.sh, evidence.py and the
# pinned Native checker. These labels confer no format/privacy exception.
UTF8_MEMBER_DIAGNOSTICS.update({
    'vm-prepared-image-id.txt': 'native-tool-image-id',
    'vm-prepared-image-owner.json': 'native-tool-image-owner',
    'taskbar-display-capabilities.txt': 'native-display-capabilities',
    'native-stages.json': 'native-stage-results',
    'harness/vm-toolchain.txt': 'native-vm-toolchain',
    'harness/native-audio-capabilities.txt': 'native-audio-capabilities',
    'harness/test-install-stage.log': 'native-install-driver',
    'virtual-audio/native-audio-install.json': 'native-live-audio-receipt',
    'virtual-audio/native-audio-boot.json': 'native-installed-audio-receipt',
})
for _native_stage, _vm_stage in (('live', 'install'), ('installed', 'boot')):
    for _filename, _role in (
        ('native-stop-' + _vm_stage + '.json', 'stop'),
        ('taskbar-display-' + _vm_stage + '.json', 'display-receipt'),
        ('native-physical-' + _native_stage + '.log', 'physical-host'),
        ('native-editor-save-' + _native_stage + '.log', 'editor-host'),
    ):
        UTF8_MEMBER_DIAGNOSTICS['harness/' + _filename] = 'native-' + _native_stage + '-' + _role
    for _filename, _role in (
        ('report.json', 'report'),
        ('transport-manifest.json', 'transport-manifest'),
        ('serial-native-report.json', 'serial-report'),
        ('serial-native-provenance.json', 'provenance'),
        ('physical-host-receipt.json', 'physical-receipt'),
        ('editor-save-host-receipt.json', 'editor-receipt'),
        ('0-native-protocol-viewport.json', 'protocol-receipt'),
        ('0-controlled-renderer-trials.json', 'renderer-trial-receipt'),
        ('gui-trace-summary.json', 'gui-summary'),
        ('final-clients.json', 'final-clients'),
        ('fullscreen-player-receipts.json', 'fullscreen-receipts'),
        ('fullscreen-player-captures.json', 'fullscreen-captures'),
        ('moving-player-proof.json', 'moving-player'),
        ('visual-oracle.json', 'visual-oracle'),
        ('terminal-role.json', 'terminal-role'),
        ('file-manager-terminal.json', 'file-manager-terminal'),
        ('files with spaces/editor fixture.txt', 'editor-fixture'),
        ('archive source/Unicode-\u05e9.txt', 'archive-unicode-fixture'),
    ):
        UTF8_MEMBER_DIAGNOSTICS['native-' + _native_stage + '/' + _filename] = 'native-' + _native_stage + '-' + _role
    for _archive_kind in ('zip', '7z', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', 'tar.zst', 'cpio', '7z-encrypted'):
        UTF8_MEMBER_DIAGNOSTICS['native-' + _native_stage + '/extracted ' + _archive_kind + '/Unicode-\u05e9.txt'] = 'native-' + _native_stage + '-archive-unicode-extract'
    # Every numbered launch log remains in the export root. At most 128 guest
    # files are admitted; the two subordinate renderer launches can advance
    # self.launches without creating these logs. No number is printed.
    for _launch_index in range(130):
        UTF8_MEMBER_DIAGNOSTICS['native-' + _native_stage + '/gui-launch-' + str(_launch_index) + '.log'] = 'native-' + _native_stage + '-gui-launch'
for _filename, _role in (
    ('transport-manifest.json', 'transport'),
    ('taskbar-report.json', 'report'),
    ('serial-taskbar-report.json', 'serial-report'),
    ('serial-taskbar-provenance.json', 'provenance'),
    ('taskbar-state.json', 'state'),
    ('gui-trace.log', 'gui-trace'),
    ('gui-trace-summary.json', 'gui-summary'),
    ('final-clients.json', 'final-clients'),
):
    UTF8_MEMBER_DIAGNOSTICS['taskbar/' + _filename] = 'native-taskbar-' + _role
del _native_stage, _vm_stage, _filename, _role, _archive_kind, _launch_index
# END NATIVE_UTF8_MEMBER_INVENTORY


def diagnose_invalid_utf8_member(relative):
    """Emit only a fixed role and reason; no error contents are inspected."""
    role = UTF8_MEMBER_DIAGNOSTICS.get(relative, 'other-text') if type(relative) is str else 'other-text'
    print('ARCTIC-EVIDENCE-DIAGNOSTIC=utf8-' + role + '-rejection-invalid-utf8', flush=True)


# BEGIN PUBLIC_NATIVE_BINARY_ARCHIVE_FIXTURE
# The public archive roundtrip intentionally includes NUL and 0xff in a .txt
# fixture. Only its finite, source-bound extractor destinations and public bytes
# receive a binary format; arbitrary text and changed fixtures stay rejected.
PUBLIC_NATIVE_BINARY_PATHS = frozenset((
    'native-live/archive source/nested directory/hello world.txt',
    'native-installed/archive source/nested directory/hello world.txt',
    'native-live/extracted zip/nested directory/hello world.txt',
    'native-installed/extracted zip/nested directory/hello world.txt',
    'native-live/extracted 7z/nested directory/hello world.txt',
    'native-installed/extracted 7z/nested directory/hello world.txt',
    'native-live/extracted tar/nested directory/hello world.txt',
    'native-installed/extracted tar/nested directory/hello world.txt',
    'native-live/extracted tar.gz/nested directory/hello world.txt',
    'native-installed/extracted tar.gz/nested directory/hello world.txt',
    'native-live/extracted tar.bz2/nested directory/hello world.txt',
    'native-installed/extracted tar.bz2/nested directory/hello world.txt',
    'native-live/extracted tar.xz/nested directory/hello world.txt',
    'native-installed/extracted tar.xz/nested directory/hello world.txt',
    'native-live/extracted tar.zst/nested directory/hello world.txt',
    'native-installed/extracted tar.zst/nested directory/hello world.txt',
    'native-live/extracted cpio/nested directory/hello world.txt',
    'native-installed/extracted cpio/nested directory/hello world.txt',
    'native-live/extracted 7z-encrypted/nested directory/hello world.txt',
    'native-installed/extracted 7z-encrypted/nested directory/hello world.txt',
))
PUBLIC_NATIVE_BINARY_BYTES = b'Arctic archive roundtrip\n\x00\xff\n'
PUBLIC_NATIVE_BINARY_SHA256 = 'c9d50f54b92301a97f875d92dff1900e82942dafb5af5404c9feda6183a97bc4'


def public_native_binary_format(relative, content):
    if type(relative) is not str or relative not in PUBLIC_NATIVE_BINARY_PATHS:
        return None
    if (type(content) is not bytes or content != PUBLIC_NATIVE_BINARY_BYTES
            or hashlib.sha256(content).hexdigest() != PUBLIC_NATIVE_BINARY_SHA256):
        raise RuntimeError('Native public binary archive fixture bytes differ')
    return dict(schema='arctic-native-public-binary-fixture-v1',
                source_format='binary-archive-roundtrip', bytes=28,
                sha256=PUBLIC_NATIVE_BINARY_SHA256, release_acceptance=False)
# END PUBLIC_NATIVE_BINARY_ARCHIVE_FIXTURE


def copy_screened(source, target, *, external=False):
    files = sorted(source.rglob('*'))
    if len(files) > 1000:
        raise RuntimeError('Too many diagnostic members')
    manifest = dict(scope='Owned synthetic QEMU VM only; no host desktop, VM disks or credentials', files={})
    total = 0
    for path in files:
        if path.is_symlink():
            raise RuntimeError('Diagnostic symlinks are forbidden')
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeError('Diagnostic members must be regular files')
        if path.suffix not in TEXT | BINARY and not path.name.endswith('.bounded-prefix.bin'):
            raise RuntimeError('Unexpected diagnostic file type: ' + path.name)
        size = path.stat().st_size
        total += size
        if size > 128 * 1024 * 1024 or total > 512 * 1024 * 1024:
            raise RuntimeError('Diagnostic byte bounds exceeded')
        content = path.read_bytes()
        original = hashlib.sha256(content).hexdigest()
        redactions = 0
        source_format = public_native_binary_format(path.relative_to(source).as_posix(), content)
        if path.suffix in TEXT and source_format is None:
            if external:
                try:
                    content = external_text(content)
                except Exception as error:
                    try:
                        diagnose_external_member(path.relative_to(source).as_posix(), error)
                    except Exception:
                        pass  # Optional observations cannot replace the original rejection.
                    raise
            else:
                try:
                    value = content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        diagnose_invalid_utf8_member(path.relative_to(source).as_posix())
                    except BaseException:
                        pass  # A diagnostic failure cannot replace the strict original decode rejection.
                    raise
                value, redactions = SENSITIVE.subn('[redacted]', value)
                content = value.encode()
        relative = path.relative_to(source)
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        manifest['files'][relative.as_posix()] = dict(original_sha256=original,
                uploaded_sha256=hashlib.sha256(content).hexdigest(), bytes=len(content), redactions=redactions)
        if source_format is not None:
            manifest.setdefault('source_formats', {})[relative.as_posix()] = source_format
    (target / 'upload-screening.json').write_text(json.dumps(manifest, indent=2) + '\n')


def screen(source, target, *, external=False):
    if not source.exists():
        return
    if source.is_symlink() or not source.is_dir() or target.exists():
        raise RuntimeError('Diagnostics must be an owned directory and upload path unused')
    # No partial directory is published if any screening or bounds check fails.
    with tempfile.TemporaryDirectory(prefix='arctic-screening-', dir=target.parent) as staging:
        stage = Path(staging)
        copy_screened(source, stage, external=external)
        stage.rename(target)


def screen_external(source, target):
    """Original-byte evidence must preserve every complete original member."""
    screen(source, target, external=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--preserve-original', action='store_true',
        help='Preserve complete original bytes; reject unknown sensitive text instead of redacting')
    args = parser.parse_args()
    screen(args.source, args.out, external=args.preserve_original)


if __name__ == '__main__':
    main()
