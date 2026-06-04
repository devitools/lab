package publish

import (
	"archive/zip"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/devitools/lab/server/internal/registry"
)

type Handler struct {
	reg         *registry.Registry
	sitesDir    string
	maxUploadMB int64
}

func New(reg *registry.Registry, sitesDir string, maxUploadMB int64) *Handler {
	return &Handler{reg: reg, sitesDir: sitesDir, maxUploadMB: maxUploadMB}
}

type publishResponse struct {
	URL  string `json:"url"`
	Slug string `json:"slug"`
}

func (h *Handler) Handle(w http.ResponseWriter, r *http.Request, rootDomain string) {
	maxBytes := h.maxUploadMB << 20
	r.Body = http.MaxBytesReader(w, r.Body, maxBytes+(1<<20))

	if err := r.ParseMultipartForm(32 << 20); err != nil {
		http.Error(w, "invalid multipart: "+err.Error(), http.StatusBadRequest)
		return
	}

	friendly := r.FormValue("friendly")
	slug, err := registry.NewSlug(friendly)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	file, header, err := r.FormFile("file")
	if err != nil {
		http.Error(w, "missing file field: "+err.Error(), http.StatusBadRequest)
		return
	}
	defer file.Close()

	if header.Size > maxBytes {
		http.Error(w, fmt.Sprintf("file too large (max %dMB)", h.maxUploadMB), http.StatusRequestEntityTooLarge)
		return
	}

	dir := filepath.Join(h.sitesDir, slug)
	if err := extractZip(file, header.Size, dir); err != nil {
		_ = os.RemoveAll(dir)
		http.Error(w, "extract failed: "+err.Error(), http.StatusBadRequest)
		return
	}

	h.reg.PutStatic(slug, dir)
	log.Printf("publish: slug=%s files extracted to %s", slug, dir)

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(publishResponse{
		URL:  fmt.Sprintf("https://%s.%s", slug, rootDomain),
		Slug: slug,
	})
}

func extractZip(src io.ReaderAt, size int64, destDir string) error {
	zr, err := zip.NewReader(src, size)
	if err != nil {
		return fmt.Errorf("open zip: %w", err)
	}
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return err
	}

	root := stripCommonPrefix(zr.File)

	for _, f := range zr.File {
		name := strings.TrimPrefix(f.Name, root)
		if name == "" {
			continue
		}
		target, err := safeJoin(destDir, name)
		if err != nil {
			return err
		}
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(target, 0o755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		if err := writeZipEntry(f, target); err != nil {
			return err
		}
	}
	return nil
}

func stripCommonPrefix(files []*zip.File) string {
	if len(files) == 0 {
		return ""
	}
	first := files[0].Name
	idx := strings.Index(first, "/")
	if idx < 0 {
		return ""
	}
	prefix := first[:idx+1]
	for _, f := range files {
		if !strings.HasPrefix(f.Name, prefix) {
			return ""
		}
	}
	return prefix
}

func writeZipEntry(f *zip.File, dest string) error {
	src, err := f.Open()
	if err != nil {
		return err
	}
	defer src.Close()
	dst, err := os.OpenFile(dest, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	defer dst.Close()
	if _, err := io.Copy(dst, src); err != nil {
		return err
	}
	return nil
}

func safeJoin(base, name string) (string, error) {
	clean := filepath.Clean("/" + filepath.ToSlash(name))
	target := filepath.Join(base, clean)
	rel, err := filepath.Rel(base, target)
	if err != nil || strings.HasPrefix(rel, "..") {
		return "", errors.New("zip slip detected: " + name)
	}
	return target, nil
}
