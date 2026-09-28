# Contributing

Thanks for helping with Arctic Linux. Reports from people trying it on real computers are as
valuable as code.

## Reporting a problem

Open an [issue](https://github.com/yuvalkolodkingal/Arctic-Linux/issues) and include:

- what you did, what you expected and what happened instead;
- your computer's model, and whether it starts in UEFI or BIOS mode;
- for installer problems, the log from **Save log to USB** (see
  [Troubleshooting](Troubleshooting#saving-the-installer-log));
- for desktop problems, the output of `journalctl --user -b` or `arctic-shell --foreground`;
- a screenshot (`Print` saves one to `~/Pictures/Screenshots`).

## Before you change something

- **Read the contracts.** [`docs/BUILD-SPEC.md`](https://github.com/yuvalkolodkingal/Arctic-Linux/blob/main/docs/BUILD-SPEC.md)
  fixes the paths, package names, the engine ↔ UI protocol and the wizard steps that every
  component is built against. When a detail there turns out to be wrong on a real system, fix it
  there first, then in the code. [`docs/PLAN.md`](https://github.com/yuvalkolodkingal/Arctic-Linux/blob/main/docs/PLAN.md)
  explains why things are the way they are.
- **Follow the design system.** Colours, sizes, radii and durations come from the tokens, never
  hard-coded values. See [Design system](Design-System) and `design/brand-book.md`.
- **Write copy the Arctic way:** sentence case, "you", plain words, buttons that say what happens,
  no exclamation marks. Installer text follows `design/guidelines/20-installer-copy.md`.
- **Keep the engine in charge.** The installer UI only draws what `arcticd` sends; steps,
  defaults and validation live in Go (`internal/wizard`).
- **Catalog entries are data.** Adding an app means a new `modules/<category>/<id>/module.toml`
  and a line in `modules/catalog.toml`. Profiles and the UI reference module ids only, never
  commands. Name Flatpak remotes explicitly, and use Nix only for command-line apps.
- **Go uses the standard library only**, so the RPM builds offline.

## Where things live

| You want to change | Look in |
|---|---|
| The installer's steps, copy, defaults or validation | `internal/wizard/` |
| What the installer does to the disk and system | `internal/installer/` |
| The installer screens | `installer-ui/steps/`, `installer-ui/components/` |
| The apps on offer | `modules/` |
| The bar, launcher, lock screen, OSD, Get apps | `shell/` |
| Arctic Settings | `settings/` (pages in `settings/pages/`, reads and writes in `settings/scripts/arctic_settings.py`) |
| Drivers and their detection | `modules/drivers/`, `internal/hw/`, `internal/installer/drivers.go` |
| Keyboard shortcuts | `dotfiles/.config/mango/arctic/binds.conf` and `dotfiles/.local/share/arctic/keys.txt` (keep both in step) |
| Window manager look and behaviour | `dotfiles/.config/mango/arctic/` |
| The `arctic-*` commands | `dotfiles/.local/bin/` |
| Colours | `design/tokens.json`, then `design/tools/gen-desktop-themes.py` |
| The theme engine and which apps it themes | `design/themegen/` (templates in `design/themegen/templates/`), `packaging/theme-hooks.d/` |
| Login screen, boot menu, splash, logos | `branding/` |
| Packages | `packaging/arctic-linux.spec` |
| The live session | `live/`, `iso/kiwi/` |
| These wiki pages | `docs/wiki/` |

## Checking your change

Run the same checks CI runs (see [Building from source](Building-from-Source#continuous-integration)):

```sh
go vet ./... && go test ./...                                   # engine
python3 -m unittest discover -s shell/tests                      # shell helpers
node shell/tests/test-launcher.cjs                               # launcher ranking, calculator
node shell/tests/test-package-search.cjs                         # Get apps completion
python3 -m unittest discover -s packaging/firstboot              # arctic-firstboot
python3 -m unittest discover -s packaging/updates -p 'test_*.py' # arctic-update
python3 -m unittest discover -s design/themegen/tests            # theme engine, wallpaper colours, arctic-theme
python3 -m unittest discover -s settings/tests -p 'test_*.py'    # Arctic Settings' helper
python3 -m unittest discover -s tools/tests -p 'test_*.py'       # repository publishing
python3 -m unittest installer-ui/dev/test_mock_bridge.py         # installer protocol
shellcheck -x dotfiles/.local/bin/* tools/*.sh live/live-* live/livesys-arctic   # scripts
```

Then look at it running:

- **Installer UI:** `installer-ui/dev/run.sh` runs it against a mock engine, no root needed.
  `installer-ui/dev/test-headless.sh` walks every step in a headless sway and saves screenshots.
- **Shell:** `shell/dev/headless.sh --fixtures demo ipc launcher search ze sleep 1 shot launcher`
  runs it headless and takes a screenshot.
- **Settings:** `settings/dev/headless.sh --smoke --fixtures` opens every page in a headless sway
  and saves screenshots.
- **Whole system:** build the RPMs and ISO and boot it with `tools/test-iso.sh`; for installer
  engine changes, `tools/test-install.sh --installer <your arctic-install build>` tests them
  without rebuilding the ISO.

Update the screenshots in `installer-ui/dev/screenshots/` or `shell/dev/screenshots/` when your
change alters a screen.

## Pull requests

- Keep each pull request to one change, and describe what it changes for the person using Arctic
  Linux.
- Update the docs when behaviour changes: the component's `README.md`, `docs/BUILD-SPEC.md` for
  contracts, and the wiki pages in `docs/wiki/`.
- CI must pass.

## Editing this wiki

The wiki is written in [`docs/wiki/`](https://github.com/yuvalkolodkingal/Arctic-Linux/tree/main/docs/wiki)
and published by the `wiki.yml` workflow when changes reach `main`. Edits made in GitHub's wiki
editor are overwritten, so change the files in the repository instead:

- one Markdown file per page, named after the page with dashes (`Install-Arctic-Linux.md`);
- links as `[text](Page-Name)` or `[text](Page-Name#heading)`;
- images in `docs/wiki/images/`, referenced as `images/<file>.png`;
- `_Sidebar.md` and `_Footer.md` appear on every page.

Write for someone who has never used Linux: plain words, "you", sentence case, and the exact
labels shown on screen.

## Licence

Arctic Linux is under the MIT licence (see `LICENSE`). By contributing you agree your contribution
is released under it. The fonts are under the SIL Open Font Licence and the Nix SELinux policy under
the LGPL 2.1 or later.
