// Package host is the real backend: it probes the live system (disks with lsblk/sfdisk,
// firmware, DMI, NetworkManager through nmcli, GeoIP time zone) and runs the install
// pipeline of package installer with a real Runner.
package host

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/installer"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
)

// Options configure the host backend.
type Options struct {
	// Log receives command output during the install (the engine log). Never secrets.
	Log io.Writer
	// LogPath is the engine log file (copied to the target and by SaveLog).
	LogPath string
	// Target mount point (default /mnt).
	Target string
	// VolumeID of the live ISO, used to recognise the install media.
	VolumeID string
}

// Backend is the real system backend.
type Backend struct {
	opts Options
}

// New creates the host backend.
func New(opts Options) *Backend {
	if opts.VolumeID == "" {
		opts.VolumeID = "Arctic-Linux"
	}
	return &Backend{opts: opts}
}

func exists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

func readTrim(p string) string {
	b, err := os.ReadFile(p)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

// Firmware reports uefi when the kernel exposes EFI runtime services.
func Firmware() string {
	if exists("/sys/firmware/efi") {
		return "uefi"
	}
	return "bios"
}

// IsLive reports whether we run from the live ISO.
func IsLive() bool {
	if exists("/run/initramfs/live") {
		return true
	}
	return strings.Contains(readTrim("/proc/cmdline"), "rd.live.image")
}

// Info implements backend.Backend.
func (b *Backend) Info() backend.Info {
	return backend.Info{Mock: false, Live: IsLive(), Firmware: Firmware()}
}

// Language implements backend.Backend.
func (b *Backend) Language() string {
	if l := os.Getenv("LANG"); l != "" {
		return l
	}
	for _, line := range strings.Split(readTrim("/etc/locale.conf"), "\n") {
		if v, ok := strings.CutPrefix(line, "LANG="); ok {
			return strings.Trim(v, `"`)
		}
	}
	return "en_US.UTF-8"
}

// DMI implements backend.Backend.
func (b *Backend) DMI() wizard.DMI {
	return wizard.DMI{
		Vendor:  readTrim("/sys/class/dmi/id/sys_vendor"),
		Family:  readTrim("/sys/class/dmi/id/product_family"),
		Product: readTrim("/sys/class/dmi/id/product_name"),
	}
}

func output(ctx context.Context, name string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	var out, errb bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &errb
	if err := cmd.Run(); err != nil {
		return out.String(), fmt.Errorf("%s: %v: %s", name, err, strings.TrimSpace(errb.String()))
	}
	return out.String(), nil
}

// lsblkColumns are requested from lsblk (util-linux ≥ 2.39 for PARTN).
const lsblkColumns = "PATH,TYPE,SIZE,MODEL,TRAN,ROTA,RM,RO,HOTPLUG,PTTYPE,FSTYPE,LABEL,PARTTYPE,PARTLABEL,PARTN,START,LOG-SEC,MOUNTPOINTS"

// Disks implements backend.Backend.
func (b *Backend) Disks(ctx context.Context) ([]hw.Disk, error) {
	out, err := output(ctx, "lsblk", "--json", "--bytes", "--tree", "--output", lsblkColumns)
	if err != nil {
		return nil, err
	}
	disks, err := ParseLsblk([]byte(out), b.opts.VolumeID)
	if err != nil {
		return nil, err
	}
	for i := range disks {
		d := &disks[i]
		if d.PTType == "" || d.InstallMedia {
			continue
		}
		free, err := output(ctx, "sfdisk", "--list-free", d.Path)
		if err == nil {
			d.FreeRegions = ParseFree(free, d.SectorSize)
		}
	}
	return disks, nil
}

type lsblkDev struct {
	Path        string     `json:"path"`
	Type        string     `json:"type"`
	Size        int64      `json:"size"`
	Model       *string    `json:"model"`
	Tran        *string    `json:"tran"`
	Rota        flexBool   `json:"rota"`
	RM          flexBool   `json:"rm"`
	RO          flexBool   `json:"ro"`
	Hotplug     flexBool   `json:"hotplug"`
	PTType      *string    `json:"pttype"`
	FSType      *string    `json:"fstype"`
	Label       *string    `json:"label"`
	PartType    *string    `json:"parttype"`
	PartLabel   *string    `json:"partlabel"`
	PartN       *int       `json:"partn"`
	Start       *int64     `json:"start"`
	LogSec      int64      `json:"log-sec"`
	Mountpoints []*string  `json:"mountpoints"`
	Children    []lsblkDev `json:"children"`
}

// flexBool accepts true/false and the "0"/"1" strings older lsblk versions print.
type flexBool bool

func (f *flexBool) UnmarshalJSON(b []byte) error {
	s := strings.Trim(string(b), `"`)
	*f = s == "true" || s == "1"
	return nil
}

func str(p *string) string {
	if p == nil {
		return ""
	}
	return strings.TrimSpace(*p)
}

// ParseLsblk turns `lsblk --json --bytes --tree` output into disks.
func ParseLsblk(data []byte, volumeID string) ([]hw.Disk, error) {
	var doc struct {
		Blockdevices []lsblkDev `json:"blockdevices"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		return nil, fmt.Errorf("lsblk: %w", err)
	}
	var disks []hw.Disk
	for _, dev := range doc.Blockdevices {
		if dev.Type != "disk" || dev.Size == 0 || strings.HasPrefix(dev.Path, "/dev/zram") || strings.HasPrefix(dev.Path, "/dev/ram") {
			continue
		}
		d := hw.Disk{
			Path: dev.Path, Model: str(dev.Model), SizeBytes: dev.Size, Transport: str(dev.Tran),
			Rotational: bool(dev.Rota), Removable: bool(dev.RM) || bool(dev.Hotplug), ReadOnly: bool(dev.RO),
			PTType: str(dev.PTType), SectorSize: dev.LogSec,
		}
		if d.SectorSize == 0 {
			d.SectorSize = 512
		}
		media := isMedia(dev, volumeID)
		for _, c := range dev.Children {
			if isMedia(c, volumeID) {
				media = true
			}
			if c.Type != "part" {
				continue
			}
			p := hw.Partition{Path: c.Path, SizeBytes: c.Size, Type: strings.ToUpper(str(c.PartType)),
				FSType: str(c.FSType), Label: str(c.Label), PartLabel: str(c.PartLabel)}
			if c.PartN != nil {
				p.Number = *c.PartN
			} else if n := trailingNumber(c.Path); n > 0 {
				p.Number = n
			}
			if c.Start != nil {
				p.StartByte = *c.Start * 512 // lsblk START is in 512-byte sectors
			}
			d.Partitions = append(d.Partitions, p)
		}
		d.InstallMedia = media
		d.ExistingOS = guessOS(d)
		disks = append(disks, d)
	}
	return disks, nil
}

func isMedia(dev lsblkDev, volumeID string) bool {
	if strings.HasPrefix(str(dev.Label), volumeID) {
		return true
	}
	for _, m := range dev.Mountpoints {
		if mp := str(m); mp == "/run/initramfs/live" || strings.HasPrefix(mp, "/run/initramfs/") {
			return true
		}
	}
	return false
}

var trailingNum = regexp.MustCompile(`(\d+)$`)

func trailingNumber(p string) int {
	m := trailingNum.FindStringSubmatch(p)
	if m == nil {
		return 0
	}
	n, _ := strconv.Atoi(m[1])
	return n
}

// guessOS names existing systems from partition metadata (no mounting).
func guessOS(d hw.Disk) []string {
	var out []string
	seen := map[string]bool{}
	add := func(s string) {
		if !seen[s] {
			seen[s] = true
			out = append(out, s)
		}
	}
	for _, p := range d.Partitions {
		switch {
		case p.FSType == "ntfs" && (strings.EqualFold(p.Type, hw.TypeMSData) || p.Type == "0X7" || p.Type == "0x7") && !strings.Contains(strings.ToLower(p.PartLabel), "recovery"):
			add("Windows")
		case p.FSType == "BitLocker":
			add("Windows")
		case p.FSType == "apfs" || p.FSType == "hfsplus":
			add("macOS")
		case strings.Contains(strings.ToLower(p.Label), "fedora") || strings.Contains(strings.ToLower(p.PartLabel), "fedora"):
			add("Fedora Linux")
		case strings.Contains(strings.ToLower(p.Label+p.PartLabel), "arctic"):
			add("Arctic Linux")
		case p.FSType == "ext4" || p.FSType == "btrfs" || p.FSType == "xfs" || strings.EqualFold(p.Type, hw.TypeLUKS) || p.FSType == "crypto_LUKS":
			if strings.EqualFold(p.Type, hw.TypeLinux) || strings.EqualFold(p.Type, hw.TypeLUKS) || p.FSType == "crypto_LUKS" {
				add("Linux")
			}
		}
	}
	return out
}

var freeRow = regexp.MustCompile(`^\s*(\d+)\s+(\d+)\s+(\d+)\s+\S+\s*$`)

// ParseFree reads `sfdisk --list-free` rows (Start End Sectors Size) into byte regions.
func ParseFree(out string, sector int64) []hw.Region {
	if sector == 0 {
		sector = 512
	}
	var rs []hw.Region
	for _, line := range strings.Split(out, "\n") {
		m := freeRow.FindStringSubmatch(line)
		if m == nil {
			continue
		}
		start, _ := strconv.ParseInt(m[1], 10, 64)
		n, _ := strconv.ParseInt(m[3], 10, 64)
		rs = append(rs, hw.Region{StartByte: start * sector, SizeBytes: n * sector})
	}
	sort.Slice(rs, func(i, j int) bool { return rs[i].StartByte < rs[j].StartByte })
	return rs
}

// ---- network (NetworkManager via nmcli) ----

// Network implements backend.Backend.
func (b *Backend) Network(ctx context.Context) protocol.NetworkState {
	var st protocol.NetworkState
	out, err := output(ctx, "nmcli", "--terse", "--fields", "TYPE,STATE,CONNECTION", "device", "status")
	if err != nil {
		return st
	}
	for _, line := range strings.Split(out, "\n") {
		f := splitTerse(line)
		if len(f) < 3 || f[1] != "connected" {
			continue
		}
		switch f[0] {
		case "ethernet":
			st.Wired = true
		case "wifi":
			st.SSID = f[2]
		}
	}
	c, err := output(ctx, "nmcli", "networking", "connectivity", "check")
	st.Online = err == nil && strings.TrimSpace(c) == "full"
	return st
}

// splitTerse splits nmcli --terse output on unescaped colons.
func splitTerse(line string) []string {
	var out []string
	var cur strings.Builder
	for i := 0; i < len(line); i++ {
		c := line[i]
		if c == '\\' && i+1 < len(line) {
			cur.WriteByte(line[i+1])
			i++
			continue
		}
		if c == ':' {
			out = append(out, cur.String())
			cur.Reset()
			continue
		}
		cur.WriteByte(c)
	}
	return append(out, cur.String())
}

// ParseWifiList reads `nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY device wifi list`.
func ParseWifiList(out string) []protocol.WifiNetwork {
	best := map[string]protocol.WifiNetwork{}
	for _, line := range strings.Split(out, "\n") {
		f := splitTerse(line)
		if len(f) < 4 || strings.TrimSpace(f[1]) == "" || f[1] == "--" {
			continue
		}
		sig, _ := strconv.Atoi(f[2])
		n := protocol.WifiNetwork{SSID: f[1], Signal: sig, Secure: strings.TrimSpace(f[3]) != "" && f[3] != "--", Connected: f[0] == "*"}
		if old, ok := best[n.SSID]; ok {
			n.Connected = n.Connected || old.Connected
			if old.Signal > n.Signal {
				n.Signal = old.Signal
			}
		}
		best[n.SSID] = n
	}
	out2 := make([]protocol.WifiNetwork, 0, len(best))
	for _, n := range best {
		out2 = append(out2, n)
	}
	sort.Slice(out2, func(i, j int) bool {
		if out2[i].Connected != out2[j].Connected {
			return out2[i].Connected
		}
		if out2[i].Signal != out2[j].Signal {
			return out2[i].Signal > out2[j].Signal
		}
		return out2[i].SSID < out2[j].SSID
	})
	return out2
}

// ScanWifi implements backend.Backend.
func (b *Backend) ScanWifi(ctx context.Context) ([]protocol.WifiNetwork, error) {
	out, err := output(ctx, "nmcli", "--terse", "--fields", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes")
	if err != nil {
		return nil, protocol.Errorf(protocol.CodeInternal, "Couldn’t look for Wi-Fi networks.")
	}
	return ParseWifiList(out), nil
}

func securityOf(ctx context.Context, ssid string) string {
	out, err := output(ctx, "nmcli", "--terse", "--fields", "SSID,SECURITY", "device", "wifi", "list")
	if err != nil {
		return "WPA2"
	}
	for _, line := range strings.Split(out, "\n") {
		f := splitTerse(line)
		if len(f) >= 2 && f[0] == ssid {
			return f[1]
		}
	}
	return "WPA2"
}

func randomUUID() string {
	var b [16]byte
	rand.Read(b[:])
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func keyfileEscape(s string) string {
	r := strings.NewReplacer(`\`, `\\`, "\n", `\n`, "\r", `\r`, "\t", `\t`)
	s = r.Replace(s)
	if strings.HasPrefix(s, " ") {
		s = `\s` + s[1:]
	}
	return s
}

// ConnectWifi implements backend.Backend. The password is written into a root-only
// NetworkManager keyfile (never a command line); the profile is later copied to the new system.
func (b *Backend) ConnectWifi(ctx context.Context, ssid, password string) error {
	sec := securityOf(ctx, ssid)
	if strings.Contains(sec, "802.1X") {
		return protocol.Errorf(protocol.CodeAuth, "%s needs a company login, which the installer can’t do yet. Plug in a cable instead.", ssid)
	}
	name := "arctic-" + regexp.MustCompile(`[^A-Za-z0-9_-]+`).ReplaceAllString(ssid, "_")
	var kf strings.Builder
	fmt.Fprintf(&kf, "[connection]\nid=%s\nuuid=%s\ntype=wifi\n\n[wifi]\nmode=infrastructure\nssid=%s\n\n", keyfileEscape(ssid), randomUUID(), keyfileEscape(ssid))
	if strings.TrimSpace(sec) != "" && sec != "--" {
		mgmt := "wpa-psk"
		if strings.Contains(sec, "WPA3") && !strings.Contains(sec, "WPA2") {
			mgmt = "sae"
		}
		fmt.Fprintf(&kf, "[wifi-security]\nkey-mgmt=%s\npsk=%s\n\n", mgmt, keyfileEscape(password))
	}
	kf.WriteString("[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=auto\n")
	path := filepath.Join("/etc/NetworkManager/system-connections", name+".nmconnection")
	if err := os.WriteFile(path, []byte(kf.String()), 0o600); err != nil {
		return protocol.Errorf(protocol.CodeInternal, "Couldn’t save the Wi-Fi settings: %v", err)
	}
	if _, err := output(ctx, "nmcli", "connection", "load", path); err != nil {
		os.Remove(path)
		return protocol.Errorf(protocol.CodeInternal, "Couldn’t load the Wi-Fi settings.")
	}
	cctx, cancel := context.WithTimeout(ctx, 45*time.Second)
	defer cancel()
	_, err := output(cctx, "nmcli", "--wait", "40", "connection", "up", "id", ssid)
	if err == nil {
		return nil
	}
	output(context.Background(), "nmcli", "connection", "delete", "id", ssid)
	os.Remove(path)
	msg := strings.ToLower(err.Error())
	if cctx.Err() != nil || strings.Contains(msg, "timeout") || strings.Contains(msg, "timed out") {
		return protocol.Errorf(protocol.CodeTimeout, "%s didn’t answer. Move closer to the router and try again.", ssid)
	}
	return protocol.Errorf(protocol.CodeAuth, "That password didn’t work for %s. Check it and try again.", ssid)
}

// DetectTimezone implements backend.Backend with Fedora's GeoIP service.
func (b *Backend) DetectTimezone(ctx context.Context) wizard.Detected {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "https://geoip.fedoraproject.org/city", nil)
	if err != nil {
		return wizard.Detected{}
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return wizard.Detected{}
	}
	defer resp.Body.Close()
	var g struct {
		TimeZone string `json:"time_zone"`
	}
	if json.NewDecoder(io.LimitReader(resp.Body, 1<<16)).Decode(&g) != nil || !wizard.ValidTimezone(g.TimeZone) {
		return wizard.Detected{}
	}
	return wizard.Detected{Timezone: g.TimeZone, Source: "network"}
}

// Install implements backend.Backend.
func (b *Backend) Install(ctx context.Context, job *backend.Job, r backend.Reporter) error {
	if os.Geteuid() != 0 {
		return errors.New("the installer engine must run as root")
	}
	runner := &installer.ExecRunner{Log: b.opts.Log}
	return installer.New(runner, job, r, installer.Options{Target: b.opts.Target, LogPath: b.opts.LogPath}).Run(ctx)
}

// SaveLog implements backend.Backend: next to the live image when writable, else /tmp.
func (b *Backend) SaveLog(ctx context.Context) (string, error) {
	data, err := os.ReadFile(b.opts.LogPath)
	if err != nil {
		return "", err
	}
	name := "arctic-install-" + time.Now().Format("20060102-150405") + ".log"
	for _, dir := range []string{"/run/initramfs/live", os.TempDir()} {
		p := filepath.Join(dir, name)
		if err := os.WriteFile(p, data, 0o644); err == nil {
			return p, nil
		}
	}
	return "", errors.New("no writable place for the log")
}

// Reboot implements backend.Backend.
func (b *Backend) Reboot(ctx context.Context) error {
	_, err := output(ctx, "systemctl", "reboot")
	return err
}
