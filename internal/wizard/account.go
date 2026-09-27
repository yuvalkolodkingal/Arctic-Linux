package wizard

import (
	"regexp"
	"strings"
	"unicode"
)

// Username rules follow shadow-utils' useradd on Fedora, narrowed to what is safe everywhere:
// start with a lowercase letter or _, then lowercase letters, digits, - and _, at most 32.
var usernameRe = regexp.MustCompile(`^[a-z_][a-z0-9_-]*$`)

// reservedUsers are names taken by Fedora system accounts (and the live session's user).
var reservedUsers = map[string]bool{}

func init() {
	for _, n := range strings.Fields(`root bin daemon adm lp sync shutdown halt mail operator games ftp nobody
		dbus polkitd sddm liveuser tss systemd-coredump systemd-network systemd-oom systemd-resolve
		systemd-timesync systemd-journal-remote rtkit pipewire avahi colord geoclue chrony unbound
		dnsmasq nm-openconnect nm-openvpn openvpn usbmuxd saned flatpak gluster qemu setroubleshoot
		sshd tcpdump abrt brlapi nixbld wheel users admin arctic`) {
		reservedUsers[n] = true
	}
}

// ValidateUsername returns an error message, or "" when the username is fine.
func ValidateUsername(u string) string {
	switch {
	case u == "":
		return "Pick a username."
	case len(u) > 32:
		return "Use 32 characters or fewer."
	case strings.Trim(u, "abcdefghijklmnopqrstuvwxyz0123456789_-") != "":
		return "Use lowercase letters, numbers, - and _."
	case !usernameRe.MatchString(u):
		return "Start with a lowercase letter."
	case reservedUsers[u] || strings.HasPrefix(u, "systemd-"):
		return "That name is taken by the system. Pick another one."
	}
	return ""
}

var hostnameRe = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`)

// ValidateHostname checks a single-label hostname (RFC 1123, lowercase).
func ValidateHostname(h string) string {
	switch {
	case h == "":
		return "Pick a name for this computer."
	case len(h) > 63:
		return "Use 63 characters or fewer."
	case strings.Trim(h, "abcdefghijklmnopqrstuvwxyz0123456789-") != "":
		return "Use lowercase letters, numbers and -."
	case !hostnameRe.MatchString(h):
		return "Start and end with a letter or number."
	case h == "localhost":
		return "Pick a name other than localhost."
	}
	return ""
}

// ValidateFullName checks the display name (GECOS field).
func ValidateFullName(n string) string {
	if strings.TrimSpace(n) == "" {
		return "Type your name."
	}
	if strings.ContainsAny(n, ":\n\r,") {
		return "Your name can't contain : , or line breaks."
	}
	if len(n) > 128 {
		return "Use a shorter name."
	}
	return ""
}

// FirstName is the first word of the full name ("Welcome aboard, Noa").
func FirstName(full string) string {
	f := strings.Fields(full)
	if len(f) == 0 {
		return ""
	}
	return f[0]
}

var fold = map[rune]string{
	'à': "a", 'á': "a", 'â': "a", 'ã': "a", 'ä': "a", 'å': "a", 'ā': "a", 'ą': "a", 'æ': "ae",
	'ç': "c", 'ć': "c", 'č': "c", 'ď': "d", 'đ': "d", 'ð': "d",
	'è': "e", 'é': "e", 'ê': "e", 'ë': "e", 'ē': "e", 'ę': "e", 'ě': "e",
	'ì': "i", 'í': "i", 'î': "i", 'ï': "i", 'ī': "i", 'ı': "i",
	'ł': "l", 'ľ': "l", 'ñ': "n", 'ń': "n", 'ň': "n",
	'ò': "o", 'ó': "o", 'ô': "o", 'õ': "o", 'ö': "o", 'ø': "o", 'ō': "o", 'ő': "o", 'œ': "oe",
	'ř': "r", 'ś': "s", 'š': "s", 'ş': "s", 'ß': "ss", 'ť': "t", 'ţ': "t", 'þ': "th",
	'ù': "u", 'ú': "u", 'û': "u", 'ü': "u", 'ū': "u", 'ů': "u", 'ű': "u",
	'ý': "y", 'ÿ': "y", 'ž': "z", 'ź': "z", 'ż': "z",
}

// asciiFold lowercases and folds common Latin accents; other letters are dropped.
func asciiFold(s string) string {
	var b strings.Builder
	for _, r := range strings.ToLower(s) {
		switch {
		case r < 128:
			b.WriteRune(r)
		case fold[r] != "":
			b.WriteString(fold[r])
		}
	}
	return b.String()
}

// SuggestUsername derives a username from a full name: the first name, lowercased and
// ASCII-folded ("Noa Levi" → "noa", "Zoë" → "zoe"). Names with no Latin letters give "user".
func SuggestUsername(full string) string {
	for _, word := range strings.Fields(full) {
		var b strings.Builder
		for _, r := range asciiFold(word) {
			if r >= 'a' && r <= 'z' || r >= '0' && r <= '9' || r == '-' || r == '_' {
				b.WriteRune(r)
			}
		}
		u := strings.TrimLeft(b.String(), "0123456789-")
		if len(u) > 32 {
			u = u[:32]
		}
		if u == "" {
			continue
		}
		if ValidateUsername(u) != "" {
			u = strings.TrimRight(u, "-_")
			if len(u) > 30 {
				u = u[:30]
			}
			u += "1"
		}
		if ValidateUsername(u) == "" {
			return u
		}
	}
	return "user"
}

// SuggestHostname is "{username}-{model}", lowercased, "-"-joined, at most 63 characters.
func SuggestHostname(username, model string) string {
	h := sanitizeHostname(username + "-" + model)
	if h == "" {
		return "arctic"
	}
	return h
}

func sanitizeHostname(s string) string {
	var b strings.Builder
	dash := false
	for _, r := range asciiFold(s) {
		ok := r >= 'a' && r <= 'z' || r >= '0' && r <= '9'
		if ok {
			b.WriteRune(r)
			dash = false
		} else if !dash && b.Len() > 0 {
			b.WriteByte('-')
			dash = true
		}
	}
	h := strings.Trim(b.String(), "-")
	if len(h) > 63 {
		h = strings.TrimRight(h[:63], "-")
	}
	return h
}

// DMI is what /sys/class/dmi/id says about the machine.
type DMI struct {
	Vendor  string // sys_vendor
	Family  string // product_family
	Product string // product_name
}

var junkDMI = map[string]bool{
	"to be filled by o.e.m.": true, "system product name": true, "default string": true, "not applicable": true,
	"none": true, "o.e.m.": true, "oem": true, "unknown": true, "type1productconfigid": true, "not specified": true,
	"system version": true, "product name": true, "all series": true, "": true,
}

var junkWords = map[string]bool{
	"lenovo": true, "hp": true, "hewlett-packard": true, "dell": true, "inc": true, "inc.": true, "asus": true,
	"asustek": true, "acer": true, "msi": true, "micro-star": true, "samsung": true, "electronics": true, "lg": true,
	"toshiba": true, "fujitsu": true, "sony": true, "apple": true, "microsoft": true, "google": true,
	"framework": true, "gigabyte": true, "system76": true, "tuxedo": true, "huawei": true, "xiaomi": true,
	"computer": true, "computers": true, "notebook": true, "laptop": true, "desktop": true, "pc": true, "co.": true,
	"co.,": true, "ltd": true, "ltd.": true, "corporation": true, "corp": true, "corp.": true, "international": true,
	"technology": true, "gen": true, "intel": true, "amd": true, "core": true, "series": true, "the": true,
}

// ModelName turns DMI data into the short machine word used in hostnames:
// "ThinkPad X1 Carbon Gen 11" → "thinkpad", "HP EliteBook 840 G8 Notebook PC" → "elitebook".
// Virtual machines give "vm"; nothing usable gives "pc".
func ModelName(d DMI) string {
	all := strings.ToLower(d.Vendor + " " + d.Family + " " + d.Product)
	for _, vm := range []string{"qemu", "virtualbox", "vmware", "kvm", "bochs", "standard pc (", "hyper-v", "virtual machine", "parallels"} {
		if strings.Contains(all, vm) {
			return "vm"
		}
	}
	for _, cand := range []string{d.Family, d.Product} {
		if junkDMI[strings.ToLower(strings.TrimSpace(cand))] {
			continue
		}
		for _, w := range strings.Fields(cand) {
			lw := strings.ToLower(w)
			if junkWords[lw] || junkWords[strings.Trim(lw, "()[],")] {
				continue
			}
			clean := sanitizeHostname(w)
			if clean == "" || !unicode.IsLetter(rune(clean[0])) {
				continue
			}
			if i := strings.IndexByte(clean, '-'); i > 0 {
				clean = clean[:i]
			}
			return clean
		}
	}
	if f := strings.Fields(d.Vendor); len(f) > 0 && !junkDMI[strings.ToLower(strings.TrimSpace(d.Vendor))] {
		v := sanitizeHostname(f[0])
		if i := strings.IndexByte(v, '-'); i > 0 {
			v = v[:i]
		}
		if v != "" && unicode.IsLetter(rune(v[0])) {
			return v
		}
	}
	return "pc"
}
