#!/bin/bash
# Arctic Linux live ISO: runs inside the image root after the packages are installed
# (kiwi "config.sh"). Derived from fedora-kiwi-descriptions config.sh (f44), live parts only.
set -euxo pipefail

# shellcheck source=/dev/null
test -f /.kconfig && . /.kconfig
# shellcheck source=/dev/null
test -f /.profile && . /.profile

echo "Configure image: [${kiwi_iname:-Arctic-Linux}]"

#======================================
# SELinux booleans (as Fedora)
#--------------------------------------
setsebool -P selinuxuser_execmod 1 || :

#======================================
# Clear machine specific configuration
#--------------------------------------
rm -f /etc/machine-id
echo 'uninitialized' > /etc/machine-id
rm -f /var/lib/systemd/random-seed

#======================================
# Remove the rescue kernel and images to save space (as Fedora's live kickstarts did)
#--------------------------------------
# kernel-install made them for the image build's machine id: the rescue initramfs (non-host-
# only, ~210 MB, already compressed) and kernel, and a generic initramfs. The live USB boots
# kiwi's own initrd (made after this script), and the installer runs kernel-install on the
# new system, which makes that system's initramfs and rescue image. Left here, they would go
# into the root image and push the ISO over its 2 GiB budget.
rm -f /boot/*-rescue* /boot/loader/entries/*-0-rescue.conf /boot/initramfs-*.img

#======================================
# GRUB defaults for the installed system (the live root is copied to the target)
#--------------------------------------
{
	echo "GRUB_DEFAULT=saved"
	echo "GRUB_DISABLE_SUBMENU=true"
	echo "GRUB_DISABLE_RECOVERY=true"
} >> /etc/default/grub

#======================================
# Delete & lock the root password (livesys unlocks it for the live session)
#--------------------------------------
passwd -d root
passwd -l root

#======================================
# Live session: livesys-scripts runs /usr/libexec/livesys/sessions.d/livesys-arctic
#--------------------------------------
echo 'livesys_session="arctic"' > /etc/sysconfig/livesys

#======================================
# Services and default target
#--------------------------------------
# Presets (arctic-release) already enable these; be explicit for the live image.
systemctl enable sddm.service
systemctl enable livesys.service livesys-late.service
systemctl enable arcticd.socket
systemctl enable nix-daemon.service || :
# Updates and snapshot cleanup for the installed system (both skip the live session: the timer
# checks the kernel command line, and snapper has no configuration until the installer's).
systemctl enable arctic-update-stage.timer || :
systemctl enable snapper-cleanup.timer || :
# Stream 5: Flatpak apps updated daily (the system's, and each user's own), SSH keys once per
# session (gcr-ssh-agent). The presets say so too.
systemctl enable arctic-flatpak-update.timer || :
systemctl --global enable arctic-flatpak-update.timer gcr-ssh-agent.socket || :
systemctl disable dnf5-automatic.timer 2>/dev/null || :
# No SSH server on the live USB or (since the installer copies this root) installed systems;
# 80-arctic.preset already says so, this makes sure whatever the install order was.
systemctl disable sshd.service || :
systemctl disable sshd.socket || :
systemctl set-default graphical.target

#======================================
# Boot splash: the arctic Plymouth theme goes into the live initrd kiwi builds next
#--------------------------------------
if [ -f /usr/share/plymouth/themes/arctic/arctic.plymouth ]; then
	plymouth-set-default-theme arctic
fi

#======================================
# Nix: store optimisation corrupts hard links on Fedora (bug 2416675)
#--------------------------------------
if [ -f /etc/nix/nix.conf ] && ! grep -q '^auto-optimise-store' /etc/nix/nix.conf; then
	echo 'auto-optimise-store = false' >> /etc/nix/nix.conf
fi

#======================================
# Flatpak: the installer adds Flathub itself; do not add Fedora's OCI remote on first boot
#--------------------------------------
mkdir -p /var/lib/flatpak
touch /var/lib/flatpak/.fedora-initialized

#======================================
# Finalization (as Fedora): inhibit the ldconfig cache generation unit (rhbz#2348669)
#--------------------------------------
touch -r "/usr" "/etc/.updated" "/var/.updated"

exit 0
