# Screens and the laptop lid

## Presenting and a second screen

Press `Super + P` with another screen or a projector plugged in and pick:

| Choice | What you get |
|---|---|
| **Laptop screen only** | The other screen is off |
| **Duplicate** | The same picture on every screen (for a projector) |
| **Extend** | One big desktop across the screens (the default) |
| **Other screen only** | The laptop screen is off |

The choice lasts until you log out or plug a screen in again; for a layout that stays, use
**Settings → Displays**. If a screen goes dark and you can't see the menu, press `Super + P`, then
`Enter` on the first line: that's **Laptop screen only**.

**Duplicate** shows the laptop screen on the other one with [wl-mirror](https://github.com/Ferdi265/wl-mirror)
(installed with Arctic Linux), scaled to fit. From a terminal: `arctic-display mode laptop|mirror|extend|external`,
and `arctic-display status` shows the screens.

## Closing the lid

With **another screen plugged in**, closing the lid turns the laptop screen off and your windows
move to the other screen; the computer keeps running (a "clamshell" setup with a keyboard and
mouse). Opening the lid turns the laptop screen back on.

With **no other screen**, **Settings → Power and lock → When you close the lid** decides:

- **Suspend** (the default): the screen locks and the computer sleeps.
- **Lock and turn the screen off**: it keeps running (downloads go on), locked, with the laptop
  screen off.
- **Keep running, screen off**: it keeps running and doesn't lock right away (it locks later
  when you're away, as always). Use this only somewhere safe.

For the last two, Arctic holds logind's lid switch while you're logged in (`systemd-inhibit
--what=handle-lid-switch`, in `systemd-inhibit --list` as "Arctic Linux"), so nothing needs root
and logind's own setting comes back when you log out. The lid is Mango's `switchbind=fold` /
`unfold` in `binds.conf`, which runs `arctic-display lid-closed` / `lid-opened`.

## Lighter effects and game mode

**Settings → Windows → Effects**:

- **Lighter effects** turn off animations, blur and shadows. **Automatic** (the default) does
  that in a virtual machine and when there's no graphics driver (software rendering), where
  those effects make everything slow.
- **Game mode** also removes the gaps between windows, until you turn it off or log out.

From a terminal: `arctic-effects lighter auto|on|off`, `arctic-effects game on|off|toggle`. They
write `~/.config/arctic/effects.conf`, which `~/.config/mango/config.conf` reads after
`settings.conf` (Arctic adds that line to older copies of `config.conf`, keeping a backup in
`~/.local/state/arctic/settings-backups`).
