// Package backend is the seam between the engine (wizard, protocol, events) and the machine:
// the real backend probes the live system and runs the install; the mock backend simulates
// everything and never touches the system (BUILD-SPEC §4).
package backend

import (
	"context"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
)

// EngineVersion is reported by Hello.
const EngineVersion = "0.1.0"

// Info describes the environment.
type Info struct {
	Mock     bool
	Live     bool
	Firmware string // uefi | bios
}

// Backend is implemented by the real system backend and the mock.
type Backend interface {
	Info() Info
	// Language is the live session's LANG (used to pre-select the language).
	Language() string
	DMI() wizard.DMI
	Disks(ctx context.Context) ([]hw.Disk, error)
	Network(ctx context.Context) protocol.NetworkState
	ScanWifi(ctx context.Context) ([]protocol.WifiNetwork, error)
	// ConnectWifi returns a *protocol.Error with code auth or timeout on failure.
	ConnectWifi(ctx context.Context, ssid, password string) error
	DetectTimezone(ctx context.Context) wizard.Detected
	// Install runs the whole install and reports through r. It returns nil when the system
	// is installed (optional apps may have been skipped or deferred) and an error for a
	// fatal failure.
	Install(ctx context.Context, job *Job, r Reporter) error
	SaveLog(ctx context.Context) (string, error)
	Reboot(ctx context.Context) error
}

// Secrets are held in memory only and wiped after the install.
type Secrets struct {
	LUKS     []byte
	Password []byte
}

// Wipe overwrites the secrets.
func (s *Secrets) Wipe() {
	for i := range s.LUKS {
		s.LUKS[i] = 0
	}
	for i := range s.Password {
		s.Password[i] = 0
	}
	s.LUKS, s.Password = nil, nil
}

// Job is everything an install needs.
type Job struct {
	Data     wizard.Data
	Disk     hw.Disk
	Firmware string
	Catalog  *catalog.Catalog
	Secrets  *Secrets
	LogPath  string
}

// Apps returns the visible modules the job installs (what "9 apps" counts).
func (j *Job) Apps() []*catalog.Module { return j.Catalog.Apps(j.Data.Apps.Selection) }

// Decision answers an attention event.
type Decision int

const (
	Retry Decision = iota
	Skip
	Defer // unattended: give up now, retry at first boot
)

// Reporter receives progress from Install. Attention blocks until the person (or the
// unattended policy) decides.
type Reporter interface {
	Progress(ev protocol.ProgressEvent)
	Module(ev protocol.ModuleEvent)
	Attention(ctx context.Context, ev protocol.AttentionEvent) Decision
	Logf(format string, a ...any)
}
