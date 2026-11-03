import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.resolve()
INSTALL = ROOT / "install.sh"
COMMAND = ROOT / "bin/omaupdateimpact"


class Home(unittest.TestCase):
    """Runs the real script. HOME is a folder of its own, with a space in it."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "a home"
        self.home.mkdir()
        self.folder = self.home / ".local/bin"
        self.link = self.folder / "omaupdateimpact"
        self.cache = self.home / ".cache/omaupdateimpact"
        # Nothing from the developer's PATH, where python3 can be a shim that fails
        # under a made-up HOME. This Python first, so each Python CI lists is the one tested.
        self.without_folder = f"{Path(sys.executable).parent}:/usr/bin:/bin"
        self.path = f"{self.folder}:{self.without_folder}"

    def run_script(self, *args, script=INSTALL, **env):
        env = {"PATH": self.path, "HOME": str(self.home), **env}
        return subprocess.run([script, *args], env=env, capture_output=True, text=True, timeout=60, check=False)

    def assert_exit(self, result, code):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)

    def assert_left_alone(self, result):
        self.assert_exit(result, 1)
        self.assertEqual(result.stderr, f"{self.link} isn't a link to this checkout, so it was left alone.\n")

    def everything_in_home(self):
        return sorted(str(path.relative_to(self.home)) for path in self.home.rglob("*"))


class Install(Home):
    def test_it_links_the_command(self):
        result = self.run_script()
        self.assert_exit(result, 0)
        self.assertTrue(self.link.is_symlink())
        self.assertEqual(self.link.resolve(), COMMAND)
        self.assertIn(f"at {self.link}.", result.stdout)
        ran = subprocess.run(
            [self.link, "--version"], env={"PATH": self.path}, capture_output=True, text=True, timeout=60, check=False
        )
        self.assert_exit(ran, 0)
        self.assertTrue(ran.stdout.startswith("omaupdateimpact "))

    def test_installing_twice_is_harmless(self):
        self.assert_exit(self.run_script(), 0)
        made = self.link.lstat()
        result = self.run_script()
        self.assert_exit(result, 0)
        self.assertIn("already installed", result.stdout)
        self.assertEqual(self.link.lstat().st_ino, made.st_ino)

    def test_a_regular_file_is_left_alone(self):
        self.folder.mkdir(parents=True)
        self.link.write_text("mine\n")
        for args in ((), ("--uninstall",)):
            self.assert_left_alone(self.run_script(*args))
            self.assertEqual(self.link.read_text(), "mine\n")
            self.assertFalse(self.link.is_symlink())

    def test_a_link_to_something_else_is_left_alone(self):
        self.folder.mkdir(parents=True)
        other = self.base / "other"
        other.write_text("mine\n")
        self.link.symlink_to(other)
        for args in ((), ("--uninstall",)):
            self.assert_left_alone(self.run_script(*args))
            self.assertEqual(self.link.readlink(), other)

    def test_a_broken_link_is_left_alone(self):
        self.folder.mkdir(parents=True)
        self.link.symlink_to(self.base / "gone/omaupdateimpact")
        for args in ((), ("--uninstall",)):
            self.assert_left_alone(self.run_script(*args))
            self.assertTrue(self.link.is_symlink())

    def test_a_folder_is_left_alone(self):
        self.link.mkdir(parents=True)
        self.assert_left_alone(self.run_script())
        self.assertEqual(list(self.link.iterdir()), [])

    def test_a_link_from_another_checkout_is_left_alone(self):
        other = self.base / "other checkout"
        (other / "bin").mkdir(parents=True)
        shutil.copy(INSTALL, other)
        shutil.copy(COMMAND, other / "bin")
        self.assert_exit(self.run_script(), 0)
        self.assert_left_alone(self.run_script(script=other / "install.sh"))
        self.assert_left_alone(self.run_script("--uninstall", script=other / "install.sh"))
        self.assertEqual(self.link.resolve(), COMMAND)

    def test_an_old_python_stops_the_install(self):
        stubs = self.base / "stubs"
        stubs.mkdir()
        python = stubs / "python3"
        python.write_text("#!/bin/sh\necho 'too old' >&2\nexit 2\n")
        python.chmod(0o755)
        result = self.run_script(PATH=f"{stubs}:{self.path}")
        self.assert_exit(result, 2)
        self.assertEqual(result.stderr, "too old\n")
        self.assertEqual(self.everything_in_home(), [])

    def test_it_says_when_the_folder_is_not_on_path(self):
        result = self.run_script(PATH=self.without_folder)
        self.assert_exit(result, 0)
        self.assertIn(f"{self.folder} isn't on your PATH", result.stdout)
        self.assertNotIn("PATH", self.run_script("--uninstall").stdout)
        self.assertNotIn("PATH", self.run_script().stdout)

    def test_uninstall_leaves_only_the_cache_and_says_so(self):
        self.assert_exit(self.run_script(), 0)
        self.cache.mkdir(parents=True)
        (self.cache / "v4.5.0").write_text("kept\n")
        result = self.run_script("--uninstall")
        self.assert_exit(result, 0)
        self.assertIn(f"Removed {self.link}.", result.stdout)
        self.assertIn(f"The cache is still at {self.cache}.", result.stdout)
        self.assertEqual((self.cache / "v4.5.0").read_text(), "kept\n")
        self.assertEqual(
            self.everything_in_home(),
            [".cache", ".cache/omaupdateimpact", ".cache/omaupdateimpact/v4.5.0", ".local", ".local/bin"],
        )

    def test_uninstall_finds_the_cache_where_the_command_puts_it(self):
        cache = self.base / "elsewhere/omaupdateimpact"
        cache.mkdir(parents=True)
        result = self.run_script("--uninstall", XDG_CACHE_HOME=str(cache.parent))
        self.assertIn(f"The cache is still at {cache}.", result.stdout)
        self.cache.mkdir(parents=True)
        result = self.run_script("--uninstall", XDG_CACHE_HOME="")
        self.assertIn(f"The cache is still at {self.cache}.", result.stdout)

    def test_uninstall_leaves_the_reviewed_findings_and_says_so(self):
        self.assert_exit(self.run_script(), 0)
        config = self.home / ".config/omaupdateimpact"
        config.mkdir(parents=True)
        (config / "reviewed").write_text("v4.5.0 3344d3a A finding\n")
        result = self.run_script("--uninstall")
        self.assert_exit(result, 0)
        self.assertIn(f"Your reviewed findings are still at {config}/reviewed.", result.stdout)
        self.assertNotIn("Nothing is left behind.", result.stdout)
        self.assertEqual((config / "reviewed").read_text(), "v4.5.0 3344d3a A finding\n")
        elsewhere = self.base / "elsewhere/omaupdateimpact"
        elsewhere.mkdir(parents=True)
        result = self.run_script("--uninstall", XDG_CONFIG_HOME=str(elsewhere.parent))
        self.assertIn(f"Your reviewed findings are still at {elsewhere}/reviewed.", result.stdout)

    def test_uninstall_says_when_nothing_is_left(self):
        self.assert_exit(self.run_script(), 0)
        result = self.run_script("--uninstall")
        self.assert_exit(result, 0)
        self.assertIn("Nothing is left behind.", result.stdout)

    def test_uninstalling_twice_is_harmless(self):
        self.assert_exit(self.run_script(), 0)
        self.assert_exit(self.run_script("--uninstall"), 0)
        result = self.run_script("--uninstall")
        self.assert_exit(result, 0)
        self.assertIn("nothing to remove", result.stdout)

    def test_anything_else_is_bad_usage(self):
        for args in (("--nope",), ("--uninstall", "extra")):
            result = self.run_script(*args)
            self.assert_exit(result, 2)
            self.assertIn("Usage", result.stderr)
        self.assertEqual(self.everything_in_home(), [])


# A user's menu file, as Omarchy's template leaves it after a few edits.
MENU = """{
  // Extend the Omarchy menu with JSONC.
  //
  // "personal.notes": {"icon":"","label":"Notes","action":"omarchy-launch-editor ~/notes"},
  "personal": {"icon":"","label":"Personal"},
  "personal.diary": {"icon":"󰎞","label":"Diary","action":"omarchy-launch-editor ~/diary.md"},
}
"""
ROW_ID = "update.omaupdateimpact"
BLOCK = (
    "\n  // omaupdateimpact: begin. ./install.sh --uninstall removes this block.\n"
    '  "update.omaupdateimpact": {"icon":"\\uf002","label":"Omarchy Impact",'
    '"description":"What the next Omarchy update would change on this machine",'
    '"action":"omarchy-launch-floating-terminal-with-presentation omaupdateimpact"},\n'
    "  // omaupdateimpact: end"
)


def menu_rows(text):
    """The rows Omarchy's menu reads from the file, as its MenuModel.js does."""
    text = re.sub(r"^\s*//[^\n]*(\n|$)", "", text, flags=re.MULTILINE)
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


class MenuRow(Home):
    """install.sh --menu, against a fictional Omarchy whose menu reads the user's file."""

    def setUp(self):
        super().setUp()
        self.omarchy = self.base / "omarchy"
        (self.omarchy / "default/omarchy").mkdir(parents=True)
        (self.omarchy / "default/omarchy/omarchy-menu.jsonc").write_text('{\n  "update": {"label":"Update"},\n}\n')
        self.menu = self.home / ".config/omarchy/extensions/omarchy-menu.jsonc"
        self.menu.parent.mkdir(parents=True)

    def run_script(self, *args, script=INSTALL, **env):
        return super().run_script(*args, script=script, **{"OMARCHY_PATH": str(self.omarchy), **env})

    def test_the_row_runs_the_report_in_a_terminal(self):
        self.menu.write_text(MENU)
        result = self.run_script("--menu")
        self.assert_exit(result, 0)
        self.assertIn(f"Added an Omarchy Impact row to the Update menu, in {self.menu}.", result.stdout)
        self.assertEqual(self.link.resolve(), COMMAND)
        rows = menu_rows(self.menu.read_text())
        self.assertEqual(rows[ROW_ID]["label"], "Omarchy Impact")
        self.assertEqual(rows[ROW_ID]["icon"], "")
        self.assertEqual(sorted(rows), ["personal", "personal.diary", ROW_ID])
        # Omarchy runs the action with bash -lc, and its launcher hands the rest to a
        # terminal. This one records the command the terminal would get, and where
        # the shell finds it.
        stubs = self.base / "stubs"
        stubs.mkdir()
        launcher = stubs / "omarchy-launch-floating-terminal-with-presentation"
        launcher.write_text('#!/bin/bash\nprintf "%s\\n" "$*" "$(command -v "$1")"\n')
        launcher.chmod(0o755)
        ran = subprocess.run(
            ["bash", "-c", rows[ROW_ID]["action"]],
            env={"PATH": f"{stubs}:{self.path}"},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assert_exit(ran, 0)
        self.assertEqual(ran.stdout.splitlines(), ["omaupdateimpact", str(self.link)])

    def test_only_the_block_is_added_and_uninstall_takes_only_it(self):
        self.menu.write_text(MENU)
        self.assert_exit(self.run_script("--menu"), 0)
        self.assertEqual(self.menu.read_text(), "{" + BLOCK + MENU[1:])
        result = self.run_script("--uninstall")
        self.assert_exit(result, 0)
        self.assertIn(f"Removed the menu row from {self.menu}.", result.stdout)
        self.assertIn(f"Removed {self.link}.", result.stdout)
        self.assertIn("Nothing is left behind.", result.stdout)
        self.assertEqual(self.menu.read_text(), MENU)

    def test_running_it_twice_adds_one_row(self):
        self.menu.write_text(MENU)
        self.assert_exit(self.run_script("--menu"), 0)
        once = self.menu.read_bytes()
        result = self.run_script("--menu")
        self.assert_exit(result, 0)
        self.assertIn(f"The menu row is already in {self.menu}.", result.stdout)
        self.assertEqual(self.menu.read_bytes(), once)
        self.assertEqual(once.decode().count(ROW_ID), 1)

    def test_an_edited_block_is_put_back_in_place(self):
        self.menu.write_text(MENU.replace("{\n", "{" + BLOCK.replace("Omarchy Impact", "Mine") + "\n", 1))
        result = self.run_script("--menu")
        self.assert_exit(result, 0)
        self.assertIn(f"Updated the menu row in {self.menu}.", result.stdout)
        self.assertEqual(self.menu.read_text(), "{" + BLOCK + MENU[1:])

    def test_a_missing_file_gets_an_object_of_its_own(self):
        self.menu.parent.rmdir()
        self.assert_exit(self.run_script("--menu"), 0)
        self.assertEqual(self.menu.read_text(), "{" + BLOCK + "\n}\n")
        self.assertEqual(self.menu.stat().st_mode & 0o777, 0o644 & ~current_umask())
        self.assert_exit(self.run_script("--uninstall"), 0)
        self.assertEqual(self.menu.read_text(), "{\n}\n")

    def test_a_file_of_only_comments_keeps_them(self):
        self.menu.write_text("// Rows of mine go here.")
        self.assert_exit(self.run_script("--menu"), 0)
        self.assertEqual(self.menu.read_text(), "// Rows of mine go here.\n{" + BLOCK + "\n}\n")
        self.assertIn(ROW_ID, menu_rows(self.menu.read_text()))

    def test_a_menu_on_one_line(self):
        self.menu.write_text('{"personal": {"label":"Personal"}}')
        self.assert_exit(self.run_script("--menu"), 0)
        self.assertEqual(sorted(menu_rows(self.menu.read_text())), ["personal", ROW_ID])
        self.assert_exit(self.run_script("--uninstall"), 0)
        self.assertEqual(self.menu.read_text(), '{\n"personal": {"label":"Personal"}}')

    def test_a_linked_file_stays_a_link_and_keeps_its_mode(self):
        dotfiles = self.base / "dotfiles/omarchy-menu.jsonc"
        dotfiles.parent.mkdir()
        dotfiles.write_text(MENU)
        dotfiles.chmod(0o600)
        self.menu.symlink_to(dotfiles)
        self.assert_exit(self.run_script("--menu"), 0)
        self.assertTrue(self.menu.is_symlink())
        self.assertEqual(dotfiles.read_text(), "{" + BLOCK + MENU[1:])
        self.assertEqual(dotfiles.stat().st_mode & 0o777, 0o600)
        self.assert_exit(self.run_script("--uninstall"), 0)
        self.assertTrue(self.menu.is_symlink())
        self.assertEqual(dotfiles.read_text(), MENU)
        self.assertEqual(sorted(path.name for path in dotfiles.parent.iterdir()), ["omarchy-menu.jsonc"])

    def test_it_goes_where_omarchy_reads_it_whatever_xdg_says(self):
        elsewhere = self.base / "elsewhere"
        self.assert_exit(self.run_script("--menu", XDG_CONFIG_HOME=str(elsewhere)), 0)
        self.assertIn(ROW_ID, self.menu.read_text())
        self.assertFalse(elsewhere.exists())

    def test_a_menu_omarchy_cant_read_is_left_alone(self):
        for text in (
            '{\n  "personal": {"label":"Personal"}, // an inline comment Omarchy keeps\n}\n',
            '["personal"]\n',
            '{\n  "items": {"personal": {"label":"Personal"}},\n}\n',
            "{\n  // omaupdateimpact: begin. A block whose end was deleted.\n}\n",
        ):
            with self.subTest(text=text):
                self.menu.write_text(text)
                result = self.run_script("--menu")
                self.assert_exit(result, 1)
                self.assertRegex(result.stderr, rf"^{re.escape(str(self.menu))} .*, so it was left alone\.\n$")
                self.assertEqual(self.menu.read_text(), text)
                self.assertEqual(sorted(path.name for path in self.menu.parent.iterdir()), ["omarchy-menu.jsonc"])

    def test_without_omarchys_menu_nothing_is_installed(self):
        (self.omarchy / "default/omarchy/omarchy-menu.jsonc").unlink()
        self.menu.parent.rmdir()
        result = self.run_script("--menu")
        self.assert_exit(result, 1)
        self.assertIn("no menu that reads", result.stderr)
        self.assertEqual(self.everything_in_home(), [".config", ".config/omarchy"])

    def test_a_link_that_is_left_alone_adds_no_row(self):
        self.menu.write_text(MENU)
        self.folder.mkdir(parents=True)
        self.link.write_text("mine\n")
        self.assert_left_alone(self.run_script("--menu"))
        self.assertEqual(self.menu.read_text(), MENU)

    def test_uninstall_without_a_row_says_nothing_of_it(self):
        self.menu.write_text(MENU)
        self.assert_exit(self.run_script(), 0)
        result = self.run_script("--uninstall")
        self.assert_exit(result, 0)
        self.assertNotIn("menu", result.stdout)
        self.assertEqual(self.menu.read_text(), MENU)

    def test_uninstall_leaves_a_broken_block_and_still_removes_the_link(self):
        text = "{\n  // omaupdateimpact: begin. A block whose end was deleted.\n}\n"
        self.menu.write_text(text)
        self.assert_exit(self.run_script(), 0)
        result = self.run_script("--uninstall")
        self.assert_exit(result, 1)
        self.assertEqual(result.stderr, f"{self.menu} has an omaupdateimpact block without its two marks, so it was left alone.\n")
        self.assertEqual(self.menu.read_text(), text)
        self.assertFalse(self.link.is_symlink())
        self.assertNotIn("Nothing is left behind.", result.stdout)


def current_umask():
    mask = os.umask(0)
    os.umask(mask)
    return mask


class InstallUnderABrokenPython(Install):
    """The same tests, with a python3 first on the inherited PATH that only prints an
    error, as a mise shim does under a made-up HOME."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        python = Path(directory.name) / "python3"
        python.write_text("#!/bin/sh\necho 'not this python' >&2\nexit 1\n")
        python.chmod(0o755)
        environ = mock.patch.dict(os.environ, {"PATH": f"{directory.name}:{os.environ['PATH']}"})
        environ.start()
        self.addCleanup(environ.stop)
        super().setUp()
