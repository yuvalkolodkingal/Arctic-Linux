# Printing and scanning

Arctic Linux prints and scans with the same tools as Fedora Workstation: CUPS for printing and
SANE for scanning. Most printers and scanners made in the last ten years work without drivers
("driverless": IPP Everywhere, AirPrint, Mopria, eSCL), over USB or your network.

## Print

Turn the printer on and print from the app (`Ctrl + P`). A printer on your network, or one plugged
in by USB, shows up in the print dialog by itself: CUPS finds network printers with Avahi (mDNS),
and `ipp-usb` makes USB printers look like network printers.

**Settings → Printers and scanners** shows the printers you've set up, whether they're ready,
paused or printing, and how many jobs are waiting:

- **Make default** picks the printer apps choose first (for you only; saved in
  `~/.cups/lpoptions`).
- **Cancel jobs** cancels your jobs waiting on that printer.
- **On your network** lists driverless printers CUPS found. They work from any print dialog as
  they are; **Make default** works for them too.
- **Open printer settings** opens *Print Settings* (system-config-printer) to set up a printer for
  good, share it, or change its paper size and quality. It asks for your password.

### An older printer that isn't found

Some printers from before about 2015 need a driver:

```
sudo dnf install gutenprint-cups      # many Canon, Epson and older inkjets (installed already)
sudo dnf install hplip                # HP printers that aren't driverless
sudo dnf install foomatic-db-ppds     # a large collection of older PostScript and PCL printers
```

Then add the printer in *Print Settings*.

Arctic doesn't run `cups-browsed`, which would add every printer it sees on the network as a
permanent queue; the print dialogs list them anyway. Install it (`sudo dnf install cups-browsed`)
if you need shared queues from another CUPS server.

## Scan

**Settings → Printers and scanners → Open Document Scanner** opens *Document Scanner*
(simple-scan). It finds driverless scanners on USB and the network (`sane-airscan`), including
the scanner in most multi-function printers, and classic USB scanners with the SANE drivers.
Scan to PDF or images, several pages at a time.

HP multi-function devices that aren't driverless need `sudo dnf install hplip`.

## From the terminal

```
lpstat -p -d          # printers and the default
lp -d NAME file.pdf   # print a file
cancel -a NAME        # cancel your jobs
scanimage -L          # scanners SANE can see
```
