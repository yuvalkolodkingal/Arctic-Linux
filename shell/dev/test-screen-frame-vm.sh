#!/usr/bin/env bash
# Run the private compositor replay with Fedora's real kernel and allocator.
# The hosted Azure kernel lacks CONFIG_UDMABUF. No host GPU or kernel module is used.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]] || {
  echo 'This fixture requires a disposable GitHub-hosted runner.' >&2; exit 2;
}
[[ "${GITHUB_REPOSITORY:-}" == yuvalkolodkingal/Arctic-Linux ]] || exit 2
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$REPO/out/test/frame-vm"
mkdir -p "$WORK/root" "$WORK/initrd/bin" "$WORK/initrd/dev" "$WORK/initrd/proc" "$WORK/initrd/sys" "$WORK/initrd/newroot"
[[ ! -e "$WORK/guest.tar" ]] || { echo 'The VM fixture already exists.' >&2; exit 2; }
container=""
cleanup() { [[ -z "$container" ]] || docker rm -f "$container" >/dev/null; }
trap cleanup EXIT
container=$(docker create -v "$REPO:/arctic:ro" registry.fedoraproject.org/fedora:44 bash -euxc '
  dnf -y install kernel-core kernel-modules-core kmod git quickshell qt6-qtsvg qt6-qtwayland \
    sway grim wlr-randr python3 python3-pillow python3-pyte python3-dbus python3-gobject-base \
    dbus-daemon fontconfig google-noto-sans-fonts procps-ng libcap gcc wayland-devel \
    mesa-dri-drivers findutils which glib2
  dnf -y install /arctic/out/frame-rpms/repo/mangowm-*.x86_64.rpm
  mkdir -p /arctic /root /run /tmp
  kernel=$(rpm -q kernel-core --qf "%{VERSION}-%{RELEASE}.%{ARCH}")
  test -f "/lib/modules/$kernel/vmlinuz"
  grep -E "^CONFIG_UDMABUF=(y|m)$" "/lib/modules/$kernel/config"
  printf "%s\n" "$kernel" > /frame-kernel
  dnf clean all
')
docker start -a "$container"
docker export "$container" > "$WORK/guest.tar"
sudo tar -xf "$WORK/guest.tar" -C "$WORK/root"
# QEMU runs as the runner. Passthrough exports must be accessible to that user,
# including the fixture's /root; this tree is rendering-only, not an OS install.
sudo chown -R "$(id -u):$(id -g)" "$WORK/root"
kernel=$(cat "$WORK/root/frame-kernel")
cp "$WORK/root/lib/modules/$kernel/vmlinuz" "$WORK/vmlinuz"
cp /bin/busybox "$WORK/initrd/bin/busybox"
(ldd "$WORK/initrd/bin/busybox" 2>&1 || true) | grep -Eq 'not a dynamic executable|statically linked'
sudo cp /bin/busybox "$WORK/root/frame-busybox"
for module in virtio_pci 9pnet_virtio 9p; do
  sudo modprobe --show-depends --dirname "$WORK/root" --set-version "$kernel" "$module"
done | awk '$1 == "insmod" {print $2}' | sort -u > "$WORK/modules"
while IFS= read -r file; do
  relative=$(basename "$file")
  target="$WORK/initrd/lib/modules/$kernel/kernel/${relative%.xz}"
  target="${target%.zst}"
  mkdir -p "$(dirname "$target")"
  case "$file" in
    *.xz) xz -dc "$file" > "$target" ;;
    *.zst) zstd -dc "$file" > "$target" ;;
    *) cp "$file" "$target" ;;
  esac
done < "$WORK/modules"
for metadata in modules.order modules.builtin modules.builtin.modinfo; do
  if [[ -f "$WORK/root/lib/modules/$kernel/$metadata" ]]; then
    cp "$WORK/root/lib/modules/$kernel/$metadata" "$WORK/initrd/lib/modules/$kernel/"
  fi
done
depmod --basedir "$WORK/initrd" "$kernel"
cat > "$WORK/initrd/init" <<'INIT'
#!/bin/busybox sh
set -eu
export PATH=/bin
busybox --install -s /bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
modprobe virtio_pci
modprobe 9pnet_virtio
modprobe 9p
mount -t 9p -o trans=virtio,version=9p2000.L,msize=262144 arctic-root /newroot
mount -t 9p -o trans=virtio,version=9p2000.L,msize=262144 arctic-source /newroot/arctic
mount --move /dev /newroot/dev
mount --move /proc /newroot/proc
mount --move /sys /newroot/sys
exec switch_root /newroot /bin/bash /arctic/shell/dev/test-screen-frame-vm-guest.sh
INIT
chmod 755 "$WORK/initrd/init"
(cd "$WORK/initrd" && find . -print0 | cpio --null -o -H newc | gzip -1) > "$WORK/initrd.gz"
kvm=()
qemu=(qemu-system-x86_64)
if [[ -c /dev/kvm ]]; then
  # Keep QEMU's runner UID, with only the existing device's kvm group. Do not
  # change host device modes, install host modules, or run the emulator as root.
  [[ "$(stat -c %G /dev/kvm)" == kvm ]]
  qemu=(sudo -u "$(id -un)" -g kvm -- qemu-system-x86_64)
  kvm=(-enable-kvm -cpu host)
fi
timeout --signal=TERM --kill-after=15s 35m "${qemu[@]}" "${kvm[@]}" \
  -m 4096 -smp 2 -nodefaults -no-reboot -display none -serial stdio \
  -kernel "$WORK/vmlinuz" -initrd "$WORK/initrd.gz" \
  -append 'console=ttyS0 rdinit=/init panic=-1 selinux=0 arctic.frame-test=1' \
  -virtfs "local,path=$WORK/root,mount_tag=arctic-root,security_model=none" \
  -virtfs "local,path=$REPO,mount_tag=arctic-source,security_model=none" \
  2>&1 | tee "$WORK/serial.log"
test "$(grep -c '^ARCTIC-FRAME-VM-PASS' "$WORK/serial.log")" -eq 1
! grep -q '^ARCTIC-FRAME-VM-FAIL' "$WORK/serial.log"
