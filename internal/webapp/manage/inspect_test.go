package manage

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/discover"
)

// WhatsApp's metadata request returns HTTP 400. The preview must remain installable
// through the same token flow that Get apps uses, with a visible warning and a local icon.
func TestInstallFromRejectedMetadataPreview(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer srv.Close()
	m := testManager(t)
	input := srv.URL + "/messages?account=2"
	p, err := m.Inspect(context.Background(), input)
	if err != nil {
		t.Fatal(err)
	}
	foundWarning := false
	for _, w := range p.Warnings {
		foundWarning = foundWarning || w.Code == "metadata_unavailable"
	}
	if !foundWarning || len(p.Icons) != 1 || p.Icons[0].Source != "monogram" {
		t.Fatalf("preview must explain the fallback and offer a letter icon: %+v", p)
	}
	res, err := m.Install(context.Background(), api.InstallParams{Token: p.Token})
	if err != nil {
		t.Fatal(err)
	}
	app, err := m.Paths.Load(res.App.ID)
	if err != nil || app.StartURL != input || app.Icon.Source != "monogram" {
		t.Fatalf("installed app: %+v, %v", app, err)
	}
	if _, err := os.Stat(m.Paths.DesktopFile(app.ID)); err != nil {
		t.Fatal("launcher entry missing:", err)
	}
}

func TestWhatsAppRuntimeRecommendationAndInstallDefault(t *testing.T) {
	for _, tc := range []struct {
		name, explicit, want string
		chromium             bool
	}{
		{"with Chromium", "", "chromium:chromium", true},
		{"explicit built-in choice", "webkit", "webkit", true},
		{"without Chromium", "", "webkit", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			m := testManager(t)
			if tc.chromium {
				bin := filepath.Join(m.Env.Root, "usr/bin/chromium-browser")
				if err := os.MkdirAll(filepath.Dir(bin), 0o755); err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(bin, nil, 0o755); err != nil {
					t.Fatal(err)
				}
			}
			u, _ := url.Parse("https://web.whatsapp.com/")
			p, err := m.storePreview(u.String(), &discover.Result{Input: u, FinalURL: u,
				Name: "WhatsApp", NameSource: "host", StartURL: u.String(), Site: "whatsapp.com",
				Scheme: "https", Category: "Network", MetadataStatus: 400})
			if err != nil {
				t.Fatal(err)
			}
			warning := false
			for _, w := range p.Warnings {
				warning = warning || w.Code == "calls_unsupported"
			}
			if !warning {
				t.Fatal("WhatsApp preview must explain the calling engine")
			}
			if tc.chromium && p.SuggestedRuntime != "chromium:chromium" {
				t.Fatalf("recommendation = %s", p.SuggestedRuntime)
			}
			res, err := m.Install(context.Background(), api.InstallParams{Token: p.Token, Runtime: tc.explicit})
			if err != nil {
				t.Fatal(err)
			}
			if res.App.Runtime != tc.want {
				t.Fatalf("runtime = %s, want %s", res.App.Runtime, tc.want)
			}
			app, err := m.Paths.Load(res.App.ID)
			if err != nil || app.Runtime != tc.want || app.StartURL != u.String() {
				t.Fatalf("saved app = %+v, %v", app, err)
			}
		})
	}
}
