package installer

import (
	"errors"
	"strings"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/mock"
	"github.com/yuvalkolodkingal/o-tism/internal/profile"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/modules"
	"github.com/yuvalkolodkingal/o-tism/profiles"
)

const testMOKCode = "48210937"

// loadHWJob is loadJob on a fixture machine: the catalog is marked with its hardware before
// the profile's defaults are taken, as the engine does.
func loadHWJob(t *testing.T, profilePath, firmware, fixture string, secureBoot bool) *backend.Job {
	t.Helper()
	cat, err := catalog.Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	h, ok := hw.Fixture(fixture, secureBoot)
	if !ok {
		t.Fatalf("no fixture %q", fixture)
	}
	cat.MarkDetected(h)
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
	job := &backend.Job{Data: d, Disk: disk, Firmware: firmware, Catalog: cat, Hardware: h,
		Secrets: &backend.Secrets{LUKS: []byte(testLUKS), Password: []byte(testPassword)}, LogPath: "/var/log/arctic-install/engine.log"}
	if job.NeedsMOK() {
		job.MOKCode = testMOKCode
	}
	return job
}

func driverOutcome(job *backend.Job) map[string]string {
	out := map[string]string{}
	for _, d := range job.Outcome.Drivers {
		out[d.ID] = d.Status
	}
	return out
}

// Default profile on an NVIDIA hybrid laptop (Intel Iris Xe + RTX 4060), UEFI with Secure
// Boot, LUKS: the NVIDIA driver and Intel's media driver are installed, NVIDIA's is built for
// the kernel, the kernel arguments are set and the akmods key is queued for enrolment.
func TestGoldenNVIDIASecureBootUEFI(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "uefi", "nvidia-laptop", true)
	if got := job.Data.Apps.Selection["drivers"]; strings.Join(got, ",") != "nvidia,intel-media" {
		t.Fatalf("default drivers %v", got)
	}
	rec := &Recorder{}
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	golden(t, "nvidia-secureboot-uefi.plan", plan)
	checkNoSecrets(t, plan)
	if strings.Contains(plan, testMOKCode) {
		t.Error("plan contains the one-time code")
	}
	want := []string{
		"$ chroot /mnt dnf install -y akmods",
		"$ chroot /mnt kmodgenca -a",
		"akmod-nvidia xorg-x11-drv-nvidia-cuda libva-nvidia-driver intel-media-driver",
		"$ chroot /mnt dnf swap -y --allowerasing libva-intel-media-driver intel-media-driver",
		"$ chroot /mnt akmods --force --kernels 6.17.8-300.fc44.x86_64 --akmod nvidia",
		"$ chroot /mnt modinfo -k 6.17.8-300.fc44.x86_64 -F version nvidia",
		"$ chroot /mnt grubby --update-kernel=ALL '--args=rd.driver.blacklist=nouveau,nova_core modprobe.blacklist=nouveau,nova_core nvidia-drm.modeset=1'",
		"$ chroot /mnt mokutil --import /etc/pki/akmods/certs/public_key.der --hash-file /dev/stdin < [secret: one-time code hash]",
	}
	for _, w := range want {
		if !strings.Contains(plan, w) {
			t.Errorf("plan lacks %q", w)
		}
	}
	// The iGPU draws the screen, so the LUKS prompt needs no simpledrm argument.
	if strings.Contains(plan, "plymouth.use-simpledrm") {
		t.Error("simpledrm argument on a hybrid laptop")
	}
	// Order: key before the driver transaction, build after it, arguments and key last.
	idx := func(s string) int { return strings.Index(plan, s) }
	if !(idx("kmodgenca -a") < idx("akmod-nvidia xorg-x11-drv-nvidia-cuda") &&
		idx("akmod-nvidia xorg-x11-drv-nvidia-cuda") < idx("akmods --force") &&
		idx("akmods --force") < idx("grubby --update-kernel=ALL") &&
		idx("grubby --update-kernel=ALL") < idx("mokutil --import")) {
		t.Error("driver steps out of order")
	}
	if got := driverOutcome(job); got["nvidia"] != protocol.DriverInstalled || got["intel-media"] != protocol.DriverInstalled {
		t.Errorf("drivers %v", got)
	}
	if job.Outcome.MOK != backend.MOKRequested {
		t.Errorf("MOK %q", job.Outcome.MOK)
	}
	// Drivers aren't apps: 8 apps, no module events for drivers.
	if _, ok := rep.modules["nvidia"]; ok {
		t.Error("module event for a driver")
	}
	last := rep.progress[len(rep.progress)-1]
	if last.AppsDone != 8 || last.AppsTotal != 8 {
		t.Errorf("last progress %+v", last)
	}
}

// The MOK hash handed to mokutil is what mokutil --generate-hash prints for the code.
func TestMOKHash(t *testing.T) {
	in := New(&Recorder{}, &backend.Job{MOKCode: "12345678"}, newReporter(), Options{Salt: "testsalt"})
	h, err := in.mokHash()
	if err != nil {
		t.Fatal(err)
	}
	// crypt("12345678", "$6$testsalt") (glibc, Python crypt.crypt).
	want, _ := SHA512Crypt([]byte("12345678"), "$6$testsalt")
	if h != want || !strings.HasPrefix(h, "$6$testsalt$") || strings.Contains(h, "rounds=") {
		t.Errorf("hash %q", h)
	}
}

// NVIDIA-only desktop without Secure Boot, LUKS: the NVIDIA card drives the passphrase
// prompt, so plymouth gets simpledrm; no key enrolment.
func TestNVIDIADesktopNoSecureBoot(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "uefi", "nvidia-desktop", false)
	rec := &Recorder{}
	if err := runPlan(t, job, rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	if !strings.Contains(plan, "nvidia-drm.modeset=1 plymouth.use-simpledrm=1'") {
		t.Error("no simpledrm argument for an NVIDIA boot display with LUKS")
	}
	if strings.Contains(plan, "mokutil") || job.MOKCode != "" || job.Outcome.MOK != backend.MOKNone {
		t.Error("key enrolment without Secure Boot")
	}
	if !strings.Contains(plan, "kmodgenca -a") {
		t.Error("the key is created anyway (akmods-keygen would at boot)")
	}
}

// Pascal gets the 580 series; Kepler, a VM and an AMD card get no NVIDIA driver.
func TestDriverSelectionByGeneration(t *testing.T) {
	cases := map[string]string{
		"pascal":         "nvidia-580xx",
		"maxwell":        "nvidia-580xx",
		"kepler":         "",
		"vm":             "",
		"amd":            "amd-video",
		"broadcom-mac":   "broadcom-wl", // Haswell: i965, not the media driver
		"intel":          "intel-media",
		"nvidia-desktop": "nvidia",
		"none":           "",
	}
	for fx, want := range cases {
		job := loadHWJob(t, "defaults.toml", "uefi", fx, false)
		if got := strings.Join(job.Data.Apps.Selection["drivers"], ","); got != want {
			t.Errorf("%s: drivers %q, want %q", fx, got, want)
		}
	}
}

// Offline: the drivers go to pending.json with their akmod and kernel arguments, and the key's
// hash is kept for arctic-firstboot. Nothing driver-related runs during the install.
func TestOfflineDriversDeferred(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "uefi", "nvidia-laptop", true)
	job.Offline = true
	rec := &Recorder{}
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	for _, not := range []string{"akmod-nvidia", "kmodgenca", "akmods --force", "grubby --update-kernel", "mokutil"} {
		if strings.Contains(plan, "$ chroot /mnt "+not) || strings.Contains(plan, " "+not+" ") && strings.Contains(plan, "$ chroot /mnt dnf install -y "+not) {
			t.Errorf("offline plan runs %s", not)
		}
	}
	for _, w := range []string{
		"$ install -D -m 0600 /dev/stdin /mnt/var/lib/arctic/mok.hash < [secret: one-time code hash]",
		`"mok_hash": "/var/lib/arctic/mok.hash"`,
		`"name": "nvidia"`,
		`"module": "nvidia"`,
		`"rd.driver.blacklist=nouveau,nova_core",`,
		`"id": "intel-media"`,
	} {
		if !strings.Contains(plan, w) {
			t.Errorf("plan lacks %q", w)
		}
	}
	if got := driverOutcome(job); got["nvidia"] != protocol.DriverDeferred || got["intel-media"] != protocol.DriverDeferred {
		t.Errorf("drivers %v", got)
	}
	if job.Outcome.MOK != backend.MOKRequested {
		t.Errorf("MOK %q", job.Outcome.MOK)
	}
	checkNoSecrets(t, plan)
}

// The build fails: Skip removes the driver again and sets no arguments or key; Defer
// (unattended) leaves it to akmods at boot and still sets them.
func TestDriverBuildFailure(t *testing.T) {
	failBuild := func(c Cmd) (string, error) {
		if c.Name == "chroot" && len(c.Args) > 1 && c.Args[1] == "modinfo" {
			return "", errors.New("modinfo: ERROR: Module nvidia not found.")
		}
		return DefaultRespond(c)
	}
	job := loadHWJob(t, "defaults.toml", "uefi", "nvidia-laptop", true)
	rec := &Recorder{Respond: failBuild}
	rep := newReporter() // skips
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	if len(rep.attention) != 1 || rep.attention[0] != "nvidia" {
		t.Fatalf("attention %v", rep.attention)
	}
	if !strings.Contains(plan, "$ chroot /mnt dnf remove -y akmod-nvidia xorg-x11-drv-nvidia-cuda libva-nvidia-driver") {
		t.Error("skipped driver not removed")
	}
	if strings.Contains(plan, "--args=") || strings.Contains(plan, "mokutil") {
		t.Error("arguments or key for a skipped driver")
	}
	if got := driverOutcome(job); got["nvidia"] != protocol.DriverSkipped || got["intel-media"] != protocol.DriverInstalled {
		t.Errorf("drivers %v", got)
	}

	job = loadHWJob(t, "defaults.toml", "uefi", "nvidia-laptop", true)
	rec = &Recorder{Respond: failBuild}
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
	plan = rec.Plan()
	if strings.Count(plan, "akmods --force") != 2 || !strings.Contains(plan, "mokutil --import") {
		t.Error("deferred build: retry and key expected")
	}
	// No arguments until the module exists (nouveau keeps the screen if akmods fails at boot
	// too); the %posttrans blacklist is taken off again, and arctic-firstboot finishes it.
	if strings.Contains(plan, "--args=") {
		t.Error("kernel arguments for a driver that isn't built")
	}
	for _, w := range []string{
		"$ chroot /mnt grubby --update-kernel=ALL '--remove-args=rd.driver.blacklist=nouveau,nova_core modprobe.blacklist=nouveau,nova_core nvidia-drm.modeset=1'",
		`"akmod": {`,
		`"id": "nvidia"`,
	} {
		if !strings.Contains(plan, w) {
			t.Errorf("plan lacks %q", w)
		}
	}
	if strings.Contains(plan, `"mok_hash"`) {
		t.Error("key already queued, yet its hash is kept for first boot")
	}
	if got := driverOutcome(job); got["nvidia"] != protocol.DriverDeferred {
		t.Errorf("drivers %v", got)
	}
}

// Default profile on an AMD desktop (Radeon RX 7900): the freeworld media drivers are installed
// next to Fedora's VA driver, never swapped for it (F44's mesa-dri-drivers provides
// mesa-va-drivers, so dnf swap would erase it and the desktop); the Vulkan one is swapped only
// when that exact package is installed.
func TestGoldenAMDDesktop(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "uefi", "amd", false)
	if got := strings.Join(job.Data.Apps.Selection["drivers"], ","); got != "amd-video" {
		t.Fatalf("default drivers %q", got)
	}
	rec := &Recorder{}
	if err := runPlan(t, job, rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	golden(t, "amd-desktop-uefi.plan", plan)
	if strings.Contains(plan, "swap -y --allowerasing mesa-va-drivers") {
		t.Error("mesa-va-drivers is swapped")
	}
	for _, w := range []string{
		"$ chroot /mnt rpm -q --quiet mesa-vulkan-drivers\n$ chroot /mnt dnf swap -y --allowerasing mesa-vulkan-drivers mesa-vulkan-drivers-freeworld",
		"mesa-va-drivers-freeworld mesa-vulkan-drivers-freeworld",
	} {
		if !strings.Contains(plan, w) {
			t.Errorf("plan lacks %q", w)
		}
	}
	for _, not := range []string{"akmods", "kmodgenca", "grubby --update-kernel", "mokutil"} {
		if strings.Contains(plan, "$ chroot /mnt "+not) {
			t.Errorf("AMD plan runs %s", not)
		}
	}
	if got := driverOutcome(job); got["amd-video"] != protocol.DriverInstalled {
		t.Errorf("drivers %v", got)
	}
}

// A swap whose package isn't installed under that exact name is left out.
func TestSwapOnlyInstalledPackage(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "uefi", "amd", false)
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "chroot" && len(c.Args) > 4 && c.Args[1] == "rpm" && c.Args[4] == "mesa-vulkan-drivers" {
			return "", errors.New("package mesa-vulkan-drivers is not installed")
		}
		return DefaultRespond(c)
	}}
	if err := runPlan(t, job, rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	if plan := rec.Plan(); strings.Contains(plan, "swap -y --allowerasing mesa-vulkan-drivers") {
		t.Error("swapped a package that isn't installed")
	}
}

// Old and new AMD cards: R100–R500 (no VA-API) get no media driver.
func TestAMDVideoDetection(t *testing.T) {
	cat, err := catalog.Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	m := cat.Modules["amd-video"]
	cases := map[string]bool{
		"744c": true, "7550": true, "73bf": true, "67df": true, "6798": true, "1638": true,
		"15bf": true, "1114": true, "9874": true, "9440": true, "6f00": true,
		"5159": false, "4150": false, "7142": false, "71c5": false, "791e": false, "796e": false, "3e50": false,
	}
	for dev, want := range cases {
		got := false
		for _, d := range m.Detect {
			if d.Matches(hw.PCIDevice{Vendor: "1002", Device: dev, Class: "0300"}) {
				got = true
			}
		}
		if got != want {
			t.Errorf("1002:%s detected %v, want %v", dev, got, want)
		}
	}
}

// Two kernels in the new system: the development files are asked for both by version; when
// that fails (the version left the repositories), the newest complete kernel is installed
// with them, and the driver is built for the kernel that has kernel-devel only.
func TestAkmodsKernelDevel(t *testing.T) {
	const old, cur = "6.17.8-300.fc44.x86_64", "7.2.7-200.fc44.x86_64"
	job := loadHWJob(t, "defaults.toml", "uefi", "nvidia-desktop", false)
	rec := &Recorder{
		GlobFn: func(p string) []string {
			if strings.HasSuffix(p, "/lib/modules/*") {
				root := strings.TrimSuffix(p, "/lib/modules/*")
				return []string{root + "/lib/modules/" + cur, root + "/lib/modules/" + old}
			}
			return DefaultGlob(p)
		},
		ExistsFn: func(p string) bool {
			if strings.Contains(p, "/usr/src/kernels/") {
				return strings.Contains(p, cur)
			}
			return DefaultExists(p)
		},
		Respond: func(c Cmd) (string, error) {
			if c.Name == "chroot" && strings.Contains(strings.Join(c.Args, " "), "kernel-devel-matched-") {
				return "", errors.New("No match for argument: kernel-devel-matched-" + old)
			}
			return DefaultRespond(c)
		},
	}
	if err := runPlan(t, job, rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	for _, w := range []string{
		"$ chroot /mnt dnf install -y akmods kernel-devel-matched-" + old + " kernel-devel-matched-" + cur,
		"$ chroot /mnt dnf install -y " + strings.Join(KernelFallback, " "),
		"$ chroot /mnt akmods --force --kernels " + cur + " --akmod nvidia",
	} {
		if !strings.Contains(plan, w) {
			t.Errorf("plan lacks %q", w)
		}
	}
	for _, p := range []string{"kernel-modules", "kernel-modules-extra", "kernel-core"} {
		found := false
		for _, k := range KernelFallback {
			found = found || k == p
		}
		if !found {
			t.Errorf("fallback lacks %s", p)
		}
	}
	if strings.Contains(plan, "akmods --force --kernels "+old) {
		t.Error("built for a kernel without kernel-devel")
	}
	if !(strings.Index(plan, "kmodgenca -a") < strings.Index(plan, "akmod-nvidia xorg-x11-drv-nvidia-cuda")) {
		t.Error("key after the driver transaction")
	}
	// The background build is waited for before anything else uses dnf.
	i := strings.Index(plan, "akmod-nvidia xorg-x11-drv-nvidia-cuda")
	if j := strings.Index(plan[i:], "\n$ "); j < 0 || !strings.HasPrefix(plan[i+j+1:], "$ chroot /mnt flock -w 1800 /run/akmods/akmods.lock true") {
		t.Error("no wait for the background akmods build after the driver transaction")
	}
	if got := driverOutcome(job); got["nvidia"] != protocol.DriverInstalled {
		t.Errorf("drivers %v", got)
	}
}

// The install fails after the key was queued: cleanup revokes the request.
func TestMOKRevokedOnFailure(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "uefi", "nvidia-laptop", true)
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "setfiles" || (c.Name == "chroot" && len(c.Args) > 1 && c.Args[1] == "setfiles") ||
			(c.Name == "usermod") {
			return "", errors.New("boom")
		}
		return DefaultRespond(c)
	}}
	if err := runPlan(t, job, rec, newReporter()); err == nil {
		t.Fatal("no failure")
	}
	plan := rec.Plan()
	if !(strings.Contains(plan, "mokutil --import") && strings.Index(plan, "mokutil --import") < strings.Index(plan, "$ mokutil --revoke-import")) {
		t.Error("key request not revoked after the failure")
	}
	if job.Outcome.MOK != backend.MOKNone {
		t.Errorf("MOK %q", job.Outcome.MOK)
	}
}

// mokutil refuses (e.g. no EFI variables): the install goes on and says so.
func TestMOKImportFailure(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "uefi", "nvidia-laptop", true)
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "chroot" && len(c.Args) > 1 && c.Args[1] == "mokutil" {
			return "", errors.New("EFI variables are not supported on this system")
		}
		return DefaultRespond(c)
	}}
	if err := runPlan(t, job, rec, newReporter()); err != nil {
		t.Fatal(err)
	}
	if job.Outcome.MOK != backend.MOKFailed {
		t.Errorf("MOK %q", job.Outcome.MOK)
	}
}

// BIOS never enrolls a key (no Secure Boot), even if the probe said so.
func TestNoMOKOnBIOS(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "bios", "nvidia-laptop", true)
	if job.NeedsMOK() {
		t.Fatal("NeedsMOK on BIOS")
	}
}
