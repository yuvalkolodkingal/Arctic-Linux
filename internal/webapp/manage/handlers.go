package manage

import (
	_ "embed"
	"encoding/json"
	"net/url"
	"strings"
)

// Mail sites whose web apps may handle mailto: links, by your explicit choice ("Open email
// links in this app", off by default). The table is Arctic's: nothing a site declares becomes
// a handler.
//
//go:embed handlers.json
var handlersJSON []byte

type mailSite struct {
	Name     string   `json:"name"`
	Hosts    []string `json:"hosts"`
	Template string   `json:"template"`
}

var mailSites = func() []mailSite {
	var s []mailSite
	if err := json.Unmarshal(handlersJSON, &s); err != nil {
		panic("handlers.json: " + err.Error())
	}
	return s
}()

// MailTemplate returns the compose template for an app's start URL, "" when its host is not a
// known mail site.
func MailTemplate(startURL string) string {
	u, err := url.Parse(startURL)
	if err != nil || u.Scheme != "https" {
		return ""
	}
	host := strings.ToLower(u.Hostname())
	for _, s := range mailSites {
		for _, h := range s.Hosts {
			if host == h {
				return s.Template
			}
		}
	}
	return ""
}

// MailtoURL turns `run <id> mailto:…` into the page to open: only mailto: URIs of at most
// 2,048 bytes, percent-encoded into the template. It returns "" for anything else (including a
// literal %u from a launcher that passes field codes through).
func MailtoURL(startURL, uri string) string {
	if len(uri) > 2048 || !strings.HasPrefix(strings.ToLower(uri), "mailto:") {
		return ""
	}
	if strings.ContainsAny(uri, " \t\r\n\x00") {
		return ""
	}
	t := MailTemplate(startURL)
	if t == "" {
		return ""
	}
	return strings.Replace(t, "{mailto}", url.QueryEscape(uri), 1)
}
