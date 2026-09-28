# shellcheck shell=bash
# Arctic Linux — bash (installed, not the default shell). Fedora's ~/.bashrc sources ~/.bashrc.d/*.
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH" ;; esac

# Same prompt as zsh: "~/projects ❯" — green directory, amber arrow, red after a failure.
__arctic_ps1() {
  local s=$?
  local arrow='\[\e[33m\]❯\[\e[0m\]'
  (( s != 0 )) && arrow='\[\e[31m\]❯\[\e[0m\]'
  PS1="\[\e[32m\]\w\[\e[0m\] ${arrow} "
}
# fzf reads its colours from the active theme's fzf/fzfrc on every run, but refuses to start
# when FZF_DEFAULT_OPTS_FILE names a missing file (a theme without one, a dangling `current`):
# so it is set only while the file is there, checked again before every prompt so a theme
# switch is followed. A FZF_DEFAULT_OPTS_FILE of your own is never touched.
__arctic_fzf() {
  local f="${XDG_CONFIG_HOME:-$HOME/.config}/arctic/current/fzf/fzfrc"
  [[ -n "${FZF_DEFAULT_OPTS_FILE:-}" && "$FZF_DEFAULT_OPTS_FILE" != "$f" ]] && return 0
  if [[ -r "$f" ]]; then
    export FZF_DEFAULT_OPTS_FILE="$f"
  else
    unset FZF_DEFAULT_OPTS_FILE
  fi
}
__arctic_fzf
# __arctic_ps1 first: it reads the last command's exit status.
PROMPT_COMMAND="__arctic_ps1; __arctic_fzf${PROMPT_COMMAND:+; $PROMPT_COMMAND}"

# bat and delta use the terminal's palette.
export BAT_THEME="${BAT_THEME:-ansi}"

alias ls='ls --color=auto --group-directories-first'
alias ll='ls -lh'
alias la='ls -lAh'
