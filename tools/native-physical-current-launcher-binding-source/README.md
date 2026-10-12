Disabled Source-only repair of two stale launcher identity literals.

The current v6 checker calls verify_barrier with the full current launcher SHA256. Both physical controllers must compare that exact bound identity. All other original code bytes, ownership, nonce, checker, UID, boot, one-use, action and timing predicates remain unchanged. Canonical files and every prior execution remain untouched. This component does not authenticate the cause of any completed runtime failure or authorize a new execution.
