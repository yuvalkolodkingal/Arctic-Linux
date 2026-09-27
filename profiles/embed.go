// Package profiles embeds the unattended install profiles so `arctic-install plan` and the
// tests can use them from any working directory.
package profiles

import "embed"

// FS holds defaults.toml and ci/*.toml.
//
//go:embed defaults.toml ci/*.toml
var FS embed.FS
