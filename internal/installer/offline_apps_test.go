package installer

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
)

func TestOfflineAppsPreserveLocalPayloadAndQueueDownloads(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	job.Offline = true
	job.Data.Welcome.Language = "he_IL"
	job.Data.Apps.Selection["browser"] = []string{"zen"}
	job.Data.Apps.Selection["editor"] = []string{"featherpad", "zed"}
	job.Data.Apps.Selection["files"] = []string{"pcmanfm", "yazi"}
	var queued []byte
	var remote, removed []string
	rec := &Recorder{ExistsFn: func(p string) bool {
		return p == "/mnt/var/lib/flatpak/app/app.zen_browser.zen" || DefaultExists(p)
	}, Respond: func(c Cmd) (string, error) {
		if c.Name == "chroot" && len(c.Args) == 5 && c.Args[1] == "/usr/bin/python3" && c.Args[4] == "--queue" {
			queued = append([]byte{}, c.Stdin...)
		}
		if c.Name == "flatpak" && len(c.Args) > 0 && (c.Args[0] == "install" || c.Args[0] == "remote-add") ||
			c.Name == "chroot" && len(c.Args) > 2 && (c.Args[1] == "dnf" && (c.Args[2] == "install" || c.Args[2] == "swap" || c.Args[2] == "copr") || c.Args[1] == "nix") {
			remote = append(remote, c.String())
			return "", errors.New("offline remote operation")
		}
		if c.Name == "chroot" && len(c.Args) > 2 && c.Args[1] == "dnf" && c.Args[2] == "remove" || c.Name == "flatpak" && len(c.Args) > 0 && c.Args[0] == "uninstall" {
			if c.Name != "chroot" || len(c.Args) < 5 || strings.Join(c.Args[5:], " ") != strings.Join(LiveOnlyPackages, " ") {
				removed = append(removed, c.String())
			}
		}
		return DefaultRespond(c)
	}}
	rep := newReporter()
	rep.decide = func(string, int) backend.Decision {
		t.Error("offline installation asked for Attention")
		return backend.Defer
	}
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	if len(remote) != 0 || len(removed) != 0 || len(rep.attention) != 0 {
		t.Fatalf("offline changed local payload or tried remote setup: downloads=%v removals=%v attention=%v", remote, removed, rep.attention)
	}
	if rep.modules["zen"] != protocol.ModInstalled || rep.modules["featherpad"] != protocol.ModInstalled || rep.modules["zed"] != protocol.ModDeferred || rep.modules["yazi"] != protocol.ModDeferred {
		t.Fatalf("local/deferred states differ: %v", rep.modules)
	}
	var doc struct {
		Version int `json:"version"`
		Modules []struct {
			ID      string `json:"id"`
			Install []struct {
				Method   string   `json:"method"`
				Packages []string `json:"packages"`
				Repos    []string `json:"repos"`
			} `json:"install"`
		} `json:"modules"`
	}
	if err := json.Unmarshal(queued, &doc); err != nil {
		t.Fatal(err)
	}
	if doc.Version != 2 {
		t.Fatal("offline setup did not use the existing queue schema")
	}
	ids := map[string]bool{}
	for _, m := range doc.Modules {
		if ids[m.ID] {
			t.Fatal("duplicate queue module")
		}
		ids[m.ID] = true
		if m.ID == "installer-support" && !strings.Contains(strings.Join(m.Install[0].Packages, " "), "glibc-langpack-he") {
			t.Fatal("language support was silently omitted")
		}
		if m.ID == "codecs" && (len(m.Install[0].Repos) != 2 || len(m.Install[0].Packages) == 0) {
			t.Fatal("codecs lost their signed repository setup")
		}
	}
	for _, id := range []string{"codecs", "adw-gtk3-flatpak", "adw-gtk3-dark-flatpak", "zed", "yazi", "installer-support"} {
		if !ids[id] {
			t.Fatalf("lost deferred setup %s", id)
		}
	}
	if ids["zen"] || ids["featherpad"] {
		t.Fatal("local payload was unnecessarily queued")
	}
	if !strings.Contains(strings.Join(job.Outcome.Notes, "\n"), NoteAppsPending) || !strings.Contains(rec.Plan(), "dictation.py --install --offline") {
		t.Fatal("pending apps/dictation readiness is not disclosed")
	}
}

func TestOfflineAppQueueFailureDoesNotClaimCompletion(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	job.Offline = true
	failure := errors.New("queue could not be saved")
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "chroot" && len(c.Args) == 5 && c.Args[4] == "--queue" {
			return "", failure
		}
		return DefaultRespond(c)
	}}
	if err := runPlan(t, job, rec, newReporter()); !errors.Is(err, failure) {
		t.Fatalf("queue failure was swallowed: %v", err)
	}
	if strings.Contains(strings.Join(job.Outcome.Notes, "\n"), NoteAppsPending) {
		t.Fatal("failed queue was described as retryable")
	}
}
