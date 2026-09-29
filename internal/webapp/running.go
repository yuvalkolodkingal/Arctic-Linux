package webapp

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// ProcRoot is /proc; tests point it at a fake tree.
var ProcRoot = "/proc"

// WritePid records pid as the app's running process. The WebKit host writes it only in its
// primary instance (GApplication startup); `run` writes it for a Chromium runtime only when no
// live pid is recorded (a second start would otherwise overwrite the running app's pid).
func (p Paths) WritePid(id string, pid int) error {
	if !Valid(id) {
		return errors.New("bad id")
	}
	if err := p.EnsureRuntimeDir(); err != nil {
		return err
	}
	return WriteFileAtomic(p.PidFile(id), []byte(strconv.Itoa(pid)+"\n"), 0o600)
}

// RemovePid deletes the pid file if it still names pid.
func (p Paths) RemovePid(id string, pid int) {
	if got, _ := p.readPid(id); got == pid {
		os.Remove(p.PidFile(id))
	}
}

func (p Paths) readPid(id string) (int, error) {
	data, err := os.ReadFile(p.PidFile(id))
	if err != nil {
		return 0, err
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(data)))
	if err != nil || pid <= 1 {
		return 0, errors.New("bad pid file")
	}
	return pid, nil
}

// RunningPid returns the app's live pid, or 0. A pid counts only while /proc/<pid>/cmdline still
// names this app (the host's --app-id <id>, or a browser's --user-data-dir inside the app's
// directories), so a recycled pid is never signalled.
func (p Paths) RunningPid(id string) int {
	if !Valid(id) {
		return 0
	}
	pid, err := p.readPid(id)
	if err != nil {
		return 0
	}
	cmd, err := os.ReadFile(filepath.Join(ProcRoot, strconv.Itoa(pid), "cmdline"))
	if err != nil {
		return 0
	}
	for _, arg := range bytes.Split(cmd, []byte{0}) {
		a := string(arg)
		if a == id || strings.HasSuffix(a, "/"+id) || strings.Contains(a, "/"+id+"/") {
			return pid
		}
	}
	return 0
}

// Signal sends sig to the running app; false when it isn't running.
func (p Paths) Signal(id string, sig syscall.Signal) bool {
	pid := p.RunningPid(id)
	if pid == 0 {
		return false
	}
	return syscall.Kill(pid, sig) == nil
}

// Stop asks the running app to quit (SIGTERM) and waits up to wait for it to go. It reports
// whether the app was running, and an error when it is still running afterwards.
func (p Paths) Stop(id string, wait time.Duration) (bool, error) {
	pid := p.RunningPid(id)
	if pid == 0 {
		return false, nil
	}
	syscall.Kill(pid, syscall.SIGTERM)
	deadline := time.Now().Add(wait)
	for time.Now().Before(deadline) {
		if p.RunningPid(id) == 0 || !alive(pid) {
			os.Remove(p.PidFile(id))
			return true, nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return true, Errorf(CodeState, "The app is still open. Close it and try again.")
}

func alive(pid int) bool {
	err := syscall.Kill(pid, 0)
	if err != nil {
		return false
	}
	// A zombie still answers kill(0); it is gone for our purposes.
	st, err := os.ReadFile(filepath.Join(ProcRoot, strconv.Itoa(pid), "stat"))
	if err != nil {
		return false
	}
	if i := bytes.LastIndexByte(st, ')'); i >= 0 && i+2 < len(st) {
		return st[i+2] != 'Z'
	}
	return true
}
