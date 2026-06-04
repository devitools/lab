package registry

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"
)

type Mode string

const (
	ModeStatic Mode = "static"
	ModeTunnel Mode = "tunnel"
)

type Entry struct {
	Slug       string    `json:"slug"`
	Mode       Mode      `json:"mode"`
	Dir        string    `json:"dir,omitempty"`
	CreatedAt  time.Time `json:"created_at"`
	lastAccess atomic.Int64

	conn TunnelConn `json:"-"`
}

type TunnelConn interface {
	SendRequest(ctx context.Context, env []byte) ([]byte, error)
	Close() error
}

func (e *Entry) Touch() {
	e.lastAccess.Store(time.Now().Unix())
}

func (e *Entry) LastAccess() time.Time {
	return time.Unix(e.lastAccess.Load(), 0)
}

func (e *Entry) Conn() TunnelConn { return e.conn }

type Registry struct {
	mu      sync.RWMutex
	entries map[string]*Entry
	path    string
}

func Load(sitesDir string) (*Registry, error) {
	r := &Registry{
		entries: map[string]*Entry{},
		path:    filepath.Join(sitesDir, ".registry.json"),
	}
	data, err := os.ReadFile(r.path)
	if err != nil {
		if os.IsNotExist(err) {
			return r, nil
		}
		return nil, err
	}
	var snap []*Entry
	if err := json.Unmarshal(data, &snap); err != nil {
		return nil, fmt.Errorf("parse registry: %w", err)
	}
	now := time.Now().Unix()
	for _, e := range snap {
		if e.Mode != ModeStatic {
			continue
		}
		e.lastAccess.Store(now)
		r.entries[e.Slug] = e
	}
	return r, nil
}

func (r *Registry) Get(slug string) *Entry {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.entries[slug]
}

func (r *Registry) PutStatic(slug, dir string) *Entry {
	e := &Entry{
		Slug:      slug,
		Mode:      ModeStatic,
		Dir:       dir,
		CreatedAt: time.Now(),
	}
	e.Touch()
	r.mu.Lock()
	r.entries[slug] = e
	r.mu.Unlock()
	r.persist()
	return e
}

func (r *Registry) PutTunnel(slug string, conn TunnelConn) *Entry {
	e := &Entry{
		Slug:      slug,
		Mode:      ModeTunnel,
		CreatedAt: time.Now(),
		conn:      conn,
	}
	e.Touch()
	r.mu.Lock()
	r.entries[slug] = e
	r.mu.Unlock()
	return e
}

func (r *Registry) Remove(slug string) {
	r.mu.Lock()
	e, ok := r.entries[slug]
	delete(r.entries, slug)
	r.mu.Unlock()
	if !ok {
		return
	}
	if e.Mode == ModeStatic {
		if e.Dir != "" {
			_ = os.RemoveAll(e.Dir)
		}
		r.persist()
	}
}

func (r *Registry) persist() {
	r.mu.RLock()
	snap := make([]*Entry, 0, len(r.entries))
	for _, e := range r.entries {
		if e.Mode == ModeStatic {
			snap = append(snap, e)
		}
	}
	r.mu.RUnlock()

	data, err := json.MarshalIndent(snap, "", "  ")
	if err != nil {
		log.Printf("registry marshal: %v", err)
		return
	}
	tmp := r.path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		log.Printf("registry write: %v", err)
		return
	}
	if err := os.Rename(tmp, r.path); err != nil {
		log.Printf("registry rename: %v", err)
	}
}

func (r *Registry) RunGC(ctx context.Context, interval, ttl time.Duration) {
	t := time.NewTicker(interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			r.gcOnce(ttl)
		}
	}
}

func (r *Registry) gcOnce(ttl time.Duration) {
	cutoff := time.Now().Add(-ttl).Unix()
	var stale []string
	r.mu.RLock()
	for slug, e := range r.entries {
		if e.Mode == ModeStatic && e.lastAccess.Load() < cutoff {
			stale = append(stale, slug)
		}
	}
	r.mu.RUnlock()
	for _, slug := range stale {
		log.Printf("gc: removing stale slug %s", slug)
		r.Remove(slug)
	}
}
