package backend

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
)

type rec struct {
	mu  sync.Mutex
	evs []protocol.ProgressEvent
}

func (r *rec) Progress(ev protocol.ProgressEvent) {
	r.mu.Lock()
	r.evs = append(r.evs, ev)
	r.mu.Unlock()
}
func (r *rec) Module(protocol.ModuleEvent) {}
func (r *rec) Attention(context.Context, protocol.AttentionEvent) Decision {
	return Skip
}
func (r *rec) Logf(string, ...any) {}

func TestTracker(t *testing.T) {
	now := time.Date(2026, 9, 27, 12, 0, 0, 0, time.UTC)
	clock := func() time.Time { return now }
	r := &rec{}
	tr := NewTracker(r, 9, 10*time.Minute, clock)
	tr.Phase(protocol.PhaseDisk, "Preparing the disk…")
	if ev := r.evs[0]; ev.Percent != 0 || ev.Substeps[0].State != "active" || ev.Substeps[1].State != "todo" || ev.ETALabel != "About 10 min left" {
		t.Fatalf("first %+v", ev)
	}
	now = now.Add(4 * time.Minute)
	tr.Phase(protocol.PhaseApps, "Installing Zed, your code editor…")
	tr.AppDone()
	tr.AppDone()
	ev := r.evs[len(r.evs)-1]
	if ev.Percent != 55 || ev.Substeps[0].State != "done" || ev.Substeps[1].State != "done" || ev.Substeps[2].State != "active" {
		t.Fatalf("apps %+v", ev)
	}
	if ev.Substeps[2].Label != "Installing your apps · 3 of 9" || ev.AppsDone != 2 {
		t.Errorf("apps label %q done %d", ev.Substeps[2].Label, ev.AppsDone)
	}
	if ev.ETASeconds <= 0 || ev.ETASeconds > 600 {
		t.Errorf("eta %d", ev.ETASeconds)
	}
	tr.Paused("Paused on Steam")
	ev = r.evs[len(r.evs)-1]
	if !ev.Paused || ev.Status != "Paused on Steam" || ev.Substeps[2].State != "error" {
		t.Errorf("paused %+v", ev)
	}
	tr.Finish("Arctic Linux is installed.")
	ev = r.evs[len(r.evs)-1]
	if ev.Percent != 100 || ev.ETASeconds != 0 || ev.Substeps[3].State != "done" {
		t.Errorf("finish %+v", ev)
	}
	if ETALabel(30*time.Second, 90) != "Less than a minute left" || ETALabel(6*time.Minute, 50) != "About 6 min left" {
		t.Error("ETALabel")
	}
}
