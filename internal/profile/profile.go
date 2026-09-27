// Package profile reads unattended install profiles (profiles/*.toml). A profile answers the
// wizard's questions for CI and automation; it references module ids only and can never
// contain commands. Secrets never live in profiles: they come from ARCTIC_LUKS_PASSPHRASE and
// ARCTIC_USER_PASSWORD.
package profile

import (
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/toml"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
)

// Profile mirrors the wizard steps.
type Profile struct {
	Description string `toml:"description"`
	Welcome     struct {
		Language string `toml:"language"`
	} `toml:"welcome"`
	Keyboard struct {
		Layout  string `toml:"layout"`
		Variant string `toml:"variant"`
	} `toml:"keyboard"`
	Timezone struct {
		Timezone string `toml:"timezone"`
		AutoTime *bool  `toml:"auto_time"`
	} `toml:"timezone"`
	Disk struct {
		Disk string `toml:"disk"` // "" = the wizard's default choice
		Mode string `toml:"mode"` // erase | alongside
	} `toml:"disk"`
	Encryption struct {
		Enabled *bool `toml:"enabled"`
	} `toml:"encryption"`
	Account struct {
		FullName  string `toml:"full_name"`
		Username  string `toml:"username"`
		Hostname  string `toml:"hostname"` // "" = suggested
		Autologin bool   `toml:"autologin"`
	} `toml:"account"`
	// Apps maps category → module ids; categories left out keep the catalog defaults.
	Apps map[string][]string `toml:"apps"`
}

// Parse reads a profile.
func Parse(data []byte) (*Profile, error) {
	var p Profile
	if err := toml.Unmarshal(data, &p); err != nil {
		return nil, err
	}
	return &p, nil
}

// Load reads a profile file.
func Load(path string) (*Profile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	p, err := Parse(data)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return p, nil
}

// Selection merges the profile's apps over the catalog defaults.
func (p *Profile) Selection(c *catalog.Catalog) catalog.Selection {
	sel := c.DefaultSelection()
	keys := make([]string, 0, len(p.Apps))
	for k := range p.Apps {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		sel[k] = append([]string{}, p.Apps[k]...)
	}
	return c.Normalize(sel)
}

// Data turns a profile into wizard answers for a machine (disks, DMI model). Empty fields get
// the wizard's defaults; the result is validated with the wizard's rules.
func (p *Profile) Data(c *catalog.Catalog, disks []hw.Disk, model string) (wizard.Data, hw.Disk, error) {
	var d wizard.Data
	var errs []string
	bad := func(format string, a ...any) { errs = append(errs, fmt.Sprintf(format, a...)) }

	d.Welcome.Language = p.Welcome.Language
	if d.Welcome.Language == "" {
		d.Welcome.Language = "en_US.UTF-8"
	}
	if _, ok := wizard.FindLanguage(d.Welcome.Language); !ok {
		bad("welcome.language %q is not supported", d.Welcome.Language)
	}
	d.Keyboard = wizard.KeyboardData{Layout: p.Keyboard.Layout, Variant: p.Keyboard.Variant}
	if d.Keyboard.Layout == "" {
		d.Keyboard.Layout, d.Keyboard.Variant = wizard.SuggestedLayout(d.Welcome.Language)
	}
	if _, ok := wizard.FindLayout(d.Keyboard.Layout, d.Keyboard.Variant); !ok {
		bad("keyboard %q/%q is not supported", d.Keyboard.Layout, d.Keyboard.Variant)
	}
	d.Timezone = wizard.TimezoneData{Timezone: p.Timezone.Timezone, AutoTime: true}
	if d.Timezone.Timezone == "" {
		d.Timezone.Timezone = "UTC"
	}
	if p.Timezone.AutoTime != nil {
		d.Timezone.AutoTime = *p.Timezone.AutoTime
	}
	if !wizard.ValidTimezone(d.Timezone.Timezone) {
		bad("timezone %q is not a valid zone", d.Timezone.Timezone)
	}
	d.Disk = wizard.DiskData{Disk: p.Disk.Disk, Mode: p.Disk.Mode}
	if d.Disk.Mode == "" {
		d.Disk.Mode = wizard.ModeErase
	}
	if d.Disk.Disk == "" {
		if d.Disk.Mode == wizard.ModeAlongside {
			for _, x := range disks {
				if !x.InstallMedia && x.AlongsidePossible() {
					d.Disk.Disk = x.Path
					break
				}
			}
		}
		if d.Disk.Disk == "" {
			d.Disk.Disk = wizard.DefaultDisk(disks)
		}
	}
	var disk hw.Disk
	found := false
	for _, x := range disks {
		if x.Path == d.Disk.Disk {
			disk, found = x, true
		}
	}
	switch {
	case !found:
		bad("disk %q not found", d.Disk.Disk)
	case disk.InstallMedia:
		bad("disk %s is the install media", disk.Path)
	case disk.SizeBytes < hw.MinInstallBytes:
		bad("disk %s is smaller than 40 GB", disk.Path)
	case d.Disk.Mode == wizard.ModeAlongside && !disk.AlongsidePossible():
		bad("disk %s has no 40 GB free region for alongside", disk.Path)
	case d.Disk.Mode != wizard.ModeErase && d.Disk.Mode != wizard.ModeAlongside:
		bad("disk.mode must be erase or alongside")
	}
	d.Encryption.Enabled = true
	if p.Encryption.Enabled != nil {
		d.Encryption.Enabled = *p.Encryption.Enabled
	}
	d.Account = wizard.AccountData{FullName: p.Account.FullName, Username: p.Account.Username, Hostname: p.Account.Hostname, Autologin: p.Account.Autologin}
	if d.Account.Username == "" {
		d.Account.Username = wizard.SuggestUsername(d.Account.FullName)
	}
	if d.Account.Hostname == "" {
		d.Account.Hostname = wizard.SuggestHostname(d.Account.Username, model)
	}
	for field, msg := range map[string]string{
		"account.full_name": wizard.ValidateFullName(d.Account.FullName),
		"account.username":  wizard.ValidateUsername(d.Account.Username),
		"account.hostname":  wizard.ValidateHostname(d.Account.Hostname),
	} {
		if msg != "" {
			bad("%s: %s", field, msg)
		}
	}
	d.Apps.Selection = p.Selection(c)
	for k, v := range c.Validate(d.Apps.Selection) {
		bad("apps.%s: %s", k, v)
	}
	if len(errs) > 0 {
		sort.Strings(errs)
		return d, disk, fmt.Errorf("profile: %s", strings.Join(errs, "; "))
	}
	return d, disk, nil
}
