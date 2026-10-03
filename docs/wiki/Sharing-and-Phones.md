# Sharing and phones

## Send files nearby: LocalSend

[LocalSend](https://localsend.org) sends files between phones and computers on the same network,
like AirDrop, without an account or the internet. Install it from Get apps (`Super + Shift + A`,
search for LocalSend; it's on Flathub) and on your phone.

`Super + Ctrl + S` opens the share menu:

- **Send the clipboard**: what you copied (text or a picture) is saved to your Downloads folder
  and LocalSend opens with it ready to send; pick the device to send it to.
- **Send files or receive (LocalSend)**: opens LocalSend.
- **Your phone (KDE Connect)**, when KDE Connect is installed.
- **Sharing settings**.

If you installed Thunar, right-click files or folders and choose **Send To → LocalSend**: LocalSend
opens with them on its Send page.

To receive, LocalSend needs port 53317: turn on **Settings → Sharing → LocalSend**.

From a terminal: `arctic-share files PATH…`, `arctic-share clipboard`, `arctic-share open`,
`arctic-share status`.

## Your phone: KDE Connect

KDE Connect shows your Android phone's notifications on the computer, shares the clipboard and
sends files both ways. Install it with `sudo dnf install kde-connect` and the KDE Connect app on
the phone, turn on **Settings → Sharing → KDE Connect** so the phone can reach the computer, and
log out and back in: its daemon then starts with the desktop (XDG autostart).

## The Sharing page

**Settings → Sharing** shows whether the firewall is on and what it lets in: devices looking for
each other (mDNS), LocalSend, KDE Connect and remote login. Each switch asks for your password.

**Remote login (SSH)** turns the SSH server on (off by default) and shows how to connect:
`ssh you@your-computer.local`. With **Allow password login** off, only the keys in
`~/.ssh/authorized_keys` can log in, which is safer; Settings warns when that would lock
everyone out. Your own SSH keys are unlocked once per session by an agent; see
[Terminal and shell](Terminal-and-Shell#ssh-keys).
