package webapp

import (
	"testing"
	"time"
)

// testPaths is a fresh per-test tree.
func testPaths(t *testing.T) Paths {
	t.Helper()
	d := t.TempDir()
	return Paths{
		Home: d, DataHome: d + "/data", CacheHome: d + "/cache", StateHome: d + "/state", RuntimeDir: d + "/run/arctic-webapp",
	}
}

func sampleApp() *App {
	a := &App{
		Schema: Schema, Render: RenderVersion, EngineVersion: Version,
		ID: "org.arcticlinux.WebApp.YouTubeMusic_4c1a9e", Copy: 1,
		Name: "YouTube Music", NameSource: "manifest", InputURL: "music.youtube.com",
		StartURL:    "https://music.youtube.com/?source=pwa",
		ManifestURL: "https://music.youtube.com/manifest.webmanifest",
		ManifestID:  "https://music.youtube.com/?source=pwa",
		Scope:       Scope{Site: "youtube.com", Scheme: "https", Manifest: "https://music.youtube.com/"},
		Category:    "AudioVideo", ThemeColor: "#0f0f0f",
		Icon:    Icon{Source: "manifest", URL: "https://music.youtube.com/img/favicon_512.png", Purpose: "any"},
		Runtime: "webkit", Options: DefaultOptions(),
		Created: time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC), Updated: time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC),
	}
	a.Normalize()
	return a
}
