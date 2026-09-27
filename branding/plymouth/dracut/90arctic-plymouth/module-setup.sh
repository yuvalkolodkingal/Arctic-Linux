#!/usr/bin/bash
# dracut module: honour arctic.reduce_motion=1 in the Arctic boot splash.
#
# Plymouth script themes cannot read the kernel command line, so before
# plymouthd starts (ExecStartPre of plymouth-start.service) a tiny hook links
# /run/arctic/reduce-motion.png when the argument is present; arctic.script
# loads that path and, if it exists, keeps the mark and dots still. /run
# survives the switch to the real root, so the shutdown splash follows too.
# Installed by arctic-plymouth-theme to /usr/lib/dracut/modules.d/90arctic-plymouth/.

check() {
    require_binaries plymouthd || return 1
    return 0
}

depends() {
    echo plymouth
    return 0
}

# shellcheck disable=SC2154  # $moddir and $systemdsystemunitdir come from dracut
install() {
    inst_simple "$moddir/arctic-reduce-motion.sh" /usr/libexec/arctic/plymouth-reduce-motion
    inst_simple "$moddir/arctic-reduce-motion.conf" \
        "${systemdsystemunitdir:-/usr/lib/systemd/system}/plymouth-start.service.d/arctic-reduce-motion.conf"
}
