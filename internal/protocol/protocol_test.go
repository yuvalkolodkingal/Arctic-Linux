package protocol

import (
	"encoding/json"
	"strings"
	"testing"
)

// The JSON field names are the contract with the UI (BUILD-SPEC §4).
func TestWireShapes(t *testing.T) {
	cases := []struct {
		v    any
		want []string
	}{
		{ProgressEvent{Event: EventProgress, Substeps: []Substep{{ID: "disk", Label: "Preparing the disk", State: "done"}}},
			[]string{`"event":"progress"`, `"percent":`, `"phase":`, `"status":`, `"eta_seconds":`, `"substeps":[{"id":"disk","label":"Preparing the disk","state":"done"}]`}},
		{ModuleEvent{Event: EventModule, ID: "zed", Name: "Zed", Status: ModDownloading, Percent: 40},
			[]string{`{"event":"module","id":"zed","name":"Zed","status":"downloading","percent":40}`}},
		{AttentionEvent{Event: EventAttention, Module: ModuleRef{ID: "steam", Name: "Steam"}, Message: "m", Optional: true},
			[]string{`"module":{"id":"steam","name":"Steam"}`, `"message":"m"`, `"optional":true`}},
		{FailedEvent{Event: EventFailed, Message: "x", Fatal: true}, []string{`"event":"failed"`, `"fatal":true`}},
		{DoneEvent{Event: EventDone, AppsInstalled: 9, FirstName: "Noa"}, []string{`"apps_installed":9`, `"first_name":"Noa"`}},
		{Response{ID: json.RawMessage("7"), Error: FieldErrors("Fix it.", map[string]string{"username": "Use lowercase letters, numbers, - and _."})},
			[]string{`{"id":7,"error":{"code":"invalid","message":"Fix it.","fields":{"username":"Use lowercase letters, numbers, - and _."}}}`}},
		{Response{ID: json.RawMessage(`"a"`), Result: OKResult{OK: true}}, []string{`{"id":"a","result":{"ok":true}}`}},
		{HelloResult{EngineVersion: "0.2.0", Firmware: "uefi"}, []string{`"engine_version":"0.2.0"`, `"mock":false`, `"live":false`, `"firmware":"uefi"`}},
		{PassphraseResult{Score: 4, Label: "Strong", Words: 4, OK: true}, []string{`{"score":4,"label":"Strong","words":4,"ok":true}`}},
		{EstimateResult{Apps: 9, Bytes: 1, Label: "l"}, []string{`{"apps":9,"bytes":1,"label":"l"}`}},
		{SummaryResult{Rows: []SummaryRow{{Step: "disk", Label: "Disk", Value: "v"}}, Warning: "w", PrimaryLabel: "p"},
			[]string{`"rows":[{"step":"disk","label":"Disk","value":"v"}]`, `"warning":"w"`, `"primary_label":"p"`}},
		{WizardResult{Steps: []StepState{{ID: "welcome", Title: "Welcome", State: "current"}}, Current: "welcome"},
			[]string{`"steps":[{"id":"welcome","title":"Welcome","state":"current"}]`, `"current":"welcome"`}},
	}
	for _, c := range cases {
		b, err := json.Marshal(c.v)
		if err != nil {
			t.Fatal(err)
		}
		for _, w := range c.want {
			if !strings.Contains(string(b), w) {
				t.Errorf("%T: %s lacks %s", c.v, b, w)
			}
		}
	}
}

func TestRequestDecoding(t *testing.T) {
	var r Request
	if err := json.Unmarshal([]byte(`{"id": 7, "method": "SetStep", "params": {"id":"account","data":{"username":"noa"}}}`), &r); err != nil {
		t.Fatal(err)
	}
	var p SetStepParams
	if err := json.Unmarshal(r.Params, &p); err != nil || p.ID != "account" || string(r.ID) != "7" {
		t.Fatalf("%+v %+v %v", r, p, err)
	}
	if !SecretMethods[MethodSetSecrets] || !SecretMethods[MethodConnectWifi] || SecretMethods[MethodSetStep] {
		t.Error("secret methods")
	}
}
