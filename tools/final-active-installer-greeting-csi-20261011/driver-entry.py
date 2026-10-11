#!/usr/bin/env python3
"""Run only the reviewed readiness additions over the retained inner driver."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('active_diagnostic_composition', HERE / 'composition.py')
composition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(composition)


def main():
    manifest = json.loads((HERE / 'execution-manifest.json').read_bytes())
    composition.checked(manifest, ready=True)
    return composition.driver().main()


if __name__ == '__main__':
    raise SystemExit(main())
