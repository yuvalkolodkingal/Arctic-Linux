#!/usr/bin/env python3
"""Read configured Portage repositories without requiring privileges."""
import json
try:
    import portage
    packages = sorted(set(portage.db[portage.root]['porttree'].dbapi.cp_all()))
    print(json.dumps({'packages': packages}))
except Exception:
    print(json.dumps({'error': 'Could not read the Portage package index.'}))
