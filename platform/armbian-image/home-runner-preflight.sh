#!/usr/bin/env bash
# Read-only self-hosted Armbian build readiness check.
set -euo pipefail
TARGET=${1:-"$HOME"}
[[ -d "$TARGET" ]] || { echo "NOT READY: workspace missing: $TARGET" >&2; exit 2; }
TARGET=$(realpath "$TARGET")
echo "Runner: ${RUNNER_NAME:-manual} / ${RUNNER_OS:-$(uname -s)} / $(uname -m)"
echo "Workspace: $TARGET"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo "NOT READY: use Linux/x86_64 (native or WSL2), not Windows runner" >&2; exit 1;
}
case "$TARGET" in /mnt/[a-z]|/mnt/[a-z]/*)
  echo "NOT READY: use Linux filesystem, not /mnt/c or another Windows drive" >&2; exit 1;;
esac
type=$(findmnt -n -o FSTYPE -T "$TARGET" 2>/dev/null || echo unknown)
case "$type" in drvfs|9p|cifs|smb3|fuseblk)
  echo "NOT READY: workspace filesystem is $type" >&2; exit 1;;
esac
mem_kib=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)
available_kib=$(df -Pk "$TARGET" | awk 'NR==2{print $4}')
echo "Linux RAM: $((mem_kib/1024/1024)) GiB"
echo "Free workspace disk: $((available_kib/1024/1024)) GiB"
echo "Workspace FS: $type"
(( mem_kib >= 8*1024*1024 )) || {
  echo "NOT READY: Armbian needs at least 8 GiB of assigned Linux RAM" >&2; exit 1;
}
(( available_kib >= 50*1024*1024 )) || {
  echo "NOT READY: Armbian needs at least 50 GiB free at build destination" >&2; exit 1;
}
for cmd in git bash tar patch make realpath docker timeout sudo; do
  command -v "$cmd" >/dev/null || { echo "NOT READY: missing $cmd" >&2; exit 1; }
done
echo "Checking Docker daemon (timeout 20s)"
timeout 20s docker info --format 'Docker version={{.ServerVersion}} Root={{.DockerRootDir}}' || {
  echo "NOT READY: Docker daemon unavailable in Linux/WSL2" >&2; exit 1;
}
sudo -n true >/dev/null 2>&1 || {
  echo "NOT READY: passwordless sudo is required for the unattended runner" >&2; exit 1;
}
echo "READY for experimental image build."
echo "In WSL2, ALSO verify >=50 GiB free on physical Windows disk."
