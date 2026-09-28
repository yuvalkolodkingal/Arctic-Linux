# Web apps

A web app is a website with its own launcher entry, icon and window, and its own sign-in, kept
apart from your browser. Gmail, YouTube Music, Notion or your Home Assistant can live in the
launcher and the app switcher like any other app. Arctic Linux makes them with its own engine,
`arctic-webapp`, from version 0.3.

## Add a web app

In the launcher, open **Get apps** and choose **Web apps**, then type or paste an address, like
`music.youtube.com`. Arctic reads the site (its name, its app manifest and its icons, without
running any of its JavaScript) and shows a preview: the name, which you can change, a choice of
icons, a category and the engine. Click **Add app**. The app is in the launcher straight away.

From a terminal:

```sh
arctic-webapp install music.youtube.com                # add it with what the site offers
arctic-webapp install mail.google.com/mail/u/1/        # a deep address is kept: a second Gmail account
arctic-webapp install ha.lan:8123 --name "Home"        # a site on your own network
arctic-webapp list                                     # what you have
```

If the site has no usable icon, Arctic draws a letter icon in the category's tile colour. When
you add the same site twice, Arctic says it's already added; **Add a second copy** makes another
app with its own sign-in (a second account).

## Remove a web app

In the launcher, open **Remove apps** and choose **Web apps**. Removing an app there keeps its sign-in data unless you tick **Also delete sign-in
data**, so adding the same site again later finds you still signed in. Kept data is listed under
**Saved sign-in data**, where **Forget** deletes it.

```sh
arctic-webapp remove org.arcticlinux.WebApp.YouTubeMusic_4c1a9e              # deletes its data too
arctic-webapp remove org.arcticlinux.WebApp.YouTubeMusic_4c1a9e --keep-data  # keeps your sign-in
arctic-webapp forget org.arcticlinux.WebApp.YouTubeMusic_4c1a9e              # deletes kept data
```

## The window

Each web app opens in its own window with Back, Forward and Reload in the header. Links to other
sites open in your browser (the one you chose in **Settings → Apps**); sign-in pages that the
site sends you to, like Google's or Microsoft's, open inside the app so signing in works. When a
page of another site is showing, the header shows its address and **Back to _App_**.

| Keys | Action |
|---|---|
| `Ctrl + F`, then `Enter` / `Shift + Enter`, `Esc` | Find in the page |
| `Ctrl + =` / `Ctrl + -` / `Ctrl + 0` | Zoom in, out, reset (remembered per app) |
| `F5` or `Ctrl + R`; `Ctrl + Shift + R` | Reload; reload without the cache |
| `Alt + ←` / `Alt + →`, mouse back and forward buttons | Back / forward |
| `Ctrl + L` | Copy the page's address |
| `Ctrl + P` | Print |
| `F11` | Full screen |
| `Ctrl + W` | Close the window |
| `F12` or `Ctrl + Shift + I` | Web inspector (when **Developer tools** is on) |

The app keeps its window size and zoom, and opens where you left off when that page belongs to
it. Starting a web app that is already open brings its window to the front.

Pages that want your camera, microphone, location or clipboard ask in a bar under the header,
outside the page, so a page can't imitate it: **Allow** or **Block**, remembered for that site.
Notifications from the app's own site are allowed by default and show in Arctic's notification
centre under the app's name and icon. Downloads go to your Downloads folder and never replace a
file that is already there.

The window follows the Arctic theme, light or dark, and changes with it.

## What works, and the engine

Web apps run on WebKitGTK, the engine of GNOME Web, with their own profile. Most sites work.
Fedora's WebKitGTK has no video or voice calls (WebRTC) and can't play protected video (DRM), so:

- **Calls**: Google Meet, Teams, Zoom, Discord, Slack huddles, Whereby and Jitsi calls don't work.
- **Protected video and music**: Netflix, Spotify, Prime Video, Tidal, Disney+, Max, Apple Music
  and TV, Deezer and Hulu don't play.

For those sites the preview warns you and suggests another engine: **Brave**, **Google Chrome**
or **Vivaldi** (they include the DRM module) or **Chromium**, installed from Get apps. The web app
then opens as an app window of that browser, still with its own profile. Choose the engine in the
preview, or later:

```sh
arctic-webapp set org.arcticlinux.WebApp.Netflix_0a1b2c --runtime chromium:brave
```

If that browser is removed later, the app opens in the Arctic engine again with a note saying so.

## Email links

For Gmail, Outlook, Proton Mail, Fastmail and HEY, the preview offers **Open email links in this
app** (off by default; `arctic-webapp set ID --mail-links on` later). With it on, the app is
offered for `mailto:` links; to make it your email app:

```sh
xdg-mime default org.arcticlinux.WebApp.Gmail_77aa01.desktop x-scheme-handler/mailto
```

Clicking an email address anywhere then opens a new message in it.

## Keyboard shortcut for a web app

Web apps have no shortcuts of their own. Give one a key in `~/.config/mango/user.conf`, with its
id from `arctic-webapp list`:

```
bind=SUPER+ALT,m,spawn,arctic-webapp run org.arcticlinux.WebApp.YouTubeMusic_4c1a9e
```

Pressing it again brings the open window to the front.

## Troubleshooting

- **The window stays blank or flickers** (some NVIDIA setups): turn on software rendering:
  `arctic-webapp set ID --rendering software`. On the NVIDIA driver, Arctic already applies the
  usual workarounds.
- **A site on your network has a self-signed certificate**: the page says the connection isn't
  private. Arctic only lets you trust a certificate for sites on your own network (names ending in
  `.lan`, `.local`, `.home.arpa`, `.internal`, or private addresses).
- **Sign out of an app**: `arctic-webapp clear-data ID` deletes its cookies and data and keeps the
  app.
- **Log**: `~/.local/state/arctic/webapps/ID.log` (addresses without their query part).
- **Launcher entries look wrong**: `arctic-webapp repair` rewrites them and their icons.

## Privacy

Arctic reads a site only when you add it or ask to refresh it, with the same address and user
agent the app uses. It never asks third-party icon services (they would learn which sites you
use) and sends nothing anywhere else. Each app's cookies and data stay in
`~/.local/share/arctic/webapps/ID/`; nothing is shared with your browser or with other web apps.

## Not in 0.3

Notifications while the window is closed, the manifest's shortcuts and file and share handlers,
saved passwords, and Firefox-based browsers as engines (they have no app mode).
