#!/bin/sh
# Link the reduced-motion flag for the Arctic Plymouth theme when the kernel
# command line has arctic.reduce_motion=1 (also accepts =yes / =true / bare).
read -r cmdline < /proc/cmdline || cmdline=""
for arg in $cmdline; do
    case "$arg" in
        arctic.reduce_motion|arctic.reduce_motion=1|arctic.reduce_motion=yes|arctic.reduce_motion=true)
            mkdir -p /run/arctic
            ln -sf /usr/share/plymouth/themes/arctic/dot.png /run/arctic/reduce-motion.png
            ;;
    esac
done
exit 0
