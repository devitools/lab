package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/devitools/lab/server/internal/publish"
	"github.com/devitools/lab/server/internal/registry"
	"github.com/devitools/lab/server/internal/server"
	"github.com/devitools/lab/server/internal/tunnel"
)

func main() {
	cfg := server.Config{
		Listen:        envOr("LAB_LISTEN", ":8080"),
		RootDomain:    envOr("LAB_ROOT_DOMAIN", "devi.tools"),
		AdminHost:     envOr("LAB_ADMIN_HOST", "lab.devi.tools"),
		SitesDir:      envOr("LAB_SITES_DIR", "/srv/sites"),
		MaxUploadMB:   50,
		TunnelTimeout: 30 * time.Second,
	}

	if err := os.MkdirAll(cfg.SitesDir, 0o755); err != nil {
		log.Fatalf("create sites dir: %v", err)
	}

	reg, err := registry.Load(cfg.SitesDir)
	if err != nil {
		log.Fatalf("load registry: %v", err)
	}

	pub := publish.New(reg, cfg.SitesDir, cfg.MaxUploadMB)
	tun := tunnel.New(reg, cfg.TunnelTimeout)

	srv := server.New(cfg, reg, pub, tun)

	httpServer := &http.Server{
		Addr:              cfg.Listen,
		Handler:           srv,
		ReadHeaderTimeout: 15 * time.Second,
	}

	go reg.RunGC(context.Background(), time.Hour, 30*24*time.Hour)

	go func() {
		log.Printf("lab listening on %s, root=%s admin=%s", cfg.Listen, cfg.RootDomain, cfg.AdminHost)
		if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("listen: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	log.Println("shutting down…")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpServer.Shutdown(ctx)
	tun.CloseAll()
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
