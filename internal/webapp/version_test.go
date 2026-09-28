package webapp

import (
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
)

// The engine ships in the same release as the installer backend; bump both together.
func TestVersionMatchesBackend(t *testing.T) {
	if Version != backend.EngineVersion {
		t.Fatalf("webapp.Version %q != backend.EngineVersion %q", Version, backend.EngineVersion)
	}
}
