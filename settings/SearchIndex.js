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
      words: "monitor screen resolution scale refresh hdmi night light" },
    { id: "input", title: "Keyboard and mouse", icon: "mouse", file: "InputPage.qml",
      words: "input keyboard layout touchpad trackpad mouse pointer typing" },
    { id: "shortcuts", title: "Shortcuts", icon: "keyboard", file: "ShortcutsPage.qml",
      words: "keybindings keys hotkeys binds super screenshot print capture record" },
    { id: "apps", title: "Default apps", icon: "grid", file: "AppsPage.qml",
      words: "browser terminal files editor video music pictures pdf open with" },
    { id: "network", title: "Network", icon: "wifi", file: "NetworkPage.qml",
      words: "wi-fi wifi internet ethernet wired vpn connection" },
    { id: "sharing", title: "Sharing", icon: "send", file: "SharingPage.qml",
      words: "firewall ssh remote login localsend kde connect mdns ports" },
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
    { id: "webapps", title: "Web apps", icon: "globe", file: "WebAppsPage.qml",
      words: "website site pwa app browser sign in" },
    { id: "printers", title: "Printers and scanners", icon: "printer", file: "PrintersPage.qml",
      words: "print printer printing cups scanner scan paper ipp airprint" },
    { id: "datetime", title: "Date and time", icon: "clock", file: "DateTimePage.qml",
      words: "time zone timezone clock date ntp language region locale" },
    { id: "users", title: "Users and sign-in", icon: "user", file: "UsersPage.qml",
      words: "account password avatar picture name fingerprint disk encryption passphrase" },
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
    ["windows", "windows.lighter", "Lighter effects", "virtual machine vm performance software rendering slow"],
    ["windows", "windows.gamemode", "Game mode", "games gaps performance"],
    ["displays", "displays.arrange", "Arrangement", "position left right above below multiple monitors drag layout screens"],
    ["displays", "displays.main", "Main display", "primary monitor screen start"],
    ["displays", "displays.use", "Use this display", "turn off disable enable monitor screen"],
    ["displays", "displays.resolution", "Resolution", "size pixels"],
    ["displays", "displays.refresh", "Refresh rate", "hz fps"],
    ["displays", "displays.scale", "Scale", "hidpi zoom size"],
    ["displays", "displays.rotation", "Rotation", "portrait transform flip mirror"],
    ["displays", "displays.nightlight", "Night light", "night shift blue light warm evening sunset colour temperature redshift"],
    ["displays", "displays.nighthours", "Night light hours", "schedule evening morning time"],
    ["displays", "displays.warmth", "Night light warmth", "colour temperature kelvin warm"],
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
    ["network", "network.saved", "Saved Wi-Fi networks", "forget password known networks"],
    ["network", "network.vpn", "Import a VPN file", "openvpn wireguard ovpn conf vpn"],
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
    ["updates", "updates.apps", "Flatpak apps", "flathub app updates"],
    ["updates", "updates.firmware", "Firmware", "fwupd bios uefi device updates"],
    ["updates", "updates.snapshots", "Snapshots", "undo an update rollback snapper restore btrfs"],
    ["updates", "updates.upgrade", "Upgrade to the next Fedora", "fedora release version system-upgrade"],
    ["sharing", "sharing.firewall", "Firewall", "ports allow block security incoming"],
    ["sharing", "sharing.mdns", "Find printers and devices", "mdns avahi bonjour discovery"],
    ["sharing", "sharing.localsend", "LocalSend", "airdrop send files nearby"],
    ["sharing", "sharing.kdeconnect", "KDE Connect", "phone android gsconnect"],
    ["sharing", "sharing.ssh", "Remote login (SSH)", "ssh sshd remote server login terminal"],
    ["sharing", "sharing.password", "Allow password login", "ssh keys authorized_keys"],
    ["power", "power.lock", "Lock the screen after", "idle timeout screensaver"],
    ["power", "power.suspend", "Suspend after", "sleep idle"],
    ["power", "power.awake", "Keep the computer awake", "keep awake caffeine presentation no sleep no lock inhibit"],
    ["power", "power.battery.times", "Times on battery", "battery unplugged lock suspend sooner save power"],
    ["power", "power.dim", "Dim the screen before it locks", "fade dim warning locking soon brightness"],
    ["power", "power.screenoff", "Turn the screens off after locking", "display off dpms blank monitor sleep"],
    ["power", "power.profile", "Power mode", "performance balanced power saver battery"],
    ["power", "power.lid", "When you close the lid", "laptop lid switch clamshell docked external monitor"],
    ["power", "power.limit", "Limit charging", "battery charge threshold health 80"],
    ["power", "power.warnings", "Warn me when the battery is low", "battery low warning notification"],
    ["startup", "startup.mine", "Your startup apps", "autostart login"],
    ["startup", "startup.arctic", "Started by Arctic", "session services"],
    ["webapps", "webapps.list", "Your web apps", "websites pwa"],
    ["webapps", "webapps.links", "Open other sites in your browser", "links external scope"],
    ["webapps", "webapps.notifications", "Web app notifications", "allow ask block"],
    ["webapps", "webapps.engine", "Web app engine", "brave chrome chromium vivaldi drm netflix spotify calls"],
    ["webapps", "webapps.rendering", "Web app rendering", "blank window software nvidia"],
    ["webapps", "webapps.signout", "Sign out of a web app", "cookies clear data"],
    ["webapps", "webapps.kept", "Saved sign-in data", "forget removed web apps"],
    ["startup", "startup.xdg", "Apps that start themselves", "autostart start on login xdg discord steam"],
    ["printers", "printers.list", "Printers", "default printer print queue jobs cancel"],
    ["printers", "printers.add", "Add a printer", "set up printer driver share"],
    ["printers", "printers.scan", "Scan a document", "scanner scanning photo"],
    ["datetime", "datetime.timezone", "Time zone", "timezone travel city utc"],
    ["datetime", "datetime.ntp", "Set the time automatically", "ntp network time sync clock"],
    ["datetime", "datetime.clock", "Date and time", "clock set time manually"],
    ["datetime", "datetime.language", "Language", "locale region translation"],
    ["users", "users.picture", "Your picture", "avatar photo face account"],
    ["users", "users.name", "Your name", "full name account"],
    ["users", "users.password", "Change your password", "password login"],
    ["users", "users.disk", "Disk encryption passphrase", "luks encryption unlock boot"],
    ["users", "users.fingerprint", "Fingerprint", "fprint biometric reader unlock"],
    ["users", "users.lockfinger", "Unlock the screen with your fingerprint", "fingerprint lock screen biometric touch"],
    ["input", "input.im", "Input method", "chinese japanese korean pinyin mozc hangul ime fcitx cjk"],
    ["about", "about.system", "This computer", "cpu processor memory ram graphics gpu disk storage"],
    ["about", "about.software", "Software", "version mango quickshell kernel"],
    ["about", "about.hostname", "Computer name", "hostname host name device name network bluetooth rename"],
    ["about", "about.help", "Help and feedback", "wiki issues bug report"],
    ["about", "about.troubleshoot", "If something stops working", "fix broken no sound wifi bluetooth restart reset shell bar"]
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
