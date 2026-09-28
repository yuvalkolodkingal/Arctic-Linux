.pragma library
// The pages of Arctic Settings and what the search finds on them. Each entry names the page
// and the row's searchKey (SettingRow.searchKey), so a result opens the page and highlights
// the row. Words are what people might type ("dark mode", "wifi", "hz") besides the title.

var PAGES = [
    { id: "appearance", title: "Appearance", icon: "brush", file: "AppearancePage.qml",
      words: "theme colours colors look style" },
    { id: "windows", title: "Windows", icon: "tiling", file: "WindowsPage.qml",
      words: "desktop tiling mango gaps borders animations layout focus" },
    { id: "displays", title: "Displays", icon: "display", file: "DisplaysPage.qml",
      words: "monitor screen resolution scale refresh hdmi" },
    { id: "input", title: "Keyboard and mouse", icon: "mouse", file: "InputPage.qml",
      words: "input keyboard layout touchpad trackpad mouse pointer typing" },
    { id: "shortcuts", title: "Shortcuts", icon: "keyboard", file: "ShortcutsPage.qml",
      words: "keybindings keys hotkeys binds super screenshot print capture record" },
    { id: "apps", title: "Default apps", icon: "grid", file: "AppsPage.qml",
      words: "browser terminal files editor video music pictures pdf open with" },
    { id: "network", title: "Network", icon: "wifi", file: "NetworkPage.qml",
      words: "wi-fi wifi internet ethernet wired vpn connection" },
    { id: "bluetooth", title: "Bluetooth", icon: "bluetooth", file: "BluetoothPage.qml",
      words: "headphones devices pair wireless" },
    { id: "sound", title: "Sound", icon: "volume", file: "SoundPage.qml",
      words: "audio volume speakers microphone output input mute" },
    { id: "notifications", title: "Notifications", icon: "bell", file: "NotificationsPage.qml",
      words: "alerts do not disturb dnd history banners pop-ups toasts quiet" },
    { id: "updates", title: "Updates", icon: "download", file: "UpdatesPage.qml",
      words: "upgrade software dnf security channel testing" },
    { id: "power", title: "Power and lock", icon: "lock", file: "PowerPage.qml",
      words: "idle sleep suspend screen lock battery lid power mode performance" },
    { id: "startup", title: "Startup apps", icon: "play", file: "StartupPage.qml",
      words: "autostart login exec-once start" },
    { id: "about", title: "About", icon: "info", file: "AboutPage.qml",
      words: "system version hardware cpu memory disk fedora help wiki" }
];

var ENTRIES = [
    ["appearance", "appearance.theme", "Theme", "winter polar night dark light mode colours"],
    ["appearance", "appearance.auto", "Match colours to the wallpaper", "auto automatic accent"],
    ["appearance", "appearance.mode", "Light or dark", "dark mode light mode"],
    ["appearance", "appearance.wallpaper", "Wallpaper", "background picture desktop image add upload drop rename delete my own pictures"],
    ["appearance", "appearance.wallhaven", "Find wallpapers on Wallhaven", "wallhaven online download internet search browse wallpaper"],
    ["appearance", "appearance.wallhaven.key", "Wallhaven API key", "wallhaven account apikey nsfw sketchy"],
    ["appearance", "appearance.motion", "Reduce motion", "animations accessibility"],
    ["appearance", "appearance.textscale", "Text size in apps", "font scale bigger"],
    ["appearance", "appearance.cursor", "Pointer size and style", "cursor theme"],
    ["windows", "windows.gaps", "Gap between windows", "gaps inner spacing"],
    ["windows", "windows.outer", "Gap at the screen edge", "outer gaps margin"],
    ["windows", "windows.border", "Border width", "borderpx outline"],
    ["windows", "windows.radius", "Rounded corners", "radius corner"],
    ["windows", "windows.smart", "One window on its own", "smartgaps single border"],
    ["windows", "windows.animations", "Window animations", "motion effects"],
    ["windows", "windows.speed", "Animation speed", "duration fast slow"],
    ["windows", "windows.blur", "Frosted bar", "blur transparency"],
    ["windows", "windows.shadows", "Shadows", "shadow elevation"],
    ["windows", "windows.dim", "Dim windows you aren’t using", "opacity unfocused inactive"],
    ["windows", "windows.focus", "Focus follows the mouse", "sloppy focus hover"],
    ["windows", "windows.warp", "Pointer follows the focus", "warp cursor"],
    ["windows", "windows.hotcorner", "Hot corner", "overview corner mouse pointer"],
    ["windows", "windows.activate", "Apps can bring themselves forward", "activate urgent focus"],
    ["windows", "windows.layout", "Layout for every workspace", "tile scroller monocle grid dwindle tiling"],
    ["windows", "windows.master", "New windows open as the main window", "master stack"],
    ["windows", "windows.mfact", "Width of the main area", "master factor split"],
    ["displays", "displays.arrange", "Arrangement", "position left right above below multiple monitors drag layout screens"],
    ["displays", "displays.main", "Main display", "primary monitor screen start"],
    ["displays", "displays.use", "Use this display", "turn off disable enable monitor screen"],
    ["displays", "displays.resolution", "Resolution", "size pixels"],
    ["displays", "displays.refresh", "Refresh rate", "hz fps"],
    ["displays", "displays.scale", "Scale", "hidpi zoom size"],
    ["displays", "displays.rotation", "Rotation", "portrait transform flip mirror"],
    ["input", "input.layouts", "Keyboard layouts", "language xkb variant"],
    ["input", "input.switch", "Switch layouts with", "alt shift toggle"],
    ["input", "input.caps", "Caps Lock key", "escape ctrl"],
    ["input", "input.compose", "Compose key", "special characters accents symbols multi key"],
    ["input", "input.repeat", "Key repeat", "delay rate typing speed"],
    ["input", "input.numlock", "Num Lock", "number pad"],
    ["input", "input.tap", "Tap to click", "touchpad trackpad"],
    ["input", "input.natural", "Natural scrolling", "reverse scroll direction touchpad"],
    ["input", "input.typing", "Turn the touchpad off while typing", "disable while typing palm"],
    ["input", "input.tpspeed", "Touchpad speed", "sensitivity acceleration pointer"],
    ["input", "input.click", "Right click on the touchpad", "clickfinger button areas"],
    ["input", "input.mousespeed", "Mouse speed", "sensitivity acceleration"],
    ["input", "input.lefthanded", "Left-handed mouse", "swap buttons"],
    ["input", "input.clipboard", "Clipboard history", "cliphist copy paste privacy clear super v"],
    ["shortcuts", "shortcuts.mine", "Your shortcuts", "add custom keybinding command"],
    ["shortcuts", "shortcuts.sheet", "Arctic’s shortcuts", "keys cheat sheet"],
    ["apps", "apps.browser", "Web browser", "firefox zen chromium links"],
    ["apps", "apps.terminal", "Terminal", "kitty foot alacritty"],
    ["apps", "apps.files", "Files", "file manager thunar nautilus folders"],
    ["apps", "apps.editor", "Text editor", "code zed"],
    ["apps", "apps.video", "Videos", "vlc mpv player"],
    ["apps", "apps.software", "Install and remove apps", "get apps remove uninstall software flatpak flathub dnf fedora web app terminal"],
    ["network", "network.wifi", "Wi-Fi", "wireless"],
    ["network", "network.connections", "Connections", "vpn ethernet proxy"],
    ["bluetooth", "bluetooth.power", "Bluetooth", "on off"],
    ["bluetooth", "bluetooth.devices", "Devices", "headphones mouse keyboard pair"],
    ["sound", "sound.output", "Output", "speakers headphones volume"],
    ["sound", "sound.input", "Input", "microphone mic"],
    ["notifications", "notifications.dnd", "Do not disturb", "dnd quiet silence focus mute notifications"],
    ["notifications", "notifications.schedule", "Do not disturb on a schedule", "night quiet hours time"],
    ["notifications", "notifications.history", "Keep notifications after a restart", "history centre center clear"],
    ["notifications", "notifications.apps", "What each app may do", "per app rules pop-ups urgent banners"],
    ["updates", "updates.status", "Updates", "check now install restart"],
    ["updates", "updates.auto", "Download updates automatically", "automatic"],
    ["updates", "updates.channel", "Update channel", "stable testing beta"],
    ["power", "power.lock", "Lock the screen after", "idle timeout screensaver"],
    ["power", "power.suspend", "Suspend after", "sleep idle"],
    ["power", "power.profile", "Power mode", "performance balanced power saver battery"],
    ["power", "power.lid", "Closing the lid", "laptop lid switch"],
    ["startup", "startup.mine", "Your startup apps", "autostart login"],
    ["startup", "startup.arctic", "Started by Arctic", "session services"],
    ["about", "about.system", "This computer", "cpu processor memory ram graphics gpu disk storage"],
    ["about", "about.software", "Software", "version mango quickshell kernel"],
    ["about", "about.help", "Help and feedback", "wiki issues bug report"]
];

function pageIndex(id) {
    for (var i = 0; i < PAGES.length; i++)
        if (PAGES[i].id === id)
            return i;
    return -1;
}

// Pages and settings that match every word typed, best first (title start, title, words).
function search(query) {
    var words = String(query || "").toLowerCase().split(/\s+/).filter(function (w) { return w.length > 0; });
    if (!words.length)
        return [];
    var out = [];
    function score(title, extra) {
        var t = title.toLowerCase(), all = t + " " + extra.toLowerCase(), s = 0;
        for (var i = 0; i < words.length; i++) {
            if (all.indexOf(words[i]) < 0)
                return -1;
            s += t.indexOf(words[i]) === 0 ? 3 : t.indexOf(words[i]) >= 0 ? 2 : 1;
        }
        return s;
    }
    PAGES.forEach(function (p) {
        var s = score(p.title, p.words);
        if (s >= 0)
            out.push({ page: p.id, key: "", title: p.title, where: "Page", icon: p.icon, score: s + 1 });
    });
    ENTRIES.forEach(function (e) {
        var p = PAGES[pageIndex(e[0])];
        var s = score(e[2], e[3] + " " + p.title);
        if (s >= 0)
            out.push({ page: e[0], key: e[1], title: e[2], where: p.title, icon: p.icon, score: s });
    });
    out.sort(function (a, b) { return b.score - a.score || a.title.localeCompare(b.title); });
    return out.slice(0, 40);
}
