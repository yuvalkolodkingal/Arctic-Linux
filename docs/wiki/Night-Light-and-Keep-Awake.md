# Night light and keep awake

Two modes you turn on and off from the keyboard: **night light** makes the screen warmer in the
evening, and **keep awake** stops the screen locking and the computer sleeping while you're away.

## Night light

`Super + Ctrl + N` turns night light on or off right away. **Settings → Displays → Night light**
sets when it comes on by itself:

| Choice | When the screen is warm |
|---|---|
| **Off** | Only when you press `Super + Ctrl + N` (until you log out or press it again) |
| **Sunset to sunrise** | From sunset to sunrise where you are |
| **Custom hours** | Between two times you pick, for example 20:00 to 07:00 |
| **Always on** | All the time |

**Warmth** sets how warm it gets. It changes as soon as you let go of the slider.

With a schedule, `Super + Ctrl + N` (and **Turn on** / **Turn off** in Settings) lasts until the
schedule changes anyway: turned off at 23:00, night light comes back the next evening; turned on
at noon, it simply stays on into the evening. The note on your screen says until when.

**Where does "sunset" come from?** From your time zone. Each time zone in the tz database has the
coordinates of its main city (`/usr/share/zoneinfo/zone1970.tab`), so Arctic works out sunset and
sunrise without looking up your location online. If your time zone is `UTC` or has no city, night
light uses the custom hours instead and Settings says so. To use your exact location, add it to
`~/.config/arctic/nightlight.conf`:

```
lat=47.3769
lon=8.5417
```

### How it works

`arctic-nightlight` keeps its schedule in `~/.config/arctic/nightlight.conf` and runs
[wlsunset](https://sr.ht/~kennylevinsen/wlsunset/), which changes the screen's colours through
Mango's gamma control. The session starts it at login (`arctic-session nightlight` in
`~/.config/mango/arctic/autostart.conf`).

```
arctic-nightlight toggle            # what Super + Ctrl + N runs
arctic-nightlight on | off          # warm now / normal now
arctic-nightlight status --json     # one line of JSON (the bar and Quick Settings read it)
arctic-nightlight set mode=hours from=21:00 to=06:30 temp=3500
```

Night light can't work where the screen doesn't let apps change its colours, for example in some
virtual machines. Settings then says so.

## Keep awake

`Super + Ctrl + I` turns keep awake on until you turn it off. While it's on, the screen doesn't
lock and the computer doesn't suspend when you're away, which is handy for presentations, long
downloads and builds. Full-screen videos, games and slideshows already keep the screen awake by
themselves.

For a set time, use the command:

```
arctic-keep-awake on 90       # for an hour and a half
arctic-keep-awake off
arctic-keep-awake status --json
```

Keep awake still locks the screen **before** the computer sleeps: suspending from the power menu
or closing the lid locks it as always. It ends when you log out.

Under the hood `arctic-keep-awake` writes its end time to `$XDG_RUNTIME_DIR/arctic/keep-awake` and
restarts swayidle without its lock and suspend timeouts (`arctic-session idle`); when it ends,
the times from **Settings → Power and lock** apply again.
