"""Read-only actual-image application inventory, GTK3 linkage and GIO defaults.

This additive probe never launches applications or changes configuration. It
supplements, and cannot replace, the original eight native functional gates.
"""
import configparser
from pathlib import Path
import re
import subprocess

PACKAGES = tuple(sorted(('epiphany', 'foot', 'pcmanfm', 'xarchiver', 'celluloid',
                         'featherpad', 'nano', 'fish', 'bash')))
CONTEXT = {'source_sha', 'iso_sha256', 'iso_bytes', 'checker_sha256',
           'native_sha256', 'manifest_sha256', 'mimeapps_sha256'}
UUID = re.compile('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
GTK3 = 'libgtk-3.so.0()(64bit)'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def mime_defaults(data):
    require(type(data) is bytes and 0 < len(data) < 128 * 1024, 'MIME source bounds differ')
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.read_string(data.decode('utf-8'))
    require(parser.sections() == ['Default Applications'], 'MIME source section differs')
    result = {}
    for mime, value in parser['Default Applications'].items():
        require(re.fullmatch('[a-z0-9.+-]+/[a-z0-9.+-]+', mime) and
                re.fullmatch(r'[A-Za-z0-9_.+-]+\.desktop;', value), 'MIME source default differs')
        result[mime] = value[:-1]
    require(result and result.get('inode/directory') == 'pcmanfm.desktop' and
            result.get('text/plain') == 'featherpad.desktop' and
            result.get('text/html') == 'org.gnome.Epiphany.desktop' and
            result.get('application/zip') == 'xarchiver.desktop' and
            result.get('video/mp4') == 'io.github.celluloid_player.Celluloid.desktop',
            'Requested fresh MIME roles differ')
    return result


def context_check(context):
    require(type(context) is dict and set(context) == CONTEXT and
            re.fullmatch('[0-9a-f]{40}', context['source_sha']) and
            type(context['iso_bytes']) is int and 0 < context['iso_bytes'] < 2_000_000_000 and
            all(type(context[key]) is str and re.fullmatch('[0-9a-f]{64}', context[key])
                for key in CONTEXT - {'source_sha', 'iso_bytes'}), 'Application probe context differs')


def command(argv):
    result = subprocess.run(argv, check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, timeout=10)
    require(len(result.stdout) <= 128 * 1024 and len(result.stderr) <= 16 * 1024,
            'Application probe command output exceeds bounds')
    return result.stdout.strip()


def gio_default(text, mime):
    # LC_ALL=C is enforced for the real GIO command; only its one default row
    # is relevant, not registered/recommended fallback applications.
    rows = [line for line in text.splitlines() if line.startswith('Default application for ')]
    require(len(rows) == 1 and re.fullmatch('Default application for “' + re.escape(mime) +
            r'”: [A-Za-z0-9_.+-]+\.desktop', rows[0]), 'GIO has no unique actual default: ' + mime)
    return rows[0].rsplit(': ', 1)[1]


def gtk_check(owner, requirements):
    require(owner == 'pcmanfm' and type(requirements) is list and requirements == sorted(set(requirements)) and
            GTK3 in requirements and not any(re.search(r'libgtk-(?:x11-|win32-)?2\.0', item) for item in requirements),
            'Installed PCManFM does not have explicit GTK3-only RPM linkage')


def probe(prefix, stage, context, mimes):
    context_check(context)
    require(stage in ('live', 'installed') and isinstance(prefix, list) and
            prefix[:2] == ['runuser', '-u'] and prefix[3:5] == ['--', 'env'],
            'Application probe requires the actual desktop-user prefix')
    require(('rd.live.image' in Path('/proc/cmdline').read_text().split()) == (stage == 'live'),
            'Application probe boot medium differs')
    uid = int(command(prefix + ['id', '-u']))
    sessions = [value.split('=', 1)[1] for value in prefix if value.startswith('XDG_SESSION_ID=')]
    require(uid >= 1000 and len(sessions) == 1 and re.fullmatch('[A-Za-z0-9_-]{1,64}', sessions[0]),
            'Application probe desktop identity differs')
    session = sessions[0]
    for key, expected in (('User', str(uid)), ('Type', 'wayland'), ('Active', 'yes')):
        require(command(['loginctl', 'show-session', session, '-p', key, '--value']) == expected,
                'Application probe actual active desktop differs: ' + key)
    package_rows = command(['rpm', '-q', '--qf', '%{NAME}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\n', *PACKAGES])
    packages = {}
    for row in package_rows.splitlines():
        fields = row.split('\t')
        require(len(fields) == 4 and fields[0] in PACKAGES and fields[0] not in packages and
                all(re.fullmatch('[A-Za-z0-9_.+~-]+', value) for value in fields),
                'Installed application RPM inventory is missing, duplicate or malformed')
        packages[fields[0]] = dict(version=fields[1], release=fields[2], arch=fields[3])
    require(set(packages) == set(PACKAGES), 'Installed requested application set differs')
    owner = command(['rpm', '-qf', '--qf', '%{NAME}\n', '/usr/bin/pcmanfm'])
    requirements = sorted(set(command(['rpm', '-q', '--requires', 'pcmanfm']).splitlines()))
    gtk_check(owner, requirements)
    actual = {mime: gio_default(command(prefix + ['LC_ALL=C', 'gio', 'mime', mime]), mime) for mime in sorted(mimes)}
    require(actual == mimes, 'Actual desktop-user GIO defaults differ from the pinned image source')
    record = dict(schema='arctic-native-app-defaults-v1', stage=stage, status='passed', release_acceptance=False,
                  context=context, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  desktop_uid=uid, active_desktop_session=session, packages=packages,
                  pcmanfm=dict(owner=owner, requirements=requirements), mime_defaults=actual,
                  scope='Actual RPM inventory/GTK3 requirements and fresh GIO defaults; separate original functional gates remain required')
    validate_report(record, context, mimes)
    return record


def validate_report(record, expected_context, mimes, provenance=None):
    context_check(expected_context)
    fields = {'schema', 'stage', 'status', 'release_acceptance', 'context', 'boot_id', 'desktop_uid',
              'active_desktop_session', 'packages', 'pcmanfm', 'mime_defaults', 'scope'}
    require(type(record) is dict and set(record) == fields and record['schema'] == 'arctic-native-app-defaults-v1' and
            record['stage'] in ('live', 'installed') and record['status'] == 'passed' and
            record['release_acceptance'] is False and record['context'] == expected_context and
            type(record['boot_id']) is str and UUID.fullmatch(record['boot_id']) and
            type(record['desktop_uid']) is int and record['desktop_uid'] >= 1000 and
            type(record['active_desktop_session']) is str and re.fullmatch('[A-Za-z0-9_-]{1,64}', record['active_desktop_session']),
            'Actual-image application report identity/status differs')
    require(type(record['packages']) is dict and set(record['packages']) == set(PACKAGES),
            'Installed requested application inventory differs')
    for name, package in record['packages'].items():
        require(type(package) is dict and set(package) == {'version', 'release', 'arch'} and
                all(type(value) is str and re.fullmatch('[A-Za-z0-9_.+~-]+', value) for value in package.values()) and
                package['arch'] == 'x86_64', 'Installed application NEVRA differs: ' + name)
    require(type(record['pcmanfm']) is dict and set(record['pcmanfm']) == {'owner', 'requirements'},
            'PCManFM RPM linkage inventory differs')
    gtk_check(record['pcmanfm']['owner'], record['pcmanfm']['requirements'])
    require(record['mime_defaults'] == mimes, 'Actual desktop GIO default inventory differs')
    if provenance is not None:
        require(all(record[key] == provenance[key] for key in
                    ('stage', 'boot_id', 'desktop_uid', 'active_desktop_session')),
                'Application defaults are not bound to the original native boot/session')
    return dict(packages=record['packages'], gtk3='explicit installed PCManFM RPM requirements',
                mime_defaults=record['mime_defaults'], release_acceptance=False)
