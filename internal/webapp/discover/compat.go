package discover

import (
	_ "embed"
	"encoding/json"
	"strings"
)

// Sites that need what Fedora's WebKitGTK does not have: WebRTC calls or Widevine DRM. They
// get a warning and a suggested Chromium-family runtime; they are never blocked.
//
//go:embed compat.json
var compatJSON []byte

var compat = func() map[string][]string {
	var m map[string][]string
	if err := json.Unmarshal(compatJSON, &m); err != nil {
		panic("compat.json: " + err.Error())
	}
	return m
}()

// Needs reports what a host needs: "drm", "calls" or "". A listed host matches itself and its
// subdomains (www.netflix.com is netflix.com).
func Needs(host string) string {
	host = strings.ToLower(host)
	match := func(list []string) bool {
		for _, h := range list {
			if host == h || strings.HasSuffix(host, "."+h) {
				return true
			}
		}
		return false
	}
	switch {
	case match(compat["drm_unsupported"]):
		return "drm"
	case match(compat["calls_unsupported"]):
		return "calls"
	}
	return ""
}

// Category maps manifest categories to one launcher category: music, entertainment, photo and
// video → AudioVideo; games → Game; productivity, business, finance → Office; developer →
// Development; education → Education; design → Graphics; utilities → Utility; else Network.
func Category(cats []string) string {
	for _, c := range cats {
		switch strings.ToLower(strings.TrimSpace(c)) {
		case "music", "entertainment", "photo", "video", "podcasts":
			return "AudioVideo"
		case "games", "game":
			return "Game"
		case "productivity", "business", "finance", "office":
			return "Office"
		case "developer", "development", "developer tools":
			return "Development"
		case "education", "kids", "books":
			return "Education"
		case "design", "graphics":
			return "Graphics"
		case "utilities", "utility":
			return "Utility"
		}
	}
	return "Network"
}
