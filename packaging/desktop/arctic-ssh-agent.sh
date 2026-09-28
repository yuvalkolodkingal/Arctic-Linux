# shellcheck shell=sh
# /etc/profile.d/arctic-ssh-agent.sh (arctic-desktop-config)
# SSH keys: gcr-ssh-agent (the user unit gcr-ssh-agent.socket, enabled by Arctic's user preset)
# holds them for the session and asks for a key's passphrase in a dialog, once. Mango and the
# apps it starts inherit the login shell's environment, so the socket is named here. An agent you
# start yourself (SSH_AUTH_SOCK already set) wins.
if [ -z "${SSH_AUTH_SOCK:-}" ] && [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -S "$XDG_RUNTIME_DIR/gcr/ssh" ]; then
  export SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/gcr/ssh"
fi
