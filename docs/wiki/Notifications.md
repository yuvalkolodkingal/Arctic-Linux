# Notifications

Arctic's desktop shows notifications itself: they pop up in the top-right corner, wait in the
notification centre under the bell, and stay quiet while do not disturb is on. (In the
[fallback desktop](Architecture) with waybar, mako shows them instead, as in Arctic 0.2.)

## Pop-ups

A notification appears as a card in the top-right corner of the screen you're working on,
newest on top. Up to three show at once; a "2 more" row under them opens the centre.

- A normal notification stays for 8 seconds, a quiet one (low urgency) for 5. **Urgent** ones
  have a red edge and the word "Urgent", and stay until you close them. An app can ask for its
  own time instead.
- Point at a card to keep it there; its close button appears in the corner.
- **Click** a card to do what the app offers first (open the chat, show the download), or to
  bring the app's window forward. Buttons on the card run the app's other actions.
- Closing a card, or letting it time out, doesn't delete it: it stays in the centre.
- Nothing pops up while the screen is locked. The lock screen says how many arrived instead
  ("3 notifications"), never what they say.

## The notification centre

Click the **bell** on the bar, or press `Super + Alt + N`. A dot on the bell means something
arrived since you last looked.

- Notifications are grouped by app, newest first. The three newest apps are open; older ones
  fold into one card ("5 from Signal"). Click a folded card to open it.
- Click a notification to act on it, use its buttons, or the **×** to dismiss it. The **×** next
  to an app's name clears that app. **Clear all** empties the centre.
- The centre keeps the last 50 notifications, also after a restart (in
  `~/.local/state/arctic/notifications`, readable only by you). Notifications from before the
  restart have no buttons any more; clicking one opens the app.
- If the app withdraws a notification (you read the message on your phone), it leaves the
  centre too.

With the keyboard: `↑` `↓` move, `Enter` acts, `→` opens a folded app or do not disturb's
choices, `←` folds or goes back, `Tab` steps through a notification's buttons, `Delete`
dismisses (on an app's name: clears the app), `Shift + Delete` clears everything, `Esc` closes.

## Do not disturb

Turn it on with the switch at the top of the centre, by right-clicking the bell, or with
`Super + Shift + N`. The **›** next to the switch (or `→`) offers **For 1 hour**, **Until
tomorrow** (08:00) and **Until I turn it off**. The bell shows a crossed-out bell while it's on.

While it's on, pop-ups wait quietly in the centre. These still show:

- **Arctic's own alerts**, like a battery about to run out or updates that failed to install;
- **urgent** notifications (alarms, calls), unless you told Arctic to keep an app's urgent ones
  quiet too (see below);
- apps you allowed "even during do not disturb".

This is Arctic's own rule. (Omarchy lets no urgent notification through, because some chat apps
mark every message urgent; in Arctic you can silence such an app instead.)

**On a schedule**: Settings → Notifications turns it on every day between two times, for example
22:00 to 07:00. Turning it off during the scheduled time keeps it off until the schedule starts
again.

## Per-app choices

Settings → Notifications lists every app that has sent a notification. For each one:

| Choice | Pops up | In the centre | During do not disturb |
|---|---|---|---|
| **Pop-ups, kept in the centre** (the default) | yes | yes | only urgent ones |
| **Pop-ups, even during do not disturb** | yes | yes | yes |
| **Pop-ups, never during do not disturb** | yes | yes | no, not even urgent ones |
| **Only in the notification centre** | no | yes | — |
| **Pop-ups only, not kept** | yes | no | only urgent ones |
| **Nothing** | no | no | — |

The choices are saved in `~/.config/arctic/notifications.json`.

## From the terminal and keys

| Command | Key | Does |
|---|---|---|
| `arctic-notify dismiss` | `Super + Delete` | Close the newest pop-up (it stays in the centre) |
| `arctic-notify dismiss-all` | `Super + Shift + Delete` | Close every pop-up |
| `arctic-notify center` | `Super + Alt + N` | Open or close the centre |
| `arctic-notify invoke` | `Super + Alt + ,` | Act on the newest notification (like clicking it) |
| `arctic-notify history` | — | What the centre holds, one JSON line per notification |
| `arctic-notify count` | — | How many notifications the centre holds |
| `arctic-dnd toggle`, `on`, `off`, `for 1h`, `until-tomorrow`, `status` | `Super + Shift + N` | Do not disturb |

Apps and scripts send notifications the usual way (`notify-send`, libnotify, GNotification).
The shell understands action buttons, replacing a notification, `-t` timeouts, `-e`
(transient: never kept), the `value` hint (a level bar) and `x-canonical-private-synchronous`
(a newer message with the same tag replaces the older one).

## If notifications don't show up

- Another notification program (dunst, swaync) was started and owns notifications. The centre
  then says so and the bell falls back to plain do not disturb. Stop that program and log in
  again.
- If the shell can't become the notification service at all, it starts mako so notifications
  keep working.
