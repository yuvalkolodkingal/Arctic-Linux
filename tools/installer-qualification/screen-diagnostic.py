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
SCANNER_SHA256 = '8754ad7f3a97803ce1d84fd889667853dd5d407a8907adfb52afd6a7d41067be'
MAX_MEMBER = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_MATCH = 16 * 1024
# These are diagnostic candidates, not admitted privacy exceptions. The
# retained package-verified getty@.service template permits %I instances, and
# the exact guest returns to its discovered VT after explicitly visiting VT6.
# No alias, arbitrary instance, or unknown token is exported.
EXTRA_UNIT_CANDIDATES = tuple(('getty@tty' + str(n) + '.service', 'getty-template-tty' + str(n)) for n in range(2, 6))


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


def classify_match(m, match, phase, original=None, boundaries=None, removed=None):
    result = dict(phase=phase if type(phase) is str and phase in m.EXTERNAL_RULE_PHASES else 'unknown',
        rule='unknown-rule', codepoints=None, bytes=None, unit_like=None,
        original_contiguous=False, delimiter_bounded=False,
        public_candidate='unknown', public_candidate_sha256=None)
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
        observations.append(classify_match(m, match, phase, original, boundaries, removed))
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
