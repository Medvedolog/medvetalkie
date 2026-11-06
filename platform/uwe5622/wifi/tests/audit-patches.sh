#!/usr/bin/env bash
# CI-only static patch applicability audit. NEVER builds or loads modules.
set -euo pipefail

if (( $# != 3 )); then
    echo "usage: $0 <clean-upstream-source> <openwrt-patches-dir> <report.md>" >&2
    exit 2
fi
source_tree=$(realpath "$1")
patch_dir=$(realpath "$2")
report=$3
[[ -d "$source_tree/.git" && -d "$patch_dir" ]] || {
    echo "Missing source git worktree or patch directory" >&2
    exit 1
}
shopt -s nullglob
patches=("$patch_dir"/*.patch)
if (( ${#patches[@]} != 30 )); then
    echo "Expected exactly 30 UWE5622 driver patches, got ${#patches[@]}" >&2
    exit 1
fi
mkdir -p "$(dirname "$report")"
errors_file="$(dirname "$report")/uwe5622-patch-conflicts.txt"
: > "$errors_file"
cat > "$report" <<'EOF'
# UWE5622 patch applicability audit

This is a **static** cumulative `git apply` check against the pinned upstream
source. It does **not** compile a module, verify firmware behavior, or prove
compatibility with the kernel installed on Orange Pi Zero 3.

`apply` means the patch can be applied in series to the *test worktree*;
`reverse` means the patch text already matches that worktree; `conflict`
means the current sequence cannot apply. An earlier conflict may cause later
conflicts. No kernel modules or firmware are installed.

| Patch | Selection | Result | Files |
|---|---|---|---|
EOF
applied=0
reverse=0
conflicts=0
skipped=0
for patch in "${patches[@]}"; do
    file=${patch##*/}
    id=${file%%-*}
    selection=review
    case "$id" in
        010|080) selection=openwrt-cfg80211; result=skip ;;
        110) selection=openwrt-lean; result=skip ;;
        020) selection=optional-build-flag ;;
        030|070|130|160|190|220|250|310|330) selection=stability ;;
        180|200|290) selection=ap-sta ;;
        *) selection=diagnostics ;;
    esac
    targets=$(sed -n -e 's|^+++ b/||p' "$patch" | paste -sd ',' -)
    if [[ -z "$targets" ]]; then
        result=malformed
        ((conflicts+=1))
    elif [[ "$result" == skip ]]; then
        ((skipped+=1))
    elif git -C "$source_tree" apply --check --recount -- "$patch" >/dev/null 2>&1; then
        if git -C "$source_tree" apply --recount -- "$patch"; then
            result=apply
            ((applied+=1))
        else
            result=conflict
            ((conflicts+=1))
        fi
    elif git -C "$source_tree" apply --reverse --check --recount -- "$patch" >/dev/null 2>&1; then
        result=reverse
        ((reverse+=1))
    else
        result=conflict
        ((conflicts+=1))
        {
            printf "\\n--- %s ---\\n" "$file"
            git -C "$source_tree" apply --check --recount -- "$patch" 2>&1 || :
        } >> "$errors_file"
    fi
    # shellcheck disable=SC2016 # Markdown backticks are literal; no shell interpolation intended.
    printf '| `%s` | %s | **%s** | `%s` |\n' "$file" "$selection" "$result" "$targets" >> "$report"
    result=
done
{
    echo
    echo "## Summary"
    echo
    printf 'Applied in audit worktree: **%d**, already matched: **%d**, conflicts: **%d**, OpenWrt-only skipped: **%d**.\n' "$applied" "$reverse" "$conflicts" "$skipped"
    echo
    echo "**Never install the resulting source tree or modules based on this audit alone.**"
    echo
    echo "Individual conflict locations are in the downloadable conflict log."
} >> "$report"
echo "Patches: applied=$applied reverse=$reverse conflicts=$conflicts skipped=$skipped"
cat "$report"
printf "\\nPatch conflict locations:\\n"
cat "$errors_file"
