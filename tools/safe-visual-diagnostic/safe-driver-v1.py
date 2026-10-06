#!/usr/bin/env python3
"""QMP Safe diagnosis only; called by the default-off test-iso hook."""
import json
import os
from pathlib import Path
import time


def require(value, message):
    if not value:
        raise RuntimeError(message)


def qemu_process_origin(pid):
    """Actual /proc start tick, calibrated to this host's monotonic clock.

The start tick is quantized to 1/HZ; retain that precision and calibration bounds.
No claimed guest kernel/performance timestamp is derived from this estimate.
"""
    ticks = int((Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19])
    hz = os.sysconf('SC_CLK_TCK')
    before = time.monotonic()
    boot = time.clock_gettime(time.CLOCK_BOOTTIME)
    after = time.monotonic()
    return dict(pid=pid, start_ticks=ticks, ticks_per_second=hz,
                monotonic_estimate_seconds=(before+after)/2 + ticks/hz - boot,
                precision_seconds=1/hz+(after-before), calibration_monotonic_before=before,
                calibration_monotonic_after=after, calibration_boottime=boot)


def run(vm, out, qemu_origin, entry_origin, menu_seen, clock=time.monotonic, sleep=time.sleep):
    require(menu_seen, 'Diagnostic requires detected/selected Safe entry')
    out = Path(out)
    log = out / 'safe-events.log'
    require(not log.exists(), 'Safe event evidence must be unused')

    def record(event, **values):
        now = clock()
        item = dict(event=event, monotonic_seconds=now,
                    qemu_elapsed_seconds=now-qemu_origin['monotonic_estimate_seconds'],
                    entry_elapsed_seconds=now-entry_origin, **values)
        with log.open('a') as stream:
            stream.write(json.dumps(item, sort_keys=True) + '\n')
        return item

    def capture(name):
        require(vm.alive(), 'Owned VM exited before capture')
        path = vm.shot(name)
        require(path and Path(path).is_file(), 'Required QMP screenshot failed: ' + name)
        record('capture', name=name + '.png')

    def wait_until(target):
        while clock() < target:
            require(vm.alive(), 'Owned VM exited during bounded wait')
            sleep(min(.5, target-clock()))

    def serial_records(prefix):
        path = out / 'serial.log'
        text = path.read_text(errors='replace') if path.exists() else ''
        return [json.loads(line[len(prefix):]) for line in text.splitlines() if line.startswith(prefix)]

    def await_marker(marker, seconds):
        end = clock() + seconds
        while clock() < end:
            values = serial_records('ARCTIC-SAFE-' + marker + ' ')
            if values:
                require(len(values) == 1, 'Duplicate guest marker: ' + marker)
                record('guest-marker', marker=marker, value=values[0])
                return values[0]
            require(vm.alive(), 'Owned VM exited while awaiting guest marker')
            sleep(.5)
        raise RuntimeError('Guest marker timeout: ' + marker)

    record('passive-begin', requested_seconds=600, no_input=True, qemu_origin=qemu_origin,
           entry_selection_monotonic_origin=entry_origin)
    for elapsed in list(range(0, 121, 10)) + list(range(180, 601, 60)):
        wait_until(entry_origin + elapsed)
        capture('safe-passive-%04ds' % elapsed)
    quiet_origin = record('passive-end', no_input=True)['monotonic_seconds']
    # Additional bounded quiet window makes an explicit 120-second no-input control.
    for elapsed in (660, 720):
        wait_until(max(entry_origin + elapsed, quiet_origin + elapsed - 600))
        capture('safe-quiet-%04ds' % elapsed)
    record('quiet-end', no_input=True)
    capture('safe-10-before-pointer')
    started = record('pointer-only', position='outside welcome, no click or key')['monotonic_seconds']
    response = vm.cmd('input-send-event', events=[
        {'type': 'abs', 'data': {'axis': 'x', 'value': 3000}},
        {'type': 'abs', 'data': {'axis': 'y', 'value': 3000}}])
    require('error' not in response, 'QMP pointer-only input failed; no fallback input permitted')
    record('input-complete', phase='pointer-only', input_origin_monotonic_seconds=started,
           call_elapsed_seconds=clock()-started)
    for elapsed in (1, 5):
        wait_until(started + elapsed); capture('safe-11-pointer-%02ds' % elapsed)
    started = record('super-enter')['monotonic_seconds']
    vm.keys('meta_l-ret')
    record('input-complete', phase='super-enter', input_origin_monotonic_seconds=started,
           call_elapsed_seconds=clock()-started)
    for elapsed in (1, 5, 60):
        wait_until(started + elapsed); capture('safe-20-super-enter-%02ds' % elapsed)
    started = record('return-only')['monotonic_seconds']
    vm.keys('ret')
    record('input-complete', phase='return-only', input_origin_monotonic_seconds=started,
           call_elapsed_seconds=clock()-started)
    for elapsed in (1, 5):
        wait_until(started + elapsed); capture('safe-30-return-%02ds' % elapsed)
    record('collector-command', scope='post-separated-input read-only telemetry')
    vm.type_text('sudo sh /dev/sr1', gap=.2)
    vm.keys('ret')
    ready = await_marker('GRIM-READY', 120)
    require(ready.get('wait_seconds') == 20 and not serial_records('ARCTIC-SAFE-GRIM-BEGIN '), 'Guest screencopy began before host pre-capture')
    capture('safe-40-qmp-before-grim')
    require(not serial_records('ARCTIC-SAFE-GRIM-BEGIN '), 'Guest screencopy overlapped host pre-capture; cannot qualify pair')
    await_marker('GRIM-DONE', 60)
    capture('safe-41-qmp-after-grim')
    end = await_marker('END', 120)
    capture('safe-99-final')
    require(end.get('status') == 'collected' and end.get('error') is None and end.get('release_acceptance') is False,
            'Guest telemetry/security collector failed; original Safe visual gate stays open')
    record('diagnostic-complete', release_acceptance=False, safe_visual_gate='open')
