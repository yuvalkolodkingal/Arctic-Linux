package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"text/tabwriter"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
)

func (c *cli) cmdList(args []string) int {
	var sizes, kept *bool
	_, pos, j, ok := c.flags("list", args, func(fs *flag.FlagSet) {
		sizes = fs.Bool("sizes", false, "")
		kept = fs.Bool("kept", false, "")
	})
	if !ok {
		return 2
	}
	if len(pos) > 0 {
		return c.usageError(j, "arctic-webapp list takes no arguments.")
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	res, err := m.List(*sizes, *kept)
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, res, func(w io.Writer) {
		tw := tabwriter.NewWriter(w, 0, 4, 2, ' ', 0)
		for _, a := range res.Apps {
			extra := a.Runtime
			if a.Running {
				extra += ", open"
			}
			if a.Problem != "" {
				extra += ", " + a.Problem
			}
			fmt.Fprintf(tw, "%s\t%s\t%s\t%s%s\n", a.ID, a.Name, a.Host, extra, sizeText(a.DataBytes))
		}
		for _, k := range res.Kept {
			fmt.Fprintf(tw, "%s\t%s\t%s\tsaved sign-in data%s\n", k.ID, k.Name, hostOf(k.URL), sizeText(k.DataBytes))
		}
		tw.Flush()
	})
}

func sizeText(n *int64) string {
	if n == nil {
		return ""
	}
	return fmt.Sprintf(", %.1f MB", float64(*n)/1e6)
}

func hostOf(u string) string {
	u = strings.TrimPrefix(strings.TrimPrefix(u, "https://"), "http://")
	if i := strings.IndexByte(u, '/'); i >= 0 {
		u = u[:i]
	}
	return u
}

func (c *cli) cmdShow(args []string) int {
	var sizes *bool
	_, pos, j, ok := c.flags("show", args, func(fs *flag.FlagSet) { sizes = fs.Bool("sizes", false, "") })
	if !ok || !c.needIDs("show", j, pos, 1, 1) {
		return 2
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	info, err := m.Get(pos[0], *sizes)
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, api.AppResult{App: info}, func(w io.Writer) { printInfo(w, info) })
}

func printInfo(w io.Writer, a api.AppInfo) {
	tw := tabwriter.NewWriter(w, 0, 4, 2, ' ', 0)
	row := func(k string, v any) { fmt.Fprintf(tw, "%s\t%v\n", k, v) }
	row("id", a.ID)
	row("name", a.Name)
	row("url", a.URL)
	row("category", a.Category)
	row("runtime", a.Runtime)
	row("open", a.Running)
	row("links", a.Links)
	row("notifications", a.Notifications)
	row("devtools", a.Devtools)
	row("keep running", a.KeepRunning)
	row("start at login", a.StartAtLogin)
	row("ask download", a.AskDownload)
	row("rendering", a.Rendering)
	if len(a.ExtraDomains) > 0 {
		row("extra domains", strings.Join(a.ExtraDomains, ", "))
	}
	if len(a.Handlers) > 0 {
		row("handles", strings.Join(a.Handlers, ", "))
	}
	for _, e := range a.TLSExceptions {
		row("trusted certificate", e.Host+" "+e.SHA256)
	}
	if a.DataBytes != nil {
		row("data", strings.TrimPrefix(sizeText(a.DataBytes), ", "))
	}
	if a.Problem != "" {
		row("problem", a.Problem)
	}
	tw.Flush()
}

func (c *cli) cmdRemove(args []string) int {
	var keep *bool
	_, pos, j, ok := c.flags("remove", args, func(fs *flag.FlagSet) { keep = fs.Bool("keep-data", false, "") })
	if !ok || !c.needIDs("remove", j, pos, 1, 0) {
		return 2
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	res, err := m.Remove(pos, *keep)
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, res, func(w io.Writer) {
		for _, r := range res.Removed {
			note := ""
			if r.KeptData {
				note = " (sign-in data kept; `arctic-webapp forget " + r.ID + "` deletes it)"
			}
			fmt.Fprintf(w, "Removed %s%s\n", r.ID, note)
		}
	})
}

func (c *cli) cmdForget(args []string) int {
	_, pos, j, ok := c.flags("forget", args, nil)
	if !ok || !c.needIDs("forget", j, pos, 1, 0) {
		return 2
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	if err := m.Forget(pos); err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, api.Empty{}, nil)
}

func (c *cli) cmdClearData(args []string) int {
	_, pos, j, ok := c.flags("clear-data", args, nil)
	if !ok || !c.needIDs("clear-data", j, pos, 1, 1) {
		return 2
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	if err := m.ClearData(pos[0]); err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, api.Empty{}, nil)
}

func (c *cli) cmdRepair(args []string) int {
	_, pos, j, ok := c.flags("repair", args, nil)
	if !ok {
		return 2
	}
	if len(pos) > 0 {
		return c.usageError(j, "arctic-webapp repair takes no arguments.")
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	res, err := m.Repair()
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, res, func(w io.Writer) {
		fmt.Fprintf(w, "Rewrote %d launcher entries; removed %d orphans.\n", len(res.Repaired), len(res.OrphansRemoved))
	})
}

func (c *cli) cmdRuntimes(args []string) int {
	_, _, j, ok := c.flags("runtimes", args, nil)
	if !ok {
		return 2
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	rs := m.Env.Runtimes()
	return c.ok(j, api.RuntimesResult{Runtimes: rs}, func(w io.Writer) {
		tw := tabwriter.NewWriter(w, 0, 4, 2, ' ', 0)
		for _, r := range rs {
			state := "not installed"
			if r.Available {
				state = "installed"
			}
			fmt.Fprintf(tw, "%s\t%s\t%s\n", r.ID, r.Name, state)
		}
		tw.Flush()
	})
}

func (c *cli) cmdLaunch(args []string) int {
	var u *string
	_, pos, j, ok := c.flags("launch", args, func(fs *flag.FlagSet) { u = fs.String("url", "", "") })
	if !ok || !c.needIDs("launch", j, pos, 1, 1) {
		return 2
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	res, err := m.Launch(pos[0], *u)
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, res, nil)
}

func (c *cli) cmdVersion(args []string) int {
	var wk *bool
	_, _, j, ok := c.flags("version", args, func(fs *flag.FlagSet) { wk = fs.Bool("webkit", false, "") })
	if !ok {
		return 2
	}
	host := os.Getenv("ARCTIC_WEBAPP_HOST")
	if host == "" {
		host = webapp.HostPath
	}
	res := api.VersionResult{Version: webapp.Version, Host: host}
	if _, err := os.Stat(host); err == nil {
		res.HostPresent = true
	}
	if *wk && res.HostPresent {
		out, err := exec.Command(host, "--version").Output()
		if err == nil {
			// "arctic-webapp-host 0.3.0 (WebKitGTK 2.54.0)"
			s := string(out)
			if i := strings.Index(s, "WebKitGTK "); i >= 0 {
				res.WebKitVersion = strings.TrimRight(strings.Fields(s[i+len("WebKitGTK "):])[0], ")")
			}
		}
	}
	return c.ok(j, res, func(w io.Writer) {
		fmt.Fprintln(w, "arctic-webapp", webapp.Version)
		if res.WebKitVersion != "" {
			fmt.Fprintln(w, "WebKitGTK", res.WebKitVersion)
		}
	})
}

// cmdQuit stops the verified app process, including an app running without a window.
func (c *cli) cmdQuit(args []string) int {
	_, pos, j, ok := c.flags("quit", args, nil)
	if !ok || !c.needIDs("quit", j, pos, 1, 1) {
		return 2
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	if _, err := m.Paths.Load(pos[0]); err != nil {
		return c.fail(j, err)
	}
	stopped, err := m.Paths.Stop(pos[0], m.StopWait)
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, map[string]any{"stopped": stopped}, func(w io.Writer) { fmt.Fprintln(w, "App stopped") })
}
