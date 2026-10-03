# Arctic Linux — zsh (an optional shell). Personal additions go in ~/.zshrc.local.

# ---- Environment --------------------------------------------------------
typeset -U path
path=("$HOME/.local/bin" $path)
export EDITOR="${EDITOR:-nano}"
export PAGER="${PAGER:-less}"
export LESS="-R --mouse"

# ---- History ------------------------------------------------------------
HISTFILE="${XDG_STATE_HOME:-$HOME/.local/state}/zsh/history"
mkdir -p "${HISTFILE:h}"
HISTSIZE=50000
SAVEHIST=50000
setopt EXTENDED_HISTORY HIST_IGNORE_DUPS HIST_IGNORE_SPACE HIST_REDUCE_BLANKS SHARE_HISTORY

# ---- Behaviour ----------------------------------------------------------
setopt AUTO_CD INTERACTIVE_COMMENTS NO_BEEP
bindkey -e
bindkey '^[[H' beginning-of-line  '^[[F' end-of-line  '^[[3~' delete-char
bindkey '^[[1;5D' backward-word   '^[[1;5C' forward-word
autoload -Uz up-line-or-beginning-search down-line-or-beginning-search
zle -N up-line-or-beginning-search; zle -N down-line-or-beginning-search
bindkey '^[[A' up-line-or-beginning-search '^[[B' down-line-or-beginning-search

# ---- Completion ---------------------------------------------------------
autoload -Uz compinit
compinit -d "${XDG_CACHE_HOME:-$HOME/.cache}/zsh/zcompdump-$ZSH_VERSION"
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"

# ---- Theme colours: the active theme's zsh/colors.zsh (prompt, completion menu, plugins),
#      read again before the next prompt whenever the theme changes. fzf reads its colours
#      from the theme's fzf/fzfrc on every run, but refuses to start when
#      FZF_DEFAULT_OPTS_FILE names a missing file: so it is set only while the file is
#      there (checked before every prompt; your own FZF_DEFAULT_OPTS_FILE is never touched).
#      bat and delta use the terminal's palette. -------
export BAT_THEME="${BAT_THEME:-ansi}"
_arctic_fzf() {
  local f=${XDG_CONFIG_HOME:-$HOME/.config}/arctic/current/fzf/fzfrc
  [[ -n ${FZF_DEFAULT_OPTS_FILE:-} && $FZF_DEFAULT_OPTS_FILE != "$f" ]] && return 0
  if [[ -r $f ]]; then
    export FZF_DEFAULT_OPTS_FILE=$f
  else
    unset FZF_DEFAULT_OPTS_FILE
  fi
}
_arctic_fzf
zmodload -F zsh/stat b:zstat 2>/dev/null
typeset -g _arctic_colors_seen=
_arctic_colors() {   # source colors.zsh when the active theme (or its file) changed
  local f=${XDG_CONFIG_HOME:-$HOME/.config}/arctic/current/zsh/colors.zsh stamp
  local -a mtime
  [[ -r $f ]] || return 0
  zstat -A mtime +mtime -- $f 2>/dev/null
  stamp="${f:A} ${mtime[1]:-}"
  [[ $stamp == "$_arctic_colors_seen" ]] && return 0
  _arctic_colors_seen=$stamp
  source $f
}

# ---- Prompt: "~/projects ❯" — directory in green (color2), amber arrow (color3),
#      git branch in dim color8, red arrow after a failed command. With a 24-bit terminal
#      (COLORTERM=truecolor, as in kitty) the theme's exact colours are used instead. -------
autoload -Uz vcs_info
zstyle ':vcs_info:*' enable git
typeset -g _ap_dir=2 _ap_arrow=3 _ap_error=1 _ap_git=8
_arctic_prompt_colors() {
  _arctic_fzf
  _arctic_colors
  if [[ $COLORTERM == (truecolor|24bit) && -n ${ARCTIC_PROMPT_COLORS[dir]:-} ]]; then
    _ap_dir=${ARCTIC_PROMPT_COLORS[dir]} _ap_arrow=${ARCTIC_PROMPT_COLORS[arrow]}
    _ap_error=${ARCTIC_PROMPT_COLORS[error]} _ap_git=${ARCTIC_PROMPT_COLORS[git]}
  fi
  zstyle ':vcs_info:git:*' formats " %F{$_ap_git}%b%f"
  [[ -n ${ARCTIC_MENU_SELECTION:-} ]] && zstyle ':completion:*:default' list-colors "${(s.:.)LS_COLORS}" "ma=$ARCTIC_MENU_SELECTION"
}
precmd() { _arctic_prompt_colors; vcs_info }
setopt PROMPT_SUBST
PROMPT='%F{$_ap_dir}%~%f${vcs_info_msg_0_} %(?.%F{$_ap_arrow}.%F{$_ap_error})❯%f '

# ---- Aliases ------------------------------------------------------------
alias ls='ls --color=auto --group-directories-first'
alias ll='ls -lh'
alias la='ls -lAh'
alias grep='grep --color=auto'
alias y='yazi'

# ---- Greeting: the animated fox (interactive terminals only; ARCTIC_FETCH=0 turns it off) --
if [[ -o interactive && -t 1 && "${ARCTIC_FETCH:-1}" != 0 && "$TERM" != dumb ]] && (( $+commands[arctic-fetch] )); then
  arctic-fetch
fi

[[ -r "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"
