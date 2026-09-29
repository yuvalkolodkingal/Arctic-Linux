package main

import (
	"flag"
	"fmt"
	"os"
	"syscall"
)

// execFn is syscall.Exec; tests replace it.
var execFn = syscall.Exec

// cmdRun is the launcher entry's Exec: it replaces itself with the app's runtime (same pid, no
// shell). For a running Chromium-runtime app it focuses the window instead; a running WebKit
// app is raised by the host's own single-instance handling.
func (c *cli) cmdRun(args []string) int {
	var u *string
	var inspect *bool
	_, pos, _, ok := c.flags("run", args, func(fs *flag.FlagSet) {
		u = fs.String("url", "", "")
		inspect = fs.Bool("inspect", false, "")
	})
	if !ok {
		return 2
	}
	if len(pos) < 1 || len(pos) > 2 {
		return c.usageError(false, "arctic-webapp run needs an app id.")
	}
	uri := ""
	if len(pos) == 2 {
		uri = pos[1]
	}
	m, code := c.manager(false)
	if m == nil {
		return code
	}
	plan, err := m.PlanRun(pos[0], uri, *u, *inspect)
	if err != nil {
		return c.fail(false, err)
	}
	if plan.Ignored != "" {
		fmt.Fprintf(c.stderr, "arctic-webapp: ignoring %q: this app doesn't open it\n", plan.Ignored)
	}
	if plan.Focused {
		return 0
	}
	if plan.Browser && m.Paths.RunningPid(pos[0]) == 0 {
		// Our pid becomes the browser's after exec.
		m.Paths.WritePid(pos[0], os.Getpid())
	}
	err = execFn(plan.Exec.Path, plan.Exec.Argv, plan.Exec.Env)
	return c.fail(false, fmt.Errorf("couldn't start %s: %v", plan.Exec.Path, err))
}
