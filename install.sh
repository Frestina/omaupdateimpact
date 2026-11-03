#!/usr/bin/env bash
# Links bin/omaupdateimpact into ~/.local/bin. With --menu, also adds a row to the
# Omarchy menu. With --uninstall, removes the link and that row.
set -euo pipefail

program="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/bin/omaupdateimpact"
folder="$HOME/.local/bin"
link="$folder/omaupdateimpact"
# Omarchy's menu reads this path under HOME, not under XDG_CONFIG_HOME.
menu_file="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
omarchy_menu="${OMARCHY_PATH:-$HOME/.local/share/omarchy}/default/omarchy/omarchy-menu.jsonc"

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

# Adds (add) or removes (remove) the marked block in the menu file, and nothing else.
# The file is read the way Omarchy reads it: comments on their own lines and
# trailing commas are dropped, then it is parsed as JSON. Exit 1 leaves it alone.
edit_menu() {
  python3 -I - "$1" "$menu_file" <<'PY'
import json
import os
import re
import shutil
import sys
import tempfile

action, path = sys.argv[1], sys.argv[2]
ID = "update.omaupdateimpact"
ROW = {
    "icon": "",
    "label": "Omarchy Impact",
    "description": "What the next Omarchy update would change on this machine",
    "action": "omarchy-launch-floating-terminal-with-presentation omaupdateimpact",
}
BEGIN = "// omaupdateimpact: begin. ./install.sh --uninstall removes this block."
END = "// omaupdateimpact: end"
BLOCK = "\n  " + BEGIN + "\n  " + json.dumps(ID) + ": " + json.dumps(ROW, separators=(",", ":")) + ",\n  " + END
FOUND = re.compile(r"\n[ \t]*// omaupdateimpact: begin\b[^\n]*\n.*?\n[ \t]*// omaupdateimpact: end\b[^\n]*", re.S)


def left_alone(why):
    sys.stderr.write(path + " " + why + ", so it was left alone.\n")
    sys.exit(1)


def rows(text):
    """The rows Omarchy's MenuModel.js would read, or None where it reads none."""
    text = re.sub(r"^\s*//[^\n]*(\n|$)", "", text, flags=re.MULTILINE)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    items = parsed.get("items")
    return items if isinstance(items, dict) else parsed


def opening_brace(text):
    offset = 0
    for line in text.splitlines(True):
        stripped = line.strip()
        if stripped and not stripped.startswith("//"):
            return offset + line.index("{") if stripped.startswith("{") else None
        offset += len(line)
    return None


def others(menu):
    return {key: value for key, value in menu.items() if key != ID}


def write(text):
    real = os.path.realpath(path)
    folder = os.path.dirname(real)
    os.makedirs(folder, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".omaupdateimpact-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as out:
            out.write(text)
        if os.path.exists(real):
            shutil.copymode(real, temporary)
        else:
            mask = os.umask(0)
            os.umask(mask)
            os.chmod(temporary, 0o666 & ~mask)
        os.replace(temporary, real)
    except BaseException:
        os.unlink(temporary)
        raise


try:
    with open(path, encoding="utf-8", newline="") as source:
        text = source.read()
except FileNotFoundError:
    text = None
except (OSError, UnicodeDecodeError) as error:
    left_alone("couldn't be read (" + str(error) + ")")

if action == "remove":
    if text is None:
        sys.exit(0)
    found = FOUND.findall(text)
    if not found:
        if "// omaupdateimpact: " in text:
            left_alone("has an omaupdateimpact block without its two marks")
        sys.exit(0)
    write(FOUND.sub("", text))
    print("Removed the menu row from " + path + ".")
    sys.exit(0)

before = rows(text or "")
if before is None:
    left_alone("isn't a menu Omarchy can read")
found = list(FOUND.finditer(text or ""))
if len(found) > 1:
    left_alone("has more than one omaupdateimpact block")
if found:
    after = text[: found[0].start()] + BLOCK + text[found[0].end() :]
    if after == text:
        print("The menu row is already in " + path + ".")
        sys.exit(0)
    done = "Updated the menu row in " + path + "."
elif text is not None and "// omaupdateimpact: " in text:
    left_alone("has an omaupdateimpact block without its two marks")
else:
    brace = opening_brace(text or "")
    if brace is not None:
        rest = text[brace + 1 :]
        # The end mark is a comment to the end of its line, so it needs a line of its own.
        after = text[: brace + 1] + BLOCK + ("" if re.match(r"[ \t]*(\r?\n|$)", rest) else "\n") + rest
    else:
        # Nothing but comments, or no file: the rows get an object of their own.
        lead = text or ""
        if lead and not lead.endswith("\n"):
            lead += "\n"
        after = lead + "{" + BLOCK + "\n}\n"
    done = "Added an Omarchy Impact row to the Update menu, in " + path + "."
menu = rows(after)
if menu is None or menu.get(ID) != ROW or others(menu) != others(before):
    left_alone("wouldn't show the row as written")
write(after)
print(done)
PY
}

# Before the link, so a machine without this menu gets neither.
check_omarchy_menu() {
  if [[ ! -f "$omarchy_menu" ]]; then
    echo "This Omarchy has no menu that reads $menu_file, so nothing was installed." >&2
    exit 1
  fi
}

uninstall() {
  # The row first, so a link that is left alone doesn't keep it.
  local status=0
  edit_menu remove || status=1
  if is_own_link; then
    rm -- "$link"
    echo "Removed $link."
  else
    leave_anything_else
    echo "$link isn't there, so there was nothing to remove."
  fi
  local cache="${XDG_CACHE_HOME:-$HOME/.cache}/omaupdateimpact"
  local config="${XDG_CONFIG_HOME:-$HOME/.config}/omaupdateimpact"
  local left=""
  if [[ -e "$cache" ]]; then
    echo "The cache is still at $cache. To delete it: rm -rf \"$cache\""
    left=yes
  fi
  # Only --ack writes here, so the folder holds the reviewed file, or once did.
  if [[ -e "$config" ]]; then
    echo "Your reviewed findings are still at $config/reviewed. To delete them: rm -rf \"$config\""
    left=yes
  fi
  if [[ -z "$left" && "$status" == 0 ]]; then
    echo "Nothing is left behind."
  fi
  return "$status"
}

case "$*" in
"") install_link ;;
--menu)
  check_omarchy_menu
  install_link
  edit_menu add
  ;;
--uninstall) uninstall ;;
*)
  echo "Usage: install.sh [--menu | --uninstall]" >&2
  exit 2
  ;;
esac
