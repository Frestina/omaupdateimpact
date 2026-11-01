import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tests.test_omaupdateimpact import QMLLINT_OUTPUT, ProgramCase, impact

COMMAND = Path(__file__).parent.parent / "bin/omaupdateimpact"
FIXTURES = Path(__file__).parent / "fixtures"
HOME = FIXTURES / "home"
OLD = FIXTURES / "releases/v4.0.6"
NEW = FIXTURES / "releases/v4.5.0-rc2"
# A migration v4.5.0-rc2 removes packages in, through an array it can't read.
UNREADABLE_MIGRATION = "1785351479.sh"
NOTHING_LISTENS = "http://127.0.0.1:9"


def files(*roots):
    return {path: path.read_bytes() for root in roots for path in root.rglob("*") if path.is_file()}


def flat(text):
    """Report text with its line wrapping undone. A line can also break after a hyphen."""
    return " ".join(re.sub(r"(?<=\w-)\n\s+", "", text).split())


class RealCommand(unittest.TestCase):
    """Runs the real command on trimmed real releases.

    PATH holds only stubs, so nothing on this machine leaks in, and a proxy that
    nothing listens on stops any request.
    """

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.stubs = self.base / "stubs"
        self.stubs.mkdir()
        (self.stubs / "python3").symlink_to(sys.executable)
        (self.stubs / "cat").symlink_to(shutil.which("cat"))
        self.stub("omarchy-version", "echo 4.0.6-1")
        self.stub("omarchy-version-channel", "echo stable")
        self.packages("fictional-editor")
        self.stub("qmllint", f"""
            cd -P "$2/qs" || exit 1
            case "$PWD" in
            *v4.5.0-rc2*) cat "{QMLLINT_OUTPUT}/release.txt" ;;
            *) cat "{QMLLINT_OUTPUT}/current.txt" ;;
            esac
        """)
        self.cache = self.base / "cache"
        # Nothing in it needs attention, and the migration it can't read has run.
        self.clean_home = self.base / "clean-home"
        (self.clean_home / ".local/state/omarchy/migrations").mkdir(parents=True)
        (self.clean_home / ".local/state/omarchy/migrations" / UNREADABLE_MIGRATION).touch()

    def stub(self, name, body):
        path = self.stubs / name
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)

    def packages(self, *names):
        self.stub("pacman", f"printf '%s\\n' {' '.join(names)}")

    def env(self, **extra):
        return {
            "PATH": str(self.stubs),
            "HOME": str(self.base / "nobody"),
            "XDG_CACHE_HOME": str(self.cache),
            "https_proxy": NOTHING_LISTENS,
            **extra,
        }

    def command(self, *args, **env):
        return subprocess.run(
            [COMMAND, *map(str, args)], env=self.env(**env), capture_output=True, text=True, timeout=60, check=False
        )

    def compare(self, home, *args):
        return self.command("--root", OLD, "--target", NEW, "--home", home, *args)

    def assert_exit(self, result, code):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)

    def assert_no_verdict(self, result, message):
        self.assert_exit(result, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn(message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class ExitCodes(RealCommand):
    def test_nothing_to_worry_about_exits_0(self):
        result = self.compare(self.clean_home)
        self.assert_exit(result, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines()[0], "Omarchy 4.0.6-1 -> v4.5.0-rc2 (stable channel, prerelease). Nothing was changed.")
        self.assertEqual(result.stdout.splitlines()[-1], "Nothing found that needs attention.")
        self.assertNotIn("Needs attention", result.stdout)

    def test_the_release_you_already_have_exits_0(self):
        self.stub("omarchy-version", "echo 4.5.0rc2-1")
        result = self.command("v4.5.0-rc2", OMARCHY_PATH=NEW, HOME=HOME)
        self.assert_exit(result, 0)
        self.assertIn("There is no update.", result.stdout)
        self.assertIn("Couldn't check for newer releases", result.stdout)

    def test_a_clash_exits_1(self):
        result = self.compare(HOME)
        self.assert_exit(result, 1)
        self.assertIn("Needs attention", result.stdout)

    def test_a_removal_it_cant_read_exits_3(self):
        (self.clean_home / ".local/state/omarchy/migrations" / UNREADABLE_MIGRATION).unlink()
        result = self.compare(self.clean_home)
        self.assert_exit(result, 3)
        self.assertIn(f"Couldn't read what migrations/{UNREADABLE_MIGRATION} removes", flat(result.stdout))
        self.assertEqual(result.stdout.splitlines()[-1], "These checks didn't run: packages.")

    def test_a_missing_pacman_exits_3(self):
        (self.stubs / "pacman").unlink()
        result = self.compare(self.clean_home)
        self.assert_exit(result, 3)
        self.assertIn("pacman wasn't available", result.stdout)
        self.assertNotIn("nothing found", result.stdout.lower())

    def test_a_qmllint_killed_by_a_signal_exits_3(self):
        self.stub("qmllint", "kill -TERM $$")
        plugin = self.clean_home / ".config/omarchy/plugins/demo"
        shutil.copytree(HOME / ".config/omarchy/plugins/demo", plugin)
        result = self.compare(self.clean_home)
        self.assert_exit(result, 3)
        self.assertIn("demo couldn't be linted", result.stdout)
        self.assertEqual(result.stdout.splitlines()[-1], "These checks didn't run: plugins.")

    def test_a_bad_option_exits_2(self):
        result = self.command("--no-such-option")
        self.assert_exit(result, 2)
        self.assertIn("usage:", result.stderr)

    def test_a_bad_tag_exits_2(self):
        self.assert_no_verdict(self.compare(self.clean_home, "main"), "isn't a release tag")

    def test_an_unusable_tree_exits_2(self):
        result = self.command("--root", OLD, "--target", self.clean_home, "--home", self.clean_home)
        self.assert_no_verdict(result, "has nothing in bin, default/hypr, migrations, shell")

    def test_a_release_with_no_readable_bindings_exits_2(self):
        target = self.base / "moved"
        shutil.copytree(NEW, target)
        shutil.rmtree(target / "default/hypr/bindings")
        result = self.command("--root", OLD, "--target", target, "--home", self.clean_home)
        self.assert_no_verdict(result, "no readable default bindings")

    def test_a_channel_with_no_tags_exits_2(self):
        self.stub("omarchy-version-channel", "echo edge")
        result = self.command("--root", OLD, "--home", self.clean_home)
        self.assert_no_verdict(result, "the channel is edge")

    def test_a_failed_download_exits_2(self):
        result = self.command("v4.5.0-rc2", "--root", OLD, "--home", self.clean_home)
        self.assert_no_verdict(result, "Couldn't download the release")
        self.assertEqual(list(self.cache.glob("omaupdateimpact/*")), [])

    def test_a_crash_exits_2_on_one_line(self):
        target = self.base / "broken"
        shutil.copytree(NEW, target)
        (target / "default/hypr/bindings/broken.lua").mkdir()
        result = self.command("--root", OLD, "--target", target, "--home", self.clean_home)
        self.assert_no_verdict(result, "Unexpected IsADirectoryError")
        self.assertEqual(len(result.stderr.splitlines()), 1)


class Report(RealCommand):
    """The fictional home against the step from v4.0.6 to v4.5.0-rc2."""

    def setUp(self):
        super().setUp()
        self.packages("dua-cli", "dust", "t3code-bin", "tensaku", "fictional-editor")
        self.result = self.compare(HOME)
        self.output = flat(self.result.stdout)

    def attention(self):
        return flat(self.result.stdout.partition("Needs attention")[2].partition("Worth knowing")[0])

    def test_it_exits_1_and_still_names_what_it_couldnt_read(self):
        self.assert_exit(self.result, 1)
        self.assertEqual(self.result.stderr, "")
        self.assertEqual(self.result.stdout.splitlines()[-1], "These checks didn't run: packages.")

    def test_a_new_default_on_your_key_is_a_clash(self):
        self.assertIn(
            'SUPER + M: your "Music" will clash with the new default "Minimize window to the dock". Both will fire. '
            'Add hl.unbind("SUPER + M") or choose another key.',
            self.attention(),
        )

    def test_a_key_no_default_uses_is_no_clash(self):
        self.assertNotIn("SUPER + F12", self.output)

    def test_a_shortcut_you_turned_off_that_moves_comes_back(self):
        self.assertIn(
            'SUPER + CTRL + T: you turned off "Activity" here, but it moves to SUPER + SHIFT + T, so it comes back.',
            self.attention(),
        )

    def test_removed_packages_you_have_are_named(self):
        self.assertIn("The update will remove dua-cli, which is installed here.", self.attention())
        self.assertIn("The update will remove tensaku, which is installed here.", self.attention())

    def test_a_removal_through_another_release_file_may_happen(self):
        self.assertIn("The update may remove t3code-bin, which is installed here.", self.attention())

    def test_a_migration_already_run_doesnt_count(self):
        self.assertNotIn("dust", self.output)

    def test_every_call_to_a_deleted_command_is_named(self):
        calls = {
            "~/.bashrc": "omarchy-voxtype-remove",
            "~/.config/omarchy/hooks/post-update": "omarchy-voxtype-status",
            "~/.config/systemd/user/nightly-backup.service": "omarchy-system-shutdown",
            "~/.local/bin/end-of-day": "omarchy-system-reboot",
        }
        for file, command in calls.items():
            self.assertIn(f"{file} calls {command}, which the release deletes.", self.attention())

    def test_a_comment_is_no_call(self):
        self.assertNotIn("omarchy-system-logout", self.output)

    def test_a_copy_of_omarchys_own_hook_is_only_a_note(self):
        title = "install-voxtype.hook calls omarchy-voxtype-install, which the release deletes."
        self.assertNotIn(title, self.attention())
        self.assertIn(f"{title} It's Omarchy's own file, unchanged, so there's nothing for you to fix.", self.output)

    def test_a_new_lint_warning_is_a_note(self):
        self.assertNotIn("qmllint", self.attention())
        self.assertIn("demo: 2 new qmllint warnings, such as Demo.qml: Warnings occurred while importing module", self.output)
        self.assertIn("qmllint can't prove a plugin works.", self.output)


class BindHold(RealCommand):
    """v4.5.0-rc2 moved its dictation keys to o.bind_hold, which the first version couldn't read."""

    def test_a_key_moved_to_the_helper_is_not_removed(self):
        result = self.compare(self.clean_home)
        self.assertNotIn("F9", result.stdout)
        self.assertNotIn("Default shortcuts removed", flat(result.stdout))

    def test_a_key_bound_with_the_helper_is_new(self):
        output = flat(self.compare(self.clean_home).stdout)
        self.assertIn('ALT + ALT_R ("Start dictation (push-to-talk) / Stop dictation (push-to-talk)")', output)

    def test_your_key_clashes_with_the_helper(self):
        self.assertIn(
            'ALT + ALT_R: your "Scratchpad" will clash with the new default '
            '"Start dictation (push-to-talk) / Stop dictation (push-to-talk)".',
            flat(self.compare(HOME).stdout),
        )

    def test_the_helper_is_no_limit(self):
        self.assertNotIn("isn't one this tool can read", flat(self.compare(self.clean_home).stdout))


class Promises(RealCommand):
    def test_a_run_changes_nothing(self):
        before = files(HOME, OLD, NEW)
        self.assert_exit(self.compare(HOME), 1)
        self.assertEqual(files(HOME, OLD, NEW), before)
        self.assertFalse(self.cache.exists())
        self.assertFalse((self.base / "nobody").exists())

    def test_a_cached_release_needs_no_network(self):
        shutil.copytree(NEW, self.cache / "omaupdateimpact/v4.5.0-rc2")
        cached = self.command("v4.5.0-rc2", "--root", OLD, "--home", self.clean_home)
        self.assert_exit(cached, 0)
        self.assertEqual(cached.stdout, self.compare(self.clean_home).stdout)

    def test_the_default_trees_and_home_come_from_the_environment(self):
        result = self.command("--target", NEW, OMARCHY_PATH=OLD, HOME=HOME)
        self.assertEqual(result.stdout, self.compare(HOME).stdout)

    def test_the_fictional_home_names_nobody(self):
        for path, data in files(HOME, QMLLINT_OUTPUT).items():
            self.assertNotIn(b"/home/", data, path)


class Handler(BaseHTTPRequestHandler):
    """Answers from server.routes. A method other than GET gets a 501 and fails the test."""

    def do_GET(self):
        self.server.seen.append((self.path, self.headers.get("Authorization")))
        status, headers, body = self.server.routes.get(self.path, (404, {}, b""))
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class LocalDownloads(ProgramCase):
    """fetch_release over real HTTP, on a server here. Only the host in the URL changes."""

    ARCHIVE = "/omacom/omarchy/archive/refs/tags/v4.5.0-rc2.tar.gz"
    CODELOAD = "/codeload/v4.5.0-rc2.tar.gz"
    LATEST = "/api/repos/omacom/omarchy/releases/latest"

    def setUp(self):
        super().setUp()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.routes, server.seen = {}, []
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.routes, self.seen = server.routes, server.seen
        here = f"http://127.0.0.1:{server.server_port}"
        urlopen = urllib.request.urlopen

        def local(request, timeout):
            request.full_url = (
                request.full_url.replace("https://api.github.com", f"{here}/api").replace("https://github.com", here)
            )
            return urlopen(request, timeout=timeout)

        for patcher in [
            mock.patch.object(impact.urllib.request, "urlopen", local),
            mock.patch.dict(os.environ, no_proxy="*"),
            mock.patch.object(impact, "installed_packages", return_value=set()),
        ]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def real_archive(self):
        (self.base / "target").rename(self.base / "small")
        shutil.copytree(NEW, self.base / "target")
        return self.archive()

    def serve(self, body, **headers):
        """GitHub redirects an archive to another host, and doesn't say its size."""
        self.routes[self.ARCHIVE] = (302, {"Location": self.CODELOAD}, b"")
        self.routes[self.CODELOAD] = (200, {k.replace("_", "-"): v for k, v in headers.items()}, body)

    def run_tag(self, *args):
        return self.run_argv("--root", str(OLD), "--home", str(self.home), "--channel", "stable", *args)

    def test_a_download_gives_the_report_of_the_same_release_on_disk(self):
        self.serve(self.real_archive())
        code, out, err = self.run_tag("v4.5.0-rc2")
        self.assertEqual(err, "")
        self.assertEqual([path for path, _ in self.seen], [self.ARCHIVE, self.CODELOAD])
        self.assertEqual((code, out), self.run_tag("--target", str(NEW))[:2])
        self.assertTrue((self.cache / "omaupdateimpact/v4.5.0-rc2/bin").is_dir())

    def test_a_cached_release_isnt_fetched_again(self):
        self.serve(self.real_archive())
        first = self.run_tag("v4.5.0-rc2")
        self.seen.clear()
        self.assertEqual(self.run_tag("v4.5.0-rc2"), first)
        self.assertEqual(self.seen, [])

    def test_an_archive_cut_short_exits_2(self):
        data = self.real_archive()
        self.serve(data[: len(data) // 2])
        self.assert_download_failed(self.run_tag("v4.5.0-rc2"))

    def test_an_archive_shorter_than_it_said_exits_2(self):
        data = self.real_archive()
        self.serve(data[: len(data) // 2], Content_Length=str(len(data)))
        self.assert_download_failed(self.run_tag("v4.5.0-rc2"))

    def test_a_tag_that_isnt_there_exits_2(self):
        self.assert_download_failed(self.run_tag("v4.5.0-rc2"))

    def test_the_rate_limit_is_named(self):
        self.routes[self.ARCHIVE] = (403, {"x-ratelimit-remaining": "0"}, b"")
        result = self.run_tag("v4.5.0-rc2")
        self.assert_download_failed(result)
        self.assertIn("rate limit", result[2])

    def test_a_channel_leads_to_its_release_and_the_token_stays_with_the_api(self):
        self.serve(self.real_archive())
        self.routes[self.LATEST] = (200, {}, json.dumps({"tag_name": "v4.5.0-rc2"}).encode())
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional-token"):
            code = self.run_tag()[0]
        self.assertEqual(code, 3)
        self.assertEqual(self.seen, [
            (self.LATEST, "Bearer fictional-token"),
            (self.ARCHIVE, None),
            (self.CODELOAD, None),
        ])

    def test_a_redirect_from_the_api_doesnt_carry_the_token(self):
        self.routes[self.LATEST] = (302, {"Location": "/elsewhere"}, b"")
        self.routes["/elsewhere"] = (200, {}, json.dumps({"tag_name": "v4.5.0-rc2"}).encode())
        self.serve(self.real_archive())
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional-token"):
            self.run_tag()
        self.assertEqual(self.seen[:2], [(self.LATEST, "Bearer fictional-token"), ("/elsewhere", None)])
