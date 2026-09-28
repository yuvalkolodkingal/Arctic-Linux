package manage

import (
	"os"
	"os/exec"
	"strings"
	"syscall"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
)

// RunPlan is what `run` does: exec a runtime, or (for a running Chromium-runtime app) focus it.
type RunPlan struct {
	Exec    Exec
	Focused bool   // a running Chromium-runtime window was raised; nothing to exec
	Browser bool   // the runtime is a browser: `run` records its pid
	Ignored string // a URI argument that was ignored (logged)
}

// PlanRun validates the id, reads the record under the shared lock (re-rendering it when an
// older engine rendered it) and builds the runtime's command. uri is the optional positional
// %u argument (mailto: for a mail-link app); openURL is --url.
func (m *Manager) PlanRun(id, uri, openURL string, inspect bool) (RunPlan, error) {
	var plan RunPlan
	if !webapp.Valid(id) {
		return plan, webapp.Errorf(webapp.CodeNotFound, "There’s no web app called %q.", id)
	}
	var a *webapp.App
	err := m.shared(func() error {
		var err error
		a, err = m.Paths.Load(id)
		return err
	})
	if err != nil {
		return plan, err
	}
	if a.Render < webapp.RenderVersion {
		m.rerender([]*webapp.App{a})
	}
	if uri != "" {
		switch {
		case uri == "%u" || uri == "%U":
			// A launcher passed the field code through: nothing to open.
		case a.HasHandler("mailto") && MailtoURL(a.StartURL, uri) != "":
			openURL = MailtoURL(a.StartURL, uri)
		default:
			plan.Ignored = uri
		}
	}
	if openURL != "" && !webURL(openURL) {
		plan.Ignored = openURL
		openURL = ""
	}
	notice := ""
	if b, ok := BrowserFor(a.Runtime); ok {
		if m.Env.Available(a.Runtime) {
			if openURL == "" && FocusRunning(a.WMClass) {
				plan.Focused = true
				return plan, nil
			}
			target := openURL
			if target == "" {
				target = a.StartURL
			}
			if ex, ok := BrowserExec(b, m.Paths, m.Env, a.ID, target, m.Environ); ok {
				plan.Exec, plan.Browser = ex, true
				return plan, nil
			}
		}
		// The browser was removed: open in the Arctic engine with a banner saying so.
		notice = "runtime-missing"
	}
	if !m.Env.Available("webkit") {
		return plan, webapp.Errorf(webapp.CodeUnsupported, "The web app window isn’t installed (package arctic-webapps).")
	}
	plan.Exec = HostExec(m.Env.HostBin, a.ID, openURL, inspect, notice, a.Options.Rendering, m.Environ, NVIDIA())
	return plan, nil
}

func webURL(s string) bool {
	return (strings.HasPrefix(s, "https://") || strings.HasPrefix(s, "http://")) &&
		!strings.ContainsAny(s, " \t\r\n\x00") && len(s) <= 8192
}

// Launch starts `arctic-webapp run <id> [--url U]` detached (its own session), for the shell
// and Settings. A running WebKit app is raised by its own single-instance handling; a running
// Chromium-runtime app is focused here and reports focused.
func (m *Manager) Launch(id, openURL string) (api.LaunchResult, error) {
	var res api.LaunchResult
	a, err := m.Paths.Load(id)
	if err != nil {
		return res, err
	}
	if openURL != "" && !webURL(openURL) {
		return res, webapp.Errorf(webapp.CodeInvalid, "That isn’t a web address.")
	}
	if _, ok := BrowserFor(a.Runtime); ok && openURL == "" && m.Env.Available(a.Runtime) && FocusRunning(a.WMClass) {
		res.Focused = true
		return res, nil
	}
	self, err := os.Executable()
	if err != nil {
		self = "arctic-webapp"
	}
	argv := []string{"run", id}
	if openURL != "" {
		argv = append(argv, "--url", openURL)
	}
	cmd := exec.Command(self, argv...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	devnull, err := os.OpenFile(os.DevNull, os.O_RDWR, 0)
	if err == nil {
		cmd.Stdin, cmd.Stdout, cmd.Stderr = devnull, devnull, devnull
		defer devnull.Close()
	}
	if err := cmd.Start(); err != nil {
		return res, webapp.Errorf(webapp.CodeInternal, "%s couldn’t start: %v.", a.Name, err)
	}
	res.Pid = cmd.Process.Pid
	go cmd.Wait() // reap it; the app runs on in its own session
	return res, nil
}
