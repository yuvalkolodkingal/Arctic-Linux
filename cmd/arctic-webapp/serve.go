package main

import (
	"bufio"
	"context"
	"encoding/json"
	"io"
	"sync"

	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/manage"
)

// server answers `serve` requests: JSON lines on stdin/stdout in the internal/protocol
// envelope (docs/BUILD-SPEC.md §11). Inspect, Install, Update and Set run in the background so
// Cancel and other requests are answered meanwhile; a new Inspect cancels the previous one.
type server struct {
	m   *manage.Manager
	out io.Writer

	mu          sync.Mutex // guards writes and the fields below
	cancels     map[string]context.CancelFunc
	lastInspect string
	tokens      []string
	wg          sync.WaitGroup
}

func (c *cli) cmdServe(args []string) int {
	if len(args) > 0 {
		return c.usageError(false, "arctic-webapp serve takes no arguments.")
	}
	m, code := c.manager(true)
	if m == nil {
		return code
	}
	s := &server{m: m, out: c.stdout, cancels: map[string]context.CancelFunc{}}
	s.run(c.stdin)
	return 0
}

func (s *server) run(in io.Reader) {
	sc := bufio.NewScanner(in)
	sc.Buffer(make([]byte, 64*1024), 1<<20)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var req protocol.Request
		if err := json.Unmarshal(line, &req); err != nil {
			s.reply(nil, nil, webapp.Errorf(webapp.CodeBadRequest, "That request isn’t valid JSON."))
			continue
		}
		s.handle(req)
	}
	// stdin closed: the launcher went away. Stop background work and delete our previews.
	s.mu.Lock()
	for _, cancel := range s.cancels {
		cancel()
	}
	s.mu.Unlock()
	s.wg.Wait()
	s.m.DropPreviews(s.tokens)
}

func (s *server) write(v any) {
	data, err := json.Marshal(v)
	if err != nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.out.Write(append(data, '\n'))
}

func (s *server) reply(id json.RawMessage, result any, err error) {
	if err != nil {
		s.write(protocol.Response{ID: id, Error: webapp.AsError(err)})
		return
	}
	s.write(protocol.Response{ID: id, Result: result})
}

func (s *server) changed(ids ...string) {
	if len(ids) > 0 {
		s.write(api.ChangedEvent{Event: api.EventChanged, IDs: ids})
	}
}

// manager returns a Manager whose progress becomes events for this request.
func (s *server) manager(id json.RawMessage) *manage.Manager {
	m := *s.m
	m.Progress = func(stage, msg string) {
		s.write(api.ProgressEvent{Event: api.EventProgress, Request: id, Stage: stage, Message: msg})
	}
	return &m
}

func decode(raw json.RawMessage, v any) error {
	if len(raw) == 0 {
		return nil
	}
	if err := json.Unmarshal(raw, v); err != nil {
		return webapp.Errorf(webapp.CodeBadRequest, "The request’s parameters aren’t valid.")
	}
	return nil
}

// background runs fn with a cancellable context registered under the request id; after the
// response it sends a changed event for the ids fn returns.
func (s *server) background(req protocol.Request, fn func(ctx context.Context) (any, []string, error)) {
	ctx, cancel := context.WithCancel(context.Background())
	key := string(req.ID)
	s.mu.Lock()
	s.cancels[key] = cancel
	s.mu.Unlock()
	s.wg.Add(1)
	go func() {
		defer s.wg.Done()
		defer func() {
			s.mu.Lock()
			delete(s.cancels, key)
			s.mu.Unlock()
			cancel()
		}()
		res, changed, err := fn(ctx)
		s.reply(req.ID, res, err)
		if err == nil {
			s.changed(changed...)
		}
	}()
}

func (s *server) handle(req protocol.Request) {
	m := s.manager(req.ID)
	switch req.Method {
	case api.MethodHello:
		s.reply(req.ID, api.HelloResult{EngineVersion: webapp.Version, ProtocolVersion: protocol.Version, Runtimes: m.Env.Runtimes()}, nil)
	case api.MethodRuntimes:
		s.reply(req.ID, api.RuntimesResult{Runtimes: m.Env.Runtimes()}, nil)
	case api.MethodInspect:
		var p api.InspectParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		s.mu.Lock()
		if prev, ok := s.cancels[s.lastInspect]; ok {
			prev()
		}
		s.lastInspect = string(req.ID)
		s.mu.Unlock()
		s.background(req, func(ctx context.Context) (any, []string, error) {
			pr, err := m.Inspect(ctx, p.URL)
			if err != nil {
				return nil, nil, err
			}
			s.mu.Lock()
			s.tokens = append(s.tokens, pr.Token)
			s.mu.Unlock()
			return pr, nil, nil
		})
	case api.MethodInstall:
		var p api.InstallParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		s.background(req, func(ctx context.Context) (any, []string, error) {
			res, err := m.Install(ctx, p)
			return res, []string{res.App.ID}, err
		})
	case api.MethodList:
		var p api.ListParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		res, err := m.List(p.Sizes, p.Kept)
		s.reply(req.ID, res, err)
	case api.MethodGet:
		var p api.GetParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		info, err := m.Get(p.ID, p.Sizes)
		s.reply(req.ID, api.AppResult{App: info}, err)
	case api.MethodLaunch:
		var p api.LaunchParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		res, err := m.Launch(p.ID, p.URL)
		s.reply(req.ID, res, err)
	case api.MethodUpdate:
		var p api.UpdateParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		s.background(req, func(ctx context.Context) (any, []string, error) {
			res, err := m.Update(ctx, p.IDs, p.All)
			var ids []string
			for _, u := range res.Updated {
				if len(u.Changed) > 0 {
					ids = append(ids, u.ID)
				}
			}
			return res, ids, err
		})
	case api.MethodSet:
		var p api.SetParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		// In the background: "get the icon from the site again" reads the site.
		s.background(req, func(ctx context.Context) (any, []string, error) {
			res, err := m.Set(ctx, p)
			return res, []string{p.ID}, err
		})
	case api.MethodRemove:
		var p api.RemoveParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		res, err := m.Remove(p.IDs, p.KeepData)
		s.reply(req.ID, res, err)
		if err == nil {
			s.changed(p.IDs...)
		}
	case api.MethodForget:
		var p api.IDsParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		err := m.Forget(p.IDs)
		s.reply(req.ID, api.Empty{}, err)
		if err == nil {
			s.changed(p.IDs...)
		}
	case api.MethodClearData:
		var p api.IDParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		s.reply(req.ID, api.Empty{}, m.ClearData(p.ID))
	case api.MethodCancel:
		var p api.CancelParams
		if err := decode(req.Params, &p); err != nil {
			s.reply(req.ID, nil, err)
			return
		}
		s.mu.Lock()
		if cancel, ok := s.cancels[string(p.Request)]; ok {
			cancel()
		}
		s.mu.Unlock()
		s.reply(req.ID, api.Empty{}, nil)
	default:
		s.reply(req.ID, nil, webapp.Errorf(webapp.CodeUnknown, "Unknown method %q.", req.Method))
	}
}
