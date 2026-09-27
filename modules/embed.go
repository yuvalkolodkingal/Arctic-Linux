// Package modules embeds the app catalog (catalog.toml and every module.toml) so the engine
// binaries also work without /usr/share/arctic/catalog: in development, for
// `arctic-install bridge --mock` and in tests. The packaged catalog directory wins when present.
package modules

import "embed"

// FS holds catalog.toml and */*/module.toml (including _system/*).
//
//go:embed catalog.toml */*/module.toml
var FS embed.FS
