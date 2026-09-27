package wizard

import (
	"fmt"
	"sort"
	"strings"
	"time"
	_ "time/tzdata" // time zones work even where /usr/share/zoneinfo is missing (mock, tests)
)

// Language is one entry of the welcome step's list.
type Language struct {
	ID        string   `json:"id"`      // locale, e.g. "he_IL.UTF-8"
	Name      string   `json:"name"`    // native name
	English   string   `json:"english"` // English name
	Keyboards []string `json:"-"`       // suggested layouts, "layout" or "layout:variant", best first
	Timezone  string   `json:"-"`       // fallback time zone when nothing is detected
}

// Languages: the design's first six in its order, then the rest by English name.
var Languages = []Language{
	{"en_US.UTF-8", "English (US)", "English", []string{"us", "us:intl"}, "America/New_York"},
	{"he_IL.UTF-8", "עברית", "Hebrew", []string{"il", "us"}, "Asia/Jerusalem"},
	{"de_DE.UTF-8", "Deutsch", "German", []string{"de", "de:nodeadkeys"}, "Europe/Berlin"},
	{"es_ES.UTF-8", "Español", "Spanish", []string{"es"}, "Europe/Madrid"},
	{"fr_FR.UTF-8", "Français", "French", []string{"fr"}, "Europe/Paris"},
	{"ja_JP.UTF-8", "日本語", "Japanese", []string{"jp"}, "Asia/Tokyo"},
	{"ar_EG.UTF-8", "العربية", "Arabic", []string{"ara", "us"}, "Africa/Cairo"},
	{"zh_CN.UTF-8", "简体中文", "Chinese (Simplified)", []string{"us"}, "Asia/Shanghai"},
	{"cs_CZ.UTF-8", "Čeština", "Czech", []string{"cz"}, "Europe/Prague"},
	{"da_DK.UTF-8", "Dansk", "Danish", []string{"dk"}, "Europe/Copenhagen"},
	{"nl_NL.UTF-8", "Nederlands", "Dutch", []string{"us:intl", "nl"}, "Europe/Amsterdam"},
	{"en_GB.UTF-8", "English (UK)", "English (UK)", []string{"gb"}, "Europe/London"},
	{"fi_FI.UTF-8", "Suomi", "Finnish", []string{"fi"}, "Europe/Helsinki"},
	{"el_GR.UTF-8", "Ελληνικά", "Greek", []string{"gr", "us"}, "Europe/Athens"},
	{"hu_HU.UTF-8", "Magyar", "Hungarian", []string{"hu"}, "Europe/Budapest"},
	{"it_IT.UTF-8", "Italiano", "Italian", []string{"it"}, "Europe/Rome"},
	{"ko_KR.UTF-8", "한국어", "Korean", []string{"kr"}, "Asia/Seoul"},
	{"nb_NO.UTF-8", "Norsk bokmål", "Norwegian", []string{"no"}, "Europe/Oslo"},
	{"pl_PL.UTF-8", "Polski", "Polish", []string{"pl"}, "Europe/Warsaw"},
	{"pt_BR.UTF-8", "Português (Brasil)", "Portuguese (Brazil)", []string{"br"}, "America/Sao_Paulo"},
	{"pt_PT.UTF-8", "Português", "Portuguese", []string{"pt"}, "Europe/Lisbon"},
	{"ro_RO.UTF-8", "Română", "Romanian", []string{"ro"}, "Europe/Bucharest"},
	{"ru_RU.UTF-8", "Русский", "Russian", []string{"ru", "us"}, "Europe/Moscow"},
	{"es_MX.UTF-8", "Español (México)", "Spanish (Mexico)", []string{"latam"}, "America/Mexico_City"},
	{"sv_SE.UTF-8", "Svenska", "Swedish", []string{"se"}, "Europe/Stockholm"},
	{"tr_TR.UTF-8", "Türkçe", "Turkish", []string{"tr"}, "Europe/Istanbul"},
	{"uk_UA.UTF-8", "Українська", "Ukrainian", []string{"ua", "us"}, "Europe/Kyiv"},
}

// FindLanguage looks a language up by locale id (also accepts "he_IL.utf8" / "he_IL").
func FindLanguage(id string) (Language, bool) {
	norm := normalizeLocale(id)
	for _, l := range Languages {
		if l.ID == norm {
			return l, true
		}
	}
	return Language{}, false
}

func normalizeLocale(id string) string {
	base, _, _ := strings.Cut(id, ".")
	base, _, _ = strings.Cut(base, "@")
	if base == "" || base == "C" || base == "POSIX" {
		return ""
	}
	return base + ".UTF-8"
}

// GuessLanguage maps a LANG-style value to a known language, defaulting to en_US.UTF-8.
func GuessLanguage(lang string) string {
	if l, ok := FindLanguage(lang); ok {
		return l.ID
	}
	// Same language, other region: "de_AT" → "de_DE".
	prefix, _, _ := strings.Cut(lang, "_")
	for _, l := range Languages {
		if prefix != "" && strings.HasPrefix(l.ID, prefix+"_") {
			return l.ID
		}
	}
	return "en_US.UTF-8"
}

// Layout is one keyboard layout choice (xkb layout + variant).
type Layout struct {
	Layout      string `json:"layout"`
	Variant     string `json:"variant"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Suggested   bool   `json:"suggested"`
}

// Key is "layout" or "layout:variant".
func (l Layout) Key() string {
	if l.Variant == "" {
		return l.Layout
	}
	return l.Layout + ":" + l.Variant
}

// Layouts known to the keyboard step (xkeyboard-config names).
var Layouts = []Layout{
	{Layout: "us", Name: "English (US)", Description: "Standard"},
	{Layout: "us", Variant: "intl", Name: "English (US, international)", Description: "Dead keys for accents"},
	{Layout: "gb", Name: "English (UK)"},
	{Layout: "il", Name: "Hebrew", Description: "Standard"},
	{Layout: "de", Name: "German", Description: "Standard"},
	{Layout: "de", Variant: "nodeadkeys", Name: "German (no dead keys)"},
	{Layout: "fr", Name: "French", Description: "AZERTY"},
	{Layout: "es", Name: "Spanish"},
	{Layout: "latam", Name: "Spanish (Latin American)"},
	{Layout: "jp", Name: "Japanese"},
	{Layout: "ara", Name: "Arabic"},
	{Layout: "cz", Name: "Czech"},
	{Layout: "dk", Name: "Danish"},
	{Layout: "nl", Name: "Dutch"},
	{Layout: "fi", Name: "Finnish"},
	{Layout: "gr", Name: "Greek"},
	{Layout: "hu", Name: "Hungarian"},
	{Layout: "it", Name: "Italian"},
	{Layout: "kr", Name: "Korean"},
	{Layout: "no", Name: "Norwegian"},
	{Layout: "pl", Name: "Polish"},
	{Layout: "br", Name: "Portuguese (Brazil)", Description: "ABNT2"},
	{Layout: "pt", Name: "Portuguese"},
	{Layout: "ro", Name: "Romanian"},
	{Layout: "ru", Name: "Russian"},
	{Layout: "se", Name: "Swedish"},
	{Layout: "ch", Name: "Swiss German"},
	{Layout: "ca", Name: "French (Canada)"},
	{Layout: "tr", Name: "Turkish", Description: "Q layout"},
	{Layout: "ua", Name: "Ukrainian"},
}

// FindLayout looks up a layout/variant pair.
func FindLayout(layout, variant string) (Layout, bool) {
	for _, l := range Layouts {
		if l.Layout == layout && l.Variant == variant {
			return l, true
		}
	}
	return Layout{}, false
}

// LayoutsFor returns every layout with the language's suggestions first; the best one is
// marked Suggested and described "Suggested for your language".
func LayoutsFor(lang string) []Layout {
	l, _ := FindLanguage(lang)
	rank := map[string]int{}
	for i, k := range l.Keyboards {
		rank[k] = i + 1
	}
	out := append([]Layout{}, Layouts...)
	sort.SliceStable(out, func(i, j int) bool {
		ri, rj := rank[out[i].Key()], rank[out[j].Key()]
		if ri != 0 && rj != 0 {
			return ri < rj
		}
		return ri != 0 && rj == 0
	})
	if len(l.Keyboards) > 0 {
		for i := range out {
			if out[i].Key() == l.Keyboards[0] {
				out[i].Suggested = true
				out[i].Description = "Suggested for your language"
			}
		}
	}
	return out
}

// SuggestedLayout is the layout pre-selected for a language.
func SuggestedLayout(lang string) (layout, variant string) {
	l, ok := FindLanguage(lang)
	if !ok || len(l.Keyboards) == 0 {
		return "us", ""
	}
	layout, variant, _ = strings.Cut(l.Keyboards[0], ":")
	return layout, variant
}

// City is one time zone choice.
type City struct {
	City     string `json:"city"`
	Country  string `json:"country"`
	Timezone string `json:"timezone"`
}

// Cities per region (the Region + City dropdowns). Any valid IANA zone is also accepted.
var Regions = map[string][]City{
	"Africa": {
		{"Abidjan", "Côte d'Ivoire", "Africa/Abidjan"}, {"Accra", "Ghana", "Africa/Accra"}, {"Addis Ababa", "Ethiopia", "Africa/Addis_Ababa"},
		{"Algiers", "Algeria", "Africa/Algiers"}, {"Cairo", "Egypt", "Africa/Cairo"}, {"Casablanca", "Morocco", "Africa/Casablanca"},
		{"Dar es Salaam", "Tanzania", "Africa/Dar_es_Salaam"}, {"Johannesburg", "South Africa", "Africa/Johannesburg"},
		{"Kinshasa", "DR Congo", "Africa/Kinshasa"}, {"Lagos", "Nigeria", "Africa/Lagos"}, {"Nairobi", "Kenya", "Africa/Nairobi"},
		{"Tunis", "Tunisia", "Africa/Tunis"},
	},
	"America": {
		{"Anchorage", "United States", "America/Anchorage"}, {"Bogotá", "Colombia", "America/Bogota"},
		{"Buenos Aires", "Argentina", "America/Argentina/Buenos_Aires"}, {"Caracas", "Venezuela", "America/Caracas"},
		{"Chicago", "United States", "America/Chicago"}, {"Denver", "United States", "America/Denver"},
		{"Halifax", "Canada", "America/Halifax"}, {"Havana", "Cuba", "America/Havana"}, {"Lima", "Peru", "America/Lima"},
		{"Los Angeles", "United States", "America/Los_Angeles"}, {"Mexico City", "Mexico", "America/Mexico_City"},
		{"Montevideo", "Uruguay", "America/Montevideo"}, {"New York", "United States", "America/New_York"},
		{"Phoenix", "United States", "America/Phoenix"}, {"Santiago", "Chile", "America/Santiago"},
		{"São Paulo", "Brazil", "America/Sao_Paulo"}, {"St. John's", "Canada", "America/St_Johns"},
		{"Toronto", "Canada", "America/Toronto"}, {"Vancouver", "Canada", "America/Vancouver"},
	},
	"Asia": {
		{"Almaty", "Kazakhstan", "Asia/Almaty"}, {"Baghdad", "Iraq", "Asia/Baghdad"}, {"Bangkok", "Thailand", "Asia/Bangkok"},
		{"Beirut", "Lebanon", "Asia/Beirut"}, {"Dhaka", "Bangladesh", "Asia/Dhaka"}, {"Dubai", "United Arab Emirates", "Asia/Dubai"},
		{"Ho Chi Minh City", "Vietnam", "Asia/Ho_Chi_Minh"}, {"Hong Kong", "Hong Kong", "Asia/Hong_Kong"},
		{"Jakarta", "Indonesia", "Asia/Jakarta"}, {"Jerusalem", "Israel", "Asia/Jerusalem"}, {"Karachi", "Pakistan", "Asia/Karachi"},
		{"Kathmandu", "Nepal", "Asia/Kathmandu"}, {"Kolkata", "India", "Asia/Kolkata"}, {"Kuala Lumpur", "Malaysia", "Asia/Kuala_Lumpur"},
		{"Manila", "Philippines", "Asia/Manila"}, {"Riyadh", "Saudi Arabia", "Asia/Riyadh"}, {"Seoul", "South Korea", "Asia/Seoul"},
		{"Shanghai", "China", "Asia/Shanghai"}, {"Singapore", "Singapore", "Asia/Singapore"}, {"Taipei", "Taiwan", "Asia/Taipei"},
		{"Tashkent", "Uzbekistan", "Asia/Tashkent"}, {"Tbilisi", "Georgia", "Asia/Tbilisi"}, {"Tehran", "Iran", "Asia/Tehran"},
		{"Tokyo", "Japan", "Asia/Tokyo"}, {"Yerevan", "Armenia", "Asia/Yerevan"},
	},
	"Atlantic": {
		{"Azores", "Portugal", "Atlantic/Azores"}, {"Canary Islands", "Spain", "Atlantic/Canary"},
		{"Reykjavík", "Iceland", "Atlantic/Reykjavik"},
	},
	"Australia": {
		{"Adelaide", "Australia", "Australia/Adelaide"}, {"Brisbane", "Australia", "Australia/Brisbane"},
		{"Darwin", "Australia", "Australia/Darwin"}, {"Hobart", "Australia", "Australia/Hobart"},
		{"Melbourne", "Australia", "Australia/Melbourne"}, {"Perth", "Australia", "Australia/Perth"},
		{"Sydney", "Australia", "Australia/Sydney"},
	},
	"Europe": {
		{"Amsterdam", "Netherlands", "Europe/Amsterdam"}, {"Athens", "Greece", "Europe/Athens"}, {"Belgrade", "Serbia", "Europe/Belgrade"},
		{"Berlin", "Germany", "Europe/Berlin"}, {"Brussels", "Belgium", "Europe/Brussels"}, {"Bucharest", "Romania", "Europe/Bucharest"},
		{"Budapest", "Hungary", "Europe/Budapest"}, {"Copenhagen", "Denmark", "Europe/Copenhagen"}, {"Dublin", "Ireland", "Europe/Dublin"},
		{"Helsinki", "Finland", "Europe/Helsinki"}, {"Istanbul", "Turkey", "Europe/Istanbul"}, {"Kyiv", "Ukraine", "Europe/Kyiv"},
		{"Lisbon", "Portugal", "Europe/Lisbon"}, {"London", "United Kingdom", "Europe/London"}, {"Madrid", "Spain", "Europe/Madrid"},
		{"Moscow", "Russia", "Europe/Moscow"}, {"Oslo", "Norway", "Europe/Oslo"}, {"Paris", "France", "Europe/Paris"},
		{"Prague", "Czechia", "Europe/Prague"}, {"Riga", "Latvia", "Europe/Riga"}, {"Rome", "Italy", "Europe/Rome"},
		{"Sofia", "Bulgaria", "Europe/Sofia"}, {"Stockholm", "Sweden", "Europe/Stockholm"}, {"Tallinn", "Estonia", "Europe/Tallinn"},
		{"Vienna", "Austria", "Europe/Vienna"}, {"Vilnius", "Lithuania", "Europe/Vilnius"}, {"Warsaw", "Poland", "Europe/Warsaw"},
		{"Zurich", "Switzerland", "Europe/Zurich"},
	},
	"Pacific": {
		{"Auckland", "New Zealand", "Pacific/Auckland"}, {"Fiji", "Fiji", "Pacific/Fiji"}, {"Guam", "Guam", "Pacific/Guam"},
		{"Honolulu", "United States", "Pacific/Honolulu"},
	},
	"UTC": {
		{"UTC", "", "UTC"},
	},
}

// LookupCity finds the city entry for a zone; unknown zones get a city derived from the name.
func LookupCity(tz string) City {
	for _, cities := range Regions {
		for _, c := range cities {
			if c.Timezone == tz {
				return c
			}
		}
	}
	name := tz
	if i := strings.LastIndexByte(tz, '/'); i >= 0 {
		name = tz[i+1:]
	}
	return City{City: strings.ReplaceAll(name, "_", " "), Timezone: tz}
}

// RegionOf is the dropdown region of a zone ("Asia/Jerusalem" → "Asia").
func RegionOf(tz string) string {
	for r, cities := range Regions {
		for _, c := range cities {
			if c.Timezone == tz {
				return r
			}
		}
	}
	r, _, _ := strings.Cut(tz, "/")
	return r
}

// ValidTimezone reports whether tz is a loadable IANA zone name.
func ValidTimezone(tz string) bool {
	if tz == "" || strings.HasPrefix(tz, "/") || strings.Contains(tz, "..") {
		return false
	}
	_, err := time.LoadLocation(tz)
	return err == nil
}

// UTCOffsetLabel formats the current offset: "UTC+3", "UTC-5", "UTC+5:30", "UTC".
func UTCOffsetLabel(tz string, now time.Time) string {
	loc, err := time.LoadLocation(tz)
	if err != nil {
		return ""
	}
	_, off := now.In(loc).Zone()
	if off == 0 {
		return "UTC"
	}
	sign := "+"
	if off < 0 {
		sign = "-"
		off = -off
	}
	h, m := off/3600, (off%3600)/60
	if m == 0 {
		return fmt.Sprintf("UTC%s%d", sign, h)
	}
	return fmt.Sprintf("UTC%s%d:%02d", sign, h, m)
}

// LocalTime is "07:42" in the zone.
func LocalTime(tz string, now time.Time) string {
	loc, err := time.LoadLocation(tz)
	if err != nil {
		return ""
	}
	return now.In(loc).Format("15:04")
}
