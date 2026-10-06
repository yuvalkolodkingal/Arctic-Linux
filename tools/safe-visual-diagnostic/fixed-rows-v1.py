#!/usr/bin/env python3
"""Fixed ASCII diagnostic stimulus. No file, config, socket or network actions."""
import sys
import time
for row in range(1, 41):
    sys.stdout.write('%02d %s\n' % (row, ('ROW-%02d ' % row) * 15))
sys.stdout.flush()
time.sleep(150)
