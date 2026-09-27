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
PROMPT_COMMAND="__arctic_ps1${PROMPT_COMMAND:+; $PROMPT_COMMAND}"

alias ls='ls --color=auto --group-directories-first'
alias ll='ls -lh'
alias la='ls -lAh'
