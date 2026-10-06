#!/usr/bin/env python3
"""Freeze the same installed-system performance observer for both images."""
import argparse
import hashlib
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
source = (Path(__file__).resolve().parent / 'guest.py').read_text()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(
    '#!/usr/bin/env python3\nimport sys\n'
    'measurement = {"__name__": "arctic_measurement", "__file__": __file__}\n'
    f'exec(compile({source!r}, __file__, "exec"), measurement)\n'
    'if sys.argv[1] == "installed":\n'
    f'    measurement["emit"]("observer_source_sha256", {hashlib.sha256(source.encode()).hexdigest()!r})\n'
    '    measurement["main"](preconditioned=True)\n'
    'else:\n'
    '    print("ARCTIC-PERFORMANCE-SKIPPED: live stage; installed comparison only", flush=True)\n')
