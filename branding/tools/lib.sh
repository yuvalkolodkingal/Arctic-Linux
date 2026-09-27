# shellcheck shell=bash
# shellcheck disable=SC2034  # the path variables are used by the scripts that source this
# Shared helpers for the branding build scripts.
#
# Every script needs a few Fedora tools (rsvg-convert, python3-fonttools,
# python3-pillow, grub2-mkfont, ...). On a Fedora host with those installed the
# scripts run directly. Otherwise they re-run themselves inside a Fedora 44
# container (docker or podman), mounting the repository at /src.

set -euo pipefail

BRANDING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$BRANDING_DIR/.." && pwd)"
DESIGN_DIR="$REPO_DIR/design"
TOOLS_DIR="$BRANDING_DIR/tools"
BUILD_DIR="$BRANDING_DIR/.build"
FEDORA_IMAGE="${FEDORA_IMAGE:-registry.fedoraproject.org/fedora:44}"

# Packages the branding tools need inside Fedora.
BRANDING_DEPS=(librsvg2-tools python3-fonttools python3-brotli python3-pillow grub2-tools-extra)

log() { printf '[branding] %s\n' "$*" >&2; }
die() { printf '[branding] error: %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

have_python_mod() { python3 -c "import $1" >/dev/null 2>&1; }

# tools_ready CMD... : true when every command (and the python modules) exist.
tools_ready() {
    local t
    for t in "$@"; do have "$t" || return 1; done
    have python3 || return 1
    have_python_mod fontTools || return 1
    have_python_mod PIL || return 1
    python3 -c 'import brotli' >/dev/null 2>&1 || return 1
}

container_engine() {
    if have docker && docker info >/dev/null 2>&1; then echo docker
    elif have podman; then echo podman
    else return 1
    fi
}

# reexec_in_container SCRIPT ARGS... : run SCRIPT (path relative to the repo)
# inside a Fedora container. The proxy/CA bits are added only when present,
# so this works both here and on GitHub runners.
reexec_in_container() {
    local script="$1"; shift
    local engine
    engine="$(container_engine)" || die "missing tools and no docker/podman to provide them"
    local args=(run --rm -v "$REPO_DIR:/src:z" -w /src -e ARCTIC_BRANDING_IN_CONTAINER=1)
    if [[ -n "${HTTPS_PROXY:-${https_proxy:-}}" ]]; then
        args+=(--network host -e "https_proxy=${HTTPS_PROXY:-$https_proxy}" -e "HTTPS_PROXY=${HTTPS_PROXY:-$https_proxy}")
    fi
    if [[ -f /root/.ccr/ca-bundle.crt ]]; then
        args+=(-v /root/.ccr/ca-bundle.crt:/etc/pki/ca-trust/source/anchors/ccr.crt:ro)
    fi
    log "tools missing on the host; running $script in $FEDORA_IMAGE ($engine)"
    "$engine" "${args[@]}" "$FEDORA_IMAGE" bash -c "
        set -e
        update-ca-trust 2>/dev/null || true
        dnf -y -q install --setopt=install_weak_deps=False ${BRANDING_DEPS[*]} ${EXTRA_DEPS:-} >/dev/null
        /src/$script $*
        chown -R $(id -u):$(id -g) /src/branding 2>/dev/null || true
    "
}

# ensure_tools SCRIPT_REL CMD... : exec the calling script in a container when
# the listed commands are not available.
ensure_tools() {
    local script="$1"; shift
    if tools_ready "$@"; then return 0; fi
    if [[ -n "${ARCTIC_BRANDING_IN_CONTAINER:-}" ]]; then
        die "required tools missing inside the container: $*"
    fi
    reexec_in_container "$script" "${SCRIPT_ARGS[@]}"
    exit 0
}

# render_svg IN OUT WIDTH [HEIGHT] : SVG -> PNG with librsvg.
render_svg() {
    local in="$1" out="$2" w="$3" h="${4:-}"
    mkdir -p "$(dirname "$out")"
    if [[ -n "$h" ]]; then
        rsvg-convert -w "$w" -h "$h" -o "$out" "$in"
    else
        rsvg-convert -w "$w" -o "$out" "$in"
    fi
}
