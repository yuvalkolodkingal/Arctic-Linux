package webapp

import (
	"bufio"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

const repo = "../.."

// Mango raises a running web app on its second start only through the activation_bypass rule;
// its regex must match the ids NewID makes.
func TestRulesConfActivationBypass(t *testing.T) {
	data, err := os.ReadFile(filepath.Join(repo, "dotfiles/.config/mango/arctic/rules.conf"))
	if err != nil {
		t.Fatal(err)
	}
	var re *regexp.Regexp
	sc := bufio.NewScanner(strings.NewReader(string(data)))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if !strings.HasPrefix(line, "windowrule=") || !strings.Contains(line, "activation_bypass:1") {
			continue
		}
		for _, part := range strings.Split(strings.TrimPrefix(line, "windowrule="), ",") {
			if v, ok := strings.CutPrefix(part, "appid:"); ok {
				re = regexp.MustCompile(v)
			}
		}
	}
	if re == nil {
		t.Fatal("rules.conf has no activation_bypass rule for web apps")
	}
	id := NewID("YouTube Music", "youtube.com", "https://music.youtube.com/", func(string) string { return "" })
	if !re.MatchString(id) {
		t.Fatalf("%s does not match %s", id, re)
	}
	if re.MatchString("org.arcticlinux.Installer") || re.MatchString("org.arcticlinux.WebAppX") {
		t.Fatal("the rule matches more than web apps")
	}
}

// Every file of the cgo host starts with the build tag: an untagged Go file in
// cmd/arctic-webapp-host would make a package main without main under CGO_ENABLED=0.
func TestCgoFilesAreTagged(t *testing.T) {
	for _, dir := range []string{"internal/webkit", "cmd/arctic-webapp-host"} {
		filepath.WalkDir(filepath.Join(repo, dir), func(path string, d fs.DirEntry, err error) error {
			if err != nil || d.IsDir() {
				return nil
			}
			switch filepath.Ext(path) {
			case ".go", ".c", ".h":
			default:
				return nil
			}
			data, err := os.ReadFile(path)
			if err != nil {
				t.Error(err)
				return nil
			}
			first, _, _ := strings.Cut(string(data), "\n")
			if first != "//go:build cgo && webkit" {
				t.Errorf("%s: first line must be //go:build cgo && webkit, is %q", path, first)
			}
			return nil
		})
	}
}

// No shell strings, no disabled TLS checks and no sandbox kill switch outside tests and the
// container-only smoke script.
func TestSourceScan(t *testing.T) {
	bad := []string{`"sh", "-c"`, `"bash", "-c"`, "InsecureSkipVerify", "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"}
	for _, dir := range []string{"internal/webapp", "internal/webkit", "cmd/arctic-webapp", "cmd/arctic-webapp-host"} {
		filepath.WalkDir(filepath.Join(repo, dir), func(path string, d fs.DirEntry, err error) error {
			if err != nil || d.IsDir() || strings.HasSuffix(path, "_test.go") || strings.Contains(path, "/testdata/") || strings.HasSuffix(path, "/dev/smoke.sh") {
				return nil
			}
			switch filepath.Ext(path) {
			case ".go", ".c", ".h", ".sh":
			default:
				return nil
			}
			data, _ := os.ReadFile(path)
			for _, b := range bad {
				if !strings.Contains(string(data), b) {
					continue
				}
				// runtime.go removes the sandbox variable from the environment: allowed.
				if b == "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS" && strings.HasSuffix(path, "manage/runtime.go") {
					continue
				}
				t.Errorf("%s contains %s", path, b)
			}
			return nil
		})
	}
}
