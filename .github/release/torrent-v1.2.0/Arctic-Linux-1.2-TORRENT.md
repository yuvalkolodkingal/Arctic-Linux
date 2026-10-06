# Download Arctic Linux v1.2.0 with BitTorrent

[Download the torrent](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/v1.2.0/Arctic-Linux-1.2-x86_64.iso.parts.torrent).

This torrent downloads the **two original ISO parts** from the published
[v1.2.0 release](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/tag/v1.2.0) into a folder named `v1.2.0`.
**Join the parts before writing the ISO to USB.** It contains the same qualified
release bytes; the ISO was not rebuilt or optimized.

Use a BitTorrent client with BEP 19 HTTPS web-seed support. The embedded web seed
maps to the existing GitHub release assets. A fresh download with libtorrent
2.1.1.0 completed and verified all 2,215 pieces,
both part SHA256 hashes, and the concatenated ISO SHA256. The test disabled
trackers, DHT, PEX, local discovery, incoming listeners, and port forwarding.
It uploaded no torrent payload. A public peer seed was not used or established.

## Assemble and verify

Download the [ISO checksum file](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/v1.2.0/Arctic-Linux-1.2-x86_64.iso.sha256) separately and put it inside
the downloaded `v1.2.0` folder. Open a terminal in that folder.

Linux:

```sh
cat Arctic-Linux-1.2-x86_64.iso.part00 Arctic-Linux-1.2-x86_64.iso.part01 > Arctic-Linux-1.2-x86_64.iso
sha256sum -c Arctic-Linux-1.2-x86_64.iso.sha256
```

macOS uses the same `cat` command, followed by:

```sh
shasum -a 256 -c Arctic-Linux-1.2-x86_64.iso.sha256
```

Windows PowerShell, from the same folder:

```powershell
cmd /c copy /b Arctic-Linux-1.2-x86_64.iso.part00+Arctic-Linux-1.2-x86_64.iso.part01 Arctic-Linux-1.2-x86_64.iso
Get-FileHash Arctic-Linux-1.2-x86_64.iso -Algorithm SHA256
```

The assembled ISO must be **2,322,073,600 bytes** with SHA256:

```text
054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f
```

Only write the assembled, verified ISO to a USB stick of at least 4 GB.
Never flash an individual `.part00` or `.part01` file.

## Torrent identity and availability

- v1 infohash: `3751d7869ff5cdf50124568e93fe050b02fee559`
- Piece size: 1,048,576 bytes; 2,215 pieces
- Torrent file SHA256: `aef47ed0278212a9dfe6758d9665750915e00687961c7e0542087ced06f146c5`
- GitHub web seed: `https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/`
- Tested download completed in 87.4 seconds.

The torrent root name `v1.2.0` is deliberate: BEP 19 appends the root name and
file path to the web-seed base URL, producing each permanent release asset URL.
Clients without compatible HTTPS web-seed support need a peer seed; no public
peer-seed availability is claimed. Use the `.torrent` file to retain its embedded
web-seed metadata. An infohash or a plain magnet link alone does not bootstrap
this download when no peer supplies the metadata.

The public tracker can help clients find other peers; it does not store the ISO.
Sharing this torrent lets downloaders share the parts with one another as well
as fetch them from the verified GitHub web seed.

## References

- [BEP 3: metadata and piece hashes](https://www.bittorrent.org/beps/bep_0003.html)
- [BEP 19: web-seed URL mapping](https://www.bittorrent.org/beps/bep_0019.html)
- [libtorrent settings](https://www.libtorrent.org/reference-Settings.html)
- [OpenTrackr's announced endpoint](https://opentrackr.org/)
