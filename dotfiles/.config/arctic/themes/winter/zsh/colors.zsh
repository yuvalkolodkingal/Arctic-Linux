# Arctic Linux — Winter: colours for zsh (prompt, completion menu, plugins).
# Rendered by arctic-themegen from design/themegen/templates/zsh/colors.zsh.tmpl.
# ~/.zshrc sources ~/.config/arctic/current/zsh/colors.zsh, and sources it again before the
# next prompt whenever the theme changes, so open terminals follow a theme switch.

typeset -g ARCTIC_THEME_MODE=light

# Prompt colours ("~/projects ❯"): directory, arrow, arrow after a failed command, git branch.
# Used as 24-bit colours when the terminal supports them (COLORTERM=truecolor); otherwise the
# prompt keeps ANSI colours 2, 3, 1 and 8, which the terminal's own palette maps.
typeset -gA ARCTIC_PROMPT_COLORS
ARCTIC_PROMPT_COLORS=(
  dir   '#1d7350'
  arrow '#84500d'
  error '#b3261e'
  git   '#5f6b79'
)

# Completion menu (menu select): the selected entry on accent-soft, as in the launcher.
typeset -g ARCTIC_MENU_SELECTION="48;2;253, 240, 214;38;2;21, 26, 33"
ARCTIC_MENU_SELECTION=${ARCTIC_MENU_SELECTION//, /;}

# zsh-autosuggestions and zsh-syntax-highlighting, if you install them.
typeset -g ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#5f6b79'
typeset -gA ZSH_HIGHLIGHT_STYLES
ZSH_HIGHLIGHT_STYLES[command]='fg=#1d7350'
ZSH_HIGHLIGHT_STYLES[builtin]='fg=#1d7350'
ZSH_HIGHLIGHT_STYLES[alias]='fg=#1d7350'
ZSH_HIGHLIGHT_STYLES[function]='fg=#1f5f9e'
ZSH_HIGHLIGHT_STYLES[reserved-word]='fg=#8a3d86'
ZSH_HIGHLIGHT_STYLES[unknown-token]='fg=#b3261e'
ZSH_HIGHLIGHT_STYLES[path]='fg=#151a21,underline'
ZSH_HIGHLIGHT_STYLES[single-quoted-argument]='fg=#84500d'
ZSH_HIGHLIGHT_STYLES[double-quoted-argument]='fg=#84500d'
ZSH_HIGHLIGHT_STYLES[comment]='fg=#5f6b79'
