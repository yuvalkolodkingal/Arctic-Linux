#!/usr/bin/env python3
"""Render the actual battery widgets and exercise Quickshell's UPower wire mapping.

Needs quickshell, Qt SVG, python3-dbus, python3-gobject-base, python3-pillow and
dbus-daemon. Uses an offscreen window and a private bus; no hardware/power setting,
real desktop, notification daemon or package transaction is touched.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from PIL import Image, ImageChops
import dbus


SOURCE = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def block(text, marker, start):
    """Copy a production QML object, including its real bindings and geometry."""
    position = text.index(marker)
    begin = text.rfind(start, 0, position)
    check(begin >= 0, 'Missing production component: ' + marker)
    depth = 0
    quoted = None
    escaped = False
    comment = False
    for index in range(text.index('{', begin), len(text)):
        char = text[index]
        if comment:
            if char == '\n':
                comment = False
        elif quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quoted:
                quoted = None
        elif text[index:index + 2] == '//':
            comment = True
        elif char in "'\"":
            quoted = char
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[begin:index + 1]
    raise AssertionError('Unbalanced production QML object')


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def wait(predicate, message):
    for _ in range(100):
        if predicate():
            return
        time.sleep(.05)
    raise AssertionError(message)


def prepare(directory, negative=False):
    module = directory / 'service'
    module.mkdir()
    for name in ('BatteryService.qml', 'BatteryModel.js', 'Icon.qml', 'BarItem.qml', 'FocusRing.qml'):
        shutil.copy2(SOURCE / name, module / name)
    shutil.copytree(SOURCE / 'assets', module / 'assets')
    if negative:
        icon = module / 'Icon.qml'
        original = icon.read_text()
        broken = original.replace('Icons.icon(name, color, 0, batteryPercent)', 'Icons.icon(name, color)')
        check(broken != original, 'Negative control did not disable the live fill')
        icon.write_text(broken)
    (module / 'qmldir').write_text('singleton Theme 1.0 Theme.qml\nsingleton Session 1.0 Session.qml\n'
                                'singleton BatteryService 1.0 BatteryService.qml\n'
                                'singleton PowerService 1.0 PowerService.qml\n'
                                'BarItem 1.0 BarItem.qml\nIcon 1.0 Icon.qml\nFocusRing 1.0 FocusRing.qml\n')
    (module / 'Theme.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
    property color ink: "#151a21"
    property color ground: "#ffffff"
    property int barHeight: 40
    readonly property color error: "#b30000"
    readonly property color surfaceSunken: ground
    readonly property color accent: ink
    readonly property color accentPressed: ink
    readonly property color accentHover: ink
    readonly property color accentEdge: ink
    readonly property color focus: ink
    readonly property bool dark: false
    readonly property int focusWidth: 2
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int durationFast: 0
    readonly property string fontSans: "sans-serif"
}''')
    (module / 'Session.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { '
                                     'readonly property var settings: ({batteryWarnings: false}); '
                                     'readonly property string scripts: ' + json.dumps(str(SOURCE / 'scripts')) + '; }')
    (module / 'PowerService.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { '
                                          'readonly property bool available: false; readonly property var current: null; }')
    horizontal = block((SOURCE / 'Bar.qml').read_text(), 'id: batteryItem', 'BarItem {')
    vertical_source = (SOURCE / 'VerticalBar.qml').read_text()
    button = block(vertical_source, 'id: button', 'component Button: BarItem {')
    vertical = block(vertical_source, 'id: battery\n', 'Button {')
    geometry = '\n'.join(re.findall(r'^    readonly property (?:real|int) (?:controlWidth|controlHeight|iconSize|textSize):.*$',
                                    vertical_source, re.M))
    qml = '''import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import "service"
Scope {
    id: harness
    readonly property alias window: bar
    Window {
        id: bar; visible: true; width: 400; height: 180; color: Theme.ground
        readonly property var shell: ({togglePanel: function() {}})
        function menuOpen(name) { return false; }
        function hint(item, text) {}
        function unhint(item) {}
        HORIZONTAL
        Item {
            id: root; x: 150; width: Theme.barHeight; height: 140
            readonly property var bar: harness.window
            GEOMETRY
            function open(name, item) {}
            function coordinate(item) { return 0; }
            BUTTON
            ColumnLayout { width: parent.width; VERTICAL }
        }
        Icon { id: probe; x: 250; y: 30; size: 16; color: Theme.ink;
            name: BatteryService.charging ? 'battery-charging' : 'battery'; batteryPercent: BatteryService.percent }
    }
    IpcHandler {
        target: "batteryTest"
        function sample(): string {
            return JSON.stringify({present: BatteryService.present, percent: BatteryService.percent,
                chargeKnown: BatteryService.chargeKnown, charging: BatteryService.charging,
                full: BatteryService.full, low: BatteryService.low, text: BatteryService.percentText,
                time: BatteryService.timeText, health: BatteryService.healthPercent,
                horizontalVisible: batteryItem.visible, verticalVisible: battery.visible,
                horizontalName: batteryItem.Accessible.name, verticalName: battery.Accessible.name});
        }
        function warningReset(): string {
            BatteryService.warnedLow = true; BatteryService.warnedCritical = true; BatteryService.hookedLow = true;
            BatteryService.check();
            return JSON.stringify([BatteryService.warnedLow, BatteryService.warnedCritical, BatteryService.hookedLow]);
        }
        function capture(prefix: string, size: int, dark: bool): void {
            Theme.ink = dark ? "#ffffff" : "#151a21";
            Theme.ground = dark ? "#151a21" : "#ffffff";
            Theme.barHeight = size * 2; probe.size = size;
            Qt.callLater(function() {
                probe.grabToImage(function(result) { result.saveToFile(prefix + "-icon.png"); });
                batteryItem.grabToImage(function(result) { result.saveToFile(prefix + "-horizontal.png"); });
                battery.grabToImage(function(result) { result.saveToFile(prefix + "-vertical.png"); });
                function findIcon(item) {
                    if (item.name === "battery" || item.name === "battery-charging") return item;
                    for (let child of item.children || []) {
                        const found = findIcon(child); if (found) return found;
                    }
                    return null;
                }
                findIcon(batteryItem).grabToImage(function(result) { result.saveToFile(prefix + "-horizontal-icon.png"); });
                findIcon(battery).grabToImage(function(result) { result.saveToFile(prefix + "-vertical-icon.png"); });
            });
        }
    }
}'''.replace('HORIZONTAL', horizontal).replace('GEOMETRY', geometry).replace('BUTTON', button).replace('VERTICAL', vertical)
    qml_path = directory / 'shell.qml'
    qml_path.write_text(qml)
    return qml_path


def interior_ink(path, dark, x=15.5, y=12):
    image = Image.open(path).convert('RGBA')
    pixel = image.getpixel((min(image.width - 1, int(x * image.width / 24)),
                            min(image.height - 1, int(y * image.height / 24))))
    # grabToImage keeps transparency; composite against the actual test theme.
    bg = (21, 26, 33) if dark else (255, 255, 255)
    rgb = [pixel[i] * pixel[3] / 255 + bg[i] * (1 - pixel[3] / 255) for i in range(3)]
    return sum(rgb) / 3 > 180 if dark else sum(rgb) / 3 < 100


def run(out, scale):
    check(shutil.which('quickshell') and shutil.which('dbus-daemon'), 'Quickshell and dbus-daemon are required')
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='arctic-battery-') as temporary:
        base = Path(temporary)
        bus_process = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--nopidfile', '--print-address=1'],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        fixture = None
        shell = None
        connection = None
        log = None
        try:
            address = bus_process.stdout.readline().strip()
            check(bool(address), 'Private bus did not start')
            runtime = base / 'runtime'
            runtime.mkdir(mode=0o700)
            env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS=address, DBUS_SESSION_BUS_ADDRESS=address,
                       ARCTIC_BATTERY_TEST_BUS=address, XDG_RUNTIME_DIR=str(runtime),
                       QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                       QT_SCALE_FACTOR=str(scale), QT_QPA_PLATFORMTHEME='generic', QT_NO_XDG_DESKTOP_PORTAL='1')
            for key in ('WAYLAND_DISPLAY', 'DISPLAY', 'SWAYSOCK'):
                env.pop(key, None)
            fixture = subprocess.Popen([sys.executable, str(SOURCE / 'dev/fixtures/battery-upower.py')], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            connection = dbus.bus.BusConnection(address)
            wait(lambda: connection.name_has_owner('org.freedesktop.UPower'), 'Private UPower fixture did not start')
            device = dbus.Interface(connection.get_object('org.freedesktop.UPower',
                                    '/org/freedesktop/UPower/devices/DisplayDevice'), 'org.arcticlinux.BatteryFixture')
            report = dict(scale=scale, cases=[], rendered=[], negative_control=None,
                          source_sha256={str(path.relative_to(SOURCE)): hashlib.sha256(path.read_bytes()).hexdigest()
                                         for path in [SOURCE / name for name in
                                                      ('BatteryService.qml', 'BatteryModel.js', 'Icon.qml', 'BarItem.qml',
                                                       'Bar.qml', 'VerticalBar.qml', 'LockScreen.qml', 'QuickSettingsPanel.qml',
                                                       'BatteryPanel.qml', 'assets/Icons.js', 'dev/test-battery-indicator.py',
                                                       'dev/fixtures/battery-upower.py')]})
            for negative in (False, True):
                directory = base / ('negative' if negative else 'positive')
                directory.mkdir()
                qml = prepare(directory, negative)
                log_path = out / ('negative.log' if negative else 'positive.log')
                log = log_path.open('w')
                shell = subprocess.Popen(['quickshell', '--no-color', '-p', str(qml)], env=env, stdout=log, stderr=log)

                def ipc(function, *arguments):
                    result = subprocess.run(['quickshell', 'ipc', '-p', str(qml), 'call', 'batteryTest', function,
                                             *map(str, arguments)], env=env, text=True, capture_output=True, timeout=5)
                    check(result.returncode == 0, result.stdout + result.stderr + log_path.read_text())
                    return result.stdout.strip()

                wait(lambda: shell.poll() is not None or 'Configuration Loaded' in log_path.read_text(), 'QML did not load')
                check(shell.poll() is None, log_path.read_text())
                sample = lambda: json.loads(ipc('sample'))
                wait(lambda: sample()['present'], 'Display device did not become ready')
                if not negative:
                    aggregate = sample()
                    check(aggregate['percent'] == 70, 'Must use the multi-battery aggregate, not BAT0 or unweighted mean')
                    check(aggregate['health'] == 98, 'Health Capacity is raw 0..100, unlike charge Percentage')
                    report['aggregate'] = aggregate
                    cases = [(0, 3, 0, False, False), (1, 2, 1, False, False),
                             (80, 4, 80, False, True), (99.4, 2, 99, False, False),
                             (99.5, 4, 100, False, True), (100, 4, 100, False, True),
                             (100, 2, 100, False, False), (102, 2, 100, False, False),
                             (50, 1, 50, True, False), (100, 1, 100, True, False),
                             (80, 5, 80, True, False), (70, 6, 70, False, False),
                             (70, 0, 70, False, False), (float('nan'), 0, -1, False, False)]
                    for wire, state, expected, charging, full in cases:
                        device.Change(dbus.Double(wire), dbus.UInt32(state), True)
                        wait(lambda: sample()['percent'] == expected and sample()['charging'] == charging
                             and sample()['full'] == full, 'Wire mapping/state did not propagate')
                        actual = sample()
                        check(actual['text'] == (str(expected) + '%' if expected >= 0 else 'Charge unknown'), str(actual))
                        check('Battery' in actual['horizontalName'] and 'Battery' in actual['verticalName'], 'Accessible names lost battery context')
                        if expected < 0:
                            check(not actual['low'] and not actual['chargeKnown'], 'Unknown charge must not produce an empty/low reading')
                            check(json.loads(ipc('warningReset')) == [False, False, False],
                                  'Plugging in must reset discharge warnings even with an unknown reading')
                        if state == 0:
                            check(actual['time'] == 'Status unavailable', 'Unknown state needs a text explanation')
                        report['cases'].append(dict(wire=None if math.isnan(wire) else wire, state=state, result=actual))
                for dark in (False, True):
                    for size in (16, 20, 24, 32):
                        for wire, state in ((0, 2), (50, 2), (80, 4), (80, 5), (99.4, 2),
                                            (99.5, 4), (100, 4), (100, 1), (float('nan'), 0)):
                            if negative and (dark or size != 16 or wire != 100 or state != 4):
                                continue
                            expected = -1 if math.isnan(wire) else min(100, round(wire))
                            # JS rounds .5 upward; Python uses ties-to-even (99.5 is also100).
                            device.Change(dbus.Double(wire), dbus.UInt32(state), True)
                            wait(lambda: sample()['percent'] == expected and sample()['charging'] == (state in (1, 5)), 'Render state did not propagate')
                            label = f'{"negative" if negative else "positive"}-{dark}-{size}-{wire}-{state}'
                            prefix = out / label
                            for kind in ('icon', 'horizontal', 'vertical', 'horizontal-icon', 'vertical-icon'):
                                Path(str(prefix) + '-' + kind + '.png').unlink(missing_ok=True)
                            ipc('capture', prefix, size, str(dark).lower())
                            wait(lambda: all(Path(str(prefix) + '-' + kind + '.png').exists()
                                             for kind in ('icon', 'horizontal', 'vertical', 'horizontal-icon', 'vertical-icon')),
                                 'Render capture did not complete')
                            icon = Path(str(prefix) + '-icon.png')
                            filled = interior_ink(icon, dark)
                            if negative:
                                check(not filled, 'Negative control did not reproduce the partly filled100% artwork')
                                report['negative_control'] = dict(reproduced=True, rejected_by_full_gate=True, image=str(icon))
                            elif expected == 100:
                                check(filled, f'100% did not reach the right interior: {icon}')
                            elif expected in (0, 50, 80):
                                check(not filled, f'{expected}% filled the100% interior: {icon}')
                            for kind in ('horizontal', 'vertical'):
                                actual_bar_icon = Path(str(prefix) + '-' + kind + '-icon.png')
                                if expected == 100:
                                    check(interior_ink(actual_bar_icon, dark) == (not negative),
                                          f'{kind} bar did not propagate the100% fill: {actual_bar_icon}')
                                elif expected in (0, 50, 80):
                                    check(not interior_ink(actual_bar_icon, dark), f'{kind} bar has a static fill')
                            if not negative and wire == 100 and state == 1:
                                plain = Image.open(out / f'positive-{dark}-{size}-100-4-icon.png').convert('RGBA')
                                charged = Image.open(icon).convert('RGBA')
                                background = Image.new('RGBA', plain.size, '#151a21' if dark else '#ffffff')
                                difference = ImageChops.difference(Image.alpha_composite(background, plain).convert('RGB'),
                                                                  Image.alpha_composite(background, charged).convert('RGB'))
                                roi = tuple(int(value * plain.width / 24) for value in (8.5, 9.8, 14.8, 14.2))
                                check(difference.crop(roi).getbbox(), 'Charging bolt lost contrast over a full battery')
                            expected_pixels = round(size * scale)
                            check(Image.open(icon).size == (expected_pixels, expected_pixels),
                                  'Icon physical pixels do not match logical size × device scale')
                            report['rendered'].append(dict(label=label, filled_right_interior=filled,
                                                           icon=str(icon), horizontal=str(prefix) + '-horizontal.png',
                                                           vertical=str(prefix) + '-vertical.png'))
                if not negative:
                    device.Change(dbus.Double(100), dbus.UInt32(4), False)
                    wait(lambda: not sample()['present'] and not sample()['horizontalVisible']
                         and not sample()['verticalVisible'], 'Removed battery remained visible')
                    report['removed'] = sample()
                    device.Change(dbus.Double(100), dbus.UInt32(4), True)
                    wait(lambda: sample()['present'], 'Reinserted battery did not become visible')
                stop(shell)
                shell = None
                log.close()
                log = None
                check(not re.search(r'ReferenceError|TypeError|ERROR:|Binding loop', log_path.read_text()),
                      'Runtime QML error in battery harness: ' + log_path.read_text())
            check(report['negative_control'], 'Negative control was not run')
            report['passed'] = True
            (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
            print(f'PASS: aggregate/state mapping, {len(report["rendered"])} rendered cases, static-fill negative control; scale={scale}')
        finally:
            if shell:
                stop(shell)
            if fixture:
                stop(fixture)
                fixture.stderr.close()
            if connection:
                connection.close()
            stop(bus_process)
            bus_process.stdout.close()
            if log:
                log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('/tmp/arctic-battery-shots'))
    parser.add_argument('--scale', type=float, default=1)
    args = parser.parse_args()
    run(args.out.resolve(), args.scale)
