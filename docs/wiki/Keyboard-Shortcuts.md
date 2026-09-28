# Keyboard shortcuts

Everything on the Arctic Linux desktop has a shortcut. Press `Super + /` to see the main ones on
screen at any time.

![The keyboard shortcut sheet (Super + /)](images/keys.png)

`Super` is the key with the Windows logo on most keyboards. `Super + Shift + T` means: hold
`Super` and `Shift`, then press `T`.

## Everyday

| Shortcut | Does |
|---|---|
| `Super + Space` | Open the launcher: apps, `=` calculator, `>` commands (press again to close) |
| `Super + Enter` | Open your terminal |
| `Super + W` | Open your browser |
| `Super + E` | Open your code editor |
| `Super + F` | Open your file manager |
| `Super + Shift + F` | Open the file manager in the terminal (yazi) |
| `Super + V` | Clipboard history |
| `Super + S` | [Settings](Settings) |
| `Super + Shift + A` | Get apps: install apps with dnf or Flatpak |
| `Super + Shift + W` | Wallpapers |
| `Super + /` | The shortcut sheet |

`Super + Enter`, `W`, `E` and `F` open the apps you picked in the installer. See
[Themes and customisation](Themes-and-Customisation#default-apps) to change them.

## Windows

| Shortcut | Does |
|---|---|
| `Super + Q` | Close the window |
| `Super + ←` `→` `↑` `↓` | Move focus to the window in that direction |
| `Super + Shift + ←` `→` `↑` `↓` | Swap the window with its neighbour |
| `Super + Ctrl + ←` / `→` | Make the main area narrower / wider |
| `Super + Ctrl + ↑` / `↓` | More / fewer windows in the main area |
| `Super + Z` | Swap the window with the main window |
| `Super + T` | Float or tile the window |
| `Super + M` | Maximise |
| `Super + Shift + M` | Full screen |
| `Super + Tab` | Next window |
| `Super + Shift + Tab` | Previous window |
| `Super + O` | Overview of all windows |
| `Super + N` | Next layout |
| `Super` + drag with the left button | Move a window |
| `Super` + drag with the right button | Resize a window |

## Workspaces and monitors

| Shortcut | Does |
|---|---|
| `Super + 1` … `5` | Go to workspace 1 to 5 |
| `Super + Shift + 1` … `5` | Move the window to workspace 1 to 5 |
| `Super + Page Up` / `Page Down` | Previous / next workspace |
| `Super + Shift + Page Up` / `Page Down` | Move the window to the previous / next workspace |
| `Super` + scroll up / down | Previous / next workspace that has windows |
| `Super + ,` / `.` | Focus the monitor on the left / right |
| `Super + Shift + ,` / `.` | Move the window to the monitor on the left / right |

## System

| Shortcut | Does |
|---|---|
| `Super + L` | Lock the screen (not in the live session) |
| `Super + Esc` | Power menu |
| `Super + I` | Install Arctic Linux (live USB only) |
| `Super + Delete` | Dismiss the newest notification |
| `Super + Shift + Delete` | Dismiss all notifications |
| `Super + Shift + N` | Do not disturb on / off |
| `Super + Shift + T` | Switch between light and dark (Winter and Polar night, or your wallpaper's colours) |
| `Super + Ctrl + N` | [Night light](Night-Light-and-Keep-Awake) on / off (until its schedule changes) |
| `Super + Ctrl + I` | [Keep awake](Night-Light-and-Keep-Awake#keep-awake) on / off: no lock or sleep while you're away |
| `Super + P` | [Screens](Screens-and-Laptop-Lid): laptop screen only, duplicate, extend, other screen only |
| `Super + Shift + R` | Reload the desktop configuration |
| `Print` | Screenshot of an area you select |
| `Shift + Print` | Screenshot of the whole screen |
| `Super + Print` | Screenshot of the current window |

## Hardware keys

These also work while the screen is locked.

| Key | Does |
|---|---|
| Volume up / down | Change the volume (shows the volume pop-up) |
| Mute | Mute or unmute |
| Microphone mute | Turn the microphone off or on |
| Brightness up / down | Change the screen brightness |
| Play/Pause, Next, Previous | Control the music or video that's playing |

## Touchpad

| Gesture | Does |
|---|---|
| Swipe with 3 fingers | Move focus to the window in that direction |
| Swipe left / right with 4 fingers | Next / previous workspace |
| Swipe up / down with 4 fingers | Open / close the overview |

Tap to click and natural scrolling are on for touchpads.

## In the launcher

| Key | Does |
|---|---|
| Type | Search apps |
| `=` then a sum | Calculator; `Enter` copies the answer |
| `>` then a command | Run a command; `Shift + Enter` runs it in the terminal |
| `↑` / `↓` | Move through the results |
| `Enter` | Open |
| `Esc` | Back, or close |

## In Get apps

| Key | Does |
|---|---|
| `Tab` | Complete a package name |
| `Enter` | Run what you typed |
| `Ctrl + C` | Stop the running command |

## In Settings

| Key | Does |
|---|---|
| `Ctrl + F` or `/` | Search every setting (or just type in the page list) |
| `↑` / `↓` in the page list | Switch pages |
| `Tab` | Go into the page |
| `Esc` | Back to the page list |
| `Ctrl + Page Up` / `Page Down` | Previous / next page |
| `Ctrl + Z` | Undo the last change |
| `Ctrl + Q` | Close Settings |

## In the installer

| Key | Does |
|---|---|
| `Enter` | Next, when the screen is filled in (not on Summary) |
| `Alt + ←` | Back to the previous step |
| `Tab` / `Shift + Tab` | Move between controls |
| `Space` | Tick or untick |
| `F1` | Help for this screen |
| `Esc` | Close the help, or quit the installer |
| `Alt + Shift` | Switch between English (US) and a Hebrew, Arabic, Greek, Russian or Ukrainian layout |

## On the login screen

| Key | Does |
|---|---|
| `Enter` | Log in |
| `Tab` | Move between the password, the user list, the log in button, the session menu and the power buttons |
| `←` / `→` | Switch user (when there are several) |
| `Esc` | Clear the password field, or close a menu |

## Changing a shortcut

The easiest way to add your own is the **Shortcuts** page of [Settings](Settings#shortcuts)
(`Super + S`): press the keys, then type a command or pick an app. It saves them in
`~/.config/mango/settings.conf` and refuses keys that are already taken.

The shortcuts live in `/usr/share/arctic/mango/binds.conf`, and your home folder links to it. To
add your own, put `bind=` lines in `~/.config/mango/user.conf`. To change one of Arctic's, see
[Themes and customisation](Themes-and-Customisation#changing-a-shortcut).
