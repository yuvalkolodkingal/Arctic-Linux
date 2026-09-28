# Settings

**Arctic Settings** is the settings app of Arctic Linux, new in version 0.2. It changes the
window manager, the look, your displays, keyboard and mouse, shortcuts, default apps, updates and
more, and most changes show at once. Open it with `Super + S`, by typing **Settings** in the
launcher (`Super + Space`), or with **Settings**, the first item of the power menu (`Super + Esc`).

![Arctic Settings on the Appearance page](images/settings-appearance.png)

From a terminal:

```sh
arctic-settings              # open it (a second call brings the window forward)
arctic-settings displays     # open it on a page
```

The page names for `arctic-settings <page>` are `appearance`, `windows`, `displays`, `input`,
`shortcuts`, `apps`, `network`, `bluetooth`, `sound`, `notifications`, `updates`, `power`, `startup`
and `about`.

## Finding a setting

Type in the search box at the top of the page list (or press `Ctrl + F` or `/`, or just start
typing in the list). The search covers every setting on every page; pick a result and Settings
opens its page and highlights the row.

![Searching Settings](images/settings-search.png)

| Key | Does |
|---|---|
| `Ctrl + F` or `/` | Search every setting |
| `↑` / `↓` in the page list | Switch pages |
| `Tab` | Go into the page |
| `Esc` | Back to the page list |
| `Ctrl + Page Up` / `Page Down` | Previous / next page, from anywhere |
| `Ctrl + Z` | Undo the last change |
| `Ctrl + Q` | Close Settings |

A setting you've changed shows a **Changed** mark and a **Reset** button that puts back Arctic's
value.

![A search result highlighted on its page](images/settings-reveal.png)

## Where your changes go

Almost nothing in Settings needs your password: it writes files in your home folder, through
programs that already work without root. The exceptions change the whole computer and ask for
the password through the usual dialog: the time zone, the clock and the language (**Date and
time**), and setting up printers (*Print Settings*). Every file is checked before it's saved (window
manager settings with Mango itself), written in one go so it's never half-written, and the
previous version is kept in `~/.local/state/arctic/settings-backups/` (the newest 20 of each
file). That's what `Ctrl + Z` uses.

| Setting | Written to | Applied |
|---|---|---|
| Windows, keyboard, touchpad, mouse, pointer, default layout, your shortcuts, startup apps, kept display layouts | `~/.config/mango/settings.conf` | At once (Mango reloads its configuration); startup apps at the next login |
| Theme, colours from the wallpaper, light or dark | through `arctic-theme set`, `auto`, `mode` | At once |
| Wallpaper | through `arctic-wallpaper` | At once |
| Reduce motion | through `arctic-motion on\|off` | At once |
| Text size in apps, pointer for GTK apps | GNOME's settings (`gsettings`, `org.gnome.desktop.interface`) | New windows |
| Displays | `wlr-randr`; kept layouts as `monitorrule=` lines in `settings.conf` | At once, reverted after 15 seconds unless you keep it |
| Default apps | `~/.config/arctic/default-apps` and `~/.config/mimeapps.list` | At once |
| Lock and suspend times | `~/.config/arctic/idle.conf` | At once |
| Power mode | the power profiles service (tuned-ppd) | At once |
| Wi-Fi on or off | NetworkManager (`nmcli`) | At once |
| Bluetooth, sound | BlueZ and PipeWire directly | At once |
| Updates | through `arctic-update` | At once |
| Notifications: schedule, history, per-app choices | `~/.config/arctic/notifications.json`; do not disturb through `arctic-dnd` | At once |

`settings.conf` is read after Arctic's own Mango files and **before** your
`~/.config/mango/user.conf`, so anything you set by hand in `user.conf` still wins. When it does,
Settings says so on the row. If your `~/.config/mango/config.conf` doesn't include
`settings.conf` yet (it was copied before 0.2), Settings adds the line
`source-optional=~/.config/mango/settings.conf` just before the `user.conf` line.

When a program Settings needs is missing, the page says so instead of failing. For example,
without `wlr-randr` the Displays page can change scale, rotation and position but not the
resolution.

## Appearance

Colours, wallpaper and motion for the whole desktop: the bar, windows, the terminal and apps.

- **Theme:** Winter (light), Polar night (dark) or **From wallpaper**, which makes a theme from
  the colours of your picture.
- **Match colours to the wallpaper:** each new wallpaper makes the theme again, so the accent
  always suits the picture. This is the same switch as **Match colours to wallpaper** in the
  wallpaper picker (`Super + Shift + W`).
- **Light or dark:** for the theme made from your wallpaper: Automatic (whatever suits the
  picture), Dark or Light.
- **Wallpaper:** Arctic's wallpapers and your own pictures from `~/Pictures/Wallpapers` (the same
  list as the wallpaper picker). **Add pictures…** opens the file chooser; you can also drag
  pictures here from Files. Added pictures are copied into `~/Pictures/Wallpapers` (only real
  pictures: JPEG, PNG, WebP, BMP or GIF). Point at one of your own pictures to **rename** or
  **delete** it (or select it and press `F2` or `Delete`). The picture in use can't be deleted.
- **Wallhaven:** search [wallhaven.cc](https://wallhaven.cc) from Settings. Type some words (or
  press **Browse**), choose **Top**, **Latest** or **Random**, the categories and how safe the
  pictures must be (only **Safe** is ticked at first). **Fit my screens** shows only pictures at
  least as large as your largest screen, in your screens' shapes. Click a picture for a larger
  look, then **Download and set**: it's saved in `~/Pictures/Wallpapers/wallhaven` and becomes
  your wallpaper, and with **Match colours to the wallpaper** on, the colours follow it. Nothing
  is downloaded until you search. Without internet the section says so; the rest of Settings
  works as usual. Wallhaven allows 45 searches a minute; Settings waits or tells you when to try
  again.
- **Wallhaven API key** (optional): with the key from your Wallhaven account (Settings → Account),
  searches use your account's filters, and **NSFW** can be ticked. It's kept in
  `~/.config/arctic/wallhaven.json`, which only you can read; **Remove** deletes it.
- **Reduce motion:** windows and menus fade instead of moving, and the fox in the terminal stays
  still.
- **Text size in apps:** 100% to 175% for GTK apps such as Files and most dialogs. The bar and
  menus keep their size.
- **Pointer size** (Normal, Large, Larger) and **Pointer style** (the cursor themes installed).

See [Themes and customisation](Themes-and-Customisation) for how themes work and `arctic-theme`.

## Windows

![The Windows page](images/settings-windows.png)

How windows sit on the screen, move and take focus. Changes show at once.

- **Spacing and shape:** the gap between windows and at the screen edge, border width, rounded
  corners, and whether a window on its own gets gaps and a border.
- **Motion and effects:** window animations and their speed, the frosted bar, shadows, and
  dimming the windows you aren't using.
- **Focus:** focus follows the mouse, the pointer follows the focus, whether apps can bring
  themselves forward (for example a browser when you click a link in another app), and a **hot
  corner** that opens the overview when you push the pointer into it (off at first).
- **Layout:** the layout every workspace starts in (`Super + N` still switches the one you're on),
  whether new windows open as the main window, and the width of the main area.

**Reset all window settings** puts back Arctic's values; **Open settings.conf** shows the file.

**Effects** has **Lighter effects** (Automatic, On, Off: no animations, blur or shadows;
Automatic turns them off in a virtual machine or without a graphics driver) and **Game mode**
(lighter effects and no gaps until you turn it off or log out). They're written to
`~/.config/arctic/effects.conf`, which Mango reads after `settings.conf`, so while they're on they
win over the rows above. See [Screens and the laptop lid](Screens-and-Laptop-Lid#lighter-effects-and-game-mode).

## Displays

![The Displays page](images/settings-displays.png)

**Arrangement** shows your screens as they sit next to each other, each drawn to scale. Drag one
to where it is on your desk and let go: it snaps against the edge of another screen, and lines up
with its top, bottom or middle when you drop it close to that. Screens always touch along an edge,
because that's where the pointer crosses from one to the next, and they never overlap; a screen
that was only touching the one you moved moves along with it. With the keyboard, press `Tab` until
a screen is highlighted, then use the arrow keys.

Click a screen to change it:

- **Use this display:** switch it off or on. The last screen that's on can't be switched off.
  A screen that's off is listed under the arrangement, so you can pick it and switch it back on.
- **Main display:** the screen you start on when you log in. The pointer, your first windows,
  the launcher and notifications appear there; the bar is on every screen. Arctic's window
  manager starts at the top-left corner of the arrangement, so **Make main** moves the screen
  there: it swaps places with the screen that was there. Dragging another screen to the far left
  or top makes that one the main display instead, and the **Main** label moves with it.
- **Resolution** and **Refresh rate.**
- **Scale:** how big everything is drawn. The row says how large the desktop is at that scale,
  for example a 2560 × 1600 screen at 150% gives a 1706 × 1066 desktop.
- **Rotation:** portrait (90° or 270°), upside down, or mirrored.
- **Variable refresh rate** for screens with FreeSync or G-Sync.

If your screens overlap or have a gap between them when you open the page, Settings shows them
lined up and says so; press **Apply** to use that.

Press **Apply** and the change happens at once, with a question: **Keep these display
settings?** If you don't press **Keep changes** within 15 seconds (for example because the screen
went black), the old layout comes back by itself. If Settings has closed in the meantime, a
watchdog puts it back after 20 seconds. A kept layout is
saved as `monitorrule` lines in `settings.conf`, listed under **Saved layout**; **Forget** removes
it.

Settings remembers one place per screen. If you use a laptop with different monitors, say at home
and at work, each monitor keeps the place you last kept for it, unless that would put it on top of
the layout you kept since; then it comes back to the right of your other screens, and you can
drag it where you want once more.

A display you switch off stays off only until you log out. That's on purpose: a saved "off" could
leave a laptop's only screen dark the next time it starts without its dock.

**Night light** makes the screen warmer in the evening: **Off**, **Sunset to sunrise** (worked out
from your time zone's location, nothing is looked up online), **Custom hours** or **Always on**, and
how warm with **Warmth**. **Turn on** / **Turn off** changes it right away until the schedule
changes anyway; `Super + Ctrl + N` does the same. See [Night light and keep awake](Night-Light-and-Keep-Awake).

## Keyboard and mouse

![The Keyboard and mouse page](images/settings-input.png)

- **Keyboard:** your layouts (**Add a layout**), the keys that switch between them (with the
  shortcuts those keys would also fire, if any), what the Caps Lock key does (many people make it
  a second Esc or Ctrl), the **Compose key** (press it, then two keys: `'` then `e` types é), and a
  box to try your keyboard.
- **Typing:** repeat delay and rate, and Num Lock on when you log in.
- **Touchpad:** tap to click, tap and drag, natural scrolling, turning the touchpad off while
  typing, pointer speed and acceleration, scrolling speed, right click, middle click with both
  buttons, and turning the touchpad off altogether.
- **Mouse:** pointer speed and acceleration, natural scrolling, scrolling speed and left-handed.
- **Clipboard:** **Keep clipboard history** (what `Super + V` shows; off keeps only what you
  copied last) and **Clear history**. Saved in `~/.config/arctic/clipboard.conf`.

## Shortcuts

![The Shortcuts page](images/settings-shortcuts.png)

Every shortcut of the desktop, searchable, and **Your shortcuts**. **Add a shortcut**: click the
key box and press the keys, then type a command or pick an app to open (with **If it's open,
bring its window back**, on at first, the key shows the app's window instead of opening another). Mango uses the first
shortcut it finds for a key, so Settings refuses a key that's already taken, and one that holds
the keys that switch your keyboard layout. Your shortcuts are saved as `bind=` lines in
`settings.conf`.

Arctic's own shortcuts come first. When an update gives Arctic a key you had bound (0.3 moved the
browser to `Super + B` and added `Super + Shift + S`), a banner at the top says which of your
shortcuts no longer run, and the row is marked **Doesn't run**: remove it and add it again on
another key.

**Every shortcut in your Mango config** lists everything Mango has, including the ones in your
`user.conf`. The main ones are also on [Keyboard shortcuts](Keyboard-Shortcuts).

## Default apps

![The Default apps page](images/settings-apps.png)

The apps your keyboard shortcuts open, and the ones links and files open in: Web browser
(`Super + B`), Terminal (`Super + Enter`), Files (`Super + F`), Text editor (`Super + E`), Videos,
Music, Pictures and PDF documents. The first four are saved in `~/.config/arctic/default-apps`
(read by `arctic-open`), and every one also in `~/.config/mimeapps.list`, as `xdg-mime default`
would. **Get apps** installs more; they show up here. **Install and remove apps** opens Get apps
or Remove apps (`arctic-shell-ipc apps install|remove`).

## Network

![The Network page](images/settings-network.png)

Your connections and a Wi-Fi switch. Join a Wi-Fi network from the network icon on the bar.
**Open the editor** starts the connection editor (`nm-connection-editor`) for VPNs, proxies and
fixed addresses; **Open nmtui** lists the Wi-Fi networks around you in a terminal.

## Sharing

What other computers and phones on your network can reach. **Firewall** says whether it's on
(firewalld, which lets in only what's allowed) and opens its own settings when
`firewall-config` is installed. **Let in**: **Find printers and devices on the network** (mDNS),
**LocalSend** (port 53317, shown when LocalSend is installed) and **KDE Connect** (shown when
it's installed). **Remote login (SSH)** turns the SSH server on or off and says how to connect
(`ssh you@arctic.local`); **Allow password login** off means only keys in
`~/.ssh/authorized_keys` can log in. These change the whole computer, so they ask for your
password (once for a few minutes). Remote login is hidden in the live session.

## Bluetooth

![The Bluetooth page](images/settings-bluetooth.png)

Bluetooth on or off, and your devices, with **Connect**, **Disconnect** and **Forget**. **Pair a
device** opens the Bluetooth manager (`blueman-manager`), which also asks for pairing codes. On a
computer without a Bluetooth adapter the page says so.

## Sound

![The Sound page](images/settings-sound.png)

Where sound plays (**Play sound on**) and its volume, and which microphone you speak into and its
volume. **Open the volume control** starts the full mixer, for the volume of each app and device
profiles.

## Notifications

**Do not disturb** now, for an hour or until tomorrow, and **on a schedule** (every day between
two times); whether the notification centre **keeps its notifications after a restart**, and
**Clear**; and for every app that has sent a notification, what it may do: pop up, stay in the
centre only, show even during do not disturb, or keep even its urgent ones quiet then. See
[Notifications](Notifications).

## Updates

![The Updates page](images/settings-updates.png)

What's waiting, **Check now**, and **Restart and install** when updates have been downloaded.
Under **How updates come**: **Download updates automatically** (in the background; they only
install when you restart) and the **Channel**, Stable or Testing. These are the same as
`arctic-update auto on|off` and `arctic-update channel stable|testing`; see [Updates](Updates).
**Apps and firmware** shows how the daily update of your Flatpak apps went, with **Update apps
now**, and the firmware updates fwupd has for this computer, with **Install in a terminal**.
**Snapshots**: every dnf transaction takes a snapshot before and after. **Show snapshots**
(asks for your password) lists them; **Undo…** undoes one update in a terminal window (restart
afterwards), and **Take snapshot** takes one now.

## Power and lock

![The Power and lock page](images/settings-power.png)

- **When you're away:** lock the screen after, and suspend after, a time you pick (or never).
  The screen always locks before the computer sleeps. Saved in `~/.config/arctic/idle.conf`.
- **Keep awake:** no lock and no sleep for 30 minutes, 1 hour, 2 hours or until you turn it off
  (`Super + Ctrl + I` turns it on and off). See [Night light and keep awake](Night-Light-and-Keep-Awake).
- **On battery** (on laptops): other times while unplugged, or **Same as plugged in** (the
  default). Plugging in or unplugging switches between them.
- **Around the lock:** **Dim the screen before it locks** (half as bright 30 seconds before, on
  screens with a backlight; on by default) and **Turn the screens off after locking** (1 minute
  by default, or Never). A key or the mouse brings either back. Keep awake (`Super + Ctrl + I`)
  and apps that play video or hold a call pause all of this.
- **Power mode:** Power saver, Balanced or Performance (when the computer offers them).
- **Laptop lid** (on laptops): **When you close the lid** — **Suspend** (the default; it locks
  first), **Lock and turn the screen off**, or **Keep running, screen off**. With another screen
  plugged in, closing the lid turns the laptop screen off and your windows move to the other
  screen, whatever you pick here. See [Screens and the laptop lid](Screens-and-Laptop-Lid).

The live session never locks or suspends on its own; these settings apply once Arctic Linux is
installed.

## Startup apps

![The Startup apps page](images/settings-startup.png)

Apps and commands that start when you log in: **Add an app** (pick one) or **Add a command**.
They're saved as `exec-once=` lines in `settings.conf` and start from the next login. **Started
by Arctic** lists what the desktop itself starts; those live in `autostart.conf` in
`~/.config/mango/arctic`.

**Apps that start themselves** lists the apps that turned on their own "start on login" option
(Discord, Steam, Nextcloud, KDE Connect and others put a file in `~/.config/autostart`; some
packages put one in `/etc/xdg/autostart`). Arctic starts them like other desktops do, through
systemd's XDG autostart. Switching one off here writes a copy with `Hidden=true` to
`~/.config/autostart`, and switching it back on removes that copy again; both apply from the next
login. Entries meant only for other desktops (`OnlyShowIn=GNOME`, for example) don't start and
aren't listed, and nm-applet, blueman-applet and geoclue's demo agent stay off because Arctic
takes care of those itself.

## Printers and scanners

The printers you've set up and whether they're ready, with **Make default** and **Cancel jobs**,
driverless printers found **On your network**, **Open printer settings** (system-config-printer,
to add or change a printer) and **Open Document Scanner**. See
[Printing and scanning](Printing-and-Scanning).

## Date and time

**Time zone** (a searchable list of cities), **Set the time automatically** (network time; when
it's off, you can type the date and time), and the **Language** of the whole computer, which
changes at the next login. These go through systemd (`timedatectl`, `localectl`), so they ask for
your password. Night light's sunset and sunrise follow the time zone.

## Web apps

The websites you added as apps (see [Web apps](Web-Apps); you add them in the launcher's **Get
apps → Web apps**). For each one: its **Name** and **Icon** (a letter icon, or the site's own icon
again), **Open other sites in your browser**, **Extra sites** that stay inside the app (a sign-in
site it uses), **Notifications** (Allow, Ask or Block), the **Engine** (Brave, Chrome or Vivaldi
for protected video and calls), **Open email links in this app** for mail sites, **Developer
tools**, **Rendering** (Software when the window stays blank), trusted certificates of your own
devices, **Permissions** (reset), **Sign out** and **Remove**. Removing keeps the sign-in data
unless you tick **Also delete sign-in data**; kept data is listed under **Saved sign-in data**,
where **Forget** deletes it. `arctic-settings webapps` opens this page; so does **Web App
Settings…** in a web app's menu. The page needs the `arctic-webapps` package.

## About

![The About page](images/settings-about.png)

Which Arctic Linux and Fedora you run, the computer's model, processor, graphics, memory and
storage, and the versions of the window manager, shell and kernel. **Open the wiki** comes here,
and **Report a problem** has **Copy details** (a summary of the above to paste into an issue) and
**Open issues**.

**Computer name** is what other computers and phones see on your network (as NAME.local) and
over Bluetooth: letters, digits and hyphens; **Save** asks for your password.

## Users and sign-in

Your **Picture** (from your Pictures folder; shown on the login and lock screens), your **Name**,
and the jobs that ask questions, which open a terminal window: **Change password** (your keyring
follows), **Change passphrase** for an encrypted disk, and **Add a fingerprint** when the computer
has a reader. With a finger saved, the lock screen takes it too (not while the lid is closed);
**Unlock the screen with your fingerprint** turns that off. Hidden in the live session.

## Keyboard and mouse: input methods

**Input method** (at the end of Keyboard and mouse) installs Fcitx 5 for Chinese, Japanese or
Korean: tick the languages and **Install** (a terminal window asks for your password), then log
out and back in. `Ctrl + Space` switches between your keyboard and the input method;
**Configure** opens Fcitx's own settings.

## About: if something stops working

**If something stops working** restarts one part of the desktop: **Restart sound** (PipeWire),
**Restart Wi-Fi**, **Restart Bluetooth** (asks for your password) or **Restart the shell** (the
bar, launcher and notifications). The same from a terminal: `arctic-restart
sound|wifi|bluetooth|shell`. `Ctrl + Shift + Esc` opens a system monitor.

## If Settings won't open

Run it in a terminal to see its messages:

```sh
arctic-settings
```

To undo a change that made the desktop unusable, open a terminal (`Super + Enter`) and move the
file away, then reload Mango (`Super + Shift + R`):

```sh
mv ~/.config/mango/settings.conf ~/.config/mango/settings.conf.off
```

The earlier versions are in `~/.local/state/arctic/settings-backups/`.
