package host

import (
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/hw"
)

// Shaped like util-linux 2.41 output on Fedora 44 (booleans, numeric partn/start/log-sec).
const lsblkSample = `{
   "blockdevices": [
      {"path": "/dev/zram0", "type": "disk", "size": 8589934592, "model": null, "tran": null, "rota": false, "rm": false, "ro": false, "hotplug": false,
       "pttype": null, "fstype": null, "label": null, "parttype": null, "partlabel": null, "partn": null, "start": null, "log-sec": 4096, "mountpoints": ["[SWAP]"]},
      {"path": "/dev/nvme0n1", "type": "disk", "size": 512110190592, "model": "Samsung SSD 980 500GB", "tran": "nvme", "rota": false, "rm": false, "ro": false, "hotplug": false,
       "pttype": "gpt", "fstype": null, "label": null, "parttype": null, "partlabel": null, "partn": null, "start": null, "log-sec": 512, "mountpoints": [null],
       "children": [
          {"path": "/dev/nvme0n1p1", "type": "part", "size": 104857600, "model": null, "tran": "nvme", "rota": false, "rm": false, "ro": false, "hotplug": false, "pttype": "gpt",
           "fstype": "vfat", "label": null, "parttype": "c12a7328-f81f-11d2-ba4b-00a0c93ec93b", "partlabel": "EFI system partition", "partn": 1, "start": 2048, "log-sec": 512, "mountpoints": [null]},
          {"path": "/dev/nvme0n1p3", "type": "part", "size": 330000000000, "model": null, "tran": "nvme", "rota": false, "rm": false, "ro": false, "hotplug": false, "pttype": "gpt",
           "fstype": "ntfs", "label": "Windows", "parttype": "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7", "partlabel": "Basic data partition", "partn": 3, "start": 239616, "log-sec": 512, "mountpoints": [null]}
       ]},
      {"path": "/dev/sda", "type": "disk", "size": 30752000000, "model": "Ultra", "tran": "usb", "rota": false, "rm": true, "ro": false, "hotplug": true,
       "pttype": "dos", "fstype": "iso9660", "label": "Arctic-Linux-0.1", "parttype": null, "partlabel": null, "partn": null, "start": null, "log-sec": 512, "mountpoints": [null],
       "children": [
          {"path": "/dev/sda1", "type": "part", "size": 2000000000, "model": null, "tran": "usb", "rota": "0", "rm": "1", "ro": "0", "hotplug": "1", "pttype": "dos",
           "fstype": "iso9660", "label": "Arctic-Linux-0.1", "parttype": "0x0", "partlabel": null, "partn": 1, "start": 0, "log-sec": 512, "mountpoints": ["/run/initramfs/live"]}
       ]},
      {"path": "/dev/loop0", "type": "loop", "size": 1900000000, "model": null, "tran": null, "rota": false, "rm": false, "ro": true, "hotplug": false,
       "pttype": null, "fstype": "squashfs", "label": null, "parttype": null, "partlabel": null, "partn": null, "start": null, "log-sec": 512, "mountpoints": ["/run/rootfsbase"]}
   ]
}`

func TestParseLsblk(t *testing.T) {
	disks, err := ParseLsblk([]byte(lsblkSample), "Arctic-Linux")
	if err != nil {
		t.Fatal(err)
	}
	if len(disks) != 2 {
		t.Fatalf("want nvme + usb, got %+v", disks)
	}
	n := disks[0]
	if n.Path != "/dev/nvme0n1" || n.PTType != "gpt" || n.InstallMedia || n.Removable || len(n.Partitions) != 2 {
		t.Fatalf("nvme %+v", n)
	}
	if esp, ok := n.ESP(); !ok || esp.Number != 1 || esp.StartByte != 2048*512 {
		t.Errorf("esp %+v", esp)
	}
	if len(n.ExistingOS) != 1 || n.ExistingOS[0] != "Windows" {
		t.Errorf("os %v", n.ExistingOS)
	}
	if n.NextPartitionNumber() != 2 {
		t.Errorf("next partition %d", n.NextPartitionNumber())
	}
	u := disks[1]
	if !u.InstallMedia || !u.Removable {
		t.Errorf("usb %+v", u)
	}
}

func TestParseFree(t *testing.T) {
	// Real `sfdisk --list-free` output for the mock's Windows layout (Fedora 44, util-linux 2.41).
	out := `Unpartitioned space win.img: 168.76 GiB, 181200559616 bytes, 353907343 sectors
Units: sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes

    Start        End   Sectors   Size
644771840  996333567 351561728 167.6G
997869568 1000215182   2345615   1.1G
`
	rs := ParseFree(out, 512)
	if len(rs) != 2 || rs[0].StartByte != 644771840*512 || rs[0].SizeBytes != 351561728*512 {
		t.Fatalf("regions %+v", rs)
	}
	d := hw.Disk{PTType: "gpt", FreeRegions: rs}
	if !d.AlongsidePossible() || hw.SizeLabel(d.LargestFree().SizeBytes) != "180 GB" {
		t.Errorf("largest %+v", d.LargestFree())
	}
}

func TestParseWifiList(t *testing.T) {
	out := " :Snowfield:64:WPA2\n*:Tundra-5G:82:WPA2 WPA3\n :Cafe\\: Polar:41:\n :Tundra-5G:40:WPA2\n : :10:WPA2\n :Office:55:WPA2 802.1X\n"
	nets := ParseWifiList(out)
	if len(nets) != 4 {
		t.Fatalf("%+v", nets)
	}
	if nets[0].SSID != "Tundra-5G" || !nets[0].Connected || nets[0].Signal != 82 {
		t.Errorf("first %+v", nets[0])
	}
	found := false
	for _, n := range nets {
		if n.SSID == "Cafe: Polar" {
			found = true
			if n.Secure {
				t.Error("open network marked secure")
			}
		}
	}
	if !found {
		t.Error("escaped colon SSID not parsed")
	}
}

func TestKeyfileEscape(t *testing.T) {
	if got := keyfileEscape(" a\\b\nc"); got != `\sa\\b\nc` {
		t.Errorf("got %q", got)
	}
}
