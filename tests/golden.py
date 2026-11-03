"""The example documents in docs/json.md, and the golden files they match.

Run it from the repo with python3 -m tests.golden to write the golden files again,
then copy them into docs/json.md. The command runs on small fictional trees, with
stubs for this machine and for GitHub, so each example is what it prints.
"""

import contextlib
import io
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from tests.test_omaupdateimpact import impact

ROOT = Path(__file__).parent.parent
GOLDEN = ROOT / "tests/fixtures/json"
DOC = ROOT / "docs/json.md"

INSTALLED = {
    "bin/omarchy-launch-browser": "#!/bin/bash\n",
    "bin/omarchy-sync-notes": "#!/bin/bash\n",
    "default/hypr/bindings.lua": 'o.bind("SUPER + B", "Browser", "omarchy-launch-browser")\n',
    "migrations/1700000000.sh": "true\n",
    "shell/Bar.qml": "Item {}\n",
}
RELEASE = {
    "bin/omarchy-launch-browser": "#!/bin/bash\n",
    "default/hypr/bindings.lua": (
        'o.bind("SUPER + B", "Browser", "omarchy-launch-browser")\n'
        'o.bind("SUPER + M", "Minimize window", "omarchy-window-minimize")\n'
        'o.bind("SUPER + N", "Notifications", "omarchy-notifications")\n'
    ),
    "migrations/1700000000.sh": "true\n",
    "migrations/1700000001.sh": 'echo "Replace Fictional Editor with Fictional Writer"\nomarchy-pkg-drop fictional-editor\n',
    "migrations/1700000002.sh": 'omarchy-pkg-drop "${targets[@]}"\n',
    "migrations/1700000003.sh": "sed -i 's/dark/light/' ~/.config/fictional-app/theme.conf\n",
    "shell/Bar.qml": "Item {}\n",
    impact.NOTES: "## Deprecations\n\n- Replace Fictional Editor with Fictional Writer by @fictional-dev in #101\n",
}
HOME = {
    ".config/hypr/bindings.lua": 'o.bind("SUPER + M", "Music", "fictional-player")\n',
    ".config/fictional-app/theme.conf": "style = dark\n",
    ".local/bin/sync-all": "#!/bin/sh\nomarchy-sync-notes\n",
    ".local/state/omarchy/migrations/1700000000.sh": "",
}
RELEASES = [{"tag_name": "v1.4.0-rc1"}, {"tag_name": "v1.3.0"}, {"tag_name": "v1.2.3"}]


def write(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


def stub(folder, name, body):
    (folder / name).write_text(f"#!/bin/sh\n{body}\n")
    (folder / name).chmod(0o755)


def github(request, timeout):
    """The fictional releases: v1.3.0 is the latest stable, and v1.4.0-rc1 the newest of all."""
    if request.full_url.endswith("/releases/latest"):
        return io.BytesIO(json.dumps(RELEASES[1]).encode())
    return io.BytesIO(json.dumps(RELEASES).encode())


def printed(base, version, *args):
    """What the command prints on stdout with --json."""
    stubs = base / "stubs"
    stubs.mkdir(exist_ok=True)
    stub(stubs, "omarchy-version", f"echo {version}")
    stub(stubs, "omarchy-version-channel", "echo stable")
    stub(stubs, "pacman", "printf '%s\\n' fictional-editor fictional-player")
    environment = {"PATH": str(stubs), "XDG_CACHE_HOME": str(base / "cache"), "OMARCHY_PATH": str(base / "v1.3.0")}
    argv = ["omaupdateimpact", "--json", "--home", str(base / "home"), *args]
    with mock.patch.dict(os.environ, environment), mock.patch("sys.argv", argv), \
            mock.patch.object(impact.urllib.request, "urlopen", github), \
            contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
        impact.main()
    return out.getvalue()


def documents():
    """Each example's name and the document the command prints for it."""
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        installed, release = write(base / "v1.2.3", INSTALLED), write(base / "v1.3.0", RELEASE)
        write(base / "home", HOME)
        return {
            "report": printed(base, "1.2.3-1", "--root", str(installed), "--target", str(release)),
            "no-update": printed(base, "1.3.0-1"),
            "failed": printed(base, "1.2.3-1", "--root", str(installed), "--channel", "edge"),
        }


def main():
    GOLDEN.mkdir(exist_ok=True)
    for name, text in documents().items():
        (GOLDEN / f"{name}.json").write_text(text)


if __name__ == "__main__":
    main()
