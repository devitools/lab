package registry

import (
	"crypto/rand"
	"encoding/base32"
	"fmt"
	"regexp"
	"strings"
)

var friendlyRe = regexp.MustCompile(`^[a-z0-9]+(-[a-z0-9]+)*$`)

const (
	randLen    = 6
	friendlyMax = 24
)

func NewSlug(friendly string) (string, error) {
	friendly = strings.ToLower(strings.TrimSpace(friendly))
	if friendly != "" {
		if len(friendly) > friendlyMax {
			return "", fmt.Errorf("friendly too long (max %d chars)", friendlyMax)
		}
		if !friendlyRe.MatchString(friendly) {
			return "", fmt.Errorf("friendly must be kebab-case (a-z, 0-9, hyphens)")
		}
	}

	buf := make([]byte, 8)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	rnd := strings.ToLower(base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(buf))[:randLen]

	if friendly == "" {
		return rnd, nil
	}
	return friendly + "-" + rnd, nil
}
