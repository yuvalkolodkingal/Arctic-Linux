# Arctic Linux — zsh (the default shell). Personal additions go in ~/.zshrc.local.

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

# ---- Prompt: "~/projects ❯" — directory in green (color2), amber arrow (color3),
#      git branch in dim color8, red arrow after a failed command. -------
autoload -Uz vcs_info
zstyle ':vcs_info:git:*' formats ' %F{8}%b%f'
zstyle ':vcs_info:*' enable git
precmd() { vcs_info }
setopt PROMPT_SUBST
PROMPT='%F{2}%~%f${vcs_info_msg_0_} %(?.%F{3}.%F{1})❯%f '

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
