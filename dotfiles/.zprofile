# Arctic Linux — zsh login shell. SDDM starts the Mango session through your login shell,
# so anything set here reaches every app launched from the desktop.
typeset -U path
path=("$HOME/.local/bin" $path)
export PATH
