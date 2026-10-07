"""Bounded newc reader: data extraction only, no RPM transaction or scripts."""
from pathlib import Path
import hashlib
import os
import stat
from core import require, safe_child


def exact(stream, n):
    out = stream.read(n)
    require(len(out) == n, "truncated cpio member")
    return out


def unpack(stream, root, expected, max_bytes=1000000000):
    root = Path(root)
    require(root.is_dir() and not any(root.iterdir()), "nonempty cpio destination")
    seen, links, total = {}, {}, 0
    while True:
        h = exact(stream, 110)
        require(h[:6] == b"070701", "unsupported cpio format")
        try:
            values = [int(h[6 + 8*i:14 + 8*i], 16) for i in range(13)]
        except ValueError as e:
            raise RuntimeError("malformed cpio header") from e
        ino, mode, uid, gid, nlink, mtime, size, major, minor, rmajor, rminor, namesize, crc = values
        require(1 < namesize <= 4096 and size <= max_bytes, "cpio member limit")
        raw = exact(stream, namesize)
        require(raw[-1:] == b"\0" and b"\0" not in raw[:-1], "malformed cpio name")
        name = raw[:-1].decode("utf-8", "strict")
        exact(stream, (-(110 + namesize)) % 4)
        if name == "TRAILER!!!":
            require(size == 0, "cpio trailer data")
            padding = stream.read(4097)
            require(len(padding) <= 4096 and not padding.strip(b"\0"), "extra cpio stream/trailing data")
            break
        if name.startswith("./"):
            name = name[2:]
        dest = safe_child(root, name)
        require(name in expected and name not in seen, "unexpected/duplicate payload member")
        e = expected[name]
        require(stat.S_IFMT(mode) == stat.S_IFMT(e["mode"]), "payload/header type mismatch")
        require(stat.S_IMODE(mode) == stat.S_IMODE(e["mode"]), "payload/header mode mismatch")
        require(uid == e["uid"] and gid == e["gid"], "payload/header ownership mismatch")
        require(not stat.S_IMODE(mode) & 0o6000, "setid payload unsupported for component")
        total += size
        require(total <= max_bytes and len(seen) < 100000, "cpio total limit")
        data = exact(stream, size)
        exact(stream, (-size) % 4)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if stat.S_ISDIR(mode):
            require(not data and not dest.is_symlink(), "directory payload/linked destination")
            dest.mkdir(exist_ok=True)
        elif stat.S_ISLNK(mode):
            target = data.decode("utf-8", "strict")
            require(target == e["link"] and target and "\x00" not in target, "symlink/header mismatch")
            require(not dest.exists() and not dest.is_symlink(), "duplicate destination")
            os.symlink(target, dest)
        elif stat.S_ISREG(mode):
            require(nlink > 0 and nlink <= 100000, "hardlink count")
            if nlink > 1:
                group = links.setdefault((major, minor, ino), {"names": [], "data": None, "nlink": nlink,
                    "metadata": (mode, uid, gid, e["digest_algorithm"], e["digest"])})
                require(group["nlink"] == nlink, "hardlink header disagreement")
                require(group["metadata"] == (mode, uid, gid, e["digest_algorithm"], e["digest"]),
                    "hardlink signed metadata disagreement")
                group["names"].append(name)
                if data:
                    require(group["data"] is None, "duplicate hardlink content")
                    group["data"] = data
            else:
                require(hashlib.new(e["digest_algorithm"], data).hexdigest() == e["digest"],
                    "payload/header content mismatch")
                with dest.open("xb") as f:
                    f.write(data)
                dest.chmod(stat.S_IMODE(mode))
        else:
            raise RuntimeError("special payload member unsupported")
        seen[name] = mode
    require(set(seen) == set(expected), "missing payload members (directories included)")
    for group in links.values():
        require(len(group["names"]) == group["nlink"], "incomplete hardlink group")
        data = group["data"] if group["data"] is not None else b""
        first = None
        for name in group["names"]:
            e = expected[name]
            require(hashlib.new(e["digest_algorithm"], data).hexdigest() == e["digest"],
                "hardlink/header content mismatch")
            dest = safe_child(root, name)
            if first is None:
                with dest.open("xb") as f:
                    f.write(data)
                dest.chmod(stat.S_IMODE(e["mode"]))
                first = dest
            else:
                os.link(first, dest, follow_symlinks=False)
    # Apply directory modes after contents, so read-only signed directories do
    # not obstruct inert extraction. Ancestors remain subject to safe_child.
    for name, entry in sorted(expected.items(), key=lambda row: row[0].count("/"), reverse=True):
        if stat.S_ISDIR(entry["mode"]):
            safe_child(root, name).chmod(stat.S_IMODE(entry["mode"]))
    return {"members": len(seen), "data_bytes": total, "scripts_executed": False}
