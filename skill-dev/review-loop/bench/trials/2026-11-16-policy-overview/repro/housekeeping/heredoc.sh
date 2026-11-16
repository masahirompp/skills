. "$1/lib.sh"
git() { :; }
if hk_is_protected main main; then echo "protected=yes"; else echo "protected=NO"; fi
r=$(hk_path_in_use /a/b "$(printf '1\tzsh\t/a/b/c')"); echo "inuse=[$r]"
