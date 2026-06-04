package static

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

func Serve(w http.ResponseWriter, r *http.Request, dir string) {
	clean := filepath.Clean(r.URL.Path)
	if clean == "/" || clean == "." {
		clean = "/index.html"
	}

	target := filepath.Join(dir, filepath.FromSlash(clean))
	rel, err := filepath.Rel(dir, target)
	if err != nil || strings.HasPrefix(rel, "..") {
		http.NotFound(w, r)
		return
	}

	info, err := os.Stat(target)
	if err != nil || info.IsDir() {
		if info != nil && info.IsDir() {
			idx := filepath.Join(target, "index.html")
			if _, e := os.Stat(idx); e == nil {
				http.ServeFile(w, r, idx)
				return
			}
		}
		fallback := filepath.Join(dir, "index.html")
		if _, e := os.Stat(fallback); e == nil {
			w.Header().Set("Cache-Control", "no-cache")
			http.ServeFile(w, r, fallback)
			return
		}
		http.NotFound(w, r)
		return
	}

	http.ServeFile(w, r, target)
}
