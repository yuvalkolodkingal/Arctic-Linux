"""Additive real GUI installation lane; never substitutes the installed engine."""
import json
import os
from pathlib import Path
import re
import signal
import stat
import time

SCHEMA = 'arctic-live-installer-active-restoration-v1'
SCOPE = 'Owned 64 GiB unencrypted offline UEFI install; original copy writer continues through disruptions'
GUI_KEYS = {'page', 'current', 'view', 'valid', 'busy', 'ready', 'connected',
            'failure', 'error', 'fields', 'keyboard', 'percent', 'window'}
GUI_FILES = tuple('''Engine.qml Frame.qml Theme.qml Wizard.qml shell.qml qmldir
components/AppGroupHeader.qml components/AppRow.qml components/AppTile.qml components/ArBanner.qml
components/ArButton.qml components/ArCard.qml components/ArCheck.qml components/ArCheckIndicator.qml
components/ArDialog.qml components/ArInput.qml components/ArKbd.qml components/ArList.qml components/ArListRow.qml
components/ArMeter.qml components/ArProgress.qml components/ArRadio.qml components/ArSelect.qml components/ArSteps.qml
components/ArTag.qml components/ArText.qml components/ArToggle.qml components/AuroraBand.qml components/CornerMask.qml
components/FocusRing.qml components/Icon.qml components/Mark.qml components/ShadowRect.qml components/Wordmark.qml components/qmldir
steps/AccountStep.qml steps/AppsStep.qml steps/AttentionView.qml steps/DiskStep.qml steps/DoneStep.qml steps/EncryptionStep.qml
steps/InstallStep.qml steps/KeyboardStep.qml steps/NetworkStep.qml steps/StepPage.qml steps/SummaryStep.qml steps/TimezoneStep.qml
steps/WelcomeStep.qml steps/qmldir'''.split())


def ram_attribute(path, limit=4096):
    """Bounded nofollow read; sysfs attributes do not report content length."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not (stat.S_ISREG(before.st_mode) and before.st_uid == 0 and not before.st_mode & 0o022
                and 0 <= before.st_size <= limit):
            raise ValueError('RAM attribute protection differs')
        data = os.read(fd, limit + 1)
        after = os.fstat(fd)
        if len(data) > limit or any(getattr(before, key) != getattr(after, key)
                for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_mtime_ns', 'st_ctime_ns')):
            raise ValueError('RAM attribute identity changed')
        return data.decode('ascii').strip()
    finally:
        os.close(fd)


def proven_unbacked_zram(row, sys_root=Path('/sys'), dev_root=Path('/dev'), proc_root=Path('/proc')):
    """Exclude only a twice-observed canonical RAM device with no writeback."""
    if type(row) is not dict or type(row.get('name')) is not str or \
            not re.fullmatch(r'zram(0|[1-9][0-9]{0,3})', row['name']) or row.get('type') != 'disk' or \
            type(row.get('size')) is not int or not 0 < row['size'] <= 64 * 1024**3 or row['size'] % 512:
        return False
    name = row['name']; index = int(name[4:])
    try:
        sys_root = Path(sys_root).resolve(strict=True)
        def observation():
            node = (sys_root / 'class/block' / name).resolve(strict=True)
            if node != sys_root / 'devices/virtual/block' / name or \
                    (node / 'subsystem').resolve(strict=True) != sys_root / 'class/block':
                raise ValueError('RAM sysfs identity differs')
            identity = node.lstat()
            slaves = node / 'slaves'; slave_identity = slaves.lstat()
            if not all(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                       for info in (identity, slave_identity)) or slaves.is_symlink() or next(slaves.iterdir(), None) is not None:
                raise ValueError('RAM node protection or slaves differ')
            if any((node / key).exists() or (node / key).is_symlink() for key in ('device', 'partition')):
                raise ValueError('RAM has a transport or partition')
            devices = ram_attribute(Path(proc_root) / 'devices', 65536)
            if devices.count('Block devices:\n') != 1:
                raise ValueError('RAM block major inventory differs')
            majors = [int(match.group(1)) for line in devices.split('Block devices:\n')[1].splitlines()
                      if (match := re.fullmatch(r'\s*([0-9]{1,4})\s+zram', line))]
            if len(majors) != 1 or not 0 < majors[0] < 4096:
                raise ValueError('RAM dynamic major differs')
            dev = ram_attribute(node / 'dev')
            match = re.fullmatch(r'([0-9]{1,4}):([0-9]{1,4})', dev)
            if not match or (int(match[1]), int(match[2])) != (majors[0], index) or \
                    (sys_root / 'dev/block' / dev).resolve(strict=True) != node:
                raise ValueError('RAM major/minor backlink differs')
            block = (Path(dev_root) / name).lstat()
            if not stat.S_ISBLK(block.st_mode) or block.st_uid != 0 or \
                    (os.major(block.st_rdev), os.minor(block.st_rdev)) != (majors[0], index):
                raise ValueError('RAM block node differs')
            backing = ram_attribute(node / 'backing_dev')
            size = ram_attribute(node / 'size'); disksize = ram_attribute(node / 'disksize')
            state = ram_attribute(node / 'initstate'); algorithm = ram_attribute(node / 'comp_algorithm')
            if backing != 'none' or state != '1' or not re.fullmatch('[0-9]{1,20}', size) or \
                    not re.fullmatch('[0-9]{1,20}', disksize) or int(size) * 512 != row['size'] or int(disksize) != row['size'] or \
                    not re.fullmatch(r'(?:[a-z0-9_-]{1,32}|\[[a-z0-9_-]{1,32}\])(?:\s+(?:[a-z0-9_-]{1,32}|\[[a-z0-9_-]{1,32}\]))*', algorithm) or \
                    len(re.findall(r'\[[a-z0-9_-]{1,32}\]', algorithm)) != 1:
                raise ValueError('RAM backing or initialized size differs')
            return (node, identity.st_dev, identity.st_ino, identity.st_mode, identity.st_uid,
                    block.st_dev, block.st_ino, block.st_mode, block.st_uid, block.st_rdev,
                    slave_identity.st_dev, slave_identity.st_ino, dev, tuple(majors), backing, size, disksize, state, algorithm)
        return observation() == observation()
    except (OSError, ValueError):
        return False


def installer_type(G):
    """Build against the already hash-verified idle primitives, retaining that lane."""
    class ActiveRPC(G.EngineRPC):
        def permitted(self, method, params):
            return super().permitted(method, params) or (method == 'GetStep'
                and type(params) is dict and set(params) == {'id'}
                and params['id'] in ('disk', 'encryption', 'apps', 'network'))

        def snapshot(self):
            hello = self.call('Hello', {'client': 'installer-restoration-qualification', 'version': '1.2.1'})
            G.require(hello.get('live') is True and hello.get('mock') is False
                      and hello.get('engine_version') == '1.2.1' and hello.get('protocol_version') == 1,
                      'actual active engine identity differs')
            wizard = self.call('GetWizard')
            keyboard = self.call('GetStep', {'id': 'keyboard'})
            options = self.call('GetStep', {'id': 'install'})['options']
            progress = options.get('progress') or {}
            return dict(hello={k: hello[k] for k in ('engine_version', 'protocol_version', 'mock', 'live', 'firmware', 'state')},
                        wizard={k: wizard[k] for k in ('current', 'state')},
                        keyboard=dict(id='keyboard', data=keyboard['data']),
                        install=dict(id='install', options=dict(
                            modules=[{k: m[k] for k in ('id', 'status', 'percent')} for m in options.get('modules', [])],
                            progress={k: progress.get(k, False if k == 'paused' else 0 if k in ('percent', 'apps_done', 'apps_total') else '')
                                      for k in ('event', 'percent', 'phase', 'apps_done', 'apps_total', 'paused')},
                            attention=bool(options.get('attention')), failed=bool(options.get('failed')))))

        def config(self):
            # Account, secrets, Done and free-form engine text are never read/exported.
            return {key: dict(data=self.call('GetStep', {'id': key})['data'])['data']
                    for key in ('disk', 'encryption', 'apps', 'network')}

    class ActiveInstaller(G.Installer):
        def __init__(self, native, context, request=G.emit):
            super().__init__(native, context, request)
            self.deadline = time.monotonic() + 50 * 60
            self.samples = []
            self.started_ns = time.monotonic_ns()
            self.writer_identity = None
            self.safe_config = None

        def ipc(self, method, payload=None):
            G.require(method in ('state', 'next', 'fill'), 'active GUI method outside whitelist')
            self.assert_gui_identity()
            if method != 'state':
                state = G.strict_json(self.ipc('state'))
                page = state.get('page')
                G.require(page == state.get('current') and page in
                          ('welcome', 'keyboard', 'network', 'timezone', 'disk', 'encryption', 'account', 'apps', 'summary')
                          and state.get('ready') is True and state.get('connected') is True
                          and not state.get('busy') and not state.get('failure'), 'active GUI is not on a ready wizard page')
                if method == 'next':
                    G.require(payload is None and state.get('valid') is True, 'active Next is disabled')
                    if page == 'summary':
                        self.target_disk(pristine=True)  # Last destructive-action guard, immediately before GUI Start.
                        G.require(self.rpc.config() == self.safe_config, 'armed Summary config changed')
                else:
                    allowed = {'keyboard': {'layout': 'il', 'variant': ''},
                               'network': {'offline': True},
                               'disk': {'disk': '/dev/vda', 'mode': 'erase'},
                               'encryption': {'enabled': False}, 'apps': {}}
                    if page == 'account':
                        G.require(type(payload) is dict and set(payload) ==
                                  {'full_name', 'username', 'hostname', 'password', 'confirm', 'autologin', 'same_as_disk'}
                                  and payload['full_name'] == 'Arctic Qualification'
                                  and payload['username'] == 'arcticqual' and payload['hostname'] == 'arctic-qual'
                                  and payload['password'] == payload['confirm'] == self.password
                                  and payload['autologin'] is False and payload['same_as_disk'] is False,
                                  'account fixture differs (details withheld)')
                    else:
                        G.require(page in allowed and payload == allowed[page], 'active fill outside reviewed choice')
            else:
                G.require(payload is None, 'active state parameters differ')
            argv = ['quickshell', 'ipc', '--pid', str(self.gui_pid), 'call', 'installer', method]
            if method == 'fill':
                argv.append(json.dumps(payload))
            try:
                status, answer, _ = self.command(argv, desktop=True, allow_failure=True)
                G.require(status == 0, 'active GUI IPC failed (details withheld)')
                return answer
            except BaseException:
                # native.execute errors normally include argv: never expose account secrets.
                raise RuntimeError('active GUI IPC failed (details withheld)') from None

        def state(self):
            raw = G.strict_json(self.ipc('state'))
            return {key: raw[key] for key in GUI_KEYS}

        def packaged_sources(self):
            result = super().packaged_sources()
            for path in [*(Path(G.GUI_PATH)/name for name in GUI_FILES), Path('/usr/share/arctic/catalog/catalog.toml')]:
                data = G.read_regular(path, root_owned=True)
                result[str(path)] = dict(bytes=len(data), sha256=G.sha(data))
            return result

        def request(self, kind, cycle, **fields):
            G.require(self.samples and fields.get('engine_sha256') ==
                      G.sha(json.dumps(self.samples[-1]['engine'], sort_keys=True).encode()),
                      'active request is not bound to its latest observation')
            fields['elapsed_ns'] = self.samples[-1]['elapsed_ns']
            return super().request(kind, cycle, **fields)

        def target_read(self, phase, read):
            self.diagnostic_phase = phase
            return read()

        def target_disk(self, pristine=False):
            target_previous_phase = getattr(self, 'diagnostic_phase', 'unknown')
            disks = []
            self.diagnostic_phase = 'target-enumerate'
            for node in Path('/sys/class/block').iterdir():
                self.diagnostic_phase = 'target-partition'
                if (node / 'partition').exists():
                    self.diagnostic_phase = 'target-enumerate'
                    continue
                try:
                    if self.target_read('target-driver', lambda: (node / 'device/driver').resolve(strict=True).name) != 'virtio_blk':
                        self.diagnostic_phase = 'target-enumerate'
                        continue
                    if self.target_read('target-serial', lambda: (node / 'serial').read_text().strip()) == self.context['disk_serial']:
                        disks.append(node)
                except FileNotFoundError:
                    pass
                self.diagnostic_phase = 'target-enumerate'
            G.require(len(disks) == 1 and disks[0].name == 'vda', 'owned target serial/path is absent or ambiguous')
            node = disks[0]
            G.require(self.target_read('target-driver', lambda: (node / 'device/driver').resolve().name) == 'virtio_blk'
                      and int(self.target_read('target-size', lambda: (node / 'size').read_text())) * 512 == self.context['disk_bytes'],
                      'owned target driver/size differs')
            path = Path('/dev/vda')
            info = self.target_read('target-node-stat', lambda: path.stat())
            major_minor = self.target_read('target-major-minor', lambda: (node / 'dev').read_text().strip())
            G.require(major_minor == str(os.major(info.st_rdev)) + ':' + str(os.minor(info.st_rdev))
                      and __import__('stat').S_ISBLK(info.st_mode), 'owned target device identity differs')
            all_disks = json.loads(self.target_read('target-lsblk-disks', lambda: self.command(['lsblk', '--json', '--bytes', '--nodeps', '-o', 'NAME,TYPE,SIZE']))[1])['blockdevices']
            G.require(type(all_disks) is list and len(all_disks) <= 32 and all(type(row) is dict and
                      type(row.get('name')) is str and len(row['name']) <= 128 and type(row.get('type')) is str
                      for row in all_disks), 'guest disk inventory is not bounded')
            persistent = []
            for row in all_disks:
                if row['type'] != 'disk':
                    continue
                if row['name'] != 'vda' and re.fullmatch(r'zram(0|[1-9][0-9]{0,3})', row['name']):
                    self.diagnostic_phase = 'target-lsblk-disks-ram-proof'
                    if proven_unbacked_zram(row):
                        self.diagnostic_phase = 'target-lsblk-disks'
                        continue
                    self.diagnostic_phase = 'target-lsblk-disks-ram-unproved'
                persistent.append(row['name'])
            G.require(persistent == ['vda'], 'unexpected writable guest disk')
            if pristine:
                self.diagnostic_phase = 'target-pristine-partitions'
                G.require(not any((n / 'partition').exists() and n.resolve().parent == node.resolve()
                                  for n in Path('/sys/class/block').iterdir()), 'owned target already has partitions')
                rows = json.loads(self.target_read('target-lsblk-mounts', lambda: self.command(['lsblk', '--json', '-o', 'NAME,MOUNTPOINTS', '/dev/vda']))[1])['blockdevices']
                G.require(len(rows) == 1 and not rows[0].get('children') and not any(rows[0].get('mountpoints') or []),
                          'owned target is already in use')
            self.diagnostic_phase = target_previous_phase
            return dict(path='/dev/vda', sysfs='/sys/class/block/vda', serial=self.context['disk_serial'],
                        disk_bytes=self.context['disk_bytes'], major_minor=major_minor)

        def writer(self, identities):
            daemon = identities['daemon']['pid']
            matches = []
            for node in Path('/proc').glob('[0-9]*'):
                try:
                    fields = (node / 'stat').read_text().rsplit(')', 1)[1].split()
                    if int(fields[1]) != daemon or (node / 'comm').read_text().strip() != 'rsync':
                        continue
                    proof, _ = G.process_proof(int(node.name), 0, '/usr/bin/rsync')
                    G.require(proof['argv'][-2:] == ['/run/rootfsbase/', '/mnt/']
                              and '--info=progress2' in proof['argv'], 'actual copy writer argv differs')
                    matches.append(proof)
                except (FileNotFoundError, ProcessLookupError):
                    pass
            G.require(len(matches) == 1, 'one original daemon-owned copy writer is required')
            process = matches[0]
            G.require(self.writer_identity is None or process == self.writer_identity, 'original copy writer was replaced')
            source = self.command(['findmnt', '--raw', '--noheadings', '--output', 'SOURCE', '--mountpoint', '/mnt'])[1]
            block = self.command(['findmnt', '--raw', '--nofsroot', '--noheadings', '--output', 'SOURCE', '--mountpoint', '/mnt'])[1]
            fstype = self.command(['findmnt', '--raw', '--noheadings', '--output', 'FSTYPE', '--mountpoint', '/mnt'])[1]
            G.require(re.fullmatch('/dev/vda[1-9][0-9]*', block) and fstype == 'btrfs'
                      and source in (block, block + '[/@]'), 'actual writer target mount is not owned btrfs')
            partition = Path('/sys/class/block') / Path(block).name
            G.require(partition.resolve().parent == Path('/sys/class/block/vda').resolve(), 'target partition belongs to another disk')
            return dict(process=process, ancestor_pids=[process['pid'], daemon], target_serial=self.context['disk_serial'],
                        mount=dict(target='/mnt', source=source, block_source=block, fstype=fstype,
                                   major_minor=(partition / 'dev').read_text().strip()))

        def visible(self, state, layers, outputs, expected_count=2):
            G.require(state['page'] == state['current'] == 'install' and state['keyboard'] == 'il'
                      and state['view'] == 'step' and state['connected'] is True and state['ready'] is True
                      and state['valid'] is True and state['busy'] is False and not state['failure']
                      and not state['error'] and not state['fields'] and 0 < state['percent'] < 100,
                      'actual active GUI state differs')
            # Reuse the audited geometry/layer proof, after independently requiring install.
            projected = dict(state, page='keyboard', current='keyboard')
            return G.window_proof(projected, layers, outputs, expected_count)

        def unchanged(self):
            identities = self.identities()
            G.require(self.baseline is None or identities == self.baseline['identities'], 'original active engine/GUI identity changed')
            engine = self.rpc.snapshot()
            options = engine['install']['options']; progress = options['progress']
            G.require(engine['hello']['state'] == engine['wizard']['state'] == 'installing'
                      and engine['wizard']['current'] == 'install' and engine['keyboard']['data'] == G.KEYBOARD
                      and progress['event'] == 'progress' and progress['phase'] == 'copy'
                      and type(progress['percent']) is int and 0 < progress['percent'] < 100
                      and progress['paused'] is False and not options['attention'] and not options['failed'],
                      'genuine copy phase is required for every disruption observation')
            G.require(self.rpc.config() == self.safe_config, 'active safe configuration changed')
            if self.baseline is not None:
                G.require(self.drm_heads() == self.baseline['drm_heads']
                          and self.packaged_sources() == self.baseline['packaged_sources'],
                          'active shipped sources or physical head binding changed')
            keyboard = self.keyboard_files()
            G.require(self.baseline is None or keyboard == self.baseline['keyboard_files'], 'active Hebrew configuration changed')
            writer = self.writer(identities)
            value = dict(engine=engine, identities=identities, keyboard_files=keyboard, config=self.safe_config,
                         writer=writer, elapsed_ns=time.monotonic_ns() - self.started_ns)
            G.require(not self.samples or progress['percent'] >= self.samples[-1]['engine']['install']['options']['progress']['percent'],
                      'active engine progress regressed')
            self.samples.append(value)
            return value

        def prepare(self):
            self.diagnostic_phase = 'prepare-find-gui'
            self.find_gui()
            self.diagnostic_phase = 'prepare-identities'
            self.identities()
            self.diagnostic_phase = 'prepare-rpc'
            self.rpc = ActiveRPC()
            self.diagnostic_phase = 'prepare-target'
            self.target_disk(pristine=True)
            self.diagnostic_phase = 'prepare-credentials'
            private = G.strict_json(G.read_regular('/run/t/active-credentials.json', 4096, True))
            G.require(set(private) == {'password'} and type(private['password']) is str
                      and re.fullmatch('[a-z0-9]{32}', private['password']), 'private credential fixture differs')
            self.password = private['password']
            pages = ('welcome', 'keyboard', 'network', 'timezone', 'disk', 'encryption', 'account', 'apps', 'summary')
            for page in pages:
                self.diagnostic_phase = 'prepare-' + page + '-ready'
                self.wait(lambda: (lambda s: s.get('page') == s.get('current') == page and s.get('ready') is True)(
                    G.strict_json(self.ipc('state'))), 30, 'real wizard page did not become ready')
                values = {'keyboard': {'layout': 'il', 'variant': ''}, 'disk': {'disk': '/dev/vda', 'mode': 'erase'},
                          'network': {'offline': True},
                          'encryption': {'enabled': False}, 'apps': {},
                          'account': dict(full_name='Arctic Qualification', username='arcticqual', hostname='arctic-qual',
                                          password=self.password, confirm=self.password, autologin=False, same_as_disk=False)}
                if page in values:
                    self.diagnostic_phase = 'prepare-' + page + '-fill'
                    G.require(self.ipc('fill', values[page]) == 'ok', 'real wizard fill failed')
                self.diagnostic_phase = 'prepare-' + page + '-valid'
                self.wait(lambda: G.strict_json(self.ipc('state')).get('valid') is True, 30, 'real wizard selection is invalid')
                if page == 'summary':
                    self.diagnostic_phase = 'prepare-summary-config'
                    self.safe_config = self.rpc.config()
                    G.require(self.safe_config['disk'] == {'disk': '/dev/vda', 'mode': 'erase'}
                              and self.safe_config['encryption'] == {'enabled': False}
                              and self.safe_config['network'] == {'offline': True}, 'safe Summary offline/disk/encryption differs')
                    self.diagnostic_phase = 'prepare-summary-identities'
                    self.prestart_identities = self.identities()
                self.diagnostic_phase = 'prepare-' + page + '-next'
                G.require(self.ipc('next') == 'ok', 'real wizard armed Next failed')
            self.password = None  # No credential payload survives into the public report.
            self.diagnostic_phase = 'prepare-copy'
            value = self.wait(self.unchanged, 180, 'real GUI engine did not enter genuine copy')
            self.diagnostic_phase = 'prepare-copy-identities'
            G.require(value['identities'] == self.prestart_identities, 'GUI Start replaced the original engine')
            self.writer_identity = value['writer']['process']
            self.diagnostic_phase = 'prepare-visible'
            state, outputs = self.state(), self.outputs()
            layers = G.strict_json(self.command(['mmsg', 'get', 'all-layers'], desktop=True)[1])['layers']
            visible = self.visible(state, layers, outputs)
            self.diagnostic_phase = 'prepare-baseline-physical'
            self.baseline = dict(value, target_disk=self.target_disk(), state=state, outputs=outputs, visible=visible,
                                 capture=self.capture('baseline', visible), drm_heads=self.drm_heads(),
                                 packaged_sources=self.packaged_sources(), rpc_peer=self.rpc.peer, scope=SCOPE)
            return self.baseline

        def verify(self, kind, cycle, disruption):
            self.active_session(True)
            proof = self.unchanged(); state, outputs = self.state(), self.outputs()
            layers = G.strict_json(self.command(['mmsg', 'get', 'all-layers'], desktop=True)[1])['layers']
            visible = self.visible(state, layers, outputs)
            return dict(kind=kind, cycle=cycle, status='passed', **proof, state=state, outputs=outputs,
                        visible=visible, disruption=disruption, capture=self.capture(kind + '-0', visible))

        def vt_cycle(self, cycle):
            G.require(cycle == 0, 'active VT matrix differs')
            self.unchanged(); away = stable = request = None
            try:
                self.command(['chvt', '6'])
                def inactive():
                    value = self.active_session(False)
                    G.require(value['foreground'] == 'tty6', 'actual active lane VT6 is not foreground')
                    return value
                away = self.wait(inactive, 15, 'actual active desktop did not deactivate')
                stable = self.unchanged()
                request = self.request('vt-away', 0, away=away, original_vt=self.original_vt,
                    engine_sha256=G.sha(json.dumps(stable['engine'], sort_keys=True).encode()))
                # Host’s bounded write-growth observation may wait for Btrfs’s
                # first flush. Retain real VT6 long enough for it and the capture.
                time.sleep(25)
            finally:
                self.native.execute(['chvt', str(self.original_vt)], timeout=8)
            return self.wait(lambda: self.verify('vt', 0, dict(away=away, prepared_state=stable,
                request=request, returned_vt=self.original_vt)), 25, 'same active installer did not restore after VT6')

        def output_cycle(self, cycle):
            self.active_session(True)
            before = self.unchanged(); outputs = self.outputs(); state = self.state()
            layers = G.strict_json(self.command(['mmsg', 'get', 'all-layers'], desktop=True)[1])['layers']
            hosting = self.visible(state, layers, outputs)['window']['screen']; heads = self.drm_heads()
            common = dict(mode='hosting-only', hosting_output=hosting, hosting_head=heads['outputs'][hosting]['head'],
                          enabled_outputs=sorted(o['name'] for o in G.enabled_outputs(outputs)))
            disconnect = self.request('output-disconnect', 0, **common, engine_sha256=G.sha(json.dumps(before['engine'], sort_keys=True).encode()))
            def relocated():
                proof = self.unchanged(); current, actual = self.state(), self.outputs()
                mapped = G.strict_json(self.command(['mmsg', 'get', 'all-layers'], desktop=True)[1])['layers']
                visible = self.visible(current, mapped, actual, 1)
                G.require(visible['window']['screen'] != hosting, 'active installer did not relocate')
                return dict(**proof, state=current, outputs=actual, visible=visible, enabled_output_count=1,
                            capture=self.capture('output-0-relocated', visible))
            unavailable = self.wait(relocated, 35, 'hosting output loss was not genuinely observed')
            restore = self.request('output-restore', 0, **common, enabled_output_count=1, outputs=unavailable['outputs'],
                                   outputs_sha256=G.sha(json.dumps(unavailable['outputs'], sort_keys=True).encode()),
                                   engine_sha256=G.sha(json.dumps(unavailable['engine'], sort_keys=True).encode()))
            return self.wait(lambda: self.verify('output', 0, dict(mode='hosting-only', hosting_output=hosting,
                hosting_head=common['hosting_head'], disconnect_request=disconnect, before=before,
                unavailable=unavailable, restore_request=restore)), 35, 'same active installer did not restore')

        def finish_install(self):
            def done():
                engine = self.rpc.snapshot()
                G.require(not engine['install']['options']['failed'] and not engine['install']['options']['attention'],
                          'real active installation failed or requires attention')
                if engine['hello']['state'] != 'done':
                    return None
                gui = G.strict_json(self.ipc('state'))
                G.require(gui['page'] == gui['current'] == 'done' and gui['percent'] == 100,
                          'same real GUI did not reach Done')
                identities = self.identities()
                G.require(identities == self.baseline['identities'] and self.rpc.config() == self.safe_config
                          and self.keyboard_files() == self.baseline['keyboard_files'], 'engine/choice changed before completion')
                return dict(engine=engine, identities=identities, config=self.safe_config, keyboard_files=self.keyboard_files(),
                            gui={k: gui[k] for k in ('page', 'current', 'percent')}, elapsed_ns=time.monotonic_ns() - self.started_ns)
            return self.wait(done, 40 * 60, 'same real installation did not finish within its separate bound')

        def cleanup(self):
            # Restore VT regardless of engine failure. Leave engine and GUI intact until
            # the owned VM is shut down; an incomplete install is never retried/faked.
            self.deadline = max(self.deadline, time.monotonic() + 30)
            result = dict(original_vt_restored=False, engine_retained=False, errors=[])
            try:
                self.native.execute(['chvt', str(self.original_vt)], timeout=8)
                self.wait(lambda: self.active_session(True), 8, 'active cleanup VT return failed')
                result['original_vt_restored'] = True
            except BaseException:
                result['errors'].append('active VT cleanup failed')
            try:
                result['engine_retained'] = self.baseline is not None and self.identities() == self.baseline['identities']
                G.require(result['engine_retained'], 'active cleanup engine changed')
            except BaseException:
                result['errors'].append('active engine retention check failed')
            return result

        def run(self):
            report = dict(schema=SCHEMA, stage='live', status='failed', context=self.context,
                          boot_id=self.boot_id, desktop_uid=self.uid, active_desktop_session=self.session,
                          original_vt=self.original_vt, release_acceptance=False, evidence_root=str(self.root),
                          cases=self.results, samples=self.samples)
            errors, security = [], None
            try:
                self.diagnostic_phase = 'security-init'
                security = self.native.SecurityInterval()
                self.diagnostic_phase = 'prepare-start'
                report['baseline'] = self.prepare()
                self.diagnostic_phase = 'vt-0'
                self.results.append(self.vt_cycle(0))
                self.diagnostic_phase = 'output-0'
                self.results.append(self.output_cycle(0))
                self.diagnostic_phase = 'completion'
                report['completion'] = self.finish_install()
            except BaseException as exc:
                # Free-form stderr/RPC/account text is deliberately not exported.
                errors.append(G.masked_active_error(exc, self.diagnostic_phase))
            finally:
                self.password = None
                report['cleanup'] = self.cleanup(); errors.extend(report['cleanup']['errors'])
                try:
                    G.require(security is not None, 'active security interval absent')
                    report['security'] = security.finish()
                except BaseException:
                    errors.append('active security interval failed')
                if self.rpc is not None:
                    self.rpc.close()
                if self.gui_fd is not None:
                    os.close(self.gui_fd)
            report['errors'], report['captures'] = errors, self.capture_count
            if not errors and len(self.results) == 2 and self.capture_count == 4 and 'completion' in report:
                report['status'] = 'passed'
            (self.root / 'installer-report.json').write_text(json.dumps(report, sort_keys=True, allow_nan=False) + '\n')
            return report
    return ActiveInstaller
