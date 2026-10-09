#!/usr/bin/env python3
"""Fail missing, duplicate, failed or unrun Nix/update acceptance records."""
import argparse
import json
from pathlib import Path
import re

COMMON = set('selinux non-chromium-browser configured-browser-choice configured-files configured-terminal '
             'configured-editor native-media-player native-archive-manager native-archive-helpers'.split())
INSTALLED = set('daemon-socket-defaults daemon-store-info daemon persistent-mount store-ownership labels '
                'mango-dodge-capability desktop-customization avc'.split())
INITIAL = set('online-network-preflight desktop-before-install search desktop-preinstall-epoch install '
              'profile-export-identity desktop-hot-install-rescan desktop-after-install desktop-entry-launch '
              'hello desktop-file icons graphical-foot session-paths two-user-isolation update-personal '
              'offline-foot-profile-exports desktop-after-offline-rollback remove rollback rollback-hello '
              'trust-config signed-offline-update-stage signed-offline-update-ready engine-version-change'.split())
FINAL = set('new-boot profile-persistence hello-after-reboot nix-engine-after-update graphical-after-reboot '
            'signed-offline-update-completed signed-offline-update-history'.split())


def verify(text, phase):
    stage = 'live' if phase == 'live' else 'installed'
    rows = [json.loads(line.split(' ', 1)[1]) for line in text.splitlines()
            if line.startswith('ARCTIC-NIX-ACCEPTANCE ')]
    names = [row['check'] for row in rows]
    required = COMMON | ({'live-mutation-denied'} if phase == 'live' else INSTALLED | (INITIAL if phase == 'initial' else FINAL))
    if len(names) != len(set(names)) or set(names) != required or any(row['stage'] != stage for row in rows):
        raise RuntimeError('Missing, duplicate, unexpected or wrong-stage acceptance records: ' + phase)
    for row in rows:
        if row['status'] == 'passed':
            continue
        # Equal Nix engine version is explicitly not engine upgrade proof. Arctic
        # replacements still require actual signatures, higher EVRs and a new boot.
        if phase == 'initial' and row['check'] == 'engine-version-change' and row['status'] == 'unrun':
            continue
        raise RuntimeError('Failed/unrun acceptance: ' + row['check'])
    marker = 'ARCTIC-LIVE-SMOKE-EXIT=' if stage == 'live' else 'ARCTIC-INSTALLED-SMOKE-EXIT='
    values = re.findall(re.escape(marker) + r'([^\r\n]*)', text)
    if values != ['0']:
        raise RuntimeError('Missing/duplicate/failed generic guest completion marker: ' + phase)
    return dict(phase=phase, checks=len(rows), release_acceptance=False,
                nix_engine_version_change=next((row['status'] for row in rows
                                               if row['check'] == 'engine-version-change'), None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vm', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = {}
    for phase, name in (('live', 'serial-install.log'), ('initial', 'serial-before-update-reboot.log'),
                        ('final', 'serial-boot.log')):
        path = args.vm / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 128 * 1024 * 1024:
            raise RuntimeError('Missing/unsafe/bounded serial file: ' + name)
        report[phase] = verify(path.read_text(), phase)
    intermediate = json.loads((args.vm / 'offline-update/intermediate-boot.json').read_text())
    if intermediate['status'] != 'guest_exited_subsequent_boot_required':
        raise RuntimeError('Intermediate offline transaction did not exit for the required final boot')
    report['status'] = 'same_image_nix_signed_offline_update_reboot_passed'
    report['release_acceptance'] = False
    args.out.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
