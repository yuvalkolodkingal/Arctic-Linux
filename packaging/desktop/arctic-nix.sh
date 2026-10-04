# shellcheck shell=sh
# RPM-owned login environment; applies to existing accounts as well as /etc/skel.
# Keep the same dedicated profile path as shell/scripts/nixlib.py.
if [ -n "${HOME:-}" ]; then
    # Must exist before Quickshell starts watching XDG application directories.
    mkdir -p -- "${XDG_DATA_HOME:-$HOME/.local/share}/applications" 2>/dev/null || :
    for arctic_nix_profile in /nix/var/nix/profiles/default "$HOME/.nix-profile" "$HOME/.local/state/nix/profile" "$HOME/.local/state/nix/profiles/arctic"; do
        case ":${PATH:-}:" in
            *":$arctic_nix_profile/bin:"*) ;;
            *) PATH="$arctic_nix_profile/bin${PATH:+:$PATH}" ;;
        esac
        case ":${XDG_DATA_DIRS:-}:" in
            *":$arctic_nix_profile/share:"*) ;;
            *) XDG_DATA_DIRS="$arctic_nix_profile/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" ;;
        esac
    done
    export PATH XDG_DATA_DIRS
    unset arctic_nix_profile
fi
