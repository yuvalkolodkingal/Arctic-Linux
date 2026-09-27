package engine

import (
	"bufio"
	"context"
	"encoding/json"
	"io"
	"sync"
	"sync/atomic"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
)

var sessionIDs atomic.Int64

// Session is one client connection. Responses and events share one ordered queue that a
// writer goroutine drains, so a slow client never blocks the engine for long.
type Session struct {
	id         int64
	out        chan []byte
	quit       chan struct{}
	once       sync.Once
	subscribed atomic.Bool
}

const sessionQueue = 4096

// NewSession registers a connection.
func (e *Engine) NewSession() *Session {
	s := &Session{id: sessionIDs.Add(1), out: make(chan []byte, sessionQueue), quit: make(chan struct{})}
	e.mu.Lock()
	e.sessions[s] = true
	e.mu.Unlock()
	return s
}

// CloseSession unregisters a connection.
func (e *Engine) CloseSession(s *Session) {
	e.mu.Lock()
	delete(e.sessions, s)
	e.mu.Unlock()
	s.once.Do(func() { close(s.quit) })
}

// send queues a line. droppable lines (progress ticks) are dropped when the queue is full;
// others wait up to 5 s, then the session is considered dead.
func (s *Session) send(v any, droppable bool) {
	b, err := json.Marshal(v)
	if err != nil {
		return
	}
	b = append(b, '\n')
	select {
	case <-s.quit:
		return
	default:
	}
	if droppable {
		select {
		case s.out <- b:
		default:
		}
		return
	}
	t := time.NewTimer(5 * time.Second)
	defer t.Stop()
	select {
	case s.out <- b:
	case <-s.quit:
	case <-t.C:
		s.once.Do(func() { close(s.quit) })
	}
}

// subscribeAndReply marks the session subscribed, then queues the {"ok":true} response and a
// replay of the current install state (so a reconnecting UI can draw at once) before any new
// event can be broadcast: everything happens under the engine lock.
func (e *Engine) subscribeAndReply(s *Session, id json.RawMessage) {
	e.mu.Lock()
	defer e.mu.Unlock()
	s.send(protocol.Response{ID: id, Result: protocol.OKResult{OK: true}}, false)
	if s.subscribed.Swap(true) {
		return
	}
	if e.lastProg != nil {
		s.send(*e.lastProg, false)
	}
	for _, m := range e.moduleListLocked() {
		s.send(m, false)
	}
	if e.attention != nil {
		s.send(*e.attention, false)
	}
	if e.failed != nil {
		s.send(*e.failed, false)
	}
	if e.doneEv != nil {
		s.send(*e.doneEv, false)
	}
}

// AddListener registers an in-process event listener (used by `arctic-install unattended`).
// fn runs with the engine lock held: it must be quick and must not call the engine.
func (e *Engine) AddListener(fn func(ev any)) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.listeners = append(e.listeners, fn)
}

// broadcastLocked sends an event to every subscribed session. Called with e.mu held.
func (e *Engine) broadcastLocked(ev any, droppable bool) {
	for _, fn := range e.listeners {
		fn(ev)
	}
	for s := range e.sessions {
		if s.subscribed.Load() {
			s.send(ev, droppable)
		}
	}
}

// ServeConn runs the JSON-lines protocol on one connection until r ends or ctx is done.
func (e *Engine) ServeConn(ctx context.Context, r io.Reader, w io.Writer) error {
	s := e.NewSession()
	defer e.CloseSession(s)
	writeErr := make(chan error, 1)
	go func() {
		bw := bufio.NewWriter(w)
		for {
			select {
			case b := <-s.out:
				if _, err := bw.Write(b); err != nil {
					writeErr <- err
					s.once.Do(func() { close(s.quit) })
					return
				}
				// Flush when the queue is drained.
				if len(s.out) == 0 {
					if err := bw.Flush(); err != nil {
						writeErr <- err
						s.once.Do(func() { close(s.quit) })
						return
					}
				}
			case <-s.quit:
				// Drain what is already queued, best effort.
				for {
					select {
					case b := <-s.out:
						bw.Write(b)
					default:
						bw.Flush()
						writeErr <- nil
						return
					}
				}
			}
		}
	}()

	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64*1024), 4*1024*1024)
	for sc.Scan() {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-s.quit:
			return nil
		default:
		}
		line := sc.Bytes()
		if len(trimSpace(line)) == 0 {
			continue
		}
		var req protocol.Request
		if err := json.Unmarshal(line, &req); err != nil {
			s.send(protocol.Response{Error: protocol.Errorf(protocol.CodeBadRequest, "not a JSON request: %v", err)}, false)
			continue
		}
		if req.Method == "" {
			s.send(protocol.Response{ID: req.ID, Error: protocol.Errorf(protocol.CodeBadRequest, "missing method")}, false)
			continue
		}
		if req.Method == protocol.MethodSubscribe {
			e.log.Printf("-> %s (session %d)", req.Method, s.id)
			e.subscribeAndReply(s, req.ID)
			continue
		}
		s.send(e.Handle(ctx, s, req), false)
	}
	// The client is done sending: flush every queued response before returning.
	err := sc.Err()
	e.CloseSession(s)
	if werr := <-writeErr; err == nil {
		err = werr
	}
	return err
}

func trimSpace(b []byte) []byte {
	for len(b) > 0 && (b[0] == ' ' || b[0] == '\t' || b[0] == '\r') {
		b = b[1:]
	}
	for len(b) > 0 && (b[len(b)-1] == ' ' || b[len(b)-1] == '\t' || b[len(b)-1] == '\r') {
		b = b[:len(b)-1]
	}
	return b
}
