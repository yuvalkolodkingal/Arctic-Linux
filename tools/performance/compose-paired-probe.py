#!/usr/bin/env python3
"""Freeze the same installed-system performance observer for both images."""
import argparse
from pathlib import Path
from contract import frozen_observer_bytes

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
source = (Path(__file__).resolve().parent / 'guest.py').read_bytes()
causal = (Path(__file__).resolve().parent / 'causal.py').read_bytes()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_bytes(frozen_observer_bytes(source, causal))
