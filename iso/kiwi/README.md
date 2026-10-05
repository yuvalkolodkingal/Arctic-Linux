# Arctic Linux live ISO (kiwi-ng)

`tools/build-iso.sh` builds this description with kiwi-ng 11 in a privileged Fedora 44
container, adding the local RPM repository from `tools/build-rpms.sh` (`out/repo`) with
`--add-repo`. It runs `kiwi-ng system prepare` (packages + `config.sh`), installs Zen Browser
from Flathub into the image root from outside the chroot (`--zen yes` by default: absence fails
the build; `--zen auto/no` are explicit development choices), then `kiwi-ng system create` (SELinux labels, live initrd,
erofs, ISO). The workflow explicitly uses `--zen yes`, requiring the non-Chromium browser
even above 2 GiB; its release path already supports split downloads.
Output: `out/iso/Arctic-Linux-1.2-x86_64.iso`, its `.sha256`, the package list and
`.build-info` (whether Zen is in it).

Candidates can use `--name Arctic-Linux-1.2-optimized-candidate-x86_64.iso` and
`--max-bytes 1500000000` (decimal 1.5 GB, about 1.397 GiB). A missed size gate retains
the image/checksum and exits with a clear failure; it never removes features to meet
the budget. Explicit `--erofs-compression`, `--erofs-cluster` and `--dedupe` experiments
must pass the functional/performance gates in `docs/OPTIMIZATION.md` before adoption.

| File | What it is |
|---|---|
| `config.kiwi` | The image: type `iso` (hybrid, UEFI with Fedora's signed shim + BIOS, erofs root, volume id `Arctic-Linux-1.2`), Fedora 44 + updates, packages. Derived from fedora-kiwi-descriptions (f44) `LiveInstall` + `BootCoreLive` + `BaseCommon`. |
| `config.sh` | Runs in the image root after package installation: `livesys_session="arctic"`, SDDM / livesys / arcticd.socket / nix-daemon enabled, `graphical.target`, Plymouth theme `arctic`, root locked, machine-id cleared. SELinux labels are applied by kiwi afterwards (as for Fedora's images). |
| `grub-arctic.cfg.iso-template` | The boot menu for both firmwares (kiwi `grub_template`): Try, Install, Safe graphics mode, Check USB for errors, Boot from first disk. Uses the `arctic` GRUB theme that kiwi copies from the image (`<bootloader-theme>arctic</bootloader-theme>`, package `arctic-grub-theme`), else a text menu. |
| `iso-esp-excludes.yaml` | Files kept out of the ISO's EFI image (from Fedora, rhbz#2358785). |

Kernel arguments per entry: every entry has `quiet rhgb root=live:CDLABEL=Arctic-Linux-1.2
rd.live.image` and `arctic.mode=try` (Install: `arctic.mode=install`; Safe graphics adds
`nomodeset`; Check USB adds `rd.live.check`). `arctic.greeter=1` (typed with `e`) skips the
live autologin to show the SDDM login screen.

Test it with `tools/test-iso.sh` (QEMU, OVMF or SeaBIOS, screenshots in `out/test/`).

On a constrained builder, `--scratch /path/to/dedicated/scratch` puts create-stage
intermediates and temporary files on that storage; the prepared root stays in
`--work`. Keep enough scratch capacity for both the root payload and ISO.
