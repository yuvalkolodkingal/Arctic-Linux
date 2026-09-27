# shellcheck shell=bash
# Shared helpers for tools/*.sh: run steps inside a Fedora container with docker or podman.
#
#   ARCTIC_FEDORA_IMAGE   container image (default registry.fedoraproject.org/fedora:44)
#   CONTAINER_ENGINE      docker | podman (default: whichever is installed, docker first)
#   ARCTIC_CA_BUNDLE      extra CA bundle to trust inside the container (default:
#                         /root/.ccr/ca-bundle.crt when it exists, e.g. behind an agent proxy)
#   HTTPS_PROXY/https_proxy  passed through (with --network host) only when set
#
# Nothing proxy-specific is added on a machine without a proxy (GitHub runners).

ARCTIC_FEDORA_IMAGE="${ARCTIC_FEDORA_IMAGE:-registry.fedoraproject.org/fedora:44}"

arctic_repo_root() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  printf '%s\n' "$here"
}

arctic_log() { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
arctic_die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

arctic_engine() {
  if [[ -n "${CONTAINER_ENGINE:-}" ]]; then
    printf '%s\n' "$CONTAINER_ENGINE"
  elif command -v docker >/dev/null 2>&1; then
    printf 'docker\n'
  elif command -v podman >/dev/null 2>&1; then
    printf 'podman\n'
  else
    arctic_die "neither docker nor podman is installed"
  fi
}

# Fills the array ARCTIC_CONTAINER_ARGS with the network/proxy/CA options for this host.
arctic_container_args() {
  ARCTIC_CONTAINER_ARGS=()
  local proxy="${HTTPS_PROXY:-${https_proxy:-}}"
  if [[ -n "$proxy" ]]; then
    ARCTIC_CONTAINER_ARGS+=(--network host -e "https_proxy=$proxy" -e "HTTPS_PROXY=$proxy")
    local noproxy="${NO_PROXY:-${no_proxy:-}}"
    [[ -n "$noproxy" ]] && ARCTIC_CONTAINER_ARGS+=(-e "no_proxy=$noproxy" -e "NO_PROXY=$noproxy")
  fi
  local ca="${ARCTIC_CA_BUNDLE:-}"
  if [[ -z "$ca" && -r /root/.ccr/ca-bundle.crt ]]; then
    ca=/root/.ccr/ca-bundle.crt
  fi
  if [[ -n "$ca" && -r "$ca" ]]; then
    ARCTIC_CONTAINER_ARGS+=(-v "$ca:/etc/pki/ca-trust/source/anchors/arctic-extra-ca.crt:ro"
                            -e ARCTIC_EXTRA_CA=1)
  fi
}

# Prologue every in-container script runs first: trust the extra CA, tune dnf.
# shellcheck disable=SC2016,SC2034
ARCTIC_CONTAINER_PROLOGUE='
set -euo pipefail
if [[ "${ARCTIC_EXTRA_CA:-}" == 1 ]]; then update-ca-trust; fi
grep -q "^max_parallel_downloads" /etc/dnf/dnf.conf 2>/dev/null || echo "max_parallel_downloads=10" >> /etc/dnf/dnf.conf
grep -q "^retries" /etc/dnf/dnf.conf 2>/dev/null || echo "retries=20" >> /etc/dnf/dnf.conf
'

# Ensure the docker daemon answers (starts dockerd in the background when it is installed but
# not running, as in throwaway CI/dev VMs).
arctic_ensure_engine() {
  local engine
  engine="$(arctic_engine)"
  if [[ "$engine" == docker ]] && ! docker info >/dev/null 2>&1; then
    if [[ $EUID -eq 0 ]] && command -v dockerd >/dev/null 2>&1 && [[ ! -S /var/run/docker.sock ]]; then
      arctic_log "starting dockerd"
      (dockerd >/tmp/dockerd.log 2>&1 &)
      for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
    fi
    docker info >/dev/null 2>&1 || arctic_die "docker is installed but the daemon is not reachable"
  fi
}
