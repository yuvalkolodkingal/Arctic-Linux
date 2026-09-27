# Arctic Linux installer UI

The Quickshell (Qt 6 / QML) frontend for the 12-step installer wizard. It is a
thin renderer: the engine (`arcticd`, reached through `arctic-install bridge`)
owns steps, defaults and validation (docs/BUILD-SPEC.md §4); this directory only
draws them, following the design system (rail, header, one decision, footer).

```
shell.qml        ShellRoot: one full-screen layer-shell PanelWindow (layer Top,
                 exclusive keyboard, namespace "arctic-installer") + IpcHandler "installer"
Frame.qml        232px rail | header (overline/title/lede or aurora hero) | page | footer;
                 Enter = Next (not on Summary: only its button installs), Alt+Left = Back,
                 F1 = help, Esc = quit (asks first mid-way; not while installing),
                 step-change animation
Theme.qml        tokens from design/exports/Theme.qml (+ type, shadows, motion), fonts
Engine.qml       bridge process, JSON-lines, request ids → callbacks, events
Wizard.qml       wizard state, navigation, install progress from events
steps/           one file per step: Welcome Keyboard Network Timezone Disk Encryption
                 Account Apps Summary Install AttentionView (step 11) Done; StepPage base
components/      ArButton ArInput ArCheck ArRadio ArToggle ArSelect ArList ArListRow ArCard
                 ArProgress ArMeter ArSteps ArBanner ArKbd ArTag ArDialog AppRow AppTile
                 Icon Mark Wordmark AuroraBand FocusRing ShadowRect CornerMask ArText
assets/          exported from the design bundle by dev/export-assets.js: icons/*.svg,
                 tiles/<id>-{light,dark}.svg, mark-{light,dark}.svg, Icons.js
dev/             run.sh, mock-bridge.py, test_mock_bridge.py, test-headless.sh,
                 export-assets.js, screenshots/ (visual record of every step)
```

## Run

Installed: `arctic-installer` (= `quickshell -p /usr/share/arctic/installer-ui`).

From the repo, against the python mock engine (no root, no daemon):

```sh
installer-ui/dev/run.sh
ARCTIC_INSTALLER_THEME=light installer-ui/dev/run.sh          # Winter
ARCTIC_MOCK_ONLINE=1 ARCTIC_MOCK_FAIL=vlc installer-ui/dev/run.sh
ARCTIC_INSTALLER_BRIDGE="arctic-install bridge --mock" installer-ui/dev/run.sh   # Go mock
```

| Variable | Meaning |
|---|---|
| `ARCTIC_INSTALLER_BRIDGE` | command to run instead of `arctic-install bridge` (run with `sh -c`) |
| `ARCTIC_INSTALLER_MOCK=1` | append `--mock` to `arctic-install bridge` |
| `ARCTIC_INSTALLER_SOCKET` | pass `--socket PATH` to the bridge |
| `ARCTIC_INSTALLER_THEME=light` | Winter theme (default Polar night) |
| `ARCTIC_REDUCE_MOTION=1` | no slides; step change is a 120 ms fade |
| `ARCTIC_LIVE_KEYBOARD` | command run instead of `/usr/libexec/arctic/live-keyboard` to apply the keyboard choice to the session (tests; the real helper only runs with a live, non-mock engine) |
| `ARCTIC_MOCK_*` | mock engine knobs, see the header of `dev/mock-bridge.py` |

Fonts: `FontLoader` reads `/usr/share/fonts/arctic/*.woff2` (arctic-fonts), falling
back to `../design/fonts/` in a checkout. The design's Figtree files are named
"Figtree Light" internally; the loader's name is used, so this does not matter here.

## Automation / tests

`quickshell ipc --pid <pid> call installer <fn> [args]`:
`next` (`not ready` until the page's short arm delay has passed: wait for
`state().ready`), `back`, `goto <id>`, `fill '<json>'` (per-step form values, see each
step's `fillForm`), `state` (JSON), `retry`, `skip`, `change` (after a failed install:
back to the Summary), `quit` (Esc), `savelog`, `help`, `focused`, `tab <bool>`,
`theme light|dark`.

The keyboard layout picked on step 2 is applied to the live session as soon as the
engine has it (`live/live-keyboard`, package arctic-live: a Mango include plus
`mmsg dispatch reload_config`), so the passphrase and password are typed with the
layout the installed system checks them with.

```sh
python3 -m unittest installer-ui/dev/test_mock_bridge.py   # protocol tests (no GUI)
installer-ui/dev/test-headless.sh [out-dir]                # sway headless + grim: walks
                                                           # all steps, 3 scenarios
/usr/lib64/qt6/bin/qmllint shell.qml Frame.qml Theme.qml Engine.qml Wizard.qml \
    components/*.qml steps/*.qml                           # run inside installer-ui/
```

`test-headless.sh` needs sway, grim, quickshell, python3 and (for the real key
presses: Enter, Alt+Left, F1, Esc, Tab) wtype. On a container sway may need
`setcap -r /usr/bin/sway` (its cap_sys_nice file capability is refused).

Assets are regenerated with
`node dev/export-assets.js <design project dir containing components/bundle.js>`.
