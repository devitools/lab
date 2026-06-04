package server

import (
	_ "embed"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/devitools/lab/server/internal/publish"
	"github.com/devitools/lab/server/internal/registry"
	"github.com/devitools/lab/server/internal/static"
	"github.com/devitools/lab/server/internal/tunnel"
)

//go:embed docs_landing.html
var docsLanding []byte

var reservedSlugs = map[string]bool{
	"lab": true, "docs": true, "www": true, "api": true,
	"mail": true, "ftp": true, "smtp": true, "admin": true,
	"root": true, "dev": true, "staging": true,
}

type Config struct {
	Listen        string
	RootDomain    string
	AdminHost     string
	SitesDir      string
	MaxUploadMB   int64
	TunnelTimeout time.Duration
}

type Server struct {
	cfg     Config
	reg     *registry.Registry
	publish *publish.Handler
	tunnel  *tunnel.Handler
}

func New(cfg Config, reg *registry.Registry, pub *publish.Handler, tun *tunnel.Handler) *Server {
	return &Server{cfg: cfg, reg: reg, publish: pub, tunnel: tun}
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	host := stripPort(r.Host)

	if host == s.cfg.AdminHost {
		s.serveAdmin(w, r)
		return
	}

	slug, ok := s.slugFromHost(host)
	if !ok {
		http.Error(w, "unknown host", http.StatusNotFound)
		return
	}

	if slug == "docs" {
		writeDocsLanding(w)
		return
	}

	if reservedSlugs[slug] {
		http.Error(w, "reserved subdomain", http.StatusNotFound)
		return
	}

	entry := s.reg.Get(slug)
	if entry == nil {
		writeMissingLab(w, slug, s.cfg.RootDomain)
		return
	}
	entry.Touch()

	switch entry.Mode {
	case registry.ModeStatic:
		static.Serve(w, r, entry.Dir)
	case registry.ModeTunnel:
		s.tunnel.Forward(w, r, entry)
	default:
		http.Error(w, "invalid entry", http.StatusInternalServerError)
	}
}

func (s *Server) serveAdmin(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.URL.Path == "/health":
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	case r.URL.Path == "/publish/" || r.URL.Path == "/publish":
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		s.publish.Handle(w, r, s.cfg.RootDomain)
	case r.URL.Path == "/tunnel/" || r.URL.Path == "/tunnel":
		s.tunnel.Accept(w, r, s.cfg.RootDomain)
	case r.URL.Path == "/":
		writeDocsLanding(w)
	default:
		http.NotFound(w, r)
	}
}

func (s *Server) slugFromHost(host string) (string, bool) {
	suffix := "." + s.cfg.RootDomain
	if !strings.HasSuffix(host, suffix) {
		return "", false
	}
	slug := strings.TrimSuffix(host, suffix)
	if slug == "" || strings.Contains(slug, ".") {
		return "", false
	}
	return slug, true
}

func stripPort(host string) string {
	if i := strings.LastIndex(host, ":"); i != -1 {
		return host[:i]
	}
	return host
}

func writeDocsLanding(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "public, max-age=300")
	_, _ = w.Write(docsLanding)
}

func writeMissingLab(w http.ResponseWriter, slug, root string) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusNotFound)
	fmt.Fprintf(w, `<!doctype html><meta charset=utf-8><title>lab não encontrado</title>
<style>body{font-family:system-ui;max-width:520px;margin:80px auto;padding:0 24px;color:#222}
h1{font-size:24px;margin:0 0 8px}code{background:#f3f3f3;padding:2px 6px;border-radius:4px}</style>
<h1>lab não encontrado 🐾</h1>
<p>O lab <code>%s.%s</code> não está no ar agora.</p>
<p>Ele pode ter expirado, sido apagado, ou nunca ter existido.</p>`, slug, root)
}
