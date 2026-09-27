# Terminal and shell

`Super + Enter` opens a terminal. Out of the box that's **kitty** running **zsh**, and a small
block-drawn fox says hello.

![kitty with the arctic-fetch fox greeting and the prompt](images/terminal-fetch.png)

## The fox greeting: `arctic-fetch`

Each new terminal starts with `arctic-fetch`: the Arctic fox beside a short summary of your
system.

- **The fox** blinks, twitches an ear and flicks its tail, plays that twice, then rests. Its eyes
  are amber. Press any key to skip straight to the resting fox.
- **Next to it:** `you@your-computer`, then `os`, `base` (the Fedora release underneath),
  `kernel`, `wm` (Mango on Wayland), `shell`, `term`, `theme` and `uptime`, and two rows of colour
  swatches showing the terminal's palette.
- Colours come from the terminal's palette, so the greeting follows the Winter and Polar night
  themes.

Some ways to change it:

```sh
arctic-fetch            # show it again
arctic-fetch --static   # the resting fox, no animation
```

- It's drawn still (no animation) when reduced motion is on (`arctic-motion off`), when
  `ARCTIC_REDUCE_MOTION=1` is set, or when the window is narrower than 60 columns.
- To turn the greeting off, see [Turning the greeting off](#turning-the-greeting-off) below.
- **Fetch** in the launcher (`Super + Space`) opens a terminal with the greeting.

### Turning the greeting off

`~/.zshrc` runs the greeting before it reads `~/.zshrc.local`, so the setting has to come earlier.
Add this line to `~/.zprofile` (read once when you log in, and passed on to every terminal), then
log out and back in:

```sh
export ARCTIC_FETCH=0
```

## kitty

Arctic's kitty is set up to match the desktop:

- **JetBrains Mono** at 10.5 pt, with ligatures off under the cursor.
- An **amber block cursor** that doesn't blink.
- Comfortable padding and no title bar; Mango draws the rounded border.
- Rounded tabs at the bottom, with the active tab in bold.
- **Copy on select**: selecting text copies it to the clipboard.
- No bell sound.

The colours come from the active theme (`~/.config/arctic/current/kitty.conf`) and change when you
press `Super + Shift + T`, even in terminals that are already open.

Your own kitty settings go in `~/.config/kitty/user.conf`. It's read last, so anything there wins,
and Arctic never overwrites it:

```ini
font_size 12
background_opacity 0.95
```

kitty's own shortcuts work as usual; for example `Ctrl + Shift + T` opens a new tab and
`Ctrl + Shift + Enter` a new window inside kitty. See kitty's documentation for the full list.

## zsh

zsh is the default shell. Arctic's `~/.zshrc` gives you:

- **The prompt**: `~/projects ❯`. The folder is green, the Git branch (inside a Git repository)
  is shown dimmed after it, and the arrow is amber, turning red after a command fails.
- **History**: 50,000 lines, shared between open terminals, without the same command twice in a
  row. Commands that start with a space aren't saved. It's kept in `~/.local/state/zsh/history`.
- **Search history with the arrows**: type the start of a command, then `↑` / `↓` to go through
  earlier commands that start the same way.
- **Completion** with a menu you can move through, ignoring upper and lower case.
- **Moving around**: type a folder's name to go into it; `Ctrl + ←` / `→` jumps a word;
  `Home` / `End` go to the start and end of the line.
- **Aliases**: `ll` (long list), `la` (long list with hidden files), `y` (yazi), and coloured `ls`
  and `grep`.
- `~/.local/bin` is on your `PATH`, for your own scripts.
- `EDITOR` is `nano` unless you set it.

Add your own settings to `~/.zshrc.local`; Arctic never touches it:

```sh
export EDITOR=nvim
alias gs='git status'
```

## bash and fish

**bash** is always installed. If you picked it as your shell, you get the same `~/projects ❯`
prompt and the same `ls` aliases (from `~/.bashrc.d/arctic.sh`). The fox greeting is zsh only;
run `arctic-fetch` whenever you like.

**fish** uses its own prompt and settings.

To change your login shell later (log out and back in afterwards):

```sh
sudo usermod --shell /usr/bin/fish "$USER"     # fish
sudo usermod --shell /bin/zsh "$USER"          # zsh
sudo usermod --shell /bin/bash "$USER"         # bash
```

Install fish first with `sudo dnf install fish` if you didn't pick it in the installer.

## Other terminals

If you picked **foot** or **Alacritty** in the installer, `Super + Enter` opens that instead.
Arctic's colours are set up for kitty only, so the others start with their own look. To switch
which terminal `Super + Enter` opens, see
[Themes and customisation](Themes-and-Customisation#default-apps).

## yazi

`Super + Shift + F` (or `y` in the terminal) opens **yazi**, a quick file manager inside the
terminal. Arrow keys move around, `Enter` opens, and `q` quits.
