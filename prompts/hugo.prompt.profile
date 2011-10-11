txtgrn='\e[0;32m' # Green
txtred='\e[0;31m' # Red
txtrst='\e[0m'    # Text Reset

export TERM="xterm-color"
export PS1="[${txtred}\t ${txtgrn}\w${txtrst}]\n$> "