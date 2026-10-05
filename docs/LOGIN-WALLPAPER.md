# Shared SDDM and lock wallpaper

Settings → Appearance → Login and lock wallpaper offers a separate shared image, or
**Use desktop and follow changes**. SDDM and every Arctic lock screen use one public
system copy; the desktop keeps its independent wallpaper unless sync is selected.
Administrator authorization is required for choosing an image, enabling sync, freezing
it, undoing a change, or restoring defaults. Automatic sync never prompts for a password.

## Scope and migration

SDDM belongs to the computer, not to one user. One administrator-authorized account owns
desktop sync for the whole machine, including all seats. Settings resolves its UID to a
local account name when that account still exists.
Another administrator can explicitly choose another image or take over sync. Other users
can read the public image but cannot write it. Processes of the authorized owner's account
can publish automatic changes only while that account has an active, local X11 or Wayland
session. This account-level trust includes user timers and services; it does not isolate
other processes of the same UID (including an SSH process while its local desktop is
active). Without an active local desktop, sync is denied. The last successful copy remains
available at logout and across restarts.

An update creates no public image and does not infer consent from a desktop choice.
Existing SDDM `theme.conf.user`, desktop choice, rotation, themes and lock behavior remain
until a shared image is explicitly authorized. Restoring defaults removes retained public
copies and resumes that legacy behavior. Once a shared image is enabled, it takes priority
over the theme's configured login image and per-user lock background. Colors, blur,
authentication, keyboard handling and the rest of the theme continue as before.

**Privacy:** a selected shared image is visible to everyone at login and on every user's
lock screen. Sync includes future desktop rotation, manually selected desktop images and
theme-driven changes. Do not enable it for a desktop containing images you want private.
The copy remains readable even when the owner's home is encrypted or unmounted. Undo
retains up to three public generations; restore defaults removes all their image files.
The service stores numeric UID, mode, revision and previous revision, never source paths,
user names or original image metadata. Local sync errors stay in the user's state directory.

## Implementation and security boundaries

`arctic-login-wallpaper` is a user CLI and the system D-Bus publisher. Its service runs as
the dedicated `arctic-wallpaper` account with no capabilities, no login shell, no access to
homes, a read-only system, private temporary files/devices and AF_UNIX-only sockets. Its
only persistent writable directory is `/var/lib/arctic-login-wallpaper` (0755). The service
does not run as root and never opens a caller-supplied path. It accepts image bytes, obtains
the caller's UID from D-Bus credentials, and asks polkit about that caller's unique bus name
for `org.arcticlinux.wallpaper.change`. That policy requires a fresh administrator challenge
from an active session; it does not retain authorization or allow remote/inactive requests.
The action's `org.freedesktop.policykit.owner` annotation permits only this service account
to query another caller's authorization for this action; it grants no caller authorization.

The client opens an absolute, regular, non-symlink local file as its own user. It rejects
control characters, URLs, special files, symlinks, and proc/sys/dev/run paths. Both client
and confined publisher validate actual PNG/JPEG/WebP data, not just an extension: static
images only, at most 32 MiB, 32 million pixels and 16384 pixels on either side. Decode must
complete. EXIF orientation is applied, metadata is discarded, and the image is scaled to
fit 3840×2160 while preserving its aspect ratio, then encoded as PNG. SVG, animated images,
TIFF, BMP and GIF are not accepted for the shared image. Desktop choices remain compatible;
an unsupported source in sync leaves the last valid shared copy and reports a local error.

Each generation has a 0644 PNG and JSON policy. Files are flushed before one atomic
relative `current` symlink commits the image and its policy together. File-write,
normalization and pointer-switch failures preserve the previous generation. Revisions
reject stale sync requests; queued clients serialize and read the latest desktop cache
after waiting. The desktop applies choices, theme redraws and timer changes under a lock,
and detached programs close that lock descriptor. Re-publishing identical pixels is a
no-op. Retained generations are bounded, survive service restarts, and support explicit undo.

Every lock surface crops the same image to its own aspect ratio and retains the existing
frost/blur and contrast. The fallback swaylock also reads the public copy. SDDM uses an
image probe every five seconds to bypass Qt's cache after an atomic change; a missing or
unreadable public image falls back to its existing configured/bundled background. The lock
refreshes the policy when locking and every two seconds while visible, using immutable
generation URLs. A broken image falls back to the theme's safe lock background. Neither
reader depends on D-Bus or access to the publisher's home. Existing custom SDDM themes must
add this reader themselves; Settings targets Arctic's SDDM theme.

No PAM file, login method, password/fingerprint flow, SDDM daemon permission or home
permission changes. Package installation supplies a dedicated account and inactive,
D-Bus-activated service. It does not choose an image, enable desktop sync, restart SDDM,
activate a lock, or reboot. Any privileged deployment or security change on the actual
user computer requires separate approval when that action is performed. This work uses
only the saved cloud environment and disposable test systems.

## Delivery plan and acceptance gates

Target: October 6, 2026 morning in Asia/Jerusalem; no exact hour promised.

1. Start from the latest `main`, including PR #18's lock-clock fix. Preserve all other
   changes. Add opt-in UI, public-copy broker, shared readers and backward-compatible paths.
2. Run image/privacy, permissions, rollback, IPC ownership, stale revision, restart, desktop
   rotation and existing Settings/theme/shell regressions. Verify the systemd unit and RPM.
3. Render Settings and its confirmation, actual SDDM test greeter and actual session-lock
   surfaces in isolated compositors, including portrait and multiple monitors; validate
   explicit selection, desktop sync, automatic changes, missing images and fallbacks.
4. Publish a draft PR. Obtain independent security/correctness review and address findings.
   Require successful CI, package build/update validation, and isolated integration evidence
   before merging. Record enforcing-SELinux validation separately from container rendering.
5. Merge to `main`, observe its signed stable Repository workflow through deployment, and
   verify live stable metadata, exact source commit and package versions. Keep existing
   `v1.2.0` ISO/tag intact; no new ISO is requested or built for this feature.

## Commands and diagnosis

```sh
arctic-login-wallpaper status
arctic-login-wallpaper set /absolute/path/to/image.png  # administrator challenge
arctic-login-wallpaper sync-desktop                   # administrator challenge
arctic-login-wallpaper freeze                         # administrator challenge
arctic-login-wallpaper undo                           # administrator challenge
arctic-login-wallpaper reset                          # administrator challenge
arctic-login-wallpaper follow                         # authorized active owner only
journalctl -u arctic-login-wallpaper.service
python3 -m unittest discover -s shell/tests -p 'test_login_wallpaper*.py' -v
```

`arctic-update now` uses the normal signed stable updater and stages the available update.
The user chooses when to install that staged update through the existing update flow.
No command in this handoff has been run on the user's offline laptop.
