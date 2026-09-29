# arctic-fetch-3d

The greeting you see in a new terminal: the Arctic fox drawn in 3D on your terminal's
background, beside a short summary of your system.

This is [fastfetch](https://github.com/fastfetch-cli/fastfetch)'s `fetch.c`, vendored so Arctic
can keep its own wording, fields and artwork without forking the whole project. `fetch.c` is
ISC-licensed (see `LICENSE`); everything Arctic added to it is marked in the file.

`arctic-fetch` itself stays a shell script (`dotfiles/.local/bin/arctic-fetch`). It draws the fox
with an embedded Python renderer when the C binary is missing, so a checkout with no compiler
still gets a greeting. The binary is only the nicer, faster path.

## Building

Nothing but a C compiler and libm:

```sh
make            # ./arctic-fetch-3d
make install    # into $(LIBEXECDIR), default /usr/libexec/arctic
```

The RPM builds this in `%build` and installs the binary into `%{_libexecdir}/arctic`
(`packaging/arctic-linux.spec`). The version comes from `VERSION`, and the build machine's
codename, arch and OS are baked in as the fallbacks you see before anything is detected.

## What Arctic changed

- **Wording and fields.** `base` (the Fedora build Arctic is made from) and `updates`
  (`arctic-update` state) are new. `os` reads as "Arctic Linux …" on Arctic and passes other
  distributions through untouched, so the same binary is correct on a live USB and in a
  container.
- **The logo.** The built-in drawing is the Arctic fox (not Gentoo), in the same 8-row form the
  shell script draws. `logo.txt` can replace it, from `~/.config/arctic/fetch/logo.txt` and a few
  system paths; `$1`…`$9` are stripped, so the shell script's template can be reused as is.
- **Layout.** Labels are padded to a column instead of `label: value`, matching the fastfetch
  layouts, and the rule under the title is a `─` (configurable).
- **Mango** is recognised as a window manager, and the theme is read from Arctic's own
  `theme.env` when there is one, so the greeting matches the desktop.

## Configuring

`config` in this directory is the system default, installed to
`/usr/share/arctic/fetch/config`. To change it per user, copy it to
`~/.config/arctic/fetch/config` — that path wins. One field name per line; comment a line out to
hide that field, and the order of the lines is the order of the column. `label_color`,
`title_color` and `separator` are settings in the same file. The same list is in
`config_defaults()` in `fetch.c`; keep the two in step.

## Testing

`design/themegen/tests/test_fastfetch.py` runs `arctic-fetch --info` and checks that every line
names a real fact, and the fastfetch layouts are checked by the theme tests. The C build itself
is compiled in CI (`fetch-c` job in `.github/workflows/ci.yml`).
