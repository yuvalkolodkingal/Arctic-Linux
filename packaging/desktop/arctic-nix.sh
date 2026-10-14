# shellcheck shell=sh
# RPM-owned login environment; applies to existing accounts as well as /etc/skel.
# Keep the same dedicated profile path as shell/scripts/nixlib.py.
if [ -n "${HOME:-}" ]; then
    # Must exist before Quickshell starts watching XDG application directories.
    mkdir -p -- "${XDG_DATA_HOME:-$HOME/.local/share}/applications" 2>/dev/null || :
    # User, administrator, Flatpak and Nix entries keep precedence. Arctic's
    # Celluloid override shadows only the vendor entry under /usr/share.
    arctic_xdg_source=${XDG_DATA_DIRS:-/usr/local/share:/var/lib/flatpak/exports/share:/usr/share}
    XDG_DATA_DIRS=
    arctic_xdg_inserted=false
    arctic_xdg_old_ifs=$IFS
    IFS=:
    for arctic_xdg_dir in $arctic_xdg_source; do
        [ -n "$arctic_xdg_dir" ] || continue
        [ "$arctic_xdg_dir" = /usr/share/arctic ] && continue
        if [ "$arctic_xdg_dir" = /usr/share ] && [ "$arctic_xdg_inserted" = false ]; then
            XDG_DATA_DIRS="${XDG_DATA_DIRS:+$XDG_DATA_DIRS:}/usr/share/arctic"
            arctic_xdg_inserted=true
        fi
        XDG_DATA_DIRS="${XDG_DATA_DIRS:+$XDG_DATA_DIRS:}$arctic_xdg_dir"
    done
    IFS=$arctic_xdg_old_ifs
    unset arctic_xdg_source arctic_xdg_inserted arctic_xdg_old_ifs arctic_xdg_dir
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
