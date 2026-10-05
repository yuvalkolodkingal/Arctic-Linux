#!/usr/bin/env python3
"""Combine the probes into one self-contained script for the VM's data CD."""
import argparse
from pathlib import Path


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--wallpaper', action='store_true', help='Require the approved shared wallpaper publisher')
args = parser.parse_args()
root = Path(__file__).resolve().parent
sources = {name: (root/name).read_text() for name in ('guest.py', 'capabilities.py')}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(
    '#!/usr/bin/env python3\n'
    'measurement = {"__name__": "arctic_measurement", "__file__": __file__}\n'
    f'exec(compile({sources["guest.py"]!r}, __file__, "exec"), measurement)\n'
    'measurement["main"]()\n'
    'capabilities = {"__name__": "arctic_capabilities", "__file__": __file__}\n'
    f'exec(compile({sources["capabilities.py"]!r}, __file__, "exec"), capabilities)\n'
    f'raise SystemExit(capabilities["main"](measurement, wallpaper={args.wallpaper!r}))\n')
