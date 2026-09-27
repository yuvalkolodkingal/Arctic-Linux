// Package hw holds the hardware facts the wizard and the installer plan against: disks,
// partitions and free space. The real backend fills them from lsblk/sfdisk, the mock backend
// from a fixed inventory.
package hw

import (
	"fmt"
	"strings"
)

const (
	KB = 1000
	MB = 1000 * KB
	GB = 1000 * MB
	TB = 1000 * GB

	MiB = 1024 * 1024
	GiB = 1024 * MiB

	// MinInstallBytes is the smallest disk (erase) or free region (alongside) we install to.
	MinInstallBytes = 40 * GB
)

// GPT partition type GUIDs used by the planner and the prober.
const (
	TypeBIOSBoot = "21686148-6449-6E6F-744E-656564454649"
	TypeESP      = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
	TypeLinux    = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
	TypeLUKS     = "CA7D7CCB-63ED-4C53-861C-1742536059CC"
	TypeMSR      = "E3C9E316-0B5C-4DB8-817D-F92DF00215AE"
	TypeMSData   = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
	TypeWinRE    = "DE94BBA4-06D1-4D40-A16A-BFD50179D6AC"
)

// Disk is one whole disk.
type Disk struct {
	Path         string      `json:"path"` // /dev/nvme0n1
	Model        string      `json:"model"`
	SizeBytes    int64       `json:"size_bytes"`
	Transport    string      `json:"transport"` // nvme | sata | usb | virtio | …
	Rotational   bool        `json:"rotational"`
	Removable    bool        `json:"removable"`
	InstallMedia bool        `json:"install_media"`
	ReadOnly     bool        `json:"read_only"`
	PTType       string      `json:"pttype"` // gpt | dos | "" (blank disk)
	SectorSize   int64       `json:"sector_size"`
	Partitions   []Partition `json:"partitions"`
	FreeRegions  []Region    `json:"free_regions"` // unallocated space, largest first not required
	ExistingOS   []string    `json:"existing_os"`
}

// Partition is one partition of a Disk.
type Partition struct {
	Path      string `json:"path"`
	Number    int    `json:"number"`
	StartByte int64  `json:"start_bytes"`
	SizeBytes int64  `json:"size_bytes"`
	Type      string `json:"type"` // GPT type GUID (upper case) or MBR type ("0x83")
	FSType    string `json:"fstype"`
	Label     string `json:"label"`
	PartLabel string `json:"partlabel"`
}

// Region is unallocated space on a disk.
type Region struct {
	StartByte int64 `json:"start_bytes"`
	SizeBytes int64 `json:"size_bytes"`
}

// LargestFree returns the largest unallocated region (zero Region if none).
func (d Disk) LargestFree() Region {
	var best Region
	for _, r := range d.FreeRegions {
		if r.SizeBytes > best.SizeBytes {
			best = r
		}
	}
	return best
}

// ESP returns the first EFI system partition.
func (d Disk) ESP() (Partition, bool) {
	for _, p := range d.Partitions {
		if strings.EqualFold(p.Type, TypeESP) || p.Type == "0xef" {
			return p, true
		}
	}
	return Partition{}, false
}

// BIOSBoot returns the BIOS boot partition, if any.
func (d Disk) BIOSBoot() (Partition, bool) {
	for _, p := range d.Partitions {
		if strings.EqualFold(p.Type, TypeBIOSBoot) {
			return p, true
		}
	}
	return Partition{}, false
}

// NextPartitionNumber is the first unused partition number.
func (d Disk) NextPartitionNumber() int {
	used := map[int]bool{}
	for _, p := range d.Partitions {
		used[p.Number] = true
	}
	n := 1
	for used[n] {
		n++
	}
	return n
}

// PartitionPath names partition n of the disk: /dev/sda3, /dev/nvme0n1p3, /dev/mmcblk0p3.
func (d Disk) PartitionPath(n int) string {
	return PartitionPath(d.Path, n)
}

// PartitionPath names partition n of disk path.
func PartitionPath(disk string, n int) string {
	if disk != "" {
		last := disk[len(disk)-1]
		if last >= '0' && last <= '9' {
			return fmt.Sprintf("%sp%d", disk, n)
		}
	}
	return fmt.Sprintf("%s%d", disk, n)
}

// Label is the dropdown label, e.g. "Samsung SSD 980 · 512 GB".
func (d Disk) Label() string {
	m := strings.TrimSpace(d.Model)
	if m == "" {
		m = d.Path
	}
	return m + " · " + SizeLabel(d.SizeBytes)
}

// SizeLabel formats bytes the way disks are sold: "512 GB", "1 TB", "1.5 TB", "180 GB".
func SizeLabel(b int64) string {
	switch {
	case b >= TB:
		return trimFloat(float64(b)/TB, 1) + " TB"
	case b >= GB:
		return fmt.Sprintf("%d GB", (b+GB/2)/GB)
	case b >= MB:
		return fmt.Sprintf("%d MB", (b+MB/2)/MB)
	default:
		return fmt.Sprintf("%d KB", (b+KB/2)/KB)
	}
}

// DownloadLabel formats a download size: "850 MB", "1.4 GB".
func DownloadLabel(b int64) string {
	if b >= GB {
		return trimFloat(float64(b)/GB, 1) + " GB"
	}
	if b >= MB {
		return fmt.Sprintf("%d MB", (b+MB/2)/MB)
	}
	if b > 0 {
		return "1 MB"
	}
	return "0 MB"
}

func trimFloat(f float64, prec int) string {
	s := fmt.Sprintf("%.*f", prec, f)
	s = strings.TrimRight(strings.TrimRight(s, "0"), ".")
	return s
}

// AlongsidePossible reports whether the disk has a partition table and enough free space.
func (d Disk) AlongsidePossible() bool {
	return d.PTType != "" && d.LargestFree().SizeBytes >= MinInstallBytes
}

// OSName is the first detected OS, or a neutral name.
func (d Disk) OSName() string {
	if len(d.ExistingOS) > 0 {
		return d.ExistingOS[0]
	}
	return "your other system"
}
