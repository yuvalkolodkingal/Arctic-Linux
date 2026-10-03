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

Each web app opens in its own window with a compact Arctic header. Back appears when there
is history; Forward and Reload are available in the app menu and through their shortcuts. Links to other
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
| `Ctrl + W` | Close the window (hide it when Keep running is enabled) |
| `Ctrl + Q` | Quit the app, including background activity |
| `F12` or `Ctrl + Shift + I` | Web inspector (when **Developer tools** is on) |

The app keeps its window size and zoom, and opens where you left off when that page belongs to
it. Starting a web app that is already open brings its window to the front.

Pages that want your camera, microphone, location or clipboard ask in a bar under the header,
outside the page, so a page can't imitate it: **Allow** or **Block**, remembered for that site.
A site embedded in the page that asks to use its own cookies there (a sign-in or comments
frame) is named in the bar, and the answer holds for those two sites only.
Notifications from the app's own site are allowed by default and show in Arctic's notification
centre under the app's name and icon; **Block** in Settings stops them in the open window too.
Downloads go to your Downloads folder and never replace an existing file. Turn on **Ask where
to save downloads** in Settings → Web apps for a native save dialog. Choose a new filename;
existing files are protected from replacement. The menu's **Downloads** view shows progress,
Cancel, failures, Open and Show in folder. File uploads use a native chooser too.

The window and websites that use the system theme follow Arctic's light/dark theme live,
without reloading the page. If a website has its own appearance setting, choose **System** or
**Automatic** there; a website's explicit light/dark choice still takes precedence.

## What works, and the engine

Web apps run on WebKitGTK, the engine of GNOME Web, with their own profile. Most sites work.
Fedora's WebKitGTK has no video or voice calls (WebRTC) and can't play protected video (DRM), so:

- **Calls**: WhatsApp Web, Google Meet, Teams, Zoom, Discord, Slack huddles, Whereby and Jitsi
  need a Chromium-family engine. From 1.1, Chromium is installed with the web-app package and
  Get apps selects an available calling-capable engine automatically for these sites.
- **Protected video and music**: Netflix, Spotify, Prime Video, Tidal, Disney+, Max, Apple Music
  and TV, Deezer and Hulu don't play.

For those sites the preview warns you and suggests another engine: **Brave**, **Google Chrome**
or **Vivaldi** (they include the DRM module) or **Chromium**, installed from Get apps. The web app
then opens as an app window of that browser, still with its own profile. Choose the engine in the
preview, or later:

```sh
arctic-webapp set org.arcticlinux.WebApp.Netflix_0a1b2c --runtime chromium:brave
```

If that browser is removed later, reinstall it or choose another engine in Settings → Web
apps. Arctic keeps the old profile. Switching engines may require signing in again.

## Background apps and media

In Settings → Web apps, **Keep running when closed** lets the Arctic engine hide its window
while keeping the page and sign-in session alive. Notifications can still arrive while hidden;
clicking one invokes the website's own action and brings the app back. **Quit**, `Ctrl + Q`,
or the Quit button in Settings stops the process. Background apps remain listed as Running.

**Start at login** is separate. With Keep running enabled, it starts hidden; otherwise it
opens a window. Both settings default to off, including for existing apps. The startup entry
also appears in Settings → Startup apps. Removing an app removes its startup entry even when
you retain sign-in data.

```sh
arctic-webapp set ID --keep-running on --start-at-login on
arctic-webapp set ID --ask-download on
arctic-webapp quit ID
```

Closing an app with Keep running enabled can continue audio or capture. Use Quit to stop it,
or the header's capture button to stop its camera, microphone and screen sharing. Sharing
requires a fresh permission decision; camera and microphone permissions are checked separately.
Actual capture and calls depend on the runtime and desktop portal support.

The Arctic engine exposes ordinary audio/video elements in the app's main page through MPRIS,
so the desktop media panel and media keys can play/pause and seek when the media supports it.
It excludes call streams and does not advertise next/previous track actions. Embedded players
and sites with custom media control may not support these controls. See the
[compatibility results](../WEBAPP-COMPATIBILITY.md) for what has been tested.

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

- **An existing WhatsApp app says calls are unsupported**: after updating to 1.1, open
  **Settings → Web apps → WhatsApp → Open with** and choose **Chromium** (or an installed
  Chrome/Brave engine), then restart the app. Switching engines may require pairing again;
  the original engine's sign-in data is kept. WhatsApp must also offer web calls for your account.
- **WhatsApp or another site declines the preview request** (HTTP 400, 401, 403, 405 or 429): Arctic offers a letter icon and lets you add the app. You can rename it in the preview and sign in when its window opens. An error page is never used as the app’s name or icon.
- **Video playback is slow**: use `arctic-webapp set ID --rendering auto` and restart the app. The `arctic-webapps` package includes GStreamer’s VA-API/NVDEC plugins; hardware decoding also needs your GPU’s driver. Any driver workarounds you set in your environment still apply.
- **The window stays blank or flickers** (some NVIDIA setups): turn on software rendering:
  `arctic-webapp set ID --rendering software`. Automatic rendering keeps hardware acceleration and DMA-BUF enabled, including on NVIDIA. Use software rendering only for an app that needs it.
- **A site on your network has a self-signed certificate**: the page says the connection isn't
  private. Arctic only lets you trust a certificate for sites on your own network (names ending in
  `.lan`, `.local`, `.home.arpa`, `.internal`, or private addresses, Tailscale's 100.x ones
  included).
- **Sign out of an app**: `arctic-webapp clear-data ID` deletes its cookies and data and keeps the
  app.
- **Log**: `~/.local/state/arctic/webapps/ID.log` (addresses without their query part).
- **Launcher entries look wrong**: `arctic-webapp repair` rewrites them and their icons.

## Privacy

Arctic reads a site only when you add it or ask to refresh it, with the same address and user
agent the app uses. It never asks third-party icon services (they would learn which sites you
use) and sends nothing anywhere else. Each app's cookies and data stay in
`~/.local/share/arctic/webapps/ID/`; nothing is shared with your browser or with other web apps.

## Remaining limitations

Notifications after the app has fully quit, the manifest's shortcuts and file and share handlers,
saved passwords, and Firefox-based browsers as engines (they have no app mode).
