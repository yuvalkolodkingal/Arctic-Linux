#!/usr/bin/env bash
# Create one local, test-only immutable QEMU/firmware image for a paired run.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tools/lib/container.sh
source "$HERE/lib/container.sh"
[[ $# == 1 || $# == 2 ]] || arctic_die "usage: prepare-vm-tools.sh EVIDENCE_DIRECTORY [PAIRED_TASK_ID]"
task_id="${2:-}"
[[ $# == 1 || "$task_id" =~ ^[0-9a-f]{32}$ ]] || arctic_die "invalid paired task identity"
container="${ARCTIC_VM_CONTAINER_NAME:-arctic-paired-tools-$(date +%s)-$$}"
[[ "$container" =~ ^arctic-paired-[a-z0-9-]{1,80}$ ]] || arctic_die "invalid task provisioning container name"
[[ -z "$task_id" || "$container" =~ ^arctic-paired-${task_id}-[0-9a-f]{8}$ ]] || arctic_die "provisioning container differs from paired task"
mkdir -p "$1"
evidence="$(cd "$1" && pwd)"
arctic_ensure_engine
engine="$(arctic_engine)"
arctic_container_args
base_id="$(arctic_resolve_image "$engine" "$ARCTIC_FEDORA_IMAGE")"
cleanup() { "$engine" rm --force "$container" >/dev/null 2>&1 || :; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$engine" run --name "$container" "${ARCTIC_CONTAINER_ARGS[@]}" "$base_id" bash -c "$ARCTIC_CONTAINER_PROLOGUE"'
dnf -y install qemu-system-x86-core qemu-img edk2-ovmf seabios-bin python3-pillow xorriso \
  qemu-device-display-virtio-vga qemu-device-display-virtio-gpu qemu-device-display-virtio-gpu-pci
'
image_changes=()
if [[ -n "$task_id" ]]; then
  # Exclusive intent precedes the commit: the parent can recover its image
  # even if cancellation interrupts commit's reply or the subsequent ID file.
  python3 - "$evidence/vm-prepared-image-owner.json" "$task_id" "$container" "$base_id" <<'PY'
import json, os, sys
path, task_id, container, base_id = sys.argv[1:]
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(descriptor, 'w') as receipt:
    json.dump(dict(schema='arctic-paired-test-image-owner-v1', release_acceptance=False,
        task_id=task_id, container=container, base_id=base_id), receipt)
    receipt.write('\n')
PY
  image_changes=(--change 'LABEL org.arctic.test.vm-tools.scope=paired-v1'
    --change "LABEL org.arctic.test.vm-tools.task=$task_id"
    --change "LABEL org.arctic.test.vm-tools.container=$container"
    --change "LABEL org.arctic.test.vm-tools.base=$base_id")
fi
image_id="$("$engine" commit "${image_changes[@]}" "$container")"
[[ "$image_id" =~ ^(sha256:)?[0-9a-f]{64}$ ]] || arctic_die "invalid prepared VM image identity"
printf '%s\n' "$base_id" > "$evidence/vm-base-image-id.txt"
printf '%s\n' "$image_id" > "$evidence/vm-prepared-image-id.txt"
arctic_log "prepared test-only QEMU image: $image_id"
