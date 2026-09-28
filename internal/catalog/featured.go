package catalog

// Arctic picks: the catalog's apps as Get apps offers them before you type (the Flathub and
// Fedora pages of the shell). Installed systems don't carry the catalog (it ships with the
// installer), so `arctic-install catalog --featured` writes this into shell/assets/featured.json,
// and featured_test.go keeps that file current.

// FeaturedFlatpak is a pick's Flathub app.
type FeaturedFlatpak struct {
	Remote   string `json:"remote"`
	Ref      string `json:"ref"`
	Verified bool   `json:"verified"`
}

// FeaturedDNF is a pick's Fedora packages.
type FeaturedDNF struct {
	Packages []string `json:"packages"`
}

// FeaturedApp is one pick, with the ways Get apps can install it.
type FeaturedApp struct {
	ID          string           `json:"id"`
	Name        string           `json:"name"`
	Summary     string           `json:"summary"`
	Category    string           `json:"category"`
	Tile        string           `json:"tile"`
	Glyph       string           `json:"glyph"`
	Proprietary bool             `json:"proprietary"`
	Flatpak     *FeaturedFlatpak `json:"flatpak,omitempty"`
	DNF         *FeaturedDNF     `json:"dnf,omitempty"`
}

// Featured is the document the shell reads.
type Featured struct {
	Schema int           `json:"schema"`
	Apps   []FeaturedApp `json:"apps"`
}

// Featured lists the visible modules in picker order with the methods Get apps can use: a
// Flathub app with a ref, and plain dnf packages (no COPR, extra repositories or swaps, which
// stay the installer's and the console's). Hidden, always-installed and driver modules, and
// modules with neither method (COPR- or Nix-only), are left out.
func (c *Catalog) Featured() Featured {
	doc := Featured{Schema: 1, Apps: []FeaturedApp{}}
	for _, id := range c.Order {
		m := c.Modules[id]
		if m == nil || m.Hidden || m.Always || m.IsHardware() {
			continue
		}
		app := FeaturedApp{ID: m.ID, Name: m.Name, Summary: m.Summary, Category: m.Category,
			Tile: m.Tile, Glyph: m.Icon, Proprietary: m.Proprietary}
		for _, in := range m.Install {
			switch {
			case in.Method == MethodFlatpak && in.Remote == "flathub" && in.Ref != "" && app.Flatpak == nil:
				app.Flatpak = &FeaturedFlatpak{Remote: in.Remote, Ref: in.Ref, Verified: in.Verified}
			case in.Method == MethodDNF && len(in.Packages) > 0 && in.Copr == "" && len(in.Repos) == 0 &&
				len(in.Swap) == 0 && app.DNF == nil:
				app.DNF = &FeaturedDNF{Packages: in.Packages}
			}
		}
		if app.Flatpak == nil && app.DNF == nil {
			continue
		}
		doc.Apps = append(doc.Apps, app)
	}
	return doc
}
