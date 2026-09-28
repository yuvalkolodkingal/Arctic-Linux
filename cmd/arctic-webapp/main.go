// Command arctic-webapp manages Arctic's web apps: any website as an app with its own window,
// icon, launcher entry and sign-in (docs/BUILD-SPEC.md §11 "Web apps"). It is pure Go and never
// loads GTK or WebKit; each app's window is /usr/libexec/arctic/arctic-webapp-host.
//
//	arctic-webapp inspect URL [--json]
//	arctic-webapp install (URL | --preview TOKEN) [--name NAME] [--icon INDEX|monogram|FILE] [--icon-url URL]
//	                      [--category CAT] [--runtime webkit|chromium:VARIANT] [--links browser|app]
//	                      [--notifications allow|ask|block] [--mail-links on|off] [--new-copy] [--launch] [--json]
//	arctic-webapp list [--sizes] [--kept] [--json]
//	arctic-webapp show ID [--sizes] [--json]
//	arctic-webapp run ID [URI] [--url URL] [--inspect]   the launcher entry's Exec: execs the runtime
//	arctic-webapp launch ID [--url URL] [--json]        run, detached (the shell and Settings)
//	arctic-webapp update (ID… | --all) [--json]         re-discover name, manifest and icon
//	arctic-webapp set ID [--name N] [--icon FILE|monogram|site] [--icon-url URL] [--category C] [--runtime R]
//	                  [--links browser|app] [--add-domain HOST] [--remove-domain HOST]
//	                  [--notifications allow|ask|block] [--mail-links on|off] [--devtools on|off]
//	                  [--rendering auto|software] [--reset-permissions] [--forget-certificate HOST] [--json]
//	arctic-webapp clear-data ID [--json]                sign out: delete the profile and cache, keep the app
//	arctic-webapp remove ID… [--keep-data] [--json]
//	arctic-webapp forget ID… [--json]                   delete saved sign-in data
//	arctic-webapp icon ID --from-file FILE --source host-favicon
//	arctic-webapp trust-certificate ID --host HOST --pem FILE
//	arctic-webapp repair [--json]                       rewrite launcher entries and icons from the registry
//	arctic-webapp runtimes [--json]
//	arctic-webapp serve                                 JSON lines on stdin/stdout (the shell)
//	arctic-webapp render-sample DIR                     offline fixture render (%check)
//	arctic-webapp version [--webkit] [--json]
//
// With --json the command prints exactly one line on stdout, {"ok":true,…} or
// {"ok":false,"code":…,"error":"<sentence>"[,"fields":{…}]}, and nothing else. Messages
// otherwise go to stderr prefixed "arctic-webapp: ". Exit status: 0 ok, 1 error, 2 usage.
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/manage"
)

const usage = `usage:
  arctic-webapp inspect URL [--json]
  arctic-webapp install (URL | --preview TOKEN) [--name NAME] [--icon INDEX|monogram|FILE] [--icon-url URL]
                        [--category CAT] [--runtime webkit|chromium:VARIANT] [--links browser|app]
                        [--notifications allow|ask|block] [--mail-links on|off] [--new-copy] [--launch] [--json]
  arctic-webapp list [--sizes] [--kept] [--json]
  arctic-webapp show ID [--sizes] [--json]
  arctic-webapp run ID [URI] [--url URL] [--inspect]
  arctic-webapp launch ID [--url URL] [--json]
  arctic-webapp update (ID... | --all) [--json]
  arctic-webapp set ID [--name N] [--icon FILE|monogram|site] [--icon-url URL] [--category C] [--runtime R]
                    [--links browser|app] [--add-domain HOST] [--remove-domain HOST]
                    [--notifications allow|ask|block] [--mail-links on|off] [--devtools on|off]
                    [--rendering auto|software] [--reset-permissions] [--forget-certificate HOST] [--json]
  arctic-webapp clear-data ID [--json]
  arctic-webapp remove ID... [--keep-data] [--json]
  arctic-webapp forget ID... [--json]
  arctic-webapp icon ID --from-file FILE --source host-favicon
  arctic-webapp trust-certificate ID --host HOST --pem FILE
  arctic-webapp repair [--json]
  arctic-webapp runtimes [--json]
  arctic-webapp serve
  arctic-webapp render-sample DIR
  arctic-webapp version [--webkit] [--json]
`

// cli carries the process's streams so tests can run commands in-process.
type cli struct {
	stdin  io.Reader
	stdout io.Writer
	stderr io.Writer
	// newManager is manage.New, replaceable in tests.
	newManager func() (*manage.Manager, error)
	// terminal: stderr is a terminal (progress lines only then, never in --json mode).
	terminal bool
	// euid is os.Geteuid (tests run as root in CI containers).
	euid func() int
}

func main() {
	c := &cli{stdin: os.Stdin, stdout: os.Stdout, stderr: os.Stderr, newManager: manage.New, terminal: isTerminal(os.Stderr), euid: os.Geteuid}
	os.Exit(c.main(os.Args[1:]))
}

func (c *cli) main(args []string) int {
	if len(args) < 1 {
		fmt.Fprint(c.stderr, usage)
		return 2
	}
	cmd, rest := args[0], args[1:]
	switch cmd {
	case "help", "-h", "--help":
		fmt.Fprint(c.stdout, usage)
		return 0
	case "version", "--version":
		return c.cmdVersion(rest)
	}
	run, known := c.commands()[cmd]
	if !known {
		fmt.Fprintf(c.stderr, "arctic-webapp: unknown command %q\n%s", cmd, usage)
		return 2
	}
	if c.euid() == 0 && cmd != "render-sample" {
		// Web apps are per user; as root they would land in /root and its profile.
		return c.fail(jsonWanted(rest), webapp.Errorf(webapp.CodeState, "Web apps are per user. Run arctic-webapp without sudo."))
	}
	return run(rest)
}

func (c *cli) commands() map[string]func([]string) int {
	return map[string]func([]string) int{
		"list": c.cmdList, "show": c.cmdShow, "run": c.cmdRun, "launch": c.cmdLaunch,
		"remove": c.cmdRemove, "forget": c.cmdForget, "clear-data": c.cmdClearData,
		"repair": c.cmdRepair, "runtimes": c.cmdRuntimes,
	}
}

func jsonWanted(args []string) bool {
	for _, a := range args {
		if a == "--json" || a == "-json" {
			return true
		}
	}
	return false
}

// flags parses a subcommand's flags, allowing flags after positional arguments ("remove ID
// --keep-data"). Errors print usage on stderr, or one --json failure line.
func (c *cli) flags(name string, args []string, define func(fs *flag.FlagSet)) (fs *flag.FlagSet, pos []string, jsonOut bool, ok bool) {
	fs = flag.NewFlagSet(name, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	j := fs.Bool("json", false, "one line of JSON on stdout")
	if define != nil {
		define(fs)
	}
	rest := args
	for {
		if err := fs.Parse(rest); err != nil {
			c.usageError(jsonWanted(args), fmt.Sprintf("arctic-webapp %s: %v", name, err))
			return nil, nil, false, false
		}
		rest = fs.Args()
		if len(rest) == 0 {
			break
		}
		pos = append(pos, rest[0])
		rest = rest[1:]
	}
	return fs, pos, *j, true
}

// usageError reports a usage mistake: exit 2, usage on stderr, or a bad_request line.
func (c *cli) usageError(jsonOut bool, msg string) int {
	if jsonOut {
		writeJSONLine(c.stdout, false, map[string]any{"code": webapp.CodeBadRequest, "error": sentence(msg)})
	} else {
		fmt.Fprintf(c.stderr, "%s\n%s", msg, usage)
	}
	return 2
}

// fail reports an error: one --json line, or "arctic-webapp: <message>" on stderr. Exit 1.
func (c *cli) fail(jsonOut bool, err error) int {
	pe := webapp.AsError(err)
	if jsonOut {
		out := map[string]any{"code": pe.Code, "error": pe.Message}
		if pe.Code == webapp.CodeInvalid && len(pe.Fields) > 0 {
			out["fields"] = pe.Fields
		}
		writeJSONLine(c.stdout, false, out)
		return 1
	}
	msg := pe.Message
	for k, v := range pe.Fields {
		msg += "\n  " + k + ": " + v
	}
	fmt.Fprintf(c.stderr, "arctic-webapp: %s\n", msg)
	return 1
}

// ok prints a success: with --json one {"ok":true,…} line built from result (a struct or map
// whose fields follow "ok"), otherwise text.
func (c *cli) ok(jsonOut bool, result any, text func(w io.Writer)) int {
	if jsonOut {
		writeJSONLine(c.stdout, true, result)
		return 0
	}
	if text != nil {
		text(c.stdout)
	}
	return 0
}

// writeJSONLine writes {"ok":<ok>,<the fields of v>} on one line.
func writeJSONLine(w io.Writer, ok bool, v any) {
	head := `{"ok":false`
	if ok {
		head = `{"ok":true`
	}
	var body []byte
	if v != nil {
		var buf bytes.Buffer
		enc := json.NewEncoder(&buf)
		enc.SetEscapeHTML(false)
		if err := enc.Encode(v); err == nil {
			body = bytes.TrimSpace(buf.Bytes())
		}
	}
	line := head + "}"
	if len(body) > 2 && body[0] == '{' {
		line = head + "," + string(body[1:])
	}
	fmt.Fprintln(w, line)
}

// sentence ends a usage message with a full stop.
func sentence(s string) string {
	s = strings.TrimSpace(s)
	if s == "" || strings.HasSuffix(s, ".") {
		return s
	}
	return s + "."
}

func (c *cli) manager(jsonOut bool) (*manage.Manager, int) {
	m, err := c.newManager()
	if err != nil {
		return nil, c.fail(jsonOut, err)
	}
	if !jsonOut && c.terminal {
		m.Progress = func(_, msg string) { fmt.Fprintf(c.stderr, "%s…\n", msg) }
	}
	return m, 0
}

func isTerminal(f *os.File) bool {
	fi, err := f.Stat()
	return err == nil && fi.Mode()&os.ModeCharDevice != 0
}

// needID checks the positional id arguments.
func (c *cli) needIDs(name string, jsonOut bool, pos []string, min, max int) bool {
	if len(pos) < min || (max > 0 && len(pos) > max) {
		what := "an app id"
		if max != 1 {
			what = "one or more app ids"
		}
		c.usageError(jsonOut, fmt.Sprintf("arctic-webapp %s needs %s.", name, what))
		return false
	}
	return true
}
