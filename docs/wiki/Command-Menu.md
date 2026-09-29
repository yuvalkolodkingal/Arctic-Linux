# Command menu

The command menu puts every system action in one place you can reach from the keyboard:
screenshots, toggles, themes, Settings pages, installing and removing apps, updates and power.
Press `Super + Alt + Space` to open it. `Super + Ctrl + C` opens it at **Capture**, which is
handy on keyboards without a `Print` key.

It is the same idea as Omarchy's menu: a short tree you walk with the arrow keys, or search
by typing.

## Using it

| Key | Does |
|---|---|
| Type | Search everything under the branch you're in (a result shows where it lives, e.g. "Capture") |
| `↑` / `↓` or `Tab` | Move |
| `Enter` or `→` | Open a branch, or run a row |
| `←` or `Backspace` | Up one level |
| `Esc` | Clear the search, go up, or close |

Rows show their own shortcut when they have one, so the menu also teaches the keys. Toggles
show a switch with their current state.

## What's in it

| Branch | Rows |
|---|---|
| **Apps** | Every app, terminal, browser, files, code editor, emoji, clipboard history, calculator, system monitor |
| **Learn** | Keyboard shortcuts, this wiki, the welcome card again, Fedora’s documentation, About this computer |
| **Capture** | Screenshot of an area, a window or the screen; record the screen (and stop); copy text from the screen; read a QR code; pick a colour; open the Screenshots folder |
| **Toggle** | Dark style, night light, keep awake, do not disturb, reduce motion, high contrast |
| **Style** | Theme (every theme you can switch to, the current one ticked), wallpaper, Appearance settings, hide the top bar (and show it again) |
| **Setup** | Every page of [Settings](Settings), and the folder for your [hooks](Themes-and-Customisation#hooks-for-other-events) |
| **Install** | Get apps, and straight to Flathub, Fedora packages, web apps or the package console |
| **Remove** | Remove apps |
| **Update** | Check for updates now, update settings, update firmware, restart sound, restart Wi-Fi, restart the desktop shell |
| **Open windows** | Every window on every workspace; `Enter` brings one forward |
| **System** | Lock screen, log out, suspend, restart, shut down (the live USB has only restart and shut down) |

A row whose app or helper isn't installed is hidden, and so is a branch with nothing in it.

## Adding your own rows

The menu is data: the files in `/usr/share/arctic/shell/menu/`, read in name order. Put your own
rows in `~/.config/arctic/menu.json`, in the same format (the rows can also sit inside
`{"entries": {…}}`, as in Arctic's files). The menu reads it every time it changes; a file with a
mistake in it is left out until it's fixed.

```json
{
  "mine": {"label": "Mine", "icon": "user"},
  "mine.notes": {"label": "Notes", "icon": "document", "run": ["gnome-text-editor", "/home/me/notes.txt"]},
  "mine.backup": {"label": "Back up now", "icon": "disk", "sh": "rsync -a ~/Documents /run/media/me/usb/"},
  "capture.area": {"label": "Snip"},
  "update.firmware": {"hidden": true}
}
```

- **Ids make the tree.** `mine.notes` is a row of the branch `mine`. New branches come after
  Arctic's own.
- **Using an id Arctic already has** changes only the fields you give (`capture.area` above
  gets a new label and keeps its command). `"hidden": true` removes a row or a whole branch.
- **`run`** is the command, a list of words run as it is. **`sh`** is a line for `sh -c`, so pipes
  and `~` work there (only in your own file).

| Field | Means |
|---|---|
| `label` | The row's text |
| `icon` | One of Arctic's line icons (`camera`, `folder`, `globe`, `terminal`, …) |
| `desc` | A second, quieter line of text |
| `keys` | A shortcut to show next to it |
| `run` / `sh` | The command (see above) |
| `order` | Where it goes among its neighbours (smaller first; 1000 when not given) |
| `target` | The id of another branch to open instead |
| `shell` and `args` | An Arctic action by name: `settings` (page, setting), `url` (an `https://` address), `openView` (`apps`), `openGetApps`, `openPanel`, `toggleWallpapers`, `toggleKeys`, `toggleBar`, `lock`, `openWelcome` |
| `needs` | Commands that must be installed for the row to show (default: the one it runs) |
| `when` | `"live"` or `"installed"`: show it only on the live USB, or only on an installed system; or `{"live": false, "command": "swappy", "file": "/path", "outputs": 2}`, all of which must hold |
| `test` | A shell condition; the row shows only when it succeeds |
| `state` | A command whose output (JSON with `"on": true`, or just `on` / `off`) gives the row a switch |
| `labelOn` | The label while the state is on |

## From a script or a keybinding

```sh
arctic-menu                          # open or close the menu (Super + Alt + Space)
arctic-menu capture                  # open or close it at a branch (Super + Ctrl + C)
arctic-menu --list toggle            # print the rows that can run here
arctic-shell-ipc menu open style.theme
arctic-shell-ipc menu search night
```

Without the Arctic shell (the waybar fallback session), `arctic-menu` shows the same rows in
fuzzel, minus those that need the shell.
