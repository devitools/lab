package registry

import (
	"context"
	"sync"
	"time"
)

type Entry struct {
	Slug      string
	CreatedAt time.Time
	conn      TunnelConn
}

type TunnelConn interface {
	SendRequest(ctx context.Context, env []byte) ([]byte, error)
	Close() error
}

func (e *Entry) Conn() TunnelConn { return e.conn }

type Registry struct {
	mu      sync.RWMutex
	entries map[string]*Entry
}

func New() *Registry {
	return &Registry{entries: map[string]*Entry{}}
}

func (r *Registry) Get(slug string) *Entry {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.entries[slug]
}

func (r *Registry) PutTunnel(slug string, conn TunnelConn) *Entry {
	e := &Entry{
		Slug:      slug,
		CreatedAt: time.Now(),
		conn:      conn,
	}
	r.mu.Lock()
	r.entries[slug] = e
	r.mu.Unlock()
	return e
}

func (r *Registry) Remove(slug string) {
	r.mu.Lock()
	delete(r.entries, slug)
	r.mu.Unlock()
}
