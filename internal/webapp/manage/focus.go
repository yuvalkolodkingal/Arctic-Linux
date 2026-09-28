package manage

import (
	"context"
	"encoding/json"
	"os/exec"
	"strconv"
	"time"
)

// Mmsg is Mango's IPC client; tests put a fake one on PATH.
var Mmsg = "mmsg"

// FocusRunning is launch-or-focus for Chromium-runtime apps (a browser opens a second --app
// window on every start): if a window with this app id exists, focus it and report true. No
// mmsg (another compositor) means false, so the caller launches.
func FocusRunning(appID string) bool {
	if appID == "" {
		return false
	}
	path, err := exec.LookPath(Mmsg)
	if err != nil {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, path, "get", "all-clients").Output()
	if err != nil {
		return false
	}
	id, ok := findClient(out, appID)
	if !ok {
		return false
	}
	ctx2, cancel2 := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel2()
	return exec.CommandContext(ctx2, path, "dispatch", "focusid", "client,"+id).Run() == nil
}

// findClient looks for a client whose app id (key "appid" or "app_id") equals appID in
// `mmsg get all-clients` output and returns its id.
func findClient(out []byte, appID string) (string, bool) {
	var clients []map[string]any
	if err := json.Unmarshal(out, &clients); err != nil {
		var wrapped struct {
			Clients []map[string]any `json:"clients"`
		}
		if json.Unmarshal(out, &wrapped) != nil {
			return "", false
		}
		clients = wrapped.Clients
	}
	for _, c := range clients {
		got, _ := c["appid"].(string)
		if got == "" {
			got, _ = c["app_id"].(string)
		}
		if got != appID {
			continue
		}
		switch v := c["id"].(type) {
		case float64:
			return strconv.FormatInt(int64(v), 10), true
		case string:
			if v != "" {
				return v, true
			}
		}
	}
	return "", false
}
