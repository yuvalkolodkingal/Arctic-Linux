# Arctic Linux 0.3 — Get apps chooser (Flatpak / dnf / Web app) and Remove apps

Part of the [0.3 plan](../PLAN-0.3.md).

This section covers user requests #1 ("the get apps opens to multiple options, flatpak, dnf, and
web app") and #4 ("a remove apps option with other options flatpak webapp etc"). It implements
decisions D2 and D3, the Get apps side of D4, and these research gap items:

- `launcher-uninstall-key` (P1): Delete on a launcher row.
- `tui-launchers` (P2): Terminal apps. It is not deferred.
- The parts of `unified-updates` (P1) that concern apps installed from Get apps.
- The Install and Remove branches of `command-menu` (P1), which are links into these pages.

It ships in Arctic Linux 0.3.0 (D1). Privileges don't change (D2):

- dnf runs only as `pkexec /usr/bin/dnf5` (polkit action `org.arcticlinux.pkexec.dnf`).
- Flatpak system installs need no password for wheel users.

Facts marked ✅ were checked in the repository or upstream on 2026-09-28. Facts marked 🔍 are
unverified; each one names the check that proves it.

---

### 1. Current state (0.2.1)

#### 1.1 Entry points

Every entry point ends in `shell.openGetApps()`, which sets `launcher.view = 'get'`.

| Entry | Where | What it does |
|---|---|---|
| `Super + Shift + A` | `dotfiles/.config/mango/arctic/binds.conf:21` `bind=SUPER+SHIFT,a,spawn,arctic-shell-ipc apps install` | IPC `apps install` |
| IPC target `apps` | `shell/shell.qml:95-99`: `install()` → `openGetApps(null)`, `toggle()` → launcher | `openGetApps` (`shell.qml:34-37`) sets the view, then `launcher.openView('get')` or `present()` |
| Launcher special | `shell/Launcher.qml:51` `{kind:'get', name:'Get apps', desc:'Install apps with dnf or Flatpak', glyph:'package', …}`; `activate()` `case 'get'` at `:94` | switches the view in place |
| Settings | `settings/pages/AppsPage.qml:51-57`: the "Get apps" button appears only when a role has no candidates and runs `arctic-shell-ipc apps install` (`:56`); footnote at `:62-68` | IPC |
| Docs and automation | `dotfiles/.local/bin/arctic-shell-ipc:6`, `dotfiles/.local/share/arctic/keys.txt:11`, `dotfiles/README.md:82`, `shell/dev/screenshots.sh:21-22`, `tools/lib/tour.py:809-812`, `tools/screenshot-tour.sh:138-150` | all of these assume the console opens directly |

Launcher details:

- `shell.toggleLauncher` (`shell.qml:28-33`) treats `view === 'get'` as "not home". Super+Space in
  Get apps goes back to the launcher home instead of closing.
- In the `get` view the card is 760×600 (`Launcher.qml:25-26`) and focus goes to
  `getApps.inputItem` (`:24`).
- The footer and hints (`:139-302`) are hidden.

Esc inside the console isn't handled there. It falls through to `Popover.qml:99`
(`Keys.onEscapePressed: popover.close()`), so it closes the whole launcher instead of going back
one page.

#### 1.2 The console: `shell/InstallConsole.qml` (316 lines), embedded at `Launcher.qml:131-137`

- **Header** (`:109-128`): Back (`:112`) → `backRequested` → `launcher.openView('home')`, the title
  "Get apps" (`:114`), **Refresh list** (`:121-125`), **Clear** (`:126`) and **Stop Ctrl+C**
  (`:127`).
  - **Refresh list** only restarts `package-index.py`, which refreshes only a cache older than a day
    (`package-index.py:85-88`). The button doesn't force a refresh.
- **The well** (`:131-238`) shows one of two things:
  - a suggestion list: at most 200 ids with an icon and a source label, 'Flathub' or 'Fedora'
    (`:190`), but no names, summaries or icons;
  - the read-only monospace transcript.
- **The input line** (`:251-315`):
  - Enter completes a suggestion, then starts a job or answers a prompt (`:285-296`).
  - Tab, ↑/↓ and Ctrl+C are handled at `:297-313`.
  - A secret prompt masks the field (`:257`, `:274-277`).
- **Processes**: the console owns two, `packageIndex` (`:62-80`) and `backend` (`:81-106`). When
  the backend dies, the notice reads "The console stopped. Open Get apps again to restart it."
  (`:104`).

#### 1.3 The job backend: `shell/scripts/install-terminal.py` (318 lines, needs python3-pyte)

**Protocol** (`:4-6`, loop `:272-314`)
- In: JSON lines `{action: start|input|interrupt|clear, text, secret}`.
- Out: `{output, running, secret, notice}` after every change. The whole transcript is sent on every
  line (`emit`, `:156-160`).

**`build_command`** (`:64-100`) builds an argv list and never uses a shell:
- dnf verbs in `DNF_READONLY` (`:39-41`) run as plain `dnf`.
- Every other dnf verb runs `['pkexec','/usr/bin/dnf5',…]`, with `-y` added by `with_yes`
  (`:136-141`). This includes `remove`, so a typed removal never asks for confirmation.
- Flatpak change verbs (`:46-47`) get `-y`.
- Bare names must match `NAME` (`:49`) and install with `pkexec dnf5 install -y`.
- `flathub:<id>` installs with `flatpak install -y flathub <id>`, without `--system`.

**PTY** (`Console`, `:144-269`)
- A `pyte.HistoryScreen(88, 26, history=2000)`.
- Only one job runs at a time: `start()` returns early when `pid` is set (`:195-196`).
- Secret detection is at `:166-192`, and stale input is refused at `:218-229`.

**Finishing a job**
- The exit code is printed as `Done.` or `[Exit N]`, never sent as data (`:265-269`).
- On success, `after_flatpak_install` (`:114-133`) runs the `30-zed` theme hook.

**Stdin EOF** (`:281-283`)
- On EOF, `main` returns and `finally` closes the PTY master (`:312-314`).
- A dnf transaction still running then gets SIGHUP. A shell restart can therefore kill an install
  halfway.

#### 1.4 The name index: `shell/scripts/package-index.py` + `shell/PackageSearch.js`

**`package-index.py`**
- Caches live in `~/.cache/arctic/{packages.txt,flathub.txt}`, with `MAX_AGE` 24 h (`:24-27`).
- On start it prints the cached snapshot, then the refreshed one.
- The refresh runs two commands:
  - `dnf5 -q repoquery --available --qf '%{name}\n'` (`:64`);
  - `flatpak remote-ls --app --columns=application flathub` (`:70`), with no `--system`/`--user`.
- `query()` drops every line that contains a space (`:56`).
- Only a dnf failure produces an error sentence.

**`PackageSearch.js`**
- It works on strings only.
- `prepare()` (`:92-105`) takes the last dotted part of an app id as its name.
- `search()` (`:109-138`) ranks exact, then prefix, then substring matches, and runs a fuzzy pass
  only when there are fewer than 200 strong matches.
- `context()` (`:21-57`) and `complete()` (`:140-145`) serve the console.

#### 1.5 Privileges

- **dnf**: polkit action `org.arcticlinux.pkexec.dnf`
  (`packaging/polkit/org.arcticlinux.pkexec.dnf.policy:10-20`, `allow_active=auth_admin_keep`,
  `exec.path=/usr/bin/dnf5`). The shell's `PolkitDialog.qml` (`:14-24`) asks for the password.
- **Flatpak**: Flatpak's own polkit rules let active local wheel users install and uninstall
  without a password. The installer puts the user in `wheel` (`internal/installer/installer.go:1485`).
  Adding a system remote is `org.freedesktop.Flatpak.configure-remote`, which is `auth_admin_keep`.

#### 1.6 Packaging, tests and CI

**`arctic-shell`** (`packaging/arctic-linux.spec:240-257`)
- noarch.
- Requires python3-pyte (`:249`) and polkit, commented "pkexec, for Get apps" (`:250-251`).
- `%install` copies `shell/` without `tests/` and `dev/` (`:710`) and installs the polkit policy
  (`:729-731`).
- `%check` doesn't run `shell/tests`.

**`arctic-desktop`**
- **Hard Requires**: pavucontrol (`:439`), network-manager-applet (`:440`), blueman (`:442`), fuzzel
  (`:462`), flatpak (`:463`), nix and nix-daemon (`:464-465`), and qt5ct/qt6ct.
  - Removing any of these with dnf also removes `arctic-desktop`.
- **Weak dependencies**: kitty, kitty-shell-integration, zsh, Thunar and vlc (`:421-425`), and btop
  (`:482`).

**Protected packages**
- Nothing in the repo configures dnf protected packages.
- Only Fedora's `/etc/dnf/protected.d/{systemd,sudo,setup}.conf` apply, plus dnf5 itself and the
  running kernel.

**Snapshots**
- Every dnf transaction gets a snapper pre/post snapshot (`packaging/updates/snapper.actions`).

**Tests**
- `shell/tests/test_install_terminal.py`:
  - `CommandTests` (`:20-53`); `test_dnf_changes_need_pkexec_and_queries_do_not` expects
    `sudo dnf remove fish` to get `-y`;
  - `TerminalTests` (`:55-179`);
  - `FlatpakThemeHookTests` (`:182-216`).
- `shell/tests/test_helpers.py` `PackageIndexTests` (`:44-96`).
- `shell/tests/test-package-search.cjs`.

**CI** (`.github/workflows/ci.yml`)
- `shell-tests` (`:65-97`) runs `unittest discover -s shell/tests` and every `*.cjs`.
- `dnf5-offline` (`:116-127`) is the model for a real-dnf5 harness.
- `qml` (`:129-`) runs qmllint over every `*.qml` under `shell/`, found recursively.

#### 1.7 Missing or wrong

- There is no remove UI. The only way to remove an app is to type `dnf remove` or `flatpak uninstall`,
  and dnf then removes it with `-y`, without showing what else goes.
- Nothing shows names, summaries or icons for apps that aren't installed.
- There is no web-app source and no terminal-app source.
- Nothing stops a typed `dnf remove blueman` from also removing `arctic-desktop`.
- The launcher has no Delete key (the verification item for `launcher-uninstall-key` confirms this).
- Stale docs:
  - `shell/README.md:42` says installs run "as `sudo dnf …`" and that `[y/N]` is answered in the
    console. In fact it's pkexec with `-y`.
  - `dotfiles/.local/bin/arctic-open:86` tells users to "Pick one with the Software app".

---

### 2. Design

#### 2.1 Page map

```
Launcher (Super + Space)                       view: home | apps | get
└─ Get apps (view 'get', Super + Shift + A)    shell/getapps/GetApps.qml, property page:
   ├─ choose     chooser home: source cards                          (1 Flathub apps · 2 Fedora packages · 3 Web apps
   │                                                                  4 Terminal apps · 5 Remove apps · 6 Console)
   ├─ flatpak    Flathub apps: search, details, install
   ├─ dnf        Fedora packages: search (Apps | All packages), details, install
   ├─ web        Web apps: URL → preview → add            (arctic-webapp serve, D4)
   ├─ terminal   Terminal apps: name + command → launcher entry       (tui-launchers, P2)
   ├─ remove     Remove apps, tabs: flatpak | dnf | web | terminal     (D3)
   └─ console    the existing PTY console, for power users            (D2)
```

**Cards**
- D2 lists five cards: Flathub apps, Fedora packages, Web apps, Remove apps and Console.
- **Terminal apps** is the sixth card, added by D8 for the P2 item `tui-launchers`.
- Cards that don't apply are hidden, and the digit keys follow the visible order:
  - **Web apps** is hidden when `arctic-webapp` is missing.
  - **Remove apps** is hidden on the live USB.

#### 2.2 Processes

```
shell/AppsService.qml  (singleton, created with the launcher, alive for the shell's lifetime)
 ├─ runner  python3 scripts/install-terminal.py     long-lived, PTY, ONE job at a time (console or GUI)
 ├─ index   python3 scripts/package-index.py --details   on first open of Get apps; daily refresh
 ├─ helper  python3 scripts/apps.py <command> …          short-lived; exactly one JSON line; {ok, …}
 └─ web     WebAppClient.qml → arctic-webapp serve      long-lived JSON lines (engine-design.md §5.2)
```

Rules:

1. **The GUI never builds command text.** Pages call `AppsService.install(…)` / `remove(…)`. The
   service sends a structured job (`{"action":"run","job":{…}}`), and the runner builds the argv
   itself, validating every id.
2. **One runner.** GUI jobs and the console share the same PTY runner:
   - a second job queues in `AppsService` instead of being refused;
   - the console's input line is disabled while a GUI job runs;
   - the console transcript shows GUI jobs as well.
3. **Jobs outlive the launcher.** They belong to the singleton, not to a page, so closing the
   launcher doesn't stop an install.
   - When a job ends while Get apps isn't on screen, a notification says so (§3.10).
4. **Read-only work stays unprivileged.** Listing, previews, metadata and terminal-app entries go
   through `apps.py` as the user, with no pkexec.
   - Only the runner reaches pkexec, and only as `pkexec /usr/bin/dnf5 install|remove -y …`, the
     same shape as today.
5. **Web apps belong to the engine.** They go through `arctic-webapp serve` (per user, no
   privileges, its own progress events). They never go through the PTY runner.

#### 2.3 What each source uses

| Source | Search and metadata | Installed list | Install | Remove |
|---|---|---|---|---|
| Flathub (Flatpak) | local AppStream `…/appstream/flathub/<arch>/active/appstream.xml.gz` + icons, falling back to `flatpak remote-ls --app --columns=application,name,description` | `flatpak list --app --columns=application,name,version,origin,installation,size` | `flatpak install --system -y --noninteractive flathub ID` (`--user` for non-wheel users, §6.9) | `flatpak uninstall --system\|--user -y --noninteractive [--delete-data] ID`, then `… --unused` |
| Fedora (dnf) | Apps: `appstream-data` (`/usr/share/swcatalog/xml/*.xml.gz` + icons). All packages: `dnf5 -q repoquery --available --qf '%{name}\t%{repoid}\t%{summary}\n'` | `.desktop` files in `XDG_DATA_DIRS/applications` → owning rpm (`rpm -qf`), plus `dnf5 repoquery --installed` for reason, repo, size and install time | `pkexec /usr/bin/dnf5 install -y PKG` | preview `dnf5 remove --store=DIR -y PKG` as the user, then `pkexec /usr/bin/dnf5 remove -y PKG` |
| Web apps | `arctic-webapp serve` `Inspect` | `List{kept:true}` | `Install{token,…}` | `Remove{ids, keep_data}`, `Forget{ids}` |
| Terminal apps | none (a form) | `apps.py installed terminal` (`X-Arctic-TerminalApp-Id` entries in `$XDG_DATA_HOME/applications`) | `apps.py terminal-app add` | `apps.py terminal-app remove` |

---

### 3. Pages and layout

All colours come from `Theme.qml` tokens (D9). Amber appears only for:

- the one primary button in a view;
- focus rings;
- the selected card, row or tab (`accentSoft` fill + `accentEdge` border);
- progress fills.

Status always carries an icon and a word:

| Status | Icon | Colour | Word |
|---|---|---|---|
| Installed | `check-circle` | success | "Installed" |
| Verified | `shield-check` | info | "Verified" |
| Protected | `lock` | inkMuted | "Part of Arctic Linux" |
| Warning | `alert` | warning | a sentence |
| Failure | `x-circle` | error | a sentence |

Copy follows `design/brand-book.md`: sentence case, and buttons that start with a verb and name
the consequence ("Remove GIMP", never "OK" or "Yes").

Motion:
- Page changes crossfade over `Theme.durationFast`.
- Sheets fade and scale like the other popovers.
- Neither animates when `Session.reduceMotion` is set.

#### 3.1 Chooser (page `choose`)

The card is 640 wide by its implicit height (about 430). The list pages keep 760×600.

- **Header**:
  - Back (ghost, sm, `chevron-left`), which goes to the launcher home;
  - the title "Get apps" (16/DemiBold);
  - the subtitle "Where should the app come from?" (inkMuted 13).
- **Three large cards in a row**, each about 192×150:
  - the tile (48);
  - the title (15/DemiBold);
  - a two-line description (13, inkMuted);
  - a status line (12, inkSubtle);
  - a `Kbd` chip with its digit in the top-right corner.

| # | Card | Tile | Description | Status line |
|---|---|---|---|---|
| 1 | Flathub apps | design tile `flathub` | "Desktop apps from Flathub, each in its own sandbox." | "No password needed" · when the remote is missing: "Flathub isn't set up yet" |
| 2 | Fedora packages | **new glyph `layers`** (§7.4) on `surfaceSunken` | "Apps and tools from Fedora and RPM Fusion." | "Asks for your password" |
| 3 | Web apps | glyph `globe`, browser tint (`infoSoft`) | "Any website as an app, with its own window and sign-in." | "Needs the internet" |

- **Three small cards in a row**, each 44 high: tile 28, title and one line.
  - They repeat the same card data with smaller tiles. The chooser only links to pages and never
    installs anything, so it has no primary button.

| # | Card | Tile | Line |
|---|---|---|---|
| 4 | Terminal apps | glyph `prompt`, terminal tint (`slate900`, snow ink) | "Put a terminal program like btop in the launcher." |
| 5 | Remove apps | glyph `trash` | "Uninstall Flatpak apps, Fedora packages and web apps." |
| 6 | Console | glyph `terminal` | "Type dnf and flatpak commands." |

- **Live USB** (`Session.live`): an info line above the cards reads "You're trying Arctic Linux:
  apps you add are gone when you restart." (icon `info`, colour `info`).
- **Job strip** at the bottom, shown while a job runs or up to 60 s after one ends: see `JobCard`,
  §3.10.

Selection and focus:
- The selected card has an `accentSoft` fill and an `accentEdge` border.
- Keyboard focus also draws the `FocusRing`.
- Hovering selects, and clicking opens.

#### 3.2 Flathub apps (page `flatpak`)

- **Header**:
  - Back (to the chooser);
  - the title "Flathub apps" and the count "3,337 apps" (inkSubtle 12);
  - a ghost icon-only **Refresh** button (`refresh`, label "Refresh the list"), which runs
    `package-index.py --details --force`.
- **Search field**: an `ArcticField` with `iconName: 'search'` and the placeholder "Search Flathub".
- **Empty query**:
  - an **"Arctic picks"** header, then the catalog modules that have a Flatpak method
    (`assets/featured.json`, §6.13);
  - installed picks stay listed with the Installed chip (as Omarchy does);
  - below them, the hint "Type to search all of Flathub."
- **Results**: at most 200, ranked by `PackageSearch.searchItems` (§6.4).
- **Rows** (`getapps/AppRow.qml`, 56 high):
  - an `AppTile` (40) with `imageSource` = the AppStream icon, falling back to the glyph `package`;
  - the name (15/DemiBold) and the summary (12, inkMuted, elided);
  - on the right, a **Verified** chip when AppStream says so, then the state:
    - **Install**: secondary, sm. Only the selected row's button is primary, together with a
      `Kbd` "Enter".
    - **Installed**: success chip, plus a ghost **Open** button.
    - **Waiting**: `clock` icon.
    - **A progress bar**: 4 px, amber fill, with "45%".
- **Details sheet** (`getapps/DetailsSheet.qml`) opens with Shift+Enter or a click on the row body.
  - It is a 360-wide panel anchored to the right of the card over a `scrim` rectangle, with:
    - the icon (64), name, developer and Verified chip;
    - the summary and the first three description paragraphs;
    - version, licence, categories and a homepage link (opened with `xdg-open`);
    - "Download · Installed size" from `apps.py info flatpak ID`, which fills in asynchronously
      and is left out offline;
    - the line "Installs for everyone on this computer" (or "…only for you", §6.9);
    - **Install** (primary) and **Close**.
- **Empty and error states**:
  - **Index loading**: "Getting the list of Flathub apps… this takes a minute the first time."
  - **No Flathub remote**: "Flathub isn't set up on this computer. Adding it asks for your
    password once." with the primary button **Add Flathub**, which queues an `add-remote` job.
  - **No `flatpak` command**: "Flatpak isn't installed." It is a hard Requires of `arctic-desktop`,
    so this case is rare.
  - **No match**: "No Flathub apps match “x”." with the secondary button **Search Fedora packages**,
    which opens `dnf` with the same query.

#### 3.3 Fedora packages (page `dnf`)

This page has the same structure as §3.2, with these differences:

- **Title and placeholder**: the title is "Fedora packages"; the placeholder is "Search Fedora's
  apps" or "Search all packages".
- **Segmented control** (`getapps/Segmented.qml`) in the header, `Apps · All packages`:
  - **Apps** lists the AppStream `desktop-application` components from `appstream-data`: name,
    summary, icon and categories, keeping only those whose package is available or installed. It is
    the default when `/usr/share/swcatalog/xml` exists.
  - **All packages** lists every available package name (about 70,000 🔍 count on F44), with its
    summary and repository label:
    - `fedora` / `updates` → "Fedora";
    - `rpmfusion-*` → "RPM Fusion";
    - `copr:*` → "COPR";
    - `arctic` → "Arctic Linux".
  - The All packages rows use the `layers` glyph tile.
  - Without `appstream-data`, only **All packages** appears, with the note "Install Fedora's app
    catalogue for names and icons" and a secondary button that queues
    `install dnf appstream-data` (§8).
- **Arctic picks**: the catalog modules with a dnf method.
- **Details** come from `apps.py info dnf NAME`: version, repository, download and installed size,
  licence, URL and description, plus developer and screenshots from AppStream when present. The
  sheet says "Asks for your password" next to **Install**.
- **Pending updates**: if `UpdateService.ready`, the job card adds "The updates waiting for a
  restart are prepared again two minutes after this" (`docs/wiki/Updates.md:40-43`).

#### 3.4 Web apps (page `web`, the engine from D4)

The page follows engine-design.md §5.3 ("Get apps → Web app").

- **URL field**: the placeholder is "Website address, like music.youtube.com". The help line
  underneath reads "It opens in its own window with its own sign-in, separate from your browser."
- **Typing**: runs `Inspect{url}` after 600 ms without typing.
  - Each new `Inspect` cancels the previous one (the engine does this; the client also sends
    `Cancel{request}` when the field is cleared).
  - `progress` events drive a status line such as "Reading the app manifest".
- **Preview card**:
  - **Icon choices**: a row of 48 px tiles, including the monogram. The selected one uses the
    selection colours.
  - **Name**: an editable field, prefilled from the engine's `name`.
  - **Runtime**: a picker from `Hello.runtimes`, shown only when more than one runtime is
    `available`. It reads "Open with: Arctic (built in) · Brave".
  - **Links**: the switch "Open other sites in your browser" (`links: browser|app`), on by default.
  - **Warnings**: each engine warning shows the `alert` icon, `warning` colour and its sentence.
  - **Existing copies**: when `installed` isn't empty, the note "You already have this web app."
    appears with **Open it** and **Add a second copy** (`new_copy: true`).
  - **Add**: the primary button reads **Add YouTube Music**. It calls
    `Install{token, name, icon, runtime, links, launch:false}`.
- **Done state**: "YouTube Music is in the launcher." with **Open YouTube Music** (primary,
  `Launch{id}`) and **Add another**.
- **Errors**: the engine's error `message` is shown as it comes. For code `offline`, the page also
  offers "Add with a letter icon" (`Install{url, icon:'monogram'}`).
- **Engine missing**: the page and the card are hidden. `apps.py sources` reports `webapp.present`.

#### 3.5 Terminal apps (page `terminal`, gap `tui-launchers`)

**Form**
- **Name**: 1-64 characters, no control characters, no `/`.
- **Command**: split with `shlex`. The first word must be found on `PATH`. Otherwise the page says
  "btop isn't installed. Install it from Fedora packages first." and offers a button,
  **Find btop in Fedora packages**, that opens `dnf` with that query.
- **Window**: segmented `Floating · Tiled`. Floating is the default.
- **Icon**: the icon of the program's own desktop entry when it has one (for btop, `Icon=btop`),
  otherwise `utilities-terminal`. **Choose a picture…** opens a `FileDialog` (QtQuick.Dialogs is
  already used by `Wallpapers.qml`).
- **Primary**: **Add btop**. It runs `apps.py terminal-app add …` (§6.11). The new row appears in
  the launcher by itself, because `DesktopEntries` watches `~/.local/share/applications`.

#### 3.6 Remove apps (page `remove`, D3)

**Header**: Back · "Remove apps".

**Tabs** (`Segmented.qml` as tabs): `Flatpak (12) · Fedora packages (40) · Web apps (3) ·
Terminal apps (1)`.
- The counts count removable rows only.
- The Web apps tab is hidden when the engine is missing and `List` has nothing.
- The Terminal apps tab is hidden while it has zero rows.

**Filter field**: "Filter your apps".

**Rows**
- Each row has a tile, the name, and a second line built per source:

| Source | Second line |
|---|---|
| Flatpak | `3.0.4 · Flathub · 412 MB · For everyone` (or `Only you` for the user installation). An app installed in both installations shows as two rows. |
| Fedora | `gimp · Fedora · 120 MB · You added it` (or `Came with Arctic Linux`, §6.6) |
| Web apps | `music.youtube.com · Arctic` (the runtime's name), plus `Running` when the engine says so |
| Terminal apps | `btop · floating window` |

- The right side has a secondary **Remove…** button. The selected row shows a `Kbd` "Delete" chip.
  The destructive red button appears only in the sheet.

**Fedora tab**
- It has a second segmented control, `Apps · Other packages you added`. The second view lists
  packages without a desktop entry that you added after installing, such as `ripgrep` (§6.6).

**Protected group**
- At the bottom of the Fedora tab, a collapsed "Part of Arctic Linux (N)" group lists protected rows.
  Each shows a `lock` icon and a reason, and has no button.
- It is there so that nobody wonders why Settings, pavucontrol or Blueman can't be removed.

**Saved sign-in data**
- A second section in the Web apps tab lists the engine's `kept` records.
- Each has a secondary **Delete data** button, which runs `Forget{ids}` after a small confirmation.

**After a removal**
- The row shows "Removing…", then disappears.
- A one-line toast at the bottom says "GIMP was removed."

**Live USB**
- The page and its card are hidden.
- `apps remove` over IPC opens the chooser instead.

#### 3.7 The remove sheet (`getapps/RemoveSheet.qml`)

The sheet is modal inside the card: a centred panel, 440 wide, over a `Theme.scrim` rectangle. Both
the Remove page and the launcher (§3.9) use it.

- **Title**: "Remove GIMP?". While the preview runs, a spinner line reads "Checking what else goes…".
- **Body by source**:

| Source | Body |
|---|---|
| Flatpak | "GIMP will be removed for everyone on this computer." (or "…for you".) A checkbox, **off** by default: "Also delete its settings and data (412 MB in ~/.var/app/org.gimp.GIMP)". The line "Runtimes no other app uses are removed too." |
| Fedora | "These packages will be removed:" lists the asked packages, then "Also removed, because they need it:" (dependents), then "No longer needed:" (unused dependencies). The checkbox "Also remove packages nothing else needs" is **on** by default; unticking it runs the preview again with `--no-autoremove`. Then "Frees 180 MB.", and, when snapper's root config exists, "A snapshot is taken first, so this can be undone." |
| Web apps | "YouTube Music will be removed from the launcher." (plus "It's open and will be closed." when `running`). A checkbox, **off** by default: "Also sign out and delete its data (48 MB)". Off maps to `keep_data: true`, and the record then shows under "Saved sign-in data". |
| Terminal apps | "The launcher entry for btop will be removed. btop itself stays installed." |
| Launcher entry | "This is your own launcher entry for X." When it overrides an installed app's entry: "Removing it brings back the original." |
| Nix | "X was installed with Nix. Remove it in a terminal: `sudo nix profile remove --profile /nix/var/nix/profiles/default X`." Only **Close** is offered (§14, Nix is deferred). |

- **Buttons**:
  - **Cancel** (secondary) has the initial focus.
  - **Remove GIMP** (destructive) is reached with Tab.
  - Enter activates the focused button only.
- **Blocked**: the title becomes "GIMP can't be removed" with a `lock` icon, the reason sentence
  (§6.8) appears, and only **Close** is offered. The reasons are:
  - a protected package;
  - the transaction would remove `arctic-desktop`;
  - it is the only terminal;
  - it is your login shell.
- **Warnings** (for example, it's your default browser) show above the buttons, with an `alert` icon
  in the warning colour:
  - "Firefox opens your web links and `Super + B`. Choose another browser in Settings → Default apps
    after removing it."
- **Stale preview**: the sheet stores the preview's `rpmdb` stamp. If
  `/usr/lib/sysimage/rpm/rpmdb.sqlite` changed before you confirm (🔍 path on F44), the preview runs
  again before the job starts.

#### 3.8 Console (page `console`)

The console is `InstallConsole.qml`, moved with `git mv` to `shell/getapps/ConsolePage.qml`.

- The title reads "Console". Back returns to the chooser.
- Both Processes (`:62-106`) move into `AppsService`. The page binds to:
  - `AppsService.consoleOutput`;
  - `consoleSecret`, `consoleRunning` and `consoleNotice`;
  - `packages` and `packageIndex`.
- **Refresh list** runs the index with `--force`.
- The notice at `:104` becomes "The console stopped. It starts again the next time you open it."
  The service restarts the runner on the next `open()`.
- Changes to typed commands (§6.2) are listed in the runner's `WELCOME`:
  - `dnf remove|erase` and `flatpak uninstall|remove` no longer get `-y`. The transaction list and
    `[y/N]` appear in the console, answered on the input line, which meets D3 for the typed path.
  - A protected name is refused.

#### 3.9 Delete on a launcher row (gap `launcher-uninstall-key`)

- **Keys**: with an `app` result selected in the launcher's `home` or `apps` view, either of these
  opens `RemoveSheet` over the launcher card, for `entry.id`:
  - **Shift+Delete**;
  - **Delete** while the search field's cursor is at the end of its text (so Delete still deletes
    characters otherwise).
- **Mouse**: the hovered or selected app row shows a ghost icon-only button (`trash`, label
  "Remove app"). A right-click on the row does the same.
- **Resolving the owner**: `AppsService.owner(desktopId)` runs `apps.py owner ID`. The order is
  §6.12: web app, terminal app, Flatpak, rpm, own launcher entry, Nix.
- **Esc** closes the sheet and returns to the same launcher list and selection.
- **Footer hint**: `Delete` · "remove" appears when the selected result is an app, not on the live
  USB.

#### 3.10 Jobs, progress and notifications (`getapps/JobCard.qml`, `AppsService`)

**Queue**
- `AppsService.jobs` holds every job, `{id, kind, source, ids, label, icon, phase, percent, step,
  code, message}`, with `phase: waiting | running | done | failed | cancelled`.
- Jobs run one at a time, in order.

**Job card** (at the bottom of the chooser, source and Remove pages)
- The icon, "Installing GIMP", then the progress bar with its percent, or an indeterminate bar
  when no numbers are known yet.
- The step text, for example "Downloading 3 of 12".
- **Show details** reveals the transcript: a monospace well, 200 high, with `transcript` turned on
  in the runner (§6.2).
- **Stop**, which sends `interrupt`, while the job runs. **Cancel** takes a job that is still
  waiting off the queue.

**Password**
- While `PolkitDialog`'s agent `isActive`, the step reads "Waiting for your password".
- `PolkitDialog.qml` gets a `readonly property bool active` so `AppsService` can read it; §7.2.

**Notifications**
- A notification is sent when the job ends while `AppsService.watching` is false (the launcher is
  closed or not on Get apps). It runs `notify-send` in a `Process`, not `execDetached`, so the chosen
  action comes back on stdout:

  ```
  notify-send -a 'Arctic Linux' -i <icon> -A open=Open 'GIMP is installed' 'It's in the launcher (Super + Space).'
  notify-send -a 'Arctic Linux' -i dialog-warning -A details='Show details' 'GIMP wasn't installed' '<sentence>'
  notify-send -a 'Arctic Linux' -i <icon> 'GIMP was removed' ''
  ```

- stdout `open` launches the new desktop entry; `details` opens Get apps on the job's page with the
  transcript open.
  - 🔍 libnotify 0.8 `-A` prints the chosen action's name and waits. Test headless against D6's
    shell NotificationServer.

**Queries for other sections**
- `AppsService.busy` and `AppsService.currentLabel`. The power-menu-extras item (P2) uses them for
  "An app is still installing. Restart anyway?".

#### 3.11 Live USB

- Get apps works as today, with the note from §3.1.
- Remove apps (card, launcher special, Delete key, IPC) is hidden: removals only change the RAM
  overlay.
- Web apps and Terminal apps work, and are lost at reboot.

---

### 4. Keyboard

The whole card is keyboard-first. Every control is reachable with Tab and has a visible focus
ring.

| Where | Key | Does |
|---|---|---|
| Chooser | `←` `→` `↑` `↓`, `Tab`, `Shift + Tab` | Move between cards (a 2D grid: row 1 has 3 cards, row 2 has 3) |
| Chooser | `Enter`, `Space` | Open the selected card |
| Chooser | `1` … `6` | Open that card directly (digits follow the visible cards) |
| Source pages | type | Search (the field has focus) |
| Source pages | `↑` / `↓`, `Tab` / `Shift + Tab` | Move through the results |
| Source pages | `Enter` | Install the selected app, or open it when it is installed |
| Source pages | `Shift + Enter` | Details for the selected app |
| Fedora page | `Ctrl + Tab`, `Ctrl + Page Down` / `Ctrl + Page Up` | Switch between Apps and All packages |
| Remove page | `↑` / `↓` | Move through the rows |
| Remove page | `Delete` or `Enter` | Open the remove sheet for the selected row |
| Remove page | `Ctrl + Tab`, `Ctrl + Page Down` / `Ctrl + Page Up` | Next or previous tab |
| Sheets | `Tab` / `Shift + Tab` | Move between checkboxes and buttons; **Cancel** has the initial focus |
| Sheets | `Enter` / `Space` | Activate the focused control |
| Web apps | `Enter` in the URL field | Inspect now, without waiting for the pause |
| Web apps | `Ctrl + Enter` | Add the previewed web app |
| Console | `Tab`, `↑`/`↓`, `Enter`, `Ctrl + C` | As today (`InstallConsole.qml:285-313`) |
| Launcher | `Shift + Delete`, or `Delete` with the cursor at the end | Remove the selected app (§3.9) |
| Anywhere in Get apps | `Super + Space` | Launcher home (unchanged, `shell.qml:30`) |

**Esc goes back one step.** It never closes the launcher from inside Get apps.

- `GetApps.qml` handles Esc (`Keys.onEscapePressed`, with `event.accepted = true`), so it never
  reaches `Popover.qml:99`.
- It works through this ladder, and the pure-JS `GetApps.backStep(state)` returns which step applies:

1. A sheet or the details panel is open: close it.
2. A search, filter or URL field on this page has text: clear it. This matches the launcher's
   home rule (`Launcher.qml:179`).
3. The page isn't `choose`: go to `choose`.
4. The page is `choose`: `backRequested()` → `launcher.openView('home')`. A second Esc there closes
   the launcher as before.

**Conflicts checked** (D7):
- No new global Mango binds. `Super + Shift + A` stays (`binds.conf:21`), and Remove apps gets no
  global key: it has the chooser digit `5`, the launcher special, IPC and the command menu.
- Every key above works only inside the launcher surface, which holds `WlrKeyboardFocus.Exclusive`,
  and none uses `Super`, so no Mango bind can take them.
- None uses `Alt + Shift`, `Ctrl + Shift` or both Shifts, so none collides with any layout-switch
  option in `SWITCH_KEYS` (`settings/scripts/arctic_settings.py:2053-2054`: `grp:alt_shift_toggle`,
  `grp:ctrl_shift_toggle`, `grp:shifts_toggle`, `grp:alt_space_toggle`, …).
  - `Ctrl + Shift + Tab` was rejected for "previous tab" for this reason; `Ctrl + Page Up` replaces it.

---

### 5. Entry points and IPC

| Entry | Change |
|---|---|
| `Super + Shift + A` (`binds.conf:21`) | Unchanged: `arctic-shell-ipc apps install` now opens the chooser. |
| Launcher special "Get apps" (`Launcher.qml:51`) | desc → "Install from Flathub, Fedora or the web"; keywords add `web app terminal`. |
| **New** launcher special "Remove apps" | `{kind:'remove', name:'Remove apps', desc:'Uninstall Flatpak apps, Fedora packages and web apps', glyph:'trash', keywords:'uninstall delete remove flatpak dnf web app'}`, after "Get apps". Not on the live USB. |
| **New** launcher fallback row | When a search in `home` or `apps` finds no app: `{kind:'get-search', name:'Find “x” in Get apps', desc:'Search Flathub and Fedora', glyph:'package'}` → opens `flatpak` with the query. It goes before any "Search the web" row that `launcher-search-modes` adds. |
| Delete on an app row | §3.9 |
| Settings → Default apps | The "Get apps" button (`AppsPage.qml:51-57`) is unchanged. A new row "Install and remove apps" gets two buttons, **Get apps** and **Remove apps** (`arctic-shell-ipc apps remove`); §7.3. |
| Command menu (`command-menu` section) | Install branch rows `install.flathub|fedora|web|terminal|console` call `shell.openGetApps(screen, '<page>')` (or IPC `apps open <page>`). Remove branch rows `remove.flatpak|fedora|web|terminal` open `remove/<tab>`. Guards hide Remove rows whose count is 0 (from `apps.py counts`, cached). The menu never repeats the catalog UI. |
| first-login-welcome (P1, other section) | Its "Get apps" step calls `apps install`. |
| ocr-qr-capture (P1, other section) | "Install tesseract-langpack-heb" calls `apps search dnf tesseract-langpack-heb`. |

**IPC target `apps`** (`shell.qml:95-99`). No function is named `show` (`shell.qml:127`).

```qml
IpcHandler {
    target: 'apps'
    function install(): void { shell.openGetApps(null, 'choose', ''); }          // unchanged name
    function remove(): void { shell.openGetApps(null, 'remove', ''); }
    function open(page: string): void { shell.openGetApps(null, page, ''); }       // choose|flatpak|dnf|web|terminal|remove|remove/<tab>|console
    function search(page: string, text: string): void { shell.openGetApps(null, page, text); }
    function uninstall(desktopId: string): void { shell.uninstallEntry(null, desktopId); }
    function toggle(): void { shell.toggleLauncher(null); }                       // unchanged
}
```

- An unknown page string opens `choose`. `GetApps.parsePage()` is unit-tested.
- 🔍 Quickshell 0.2.1 snapshot `IpcHandler` with two `string` arguments: prove it with a headless
  `ipc apps search flatpak gimp` step. Fallback: one argument `"flatpak:gimp"`.

**`shell.qml`**
- `openGetApps(screen, page, query)` replaces `:34-37`. It sets `launcher.getPage` and
  `launcher.getQuery`, then `launcher.openView('get', page, query)` or `present(launcher, screen)`.
- New `uninstallEntry(screen, desktopId)`: open the launcher home, then `launcher.askRemove(desktopId)`.
- Update the header comment at `:13-15` with the new functions.

---

### 6. Backend

#### 6.1 `shell/AppsService.qml` (new singleton, registered in `shell/qmldir`)

**Properties**

```
readonly property bool busy                  // a job runs or waits
readonly property var job                    // the running job, or null
property var jobs: []                        // every job this session (last 20 kept)
readonly property string currentLabel        // "Installing GIMP"
property bool watching: false                // set by the launcher: open && view === 'get'
property var sources: ({})                   // apps.py sources
property var packages: []                    // console completion (names + 'flathub:' ids)
property var packageIndex                    // PackageSearch.prepare(packages)
property var flathubItems: []                // search items: catalog flathub, or the TSV fallback
property var fedoraApps: []                  // catalog fedora
property var fedoraPackages: []              // all packages [{id, repo, summary}]
property var installedIds: ({flatpak: {system: [], user: []}, dnf: []})
property var installed: ({})                 // per source, apps.py installed <source>
property string indexError: ''
property bool indexRefreshing: false
property string consoleOutput / consoleNotice; property bool consoleRunning / consoleSecret
```

**Functions**

```
function ensureStarted()                     // start the runner and load the index (first open of Get apps)
function install(source, ids, label, icon)   // source 'flatpak' | 'dnf'
function remove(request)                     // {source, ids, installation, delete_data, autoremove, label, icon, rpmdb}
function addFlathub()
function cancel(jobId)
function refreshIndex(force)
function refreshInstalled(source)            // apps.py installed <source>; web → WebAppClient List
function owner(desktopId, callback)
function previewRemove(request, callback)    // apps.py preview-remove …
function helper(argv, callback)              // run apps.py, parse one JSON line, {ok:false,error} on failure
function consoleSend(action, text)
signal jobFinished(var job)
```

**Children**

- the `Process` for `install-terminal.py`;
- the `Process` for `package-index.py --details`;
- a helper `Component` that creates one `Process` + `StdioCollector` per `apps.py` call, the pattern
  in `settings/Backend.qml:100-130`;
- `WebAppClient {}`;
- a `Timer` that drops the large index arrays 5 minutes after the launcher closes while no job runs.
  They are loaded again on the next open.

**Lifecycle**
- On runner exit with jobs waiting: restart the runner once, and mark the running job `failed`
  with "Get apps stopped unexpectedly. Nothing else changed; try again."
- `WebAppClient` starts only when the Web apps page or tab, or a launcher web-app Delete, needs it.

**Other**
- `ARCTIC_WEBAPP_CMD` (screenshots and tests only, like `ARCTIC_UPDATE_STATUS` in
  `UpdateService.qml:156`) replaces `arctic-webapp`.

#### 6.2 Job runner: `install-terminal.py` gains `run`

**Requests** (stdin, one JSON line each)

```json
{"action":"start","text":"dnf search editor","secret":false}             // console, unchanged
{"action":"input","text":"…","secret":true}                                // unchanged
{"action":"interrupt"}                                                      // unchanged
{"action":"clear"}                                                          // unchanged
{"action":"transcript","on":true}                                           // new: include "output" in state lines
{"action":"run","job":{"id":"j7","kind":"install","source":"dnf","ids":["gimp"]}}
{"action":"run","job":{"id":"j8","kind":"install","source":"flatpak","ids":["org.gimp.GIMP"],"installation":"system","remote":"flathub"}}
{"action":"run","job":{"id":"j9","kind":"remove","source":"dnf","ids":["gimp"],"autoremove":true}}
{"action":"run","job":{"id":"j10","kind":"remove","source":"flatpak","ids":["org.gimp.GIMP"],"installation":"system","delete_data":false,"unused":true}}
{"action":"run","job":{"id":"j11","kind":"add-remote","source":"flatpak","remote":"flathub","installation":"system"}}
```

**State** (stdout)
- The runner sends at most one line every 100 ms while a job runs. `output` is present only while
  `transcript` is on; today the full transcript goes out at 20 Hz.

```json
{"running":true,"secret":false,"notice":"",
 "job":{"id":"j8","kind":"install","source":"flatpak","ids":["org.gimp.GIMP"],"phase":"running",
        "percent":45,"done":null,"total":null,"step":"Installing org.gimp.GIMP"},
 "output":"…"}
{"running":false,"secret":false,"notice":"","job":null,
 "finished":{"id":"j8","ok":true,"code":0,"message":""}}
{"running":false,"secret":false,"notice":"","job":null,
 "finished":{"id":"j7","ok":false,"code":126,"message":"You closed the password prompt. Nothing was installed."}}
```

- A console `start` shows as `job.kind = "console"`, so the GUI knows the runner is busy.

**Builders**
- `build_job(job)` in `shell/scripts/appslib.py` returns a list of argv lists, run in order until
  one fails.
- `install-terminal.py` imports it. The script's own directory is `sys.path[0]`.

| kind / source | argv (exact; tested) |
|---|---|
| install / dnf | `['pkexec','/usr/bin/dnf5','install','-y',*pkgs]` |
| install / flatpak, system | `['flatpak','install','--system','-y','--noninteractive',remote,*ids]` |
| install / flatpak, user | `['flatpak','install','--user','-y','--noninteractive',remote,*ids]`, preceded, when the user installation has no such remote, by `['flatpak','remote-add','--user','--if-not-exists','flathub','https://dl.flathub.org/repo/flathub.flatpakrepo']` |
| remove / dnf | `['pkexec','/usr/bin/dnf5','remove','-y',*(['--no-autoremove'] if not autoremove else []),*pkgs]` |
| remove / flatpak | `['flatpak','uninstall','--'+installation,'-y','--noninteractive',*(['--delete-data'] if delete_data else []),*ids]`, then, if `unused`, `['flatpak','uninstall','--'+installation,'-y','--noninteractive','--unused']` (the installer's pattern, `installer.go:1111-1121`) |
| add-remote / flatpak | `['flatpak','remote-add','--'+installation,'--if-not-exists','flathub','https://dl.flathub.org/repo/flathub.flatpakrepo']`. Only `flathub` is allowed (`FlatpakRemotes`, `installer.go:42-44`). The system variant asks for a password (`configure-remote`). |

**Validation** (`ValueError` → `finished.ok:false` with the sentence)
- dnf names must match `NAME` (`:49`).
- Flatpak ids must match `^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*){2,}$`.
- `installation` must be `system` or `user`; `remote` must be `flathub`.
- A remove job must not contain a protected name, `appslib.protection().check(names)`, §6.8. This is
  defence in depth, since the GUI already blocks it.
- At most 50 ids per job.

**Progress** (`appslib.progress(lines)`)
- Called on the last 6 pyte screen lines each tick.
- dnf5: port `ParseDNF` from `installer.go:648-659`, `^\[\s*(\d+)/(\d+)\]`. The line's text after
  the counter becomes `step`, and `percent = done*100/total`.
- flatpak: port `ParsePercent` from `installer.go:633-646`, using the last `NN%`.
- 🔍 Capture real dnf5 5.4.6.0 and flatpak 1.18.2 PTY output on F44 as test fixtures
  (`shell/tests/fixtures/apps/progress-*.txt`). Both are the F44 versions ✅ (mdapi).

**Error sentences** (`appslib.explain(job, code, tail)`, unit-tested)

| When | Sentence |
|---|---|
| pkexec exit 126 (dialog dismissed) | "You closed the password prompt. Nothing was installed." / "…removed." |
| pkexec exit 127 | "Arctic Linux couldn't get permission to make this change. Nothing was changed." |
| dnf5 "No match for argument" | "GIMP isn't in Fedora's repositories any more. Try Flathub." |
| Download or curl errors in the tail | "GIMP couldn't be downloaded. Check your internet connection and try again. Nothing else changed." |
| "Waiting for process with pid" in the tail | step "Waiting for another software change to finish" (not an error) |
| flatpak "already installed" | treated as success |
| Anything else | "GIMP wasn't installed. Show details has what went wrong." |

**Other changes**
- After a job ends with code 0, `after_flatpak_install` still fires. Verb detection (`:117-121`)
  finds `install` after the new options ✅ (reading the code).
- **EOF safety**: when stdin closes while a job runs, `main` stops reading stdin but keeps
  draining the PTY until the job exits, then returns. A shell restart no longer sends SIGHUP to a
  running dnf transaction.
- **Console changes** in `build_command`:
  - `dnf remove|erase` and `flatpak uninstall|remove` are left out of `with_yes`, so the typed
    path confirms in the console (D3).
  - `dnf remove|erase NAME…` with a protected bare name raises "arctic-shell is part of Arctic
    Linux, so Get apps won't remove it."
  - The `WELCOME` text (`:58-61`) becomes: "Console\r\nType a dnf or flatpak command, or an app
    name to install it. Removals list what goes and ask first. The other Get apps pages have
    search, details and Remove apps.\r\n\r\n"

#### 6.3 `shell/scripts/apps.py` (new; standard library only; the `wallpapers.py` pattern)

**Output rules** (the same contract as settings/Backend.qml and the engine's `--json`)
- Every command prints **exactly one line** of JSON.
- Success is `{"ok":true,…}` with exit 0.
- Failure is `{"ok":false,"error":"<sentence>","code":"<code>"}` with exit 1.
- A usage error exits 2.
- Nothing is printed to stdout before the result.

**Commands**

```
apps.py sources
apps.py catalog flathub|fedora [--appstream FILE] [--tsv]
apps.py info flatpak ID | info dnf NAME
apps.py installed flatpak|dnf|terminal [--other]
apps.py installed-ids
apps.py counts
apps.py preview-remove dnf [--no-autoremove] PKG…
apps.py preview-remove flatpak ID --installation system|user
apps.py owner DESKTOP_ID
apps.py terminal-app add --name NAME --command CMD --window float|tile [--icon PNG]
apps.py terminal-app remove ID
apps.py launcher-entry remove DESKTOP_ID
apps.py protected
```

`--appstream FILE --tsv` is a development and tour hook (§10): it parses a given file and prints
TSV, not JSON.

**Output shapes** (snake_case):

```json
// sources
{"ok":true,"live":false,"wheel":true,
 "flatpak":{"present":true,"flathub":{"system":true,"user":false},"install_to":"system"},
 "dnf":{"present":true},"fedora_catalog":{"present":true,"files":["/usr/share/swcatalog/xml/fedora.xml.gz"]},
 "webapp":{"present":true,"command":"arctic-webapp"},"snapshots":true}

// catalog flathub (cached; see 6.5)
{"ok":true,"source":"flathub","items":[{"id":"org.gimp.GIMP","name":"GIMP","summary":"Create images and edit photographs",
  "icon":"/var/lib/flatpak/appstream/flathub/x86_64/active/icons/128x128/org.gimp.GIMP.png","categories":["Graphics"],
  "developer":"The GIMP team","verified":true,"keywords":["photo","paint"]}]}

// catalog fedora
{"ok":true,"source":"fedora","items":[{"id":"org.gimp.GIMP","pkg":"gimp","name":"GIMP","summary":"…",
  "icon":"/usr/share/swcatalog/icons/fedora/128x128/gimp.png","categories":["Graphics"],"keywords":[]}]}

// info dnf gimp
{"ok":true,"name":"gimp","evr":"2:3.2.6-1.fc44","repo":"fedora","repo_label":"Fedora","download_bytes":63963136,
 "install_bytes":201326592,"license":"GPL-3.0-or-later","url":"https://www.gimp.org/","summary":"…","description":"…",
 "appstream":{"developer":"The GIMP team","screenshots":[]}}

// installed flatpak
{"ok":true,"source":"flatpak","apps":[{"id":"org.gimp.GIMP","name":"GIMP","version":"3.0.4","origin":"flathub",
  "installation":"system","size_text":"412.3 MB","icon":"org.gimp.GIMP","desktop_id":"org.gimp.GIMP",
  "data_path":"/home/u/.var/app/org.gimp.GIMP"}]}

// installed dnf
{"ok":true,"source":"dnf","apps":[{"package":"gimp","evr":"2:3.2.6-1.fc44","name":"GIMP","summary":"…",
  "desktop_ids":["org.gimp.GIMP"],"icon":"gimp","repo":"fedora","repo_label":"Fedora","install_bytes":201326592,
  "added":"you","protected":false,"protected_reason":"","roles":[]}],
 "protected":[{"package":"blueman","name":"Blueman","reason":"needed-by-desktop",
  "message":"The Arctic desktop needs Blueman."}]}
// installed dnf --other: same shape, rows without desktop entries (added:"you" only)

// installed-ids
{"ok":true,"flatpak":{"system":["org.gimp.GIMP"],"user":[]},"dnf":["bash","gimp", "…"]}

// counts (cached; for the command menu's guards and the tab counts)
{"ok":true,"flatpak":12,"dnf":40,"web":3,"terminal":1}

// preview-remove dnf gimp
{"ok":true,"source":"dnf","request":["gimp"],"autoremove":true,"rpmdb":"1759050000.123456",
 "packages":[{"name":"gimp","evr":"2:3.2.6-1.fc44","why":"asked","install_bytes":201326592},
             {"name":"gimp-data-extras","evr":"…","why":"needs-it","install_bytes":1048576},
             {"name":"babl","evr":"…","why":"unused","install_bytes":3145728}],
 "frees_bytes":205520896,"blocked":null,
 "warnings":[{"code":"default-app","role":"images","message":"GIMP opens your pictures. Choose another app in Settings → Default apps after removing it."}],
 "undo":true}
// blocked example
{"ok":true,"source":"dnf","request":["blueman"],"packages":[…],"frees_bytes":…,
 "blocked":{"package":"arctic-desktop","code":"protected",
            "message":"Removing Blueman would also remove arctic-desktop, which Arctic Linux needs."},"warnings":[],"undo":true}

// preview-remove flatpak
{"ok":true,"source":"flatpak","id":"org.gimp.GIMP","name":"GIMP","installation":"system",
 "data_path":"/home/u/.var/app/org.gimp.GIMP","data_bytes":432013312}

// owner
{"ok":true,"desktop_id":"org.gimp.GIMP","name":"GIMP","icon":"org.gimp.GIMP",
 "path":"/var/lib/flatpak/exports/share/applications/org.gimp.GIMP.desktop",
 "source":"flatpak","target":{"id":"org.gimp.GIMP","installation":"system"},"blocked":null}
// source: webapp | terminal-app | flatpak | dnf | launcher | nix | unknown
// dnf target: {"package":"gimp"}; launcher target: {"path":"…","overrides":true}; nix target: {"name":"…"}

// terminal-app add
{"ok":true,"app":{"id":"org.arcticlinux.TerminalApp.Float.Btop","name":"Btop",
 "desktop_file":"/home/u/.local/share/applications/org.arcticlinux.TerminalApp.Float.Btop.desktop"}}
```

#### 6.4 Index and search

**`shell/scripts/package-index.py`**

- **dnf** (`:64`): `dnf5 -q repoquery --available --qf '%{name}\t%{repoid}\t%{summary}\n'`. Keep the
  first line per name, since multi-arch lines repeat. The cache is `packages.tsv`.
- **Flatpak** (`:70`): `flatpak remote-ls --system|--user --app --columns=application,name,description
  flathub`.
  - Pass the installation that has the flathub remote, from `appslib.flathub_installations()`,
    reusing `flatpak remotes --columns=name,options`.
  - 🔍 Whether `remote-ls flathub` fails with "found in multiple installations" when both
    installations have it. Test by hand on F44.
  - The cache is `flathub.tsv`.
  - This call also refreshes the remote's AppStream when it is older than 86400 s ✅ (research,
    flatpak `remote-ls.c`), which keeps §6.5 fresh.
- **Parsing** (`:56`): replace the "drop lines with spaces" filter with TSV parsing. The first field
  must match `NAME`; otherwise skip the line.
- **Old caches**: read `packages.txt` / `flathub.txt` when there is no TSV (summaries empty). The
  tour seeds these today (`tools/lib/tour.py:689-694`).
- **Flags**:
  - `--details` adds `details: {dnf: [[name, repo, summary], …], flathub: [[id, name, summary], …]}`
    to each JSON line. `packages` is unchanged, for the console.
  - `--force` refreshes even when the cache is fresh.
- **Errors**: a Flatpak failure gets the sentence "Could not read the Flathub app list.", but only
  when the flathub remote exists.
- 🔍 One stdout line with 70k names and summaries is about 6 MB. Measure `SplitParser` with it in
  the headless shell. Fallback: write `~/.cache/arctic/getapps-index.json` and read it with a
  `FileView`.

**`shell/PackageSearch.js`**

Keep `context`, `complete`, `prepare` and `search` as they are for the console. Add:

```js
// prepareItems([{id, name, summary, keywords?, repo?}]) -> index; lowercases once.
// searchItems(index, query, limit) -> items, best first:
//   name: strict (exact 10000 / prefix / substring) then fuzzy, weight +100
//   id (and last dotted part for app ids): strict then fuzzy, +50
//   keywords: substring, +20
//   summary: substring only, +0, only while strong matches < limit
```

#### 6.5 AppStream metadata (`apps.py catalog`)

**Fedora**
- Files: `/usr/share/swcatalog/xml/*.xml.gz` and `*.xml`: `fedora.xml.gz`, `other-repos.xml` and
  `gstreamer-non-free.xml` ✅ (mdapi file list for appstream-data 44-4.fc44), plus
  `rpmfusion-*.xml.gz` if present 🔍 (RPM Fusion's appstream-data packages).
- Parse with `gzip` + `xml.etree.ElementTree.iterparse`, keeping only `component`s of type
  `desktop-application` or `desktop` that have a `pkgname`. Read:
  - `id`;
  - `name` and `summary` without `xml:lang`;
  - `categories/category` and `keywords/keyword`;
  - `developer_name` (or `developer/name`);
  - `project_license`;
  - `url[@type=homepage]`;
  - the first three `description/p`.
- Icons: `icon[@type=cached]` → `/usr/share/swcatalog/icons/<origin>/<128x128|64x64>/<name>`, where
  `<origin>` is the `components` root's `origin`. There are 2051 files in 64x64 and 1021 in 128x128
  ✅ (mdapi). `icon[@type=stock]` is kept as a themed icon name.
- Filter against the dnf index: hide components whose `pkg` is neither available nor installed.

**Flathub**
- File: `<installation>/appstream/flathub/<arch>/active/appstream.xml.gz`. `<installation>` is
  `/var/lib/flatpak` or `~/.local/share/flatpak`; `<arch>` is `os.uname().machine`. The path layout
  is ✅ in `flatpak/common/flatpak-dir.c:5597-5600`.
- Icons: `…/active/icons/128x128/<name>`, falling back to `64x64` 🔍. Check the checkout on F44 with
  the flathub remote added.
- The verified flag: `custom/value[@key="flathub::verification::verified"] == "true"` 🔍. Check
  against the real file.

**Caches**
- `~/.cache/arctic/appstream-fedora.json` and `appstream-flathub.json`, keyed on each source file's
  `(path, st_mtime_ns, st_size)`.
- 🔍 Cold parse time for both (target ≤ 2 s on the reference laptop). Later calls read the cache
  (≤ 100 ms).

**Missing files**
- `apps.py` returns `{"ok":true,"items":[],"missing":true}`. The pages then fall back to the TSV
  index (names from `flatpak remote-ls`, no icons) or to All packages.

**No online Flathub API**
- It would send what you type off the machine (§14).

#### 6.6 Installed lists

**Flatpak**
- Command: `flatpak list --app --columns=application,name,version,origin,installation,size`.
  - Without a TTY, the output is tab-separated with no header ✅ (research, `flatpak-table-printer.c`).
  - `--app` hides runtimes and the adw-gtk3 theme extensions ✅.
- Name and icon come from the exported desktop file:
  - `/var/lib/flatpak/exports/share/applications/<id>.desktop` for system installs;
  - `~/.local/share/flatpak/exports/share/applications/<id>.desktop` for user installs.
- `data_path` is `~/.var/app/<id>`. Its size is computed with a bounded `os.scandir` walk (2 s)
  only in `preview-remove`.

**dnf (user-facing apps)**
1. **Desktop files.** Scan the `applications/**/*.desktop` files under each `XDG_DATA_DIRS` entry
   (default `/usr/local/share:/usr/share`). Skip:
   - flatpak export directories;
   - anything under `/nix`;
   - `$XDG_DATA_HOME`.
   Parse the files with the same rules as `settings/scripts/arctic_settings.py:1734-1786`:
   `Type=Application`, not `Hidden`, has `Name` and `Exec`, and `NoDisplay` recorded. That logic is
   copied into `appslib.py`, because Settings and the shell are separate packages. A test runs both
   parsers on the same fixture directory and compares the results.
2. **Owners.** `rpm -qf --qf '[%{FILENAMES}\t%{=NAME}\n]' -- PATH…` prints each owning package's full
   file list. Keep the lines whose first field is one of the queried paths.
   - Unowned paths print "is not owned by any package", which has no tab, so it is skipped.
   - A path with two owners gets both.
   - This doesn't depend on output order.
   - 🔍 Time on an installed Arctic system (target < 1 s); measure in WP-A0.
3. **Package facts.** `dnf5 repoquery --installed --qf '%{name}\t%{reason}\t%{from_repo}\t%{installtime}\t%{installsize}\t%{evr}\t%{summary}\n'`.
   - It loads only the system repo, so it works offline ✅ (research, `repoquery.cpp`).
   - Every tag exists ✅ (dnf5 `repoquery.8.rst`).
4. **Grouping.** One row per package.
   - Name and icon come from the entry whose id equals the package name, else from the first entry
     without `NoDisplay`.
   - Packages whose only entries are `NoDisplay` are dropped.
   - `Terminal=true` apps (btop, htop, yazi) are kept.
5. **The `added` label.**
   - `you` when `reason == "User"` and `installtime` is later than the mtime of
     `/var/log/arctic-install` (created at the end of an install, `installer.go:1537`).
   - `arctic` otherwise.
   - With no such directory (for example dotfiles on plain Fedora), the label is left out.
   - This is only a label and sort key. It never decides what can be removed.
   - 🔍 Deferred installer apps that `arctic-firstboot` installs after the first boot show as `you`.
     Accepted; §14.
6. **`--other`.** Packages with `added == you`, no desktop entry and no protection, for example
   `ripgrep` installed from the Fedora page.
7. **Protection** (§6.8) and **roles** (`/etc/arctic/default-apps`, then
   `~/.config/arctic/default-apps`, parsed like `arctic_settings.read_role_file`, `:1834-1843`) are
   added to each row.

**Web apps**
- `WebAppClient.List{kept:true}` (engine-design §5.2). The fields used are `id`, `name`, `host`,
  `icon_path` (→ `AppTile.imageSource`), `runtime`, `running` and `problem`.
- Orphans (`problem != ""`) are listed so that they can be removed.

**Terminal apps**
- `$XDG_DATA_HOME/applications/org.arcticlinux.TerminalApp.*.desktop` files that have
  `X-Arctic-TerminalApp-Id`.

**Caches**
- `~/.cache/arctic/installed-dnf.json` is keyed on:
  - the mtime of `rpmdb.sqlite`;
  - the mtimes of the scanned `applications` directories;
  - the mtimes of both `default-apps` files;
  - the user's shell.

#### 6.7 dnf removal: preview and execution

**Preview** (as the user, never pkexec)

```
dnf5 remove --store=$XDG_RUNTIME_DIR/arctic-apps/remove-<16 hex> -y [--no-autoremove] PKG…
```

- dnf5 lets a transactional command run unprivileged when the transaction is stored ✅ (research:
  `dnf5/context.cpp` `cmd_requires_privileges`).
- 🔍 That dnf5 5.4.6.0 on F44 accepts `remove --store` as a normal user. The WP-A0 harness pins it.
- `remove` loads only the system repo, so it works offline ✅ (research, `remove.cpp:111-113`).
- `apps.py` parses `DIR/transaction.json`, the same file format `packaging/updates/arctic-update-helper`
  already reads:
  - every `rpms[]` entry with `action` `Remove`;
  - its `reason` mapped to `why`: the requested names are `asked`, the reason that dnf5 uses for
    dependents is `needs-it`, and the reason for unused dependencies (clean) is `unused`.
  - 🔍 The exact `reason` strings for dependents and for unused dependencies are pinned by WP-A0 from
    a real transaction.
- The directory is deleted after parsing. Sizes come from the installed cache.
- **Fallback**, only if WP-A0 shows `--store` needs root: `LC_ALL=C dnf5 remove --assumeno PKG…`.
  - Parse the "Removing:", "Removing dependent packages:" and "Removing unused dependencies:"
    sections.
  - Exit code 1 with "Operation aborted by the user." counts as success here ✅ (research,
    `exception.cpp`).
  - A resolve error that mentions "protected packages" becomes `blocked`.

**Checks on the preview** (`blocked` set → the sheet shows the reason and only **Close**)

1. Any package in the transaction is protected (§6.8), for example `arctic-desktop` being dragged
   out as a dependent.
2. It removes the package that provides the user's login shell (`getent passwd $USER` field 7 →
   `rpm -qf`). Sentence: "zsh is your login shell. Choose another shell first (see Terminal and
   shell)."
3. It removes the last installed terminal of `kitty`, `foot` and `alacritty` (the same list as
   `TERMINALS`, `arctic_settings.py:78`). Sentence: "kitty is your only terminal, so
   `Super + Enter` would stop working. Install another terminal first."

**Warnings** (not blocking)
- A package provides the entry or program for a default-app role. The role's key comes from
  `appslib.ROLE_KEYS`: browser `Super + B` (D7), terminal `Super + Enter`, editor `Super + E`,
  files `Super + F`.
  - A test checks `ROLE_KEYS` against `dotfiles/.config/mango/arctic/apps.conf`.
- `undo` is true when `/etc/snapper/configs/root` exists 🔍 (readable by users on F44?). The line
  "A snapshot is taken first" depends on it.

**Execution**
- `pkexec /usr/bin/dnf5 remove -y [--no-autoremove] PKG…`, with exactly the preview's arguments.
- Both commands load only the system repo, so the same rpmdb gives the same transaction.
- The sheet checks the `rpmdb` stamp before it queues the job (§3.7).
- `dnf5 replay` of the stored transaction would make "what you confirmed is what runs" exact. It is
  an option, not the plan; §14.

#### 6.8 Protected packages

**Where the list lives**
- The static list is `shell/scripts/protected-packages.conf`: one `fnmatch` pattern per line, with
  `#` comments. It is installed with the shell at
  `/usr/share/arctic/shell/scripts/protected-packages.conf`.
- Administrators can add patterns in `/etc/arctic/protected-packages.d/*.conf` (read if present;
  nothing ships there).
- Both files are read by `appslib.protection()`, which `apps.py` and `install-terminal.py` share.

**Initial static list**
- Families whose every member is system-critical are listed as globs. Everything else is an exact
  name.

```
# Arctic Linux itself and its session
arctic-*
mangowm
quickshell
sddm
sddm-wayland-mango
layer-shell-qt
# package management, boot and core system
dnf5
dnf5-plugins
libdnf5*
libdnf5-plugin-actions
rpm
rpm-libs
rpm-plugin-*
kernel
kernel-core
kernel-modules*
grub2-*
shim-*
dracut
glibc
glibc-*
systemd
systemd-*
sudo
shadow-utils
selinux-policy
selinux-policy-*
snapper
btrfs-progs
polkit
polkit-libs
# the desktop runtime (modules/_system/desktop-base/module.toml:15, every package; a test checks it)
xdg-desktop-portal-wlr
xdg-desktop-portal-gtk
slurp
grim
wl-clipboard
cliphist
pipewire
pipewire-pulseaudio
pipewire-alsa
wireplumber
NetworkManager
NetworkManager-wifi
network-manager-applet
xorg-x11-server-Xwayland
qt5-qtwayland
qt6-qtwayland
gnome-keyring
gnome-keyring-pam
xdg-user-dirs
xdg-utils
libnotify
brightnessctl
playerctl
tuned-ppd
mesa-dri-drivers
# what the shell and Get apps run on
python3
python3-libs
python3-pyte
python3-pillow
flatpak
flatpak-libs
nix
nix-daemon
```

**Computed set**
- It is cached per rpmdb mtime and used for **labels**:

```
dnf5 repoquery --installed --providers-of=requires --recursive --qf '%{name}\n' arctic-desktop
```

- This is the closure of hard requirements. `--providers-of=requires` with `--recursive` ✅ (dnf5
  `repoquery.8.rst`).
- 🔍 The output on F44 is pinned by WP-A0 against a local meta package.
- Apps in this closure are listed under "Part of Arctic Linux" as "The Arctic desktop needs
  Blueman." Today that covers pavucontrol, blueman, network-manager-applet, fuzzel, qt5ct and
  qt6ct.
- If the dropdown work (D5) ever turns them into weak dependencies, they become removable with no
  change here.

**Weak dependencies**
- Recommends of `arctic-desktop` (kitty, zsh, Thunar, vlc, btop, waybar, lxqt-policykit) stay
  removable, labelled "Came with Arctic Linux". The terminal and login-shell checks (§6.7) still
  apply.

**Enforcement points**
1. The Remove list shows protected rows only in the collapsed "Part of Arctic Linux" group, with no
   button.
2. `preview-remove` blocks any transaction that contains a protected name. Because `arctic-*` is
   protected, this alone stops any removal that would drag out `arctic-desktop`.
3. The runner refuses `run` remove jobs with a protected id.
4. The console refuses a typed `dnf remove|erase` with a protected bare name, and a typed dnf
   removal always asks `[y/N]` with the full list (§6.2).

**Not in 0.3.0: a dnf-level `/etc/dnf/protected.d/arctic.conf`**
- It would also block expert terminal use: for example `sudo dnf remove blueman` fails because it
  drags out `arctic-desktop`, and so does `dnf swap arctic-release fedora-release` for someone
  leaving Arctic.
- How protected packages interact with future Obsoletes-based renames is 🔍.
- Decision recorded in §14.

#### 6.9 Flatpak: user and system

**Installs**
- **In `wheel`** (the installer's account, `installer.go:1485`): `--system`. There's no password ✅
  (Flatpak's polkit rules), it matches the installer (`installer.go:1441`), and the system update
  timer from `unified-updates` covers it.
- **Not in `wheel`**: `--user`. There's no password and it installs only for that user. The Flathub
  remote is added to the user installation first, again with no password.
- `sources.install_to` holds the choice. The details sheet states it.
- There's no switch to choose. Anyone who needs the other installation uses the Console.

**Removals**
- `--system` or `--user` comes from the row's `installation` column. `flatpak uninstall` fails for a
  ref in both installations unless you pass one ✅ (research, `flatpak-uninstall.xml`).
- System uninstalls need no password for wheel users. Other users get Flatpak's polkit admin prompt
  in `PolkitDialog`.
- `--delete-data` is opt-in and off by default. It removes `~/.var/app/<id>` of **the calling user**.
  - 🔍 That this holds for a system-installation uninstall run by the user. Test by hand on F44.
- `--unused` runs after every Flatpak removal. Explicitly installed runtimes are pinned by Flatpak
  and survive 🔍 (Flatpak ≥ 1.9 auto-pinning, test on 1.18.2).

**Adding Flathub**
- Only when `sources.flatpak.flathub` has no remote for `install_to`.
- System: `remote-add --system` asks for a password once (`configure-remote`, `auth_admin_keep`) ✅
  (research). User: no password.

#### 6.10 Web apps: the engine contract used here

This section only consumes engine-design.md §5 and engine-verdict.json. The engine section owns
`arctic-webapp`.

- **Client**: `shell/WebAppClient.qml`.
  - It runs `Process { command: [AppsService.webappCmd, 'serve']; stdinEnabled: true; stdout:
    SplitParser {…} }`.
  - It keeps a `pending` map of request id → callback.
  - It emits `progress(request, stage, message)` and `changed(ids)`.
  - It tells events from replies by the `event` key.
- **Wire format**: snake_case throughout, and errors `{"id":n,"error":{"code","message","fields"}}`
  (verdict corrections 2-3). `message` is shown as it comes, as a sentence.
- **Methods used**: `Hello`, `Runtimes`, `Inspect`, `Cancel`, `Install`, `List`, `Get`, `Launch`,
  `Remove`, `Forget`. Params follow §5.2, for example
  `Remove{"ids":[…],"keep_data":true}` and `Install{"token":…,"name":…,"icon":0,"runtime":"webkit","links":"browser"}`.
- **Launcher Delete on a web app**: `apps.py owner` recognises it by the `org.arcticlinux.WebApp.`
  id prefix or the `X-Arctic-WebApp-Id` key. The sheet then calls `Get{id, sizes:true}` for the data
  size and `Remove{ids:[id], keep_data:!deleteData}`.
- **No CLI calls from the shell**: the shell uses `serve` only. `apps.py counts` is the one place
  that runs `arctic-webapp list --json`, and it reads the single `{"ok":true,…}` line (verdict
  correction 4: no progress lines in `--json` mode).
- **Launcher tiles**: web-app rows must skip `Icons.tileFor`. The check in `Launcher.qml:61` is on
  `e.id`, using the case-sensitive prefix `org.arcticlinux.WebApp.` (verdict correction 9). This
  edit is shared with the engine section; it also skips `org.arcticlinux.TerminalApp.` (§6.11).

#### 6.11 Terminal apps (gap `tui-launchers`)

**The launcher entry `apps.py terminal-app add` writes**

- Path: `$XDG_DATA_HOME/applications/org.arcticlinux.TerminalApp.<Float|Tile>.<Slug>.desktop`.
- The slug is the name's ASCII letters and digits in CamelCase, as the engine's `Slug` does.

```ini
[Desktop Entry]
Type=Application
Version=1.5
Name=Btop
Comment=Terminal app · btop
Exec=arctic-open terminal --app-id org.arcticlinux.TerminalApp.Float.Btop -e btop
Icon=btop
Terminal=false
Categories=System;X-Arctic-TerminalApp;
Keywords=terminal;tui;btop;
X-Arctic-TerminalApp-Id=org.arcticlinux.TerminalApp.Float.Btop
X-Arctic-TerminalApp-Command=btop
X-Arctic-TerminalApp-Window=float
```

- **Exec**:
  - Each command word is quoted per the Desktop Entry spec: arguments with reserved characters go
    in double quotes, with `"`, `` ` ``, `$` and `\` escaped, and `%` becomes `%%`.
  - `Terminal=false`, because `arctic-open` starts the terminal itself with the app id.
  - Newlines and control characters are refused.
- **Name**: control and bidi characters are stripped, and the name is at most 64 characters.
- **Icon**: with `--icon PNG`, Pillow (already a Requires of arctic-shell) resizes the picture to
  256×256. It is written to `$XDG_DATA_HOME/icons/hicolor/256x256/apps/<id>.png`, and `Icon=<id>`.
- **Existing id**: `{"ok":false,"code":"exists","error":"You already have a terminal app called Btop."}`
- **Command not on PATH**: `{"ok":false,"code":"missing","error":"btop isn't installed. Install it from Fedora packages first."}`

**`arctic-open --app-id`** (`dotfiles/.local/bin/arctic-open`)
- It accepts `--app-id ID` before `-e` for the `terminal` role. ID must match `^[A-Za-z0-9._-]+$`.
- It maps the ID to the chosen terminal's flag:

| Terminal | Flag |
|---|---|
| kitty | `--class ID` |
| foot | `--app-id ID` |
| alacritty | `--class ID` |
| others | none (the window just doesn't float) |

- 🔍 kitty `--class` and alacritty `--class` set the Wayland app_id. Test by hand under Mango.
- The usage text (`:4-7`, `:17-19`) is updated. So is the notification at `:85-86`, which becomes
  "Install one with Get apps (Super + Shift + A), or set $role= in ~/.config/arctic/default-apps."

**Mango rule** (`dotfiles/.config/mango/arctic/rules.conf`, "Dialogs and small tools float")

```
windowrule=isfloating:1,width:1000,height:640,appid:^org\.arcticlinux\.TerminalApp\.Float\.
```

- 🔍 The regex anchors in `appid:`. `%check` runs `mango -p` when mango is in the build root
  (spec:884-897); the web-app engine uses the same form.

**Removal**
- `apps.py terminal-app remove ID` deletes the `.desktop` file and any icon it copied. The
  program itself stays installed.

**Launcher tiles**
- `Launcher.qml:61` skips `Icons.tileFor` for `org.arcticlinux.TerminalApp.` ids (a TUI named
  "Settings monitor" would otherwise get the Settings tile).

#### 6.12 Owner resolution for Delete on a launcher row

`apps.py owner DESKTOP_ID`:

1. **Find the file.** Resolve the desktop id to its file in XDG order: `$XDG_DATA_HOME/applications`,
   then each `XDG_DATA_DIRS/applications`, so flatpak exports are found through `XDG_DATA_DIRS`.
   - Ids with `-` may be subdirectories, following the spec's rule (`a-b` → `a/b.desktop`), the
     same as `arctic_settings.desktop_entries` builds them (`:1767`).
   - The real path must stay inside that directory.
2. **Check, in this order.** This is Omarchy's order (web app, TUI, package owner, Flatpak ✅,
   gap-verification `launcher-uninstall-key`), with Flatpak moved before rpm because exported files
   are never rpm-owned:

| Order | Test | Source |
|---|---|---|
| 1 | The id starts with `org.arcticlinux.WebApp.`, or the file has `X-Arctic-WebApp-Id` | `webapp` |
| 2 | The file has `X-Arctic-TerminalApp-Id` | `terminal-app` |
| 3 | The path is under a flatpak `exports/share/applications`, or the file has `X-Flatpak=` | `flatpak` (the installation comes from the path) |
| 4 | The path is under a system data dir and `rpm -qf` finds an owner | `dnf` (protection checked here too) |
| 5 | The path is under `$XDG_DATA_HOME/applications` | `launcher`: deletes only that file; `overrides: true` when a system entry with the same id exists |
| 6 | The path is under `/nix/` | `nix` (message only; §3.7) |
| 7 | anything else | `unknown`: "Arctic Linux can't tell where X came from." (Close only) |

- `apps.py launcher-entry remove DESKTOP_ID` resolves the same way. It refuses anything that isn't
  step 5, then unlinks the file.

#### 6.13 Arctic picks: `shell/assets/featured.json`

The curated catalog isn't on installed systems: `arctic-installer` ships it and `LiveOnlyPackages`
removes it (`installer.go:39`). So the data is generated into the shell:

- **Generating it**: new `arctic-install catalog --featured` (in `cmd/arctic-install/main.go`,
  next to `cmdCatalog`, `:541-570`). It prints:

```json
{"schema":1,"apps":[
 {"id":"gimp","name":"GIMP","summary":"Photo editing and painting.","category":"graphics","tile":"gimp",
  "glyph":"brush","proprietary":false,
  "flatpak":{"remote":"flathub","ref":"org.gimp.GIMP","verified":true},
  "dnf":{"packages":["gimp"]}}]}
```

- **What is included**: visible modules only. Hidden, `always`, hardware and `_system` modules are
  left out.
  - `flatpak` only for `remote == "flathub"` with a `ref`.
  - `dnf` only when the method has no `copr`, `repos` or `swap`.
  - Modules with neither are skipped: COPR and Nix modules stay console-only.
  - Order: catalog order (`modules/catalog.toml`).
- **Freshness**: `internal/catalog/featured.go` builds it. `featured_test.go` compares it with the
  committed `shell/assets/featured.json` in the existing `go` CI job. It is regenerated with
  `go run ./cmd/arctic-install catalog --featured > shell/assets/featured.json`.
- **Offline and read at runtime**: it is read with a `FileView`. "Installed" comes from
  `installedIds`.

#### 6.14 Updates for apps installed here (`unified-updates`, Get-apps parts only)

- **dnf apps** update with the system through `arctic-update`, as today.
  - A Get apps install or removal after an update was staged invalidates the staged update, and
    `arctic-update` prepares it again two minutes later (`docs/wiki/Updates.md:40-43`). The job card
    says so (§3.3).
- **Flatpak apps**: the default is `--system` (§6.9), so the new system `arctic-flatpak-update.timer`
  owned by the updates section keeps them current.
  - That section must also cover `--user` installations, for non-wheel users.
  - Until it lands, the Flathub card makes no "updates itself" claim.
  - After it lands, the chooser's status line may say "Updated automatically".
- **Web apps** run on WebKitGTK (dnf) or a browser (dnf or Flatpak), which update through those
  channels. Refreshing metadata (`arctic-webapp update --all`) belongs to the engine section.
- **Terminal apps** run installed programs and have nothing to update.

---

### 7. File-by-file changes

#### 7.1 New files

| Path | Contents |
|---|---|
| `shell/AppsService.qml` | Singleton, §6.1. |
| `shell/WebAppClient.qml` | `arctic-webapp serve` client, §6.10. |
| `shell/getapps/qmldir` | `GetApps`, `ChooserPage`, `SourcePage`, `AppRow`, `DetailsSheet`, `JobCard`, `WebAppPage`, `TerminalAppPage`, `RemovePage`, `RemoveSheet`, `ConsolePage`, `Segmented`, `Sheet`. The files `import ".."` for Theme, Session and the other root types, following `settings/pages/qmldir` + `import ".."` (`settings/pages/AppsPage.qml:6-8`). |
| `shell/getapps/GetApps.qml` | Page router: `property string page`, `removeTab`, `query`; `open(target, query)`; `back()` (the Esc ladder); `inputItem`; `preferredWidth`/`preferredHeight` (640×430 for the chooser, 760×600 otherwise); `signal backRequested`. A `StackLayout` or a `Loader` per page. |
| `shell/getapps/GetApps.js` | Pure logic, tested with node: `cards(state)`, `parsePage(str)`, `backStep(state)`, `rowState(item, installedIds, jobs)`, `jobLabel(job)`, `repoLabel(repoid)`, `groupRemoveRows(rows)`, `sizeText(bytes)`. |
| `shell/getapps/ChooserPage.qml` | §3.1. |
| `shell/getapps/SourcePage.qml` | §3.2 and §3.3; `property string source: 'flatpak' | 'dnf'`. |
| `shell/getapps/AppRow.qml` | The result row used by the source and Remove pages. |
| `shell/getapps/DetailsSheet.qml` | §3.2 details. |
| `shell/getapps/JobCard.qml` | §3.10. |
| `shell/getapps/WebAppPage.qml` | §3.4. |
| `shell/getapps/TerminalAppPage.qml` | §3.5. |
| `shell/getapps/RemovePage.qml` | §3.6. |
| `shell/getapps/RemoveSheet.qml` | §3.7 (also used by `Launcher.qml`). |
| `shell/getapps/Segmented.qml` | Segmented control and tabs: `surfaceSunken` track, selected segment `accentSoft` + `accentEdge`, keyboard `Ctrl + Tab` / `Ctrl + Page Up/Down`. |
| `shell/getapps/Sheet.qml` | In-card modal base: a `Theme.scrim` rectangle that swallows clicks and a `surfaceRaised` panel; `Keys.onEscapePressed` closes it (accepted). |
| `shell/getapps/ConsolePage.qml` | `git mv shell/InstallConsole.qml`. Processes removed; binds to AppsService; title "Console"; Back → chooser. |
| `shell/scripts/appslib.py` | Shared library with no import side effects: `NAME`, `FLATPAK_ID`, `build_job`, `progress`, `explain`, `protection()`, `desktop_entries()`, `flathub_installations()`, `ROLE_KEYS`, `TERMINALS`, Desktop-Entry quoting. |
| `shell/scripts/apps.py` | CLI, §6.3. |
| `shell/scripts/protected-packages.conf` | §6.8. |
| `shell/assets/featured.json` | Generated, §6.13. |
| `internal/catalog/featured.go`, `internal/catalog/featured_test.go` | §6.13. |
| `design/icons/layers.svg` | New 24-grid line icon for "Fedora packages": `<path d="M12 4l8 4-8 4-8-4z M4 12l8 4 8-4 M4 16l8 4 8-4"/>`, stroke 1.75, round caps and joins, the same format as `design/icons/download.svg` (D9). The same body is added to `ICONS` in `shell/assets/design-data.js`, sorted alphabetically as `export-design-assets.cjs` writes it. The design project's `bundle.js` gets it too, so the next export keeps it (§14). |
| `shell/tests/test_apps.py` | §9. |
| `shell/tests/test-getapps.cjs` | §9. |
| `shell/tests/test-dnf5-remove.sh` | §9, WP-A0. |
| `shell/tests/fixtures/apps/…` | Captured command outputs, transaction.json, AppStream XML samples, desktop files. |
| `shell/dev/fixtures/bin/{flatpak,rpm,dnf5,arctic-webapp}` and `shell/dev/fixtures/apps/…` | Fake commands and data for headless screenshots (dev only; not packaged, spec `:710`). |

#### 7.2 Changed files (shell)

| File:lines | Change |
|---|---|
| `shell/Launcher.qml:10-14` | Header comment: Get apps pages, Remove apps, Delete. |
| `:18` | `view` comment: `get` = Get apps (see `getapps/GetApps.qml`). Add `property string getPage: 'choose'`, `property string getQuery: ''`. |
| `:24-26` | `focusItem: view === 'get' ? getApps.inputItem : removeSheet.open ? removeSheet.focusItem : field`. The card size comes from `getApps.preferredWidth/Height` in `get`. |
| `:28-34` | `openView(name, page, query)`: for `get`, `getApps.open(page || 'choose', query || '')`. |
| `:35-39` | `setQuery` unchanged. |
| `:44` | `onOpened: openView(view === 'get' ? 'get' : 'home', getPage, getQuery)` |
| `:47-56` | Specials: new `desc` for `get` (§5); add `remove` (not live). |
| `:57-61` | Tile skip for `org.arcticlinux.WebApp.` and `org.arcticlinux.TerminalApp.` (shared with the engine section). |
| `:62-75` | Append the `get-search` row when a search has no app results (§5). |
| `:83-106` | `activate`: `case 'remove': openView('get','remove')`; `case 'get-search': openView('get','flatpak',parsed.text)`. |
| `:107-111` | Add `function askRemove(entryOrId)`: opens `removeSheet` (not live). |
| `:131-137` | Replace `InstallConsole {…}` with `GetApps { id: getApps; visible: launcher.view === 'get'; …; onBackRequested: launcher.openView('home') }`. |
| `:163-181` | In the field: `Keys.onDeletePressed` (`Shift` or cursor at end → `askRemove`, `event.accepted = true`; otherwise not accepted). |
| `:213-266` | Row delegate: hover or selected ghost `trash` button for `kind === 'app'` (not live); right-click → `askRemove`. |
| `:281-302` | Footer `Hint { label: 'remove'; keys: [Kbd { text: 'Delete' }] }`, visible for an app result and not live. |
| end of card | `RemoveSheet { id: removeSheet; anchors.fill: parent }` over the card. |
| new | `Binding { target: AppsService; property: 'watching'; value: launcher.open && launcher.view === 'get' }` |
| `shell/shell.qml:7-15` | Header comment; IPC list. |
| `:34-37` | `openGetApps(screen, page, query)`; new `uninstallEntry(screen, desktopId)`. |
| `:95-99` | IPC `apps`, §5. |
| `shell/qmldir` | Add `singleton AppsService 1.0 AppsService.qml` and `WebAppClient 1.0 WebAppClient.qml`; remove `InstallConsole 1.0 InstallConsole.qml` (`:19`). |
| `shell/AppTile.qml:9-16,31-40` | Add `property string imageSource: ''` (an absolute path or `file://` URL). `readonly property string picture: imageSource !== '' ? (imageSource.startsWith('/') ? 'file://' + imageSource : imageSource) : themedIcon`. The `Image` uses `picture`, and the glyph shows when `picture === '' || image.status === Image.Error`. `themedIcon` is unchanged. |
| `shell/PolkitDialog.qml:9-18` | Add `readonly property bool active: agent.isActive` on the root `Scope`; `shell.qml:81` gives it `id: polkit` and sets `AppsService.polkit = polkit`, or AppsService binds through a property set there. |
| `shell/PackageSearch.js` | Add `prepareItems`/`searchItems` (§6.4); update the header comment. |
| `shell/scripts/install-terminal.py` | §6.2. Docstring `:1-23` (the `run` action, removals confirm); `build_command` `:64-100` (no `-y` for remove/uninstall, protected refusal); `WELCOME` `:58-61`; `Console.start` takes a list of commands; `emit` `:156-160` (job/finished/transcript); `read` `:235-269` (exit code into `finished`, progress); `main` `:272-314` (`run`, `transcript`, EOF drain). |
| `shell/scripts/package-index.py` | §6.4. Docstring `:1-14`; `:24-27` new cache names; `:51-56` TSV parsing; `:59-73` new queries; `:76-78` `--details`; `:84-98` `--force`. |
| `shell/README.md:4,32,41,42,78` | Rewrite the Get apps row (files, pages, protection); the IPC table; fix the "sudo dnf" wording (§11). |

#### 7.3 Changed files (outside shell/)

| File:lines | Change |
|---|---|
| `settings/pages/AppsPage.qml:62-68` | Before the footnote, a `SettingRow { searchKey: "apps.software"; label: "Install and remove apps" }` with two `ArButton`s: **Get apps** (`["arctic-shell-ipc","apps","install"]`) and **Remove apps** (`["arctic-shell-ipc","apps","remove"]`, hidden on the live USB). Footnote: "Apps you install with Get apps (Super + Shift + A) show up here." The button at `:51-57` stays. |
| `settings/SearchIndex.js:82-86` | Add `["apps", "apps.software", "Install and remove apps", "get apps remove uninstall software flatpak flathub dnf fedora web app terminal"]`. `settings/tests/test_app_files.py:45-` checks that the key exists. |
| `dotfiles/.local/bin/arctic-open` | `--app-id` (§6.11); message at `:85-86`. |
| `dotfiles/.config/mango/arctic/rules.conf` | The TerminalApp float rule (§6.11). |
| `dotfiles/.local/bin/arctic-shell-ipc:6` | `apps install|remove|open <page>|search <page> <text>|uninstall <desktop-id>`. |
| `dotfiles/.local/share/arctic/keys.txt:11` | `Super + Shift + A        Get apps (install or remove apps)` (shared with the shortcuts section's edits to the same file). |
| `dotfiles/.local/bin/arctic-launcher:3`, `dotfiles/.local/bin/arctic-shell:2` | Comments: "Get apps" instead of "Get apps console". |
| `cmd/arctic-install/main.go:541-570` | `catalog --featured` (§6.13). |
| `packaging/arctic-linux.spec` | §8. |
| `packaging/polkit/org.arcticlinux.pkexec.dnf.policy:4-6` | Comment: "Arctic Linux: Get apps (the shell's app installer, its Remove apps page and its console) runs `pkexec /usr/bin/dnf5 install|remove …`." No functional change (D2). |
| `.github/workflows/ci.yml` | New job `dnf5-remove` (§9). `shell-tests` needs no change (unittest discovery and the `*.cjs` loop pick up the new tests), except that `python3-rpm` is already installed. |
| `shell/dev/screenshots.sh:4-6,9-11,21-22`, `shell/dev/headless.sh` | §10. |
| `tools/lib/tour.py:50,575,681-696,753-786,809-812`, `tools/screenshot-tour.sh:31-36,138-150` | §10. |
| Docs | §11. |

#### 7.4 Icons (D9)

- Only one new glyph is needed: `layers`, for Fedora packages. Flathub has its design tile, and the
  existing `package` glyph is the Flathub tile's own.
- Everything else reuses existing glyphs:
  - `globe`, `prompt`, `trash` and `terminal`;
  - `check-circle`, `shield-check`, `lock`, `alert`, `x-circle`, `clock`;
  - `refresh`, `search`, `chevron-left`, `info`.
- The new glyph is drawn on the 24 grid with a 1.75 stroke and round caps and joins
  (`design/brand-book.md:102`).

---

### 8. Packaging deltas (`packaging/arctic-linux.spec`)

| Where | Change |
|---|---|
| `:36` | `Version: 0.3.0` when the work lands (D1; the release work package owns this line). |
| `%package -n arctic-shell` (`:240-252`) | Keep `Requires: python3-pyte` and `polkit`; change the comment `:250` to "pkexec, for Get apps (install and remove)". Add `Recommends: appstream-data` (Fedora app names, summaries and icons for the Fedora packages page) and `Recommends: arctic-webapps = %{version}-%{release}` (the web-app engine; x86_64, recommended from a noarch package, which RPM allows). |
| `%description -n arctic-shell` (`:254-257`) | "…launcher with Get apps (Flathub, Fedora packages, web apps, terminal apps, a console) and Remove apps, wallpaper picker…" |
| `%install` (`:707-731`) | No change: everything new is inside `shell/` (the tarball at `:710`) and excludes `tests/` and `dev/`. The comment at `:729` becomes "Get apps: pkexec dnf5 (install and remove) with the password kept for a few minutes." |
| `%check` (after `:824`) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s shell/tests -p 'test_apps.py'`. It uses only the standard library (it needs `tomllib`, Python ≥ 3.11 on F44). It checks the packaged helper's contracts and that `protected-packages.conf` covers `modules/_system/desktop-base`. |
| `%files -n arctic-shell` (`:1124-1130`) | No change. |
| `iso/kiwi/config.kiwi` | Nothing explicit. `appstream-data` (15.7 MB package, 15.1 MB installed ✅ mdapi 44-4.fc44) and `arctic-webapps` come in through `patternType="plusRecommended"` (`:58`). 🔍 ISO size against the 2 GiB budget with `tools/build-iso.sh --zen auto`. If it overflows, drop the `appstream-data` Recommends; the Fedora page then offers to install it (§3.3). 🔍 Which F44 repository carries appstream-data (mdapi's repo labels disagree). |
| `modules/_system/codecs/module.toml` (optional) | Add `rpmfusion-free-appstream-data`, `rpmfusion-nonfree-appstream-data` 🔍 (the names in RPM Fusion for F44), so RPM Fusion apps have names and icons too. |

The packaging stays within D2: no new polkit action, no sudo, and `exec.path` stays `/usr/bin/dnf5`.

---

### 9. Tests

#### 9.1 Python, `shell/tests` (run by the existing `shell-tests` job)

**`test_install_terminal.py`**

- **`CommandTests`**
  - `test_dnf_changes_need_pkexec_and_queries_do_not` changes: `sudo dnf remove fish` →
    `['pkexec','/usr/bin/dnf5','remove','fish']`, with no `-y`.
  - New: `flatpak uninstall org.gimp.GIMP` → `['flatpak','uninstall','org.gimp.GIMP']`, with no `-y`.
  - New: `dnf remove arctic-shell`, `dnf erase mangowm` and `dnf remove kernel-core` raise the
    protected sentence.
  - Install lines still get `-y`.
- **New `JobTests`**
  - Exact argv for every row of the §6.2 table (dnf install; flatpak install system and user, with
    the remote-add prefix for user; dnf remove with and without autoremove; flatpak remove with
    `--delete-data` and `--unused`; add-remote system and user).
  - Refusals: bad dnf names; bad Flatpak ids (`org.gimp`, `../x`, `a b`); unknown `installation`
    or `remote`; a protected id in a remove job; more than 50 ids.
- **New `RunTests`**
  - Setup: a fake `flatpak` on `PATH` (`test_helpers.fake_command`); `appslib.PKEXEC_DNF` patched to
    a fake `pkexec` + fake `dnf5`.
  - `{"action":"run"}` produces `job` lines with `percent` from a captured flatpak fixture, then
    `finished.code == 0`.
  - A failing fake gives `finished.ok == false` with the §6.2 sentence.
  - A second `run` while one runs is refused (the queue lives in QML).
  - `transcript` on/off controls whether `output` is present.
  - Stdin closed during a job: the process waits for the job, then exits 0 (the EOF drain).
- **New `ProgressTests` / `ExplainTests`** on captured dnf5 and flatpak PTY fixtures, and on pkexec
  exit codes 126 and 127.
- The existing `TerminalTests` and `FlatpakThemeHookTests` stay unchanged. Add one case:
  `after_flatpak_install(['flatpak','install','--system','-y','--noninteractive','flathub','dev.zed.Zed'])`
  starts the hook.

**`test_helpers.py` `PackageIndexTests`** (`:44-96`)

- The fake `dnf5` prints `name\trepo\tsummary with spaces` lines, with multi-arch duplicates.
- The fake `flatpak` answers `remotes` and `remote-ls` with names and descriptions.
- Assertions:
  - `packages` is unchanged;
  - `--details` gives the dedicated arrays;
  - summaries with spaces are kept;
  - an old `packages.txt`/`flathub.txt` without TSV is still read;
  - `--force` refreshes a fresh cache;
  - `remote-ls` gets `--system` when the system installation has flathub;
  - a Flatpak failure with the remote present gives its sentence.

**New `test_apps.py`**

- **Setup**: temp `HOME`, `XDG_*` and `XDG_DATA_DIRS` pointing at fixture trees; fake `flatpak`,
  `rpm`, `dnf5`, `getent` and `arctic-webapp` on `PATH`; `ARCTIC_INSTALL_MARK` for the
  `/var/log/arctic-install` stamp in tests.
- **Contract**: every command prints one line; `ok` on success; `{ok:false,error,code}` with exit 1
  on failure; nothing else on stdout.
- **`sources`**: wheel or not → `install_to`; flathub in system, user, both or none; the web engine
  present or absent.
- **`catalog`**:
  - Fedora parsing of a trimmed real `fedora.xml.gz` sample (captured in WP-A0) and a Flathub
    `appstream.xml.gz` sample: names without `xml:lang`, icon paths, verified flag, categories.
  - Cache hit and miss by mtime.
  - Missing files → `missing: true`.
  - `--appstream FILE --tsv` output.
- **`installed flatpak`**: TSV parsing; the same id in both installations → two rows; name and icon
  from the exported desktop file.
- **`installed dnf`**:
  - desktop → package grouping with the `rpm -qf` fixture, including unowned and multi-owner paths;
  - NoDisplay-only packages dropped;
  - Terminal apps kept;
  - `added` from reason plus install time;
  - protected rows grouped separately with reasons (static, closure, login shell);
  - `roles` from both default-apps files;
  - `--other`.
  - A parity test: `appslib.desktop_entries` and `arctic_settings.desktop_entries` give the same ids
    on the fixture tree.
- **`preview-remove dnf`**:
  - `transaction.json` fixtures from WP-A0 → `asked`/`needs-it`/`unused`;
  - `frees_bytes`;
  - `--no-autoremove`;
  - `blocked` for arctic-desktop as a dependent, the login shell and the only terminal;
  - default-app warnings;
  - the fallback `--assumeno` text parser on the captured text, when kept.
- **`owner`**: one fixture per source in §6.12, including a user override of a system entry and a
  path escape attempt (a symlink out of the directory).
- **`terminal-app add/remove`**: the exact `.desktop` text; Exec quoting (spaces, `"`, `$`, `%`);
  refusals (`/` in the name, newline in the command, command not on `PATH`, existing id); the icon
  resized to 256 when given.
- **Protection**:
  - every package in `modules/_system/desktop-base/module.toml` (read with `tomllib`) matches
    `protected-packages.conf`;
  - `/etc/arctic/protected-packages.d` extension (through an env override in the test);
  - kitty, zsh, Thunar, vlc and btop are **not** statically protected.
- **`ROLE_KEYS`** matches `dotfiles/.config/mango/arctic/apps.conf`, so it breaks loudly if D7's
  Super+B change lands without it.

#### 9.2 Node, `shell/tests`

- **`test-package-search.cjs`**:
  - add `prepareItems`/`searchItems` cases: display names beat ids ("gimp" finds GIMP before
    `gimp-help`), summary matches only when strong matches are few, keyword matches, the limit, and
    a 70k synthetic index answering in < 50 ms;
  - the existing string assertions stay unchanged.
- **New `test-getapps.cjs`**:
  - `cards()` for live, no engine, and no Flathub;
  - `parsePage()` for `remove/dnf`, unknown strings and empty;
  - `backStep()` over every combination (sheet open, field text, page);
  - `rowState()` for installed, waiting, running and failed;
  - `jobLabel()`, `repoLabel()`, `sizeText()`.

#### 9.3 Go

- `internal/catalog/featured_test.go`: `Featured(cat)` equals `shell/assets/featured.json`, and it
  excludes hidden, `always`, hardware, COPR-only and Nix-only modules.
  - Runs in the existing `go` job (`CGO_ENABLED=0`, standard library only).

#### 9.4 Real dnf5 harness (WP-A0): `shell/tests/test-dnf5-remove.sh` + CI job `dnf5-remove`

Modelled on `packaging/updates/test-dnf5-offline.sh` and the `dnf5-offline` job (`ci.yml:116-127`).

- **Container setup**: in `registry.fedoraproject.org/fedora:44`, install
  `dnf5-plugins rpm-build createrepo_c python3 util-linux`.
- **Test packages**: build tiny noarch RPMs:
  - `t-app` (a `.desktop` file) requires `t-lib`;
  - `t-meta` requires `t-tool` (stands in for `arctic-desktop` → `blueman`);
  - `t-leaf` recommends nothing.
  Install them from a local repo, then add a normal user.
- **Pin, as the user**, each of these:
  1. `dnf5 remove --store=DIR -y t-app` exits 0 and writes `transaction.json`. Record the `action`
     and `reason` fields for asked, dependent and unused packages. If it fails, the harness records
     that and the `--assumeno` parser becomes the implementation.
  2. The `LC_ALL=C dnf5 remove --assumeno t-app` sections and "Operation aborted by the user."
     (exit 1).
  3. `dnf5 remove --store=DIR -y t-tool` includes `t-meta` → `apps.py preview-remove dnf t-tool`
     returns `blocked`, with `protected-packages.conf` overridden to `t-meta`.
  4. `--no-autoremove` keeps `t-lib`.
  5. `dnf5 repoquery --installed --providers-of=requires --recursive --qf '%{name}\n' t-meta`
     includes `t-tool`.
  6. The `dnf5 repoquery --installed --qf '%{name}\t%{reason}\t%{from_repo}\t%{installtime}\t…'` fields.
  7. The `rpm -qf --qf '[%{FILENAMES}\t%{=NAME}\n]'` owner mapping.
- **Then as root**: `dnf5 remove -y t-app` removes exactly what the stored preview listed.
- The harness copies its captured outputs into the job log, and into `shell/tests/fixtures/apps/`
  when run locally with `--update-fixtures`.

#### 9.5 QML and headless

- The `qml` job lints `shell/getapps/*.qml` automatically; its `find` is recursive (`ci.yml:142`).
- Headless screenshots (§10) are the smoke test for the page router, focus and Esc. They cover:
  - `ipc apps install` → chooser;
  - `ipc apps search flatpak gimp`;
  - `ipc apps open remove`;
  - `ipc apps open console`.

#### 9.6 Manual matrix (Fedora 44 VM under Mango, before merging, D10)

Every 🔍 in this section is a line in the matrix, plus the flows below:

- **Installs**:
  - install GIMP from Flathub with no password;
  - install `htop` from Fedora with the password dialog, then "Open";
  - add Flathub on a system without it.
- **Removals**:
  - remove a Flatpak with and without data;
  - remove a dnf app with dependents;
  - try to remove Blueman (blocked);
  - remove the only terminal (blocked);
  - remove Firefox when it is the browser (warning).
- **Other sources**:
  - add a web app, open it, remove it keeping data, then forget the data;
  - add btop as a floating terminal app, open it, remove it.
- **Launcher Delete** on each source.
- **Esc** at every level.
- **Robustness**:
  - close the launcher mid-install and get the notification;
  - restart the shell (`arctic-shell` restart) during a dnf install; the transaction completes.
- **Console**:
  - `dnf remove fish` asks `[y/N]` with the list;
  - `dnf remove arctic-shell` is refused.
- **Live USB**: no Remove apps anywhere.

---

### 10. Screenshots and the tour

**`shell/dev/headless.sh`**
- New option `--app-fixtures`: `PATH="$REPO/shell/dev/fixtures/bin:$PATH"`,
  `XDG_DATA_DIRS="$REPO/shell/dev/fixtures/apps/share:/usr/local/share:/usr/share"` and
  `ARCTIC_WEBAPP_CMD=$REPO/shell/dev/fixtures/bin/arctic-webapp`.
- The fake commands serve canned F44-like data: 300 packages, 40 Flathub apps with icons, installed
  lists, a transaction.json, and a web app `Inspect` result.
- Nothing from the developer's own system appears in the screenshots.

**`shell/dev/screenshots.sh`**
- Comments `:4-6` and the `ARCTIC_PACKAGES` seeding `:9-11` stay, as an optional real index.
- `:21-22` becomes:

```
  sh "$copy_packages" ipc apps install sleep 1.5 shot get-apps \
  ipc apps search flatpak gimp sleep 1.5 shot get-apps-flathub \
  ipc apps search dnf neovim sleep 1.5 shot get-apps-fedora \
  ipc apps open web sleep 1 sh "wtype -s 300 music.youtube.com" sleep 2 shot get-apps-web \
  ipc apps open terminal sleep 1 shot get-apps-terminal \
  ipc apps open remove sleep 1.5 shot remove-apps \
  ipc apps open console sleep 1 sh "wtype -s 300 neovim" sleep 1 shot get-apps-console ipc launcher close \
```

- The first `"$H"` call gains `--app-fixtures`.
- The Winter run adds `ipc apps open remove sleep 1.5 shot remove-apps-winter ipc launcher close`.
- The live run adds `ipc apps install sleep 1 shot get-apps-live`: the chooser without Remove apps,
  with the live note.

**`tools/lib/tour.py`** (live phase in a VM without internet)

- **`popup()`** (`:753-786`) accepts `chord=None`, which means opening over IPC only. That skips the
  shortcut attempt.
- **`get_apps()`** (`:809-812`) becomes the chooser shot, with no typing:
  `self.popup("get-apps", "meta_l-shift-a", "Get apps", "apps install", "apps toggle", ready=chooser_drawn)`.
  `chooser_drawn` checks `busy(p, (320, 90, 960, 520)) > 20` 🔍 (the region on the first run).
- **New `get_apps_flathub()`**:
  `self.popup("get-apps-flathub", None, "Flathub apps", "apps open flatpak", "apps toggle", field=(640, 128), typed=E.get("GETAPPS_QUERY", "gimp"), check=(260, 140, 1020, 630))`.
  The search field sits under the header of the 760-wide card 🔍 (y on the first run).
- **New `get_apps_console()`**: the old console shot, with `ipc_open` `apps open console`,
  `field=(640, 604)`, typing `neovim`.
- **`LIVE_STEPS`** (`:50`) and the step list (`:575`): `"get-apps", "get-apps-flathub",
  "get-apps-console"`. Remove apps is hidden on the live USB, so there's no live shot of it.
- **`INSTALLED_STEPS`** gains `"remove-apps"` (IPC `apps open remove` after login) 🔍. That the
  installed phase has the agent to run IPC; otherwise it's left to headless.
- **`prepare_session()`** (`:681-696`) also seeds `packages.tsv` and `flathub.tsv` when present.

**`tools/screenshot-tour.sh:138-150`** (host side)
- dnf: `--qf '%{name}\t%{repoid}\t%{summary}\n'` → `packages.tsv`, keeping `packages.txt` too for old
  shells.
- Flathub: download `https://dl.flathub.org/repo/appstream/x86_64/appstream.xml.gz` (about 10.5 MB ✅
  research), then run `python3 shell/scripts/apps.py catalog flathub --appstream FILE --tsv >
  flathub.tsv`. The VM gets names and summaries, but no icons.

**Docs images**
- `docs/wiki/images/get-apps.png` is replaced by the chooser.
- New images: `get-apps-flathub.png`, `get-apps-web.png` and `remove-apps.png` (from headless when
  the tour can't make them).

---

### 11. Docs to update

| File:lines | Change |
|---|---|
| `docs/wiki/Apps-and-Software.md:3-5` | "…The quickest way is **Get apps** (`Super + Shift + A`), which also removes apps." |
| `:314-346` | Rewrite `## Get apps` (keeps its anchor for the existing links): the chooser and each card; Flathub apps (no password, installs for everyone, verified badge, Arctic picks); Fedora packages (Apps / All packages, password once, `appstream-data`); Web apps (link to the engine's wiki page); Terminal apps; Console (what it accepts, removals ask first, protected names refused); jobs keep running when you close the launcher. Screenshot `get-apps.png`. |
| new `## Remove apps` after it | Tabs; data checkbox (off by default); dnf preview with dependents and "no longer needed"; what can't be removed and why (Part of Arctic Linux, login shell, only terminal); `Delete` on a launcher row; `/etc/arctic/protected-packages.d/` for administrators; undo through snapshots (link to Updates). Screenshot `remove-apps.png`. |
| `:348-360` dnf, `:360-380` Flatpak | Keep the terminal commands; add "or use Remove apps". |
| `:405-416` Updates | Flatpak paragraph per `unified-updates` (owned by that section; mention Get apps installs system-wide). |
| `docs/wiki/Keyboard-Shortcuts.md:23` | "Get apps: install or remove apps (Flathub, Fedora, web apps)". |
| `:100-109` In the launcher | Add `Shift + Delete` / `Delete` → "Remove the selected app". |
| `:111-117` In Get apps | Replace with the §4 table (chooser digits, Enter/Shift+Enter, `Ctrl + Tab`, `Ctrl + Page Up/Down`, Delete, Esc ladder; Console keys). |
| `docs/wiki/Desktop-Tour.md:84` | "**Get apps**: install and remove apps (see below)"; add "**Remove apps**". |
| `:108-115` | Rewrite for the chooser; new screenshot. |
| `docs/wiki/FAQ.md:119-126` | "How do I install an app?" → the chooser; new "### How do I remove an app?" (Remove apps, or `Delete` on its launcher row; why some can't be removed). |
| `docs/wiki/Settings.md:205` | Mention the new "Install and remove apps" row. |
| `docs/wiki/Try-Arctic-Linux.md:55` | "…with **Get apps → Flathub apps**; it's gone when you restart." |
| `docs/wiki/Home.md:36`, `docs/wiki/Architecture.md:15,206`, `README.md:9` | "Get apps console" → "Get apps (install and remove apps)". |
| `docs/wiki/Contributing.md:43,64` | Add `python3 -m unittest shell/tests/test_apps.py`, `node shell/tests/test-getapps.cjs`, `shell/tests/test-dnf5-remove.sh` (container). |
| `docs/wiki/Updates.md:40-43` | "…(with `dnf`, Get apps or Remove apps)…". |
| `docs/wiki/Release-Notes.md` (0.3.0) | Get apps chooser, sources, Remove apps, Delete in the launcher, web apps and terminal apps, typed removals now ask first, protected packages. |
| `docs/BUILD-SPEC.md:20` | "get-apps console" → "Get apps and Remove apps". |
| `:70` | arctic-shell row: Requires unchanged; add "Recommends appstream-data, arctic-webapps". |
| `:101-104` | IPC list: `apps install|remove|open <page>|search <page> <text>|uninstall <desktop-id>` (Get apps). |
| `:214` | Settings calls `arctic-shell-ipc apps install|remove`. |
| `:285` | The SplitParser example: `shell/AppsService.qml` (was `shell/InstallConsole.qml`). |
| `shell/README.md:4,32` | "the launcher with Get apps and Remove apps". |
| `:41` | Launcher row: Delete removes an app; Remove apps special. |
| `:42` | Rewrite the Get apps row: files (`AppsService.qml`, `getapps/`, `scripts/apps.py`, `appslib.py`, `install-terminal.py`, `package-index.py`, `protected-packages.conf`, `assets/featured.json`); pkexec + `-y` for GUI jobs, typed removals confirm; no "sudo". |
| `:78` | IPC table row for `apps`. |
| `dotfiles/README.md:10,82` | "`arctic-shell-ipc apps install|remove`: Get apps: install or remove apps (`Super + Shift + A`)". |
| `design/brand-book.md` (Iconography, optional) | No text change; `design/icons/layers.svg` added. |

---

### 12. Work packages and order

| WP | Name | Owns | Depends on | Effort |
|---|---|---|---|---|
| A0 | dnf5 remove harness | `shell/tests/test-dnf5-remove.sh`, `shell/tests/fixtures/apps/dnf5-*` | none | S |
| A1 | apps helper and protection | `shell/scripts/apps.py`, `shell/scripts/appslib.py`, `shell/scripts/protected-packages.conf`, `shell/tests/test_apps.py`, `shell/tests/fixtures/apps/*` (except dnf5) | A0 (fixtures; can start in parallel with placeholders) | L |
| A2 | Job runner | `shell/scripts/install-terminal.py`, `shell/tests/test_install_terminal.py` | A1 (`appslib.build_job`, `protection`) | M |
| A3 | Index and search | `shell/scripts/package-index.py`, `shell/PackageSearch.js`, `shell/tests/test_helpers.py` (PackageIndexTests), `shell/tests/test-package-search.cjs` | none | S |
| A4 | Service, router, chooser, console | `shell/AppsService.qml`, `shell/getapps/{qmldir,GetApps.qml,GetApps.js,ChooserPage.qml,ConsolePage.qml,Segmented.qml,Sheet.qml,JobCard.qml}`, `shell/tests/test-getapps.cjs`, `shell/AppTile.qml`, `design/icons/layers.svg` | A2, A3 | M |
| A5 | Source pages and picks | `shell/getapps/{SourcePage,AppRow,DetailsSheet}.qml`, `shell/assets/featured.json`, `internal/catalog/featured{,_test}.go` | A4, A1 | M |
| A6 | Remove apps and launcher Delete | `shell/getapps/{RemovePage,RemoveSheet}.qml` | A4, A1, A2, the engine's `serve` | M |
| A7 | Web apps page | `shell/WebAppClient.qml`, `shell/getapps/WebAppPage.qml`, `shell/dev/fixtures/bin/arctic-webapp` | A4; the engine section's `arctic-webapp serve` | M |
| A8 | Terminal apps | `shell/getapps/TerminalAppPage.qml` | A1 (`terminal-app`), A4 | S |
| A9 | Packaging, Settings, docs, screenshots, tour | `shell/dev/fixtures/*` (except A7's), docs listed in §11 that no other section owns | all | M |

Shared-file edits (other sections touch the same files) are listed per work package in the
structured summary. The main ones:

- `shell/Launcher.qml`: A4, A6 and A5's fallback row.
- `shell/shell.qml`: A4.
- `shell/qmldir`: A4.
- `PolkitDialog.qml`: A4.
- `arctic-open` and `rules.conf`: A8.
- `packaging/arctic-linux.spec`, `ci.yml`, `keys.txt`, `arctic-shell-ipc`, the Settings page and
  search index, the wiki: A9.

---

### 13. Interfaces with other sections

| Section | What this section needs or gives |
|---|---|
| Web-app engine (D4) | **Needs** `arctic-webapp serve` with the §5.2 methods and snake_case fields, the `org.arcticlinux.WebApp.` id prefix and `X-Arctic-WebApp-Id`, `list --json` one-line output, and the `arctic-webapps` package. **Shares** the `Launcher.qml:61` tile skip (one edit covering WebApp and TerminalApp). |
| Shortcuts (D7) | `ROLE_KEYS` uses `Super + B` for the browser; `test_apps.py` reads `apps.conf`, so both must land together. No new global keys here. `keys.txt:11` wording is edited here and the rest of the file there. |
| Notifications (D6) | Job notifications use `notify-send -A`; the shell NotificationServer must show actions and report the chosen one. |
| Command menu (P1) | Install and Remove branches call `openGetApps(screen, page)` or IPC `apps open …`; `apps.py counts` feeds its `when` guards. |
| Unified updates (P1) | Its Flatpak timer must cover system and user installations; the chooser mentions automatic updates only after it lands. |
| Power menu extras (P2) | Reads `AppsService.busy` / `currentLabel` instead of the old `InstallConsole` state. |
| Launcher search modes (P2) | Its web-search fallback row goes after this section's "Find “x” in Get apps" row. |
| First-login welcome (P1), OCR capture (P1) | Use `apps install` and `apps search dnf <pkg>`. |
| Bar dropdowns (D5) | pavucontrol, blueman and nm-applet stay hard Requires; they show as "Part of Arctic Linux" through the computed closure, with no static entry for them (the static list names `network-manager-applet` only because desktop-base lists it). |
| Release (D1, D10) | Version 0.3.0 and the PR; this section's CI job `dnf5-remove` must be green. |

---

### 14. Open issues and unverified points

**Open decisions** (each has a recommended answer)

1. **dnf-level protection.** Ship `/etc/dnf/protected.d/arctic.conf`? *Recommendation: not in
   0.3.0.*
   - It blocks expert removals from a terminal and `dnf swap arctic-release fedora-release`.
   - How it interacts with future Obsoletes-based renames is 🔍.
   - GUI, runner and console enforcement (§6.8) covers D3. Revisit if users break their desktop
     with `sudo dnf remove`.
2. **Executing a remove.** Replay the confirmed transaction (`pkexec /usr/bin/dnf5 replay -y DIR`,
   which errors on any difference ✅ dnf5 `replay.8.rst`) instead of `remove -y`? *Recommendation:
   `remove -y` plus the rpmdb stamp check for 0.3.0.*
   - Replay needs root's dnf5 (rpm_t) to read a stored transaction in `/run/user/<uid>`.
   - 🔍 SELinux on F44 allows that. It can't be tested in the CI container; test on a VM.
3. **Nix as a source.** *Deferred.*
   - The installer puts Nix apps in root's `/nix/var/nix/profiles/default`
     (`installer.go:1453-1455`), so removing them needs root and a new polkit action or helper,
     which D2 rules out ("privileges unchanged").
   - The remove sheet shows the terminal command, and the Console doesn't take `nix`.
4. **Online Flathub API** (verified badges, install counts, search). *Not used.*
   - Typed queries would leave the machine.
   - Local AppStream carries names, summaries, icons and (🔍) the verified flag.
5. **appstream-data on the ISO or on demand.** Decided by the 🔍 ISO measurement (§8).
6. **"You added it" label.** It relies on `installtime` vs `/var/log/arctic-install`.
   - Apps `arctic-firstboot` installs after the first boot (deferred installer apps) show as "You
     added it".
   - It is a label only. An installer marker listing its packages would fix it; that's out of scope
     here.
7. **Installer copy.** The installer and `internal/backend/progress.go:249` still say "the Software
   app" (`installer-ui/steps/{InstallStep,DoneStep,AttentionView}.qml`, `installer-ui/dev/mock-bridge.py:826`).
   - *Recommendation*: rename to "Get apps (Super + Shift + A)" in 0.3.0, then drop the FAQ entry at
     `docs/wiki/FAQ.md:124-126`. That needs the installer owner's agreement.
8. **The waybar fallback session** (`ARCTIC_SHELL=waybar`) has no Get apps: `arctic-shell-ipc` fails
   and `Super + Shift + A` does nothing. This is unchanged from 0.2.1.
9. **`design-data.js` is exported from an external design bundle** (`shell/dev/export-design-assets.cjs:9-10`).
   - The `layers` glyph must also go into that bundle, or the next export drops it.
   - Alternatively, the exporter could merge `design/icons/*.svg`.
10. **Protected-list tuning.** Review the static patterns (§6.8) with the packaging owner before
    release.
    - For example, whether `rpm-plugin-*` or `selinux-policy-*` families catch optional tools users
      should be able to remove.
11. **`auth_admin_keep` on `org.arcticlinux.pkexec.dnf`** means any process of the user can run
    arbitrary dnf5 as root for a few minutes after one install. This existing risk isn't widened
    here (D2: privileges unchanged). A narrower helper is a later option.

**Unverified (🔍), and what proves each one**

| # | Claim | Proof |
|---|---|---|
| 1 | dnf5 5.4.6.0 runs `remove --store=DIR -y` as a normal user | WP-A0 harness |
| 2 | `reason` strings in `transaction.json` for dependents and unused dependencies | WP-A0 harness |
| 3 | `repoquery --installed --providers-of=requires --recursive` gives the hard closure | WP-A0 harness |
| 4 | `rpm -qf --qf '[%{FILENAMES}\t%{=NAME}\n]'` output and its time on an installed system (< 1 s) | WP-A0 harness + F44 VM timing |
| 5 | `/usr/lib/sysimage/rpm/rpmdb.sqlite` is the rpmdb path on F44 (cache key) | F44 VM |
| 6 | Flathub AppStream checkout has `icons/128x128` and `icons/64x64`; verified is `flathub::verification::verified` | F44 VM with flathub |
| 7 | `flatpak remote-ls flathub` fails when the remote is in both installations | F44 VM |
| 8 | `flatpak uninstall --system --delete-data` run by the user deletes that user's `~/.var/app/<id>` | F44 VM |
| 9 | Explicitly installed runtimes survive `--unused` (auto-pinning) on flatpak 1.18.2 | F44 VM |
| 10 | Real dnf5/flatpak PTY progress lines match `ParseDNF`/`ParsePercent` | captured fixtures (A2) |
| 11 | `IpcHandler` functions with two `string` arguments work in the F44 Quickshell snapshot | headless `ipc apps search flatpak gimp` |
| 12 | `SplitParser` handles a ~6 MB line (index with summaries) | headless measurement |
| 13 | `notify-send -A` prints the chosen action with the D6 NotificationServer | headless |
| 14 | kitty and alacritty `--class` set the Wayland app_id under Mango | F44 VM |
| 15 | Mango `appid:` regex with `^…\.` anchors | `mango -p` in `%check` + VM |
| 16 | `DesktopEntries` shows new icons (web apps, terminal apps) without a shell restart | F44 VM |
| 17 | `/etc/snapper/configs/root` is readable by users (for the "can be undone" line) | F44 VM |
| 18 | appstream-data's F44 repository and ISO impact (15.1 MB installed) | `tools/build-iso.sh --zen auto` |
| 19 | RPM Fusion appstream-data package names for F44 | RPM Fusion repo query |
| 20 | Tour coordinates for the chooser region and the Flathub search field | first tour run |
| 21 | 70k "All packages" count on F44 and search speed in QML | headless with the real index |
