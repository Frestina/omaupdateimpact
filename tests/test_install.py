import os
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


class Install(unittest.TestCase):
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
