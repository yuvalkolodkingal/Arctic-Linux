# Arctic Linux — Fish login shell. Keep personal changes in config.local.fish.
# Path changes also apply to the login shell that starts the desktop.
fish_add_path --path $HOME/.local/bin $HOME/.local/state/nix/profiles/arctic/bin $HOME/.local/state/nix/profile/bin $HOME/.nix-profile/bin /nix/var/nix/profiles/default/bin

if not set -q EDITOR
    set -gx EDITOR nano
end
if not set -q PAGER
    set -gx PAGER less
end

# Nix's own Fish setup, when supplied by the installed Nix profile.
if test -r /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.fish
    source /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.fish
end

if status is-interactive
    alias ls 'ls --color=auto --group-directories-first'
    alias ll 'ls -lh'
    alias la 'ls -lAh'
    alias y yazi
    alias grep 'grep --color=auto'
end

if test -r $HOME/.config/fish/config.local.fish
    source $HOME/.config/fish/config.local.fish
end

if status is-interactive; and isatty stdout; and test "$TERM" != dumb; and not contains -- 0 "$ARCTIC_FETCH"; and command -q arctic-fetch
    arctic-fetch
end
