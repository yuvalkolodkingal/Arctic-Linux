# Drives, phones and cameras

## USB drives and SD cards

Plug in a USB drive or an SD card and it's ready by itself: Arctic mounts it under
`/run/media/<you>/<name>`, a notification says so, and it's in Nautilus (Files)'s side panel. An encrypted
drive asks for its passphrase first.

**Before you unplug it**, eject it, so everything written to it is really on it:

- in Nautilus (Files), the eject button next to the drive in the side panel, or
- `arctic-drives eject /dev/sdX` in a terminal (`arctic-drives list` shows what's plugged in).

If something still uses the drive (a file open in an app, a terminal inside it), ejecting says so:
close it and try again.

To stop drives mounting by themselves, put this in `~/.config/arctic/drives.conf` and log in
again; they then mount when you open them in Nautilus (Files):

```
automount=off
```

Mounting is done by [udiskie](https://github.com/coldfix/udiskie), started at login by
`arctic-session drives` (`~/.config/mango/arctic/autostart.conf`). The live USB session doesn't
mount drives by itself, so it never gets in the installer's way.

## Phones and cameras

Nautilus (Files) shows phones and cameras in its side panel through GVFS:

- **Android phones**: plug in the cable, then choose **File transfer** in the USB notification on
  the phone. The phone appears in Nautilus (Files).
- **iPhone and iPad**: unlock it and tap **Trust** when it asks.
- **Cameras**: most cameras appear as a camera (PTP) or as a USB drive.

## Network shares

In Nautilus (Files), type `smb://server/share` (Windows and NAS shares) or `sftp://you@server/` into the
address bar (`Ctrl + L`). Nautilus (Files) asks for the password and can remember it in your keyring.
