#!/usr/bin/env python3
"""Failure-only, unqualified partial originals; never a privacy exception."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

HERE = Path(__file__).resolve().parent
SCANNER_SHA256 = '8b9fbbe3bb9241dca8232e7cee61e05fec10bfbb0bc1e9d0d62dbfb7bda8e8ea'
MAX_MEMBER = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_MATCH = 16 * 1024
# These are diagnostic candidates, not admitted privacy exceptions. The
# retained package-verified getty@.service template permits %I instances, and
# the exact guest returns to its discovered VT after explicitly visiting VT6.
# No alias, arbitrary instance, or unknown token is exported.
EXTRA_UNIT_CANDIDATES = tuple(('getty@tty' + str(n) + '.service', 'getty-template-tty' + str(n)) for n in range(2, 6)) + (
    ('modprobe@nvmet_tcp.service', 'vendor-unit-006'),
    ('modprobe@thunderbolt_net.service', 'vendor-unit-007'),
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scanner():
    path = HERE.parent / 'native-functional/screen-evidence.py'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SCANNER_SHA256:
        raise RuntimeError('Diagnostic scanner source binding differs')
    module = types.ModuleType('installer_partial_original_scanner')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


PUBLIC_LITERAL = 'serial-getty@ttyS0.service'
PUBLIC_LABEL = 'serial-getty-ttyS0-source-fragment'

def serial_source_fragment(scanner, match, phase, original=None, boundaries=None, removed=None):
    result = {'candidate': 'unknown', 'original_contiguous': False,
              'privacy_admitted': False, 'operand_digest': None,
              'whole_unit_or_runtime_cause_proven': False}
    if (type(phase) is not str or phase not in scanner.EXTERNAL_RULE_PHASES
            or type(match) is not re.Match or type(original) is not str
            or type(boundaries) is not scanner.array or type(removed) is not scanner.array
            or match.end() - match.start() != len(PUBLIC_LITERAL)):
        return result
    if match.group(0) != PUBLIC_LITERAL:
        return result
    if len(boundaries) != len(removed):
        return result
    first, last = scanner.original_span(match.start(), match.end(), boundaries, removed)
    if (type(first) is int and type(last) is int and 0 <= first <= last <= len(original)
            and last - first == len(PUBLIC_LITERAL)
            and original[first:last] == PUBLIC_LITERAL):
        result['candidate'] = PUBLIC_LABEL
        result['original_contiguous'] = True
    return result


# BEGIN SERIAL_SOURCE_CONTEXT_OBSERVATION
# Official systemd v259, peeled commit 9ca433482f2281d71718718705ca8cd3bf562ad6,
# src/shared/install.c: install_change_dump_success, "Removed '%s'." and
# "Unit %s is masked, ignoring.". Whole upstream bytes/provenance are retained
# in the Source fixture; these formats grant no privacy or runtime exemption.
SERIAL_CONTEXT_PATHS = (
    ('etc-getty-wants', '/etc/systemd/system/getty.target.wants/' + PUBLIC_LITERAL),
    ('etc-system-unit', '/etc/systemd/system/' + PUBLIC_LITERAL),
    ('run-system-unit', '/run/systemd/system/' + PUBLIC_LITERAL),
    ('run-generator-getty-wants', '/run/systemd/generator/getty.target.wants/' + PUBLIC_LITERAL),
    ('run-generator-early-getty-wants', '/run/systemd/generator.early/getty.target.wants/' + PUBLIC_LITERAL),
    ('run-generator-late-getty-wants', '/run/systemd/generator.late/getty.target.wants/' + PUBLIC_LITERAL),
)
SERIAL_NEIGHBORS = {
    ' ': 'ascii-space', '\t': 'ascii-tab', "'": 'ascii-single-quotation',
    '"': 'ascii-double-quotation', '[': 'ascii-open-square', ']': 'ascii-close-square',
    '(': 'ascii-open-parenthesis', ')': 'ascii-close-parenthesis',
    '{': 'ascii-open-brace', '}': 'ascii-close-brace', ':': 'ascii-colon',
    ';': 'ascii-semicolon', '.': 'ascii-period', '-': 'ascii-hyphen',
    '/': 'ascii-slash', '\\': 'ascii-backslash', '\x1b': 'terminal-escape',
    '=': 'ascii-equals', '!': 'ascii-exclamation', '#': 'ascii-hash',
    '$': 'ascii-dollar', '%': 'ascii-percent', '&': 'ascii-ampersand',
    '*': 'ascii-asterisk', '+': 'ascii-plus', ',': 'ascii-comma',
    '<': 'ascii-angle-open', '>': 'ascii-angle-close', '?': 'ascii-question',
    '@': 'ascii-at', '^': 'ascii-caret', '_': 'ascii-underscore',
    '`': 'ascii-grave', '|': 'ascii-pipe', '~': 'ascii-tilde',
    '\x00': 'terminal-nul', '\x07': 'terminal-bel', '\x08': 'terminal-backspace',
    '\x7f': 'terminal-delete',
}


def serial_source_context(m, match, phase, original=None, boundaries=None, removed=None):
    """Only exact whole public records and closed neighboring character classes."""
    result = dict(whole_record='unknown', preceding='unknown', following='unknown',
                  privacy_admitted=False, runtime_cause_proven=False)
    fragment = serial_source_fragment(m, match, phase, original, boundaries, removed)
    if fragment['candidate'] != PUBLIC_LABEL or not fragment['original_contiguous']:
        return result
    first, last = m.original_span(match.start(), match.end(), boundaries, removed)
    # Find the original record without stripping escapes or allocating an
    # unbounded private record. Unknown records never receive a hash or excerpt.
    left = max(original.rfind('\n', 0, first), original.rfind('\r', 0, first)) + 1
    candidates = [n for n in (original.find('\n', last), original.find('\r', last)) if n >= 0]
    right = min(candidates) if candidates else len(original)
    def neighbor(position):
        if not left <= position < right:
            return 'record-edge'
        value = original[position]
        return SERIAL_NEIGHBORS.get(value, 'ascii-alphanumeric' if value.isascii() and value.isalnum()
                                    else 'other-ascii' if value.isascii() else 'non-ascii')
    result['preceding'], result['following'] = neighbor(first - 1), neighbor(last)
    if right - left > 4096:
        return result
    record = original[left:right]
    # No timestamps, ANSI removal, arbitrary paths, suffixes or substitutions
    # are accepted by this finite whole-record attestation.
    for label, path in SERIAL_CONTEXT_PATHS:
        if record == "Removed '" + path + "'.":
            result['whole_record'] = 'official-install-unlink-' + label
            return result
    if record == 'Unit ' + PUBLIC_LITERAL + ' is masked, ignoring.':
        result['whole_record'] = 'official-install-masked-serial-unit'
    return result
# END SERIAL_SOURCE_CONTEXT_OBSERVATION


# BEGIN BOUNDED_PUBLIC_BROKER_NOTIFICATION_DIAGNOSTIC
# Official broker v37 forms dbus-<unique>-<escaped Name>@<uint64>.service.
# Official mako v1.11.0 activates org.freedesktop.Notifications with Exec and
# no SystemdService. This is a Source-shaped diagnostic family only; no
# original value, numeric field, operand digest, runtime cause or exemption.
BROKER_NOTIFICATION_FRAGMENT = re.compile(
    r'1\.(?P<unique>0|[1-9][0-9]{0,19})-org\.freedesktop\.Notifications@'
    r'(?P<instance>0|[1-9][0-9]{0,19})\.service')


def generated_source_family(m, match, phase, original=None, boundaries=None, removed=None):
    if (type(phase) is not str or phase != 'source-view' or type(match) is not re.Match
            or type(original) is not str or type(boundaries) is not m.array
            or type(removed) is not m.array or len(boundaries) != len(removed)
            or not 0 < match.end() - match.start() <= 256):
        return 'unknown'
    matched = BROKER_NOTIFICATION_FRAGMENT.fullmatch(match.group(0))
    if matched is None:
        return 'unknown'
    if (int(matched.group('unique')) >= 18446744073709551615
            or int(matched.group('instance')) > 18446744073709551615):
        return 'unknown'
    first, last = m.original_span(match.start(), match.end(), boundaries, removed)
    if not (type(first) is int and type(last) is int and 6 <= first <= last <= len(original)
            and last - first == match.end() - match.start()
            and original[first:last] == match.group(0)
            and original[first - 6:first] == 'dbus-:'):
        return 'unknown'
    start, end = first - 6, last
    delimiters = ' \t\r\n:'
    if ((start != 0 and original[start - 1] not in delimiters)
            or (end != len(original) and original[end] not in delimiters)):
        return 'unknown'
    return 'broker-public-notifications'
# END BOUNDED_PUBLIC_BROKER_NOTIFICATION_DIAGNOSTIC


# BEGIN EXACT_REJECTED_MATCH_ALIGNMENT
# Additive finite Source-text diagnostics only. The original scanner and its
# first-rejection order remain unchanged. No offsets, values or new hashes are
# exported, and exact Source alignment does not authenticate executed code.
DIAGNOSTIC_SENSITIVE_PATTERN = '(?i)(?:gh[pousr]_|github_pat_)[a-z0-9_]+|AKIA[A-Z0-9]{16}|authorization:\\s*\\S+(?:\\s+\\S+)?|[\\w.+-]+@[\\w.-]+\\.[a-z]{2,}|https?://[^\\s"<>]*\\?[^\\s"<>]*|https?://[^\\s"<>]*@[^\\s"<>]+|["\\\']?\\b(?:password|passwd|token|access_token|refresh_token|api_key|client_secret|secret)["\\\']?\\s*[:=]\\s*[^\\s,}]+|--(?:password|token|api-key)\\s+(?!\\[secret: password hash\\])\\S+|\\bcryptsetup (?:luksFormat|open) [^\\r\\n]* < (?!\\[secret: disk passphrase\\])\\S+|(?:transcript|transcription|transcribed(?:\\s+text)?|recognized\\s+text|dictation\\s+(?:text|result)|תמלול|תמליל|טקסט\\s+מזוהה)["\\\']?\\s*[:=]'
DIAGNOSTIC_SENSITIVE_FLAGS = 34
DIAGNOSTIC_SGR = re.compile('\\x1b\\[[0-9;:]*m', 32)
DIAGNOSTIC_TERMINAL = re.compile('\\x1b\\[[0-?]*[ -/]*[@-~]|\\x1b\\][^\\x1b\\x07\\r\\n]*(?:\\x07|\\x1b\\\\)|\\x1b[PX^_][^\\x1b\\r\\n]*\\x1b\\\\|\\x1b(?![\\[\\]PX^_])[ -/]*[0-~]', 32)
DIAGNOSTIC_RULE_LABELS = ('github-credential', 'aws-credential', 'authorization', 'email-shape', 'queried-url', 'credential-url', 'named-secret', 'secret-option', 'disk-secret-input', 'transcription-label')
DIAGNOSTIC_BROKER_NUMERIC_FRAGMENT = re.compile(
    r'1\.(?P<unique>[0-9]{1,21})-org\.freedesktop\.Notifications@'
    r'(?P<instance>[0-9]{1,21})\.service')


def diagnostic_view_alignment(m, match, phase, original, boundaries, removed):
    result = dict(regex='unverified', offsets='unverified', mapping='unverified')
    if type(match) is not re.Match:
        result['regex'] = 'not-regex-match'
        return result
    if type(m.EXTERNAL_SENSITIVE) is not re.Pattern or match.re is not m.EXTERNAL_SENSITIVE:
        result['regex'] = 'foreign-regex-match'
        return result
    if (match.re.pattern != DIAGNOSTIC_SENSITIVE_PATTERN
            or match.re.flags != DIAGNOSTIC_SENSITIVE_FLAGS):
        result['regex'] = 'scanner-pattern-differs'
        return result
    result['regex'] = 'exact-scanner-regex'
    if (type(match.string) is not str or not 0 <= match.start() < match.end() <= len(match.string)
            or match.end() - match.start() > MAX_MATCH):
        result['offsets'] = 'match-outside-diagnostic-bound'
        return result
    if match.pos != 0 or match.endpos != len(match.string):
        result['offsets'] = 'match-window-differs'
        return result
    replay = match.re.match(match.string, match.start())
    if replay is None or replay.span() != match.span():
        result['offsets'] = 'match-span-differs'
        return result
    result['offsets'] = 'exact-scanner-span'
    if type(phase) is not str or phase not in m.EXTERNAL_RULE_PHASES:
        result['mapping'] = 'phase-unknown'
        return result
    if phase == 'terminal-payload':
        result['mapping'] = ('payload-without-original-map' if original is None
                             and boundaries is None and removed is None else 'payload-map-differs')
        return result
    if (type(original) is not str or len(original) > MAX_MEMBER
            or type(boundaries) is not m.array or type(removed) is not m.array
            or boundaries.typecode != 'I' or removed.typecode != 'I'
            or len(boundaries) != len(removed)):
        result['mapping'] = 'original-map-unavailable'
        return result
    if phase == 'source-view':
        for control in DIAGNOSTIC_TERMINAL.finditer(match.string):
            if (match.string.startswith('\x1b[', control.start())
                    and control.end() - control.start() <= 4096
                    and match.string[control.end() - 1] == '@'):
                result['mapping'] = 'scanner-view-differs'
                return result
    escapes = DIAGNOSTIC_SGR if phase == 'source-view' else DIAGNOSTIC_TERMINAL
    # Replay the exact pinned view/map with bounded chunks, rather than copy a
    # second whole private view. No chunk or mapping index leaves this function.
    cursor = view_cursor = count = index = 0
    def segment_equal(first, last, at):
        for position in range(first, last, 4096):
            end = min(position + 4096, last)
            source = original[position:end]; projected = match.string[at:at + end - position]
            if source != projected:
                if phase != 'source-view' or len(source) != len(projected):
                    return False
                for offset, (before, after) in enumerate(zip(source, projected)):
                    if before == after:
                        continue
                    if before != '@' or after != ' ':
                        return False
                    final = at + offset
                    start = match.string.rfind('\x1b[', max(0, final - 4095), final)
                    if start < 0 or final + 1 - start > 4096:
                        return False
                    # The only permitted same-position difference is a whole
                    # bounded ASCII CSI with its original final @ restored.
                    # A CSI cannot contain another ESC, so a complete string
                    # payload cannot surround this recognized control header.
                    candidate = match.string[start:final] + '@'
                    if DIAGNOSTIC_TERMINAL.fullmatch(candidate) is None:
                        return False
            at += end - position
        return True
    for escape in escapes.finditer(original):
        length = escape.start() - cursor
        if not segment_equal(cursor, escape.start(), view_cursor):
            result['mapping'] = 'scanner-view-differs'
            return result
        view_cursor += length
        expected_boundary = escape.start() - count
        count += escape.end() - escape.start()
        if (index >= len(boundaries) or boundaries[index] != expected_boundary
                or removed[index] != count):
            result['mapping'] = 'original-map-differs'
            return result
        index += 1
        cursor = escape.end()
    if index != len(boundaries):
        result['mapping'] = 'original-map-differs'
    elif (not segment_equal(cursor, len(original), view_cursor)
            or view_cursor + len(original) - cursor != len(match.string)):
        result['mapping'] = 'scanner-view-differs'
    else:
        result['mapping'] = 'exact-source-view' if phase == 'source-view' else 'exact-terminal-view'
    return result


def diagnostic_candidate_reason(row):
    if row['rule'] != 'email-shape':
        return 'rule-not-email-shape'
    if row['unit_like'] is not True:
        return 'not-unit-shaped'
    if not row['delimiter_bounded']:
        return 'match-delimiter-differs'
    if not row['original_contiguous']:
        return 'match-not-original-contiguous'
    if row['public_candidate'] != 'unknown':
        return 'known-public-literal'
    return 'not-catalogued-public-literal'


def diagnostic_family_reason(m, match, phase, original, boundaries, removed, row):
    if phase != 'source-view':
        return 'phase-not-source-view'
    if row['rule'] != 'email-shape':
        return 'rule-not-email-shape'
    if match.end() - match.start() > 256:
        return 'fragment-outside-family-bound'
    fragment = BROKER_NOTIFICATION_FRAGMENT.fullmatch(match.group(0))
    if fragment is None:
        if DIAGNOSTIC_BROKER_NUMERIC_FRAGMENT.fullmatch(match.group(0)) is not None:
            return 'noncanonical-source-numeric-shape'
        return 'not-known-public-family-fragment'
    if (int(fragment.group('unique')) >= 18446744073709551615
            or int(fragment.group('instance')) > 18446744073709551615):
        return 'source-numeric-range-differs'
    first, last = m.original_span(match.start(), match.end(), boundaries, removed)
    if not (type(first) is int and type(last) is int and 0 <= first <= last <= len(original)):
        return 'original-family-span-differs'
    if last - first != match.end() - match.start() or original[first:last] != match.group(0):
        return 'family-fragment-not-contiguous'
    if first < 6 or original[first - 6:first] != 'dbus-:':
        return 'known-family-prefix-differs'
    start, end = first - 6, last
    delimiters = ' \t\r\n:'
    if ((start != 0 and original[start - 1] not in delimiters)
            or (end != len(original) and original[end] not in delimiters)):
        return 'whole-family-delimiter-differs'
    return 'known-public-family'


def annotated_match(m, match, phase, original=None, boundaries=None, removed=None):
    alignment = diagnostic_view_alignment(m, match, phase, original, boundaries, removed)
    aligned = (alignment['regex'] == 'exact-scanner-regex'
               and alignment['offsets'] == 'exact-scanner-span'
               and alignment['mapping'] in ('exact-source-view', 'exact-terminal-view',
                                            'payload-without-original-map'))
    # Foreign/truncated/incorrectly mapped Matches cannot receive a known
    # public label merely because their copied substring resembles one.
    row = (classify_match(m, match, phase, original, boundaries, removed) if aligned
           else classify_match(m, None, phase))
    alignment.update(source_rule=('external-rule-' + format(DIAGNOSTIC_RULE_LABELS.index(row['rule']) + 1, '03d')
                                  if row['rule'] in DIAGNOSTIC_RULE_LABELS else 'unknown'),
        candidate_reason=diagnostic_candidate_reason(row) if aligned else 'source-alignment-unverified',
        family_reason=diagnostic_family_reason(m, match, phase, original, boundaries, removed, row)
                      if aligned else 'source-alignment-unverified',
        source_text_observation_only=True, actual_code_ownership=False,
        privacy_admitted=False, runtime_cause_proven=False)
    row['source_match_diagnostic'] = alignment
    return row
# END EXACT_REJECTED_MATCH_ALIGNMENT


def classify_match(m, match, phase, original=None, boundaries=None, removed=None):
    result = dict(phase=phase if type(phase) is str and phase in m.EXTERNAL_RULE_PHASES else 'unknown',
        rule='unknown-rule', codepoints=None, bytes=None, unit_like=None,
        original_contiguous=False, delimiter_bounded=False,
        public_candidate='unknown', public_candidate_sha256=None,
        known_source_fragment='unknown', generated_source_family='unknown')
    fragment = serial_source_fragment(m, match, phase, original, boundaries, removed)
    result['known_source_fragment'] = fragment['candidate']
    result['generated_source_family'] = generated_source_family(m, match, phase, original, boundaries, removed)
    result['source_context'] = serial_source_context(m, match, phase, original, boundaries, removed)
    if type(match) is not re.Match or match.end() - match.start() > MAX_MATCH:
        return result
    value = match.group(0)
    raw = value.encode('utf-8')
    if len(raw) > MAX_MATCH:
        return result
    result['codepoints'], result['bytes'] = len(value), len(raw)
    for label, rule in m.EXTERNAL_RULES:
        if rule.fullmatch(value):
            result['rule'] = label
            break
    if result['rule'] != 'email-shape':
        return result
    result['unit_like'] = re.fullmatch(r'[A-Za-z0-9_.@:\\-]{1,256}\.service', value) is not None
    start, end = match.span()
    delimiters = ' \t\r\n:'
    result['delimiter_bounded'] = ((start == 0 or match.string[start - 1] in delimiters)
        and (end == len(match.string) or match.string[end] in delimiters))
    if type(original) is str and type(boundaries) is m.array and type(removed) is m.array:
        first, last = m.original_span(start, end, boundaries, removed)
        result['original_contiguous'] = last - first == len(value) and original[first:last] == value
    if result['delimiter_bounded'] and result['original_contiguous']:
        for literal, identifier in (*m.EXTERNAL_EMAIL_CANDIDATES, *EXTRA_UNIT_CANDIDATES):
            if value == literal:
                result['public_candidate'] = identifier
                # This digest is emitted only for an exact, public literal.
                # Unknown operands never receive a digest or raw excerpt.
                result['public_candidate_sha256'] = hashlib.sha256(literal.encode()).hexdigest()
                break
    return result


def screened_text(m, content):
    observations = []
    prior = m.diagnose_sensitive_match
    def observe(match, phase, original=None, boundaries=None, removed=None):
        observations.append(annotated_match(m, match, phase, original, boundaries, removed))
        prior(match, phase, original, boundaries, removed)
    m.diagnose_sensitive_match = observe
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                result = m.external_text(content)
            except UnicodeDecodeError:
                return False, 'invalid-utf8', observations
            except RuntimeError as error:
                if type(error) is not RuntimeError:
                    raise
                if error.args == ('Sensitive text in external evidence',):
                    return False, 'sensitive-text', observations
                if error.args == ('Incomplete terminal escape in external evidence',):
                    return False, 'incomplete-terminal', observations
                raise
        if result is not content:
            raise RuntimeError('Diagnostic scanner changed original bytes')
        return True, None, observations
    finally:
        m.diagnose_sensitive_match = prior


def identity(st):
    return st.st_dev, st.st_ino, st.st_uid, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_nlink


def close_preserving(fd):
    primary = sys.exc_info()[1]
    try:
        os.close(fd)
    except BaseException:
        if primary is None:
            raise


def read_owned(root_fd, relative):
    parts = relative.split('/')
    if any(p in ('', '.', '..') for p in parts):
        raise RuntimeError('Diagnostic fixed path differs')
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            try:
                close_preserving(current)
            except BaseException:
                close_preserving(next_fd)
                raise
            current = next_fd
            st = os.fstat(current)
            if st.st_uid != os.geteuid():
                raise RuntimeError('Diagnostic parent owner differs')
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_nlink != 1 or before.st_size > MAX_MEMBER:
                raise RuntimeError('Diagnostic original type owner or bounds differ')
            blocks, total = [], 0
            while block := os.read(fd, min(1024 * 1024, MAX_MEMBER + 1 - total)):
                total += len(block)
                if total > MAX_MEMBER:
                    raise RuntimeError('Diagnostic original byte bounds differ')
                blocks.append(block)
            content = b''.join(blocks)
            if identity(os.fstat(fd)) != identity(before) or len(content) != before.st_size:
                raise RuntimeError('Diagnostic original changed during read')
            actual = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
            if identity(actual) != identity(before):
                raise RuntimeError('Diagnostic original name was replaced')
            return content
        finally:
            close_preserving(fd)
    finally:
        close_preserving(current)


def prepare(source, out, profile):
    if profile not in ('idle', 'active'):
        raise RuntimeError('Diagnostic profile differs')
    m = scanner()
    contract = load('installer_partial_fixed_contract', HERE / ('active-contract.py' if profile == 'active' else 'contract.py'))
    # Source-owned fixed inventory only. Binary UART/port prefixes are not
    # inspected or copied by this partial-text diagnostic.
    allowed = set(contract.ARCHIVE_FILES) - {'upload-screening.json'}
    root_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(root_fd).st_uid != os.geteuid():
            raise RuntimeError('Diagnostic source owner differs')
        files, rejected, missing, excluded_binary = {}, [], [], []
        content_files, total = {}, 0
        for relative in sorted(allowed):
            if relative.endswith('.bounded-prefix.bin'):
                excluded_binary.append(relative)
                continue
            try:
                content = read_owned(root_fd, relative)
            except FileNotFoundError:
                missing.append(relative)
                continue
            total += len(content)
            if total > MAX_TOTAL:
                raise RuntimeError('Diagnostic aggregate bounds differ')
            if relative.endswith('.png'):
                if not content.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise RuntimeError('Diagnostic fixed image is not PNG')
            elif Path(relative).suffix in m.TEXT:
                passed, reason, observations = screened_text(m, content)
                if not passed:
                    rejected.append(dict(member=relative, reason=reason, matches=observations))
                    continue
            else:
                raise RuntimeError('Diagnostic fixed member format differs')
            files[relative] = dict(bytes=len(content), original_sha256=hashlib.sha256(content).hexdigest(),
                uploaded_sha256=hashlib.sha256(content).hexdigest(), redactions=0)
            content_files[relative] = content
        if not rejected:
            raise RuntimeError('Partial diagnostic requires a strict rejected original')
        report = dict(schema='arctic-installer-partial-evidence-v1', profile=profile,
            purpose='Failure-only partial original diagnostics; incomplete and unqualified',
            full_strict_screen='REJECTED', release_acceptance=False, image_qualified=False,
            scanner_sha256=SCANNER_SHA256, files=files, rejected_members=rejected,
            missing_fixed_members=missing, excluded_unscreened_binary_members=excluded_binary,
            required_images=list(contract.REQUIRED_IMAGES),
            all_required_images_present=all(n in files for n in contract.REQUIRED_IMAGES),
            public_arbitrary_excerpts=0, unknown_operand_digests=0,
            original_source_members_preserved=True)
        # An unused private output directory is required. Workflow uploads it
        # only when this complete helper returns success; strictscreen's
        # original failed step continues to fail the overall job.
        os.mkdir(out, 0o700)
        for relative, content in content_files.items():
            path = out / relative
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
        fd = os.open(out / 'diagnostic-partial.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(report, stream, sort_keys=True, indent=2); stream.write('\n')
        return report
    finally:
        close_preserving(root_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--profile', choices=('idle', 'active'), required=True)
    args = parser.parse_args()
    prepare(args.source, args.out, args.profile)
    print('ARCTIC-INSTALLER-PARTIAL-DIAGNOSTIC=created-unqualified', flush=True)


if __name__ == '__main__':
    main()

# BEGIN SAME_REJECTED_MATCH_PUBLIC_SOURCE_SHAPE
# Failure observation only. Equality to a public literal and fixed upstream
# shape predicates grant no privacy exception or runtime provenance.
DIAGNOSTIC_PUBLIC_UNITS = (
    ('modprobe@configfs.service', 'unit-001'),
    ('modprobe@fuse.service', 'unit-002'),
    ('modprobe@drm.service', 'unit-003'),
    ('modprobe@loop.service', 'unit-004'),
    ('modprobe@dm_mod.service', 'unit-005'),
    ('modprobe@efi_pstore.service', 'unit-006'),
    ('user@1000.service', 'unit-007'),
    ('user-runtime-dir@1000.service', 'unit-008'),
    ('getty@tty1.service', 'unit-009'),
    ('getty@tty6.service', 'unit-010'),
    ('serial-getty@ttyS0.service', 'unit-011'),
    ('systemd-zram-setup@zram0.service', 'unit-012'),
)
DIAGNOSTIC_OSC_KEYS = ('start', 'user', 'hostname', 'machineid', 'bootid',
                       'pid', 'pidfdid', 'comm', 'servicename', 'invocationid', 'type')
DIAGNOSTIC_SHAPE_FLAGS = (
    'same_source_match_aligned', 'match_original_contiguous',
    'osc3008_prefix_near_match', 'osc3008_complete_bounded_frame',
    'match_within_osc3008_frame', 'source_field_keys_known_unique',
    'source_optional_field_order', 'required_source_fields_present',
    'match_equals_servicename_field', 'start_id_hex32', 'machine_id_hex32',
    'boot_id_hex32', 'invocation_id_hex32', 'pid_canonical_in_range',
    'pidfdid_canonical_in_range', 'user_root_exact', 'hostname_known_public',
    'comm_agetty_exact', 'type_service_exact', 'current_scanner_service_schema',
    'current_scanner_pid_limits',
)

def diagnostic_public_source_shape(m, match, phase, original=None, boundaries=None, removed=None):
    """Only Source-known IDs/booleans, from the same exact rejected Match."""
    result = {key: False for key in DIAGNOSTIC_SHAPE_FLAGS}
    result.update(schema='arctic-bios-same-match-public-source-shape-v1',
                  canonical_unit_id='unknown', privacy_admitted=False,
                  runtime_cause_proven=False, operand_value_or_digest_exported=False)
    alignment = diagnostic_view_alignment(m, match, phase, original, boundaries, removed)
    if not (alignment == {'regex': 'exact-scanner-regex', 'offsets': 'exact-scanner-span',
                          'mapping': 'exact-source-view'}
            and type(m.EXTERNAL_EMAIL_CANDIDATES) is tuple
            and m.EXTERNAL_EMAIL_CANDIDATES == DIAGNOSTIC_PUBLIC_UNITS):
        return result
    result['same_source_match_aligned'] = True
    first, last = m.original_span(match.start(), match.end(), boundaries, removed)
    if not (type(first) is int and type(last) is int and 0 <= first < last <= len(original)
            and last - first == match.end() - match.start()
            and original[first:last] == match.group(0)):
        return result
    result['match_original_contiguous'] = True
    canonical_id = 'unknown'
    for literal, identifier in DIAGNOSTIC_PUBLIC_UNITS:
        if match.group(0) == literal:
            canonical_id = identifier
            break
    delimiters = ' \t\r\n:'
    if ((first == 0 or original[first - 1] in delimiters)
            and (last == len(original) or original[last] in delimiters)):
        result['canonical_unit_id'] = canonical_id
    # The exact official v259 producer uses ANSI_OSC + "3008;start=" and
    # ANSI_ST. Inspect at most its accepted 512-character frame bound, never
    # a whole private record or an unbounded copied prefix.
    start = original.rfind('\x1b]3008;', max(0, first - 512), first + 1)
    if start < 0:
        return result
    result['osc3008_prefix_near_match'] = True
    end = original.find('\x1b\\', start + 7, min(len(original), start + 512) + 1)
    if end < 0 or end + 2 - start > 512:
        return result
    frame = original[start:end + 2]
    if any(char in frame[2:-2] for char in '\x1b\x07\r\n'):
        return result
    result['osc3008_complete_bounded_frame'] = True
    if not start <= first < last <= end:
        return result
    result['match_within_osc3008_frame'] = True
    pieces = frame[7:-2].split(';')
    if len(pieces) > len(DIAGNOSTIC_OSC_KEYS):
        return result
    fields = {}; spans = {}; cursor = start + 7
    for piece in pieces:
        key, separator, value = piece.partition('=')
        if separator != '=' or key not in DIAGNOSTIC_OSC_KEYS or key in fields:
            return result
        fields[key] = value
        spans[key] = (cursor + len(key) + 1, cursor + len(piece))
        cursor += len(piece) + 1
    result['source_field_keys_known_unique'] = True
    keys = tuple(fields)
    result['source_optional_field_order'] = keys == tuple(k for k in DIAGNOSTIC_OSC_KEYS if k in fields)
    result['required_source_fields_present'] = all(k in fields for k in ('start', 'pid', 'comm', 'invocationid', 'type'))
    result['match_equals_servicename_field'] = spans.get('servicename') == (first, last)
    if result['match_equals_servicename_field']:
        result['canonical_unit_id'] = canonical_id
    for field, flag in (('start', 'start_id_hex32'), ('machineid', 'machine_id_hex32'),
                        ('bootid', 'boot_id_hex32'), ('invocationid', 'invocation_id_hex32')):
        value = fields.get(field)
        result[flag] = type(value) is str and re.fullmatch('[0-9a-f]{32}', value) is not None
    for field, flag, digits, maximum in (
            ('pid', 'pid_canonical_in_range', 10, 2147483647),
            ('pidfdid', 'pidfdid_canonical_in_range', 20, 18446744073709551615)):
        value = fields.get(field)
        result[flag] = (type(value) is str and len(value) <= digits
                        and re.fullmatch('[1-9][0-9]*', value) is not None
                        and int(value) <= maximum)
    result['user_root_exact'] = fields.get('user') == 'root'
    result['hostname_known_public'] = fields.get('hostname') in ('arctic-ci', 'arctic-qual', 'localhost-live')
    result['comm_agetty_exact'] = fields.get('comm') == '(agetty)'
    result['type_service_exact'] = fields.get('type') == 'service'
    # This reports the existing predicate; it neither calls external_text nor
    # adds an allowed span. The original rejection/error remain in force.
    if type(m.OSC3008_SERVICE) is re.Pattern and m.OSC3008_SERVICE_MAX_CHARS == 512:
        accepted = m.OSC3008_SERVICE.fullmatch(frame)
        result['current_scanner_service_schema'] = accepted is not None
        result['current_scanner_pid_limits'] = (accepted is not None
            and int(accepted.group('pid')) <= 2147483647
            and int(accepted.group('pidfdid')) <= 18446744073709551615)
    return result
# END SAME_REJECTED_MATCH_PUBLIC_SOURCE_SHAPE
