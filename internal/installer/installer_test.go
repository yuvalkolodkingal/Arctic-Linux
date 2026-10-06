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
		"browser=epiphany",
		"editor=featherpad",
		"terminal=foot",
		"files=pcmanfm",
		"$ useradd --root /mnt --create-home --user-group --groups wheel --shell /usr/bin/fish --comment 'Arctic User' --password [secret: password hash] arctic-user",
	} {
		if !strings.Contains(plan, want) {
			t.Errorf("plan lacks %q", want)
		}
	}
	for _, id := range []string{"gnome-web", "featherpad", "foot", "fish", "pcmanfm", "celluloid"} {
		if rep.modules[id] != protocol.ModInstalled {
			t.Errorf("%s: %s", id, rep.modules[id])
		}
	}
	last := rep.progress[len(rep.progress)-1]
	if last.Percent != 100 || last.AppsDone != 6 || rep.modules["bash"] != "" {
		t.Errorf("last progress %+v", last)
	}
}

// Fresh defaults come from the image copy. Failed online package checks must
// still leave usable app roles, while genuinely downloaded codecs/themes defer.
func TestFreshDefaultsCompleteOffline(t *testing.T) {
	for _, profileName := range []string{"defaults.toml", "ci/offline.toml"} {
		t.Run(profileName, func(t *testing.T) {
			job := loadJob(t, profileName, "uefi")
			job.Offline = true
			rec := &Recorder{Respond: func(c Cmd) (string, error) {
				if c.Name == "flatpak" && len(c.Args) > 0 && (c.Args[0] == "install" || c.Args[0] == "remote-add") {
					return "", errors.New("network is unreachable")
				}
				if c.Name == "chroot" && len(c.Args) > 2 && c.Args[1] == "dnf" && (c.Args[2] == "install" || c.Args[2] == "swap") {
					return "", errors.New("network is unreachable")
				}
				return DefaultRespond(c)
			}}
			rep := newReporter()
			rep.decide = func(string, int) backend.Decision { return backend.Defer }
			if err := runPlan(t, job, rec, rep); err != nil {
				t.Fatal(err)
			}
			plan := rec.Plan()
			for _, id := range []string{"gnome-web", "featherpad", "foot", "fish", "pcmanfm", "celluloid"} {
				if !job.Catalog.Modules[id].InLiveImage || rep.modules[id] != protocol.ModInstalled {
					t.Errorf("%s: not preserved as a preloaded app (%s)", id, rep.modules[id])
				}
				if strings.Contains(plan, `"id": "`+id+`"`) {
					t.Errorf("preloaded app %s was deferred", id)
				}
			}
			for _, want := range []string{
				"browser=epiphany", "editor=featherpad", "terminal=foot", "files=pcmanfm",
				"x-scheme-handler/https=org.gnome.Epiphany.desktop", "inode/directory=pcmanfm.desktop",
				"video/mp4=io.github.celluloid_player.Celluloid.desktop",
				`"id": "codecs"`, `"id": "adw-gtk3-flatpak"`, `"id": "adw-gtk3-dark-flatpak"`,
				"write /mnt/var/lib/arctic/pending.json", "$ usermod --root /mnt --lock root",
			} {
				if !strings.Contains(plan, want) {
					t.Errorf("offline plan lacks %q", want)
				}
			}
			last := rep.progress[len(rep.progress)-1]
			if last.Percent != 100 || last.AppsDone != 6 {
				t.Errorf("offline install did not complete: %+v", last)
			}
			checkNoSecrets(t, plan)
		})
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
		"$ chroot /mnt dnf remove -y --no-autoremove epiphany featherpad pcmanfm xarchiver celluloid",
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
	// Removing the unselected file manager must keep shared archive/recovery tools.
	for _, command := range rec.Commands() {
		if !strings.Contains(command, "dnf remove") {
			continue
		}
		for _, field := range strings.Fields(command) {
			for _, helper := range []string{"7zip", "zip", "unzip", "tar", "xz", "bzip2", "zstd", "cpio"} {
				if field == helper {
					t.Errorf("fresh target removes shared archive tool %s: %s", helper, command)
				}
			}
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
	job.Data.Apps.Selection["editor"] = []string{"zed"} // old editor remains selectable
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
	job.Data.Apps.Selection["editor"] = []string{"zed"}
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
	job.Data.Apps.Selection["files"] = []string{"pcmanfm", "yazi"} // optional TUI retains Nix fallback
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

func TestLivePackagesRemovedWithoutScriptlets(t *testing.T) {
	// Real hardware, SELinux enforcing: the live packages' %preun scriptlets fail (exit 127).
	// The install goes on: their units are disabled and the packages removed without scripts.
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if s := c.String(); c.Name == "chroot" && strings.Contains(s, "dnf remove") && strings.Contains(s, "arctic-live") && !strings.Contains(s, "tsflags=noscripts") {
			return "", errors.New("exit status 1")
		}
		return DefaultRespond(c)
	}}
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	relabel := strings.Index(plan, "$ setfiles ")
	remove := strings.Index(plan, "dnf remove -y --no-autoremove arctic-live")
	if relabel < 0 || remove < 0 || relabel > remove {
		t.Error("the target is not relabelled before the first command that runs inside it")
	}
	for _, want := range []string{
		"$ systemctl --root=/mnt disable livesys.service livesys-late.service arcticd.socket arcticd.service",
		"$ chroot /mnt dnf remove -y --no-autoremove --setopt=tsflags=noscripts arctic-live livesys-scripts arctic-installer dracut-live dracut-kiwi-live",
	} {
		if !strings.Contains(plan, want) {
			t.Errorf("plan lacks %q", want)
		}
	}
	// Whole-system relabels (with the API file system excludes); snapper's files get their own.
	// setfiles doesn't cross mount points: every subvolume and /boot must be named.
	if !strings.Contains(plan, "file_contexts /mnt /mnt/home /mnt/var/log /mnt/nix /mnt/boot\n") {
		t.Error("setfiles doesn't relabel every mounted subvolume and /boot")
	}
	if n := strings.Count(plan, "$ setfiles -F -r /mnt -e "); n != 2 {
		t.Errorf("want two relabels (after the copy and at the end), got %d", n)
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
	// A partition mounted somewhere the installer doesn't own: stop before touching the disk.
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "lsblk" {
			return `{"blockdevices": [{"path": "/dev/nvme0n1", "type": "disk", "mountpoints": [null], "children": [
				{"path": "/dev/nvme0n1p3", "type": "part", "mountpoints": ["/home/liveuser/win"]}]}]}`, nil
		}
		return DefaultRespond(c)
	}}
	err := runPlan(t, job, rec, newReporter())
	if err == nil || !strings.Contains(err.Error(), "is in use (/dev/nvme0n1p3 is mounted at /home/liveuser/win)") {
		t.Fatalf("got %v", err)
	}
	if strings.Contains(rec.Plan(), "wipefs") || strings.Contains(rec.Plan(), "$ umount /home") {
		t.Errorf("touched a disk that is in use:\n%s", rec.Plan())
	}
}

// An md array that udev assembled (with LVM on it), swap and a file-manager automount are
// released before the disk is erased; the array is stopped once, after the LV above it.
func TestReleaseDisk(t *testing.T) {
	busy := `{"blockdevices": [{"path": "/dev/nvme0n1", "type": "disk", "mountpoints": [null], "children": [
		{"path": "/dev/nvme0n1p1", "type": "part", "mountpoints": ["/run/media/liveuser/DATA"]},
		{"path": "/dev/nvme0n1p2", "type": "part", "mountpoints": ["[SWAP]"]},
		{"path": "/dev/nvme0n1p3", "type": "part", "mountpoints": [null], "children": [
			{"path": "/dev/md127", "type": "raid1", "mountpoints": [null], "children": [
				{"path": "/dev/mapper/vg-data", "type": "lvm", "mountpoints": [null]}]}]},
		{"path": "/dev/nvme0n1p4", "type": "part", "mountpoints": [null], "children": [
			{"path": "/dev/md127", "type": "raid1", "mountpoints": [null], "children": [
				{"path": "/dev/mapper/vg-data", "type": "lvm", "mountpoints": [null]}]}]}]}]}`
	calls := 0
	respond := func(stillBusy bool) func(c Cmd) (string, error) {
		return func(c Cmd) (string, error) {
			if c.Name == "lsblk" {
				calls++
				if calls == 1 || stillBusy {
					return busy, nil
				}
			}
			return DefaultRespond(c)
		}
	}
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{Respond: respond(false)}
	if err := runPlan(t, job, rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	cmds := strings.Join(rec.Commands(), "\n")
	want := []string{
		"$ lsblk --json --tree --output PATH,TYPE,MOUNTPOINTS /dev/nvme0n1",
		"$ umount /run/media/liveuser/DATA",
		"$ swapoff /dev/nvme0n1p2",
		"$ dmsetup remove /dev/mapper/vg-data",
		"$ mdadm --stop /dev/md127",
		"$ udevadm settle --timeout=15",
		"$ lsblk --json --tree --output PATH,TYPE,MOUNTPOINTS /dev/nvme0n1",
		"$ wipefs --all --force /dev/nvme0n1",
	}
	if !strings.HasPrefix(cmds, strings.Join(want, "\n")) {
		t.Errorf("release sequence:\n%s", cmds)
	}
	if strings.Count(cmds, "mdadm --stop") != 1 {
		t.Errorf("the array must be stopped once:\n%s", cmds)
	}
	// Still busy after that: stop with a clear message before wipefs.
	calls = 0
	rec = &Recorder{Respond: respond(true)}
	err := runPlan(t, loadJob(t, "defaults.toml", "uefi"), rec, newReporter())
	if err == nil || !strings.Contains(err.Error(), "still in use") {
		t.Fatalf("got %v", err)
	}
	if strings.Contains(rec.Plan(), "wipefs") {
		t.Error("wiped a disk that is still in use")
	}
}

// A failed alongside install removes the partitions it added (and only those).
func TestAlongsideFailureRemovesItsPartitions(t *testing.T) {
	job := loadJob(t, "ci/alternative.toml", "bios")
	job.Secrets.LUKS = nil
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "mkfs.ext4" {
			return "", errors.New("mkfs failed")
		}
		return DefaultRespond(c)
	}}
	err := runPlan(t, job, rec, newReporter())
	if err == nil || !strings.HasPrefix(err.Error(), "disk: ") {
		t.Fatalf("got %v", err)
	}
	plan := rec.Plan()
	for _, want := range []string{"$ wipefs --all /dev/nvme0n1p5", "$ wipefs --all /dev/nvme0n1p7", "$ sfdisk --delete /dev/nvme0n1 5 6 7"} {
		if !strings.Contains(plan, want) {
			t.Errorf("cleanup lacks %q:\n%s", want, plan)
		}
	}
	// sfdisk itself failed: nothing was added, nothing is deleted.
	job = loadJob(t, "ci/alternative.toml", "bios")
	job.Secrets.LUKS = nil
	rec = &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "sfdisk" {
			return "", errors.New("Sector 644771840 already used")
		}
		return DefaultRespond(c)
	}}
	if err := runPlan(t, job, rec, newReporter()); err == nil {
		t.Fatal("want an error")
	}
	if strings.Contains(rec.Plan(), "--delete") || strings.Contains(rec.Plan(), "$ wipefs") {
		t.Errorf("deleted partitions it did not create:\n%s", rec.Plan())
	}
}

// A failure after the bootloader step removes the firmware boot entry the run created.
func TestLateFailureRemovesBootEntry(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		switch c.Name {
		case "efibootmgr":
			return "BootCurrent: 0001\nTimeout: 0 seconds\nBootOrder: 0004,0000,0001\nBoot0000* Windows Boot Manager\tHD(1,GPT,…)\nBoot0001* UEFI QEMU DVD-ROM\nBoot0004* Arctic Linux\tHD(2,GPT,…)/File(\\EFI\\fedora\\shimx64.efi)\n", nil
		case "useradd":
			return "", errors.New("useradd: group 'man' already exists")
		}
		return DefaultRespond(c)
	}}
	err := runPlan(t, job, rec, newReporter())
	if err == nil || !strings.HasPrefix(err.Error(), "finalize: ") {
		t.Fatalf("got %v", err)
	}
	if !strings.Contains(rec.Plan(), "$ efibootmgr --delete-bootnum --bootnum 0004") {
		t.Errorf("boot entry not removed:\n%s", rec.Plan())
	}
	if got := newBootEntry("BootOrder: 0000,0004\nBoot0000* Windows Boot Manager\n", "Arctic Linux"); got != "" {
		t.Errorf("took someone else's entry: %q", got)
	}
}

func TestNixSocketFailureStopsBeforeServiceDisable(t *testing.T) {
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.String() == "systemctl --root=/mnt enable nix-daemon.socket" {
			return "", errors.New("nix-daemon.socket is missing")
		}
		return DefaultRespond(c)
	}}
	err := runPlan(t, loadJob(t, "defaults.toml", "uefi"), rec, newReporter())
	if err == nil || !strings.HasPrefix(err.Error(), "configure: ") || !strings.Contains(err.Error(), "nix-daemon.socket") {
		t.Fatalf("required Nix socket failure must abort configuration, got %v", err)
	}
	plan := rec.Plan()
	if strings.Contains(plan, "$ systemctl --root=/mnt disable nix-daemon.service") ||
		strings.Contains(plan, "$ systemctl --root=/mnt set-default graphical.target") {
		t.Errorf("handed off a partially configured Nix service:\n%s", plan)
	}
}

func TestNixServiceDisableFailureRetainsSocket(t *testing.T) {
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.String() == "systemctl --root=/mnt disable nix-daemon.service" {
			return "", errors.New("cannot disable eager daemon startup")
		}
		return DefaultRespond(c)
	}}
	if err := runPlan(t, loadJob(t, "defaults.toml", "uefi"), rec, newReporter()); err != nil {
		t.Fatalf("a disable failure must retain functional Nix and finish installation: %v", err)
	}
	plan := rec.Plan()
	enable := strings.Index(plan, "$ systemctl --root=/mnt enable nix-daemon.socket")
	disable := strings.Index(plan, "$ systemctl --root=/mnt disable nix-daemon.service")
	handoff := strings.Index(plan, "$ systemctl --root=/mnt set-default graphical.target")
	if enable < 0 || !(enable < disable && disable < handoff) {
		t.Errorf("socket enable must precede service disable and handoff:\n%s", plan)
	}
}

// Non-Latin layouts get "us" first plus a switch, and a Latin console keymap for the disk
// passphrase at boot; empty values are never written (mango rejects "key=").
func TestKeyboardFiles(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	job.Data.Keyboard.Layout, job.Data.Keyboard.Variant = "ru", ""
	rec := &Recorder{}
	if err := runPlan(t, job, rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	for _, want := range []string{
		"write /mnt/etc/vconsole.conf (0644)\n    | KEYMAP=ru\n    | XKBLAYOUT=us,ru\n    | XKBOPTIONS=grp:alt_shift_toggle\n",
		"    | xkb_rules_layout=us,ru\n    | xkb_rules_options=grp:alt_shift_toggle\n",
		"keyboardLayout=us\n",
	} {
		if !strings.Contains(plan, want) {
			t.Errorf("plan lacks %q", want)
		}
	}
	if strings.Count(plan, "xkb_rules_layout=us,ru") != 2 {
		t.Error("mango and the login screen must both get the layouts")
	}
	if strings.Contains(plan, "xkb_rules_variant=\n") || strings.Contains(plan, "XKBVARIANT=\n") {
		t.Error("empty variant written")
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

// Older images may ship Zen as a Flatpak: preserve detection and selection of a
// copied optional browser even though fresh images default to GNOME Web.
func TestPreinstalledFlatpakFromTheImage(t *testing.T) {
	zenInImage := func(p string) bool {
		return DefaultExists(p) || p == "/mnt/var/lib/flatpak/app/app.zen_browser.zen"
	}
	// Ticked: kept from the copy, never downloaded, reported installed.
	job := loadJob(t, "ci/default.toml", "uefi")
	job.Data.Apps.Selection["browser"] = []string{"zen"}
	rec := &Recorder{ExistsFn: zenInImage}
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	for _, c := range rec.Commands() {
		if strings.Contains(c, "install") && strings.Contains(c, "app.zen_browser.zen") {
			t.Errorf("downloads Zen although the image has it: %s", c)
		}
	}
	if rep.modules["zen"] != protocol.ModInstalled {
		t.Errorf("zen: %q, want installed", rep.modules["zen"])
	}
	if !strings.Contains(rec.Plan(), "browser=gtk-launch app.zen_browser.zen") {
		t.Error("Zen is not the default browser")
	}

	// Unticked (Firefox instead): uninstalled from the target with its unused runtimes.
	job = loadJob(t, "ci/default.toml", "uefi")
	job.Data.Apps.Selection["browser"] = []string{"firefox"}
	rec = &Recorder{ExistsFn: zenInImage}
	if err := runPlan(t, job, rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	for _, want := range []string{
		"flatpak uninstall --system -y --noninteractive app.zen_browser.zen",
		"flatpak uninstall --system -y --noninteractive --unused",
	} {
		if !strings.Contains(plan, want) {
			t.Errorf("plan lacks %q", want)
		}
	}
	if strings.Contains(plan, "browser=gtk-launch app.zen_browser.zen") {
		t.Error("Zen is still the default browser")
	}
}

// Snapper's root configuration is created last: after every dnf run in the new system and after
// the final relabel, so the install itself leaves no snapshots and /.snapshots gets labelled.
// Without snapper, or when it fails, the install still succeeds.
func TestSnapperSetUpLast(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{}
	if err := runPlan(t, job, rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	cmds := rec.Commands()
	index := func(prefix string, last bool) int {
		found := -1
		for i, c := range cmds {
			if strings.HasPrefix(c, prefix) {
				found = i
				if !last {
					break
				}
			}
		}
		return found
	}
	create := index("$ chroot /mnt snapper --no-dbus -c root create-config /", false)
	set := index("$ chroot /mnt snapper --no-dbus -c root set-config NUMBER_CLEANUP=yes NUMBER_LIMIT=10 NUMBER_LIMIT_IMPORTANT=5 TIMELINE_CREATE=no", false)
	label := index("$ setfiles -F -r /mnt /mnt/etc/selinux/targeted/contexts/files/file_contexts /mnt/.snapshots /mnt/etc/snapper /mnt/etc/sysconfig/snapper", false)
	relabel := index("$ setfiles -F -r /mnt -e ", true)
	dnf := index("$ chroot /mnt dnf", true)
	umount := index("$ umount --recursive /mnt", false)
	if create < 0 || set < 0 || label < 0 {
		t.Fatalf("snapper not set up:\n%s", strings.Join(cmds, "\n"))
	}
	if !(dnf < relabel && relabel < create && create < set && set < label && label < umount) {
		t.Errorf("order: last dnf %d, final relabel %d, create-config %d, set-config %d, label %d, umount %d", dnf, relabel, create, set, label, umount)
	}
	// Snapshots stay root's: ALLOW_GROUPS would let any wheel process create, delete and
	// undochange snapshots through snapperd without a password.
	if strings.Contains(cmds[set], "ALLOW_") || strings.Contains(cmds[set], "SYNC_ACL") {
		t.Errorf("snapper grants access to non-root users: %s", cmds[set])
	}

	// Not in the image: nothing to set up, the install goes on.
	rec = &Recorder{ExistsFn: func(p string) bool { return p != "/mnt/usr/bin/snapper" && DefaultExists(p) }}
	rep := newReporter()
	if err := runPlan(t, loadJob(t, "defaults.toml", "uefi"), rec, rep); err != nil {
		t.Fatal(err)
	}
	if strings.Contains(rec.Plan(), "snapper") {
		t.Error("runs snapper although it isn't installed")
	}
	if !strings.Contains(strings.Join(rep.logs, "\n"), "snapper isn't in the new system") {
		t.Errorf("no log line about snapper: %v", rep.logs)
	}

	// create-config fails (say, not btrfs): logged, set-config skipped, the install finishes.
	rec = &Recorder{Respond: func(c Cmd) (string, error) {
		if strings.Contains(c.String(), "snapper --no-dbus -c root create-config") {
			return "", errors.New("creating btrfs subvolume .snapshots failed")
		}
		return DefaultRespond(c)
	}}
	rep = newReporter()
	if err := runPlan(t, loadJob(t, "defaults.toml", "uefi"), rec, rep); err != nil {
		t.Fatalf("a snapper failure must not fail the install: %v", err)
	}
	if strings.Contains(rec.Plan(), "set-config") || !strings.Contains(rec.Plan(), "$ umount --recursive /mnt") {
		t.Errorf("after a failed create-config: %s", rec.Plan())
	}

	// Labelling snapper's files fails: the first boot relabels instead.
	rec = &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "setfiles" && strings.Contains(c.String(), "/mnt/.snapshots") {
			return "", errors.New("exit status 1")
		}
		return DefaultRespond(c)
	}}
	if err := runPlan(t, loadJob(t, "defaults.toml", "uefi"), rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(rec.Plan(), "write /mnt/.autorelabel") {
		t.Error("no /.autorelabel after snapper's files couldn't be labelled")
	}
}
