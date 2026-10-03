//go:build cgo && webkit

package main

import (
	"encoding/json"
	"io"
	"log"
	"math"
	"os"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/policy"
)

func TestClosePreservesFiniteZoomAndNormalGeometry(t *testing.T) {
	c := &controller{
		paths: webapp.Paths{DataHome: t.TempDir()},
		app:   &webapp.App{ID: "org.arcticlinux.WebApp.Chat_123456"},
		state: policy.State{Zoom: 1.25}, log: log.New(io.Discard, "", 0),
	}
	if err := os.MkdirAll(c.paths.AppDir(c.app.ID), 0700); err != nil {
		t.Fatal(err)
	}
	for _, zoom := range []float64{math.NaN(), math.Inf(1), 0, 99} {
		c.CloseRequest(900, 650, true, zoom)
		data, err := os.ReadFile(c.paths.StateFile(c.app.ID))
		if err != nil {
			t.Fatal(err)
		}
		var state policy.State
		if err := json.Unmarshal(data, &state); err != nil {
			t.Fatal(err)
		}
		if state.Zoom != 1.25 || state.Width != 900 || state.Height != 650 || !state.Maximized {
			t.Fatalf("lost state: %+v", state)
		}
	}
	c.CloseRequest(850, 600, false, 1.5)
	if c.state.Zoom != 1.5 {
		t.Fatal("valid user zoom was ignored")
	}
}
