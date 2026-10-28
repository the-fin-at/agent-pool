#!/bin/sh
# Install built native artifacts. State/auth directories are never touched.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
bin_dir=${AGENT_FLEET_BIN_DIR:-"$HOME/.local/bin"}
app_dir=${AGENT_FLEET_APP_DIR:-"$HOME/Applications"}
replace=false
with_app=false
for arg in "$@"; do
  case "$arg" in
    --replace) replace=true ;;
    --desktop) with_app=true ;;
    *) echo "Usage: $0 [--replace] [--desktop]" >&2; exit 2 ;;
  esac
done
source_bin="$root/target/release/agent-fleet"
[ -x "$source_bin" ] || { echo 'Build first: cargo build -p fleet-cli --release --locked' >&2; exit 1; }
source_app="$root/target/release/bundle/macos/Agent Fleet.app"
if "$with_app"; then
  [ "$(uname -s)" = Darwin ] || { echo '--desktop requires macOS; use the native installer on Windows.' >&2; exit 1; }
  [ -d "$source_app" ] || { echo 'Build first: cd desktop && npm ci && npm run tauri build' >&2; exit 1; }
fi
# Preflight all destinations before changing any of them.
for destination in "$bin_dir/agent-fleet"; do
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    "$replace" || { echo "Already installed: $destination. Inspect it, then use --replace to keep a backup." >&2; exit 1; }
  fi
done
if "$with_app" && [ -e "$app_dir/Agent Fleet.app" ] && ! "$replace"; then
  echo 'Desktop already installed; inspect it, then use --replace to keep a backup.' >&2; exit 1
fi
stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
mkdir -p "$bin_dir"
if [ -e "$bin_dir/agent-fleet" ] || [ -L "$bin_dir/agent-fleet" ]; then
  mv "$bin_dir/agent-fleet" "$bin_dir/agent-fleet.backup-$stamp"
fi
cp "$source_bin" "$bin_dir/agent-fleet"
chmod 755 "$bin_dir/agent-fleet"
if "$with_app"; then
  mkdir -p "$app_dir"
  if [ -e "$app_dir/Agent Fleet.app" ]; then mv "$app_dir/Agent Fleet.app" "$app_dir/Agent Fleet.backup-$stamp.app"; fi
  ditto "$source_app" "$app_dir/Agent Fleet.app"
fi
"$bin_dir/agent-fleet" --version
printf 'Installed native CLI: %s\n' "$bin_dir/agent-fleet"
