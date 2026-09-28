package api

import (
	"encoding/json"
	"strings"
	"testing"
)

// The JSON names are the contract with the shell's Get apps and Remove apps pages and with
// Settings (docs/BUILD-SPEC.md §11): snake_case, never camelCase.
func TestWireNames(t *testing.T) {
	size := int64(48213504)
	cases := []struct {
		v    any
		want []string
	}{
		{HelloResult{EngineVersion: "0.3.0", ProtocolVersion: 1, Runtimes: []Runtime{{ID: "chromium:chromium", Name: "Chromium", WebRTC: true, Install: &RuntimeInstall{Module: "chromium", Method: "dnf"}}}},
			[]string{`{"engine_version":"0.3.0","protocol_version":1,"runtimes":[{"id":"chromium:chromium","name":"Chromium","available":false,"drm":false,"webrtc":true,"install":{"module":"chromium","method":"dnf"}}]}`}},
		{ProgressEvent{Event: EventProgress, Request: json.RawMessage("1"), Stage: StagePage, Message: "Opening music.youtube.com"},
			[]string{`{"event":"progress","request":1,"stage":"page","message":"Opening music.youtube.com"}`}},
		{ChangedEvent{Event: EventChanged, IDs: []string{"org.arcticlinux.WebApp.X_abcdef"}}, []string{`{"event":"changed","ids":["org.arcticlinux.WebApp.X_abcdef"]}`}},
		{Preview{Token: "b3f1c29a0d4c55a1", Scope: Scope{Site: "youtube.com", Scheme: "https"}, Icons: []IconChoice{{Index: 0, Source: "manifest", Purpose: "any", Size: 512, Format: "png", Path: "/p/0.png"}}, Warnings: []Warning{{Code: "insecure", Message: "m"}}},
			[]string{`"token":"b3f1c29a0d4c55a1"`, `"final_url":`, `"host_ascii":`, `"name_source":`, `"short_name":`, `"start_url":`, `"scope":{"site":"youtube.com","scheme":"https","manifest":""}`,
				`"manifest_url":`, `"theme_color":`, `"suggested_id":`, `"installed":`, `"icons":[{"index":0,"source":"manifest","purpose":"any","size":512,"format":"png","path":"/p/0.png"}]`,
				`"recommended_icon":0`, `"handlers_supported":`, `"warnings":[{"code":"insecure","message":"m"}]`, `"suggested_runtime":`}},
		{InstallResult{App: AppInfo{ID: "x"}, DesktopFile: "/d", Launched: true}, []string{`"app":{"id":"x"`, `"desktop_file":"/d"`, `"launched":true`}},
		{AppInfo{DataBytes: &size, TLSExceptions: []TLSExceptionInfo{{Host: "ha.lan:8123", SHA256: "ab"}}},
			[]string{`"icon_name":`, `"icon_path":`, `"runtime_available":`, `"extra_domains":`, `"handlers_supported":`, `"tls_exceptions":[{"host":"ha.lan:8123","sha256":"ab"}]`, `"data_bytes":48213504`, `"problem":`, `"created":`, `"updated":`}},
		{AppInfo{}, []string{`"data_bytes":null`}},
		{ListResult{Apps: []AppInfo{}, Kept: []KeptInfo{{ID: "k", Name: "Slack", URL: "https://app.slack.com/", DataBytes: &size}}},
			[]string{`"kept":[{"id":"k","name":"Slack","url":"https://app.slack.com/","data_bytes":48213504}]`}},
		{LaunchResult{Pid: 41234}, []string{`{"pid":41234}`}},
		{LaunchResult{Focused: true}, []string{`{"focused":true}`}},
		{UpdateResult{Updated: []Updated{{ID: "x", Changed: []string{"icon"}, Kept: []string{"name"}}}}, []string{`{"updated":[{"id":"x","changed":["icon"],"kept":["name"]}]}`}},
		{SetResult{Applied: "live"}, []string{`"applied":"live"`}},
		{RemoveResult{Removed: []Removed{{ID: "x", Stopped: true, KeptData: true}}}, []string{`{"removed":[{"id":"x","stopped":true,"kept_data":true}]}`}},
		{RepairResult{Repaired: []string{}, OrphansRemoved: []string{}}, []string{`{"repaired":[],"orphans_removed":[]}`}},
		{VersionResult{Version: "0.3.0", Host: "/h", HostPresent: true, WebKitVersion: "2.54.0"}, []string{`{"version":"0.3.0","host":"/h","host_present":true,"webkit_version":"2.54.0"}`}},
		{Empty{}, []string{`{}`}},
	}
	for _, c := range cases {
		b, err := json.Marshal(c.v)
		if err != nil {
			t.Fatal(err)
		}
		for _, w := range c.want {
			if !strings.Contains(string(b), w) {
				t.Errorf("%T: %s\n  lacks %s", c.v, b, w)
			}
		}
		var v any
		json.Unmarshal(b, &v)
		checkKeys(t, v)
	}
}

// checkKeys fails on any key that is not snake_case.
func checkKeys(t *testing.T, v any) {
	t.Helper()
	switch x := v.(type) {
	case map[string]any:
		for k, val := range x {
			if strings.ToLower(k) != k || strings.Contains(k, "-") {
				t.Errorf("key %q is not snake_case", k)
			}
			checkKeys(t, val)
		}
	case []any:
		for _, val := range x {
			checkKeys(t, val)
		}
	}
}

// Params the shell sends decode into these names.
func TestParamNames(t *testing.T) {
	var ip InstallParams
	if err := json.Unmarshal([]byte(`{"token":"t","name":"n","icon":0,"icon_file":"/f","icon_url":"https://i","category":"Office","runtime":"webkit","links":"browser","notifications":"allow","mail_links":true,"new_copy":true,"launch":true}`), &ip); err != nil {
		t.Fatal(err)
	}
	if ip.Token != "t" || string(ip.Icon) != "0" || ip.IconFile != "/f" || ip.IconURL != "https://i" || !ip.MailLinks || !ip.NewCopy || !ip.Launch {
		t.Fatalf("%+v", ip)
	}
	var sp SetParams
	if err := json.Unmarshal([]byte(`{"id":"x","name":"YT Music","links":"app","extra_domains":["accounts.google.com"],"notifications":"ask","icon":{"file":"/p.png"},"mail_links":false,"devtools":true,"reset_permissions":true,"forget_certificate":"ha.lan"}`), &sp); err != nil {
		t.Fatal(err)
	}
	if *sp.Name != "YT Music" || *sp.Links != "app" || sp.ExtraDomains[0] != "accounts.google.com" || sp.Icon.File != "/p.png" || *sp.MailLinks || !*sp.Devtools || !sp.ResetPermissions || sp.ForgetCertificate != "ha.lan" {
		t.Fatalf("%+v", sp)
	}
	var rp RemoveParams
	json.Unmarshal([]byte(`{"ids":["a"],"keep_data":true}`), &rp)
	if !rp.KeepData || rp.IDs[0] != "a" {
		t.Fatalf("%+v", rp)
	}
	var lp ListParams
	json.Unmarshal([]byte(`{"sizes":true,"kept":true}`), &lp)
	if !lp.Sizes || !lp.Kept {
		t.Fatal("list params")
	}
}
