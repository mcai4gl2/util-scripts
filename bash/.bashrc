### --- HISTORY: better, bigger, de-duplicated, timestamped, shared across shells ---
# Append instead of overwrite; load new lines added by other shells (great inside tmux)
shopt -s histappend
PROMPT_COMMAND='history -a; history -n; '"$PROMPT_COMMAND"

# Big history, avoid dupes & commands starting with a space, show timestamps
HISTSIZE=200000
HISTFILESIZE=400000
HISTCONTROL=ignoreboth:erasedups
HISTTIMEFORMAT='%F %T  '

# Ignore noisy stuff (add what you like)
HISTIGNORE='ls:bg:fg:history:clear:exit'

### --- GLOBBING & QUALITY OF LIFE ---
shopt -s checkwinsize       # Update LINES/COLUMNS after each command
shopt -s cdspell            # Fix minor typos in 'cd' targets
shopt -s autocd             # Type a folder name to cd into it
shopt -s globstar           # ** matches files/dirs recursively (bash 4+)
# shopt -s nocaseglob       # Uncomment if you want case-insensitive globs

### --- ALIASES (edit to taste) ---
alias ll='ls -alF --color=auto'
alias la='ls -A --color=auto'
alias l='ls -CF --color=auto'
alias ..='cd ..'
alias ...='cd ../..'
alias grep='grep --color=auto'
alias df='df -h'
alias du='du -h'
alias rm='rm -i'            # safety
alias cp='cp -i'
alias mv='mv -i'

### --- QUICK SEARCH HELPERS (no extra tools required) ---
# Search your history quickly (case-insensitive)
h() { history | sed 's/^[[:space:]]*[0-9]\+[[:space:]]*//' | grep -i -- "$*"; }

# Find files by name (case-insensitive):  ff readme   → ./docs/README.md
ff() { find . -type f -iname "*${1:-}*" 2>/dev/null; }

# Search within files: gf pattern [dir] (defaults to .)
gf() { grep -RIn --line-number --color=auto -- "${1:?pattern required}" "${2:-.}"; }

### --- DIRECTORY BOOKMARKS (works anywhere, no install) ---
# bookmark proj   → saves current dir as 'proj'
# jump proj       → cd to the saved dir
bookmark() { [ -z "$1" ] && { echo "bookmark <name>"; return 1; }
             mkdir -p "$HOME/.bmarks"; printf "%s\n" "$PWD" > "$HOME/.bmarks/$1"; }
jump()     { [ -f "$HOME/.bmarks/$1" ] && cd -- "$(cat "$HOME/.bmarks/$1")" || echo "No such mark: $1"; }
marks()    { ls "$HOME/.bmarks" 2>/dev/null || true; }

# Go up to an ancestor by name: bd src  → cd /…/src
bd() { local target="$1"; [ -z "$target" ] && { echo "bd <dirname>"; return 1; }
       local up="$PWD"; while [ "$up" != "/" ]; do
         [ "$(basename "$up")" = "$target" ] && { cd "$up"; return; }
         up="$(dirname "$up")"
       done; echo "No such ancestor: $target"; }

### --- PROMPT (shows git branch if available, is fast & readable) ---
# Try to load git's prompt helper if present (system paths vary)
for p in \
  /usr/share/git-core/contrib/completion/git-prompt.sh \
  /usr/share/git/completion/git-prompt.sh \
  /etc/bash_completion.d/git-prompt \
  ; do [ -f "$p" ] && . "$p" && break; done

GIT_PS1_SHOWDIRTYSTATE=1
GIT_PS1_SHOWUPSTREAM=auto
# Prompt: user@host folder (git) on one line, then $ on the next
PS1='\[\e[0;32m\]\u@\h \[\e[0;36m\]\w\[\e[0;33m\]$(__git_ps1 " (%s)")\[\e[0m\]\n\$ '

### --- LESS defaults (wrap off, preserves colors) ---
export LESS='-R -S -F -X'
export LESSHISTFILE='-'    # avoid writing a less history file if desired

### --- OPTIONAL: kubectl tiny helpers (only run if kubectl exists) ---
if command -v kubectl >/dev/null 2>&1; then
  alias k='kubectl'
  kns() { kubectl config set-context --current --namespace="${1:?namespace}"; }
  kctx() { kubectl config use-context "${1:?context}"; }
  kctxs() { kubectl config get-contexts; }
fi

# fzf-powered history/file pickers (used only if fzf exists)
if command -v fzf >/dev/null 2>&1; then
  fh() { local sel; sel="$(history | sed 's/^[[:space:]]*[0-9]\+[[:space:]]*//' \
        | fzf --height 40% --reverse --tac)"; [ -n "$sel" ] && printf '%s\n' "$sel"; }
  fe() { local f; f="$(fzf --height 40% --reverse)"; [ -n "$f" ] && "${EDITOR:-vim}" "$f"; }
  # Ctrl-R replacement (bind if desired):
  # bind -x '"\C-r": "READLINE_LINE=$(history | sed \"s/^[[:space:]]*[0-9]\+[[:space:]]*//\" | fzf --tac --reverse); READLINE_POINT=${#READLINE_LINE}"'
fi

if [ -f ~/.bash_functions_extract ]; then
    source ~/.bash_functions_extract
fi

alias x=extract

if [ -f ~/.bash_functions_tm ]; then
    source ~/.bash_functions_tm
fi


if [ -f ~/.bash_functions_pidinfo ]; then
    source ~/.bash_functions_pidinfo
fi
