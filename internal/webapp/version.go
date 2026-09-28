package webapp

// Version is the web-app engine version written into app.json. version_test keeps it equal to
// backend.EngineVersion (the manager does not import backend: it pulls in the installer), so
// the release bump raises both.
const Version = "0.2.0"

// Schema is the app.json schema version.
const Schema = 1

// RenderVersion is bumped whenever .desktop or icon rendering changes; apps rendered by an
// older version are re-rendered on their next run, list or serve.
const RenderVersion = 1

// FetchUserAgent is what discovery sends, so the preview sees what the app will see: WebKitGTK
// 2.54's default user agent on x86_64 Linux. The host's smoke test pins it against
// webkit_settings_get_user_agent(); never copy a user agent from a document.
const FetchUserAgent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"

// IDPrefix starts every web-app id (and so every app_id, desktop id and icon name).
const IDPrefix = "org.arcticlinux.WebApp."

// HostPath is the web-app window. ARCTIC_WEBAPP_HOST overrides it for development (read by
// `run` only).
const HostPath = "/usr/libexec/arctic/arctic-webapp-host"
