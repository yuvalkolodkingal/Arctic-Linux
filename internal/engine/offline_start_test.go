package engine

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/mock"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
)

type offlineStartBackend struct {
	*mock.Backend
	mu     sync.Mutex
	online *bool
	jobs   chan [2]bool
}

func (b *offlineStartBackend) Network(ctx context.Context) protocol.NetworkState {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.online != nil {
		return protocol.NetworkState{Online: *b.online}
	}
	return b.Backend.Network(ctx)
}

func (b *offlineStartBackend) Install(_ context.Context, job *backend.Job, _ backend.Reporter) error {
	b.jobs <- [2]bool{job.Offline, job.Data.Network.Offline}
	return nil
}

func TestStartHonorsOfflineChoiceAndLostConnection(t *testing.T) {
	for _, tc := range []struct {
		name             string
		selected, online bool
	}{
		{"selected-offline-connected", true, true},
		{"selected-offline-disconnected", true, false},
		{"online-connected", false, true},
		{"online-choice-lost-connection", false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			b := &offlineStartBackend{Backend: mock.New(mock.Options{Speed: 400, LogDir: t.TempDir()}), jobs: make(chan [2]bool, 1)}
			e := newEngineWith(t, b, false)
			c, stop := newClient(t, e)
			defer stop()
			fullWizard(t, c)
			c.ok("SetStep", map[string]any{"id": "network", "data": map[string]any{"offline": tc.selected}})
			b.mu.Lock()
			b.online = &tc.online
			b.mu.Unlock()
			c.ok("Start", nil)
			select {
			case got := <-b.jobs:
				if got != [2]bool{tc.selected || !tc.online, tc.selected} {
					t.Fatalf("offline decision/choice changed: %v", got)
				}
			case <-time.After(5 * time.Second):
				t.Fatal("Start did not reach the backend")
			}
		})
	}
}
