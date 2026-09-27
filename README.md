# Wallpaper picker

Open with `quickshell-wallpapers` or Super+W in Hyprland (Super+Space in Mango). Run the command again or press Escape to close.

Choose a folder, search the thumbnail grid, click an image to apply it immediately. Images are applied on all outputs with a short fade. Pywal16 extracts the palette; the picker watches its generated theme and updates automatically. Selection and folder persist in `wallpapers.json`. Login restoration uses `~/.local/bin/restore-wallpaper`.

The picker uses awww directly. Waypaper is no longer part of the launcher or restoration flow; its installation remains available for rollback. The migration backup is under `~/.local/state/quickshell/backups/`.

Supported images: JPEG, PNG, WebP, BMP and GIF. GIF thumbnails and palettes use a static frame. Wallpaper Engine scenes and video wallpapers are not supported by this first version.

Implementation: `shell.qml` contains the picker; `Theme.qml` provides shared colors; `scripts/wallpapers.py` handles thumbnails, application, persistence and Pywal16. Dependencies are isolated in `~/.local/opt/quickshell-wallpaper-venv`. Cached thumbnails and the live theme are in `~/.cache/quickshell-wallpapers`; Pywal also writes its standard `~/.cache/wal` palette.

## App bar

Apps or Super+D opens a centered, Rofi-style application list. Type to search, use Up/Down or Tab/Shift+Tab to select, and Enter to launch. Clicking an application launches it immediately. Escape or clicking outside dismisses the launcher. It uses the wallpaper's Pywal palette. Terminal applications open in Kitty.

The Wallpapers button opens the wallpaper picker. The bar starts on Hyprland login. `quickshell-apps` starts the shell if needed and opens the launcher.

Drag the small handle at the top of either widget to move it. Positions are retained while the shell is running and kept within the screen.

## Install console

Install opens a terminal-style emerge console inside the launcher. Enter a package atom or an emerge command. Commands run through doas in a PTY, with --ask enabled by default. Authentication and confirmation responses are entered in the console; password input is masked and is not logged or written to files. Ctrl+C interrupts the foreground job. Back or hiding the popup leaves the job running; restarting or reloading Quickshell closes its terminal session.

Widgets unfold from the bar with matching surfaces and no outer outline. Their drag handles remain available.
