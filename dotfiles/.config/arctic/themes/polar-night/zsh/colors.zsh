# Arctic Linux — Polar night: colours for zsh (prompt, completion menu, plugins).
# Rendered by arctic-themegen from design/themegen/templates/zsh/colors.zsh.tmpl.
# ~/.zshrc sources ~/.config/arctic/current/zsh/colors.zsh, and sources it again before the
# next prompt whenever the theme changes, so open terminals follow a theme switch.

typeset -g ARCTIC_THEME_MODE=dark

# Prompt colours ("~/projects ❯"): directory, arrow, arrow after a failed command, git branch.
# Used as 24-bit colours when the terminal supports them (COLORTERM=truecolor); otherwise the
# prompt keeps ANSI colours 2, 3, 1 and 8, which the terminal's own palette maps.
typeset -gA ARCTIC_PROMPT_COLORS
ARCTIC_PROMPT_COLORS=(
  dir   '#7fcf9b'
  arrow '#f6bd55'
  error '#ff9189'
  git   '#8f9cab'
)

# Completion menu (menu select): the selected entry on accent-soft, as in the launcher.
typeset -g ARCTIC_MENU_SELECTION="48;2;58, 45, 22;38;2;233, 238, 243"
ARCTIC_MENU_SELECTION=${ARCTIC_MENU_SELECTION//, /;}

# zsh-autosuggestions and zsh-syntax-highlighting, if you install them.
typeset -g ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#8f9cab'
typeset -gA ZSH_HIGHLIGHT_STYLES
ZSH_HIGHLIGHT_STYLES[command]='fg=#7fcf9b'
ZSH_HIGHLIGHT_STYLES[builtin]='fg=#7fcf9b'
ZSH_HIGHLIGHT_STYLES[alias]='fg=#7fcf9b'
ZSH_HIGHLIGHT_STYLES[function]='fg=#80b0e8'
ZSH_HIGHLIGHT_STYLES[reserved-word]='fg=#d49ccf'
ZSH_HIGHLIGHT_STYLES[unknown-token]='fg=#ff9189'
ZSH_HIGHLIGHT_STYLES[path]='fg=#e9eef3,underline'
ZSH_HIGHLIGHT_STYLES[single-quoted-argument]='fg=#f6bd55'
ZSH_HIGHLIGHT_STYLES[double-quoted-argument]='fg=#f6bd55'
ZSH_HIGHLIGHT_STYLES[comment]='fg=#8f9cab'
