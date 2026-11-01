"""The terminal recording in docs/demo.svg.

Run it from the repo with python3 -m tests.demo to record it again. The real command
runs in a pseudo-terminal, on the fictional home and the trimmed releases, so the
recording is what it prints. Stubs answer for this machine. The animation is SVG, so
GitHub plays it and the text can be searched.
"""

import html
import os
import pty
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests/fixtures"
OUTPUT = ROOT / "docs/demo.svg"
COMMAND = "omaupdateimpact v4.5.0-rc2"
PACKAGES = "dua-cli dust t3code-bin tensaku fictional-editor"

CODE = re.compile(r"\033\[([\d;]+)m")
CHAR_WIDTH = 8.6
LINE_HEIGHT = 18
PADDING = 16
COLUMNS = 88
BACKGROUND = "#1a1b26"
TEXT = "#c0caf5"
GREEN = "#9ece6a"
COLOURS = {"1": "#ffffff", "1;31": "#f7768e", "1;32": GREEN, "1;33": "#e0af68"}

STYLE = f"""
text {{ font: 14px ui-monospace, Menlo, Consolas, "DejaVu Sans Mono", monospace; fill: {TEXT}; white-space: pre; }}
@media (prefers-reduced-motion: no-preference) {{
  #command {{ animation: type 20s infinite; }}
  #report {{ animation: show 20s infinite; }}
}}
@keyframes type {{
  0%, 3% {{ transform: translateX(0); animation-timing-function: steps({len(COMMAND)}, end); }}
  12%, 100% {{ transform: translateX({len(COMMAND) * CHAR_WIDTH}px); }}
}}
@keyframes show {{ 0%, 14% {{ opacity: 0; }} 15%, 100% {{ opacity: 1; }} }}
"""


def stub(folder, name, body):
    path = folder / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def recorded():
    """What the command prints on a terminal, colours included."""
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        stubs = base / "stubs"
        stubs.mkdir()
        (stubs / "python3").symlink_to(sys.executable)
        (stubs / "cat").symlink_to(shutil.which("cat"))
        (stubs / "omaupdateimpact").symlink_to(ROOT / "bin/omaupdateimpact")
        stub(stubs, "omarchy-version", "echo 4.0.6-1")
        stub(stubs, "omarchy-version-channel", "echo rc")
        stub(stubs, "pacman", f"printf '%s\\n' {PACKAGES}")
        stub(stubs, "qmllint", f"""
            cd -P "$2/qs" || exit 1
            case "$PWD" in
            *v4.5.0-rc2*) cat "{FIXTURES}/qmllint-6.12.0/release.txt" ;;
            *) cat "{FIXTURES}/qmllint-6.12.0/current.txt" ;;
            esac
        """)
        shutil.copytree(FIXTURES / "releases/v4.5.0-rc2", base / "cache/omaupdateimpact/v4.5.0-rc2")
        env = {
            "PATH": str(stubs),
            "HOME": str(FIXTURES / "home"),
            "XDG_CACHE_HOME": str(base / "cache"),
            "OMARCHY_PATH": str(FIXTURES / "releases/v4.0.6"),
        }
        parent, child = pty.openpty()
        process = subprocess.Popen(COMMAND.split(), env=env, stdin=subprocess.DEVNULL, stdout=child, stderr=child)
        os.close(child)
        output = b""
        try:
            while data := os.read(parent, 65536):
                output += data
        except OSError:  # A pseudo-terminal ends this way once the command has gone.
            pass
        os.close(parent)
        process.wait(timeout=60)
    return output.decode().replace("\r\n", "\n")


def plain(text):
    return CODE.sub("", text)


def spans(line, code):
    """A line as SVG text, and the colour still on at its end."""
    parts = CODE.split(line)
    out = ""
    for index, part in enumerate(parts):
        if index % 2:
            code = part
        elif part and code in COLOURS:
            out += f'<tspan font-weight="bold" fill="{COLOURS[code]}">{html.escape(part, quote=False)}</tspan>'
        elif part:
            out += html.escape(part, quote=False)
    return out, code


def svg(text):
    lines = text.rstrip("\n").split("\n")
    width = round(COLUMNS * CHAR_WIDTH + 2 * PADDING)
    height = (len(lines) + 1) * LINE_HEIGHT + 2 * PADDING
    y = PADDING + LINE_HEIGHT - 4
    prompt_width = 2 * CHAR_WIDTH
    label = f"A terminal running {COMMAND} on a made-up machine. The same report is at the top of the README."
    size = f'viewBox="0 0 {width} {height}" width="{width}" height="{height}"'
    cover = f'x="{PADDING + prompt_width}" y="{y - 14}" width="{len(COMMAND) * CHAR_WIDTH + 2}" height="{LINE_HEIGHT}"'
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" {size} role="img" aria-label="{label}">',
        f"<style>{STYLE}</style>",
        f'<rect width="{width}" height="{height}" rx="8" fill="{BACKGROUND}"/>',
        f'<text x="{PADDING}" y="{y}" xml:space="preserve"><tspan fill="{GREEN}">$ </tspan>{COMMAND}</text>',
        f'<rect id="command" {cover} fill="{BACKGROUND}"/>',
        '<g id="report">',
    ]
    code = "0"
    for row, line in enumerate(lines, start=1):
        content, code = spans(line, code)
        if content:
            out.append(f'<text x="{PADDING}" y="{y + row * LINE_HEIGHT}" xml:space="preserve">{content}</text>')
    out += ["</g>", "</svg>", ""]
    return "\n".join(out)


def main():
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(svg(recorded()))


if __name__ == "__main__":
    main()
