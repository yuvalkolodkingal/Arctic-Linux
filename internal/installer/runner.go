// Package installer is the real install pipeline (PLAN §6): disk, copy of the live root,
// system configuration, bootloader, the app diff and finalize. Every command and file write
// goes through a Runner, so the same code prints a dry-run plan, runs for real, or records
// its calls for golden-file tests.
package installer

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
)

// Cmd is one command.
type Cmd struct {
	Name string
	Args []string
	// Env adds KEY=VALUE pairs to the environment.
	Env []string
	// Stdin is fed to the command. Secret stdin is never printed or logged; SecretLabel
	// names it in plans ("disk passphrase").
	Stdin       []byte
	Secret      bool
	SecretLabel string
	// OnLine receives each output line (split on \n and \r) for progress parsing.
	OnLine func(line string)
	// AllowFail returns the exit code in Result instead of an error.
	AllowFail bool
	// Redact lists argument indexes printed as [secret: SecretLabel] in plans and logs.
	Redact []int
}

// String renders the command like a shell line (without stdin), secrets redacted.
func (c Cmd) String() string {
	var parts []string
	parts = append(parts, c.Env...)
	parts = append(parts, quote(c.Name))
	for i, a := range c.Args {
		redacted := false
		for _, r := range c.Redact {
			if r == i {
				redacted = true
			}
		}
		if redacted {
			parts = append(parts, "[secret: "+c.SecretLabel+"]")
			continue
		}
		parts = append(parts, quote(a))
	}
	return strings.Join(parts, " ")
}

// quote shell-quotes a word when needed.
func quote(s string) string {
	if s == "" {
		return "''"
	}
	safe := true
	for _, r := range s {
		if !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || strings.ContainsRune("-_./=:,+@%^", r)) {
			safe = false
			break
		}
	}
	if safe {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'"
}

// Result of a command.
type Result struct {
	Stdout   string
	ExitCode int
}

// Runner executes the plan.
type Runner interface {
	Run(ctx context.Context, c Cmd) (Result, error)
	WriteFile(path string, data []byte, perm fs.FileMode) error
	MkdirAll(path string, perm fs.FileMode) error
	Remove(path string) error
	Exists(path string) bool
	Glob(pattern string) ([]string, error)
	// Note records a comment (phase headers in plans, log lines when running).
	Note(format string, a ...any)
}

func fsMode(perm uint32) fs.FileMode { return fs.FileMode(perm) }

// Chroot wraps a command to run inside root.
func Chroot(root string, c Cmd) Cmd {
	c.Args = append([]string{root, c.Name}, c.Args...)
	c.Name = "chroot"
	red := make([]int, len(c.Redact))
	for i, r := range c.Redact {
		red[i] = r + 2
	}
	c.Redact = red
	return c
}

// ---- real runner ----

// ExecRunner runs commands for real. Log receives every command line (never secret stdin)
// and the command output.
type ExecRunner struct {
	Log io.Writer
	mu  sync.Mutex
}

func (r *ExecRunner) logf(format string, a ...any) {
	if r.Log == nil {
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	fmt.Fprintf(r.Log, format+"\n", a...)
}

// Note implements Runner.
func (r *ExecRunner) Note(format string, a ...any) {
	if format != "" {
		r.logf("# "+format, a...)
	}
}

// Run implements Runner.
func (r *ExecRunner) Run(ctx context.Context, c Cmd) (Result, error) {
	line := "$ " + c.String()
	if len(c.Stdin) > 0 {
		if c.Secret {
			line += " < [secret: " + c.SecretLabel + "]"
		} else {
			line += " <<EOF\n" + strings.TrimRight(string(c.Stdin), "\n") + "\nEOF"
		}
	}
	r.logf("%s", line)
	cmd := exec.CommandContext(ctx, c.Name, c.Args...)
	cmd.Env = append(os.Environ(), c.Env...)
	if len(c.Stdin) > 0 {
		cmd.Stdin = bytes.NewReader(c.Stdin)
	}
	pr, pw := io.Pipe()
	var stdout bytes.Buffer
	cmd.Stdout = io.MultiWriter(&stdout, pw)
	cmd.Stderr = pw
	tail := newTail(40)
	done := make(chan struct{})
	go func() {
		defer close(done)
		sc := bufio.NewScanner(pr)
		sc.Buffer(make([]byte, 64*1024), 1024*1024)
		sc.Split(scanLinesCR)
		for sc.Scan() {
			l := sc.Text()
			if strings.TrimSpace(l) == "" {
				continue
			}
			tail.add(l)
			if c.OnLine != nil {
				c.OnLine(l)
			}
		}
		io.Copy(io.Discard, pr)
	}()
	err := cmd.Run()
	pw.Close()
	<-done
	res := Result{Stdout: stdout.String()}
	if cmd.ProcessState != nil {
		res.ExitCode = cmd.ProcessState.ExitCode()
	}
	for _, l := range tail.lines() {
		r.logf("  | %s", l)
	}
	if err != nil {
		if c.AllowFail && ctx.Err() == nil {
			var ee *exec.ExitError
			if errors.As(err, &ee) {
				return res, nil
			}
		}
		return res, &CmdError{Cmd: c.String(), Err: err, Output: strings.Join(tail.lines(), "\n")}
	}
	return res, nil
}

// CmdError is a failed command with the end of its output.
type CmdError struct {
	Cmd    string
	Err    error
	Output string
}

func (e *CmdError) Error() string {
	if e.Output != "" {
		return fmt.Sprintf("%s: %v\n%s", e.Cmd, e.Err, e.Output)
	}
	return fmt.Sprintf("%s: %v", e.Cmd, e.Err)
}

func (e *CmdError) Unwrap() error { return e.Err }

// WriteFile implements Runner (creates parent directories).
func (r *ExecRunner) WriteFile(path string, data []byte, perm fs.FileMode) error {
	r.logf("write %s (%#o, %d bytes)", path, perm, len(data))
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(path, data, perm); err != nil {
		return err
	}
	return os.Chmod(path, perm)
}

// MkdirAll implements Runner.
func (r *ExecRunner) MkdirAll(path string, perm fs.FileMode) error {
	r.logf("mkdir -p %s", path)
	return os.MkdirAll(path, perm)
}

// Remove implements Runner (missing files are fine).
func (r *ExecRunner) Remove(path string) error {
	r.logf("rm -f %s", path)
	if err := os.Remove(path); err != nil && !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	return nil
}

// Exists implements Runner.
func (r *ExecRunner) Exists(path string) bool {
	_, err := os.Lstat(path)
	return err == nil
}

// Glob implements Runner.
func (r *ExecRunner) Glob(pattern string) ([]string, error) { return filepath.Glob(pattern) }

func scanLinesCR(data []byte, atEOF bool) (int, []byte, error) {
	for i, b := range data {
		if b == '\n' || b == '\r' {
			return i + 1, data[:i], nil
		}
	}
	if atEOF && len(data) > 0 {
		return len(data), data, nil
	}
	return 0, nil, nil
}

type tailBuf struct {
	mu  sync.Mutex
	n   int
	buf []string
}

func newTail(n int) *tailBuf { return &tailBuf{n: n} }

func (t *tailBuf) add(l string) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.buf = append(t.buf, l)
	if len(t.buf) > t.n {
		t.buf = t.buf[len(t.buf)-t.n:]
	}
}

func (t *tailBuf) lines() []string {
	t.mu.Lock()
	defer t.mu.Unlock()
	return append([]string{}, t.buf...)
}

// ---- recorder: dry-run plans and tests ----

// Recorder prints/records every operation instead of doing it. It answers queries with
// deterministic fake values so a plan can be computed without touching the machine.
type Recorder struct {
	// Out receives the plan as it is produced (optional).
	Out io.Writer
	// Lines collects the plan.
	Lines []string
	// ExistsFn answers Exists (default: DefaultExists).
	ExistsFn func(path string) bool
	// GlobFn answers Glob (default: DefaultGlob).
	GlobFn func(pattern string) []string
	// Respond answers Run: stdout, and an error to simulate a failure. nil = DefaultRespond.
	Respond func(c Cmd) (string, error)

	mu sync.Mutex
}

func (r *Recorder) emit(s string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.Lines = append(r.Lines, s)
	if r.Out != nil {
		fmt.Fprintln(r.Out, s)
	}
}

// Note implements Runner.
func (r *Recorder) Note(format string, a ...any) {
	if s := fmt.Sprintf(format, a...); s != "" {
		r.emit("# " + s)
	} else {
		r.emit("")
	}
}

// Run implements Runner.
func (r *Recorder) Run(ctx context.Context, c Cmd) (Result, error) {
	line := "$ " + c.String()
	if len(c.Stdin) > 0 {
		if c.Secret {
			line += " < [secret: " + c.SecretLabel + "]"
		} else {
			var b strings.Builder
			b.WriteString(line + " <<'EOF'")
			for _, l := range strings.Split(strings.TrimRight(string(c.Stdin), "\n"), "\n") {
				b.WriteString("\n    " + l)
			}
			b.WriteString("\n    EOF")
			line = b.String()
		}
	}
	r.emit(line)
	respond := r.Respond
	if respond == nil {
		respond = DefaultRespond
	}
	out, err := respond(c)
	if err != nil {
		if c.AllowFail {
			return Result{Stdout: out, ExitCode: 1}, nil
		}
		return Result{Stdout: out, ExitCode: 1}, &CmdError{Cmd: c.String(), Err: err}
	}
	if c.OnLine != nil {
		for _, l := range strings.Split(out, "\n") {
			if l != "" {
				c.OnLine(l)
			}
		}
	}
	return Result{Stdout: out}, nil
}

// WriteFile implements Runner.
func (r *Recorder) WriteFile(path string, data []byte, perm fs.FileMode) error {
	if len(data) == 0 {
		r.emit(fmt.Sprintf("write %s (%#o, empty)", path, perm))
		return nil
	}
	var b strings.Builder
	fmt.Fprintf(&b, "write %s (%#o)", path, perm)
	for _, l := range strings.Split(strings.TrimRight(string(data), "\n"), "\n") {
		b.WriteString("\n    | " + l)
	}
	r.emit(b.String())
	return nil
}

// MkdirAll implements Runner.
func (r *Recorder) MkdirAll(path string, perm fs.FileMode) error {
	r.emit("mkdir -p " + path)
	return nil
}

// Remove implements Runner.
func (r *Recorder) Remove(path string) error {
	r.emit("rm -f " + path)
	return nil
}

// Exists implements Runner.
func (r *Recorder) Exists(path string) bool {
	if r.ExistsFn != nil {
		return r.ExistsFn(path)
	}
	return DefaultExists(path)
}

// Glob implements Runner.
func (r *Recorder) Glob(pattern string) ([]string, error) {
	if r.GlobFn != nil {
		return r.GlobFn(pattern), nil
	}
	return DefaultGlob(pattern), nil
}

// DefaultExists pretends a Fedora 44 live system with the usual files.
func DefaultExists(path string) bool {
	switch {
	case path == "/run/rootfsbase",
		strings.HasSuffix(path, "/boot/efi"),
		strings.HasSuffix(path, "/boot/grub2/themes/arctic/theme.txt"),
		path == "/etc/NetworkManager/system-connections",
		strings.HasPrefix(path, "/dev/"), strings.HasPrefix(path, "/sys/class/block/"):
		return true
	}
	return false
}

// DefaultGlob answers the globs the installer uses.
func DefaultGlob(pattern string) []string {
	switch {
	case strings.HasSuffix(pattern, "/lib/modules/*"):
		root := strings.TrimSuffix(pattern, "/lib/modules/*")
		return []string{root + "/lib/modules/6.17.8-300.fc44.x86_64"}
	case strings.HasSuffix(pattern, "/usr/lib/efi/*/*/EFI"):
		root := strings.TrimSuffix(pattern, "/usr/lib/efi/*/*/EFI")
		return []string{root + "/usr/lib/efi/grub2/1:2.12-64.fc44/EFI", root + "/usr/lib/efi/shim/16.1-5/EFI"}
	}
	return nil
}

// DefaultRespond fakes command output: stable UUIDs for blkid, a disk nobody uses for lsblk,
// no errors.
func DefaultRespond(c Cmd) (string, error) {
	if c.Name == "blkid" && len(c.Args) > 0 {
		dev := c.Args[len(c.Args)-1]
		return FakeUUID(dev) + "\n", nil
	}
	if c.Name == "lsblk" && len(c.Args) > 0 && c.Args[0] == "--json" {
		dev := c.Args[len(c.Args)-1]
		return `{"blockdevices": [{"path": "` + dev + `", "type": "disk", "mountpoints": [null]}]}` + "\n", nil
	}
	return "", nil
}

// FakeUUID is a deterministic UUID-shaped value for a device path.
func FakeUUID(dev string) string {
	h := uint32(2166136261)
	for i := 0; i < len(dev); i++ {
		h ^= uint32(dev[i])
		h *= 16777619
	}
	return fmt.Sprintf("%08x-0000-4000-8000-%012x", h, uint64(h)*2654435761%(1<<48))
}

// Plan returns the recorded plan as text.
func (r *Recorder) Plan() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return strings.Join(r.Lines, "\n") + "\n"
}

// Commands returns only the command lines (for assertions).
func (r *Recorder) Commands() []string {
	r.mu.Lock()
	defer r.mu.Unlock()
	var out []string
	for _, l := range r.Lines {
		if strings.HasPrefix(l, "$ ") {
			out = append(out, strings.SplitN(l, "\n", 2)[0])
		}
	}
	return out
}
