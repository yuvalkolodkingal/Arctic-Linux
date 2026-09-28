package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
)

func signalContext() (context.Context, context.CancelFunc) {
	return signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
}

func (c *cli) cmdInspect(args []string) int {
	_, pos, j, ok := c.flags("inspect", args, nil)
	if !ok {
		return 2
	}
	if len(pos) != 1 {
		return c.usageError(j, "arctic-webapp inspect needs a web address.")
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	ctx, stop := signalContext()
	defer stop()
	pr, err := m.Inspect(ctx, pos[0])
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, map[string]any{"preview": pr}, func(w io.Writer) {
		fmt.Fprintf(w, "%s\n  %s\n  start: %s\n  scope: %s (%s)\n", pr.Name, pr.HostASCII, pr.StartURL, pr.Scope.Site, pr.Scope.Scheme)
		for _, ic := range pr.Icons {
			mark := " "
			if ic.Index == pr.RecommendedIcon {
				mark = "*"
			}
			fmt.Fprintf(w, "  %s icon %d: %s %dpx (%s)\n", mark, ic.Index, ic.Source, ic.Size, ic.Path)
		}
		for _, wn := range pr.Warnings {
			fmt.Fprintf(w, "  ! %s\n", wn.Message)
		}
		fmt.Fprintf(w, "Add it with: arctic-webapp install --preview %s\n", pr.Token)
	})
}

// onOff reads an on/off flag value into a *bool (nil when absent).
type onOff struct{ v *bool }

func (o *onOff) String() string { return "" }
func (o *onOff) Set(s string) error {
	switch s {
	case "on", "true", "yes":
		t := true
		o.v = &t
	case "off", "false", "no":
		f := false
		o.v = &f
	default:
		return fmt.Errorf("use on or off")
	}
	return nil
}

// optString is a string flag that remembers whether it was given.
type optString struct{ v *string }

func (o *optString) String() string { return "" }
func (o *optString) Set(s string) error {
	o.v = &s
	return nil
}

func (c *cli) cmdInstall(args []string) int {
	var p api.InstallParams
	var iconArg string
	mail := &onOff{}
	_, pos, j, ok := c.flags("install", args, func(fs *flag.FlagSet) {
		fs.StringVar(&p.Token, "preview", "", "")
		fs.StringVar(&p.Name, "name", "", "")
		fs.StringVar(&iconArg, "icon", "", "")
		fs.StringVar(&p.IconURL, "icon-url", "", "")
		fs.StringVar(&p.Category, "category", "", "")
		fs.StringVar(&p.Runtime, "runtime", "", "")
		fs.StringVar(&p.Links, "links", "", "")
		fs.StringVar(&p.Notifications, "notifications", "", "")
		fs.Var(mail, "mail-links", "")
		fs.BoolVar(&p.NewCopy, "new-copy", false, "")
		fs.BoolVar(&p.Launch, "launch", false, "")
	})
	if !ok {
		return 2
	}
	switch {
	case len(pos) == 1 && p.Token == "":
		p.URL = pos[0]
	case len(pos) == 0 && p.Token != "":
	default:
		return c.usageError(j, "arctic-webapp install needs a web address or --preview TOKEN.")
	}
	if mail.v != nil {
		p.MailLinks = *mail.v
	}
	switch {
	case iconArg == "":
	case iconArg == "monogram":
		p.Icon = json.RawMessage(`"monogram"`)
	case strings.Trim(iconArg, "0123456789") == "":
		p.Icon = json.RawMessage(iconArg)
	default:
		p.IconFile = absPath(iconArg)
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	ctx, stop := signalContext()
	defer stop()
	res, err := m.Install(ctx, p)
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, res, func(w io.Writer) {
		fmt.Fprintf(w, "Added %s (%s)\n", res.App.Name, res.App.ID)
	})
}

func absPath(p string) string {
	if strings.HasPrefix(p, "/") {
		return p
	}
	wd, err := os.Getwd()
	if err != nil {
		return p
	}
	return wd + "/" + p
}

func (c *cli) cmdUpdate(args []string) int {
	var all *bool
	_, pos, j, ok := c.flags("update", args, func(fs *flag.FlagSet) { all = fs.Bool("all", false, "") })
	if !ok {
		return 2
	}
	if len(pos) == 0 && !*all || len(pos) > 0 && *all {
		return c.usageError(j, "arctic-webapp update needs app ids or --all.")
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	ctx, stop := signalContext()
	defer stop()
	res, err := m.Update(ctx, pos, *all)
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, res, func(w io.Writer) {
		for _, u := range res.Updated {
			fmt.Fprintf(w, "%s: changed %s; kept %s\n", u.ID, list(u.Changed), list(u.Kept))
		}
	})
}

func list(s []string) string {
	if len(s) == 0 {
		return "nothing"
	}
	return strings.Join(s, ", ")
}

func (c *cli) cmdSet(args []string) int {
	var p api.SetParams
	name, icon, iconURL, category, runtime, links, notif, rendering := &optString{}, &optString{}, &optString{}, &optString{}, &optString{}, &optString{}, &optString{}, &optString{}
	mail, devtools := &onOff{}, &onOff{}
	_, pos, j, ok := c.flags("set", args, func(fs *flag.FlagSet) {
		fs.Var(name, "name", "")
		fs.Var(icon, "icon", "")
		fs.Var(iconURL, "icon-url", "")
		fs.Var(category, "category", "")
		fs.Var(runtime, "runtime", "")
		fs.Var(links, "links", "")
		fs.StringVar(&p.AddDomain, "add-domain", "", "")
		fs.StringVar(&p.RemoveDomain, "remove-domain", "", "")
		fs.Var(notif, "notifications", "")
		fs.Var(mail, "mail-links", "")
		fs.Var(devtools, "devtools", "")
		fs.Var(rendering, "rendering", "")
		fs.BoolVar(&p.ResetPermissions, "reset-permissions", false, "")
		fs.StringVar(&p.ForgetCertificate, "forget-certificate", "", "")
	})
	if !ok || !c.needIDs("set", j, pos, 1, 1) {
		return 2
	}
	p.ID = pos[0]
	p.Name, p.Category, p.Runtime, p.Links, p.Notifications, p.Rendering = name.v, category.v, runtime.v, links.v, notif.v, rendering.v
	p.MailLinks, p.Devtools = mail.v, devtools.v
	switch {
	case iconURL.v != nil:
		p.Icon = &api.SetIcon{URL: *iconURL.v}
	case icon.v != nil && *icon.v == "monogram":
		p.Icon = &api.SetIcon{Monogram: true}
	case icon.v != nil && *icon.v == "site":
		p.Icon = &api.SetIcon{}
	case icon.v != nil:
		p.Icon = &api.SetIcon{File: absPath(*icon.v)}
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	ctx, stop := signalContext()
	defer stop()
	res, err := m.Set(ctx, p)
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, res, func(w io.Writer) {
		msg := map[string]string{"live": "applied to the open window", "next_start": "applies the next time it starts", "saved": "saved"}[res.Applied]
		fmt.Fprintf(w, "%s: %s\n", res.App.Name, msg)
	})
}

// cmdIcon is the host's favicon upgrade.
func (c *cli) cmdIcon(args []string) int {
	var file, source *string
	_, pos, j, ok := c.flags("icon", args, func(fs *flag.FlagSet) {
		file = fs.String("from-file", "", "")
		source = fs.String("source", "", "")
	})
	if !ok || !c.needIDs("icon", j, pos, 1, 1) {
		return 2
	}
	if *file == "" {
		return c.usageError(j, "arctic-webapp icon needs --from-file.")
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	changed, err := m.IconFromFile(pos[0], *file, *source)
	if err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, map[string]any{"changed": changed}, nil)
}

func (c *cli) cmdTrust(args []string) int {
	var host, pemFile *string
	_, pos, j, ok := c.flags("trust-certificate", args, func(fs *flag.FlagSet) {
		host = fs.String("host", "", "")
		pemFile = fs.String("pem", "", "")
	})
	if !ok || !c.needIDs("trust-certificate", j, pos, 1, 1) {
		return 2
	}
	if *host == "" || *pemFile == "" {
		return c.usageError(j, "arctic-webapp trust-certificate needs --host and --pem.")
	}
	m, code := c.manager(j)
	if m == nil {
		return code
	}
	if err := m.TrustCertificate(pos[0], *host, *pemFile); err != nil {
		return c.fail(j, err)
	}
	return c.ok(j, api.Empty{}, nil)
}
