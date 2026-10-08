# Packaged photo wallpapers

Arctic's fresh desktop, lock and SDDM defaults use the photographs from
[Yuval Kolodkin-Gal's Wallpapers](https://github.com/yuvalkolodkingal/Wallpapers).
The picker and `arctic-wallpaper rotate 1h arctic` list the exported collection.
The accessible Winter and Polar night colour palettes stay available.

`design/backgrounds/collection.json` records the exact source commit, photographer,
dimensions and SHA-256 of every master. The RPM ships one JPEG master per photo,
the filtered collection metadata and copyright/credit notices. It generates one
PNG for the greeter and `desktop-backgrounds-compat` paths. Raw captures, editing
projects, previews, extra resolutions and upstream desktop configurations are
excluded. The photographs retain their upstream copyright; inclusion at the
photographer's request does not grant an additional general reuse license.

To import a new published revision from a clean, read-only checkout:

```sh
python3 design/tools/import-wallpapers.py --source /path/to/Wallpapers \
  --revision FULL_40_CHARACTER_COMMIT --default PHOTO_SLUG
python3 design/tools/import-wallpapers.py --check
```

The import validates hashes, 16:9 dimensions, credits and absence of camera/date/GPS
EXIF fields before replacing Arctic's exports. It never changes the source repository.

Package updates do not rewrite `~/.config/arctic/wallpaper`, custom themes,
`theme.conf.user`, or the authenticated shared-login-wallpaper broker state. Existing
illustrated names and file paths continue to work; their compatibility images remain
installed but are omitted from the new photo gallery and collection rotation.
