" =========================
" Vim Easy Mode for Humans
" =========================

" ---- Basics
set nocompatible
set number relativenumber
set ignorecase smartcase incsearch hlsearch
set clipboard=unnamed,unnamedplus
set wildmenu wildmode=longest:full,full
set hidden
set undofile
set updatetime=300
set laststatus=2

" Indentation defaults (adjust per language if needed)
set expandtab shiftwidth=2 tabstop=2 softtabstop=2
filetype plugin indent on
syntax on

" ---- Leader key (Space)
let mapleader=" "

" ---- Visual cues
set showcmd showmode

" =========================
" Comprehensive F1 Cheatsheet
" =========================
function! EasyCheat() abort
  new
  setlocal buftype=nofile bufhidden=wipe nobuflisted noswapfile
  call setline(1, [
  \ 'Vim Easy Mode — Cheatsheet (press q to close)',
  \ '==============================================================',
  \ '',
  \ 'BASICS',
  \ '  i / a / o         : Insert before/after / new line below',
  \ '  Esc               : Back to Normal mode',
  \ '  u / Ctrl-r        : Undo / Redo',
  \ '  dd / yy / p       : Delete line / Yank (copy) line / Paste',
  \ '  x / X             : Delete char under / before cursor',
  \ '  .                 : Repeat last change',
  \ '',
  \ 'SAVE & QUIT',
  \ '  <Space>w          : Save (write)',
  \ '  <Space>x          : Save & close current buffer',
  \ '  <Space>q          : Save & quit (window)',
  \ '',
  \ 'SEARCH',
  \ '  /text             : Search forward; n / N next/prev match',
  \ '  <F3> / <S-F3>     : Next / Previous match (same as n / N)',
  \ '  :noh              : Clear highlights',
  \ '',
  \ 'FILES & BUFFERS',
  \ '  <C-p>             : Fuzzy open (built-in fallback)',
  \ '  :e filename       : Open file',
  \ '  :w newname        : Save as',
  \ '  <Space>bb         : List buffers; type #: to switch',
  \ '  <Space>bd         : Close current buffer',
  \ '  :ls / :b# / :bn   : List / previous / next buffer',
  \ '',
  \ 'WINDOWS / SPLITS',
  \ '  :sp / :vs         : Horizontal / Vertical split',
  \ '  Ctrl-w h/j/k/l    : Move to split left/down/up/right',
  \ '  Ctrl-w =          : Equalize split sizes',
  \ '  :q                : Close current window',
  \ '',
  \ 'TABS (optional, simple)',
  \ '  :tabnew           : New tab',
  \ '  gt / gT           : Next / Prev tab',
  \ '',
  \ 'BLOCK SELECTION & EDIT (indent-based, no plugins)',
  \ '  <Space>ii         : Select inner indentation block',
  \ '  <Space>ai         : Select outer block (incl. surrounding blanks)',
  \ '  <Space>db         : Delete current indent block',
  \ '',
  \ 'COMMENT (no plugin version)',
  \ '  :s/^/\\/\\/ /       : Prefix lines with // (C-style)',
  \ '  :s/^/# /          : Prefix lines with # (shell)',
  \ '  :%s/^/\\/\\/ /      : Comment entire file with //',
  \ '  (Tip: Visually select lines with V then run the :s command)',
  \ '',
  \ 'INDENT / FORMAT',
  \ '  >> / <<           : Indent / Outdent line (use with Visual mode too)',
  \ '  =G / gg=G         : Auto-indent from cursor to end / entire file',
  \ '',
  \ 'NAVIGATION',
  \ '  gg / G            : Start / End of file',
  \ '  0 / ^ / $         : Line start / first nonblank / end',
  \ '  w / b / e         : Next / Prev / End of word',
  \ '  Ctrl-d / Ctrl-u   : Half-page down / up',
  \ '  Ctrl-f / Ctrl-b   : Page down / up (full screen)',
  \ '  Ctrl-e / Ctrl-y   : Scroll line down / up',
  \ '  %                 : Jump matching () {} []',
  \ '',
  \ 'REGISTERS & CLIPBOARD',
  \ '  "+y / "+p         : Yank / Paste via system clipboard',
  \ '',
  \ 'VISUAL MODES',
  \ '  v / V / Ctrl-v    : Char / Line / Block visual',
  \ '  > / <             : Indent / Outdent selection',
  \ '',
  \ 'REPLACE / MULTILINE',
  \ '  rX                : Replace char with X',
  \ '  :%s/old/new/g     : Replace in whole file',
  \ '  :%s/old/new/gc    : Replace with confirm',
  \ '',
  \ 'FALLBACK FUZZY FIND (no plugins)',
  \ '  <C-p>             : Type part of filename, press <Tab> to complete',
  \ '  :Fuzzy <pattern>  : Same as above (path+=** enables recursive find)',
  \ '',
  \ 'OPTIONAL (IF YOU UNCOMMENT PLUGINS)',
  \ '  <Space> (alone)   : which-key popup of mappings',
  \ '  <Space>ff         : Files (fzf)',
  \ '  <Space>fr         : Recent files (fzf)',
  \ '  <Space>/          : Live grep (ripgrep + fzf)',
  \ '  <Space>j / <Space>J : EasyMotion jump (2-char / word)',
  \ '  gcc / gc          : Toggle comment (commentary)',
  \ '',
  \ 'Tip: You only need to remember: F1, /search, F3, Ctrl-P, Space w/x/q,',
  \ '     Space ii / ai / db for blocks, and Space bb / bd for buffers.',
  \ ])
  nnoremap <buffer> q :bd!<CR>
  setlocal nomodified nomodifiable
  normal! gg
endfunction
nnoremap <F1> :call EasyCheat()<CR>

" =========================
" Quality-of-life mappings (no plugins)
" =========================

" Save / Quit
nnoremap <leader>w :update<CR>
nnoremap <leader>x :update <bar> :bd<CR>
nnoremap <leader>q :update <bar> :q<CR>

" Search navigation on function keys
nnoremap <F3> n
nnoremap <S-F3> N
nnoremap <leader><leader> :nohlsearch<CR>

" ---------- Indentation-based block helpers (no plugin) ----------
function! EasyIndentInner() abort
  " Select lines at the same indentation level
  normal! ^
  let l:col = indent('.')
  " Go up while same-or-deeper indent
  while prevnonblank(line('.')-1) > 0 && indent(prevnonblank(line('.')-1)) >= l:col
    execute "normal! k"
  endwhile
  " Start selection
  normal! 0V
  " Go down while same-or-deeper indent
  while nextnonblank(line('.')+1) > 0 && indent(nextnonblank(line('.')+1)) >= l:col
    execute "normal! j"
  endwhile
  return ''
endfunction

function! EasyIndentOuter() abort
  " Inner block first
  call EasyIndentInner()
  " Include blank lines above
  while line('.')>1 && getline(line('.')-1) =~ '^\s*$'
    normal! kV
  endwhile
  " Include blank lines below
  normal! gv
  while line("'>") < line('$') && getline(line("'>")+1) =~ '^\s*$'
    execute "normal! gvj"
  endwhile
  return ''
endfunction

" Map block select/delete
nnoremap <leader>ii :<C-u>call EasyIndentInner()<CR>gv
vnoremap <leader>ii :<C-u>normal! gv<CR>
nnoremap <leader>ai :<C-u>call EasyIndentOuter()<CR>gv
vnoremap <leader>ai :<C-u>normal! gv<CR>
nnoremap <leader>db :<C-u>call EasyIndentInner()<CR>gvd

" ---------- Navigation shortcuts ----------
" Page up/down shortcuts (Vim defaults already work: Ctrl-f/Ctrl-b)
" But we can add additional mappings for clarity:
nnoremap <PageDown> <C-f>
nnoremap <PageUp> <C-b>
nnoremap <End> G
nnoremap <Home> gg

" ---------- Buffer helpers ----------
nnoremap <leader>bb :ls<CR>:b<Space>
nnoremap <leader>bd :bd<CR>

" ---------- Minimal fallback "fuzzy" open (no plugins) ----------
set path+=**
set wildignore+=*.o,*.obj,*.pyc,*.class,*.so,*.dll,*.zip,*.tar,*.gz,*.tgz
command! -nargs=1 -complete=file Fuzzy find <args>
nnoremap <C-p> :Fuzzy 

" =========================
" OPTIONAL PLUGINS (COMMENTED OUT BY DEFAULT)
" =========================
" To enable, UNCOMMENT this whole block.
"
" if has('nvim') || has('patch-8.0')
"   " Install vim-plug if missing
"   if empty(glob('~/.vim/autoload/plug.vim'))
"     silent !curl -fLo ~/.vim/autoload/plug.vim --create-dirs \
"       https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
"     autocmd VimEnter * PlugInstall --sync | source $MYVIMRC
"   endif
"
"   call plug#begin('~/.vim/plugged')
"     Plug 'liuchengxu/vim-which-key'          " On-screen key hints
"     Plug 'junegunn/fzf', { 'do': { -> fzf#install() } }
"     Plug 'junegunn/fzf.vim'                   " :Files, :Rg, :Buffers
"     Plug 'easymotion/vim-easymotion'          " Jump navigation
"     Plug 'tpope/vim-commentary'               " gcc to comment
"     Plug 'wellle/targets.vim'                 " Better text objects a"/) etc.
"     Plug 'tpope/vim-surround'                 " cs"'
"   call plug#end()
"
"   " which-key: press Space to see options
"   nnoremap <silent> <leader> :WhichKey '<Space>'<CR>
"
"   " fzf mappings
"   nnoremap <silent> <leader>ff :Files<CR>
"   nnoremap <silent> <leader>fr :History<CR>
"   if executable('rg')
"     nnoremap <silent> <leader>/ :Rg<Space>
"   else
"     nnoremap <silent> <leader>/ :vimgrep /<C-r><C-w>/ **/*<CR>:copen<CR>
"   endif
"
"   " easymotion
"   nmap <leader>j <Plug>(easymotion-s2)
"   nmap <leader>J <Plug>(easymotion-w)
"
"   " commentary: gcc in normal, gc in visual
" endif