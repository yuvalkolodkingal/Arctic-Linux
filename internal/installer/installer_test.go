package installer

import (
	"context"
	"errors"
	"flag"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/mock"
	"github.com/yuvalkolodkingal/o-tism/internal/profile"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/modules"
	"github.com/yuvalkolodkingal/o-tism/profiles"
)

var update = flag.Bool("update", false, "rewrite the golden files")

const (
	testLUKS     = "acid acorn acre aged"
	testPassword = "winter-fox-2026"
)

type testReporter struct {
	mu        sync.Mutex
	modules   map[string]string
	attention []string
	decide    func(id string, n int) backend.Decision
	logs      []string
	progress  []protocol.ProgressEvent
}

func newReporter() *testReporter { return &testReporter{modules: map[string]string{}} }

func (r *testReporter) Progress(ev protocol.ProgressEvent) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.progress = append(r.progress, ev)
}
func (r *testReporter) Module(ev protocol.ModuleEvent) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.modules[ev.ID] = ev.Status
}
func (r *testReporter) Attention(ctx context.Context, ev protocol.AttentionEvent) backend.Decision {
	r.mu.Lock()
	r.attention = append(r.attention, ev.Module.ID)
	n := 0
	for _, a := range r.attention {
		if a == ev.Module.ID {
			n++
		}
	}
	r.mu.Unlock()
	if r.decide != nil {
		return r.decide(ev.Module.ID, n)
	}
	return backend.Skip
}
func (r *testReporter) Logf(format string, a ...any) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.logs = append(r.logs, format)
}

func loadJob(t *testing.T, profilePath, firmware string) *backend.Job {
	t.Helper()
	cat, err := catalog.Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	data, err := profiles.FS.ReadFile(profilePath)
	if err != nil {
		t.Fatal(err)
	}
	p, err := profile.Parse(data)
	if err != nil {
		t.Fatal(err)
	}
	d, disk, err := p.Data(cat, mock.Inventory(), "thinkpad")
	if err != nil {
		t.Fatal(err)
	}
	return &backend.Job{Data: d, Disk: disk, Firmware: firmware, Catalog: cat,
		Secrets: &backend.Secrets{LUKS: []byte(testLUKS), Password: []byte(testPassword)}, LogPath: "/var/log/arctic-install/engine.log"}
}

func runPlan(t *testing.T, job *backend.Job, rec *Recorder, rep *testReporter) error {
	t.Helper()
	in := New(rec, job, rep, Options{Salt: "testsalt"})
	return in.Run(context.Background())
}

func golden(t *testing.T, name, got string) {
	t.Helper()
	path := filepath.Join("testdata", name)
	if *update {
		if err := os.MkdirAll("testdata", 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(got), 0o644); err != nil {
			t.Fatal(err)
		}
		return
	}
	want, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("%v (run go test ./internal/installer -update to create it)", err)
	}
	if string(want) != got {
		wl, gl := strings.Split(string(want), "\n"), strings.Split(got, "\n")
		for i := 0; i < len(wl) || i < len(gl); i++ {
			var w, g string
			if i < len(wl) {
				w = wl[i]
			}
			if i < len(gl) {
				g = gl[i]
			}
			if w != g {
				t.Fatalf("%s differs at line %d:\nwant: %s\n got: %s\n(run go test ./internal/installer -update after checking the change)", name, i+1, w, g)
			}
		}
	}
}

func checkNoSecrets(t *testing.T, plan string) {
	t.Helper()
	for _, s := range []string{testLUKS, testPassword, "$6$"} {
		if strings.Contains(plan, s) {
			t.Errorf("plan contains a secret (%q)", s)
		}
	}
}

// Default profile, UEFI, LUKS: erase the NVMe disk.
func TestGoldenDefaultUEFILUKS(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{}
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	golden(t, "default-uefi-luks.plan", plan)
	checkNoSecrets(t, plan)
	for _, want := range []string{
		"$ sfdisk --wipe always --wipe-partitions always /dev/nvme0n1 <<'EOF'",
		"$ cryptsetup luksFormat --batch-mode --type luks2 --pbkdf argon2id --label arctic-root --key-file - /dev/nvme0n1p4 < [secret: disk passphrase]",
		"$ efibootmgr --create --disk /dev/nvme0n1 --part 2 --label 'Arctic Linux' --loader '\\EFI\\fedora\\shimx64.efi'",
		"FLATPAK_SYSTEM_DIR=/mnt/var/lib/flatpak",
		"$ chroot /mnt dnf copr enable -y lihaohong/yazi",
		"$ useradd --root /mnt --create-home --user-group --groups wheel --shell /bin/zsh --comment 'Arctic User' --password [secret: password hash] arctic-user",
	} {
		if !strings.Contains(plan, want) {
			t.Errorf("plan lacks %q", want)
		}
	}
	for _, id := range []string{"zen", "zed", "kitty", "zsh", "yazi", "thunar", "collabora", "vlc"} {
		if rep.modules[id] != protocol.ModInstalled {
			t.Errorf("%s: %s", id, rep.modules[id])
		}
	}
	last := rep.progress[len(rep.progress)-1]
	if last.Percent != 100 || last.AppsDone != 8 || rep.modules["bash"] != "" {
		t.Errorf("last progress %+v", last)
	}
}

// Alternative profile, BIOS, no LUKS, alongside Windows on the NVMe disk.
func TestGoldenAlternativeBIOSAlongside(t *testing.T) {
	job := loadJob(t, "ci/alternative.toml", "bios")
	if job.Disk.Path != "/dev/nvme0n1" || job.Data.Disk.Mode != "alongside" || job.Data.Encryption.Enabled {
		t.Fatalf("job %+v %+v", job.Disk.Path, job.Data.Disk)
	}
	job.Secrets.LUKS = nil
	rec := &Recorder{}
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	golden(t, "alternative-bios-alongside.plan", plan)
	checkNoSecrets(t, plan)
	for _, want := range []string{
		"$ sfdisk --append /dev/nvme0n1 <<'EOF'",
		`type=21686148-6449-6E6F-744E-656564454649, name="BIOS boot"`,
		"$ chroot /mnt grub2-install --target=i386-pc /dev/nvme0n1",
		"GRUB_DISABLE_OS_PROBER=false",
		"$ chroot /mnt dnf remove -y --no-autoremove kitty kitty-shell-integration kitty-kitten zsh zsh-autosuggestions zsh-syntax-highlighting Thunar thunar-volman thunar-archive-plugin vlc vlc-gui-qt vlc-plugins-freeworld",
		"User=alt",
		"KEYMAP=de-nodeadkeys",
		"--shell /usr/bin/fish",
	} {
		if !strings.Contains(plan, want) {
			t.Errorf("plan lacks %q", want)
		}
	}
	for _, not := range []string{"cryptsetup", "wipefs", "efibootmgr", "mkfs.vfat"} {
		if strings.Contains(plan, "$ "+not) {
			t.Errorf("alongside/no-LUKS plan must not run %s", not)
		}
	}
}

func TestOptionalFailureSkipAndDefer(t *testing.T) {
	failZed := func(c Cmd) (string, error) {
		if c.Name == "flatpak" && len(c.Args) > 0 && c.Args[0] == "install" && strings.Contains(strings.Join(c.Args, " "), "dev.zed.Zed") {
			return "", errors.New("error: Unable to connect to dl.flathub.org: Could not connect: Connection timed out")
		}
		return DefaultRespond(c)
	}
	// Skip.
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{Respond: failZed}
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	if rep.modules["zed"] != protocol.ModSkipped || len(rep.attention) != 1 {
		t.Fatalf("zed %s, attention %v", rep.modules["zed"], rep.attention)
	}
	if strings.Contains(rec.Plan(), "editor=gtk-launch dev.zed.Zed") {
		t.Error("skipped editor still written to default-apps")
	}
	// Retry once, then defer (the unattended policy) → pending.json.
	job = loadJob(t, "defaults.toml", "uefi")
	rec = &Recorder{Respond: failZed}
	rep = newReporter()
	rep.decide = func(id string, n int) backend.Decision {
		if n == 1 {
			return backend.Retry
		}
		return backend.Defer
	}
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	if rep.modules["zed"] != protocol.ModDeferred || len(rep.attention) != 2 {
		t.Fatalf("zed %s attention %v", rep.modules["zed"], rep.attention)
	}
	if !strings.Contains(rec.Plan(), "write /mnt/var/lib/arctic/pending.json") {
		t.Error("no pending.json for the deferred module")
	}
}

func TestFallbackMethod(t *testing.T) {
	// The yazi COPR is down: the batch fails, then yazi falls back to Nix.
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if strings.Contains(c.String(), "copr enable") {
			return "", errors.New("copr unreachable")
		}
		return DefaultRespond(c)
	}}
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	if rep.modules["yazi"] != protocol.ModInstalled || len(rep.attention) != 0 {
		t.Fatalf("yazi %s attention %v", rep.modules["yazi"], rep.attention)
	}
	if !strings.Contains(rec.Plan(), "nix --extra-experimental-features 'nix-command flakes' --store /mnt profile add --profile /mnt/nix/var/nix/profiles/default 'github:NixOS/nixpkgs/5e2305d577ca00acbba631b05cb1094d172b29f3#yazi'") {
		t.Errorf("no nix fallback for yazi:\n%s", rec.Plan())
	}
}

func TestFatalFailureCleansUp(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "rsync" && strings.Contains(strings.Join(c.Args, " "), "--info=progress2") {
			return "", errors.New("No space left on device (28)")
		}
		return DefaultRespond(c)
	}}
	err := runPlan(t, job, rec, newReporter())
	if err == nil || !strings.HasPrefix(err.Error(), "copy: ") {
		t.Fatalf("want a copy error, got %v", err)
	}
	plan := rec.Plan()
	if !strings.Contains(plan, "$ umount -R /mnt") || !strings.Contains(plan, "$ cryptsetup close luks-") {
		t.Errorf("no cleanup after failure:\n%s", plan)
	}
}

func TestDiskInUse(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "lsblk" {
			return "\n/run/media/liveuser/Windows\n", nil
		}
		return DefaultRespond(c)
	}}
	err := runPlan(t, job, rec, newReporter())
	if err == nil || !strings.Contains(err.Error(), "is in use") {
		t.Fatalf("got %v", err)
	}
	if strings.Contains(rec.Plan(), "wipefs") {
		t.Error("wiped a disk that is in use")
	}
}

func TestParsers(t *testing.T) {
	if p, ok := ParsePercent("  1,234,567,890  45%  100.00MB/s    0:00:10 (xfr#1234, to-chk=100/5000)"); !ok || p != 45 {
		t.Errorf("rsync %d %v", p, ok)
	}
	if p, ok := ParsePercent("Installing 2/3… ████████   67%  3.1 MB/s  00:02"); !ok || p != 67 {
		t.Errorf("flatpak %d %v", p, ok)
	}
	if _, ok := ParsePercent("no numbers here"); ok {
		t.Error("false positive")
	}
	if d, n, ok := ParseDNF("[ 3/45] Installing kitty-0:0.47.1-1.fc44.x86_64"); !ok || d != 3 || n != 45 {
		t.Errorf("dnf %d/%d %v", d, n, ok)
	}
	// Progress meters stay out of the log tail; errors (even with a percent) stay in.
	for line, want := range map[string]bool{
		"  2,963,717,822  92%    5.10MB/s    0:09:14 (xfr#51636, to-chk=88/76683)":                                            true,
		"Installing 2/3… ████████   67%  3.1 MB/s  00:02":                                                                     true,
		`rsync: [receiver] rsync_xal_set: lsetxattr("/mnt/boot/efi","security.selinux") failed: Operation not supported (95)`: false,
		"error: download failed at 45%": false,
		"sent 2,966,895,947 bytes":      false,
	} {
		if got := IsProgressLine(line); got != want {
			t.Errorf("IsProgressLine(%q) = %v, want %v", line, got, want)
		}
	}
}

func TestRunnerLogKeepsErrorsNotProgress(t *testing.T) {
	var log strings.Builder
	r := &ExecRunner{Log: &log}
	script := `for i in $(seq 1 100); do printf '  %d,000  %d%%  1.0MB/s  0:00:01 (xfr#%d, to-chk=1/2)\r' $i $i $i; done
echo 'rsync: failed to set permissions on "/mnt/boot/efi": Operation not permitted (1)' >&2
printf '  100,000  100%%  1.0MB/s  0:00:01 (xfr#100, to-chk=0/2)\n'
exit 23`
	_, err := r.Run(context.Background(), Cmd{Name: "sh", Args: []string{"-c", script}, OnLine: func(string) {}})
	var ce *CmdError
	if !errors.As(err, &ce) {
		t.Fatalf("want a CmdError, got %v", err)
	}
	out := ce.Output
	if !strings.Contains(out, "Operation not permitted") {
		t.Errorf("the error line is missing:\n%s", out)
	}
	if n := strings.Count(out, "to-chk="); n != 1 {
		t.Errorf("want only the last progress line, got %d:\n%s", n, out)
	}
}

func TestRedact(t *testing.T) {
	c := Chroot("/mnt", Cmd{Name: "useradd", Args: []string{"--password", "$6$salt$hash", "noa"}, Redact: []int{1}, SecretLabel: "password hash"})
	if got := c.String(); got != "chroot /mnt useradd --password [secret: password hash] noa" {
		t.Errorf("got %s", got)
	}
	if c.Args[3] != "$6$salt$hash" {
		t.Errorf("the real argument must stay intact: %v", c.Args)
	}
}

func TestQuote(t *testing.T) {
	c := Cmd{Name: "efibootmgr", Args: []string{"--label", "Arctic Linux", `\EFI\fedora\shimx64.efi`, "it's"}, Env: []string{"A=b"}}
	if got := c.String(); got != `A=b efibootmgr --label 'Arctic Linux' '\EFI\fedora\shimx64.efi' 'it'\''s'` {
		t.Errorf("got %s", got)
	}
}
