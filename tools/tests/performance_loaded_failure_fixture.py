"""Exact inverse of the fail-only loaded-code projection; no runtime stubs."""
import hashlib
import re

FROZEN = b'ca667dc850db8483e4066d45ec39f118aae5be3ebbe777c7d1ed9297b4c4bb1b'
PREVIOUS_FROZEN = b'fbc6648c165470b9a1aa8cdb0831bc50b3f3e8565953653b32e42eaa614d8cb4'


def reader_before_projection(raw):
    raw = re.sub(rb'(?ms)^[ ]*# loaded-failure-only-begin\n.*?^[ ]*# loaded-failure-only-end\n', b'', raw)
    raw = b''.join(line for line in raw.splitlines(keepends=True) if not line.rstrip().endswith(b'# loaded-failure-only'))
    old = b"frames='unavailable', candidates='unavailable', format='none'),\n"
    assert raw.count(old) == 1
    raw = raw.replace(old, old[:-3] + b")),\n")
    historical = raw.replace(FROZEN, PREVIOUS_FROZEN)
    assert hashlib.sha256(historical).hexdigest() == 'ef4e4c0c6304b853a918a69cd447bc80a179424f46f6887aadb5786de14be911'
    return raw


def consumer_before_projection(raw):
    raw = re.sub(rb'(?ms)^[ ]*# loaded-failure-only-begin\n.*?^[ ]*# loaded-failure-only-end\n', b'', raw)
    assert raw.count(b", 'loaded_failure'}") == 1
    raw = raw.replace(b", 'loaded_failure'}", b"}")
    assert hashlib.sha256(raw).hexdigest() == '7e018cb8e378fedc8ea252fca5f1dfbef3912ffaa50b0e6896cbd934df549743'
    return raw
