#!/usr/bin/env bash
# Links bin/omaupdateimpact into ~/.local/bin. With --uninstall, removes that link.
set -euo pipefail

program="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/bin/omaupdateimpact"
folder="$HOME/.local/bin"
link="$folder/omaupdateimpact"

is_own_link() {
  [[ -L "$link" && "$(readlink -f "$link")" == "$program" ]]
}

# -L as well, since -e is false for a broken link.
leave_anything_else() {
  if [[ -e "$link" || -L "$link" ]]; then
    echo "$link isn't a link to this checkout, so it was left alone." >&2
    exit 1
  fi
}

install_link() {
  # This stops an old Python here, with the command's own one line.
  local version
  version="$("$program" --version)"
  if is_own_link; then
    echo "$version is already installed at $link."
    return
  fi
  leave_anything_else
  mkdir -p "$folder"
  ln -sT -- "$program" "$link"
  echo "Installed $version at $link."
  case ":$PATH:" in
  *":$folder:"*) ;;
  *) echo "$folder isn't on your PATH, so add it to run omaupdateimpact by name." ;;
  esac
}

uninstall() {
  if is_own_link; then
    rm -- "$link"
    echo "Removed $link."
  else
    leave_anything_else
    echo "$link isn't there, so there was nothing to remove."
  fi
  local cache="${XDG_CACHE_HOME:-$HOME/.cache}/omaupdateimpact"
  if [[ -e "$cache" ]]; then
    echo "The cache is still at $cache. To delete it: rm -rf \"$cache\""
  else
    echo "Nothing is left behind."
  fi
}

case "$*" in
"") install_link ;;
--uninstall) uninstall ;;
*)
  echo "Usage: install.sh [--uninstall]" >&2
  exit 2
  ;;
esac
