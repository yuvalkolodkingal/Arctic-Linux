package manage

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
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
