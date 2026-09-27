package backend

import (
	"fmt"
	"math"
	"strings"
	"sync"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
)

// phaseRange maps each phase to its share of the progress bar.
var phaseRange = map[string][2]float64{
	protocol.PhaseDisk:       {0, 5},
	protocol.PhaseCopy:       {5, 40},
	protocol.PhaseConfigure:  {40, 45},
	protocol.PhaseBootloader: {45, 55},
	protocol.PhaseApps:       {55, 92},
	protocol.PhaseFinalize:   {92, 100},
}

var phaseSubstep = map[string]string{
	protocol.PhaseDisk:       "disk",
	protocol.PhaseCopy:       "system",
	protocol.PhaseConfigure:  "system",
	protocol.PhaseBootloader: "system",
	protocol.PhaseApps:       "apps",
	protocol.PhaseFinalize:   "finish",
}

// Tracker turns "phase X is 40% done" into progress events with percent, sub-steps, the
// friendly status line and time left. Mock and real installs share it.
type Tracker struct {
	mu        sync.Mutex
	r         Reporter
	start     time.Time
	now       func() time.Time
	phase     string
	frac      float64
	status    string
	appsDone  int
	appsTotal int
	// Expected total duration; ETA blends it with what has been measured so far.
	expected time.Duration
	last     protocol.ProgressEvent
}

// NewTracker starts tracking. expected is the planned duration (used for the first minutes).
func NewTracker(r Reporter, appsTotal int, expected time.Duration, now func() time.Time) *Tracker {
	if now == nil {
		now = time.Now
	}
	return &Tracker{r: r, start: now(), now: now, appsTotal: appsTotal, expected: expected, phase: protocol.PhaseDisk}
}

// Phase enters a phase with a status line.
func (t *Tracker) Phase(phase, status string) {
	t.mu.Lock()
	t.phase, t.frac, t.status = phase, 0, status
	t.mu.Unlock()
	t.emit()
}

// Update sets progress within the current phase (0..1) and optionally a new status.
func (t *Tracker) Update(frac float64, status string) {
	t.mu.Lock()
	if frac > t.frac {
		t.frac = math.Min(frac, 1)
	}
	if status != "" {
		t.status = status
	}
	t.mu.Unlock()
	t.emit()
}

// AppDone counts an app as finished (installed, skipped or deferred).
func (t *Tracker) AppDone() {
	t.mu.Lock()
	if t.appsDone < t.appsTotal {
		t.appsDone++
	}
	t.mu.Unlock()
	t.emit()
}

// AppsDone returns the count so far.
func (t *Tracker) AppsDone() (int, int) {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.appsDone, t.appsTotal
}

// Paused re-sends the last event marked as paused ("Paused on Steam").
func (t *Tracker) Paused(label string) {
	t.mu.Lock()
	ev := t.last
	t.mu.Unlock()
	ev.Paused = true
	ev.PausedLabel = label
	ev.Status = label
	for i := range ev.Substeps {
		if ev.Substeps[i].State == "active" {
			ev.Substeps[i].State = "error"
		}
	}
	t.r.Progress(ev)
}

// Finish sends 100%.
func (t *Tracker) Finish(status string) {
	t.mu.Lock()
	t.phase, t.frac, t.status = protocol.PhaseFinalize, 1, status
	t.mu.Unlock()
	t.emit()
}

// Percent is the overall percentage for the current state.
func (t *Tracker) Percent() int {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.percentLocked()
}

func (t *Tracker) percentLocked() int {
	r := phaseRange[t.phase]
	return int(math.Round(r[0] + (r[1]-r[0])*t.frac))
}

func (t *Tracker) emit() {
	t.mu.Lock()
	p := t.percentLocked()
	elapsed := t.now().Sub(t.start)
	eta := t.expected - elapsed
	if p >= 5 {
		measured := time.Duration(float64(elapsed) * float64(100-p) / float64(p))
		// Trust the measurement more as the install goes on.
		w := float64(p) / 100
		eta = time.Duration(w*float64(measured) + (1-w)*float64(eta))
	}
	if eta < 0 || p >= 100 {
		eta = 0
	}
	ev := protocol.ProgressEvent{
		Event: protocol.EventProgress, Percent: p, Phase: t.phase, Status: t.status,
		ETASeconds: int(eta.Seconds()), ETALabel: ETALabel(eta, p),
		AppsDone: t.appsDone, AppsTotal: t.appsTotal,
		Substeps: t.substepsLocked(),
	}
	t.last = ev
	t.mu.Unlock()
	t.r.Progress(ev)
}

func (t *Tracker) substepsLocked() []protocol.Substep {
	cur := phaseSubstep[t.phase]
	if t.frac >= 1 && t.phase == protocol.PhaseFinalize {
		cur = "" // everything done
	}
	curIdx := len(wizard.Substeps)
	for i, s := range wizard.Substeps {
		if s.ID == cur {
			curIdx = i
		}
	}
	out := make([]protocol.Substep, len(wizard.Substeps))
	for i, s := range wizard.Substeps {
		st := "todo"
		switch {
		case i < curIdx:
			st = "done"
		case i == curIdx:
			st = "active"
		}
		label := s.Label
		if s.ID == "apps" && t.appsTotal > 0 && st == "active" {
			n := t.appsDone + 1
			if n > t.appsTotal {
				n = t.appsTotal
			}
			label = fmt.Sprintf("%s · %d of %d", s.Label, n, t.appsTotal)
		}
		out[i] = protocol.Substep{ID: s.ID, Label: label, State: st}
	}
	return out
}

// ETALabel is "About 6 min left", "Less than a minute left" or "" when done.
func ETALabel(d time.Duration, percent int) string {
	if percent >= 100 {
		return ""
	}
	m := int(math.Round(d.Minutes()))
	switch {
	case d < 45*time.Second:
		return "Less than a minute left"
	case m <= 1:
		return "About 1 min left"
	default:
		return fmt.Sprintf("About %d min left", m)
	}
}

// InstallingStatus is "Installing Zed, your code editor…".
func InstallingStatus(c *catalog.Catalog, m *catalog.Module) string {
	if m.IsHardware() {
		return fmt.Sprintf("Installing the %s for your %s…", driverNoun(m), m.Fill("{device}"))
	}
	return fmt.Sprintf("Installing %s, your %s…", m.Name, c.RoleFor(m))
}

// BuildingStatus is the status line while akmods builds a driver for the new system's kernel.
func BuildingStatus(m *catalog.Module) string {
	return fmt.Sprintf("Building the %s for this computer — this takes a few minutes…", driverNoun(m))
}

// driverNoun is a driver's name in a sentence: "NVIDIA driver", "Broadcom Wi-Fi driver".
func driverNoun(m *catalog.Module) string {
	if m.Short != "" && strings.HasSuffix(m.Short, "driver") {
		return m.Short
	}
	return m.Name
}

// AttentionFor builds the optional-app failure event (design step 11).
func AttentionFor(m *catalog.Module, message, details string) protocol.AttentionEvent {
	name := m.Name
	if m.IsHardware() {
		return protocol.AttentionEvent{
			Event:    protocol.EventAttention,
			Module:   protocol.ModuleRef{ID: m.ID, Name: name},
			Title:    "The " + driverNoun(m) + " couldn’t be installed",
			Message:  message,
			Help:     "Everything else is fine — Arctic Linux works without it, and your " + m.Fill("{device}") + " keeps the open-source driver until you add it later.",
			Details:  details,
			Optional: true,
			Retry:    "Try again",
			Skip:     "Skip the driver",
		}
	}
	return protocol.AttentionEvent{
		Event:    protocol.EventAttention,
		Module:   protocol.ModuleRef{ID: m.ID, Name: name},
		Title:    name + " couldn’t be downloaded",
		Message:  message,
		Help:     "Everything else is fine — " + name + " is optional and you can add it later from the Software app.",
		Details:  details,
		Optional: true,
		Retry:    "Try again",
		Skip:     "Skip " + name,
	}
}
