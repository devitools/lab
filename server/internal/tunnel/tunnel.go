package tunnel

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/coder/websocket"
	"github.com/google/uuid"

	"github.com/devitools/lab/server/internal/registry"
)

type Handler struct {
	reg     *registry.Registry
	timeout time.Duration

	mu    sync.Mutex
	conns map[string]*Conn
}

func New(reg *registry.Registry, timeout time.Duration) *Handler {
	return &Handler{
		reg:     reg,
		timeout: timeout,
		conns:   map[string]*Conn{},
	}
}

func (h *Handler) Accept(w http.ResponseWriter, r *http.Request, rootDomain string) {
	friendly := r.URL.Query().Get("friendly")
	slug, err := registry.NewSlug(friendly)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	wsConn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		InsecureSkipVerify: true,
	})
	if err != nil {
		log.Printf("tunnel: ws accept: %v", err)
		return
	}
	wsConn.SetReadLimit(64 << 20)

	c := newConn(slug, wsConn, h.timeout)
	h.track(slug, c)
	defer h.untrack(slug)

	h.reg.PutTunnel(slug, c)
	defer h.reg.Remove(slug)

	url := fmt.Sprintf("https://%s.%s", slug, rootDomain)
	if err := c.writeEnvelope(envelope{Type: "hello", URL: url, Slug: slug}); err != nil {
		log.Printf("tunnel: send hello: %v", err)
		return
	}
	log.Printf("tunnel: opened slug=%s", slug)

	c.runReader(r.Context())
	log.Printf("tunnel: closed slug=%s", slug)
}

func (h *Handler) Forward(w http.ResponseWriter, r *http.Request, entry *registry.Entry) {
	conn := entry.Conn()
	if conn == nil {
		http.Error(w, "tunnel offline", http.StatusBadGateway)
		return
	}

	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 16<<20))
	if err != nil {
		http.Error(w, "body too large", http.StatusRequestEntityTooLarge)
		return
	}

	req := envelope{
		Type:    "req",
		ID:      uuid.NewString(),
		Method:  r.Method,
		Path:    r.URL.RequestURI(),
		Headers: copyHeaders(r.Header),
		Body:    base64.StdEncoding.EncodeToString(body),
	}
	reqBytes, err := json.Marshal(req)
	if err != nil {
		http.Error(w, "marshal", http.StatusInternalServerError)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), h.timeout)
	defer cancel()

	respBytes, err := conn.SendRequest(ctx, reqBytes)
	if err != nil {
		http.Error(w, "tunnel error: "+err.Error(), http.StatusBadGateway)
		return
	}

	var resp envelope
	if err := json.Unmarshal(respBytes, &resp); err != nil {
		http.Error(w, "bad response from client", http.StatusBadGateway)
		return
	}

	for k, vs := range resp.Headers {
		if hopByHop[k] {
			continue
		}
		for _, v := range vs {
			w.Header().Add(k, v)
		}
	}
	status := resp.Status
	if status == 0 {
		status = http.StatusOK
	}
	w.WriteHeader(status)
	if resp.Body != "" {
		decoded, err := base64.StdEncoding.DecodeString(resp.Body)
		if err == nil {
			_, _ = w.Write(decoded)
		}
	}
}

func (h *Handler) CloseAll() {
	h.mu.Lock()
	conns := make([]*Conn, 0, len(h.conns))
	for _, c := range h.conns {
		conns = append(conns, c)
	}
	h.mu.Unlock()
	for _, c := range conns {
		_ = c.Close()
	}
}

func (h *Handler) track(slug string, c *Conn) {
	h.mu.Lock()
	h.conns[slug] = c
	h.mu.Unlock()
}

func (h *Handler) untrack(slug string) {
	h.mu.Lock()
	delete(h.conns, slug)
	h.mu.Unlock()
}

type envelope struct {
	Type    string              `json:"type"`
	ID      string              `json:"id,omitempty"`
	URL     string              `json:"url,omitempty"`
	Slug    string              `json:"slug,omitempty"`
	Method  string              `json:"method,omitempty"`
	Path    string              `json:"path,omitempty"`
	Headers map[string][]string `json:"headers,omitempty"`
	Body    string              `json:"body,omitempty"`
	Status  int                 `json:"status,omitempty"`
}

type Conn struct {
	slug    string
	ws      *websocket.Conn
	timeout time.Duration

	writeMu sync.Mutex

	pendMu  sync.Mutex
	pending map[string]chan []byte

	closed chan struct{}
}

func newConn(slug string, ws *websocket.Conn, timeout time.Duration) *Conn {
	return &Conn{
		slug:    slug,
		ws:      ws,
		timeout: timeout,
		pending: map[string]chan []byte{},
		closed:  make(chan struct{}),
	}
}

func (c *Conn) SendRequest(ctx context.Context, env []byte) ([]byte, error) {
	var req envelope
	if err := json.Unmarshal(env, &req); err != nil {
		return nil, err
	}
	id := req.ID

	ch := make(chan []byte, 1)
	c.pendMu.Lock()
	c.pending[id] = ch
	c.pendMu.Unlock()
	defer func() {
		c.pendMu.Lock()
		delete(c.pending, id)
		c.pendMu.Unlock()
	}()

	if err := c.writeRaw(env); err != nil {
		return nil, err
	}

	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-c.closed:
		return nil, errors.New("tunnel closed")
	case resp := <-ch:
		return resp, nil
	}
}

func (c *Conn) Close() error {
	select {
	case <-c.closed:
		return nil
	default:
	}
	close(c.closed)
	return c.ws.Close(websocket.StatusNormalClosure, "bye")
}

func (c *Conn) writeEnvelope(e envelope) error {
	data, err := json.Marshal(e)
	if err != nil {
		return err
	}
	return c.writeRaw(data)
}

func (c *Conn) writeRaw(data []byte) error {
	c.writeMu.Lock()
	defer c.writeMu.Unlock()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return c.ws.Write(ctx, websocket.MessageText, data)
}

func (c *Conn) runReader(ctx context.Context) {
	defer c.Close()
	for {
		typ, data, err := c.ws.Read(ctx)
		if err != nil {
			return
		}
		if typ != websocket.MessageText {
			continue
		}
		var head struct {
			Type string `json:"type"`
			ID   string `json:"id"`
		}
		if err := json.Unmarshal(data, &head); err != nil {
			continue
		}
		switch head.Type {
		case "resp":
			c.pendMu.Lock()
			ch, ok := c.pending[head.ID]
			c.pendMu.Unlock()
			if ok {
				select {
				case ch <- data:
				default:
				}
			}
		case "pong":
		}
	}
}

func copyHeaders(h http.Header) map[string][]string {
	out := make(map[string][]string, len(h))
	for k, v := range h {
		if hopByHop[k] {
			continue
		}
		out[k] = append([]string(nil), v...)
	}
	return out
}

var hopByHop = map[string]bool{
	"Connection":          true,
	"Proxy-Connection":    true,
	"Keep-Alive":          true,
	"Proxy-Authenticate":  true,
	"Proxy-Authorization": true,
	"Te":                  true,
	"Trailer":             true,
	"Transfer-Encoding":   true,
	"Upgrade":             true,
}
