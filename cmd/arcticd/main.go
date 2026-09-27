// Command arcticd is the Arctic Linux installer engine. It runs as root, socket-activated by
// arcticd.socket (ListenStream=/run/arcticd.sock, group wheel), and speaks the JSON-lines
// protocol of BUILD-SPEC §4. With --mock it simulates disks, Wi-Fi and the install and never
// touches the system.
//
//	arcticd [--socket /run/arcticd.sock] [--mock] [--catalog DIR] [--log FILE|-]
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/daemon"
)

func main() {
	var cfg daemon.Config
	socket := flag.String("socket", daemon.DefaultSocket, "unix socket to listen on (ignored under socket activation)")
	flag.BoolVar(&cfg.Mock, "mock", false, "simulate everything; never touch the system")
	flag.StringVar(&cfg.CatalogDir, "catalog", "", "catalog directory (default /usr/share/arctic/catalog, else the embedded copy)")
	flag.StringVar(&cfg.LogPath, "log", "", "engine log file, - for stderr (default "+daemon.DefaultLogPath+"; mock: $TMPDIR/arctic-install-mock/engine.log)")
	flag.StringVar(&cfg.Target, "target", "/mnt", "mount point for the new system")
	flag.Float64Var(&cfg.MockOptions.Speed, "mock-speed", 1, "mock: divide every delay by this")
	flag.StringVar(&cfg.MockOptions.FailModule, "mock-fail", "", "mock: optional app whose first download fails (\"none\" for no failure)")
	flag.BoolVar(&cfg.MockOptions.Wired, "mock-wired", false, "mock: start with a cable plugged in")
	version := flag.Bool("version", false, "print the version")
	flag.Parse()
	if *version {
		fmt.Println("arcticd", backend.EngineVersion)
		return
	}
	cfg.Env()
	if !cfg.Mock && os.Geteuid() != 0 {
		fmt.Fprintln(os.Stderr, "arcticd: the real engine must run as root (use --mock for development)")
		os.Exit(1)
	}
	e, closeFn, err := daemon.NewEngine(cfg)
	if err != nil {
		fmt.Fprintln(os.Stderr, "arcticd:", err)
		os.Exit(1)
	}
	defer closeFn()
	l, activated, err := daemon.Listen(*socket)
	if err != nil {
		fmt.Fprintln(os.Stderr, "arcticd:", err)
		os.Exit(1)
	}
	if !activated {
		defer os.Remove(*socket)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	fmt.Fprintf(os.Stderr, "arcticd %s listening on %s (mock=%v, socket-activated=%v)\n", backend.EngineVersion, l.Addr(), cfg.Mock, activated)
	if err := daemon.Serve(ctx, l, e); err != nil {
		fmt.Fprintln(os.Stderr, "arcticd:", err)
		os.Exit(1)
	}
}
