import ast
import contextlib
import dataclasses
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tests import demo, drift_watch, golden
from tests.test_omaupdateimpact import QMLLINT_OUTPUT, QT6_VERSION, ProgramCase, impact

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
    """Report text with its line wrapping undone."""
    return " ".join(text.split())


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
            {QT6_VERSION}
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
        self.assertEqual(result.stdout.splitlines()[-1], "These checks ran in part: packages.")

    def test_missing_notes_dont_change_the_exit_code(self):
        release = self.base / "v4.5.0-rc2"
        shutil.copytree(NEW, release)
        (release / impact.NOTES).unlink()
        unread = self.base / "unread-home"
        shutil.copytree(self.clean_home, unread, symlinks=True)
        (unread / ".local/state/omarchy/migrations" / UNREADABLE_MIGRATION).unlink()
        for packages, home, code in (
            (["fictional-editor"], self.clean_home, 0),
            (["dua-cli"], self.clean_home, 1),
            (["fictional-editor"], unread, 3),
        ):
            with self.subTest(packages=packages, home=home.name):
                self.packages(*packages)
                with_notes = self.compare(home, "--all")
                without = self.command("--root", OLD, "--target", release, "--home", home, "--all")
                self.assert_exit(with_notes, code)
                self.assert_exit(without, code)
                self.assertIn("Why:", with_notes.stdout)
                self.assertNotIn("Why:", without.stdout)
                self.assertEqual(without.stderr, "")

    def test_a_missing_pacman_exits_3(self):
        (self.stubs / "pacman").unlink()
        result = self.compare(self.clean_home)
        self.assert_exit(result, 3)
        self.assertIn("pacman wasn't available", result.stdout)
        self.assertNotIn("nothing found", result.stdout.lower())

    def test_a_qmllint_killed_by_a_signal_exits_3(self):
        self.stub("qmllint", f"{QT6_VERSION}\nkill -TERM $$")
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
        self.everything = self.compare(HOME, "--all")
        self.output = flat(self.everything.stdout)

    def attention(self):
        return flat(self.result.stdout.partition("Needs attention")[2].partition("Worth knowing")[0])

    def test_it_exits_1_and_still_names_what_it_couldnt_read(self):
        self.assert_exit(self.result, 1)
        self.assertEqual(self.result.stderr, "")
        self.assertEqual(self.result.stdout.splitlines()[-1], "These checks ran in part: packages.")

    def test_a_typical_report_fits_on_one_screen(self):
        self.assertLessEqual(len(self.result.stdout.splitlines()), 40)
        self.assertIn("Worth knowing: 12 notes. Add --all to see them.", self.result.stdout)
        self.assertNotIn("Moved:", self.result.stdout)

    def test_all_shows_the_notes_and_keeps_the_rest(self):
        self.assertIn("Moved:", self.everything.stdout)
        self.assertNotIn("--all", self.everything.stdout)
        self.assertEqual(self.everything.returncode, self.result.returncode)
        section = self.everything.stdout.partition("Needs attention")[2].partition("Worth knowing")[0]
        self.assertEqual(section, self.result.stdout.partition("Needs attention")[2].partition("Worth knowing")[0])
        self.assertIn("Limits of this check", self.everything.stdout)

    def test_limits_are_never_collapsed(self):
        self.assertIn(f"Couldn't read what migrations/{UNREADABLE_MIGRATION} removes", flat(self.result.stdout))

    def test_no_command_is_split_across_lines(self):
        for command in ("omarchy-voxtype-install", "omarchy-voxtype-status", "omarchy-system-shutdown"):
            self.assertIn(command, self.everything.stdout)

    def test_every_finding_that_needs_attention_has_a_fix(self):
        lines = self.result.stdout.partition("Needs attention")[2].partition("Worth knowing")[0].splitlines()
        self.assertEqual(sum(line.startswith("  - ") for line in lines), 10)
        self.assertEqual(sum(line.startswith("    Fix: ") for line in lines), 10)

    def test_a_removed_package_has_the_line_that_brings_it_back(self):
        self.assertIn(
            "Fix: After the update, run omarchy pkg add dua-cli (aur-add for an AUR package).",
            self.result.stdout,
        )
        self.assertIn(
            "Fix: If it goes, run omarchy pkg add t3code-bin (aur-add for an AUR package).",
            self.result.stdout,
        )

    def test_a_deleted_command_says_why_it_has_no_exact_fix(self):
        self.assertIn(
            "~/.bashrc calls omarchy-voxtype-remove, which the release deletes. "
            "Fix: Change or remove line 1. This tool can't tell what replaces the command.",
            self.attention(),
        )

    def test_a_clean_result_and_this_one_show_what_was_checked(self):
        self.assertIn(
            "Checked 207 default bindings, 3 of yours, 27 pending migrations for packages and 28 for "
            "file edits, 7 of your files for 6 deleted commands, 1 plugin linted.",
            flat(self.result.stdout),
        )
        clean = self.compare(self.clean_home).stdout.splitlines()
        self.assertEqual(clean[1:3], [
            "Checked 207 default bindings, 0 of yours, 28 pending migrations, 0 of your files for 6",
            "deleted commands, no plugins.",
        ])

    def test_a_move_and_what_it_displaced_are_one_finding(self):
        self.assertIn(
            'Moved: "Network" from SUPER + CTRL + W to SUPER + CTRL + N, replacing "Toggle nightlight". '
            'SUPER + CTRL + W is now "Background switcher".',
            self.output,
        )
        self.assertNotIn("SUPER + CTRL + N is now", self.output)
        self.assertNotIn('it was "Network"', self.output)

    def test_a_change_with_no_move_keeps_its_line(self):
        self.assertIn('SUPER + ALT + SPACE is now "Apps", it was "Apps menu".', self.output)

    def test_piped_output_has_no_colour(self):
        for result in (self.result, self.everything, self.compare(self.clean_home)):
            self.assertNotIn("\x1b", result.stdout)

    def test_a_new_default_on_your_key_is_a_clash(self):
        self.assertIn(
            'SUPER + M: your "Music" will clash with the new default "Minimize window to the dock". Both will fire. '
            'Fix: Add hl.unbind("SUPER + M") above your binding, or choose another key.',
            self.attention(),
        )

    def test_a_key_no_default_uses_is_no_clash(self):
        self.assertNotIn("SUPER + F12", self.output)

    def test_a_shortcut_you_turned_off_that_moves_comes_back(self):
        self.assertIn(
            'SUPER + CTRL + T: you turned off "Activity" here, but it moves to SUPER + SHIFT + T, so it comes back. '
            'Fix: Add hl.unbind("SUPER + SHIFT + T") too.',
            self.attention(),
        )

    def test_a_removal_says_why_from_the_release_notes(self):
        self.assertIn(
            "The update will remove dua-cli, which is installed here. "
            "Why: Replace the Disk Usage TUI with Disktree (#14426). Fix: After the update, run omarchy pkg add dua-cli",
            self.attention(),
        )
        findings = json.loads(self.compare(HOME, "--json").stdout)["findings"]
        removal = next(finding for finding in findings if "remove dua-cli" in finding["title"])
        self.assertEqual(removal["reason"], {
            "text": "Replace the Disk Usage TUI with Disktree",
            "reference": "#14426",
            "evidence": f"{impact.NOTES}:328",
        })

    def test_a_finding_with_no_clear_match_says_no_why(self):
        self.assertIn("The update may remove t3code-bin, which is installed here. Fix: If it goes", self.attention())
        self.assertIn('SUPER + M: your "Music" will clash with the new default "Minimize window to the dock". Both will fire. Fix:', self.attention())

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

    def test_a_migration_that_edits_a_file_you_changed_is_a_note(self):
        self.assertIn(
            "migrations/1788129995.sh, line 10, looks like it edits ~/.config/imv/config, which differs from "
            "Omarchy's default.",
            self.output,
        )
        self.assertNotIn("imv", self.result.stdout)

    def test_a_migration_that_edits_a_file_you_left_as_it_was_says_nothing(self):
        (self.clean_home / ".config/imv").mkdir(parents=True)
        shutil.copy(OLD / "config/imv/config", self.clean_home / ".config/imv/config")
        self.assertNotIn("imv", self.compare(self.clean_home, "--all").stdout)

    def test_a_new_lint_warning_is_a_note(self):
        self.assertNotIn("qmllint", self.attention())
        self.assertIn("demo: 2 new qmllint warnings, such as Demo.qml: Warnings occurred while importing module", self.output)
        self.assertIn("qmllint can't prove a plugin works.", self.output)


class JsonOutput(RealCommand):
    """--json on the real command: one document on stdout, and the same exit code as the report."""

    def assert_document(self, args, code, result, **env):
        text = self.command(*args, **env)
        found = self.command("--json", *args, **env)
        self.assert_exit(found, code)
        self.assertEqual(text.returncode, code)
        # json.loads takes one document and nothing else, so stray text would fail here.
        document = json.loads(found.stdout)
        self.assertEqual((document["schemaVersion"], document["result"]), (1, result))
        return document, found

    def trees(self, home, *args):
        return ["--root", OLD, "--target", NEW, "--home", home, *args]

    def test_every_exit_code_gives_one_document(self):
        crashing = self.base / "broken"
        shutil.copytree(NEW, crashing)
        (crashing / "default/hypr/bindings/broken.lua").mkdir()
        cases = {
            "clear": (self.trees(self.clean_home), 0, "clear", {}),
            "attention": (self.trees(HOME), 1, "attention", {}),
            "bad option": (["--no-such-option"], 2, "failed", {}),
            "bad tag": (self.trees(self.clean_home, "main"), 2, "failed", {}),
            "unusable tree": (["--root", OLD, "--target", self.clean_home, "--home", self.clean_home], 2, "failed", {}),
            "crash": (["--root", OLD, "--target", crashing, "--home", self.clean_home], 2, "failed", {}),
            "channel without tags": (["--root", OLD, "--home", self.clean_home, "--channel", "edge"], 2, "failed", {}),
            "failed download": (["v4.5.0-rc2", "--root", OLD, "--home", self.clean_home], 2, "failed", {}),
        }
        for name, (args, code, result, env) in cases.items():
            with self.subTest(name):
                document, found = self.assert_document(args, code, result, **env)
                if result == "failed":
                    self.assertIn(document["reason"].removeprefix("Bad usage: "), found.stderr)
                    self.assertNotIn("Traceback", found.stderr)
                else:
                    self.assertEqual(found.stderr, "")

    def test_a_check_that_couldnt_run_in_full_exits_3_as_a_document(self):
        (self.clean_home / ".local/state/omarchy/migrations" / UNREADABLE_MIGRATION).unlink()
        document = self.assert_document(self.trees(self.clean_home), 3, "incomplete")[0]
        self.assertEqual(document["checks"]["packages"]["state"], "ranInPart")

    def test_no_update_is_a_document(self):
        self.stub("omarchy-version", "echo 4.5.0rc2-1")
        document = self.assert_document(["v4.5.0-rc2"], 0, "noUpdate", OMARCHY_PATH=NEW, HOME=HOME)[0]
        self.assertEqual(document["target"], {"name": "v4.5.0-rc2", "prerelease": True})
        self.assertIsNone(document["newer"])
        self.assertEqual(document["newerProblem"], "Couldn't check for newer releases on other channels.")

    def test_the_document_holds_what_the_report_shows(self):
        self.packages("dua-cli", "dust", "t3code-bin", "tensaku", "fictional-editor")
        report = self.command(*self.trees(HOME, "--all"))
        document = json.loads(self.command("--json", *self.trees(HOME)).stdout)
        self.assertEqual(document["result"], "attention")
        self.assertEqual(report.stdout.splitlines()[0], "Omarchy 4.0.6-1 -> v4.5.0-rc2 (stable channel, prerelease). Nothing was changed.")
        self.assertEqual(
            (document["installed"], document["target"], document["channel"]),
            ("4.0.6-1", {"name": "v4.5.0-rc2", "prerelease": True}, "stable"),
        )
        # The report says: Checked 207 default bindings, 3 of yours, 27 pending migrations for
        # packages and 28 for file edits, 7 of your files for 6 deleted commands, 1 plugin linted.
        self.assertEqual({check: value["checked"] for check, value in document["checks"].items()}, {
            "bindings": {"defaults": 207, "yours": 3},
            "packages": {"pendingMigrations": 27},
            "commands": {"deletedCommands": 6, "yourFiles": 7},
            "plugins": {"linted": 1},
            "edits": {"pendingMigrations": 28},
        })
        # And ends: These checks ran in part: packages.
        self.assertEqual({check: value["state"] for check, value in document["checks"].items()}, {
            "bindings": "ran", "packages": "ranInPart", "commands": "ran", "plugins": "ran", "edits": "ran",
        })
        shown = flat(report.stdout)
        levels = Counter(finding["level"] for finding in document["findings"])
        self.assertEqual(levels, {"attention": 10, "note": 12, "unknown": 1})
        for finding in document["findings"]:
            with self.subTest(finding["title"]):
                self.assertIn(flat(" ".join(part for part in (finding["title"], finding["detail"]) if part)), shown)
                if finding["fix"]:
                    self.assertIn(f"Fix: {flat(finding['fix'])}", shown)
                self.assertTrue(finding["evidence"])
                self.assertEqual(finding["partial"], finding["level"] == "unknown")


class JsonDocs(unittest.TestCase):
    """docs/json.md shows the golden documents, and they are what the command prints."""

    @classmethod
    def setUpClass(cls):
        cls.printed = golden.documents()
        cls.doc = golden.DOC.read_text()

    def test_the_golden_files_are_what_the_command_prints(self):
        for name, text in self.printed.items():
            with self.subTest(name):
                self.assertEqual((golden.GOLDEN / f"{name}.json").read_text(), text, "Run python3 -m tests.golden.")

    def test_the_schema_doc_shows_the_golden_files(self):
        for name in self.printed:
            with self.subTest(name):
                text = (golden.GOLDEN / f"{name}.json").read_text()
                self.assertIn(f"```json\n{text}```\n", self.doc, f"Copy tests/fixtures/json/{name}.json into the doc.")

    def test_the_schema_doc_names_every_key_and_value(self):
        def keys(value):
            if isinstance(value, dict):
                for key, inner in value.items():
                    yield key
                    yield from keys(inner)
            elif isinstance(value, list):
                for inner in value:
                    yield from keys(inner)

        names = {key for text in self.printed.values() for key in keys(json.loads(text))}
        names |= {*impact.RESULTS, impact.RAN, impact.RAN_IN_PART, impact.DIDNT_RUN, *impact.CHECKS}
        names |= {count for counts in impact.CHECKS.values() for count in counts}
        # What a finding is about is only for finding its reason, and isn't in the document.
        names |= {field.name for field in dataclasses.fields(impact.Finding) if field.name != "about"}
        names |= {field.name for field in dataclasses.fields(impact.Reason)}
        names |= {impact.ATTENTION, impact.NOTE, impact.UNKNOWN}
        for name in sorted(names):
            self.assertIn(f"`{name}`", self.doc)

    def test_the_examples_name_nobody(self):
        for text in self.printed.values():
            for path in ("/home/", tempfile.gettempdir(), str(COMMAND.parent.parent)):
                self.assertNotIn(path, text)


class BindHold(RealCommand):
    """v4.5.0-rc2 moved its dictation keys to o.bind_hold, which the first version couldn't read."""

    def test_a_key_moved_to_the_helper_is_not_removed(self):
        result = self.compare(self.clean_home, "--all")
        self.assertNotIn("F9", result.stdout)
        self.assertNotIn("Default shortcuts removed", flat(result.stdout))

    def test_a_key_bound_with_the_helper_is_new(self):
        output = flat(self.compare(self.clean_home, "--all").stdout)
        self.assertIn('ALT + ALT_R ("Start dictation (push-to-talk) / Stop dictation (push-to-talk)")', output)

    def test_your_key_clashes_with_the_helper(self):
        self.assertIn(
            'ALT + ALT_R: your "Scratchpad" will clash with the new default '
            '"Start dictation (push-to-talk) / Stop dictation (push-to-talk)".',
            flat(self.compare(HOME).stdout),
        )

    def test_the_helper_is_no_limit(self):
        self.assertNotIn("isn't one this tool can read", flat(self.compare(self.clean_home).stdout))


class Version(RealCommand):
    def old_python(self, *version, args=("--version",)):
        """Runs the real file with sys.version_info set to version."""
        script = f"import runpy, sys; sys.version_info = {version}; sys.argv = ['x', *{args!r}]; runpy.run_path({str(COMMAND)!r}, run_name='__main__')"
        return subprocess.run(
            [sys.executable, "-c", script], env=self.env(), capture_output=True, text=True, timeout=60, check=False
        )

    def test_version_comes_from_one_place(self):
        result = self.command("--version")
        self.assert_exit(result, 0)
        self.assertEqual(result.stdout, f"omaupdateimpact {impact.__version__}\n")

    def test_the_aur_package_has_the_same_version(self):
        package = (COMMAND.parent.parent / "packaging/aur/PKGBUILD").read_text()
        self.assertIn(f"\npkgver={impact.__version__}\n", package)

    def test_help_explains_the_options_for_other_trees(self):
        text = flat(self.command("--help").stdout)
        for option in ("--channel CHANNEL follow", "--target TARGET compare", "--root ROOT the installed", "--home HOME read"):
            self.assertIn(option, text)

    def test_an_old_python_gets_one_line(self):
        result = self.old_python(3, 11, 3, "final", 0)
        self.assert_no_verdict(result, "omaupdateimpact needs Python 3.11.4 or newer, and this is 3.11.3.")
        self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_an_old_python_answers_json_too(self):
        result = self.old_python(3, 11, 3, "final", 0, args=("--js",))
        reason = "omaupdateimpact needs Python 3.11.4 or newer, and this is 3.11.3."
        self.assert_exit(result, 2)
        self.assertEqual(json.loads(result.stdout), {"schemaVersion": 1, "result": "failed", "reason": reason})
        self.assertEqual(result.stderr, reason + "\n")

    def test_the_oldest_python_it_takes_runs(self):
        result = self.old_python(3, 11, 4, "final", 0)
        self.assert_exit(result, 0)
        self.assertIn("omaupdateimpact", result.stdout)

    def test_an_old_python_can_parse_the_file(self):
        # A syntax error comes before the check, and would be a traceback. 3.7 is as far back as ast reads.
        ast.parse(COMMAND.read_text(), feature_version=(3, 7))


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


class Demo(unittest.TestCase):
    """The README's report and the recording are what the command prints."""

    @classmethod
    def setUpClass(cls):
        cls.printed = demo.recorded()

    def test_the_readme_opens_with_the_real_report(self):
        readme = (COMMAND.parent.parent / "README.md").read_text()
        report = f"```\n$ {demo.COMMAND}\n{demo.plain(self.printed)}```\n"
        self.assertIn(report, readme, "Copy the new report into the README.")
        self.assertLess(readme.index(report), readme.index("\n## "))

    def test_the_recording_is_up_to_date(self):
        self.assertEqual(demo.OUTPUT.read_text(), demo.svg(self.printed), "Run python3 -m tests.demo.")

    def test_the_recording_shows_the_whole_report(self):
        recording = demo.OUTPUT.read_text()
        for line in ("Needs attention", "Fix:", "These checks ran in part: packages."):
            self.assertIn(line, recording)

    def test_the_command_shows_when_nothing_animates(self):
        still = demo.OUTPUT.read_text().partition("@media")[0]
        self.assertIn(f"#command {{ transform: {demo.COVER_MOVED}; }}", still)

    def test_the_recording_names_nobody(self):
        recording = demo.OUTPUT.read_text()
        for path in ("/home/", tempfile.gettempdir(), str(COMMAND.parent.parent)):
            self.assertNotIn(path, recording)


class DriftWatch(unittest.TestCase):
    """The command the scheduled job runs, on a copy of a real release."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.release = Path(directory.name) / "v4.5.0-rc2"
        shutil.copytree(NEW, self.release)

    def watch(self):
        return subprocess.run(
            [sys.executable, "-m", "tests.drift_watch", "--target", str(self.release)],
            cwd=COMMAND.parent.parent, capture_output=True, text=True, timeout=60, check=False,
        )

    def assert_fails(self, message):
        result = self.watch()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stdout)

    def test_a_release_it_can_read_passes(self):
        result = self.watch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "v4.5.0-rc2 fits the parser.\n")

    def test_an_unknown_helper_fails(self):
        with (self.release / "default/hypr/helpers.lua").open("a") as helpers:
            helpers.write("\nfunction o.bind_mystery(keys) end\n")
        self.assert_fails("default/hypr/helpers.lua defines o.bind_mystery")

    def test_an_unknown_helper_in_another_file_fails(self):
        (self.release / "default/hypr/extra.lua").write_text("o.bind_mystery = function(keys) end\n")
        self.assert_fails("default/hypr/extra.lua defines o.bind_mystery")

    def test_zero_bindings_fails(self):
        shutil.rmtree(self.release / "default/hypr/bindings")
        self.assert_fails("no readable default bindings")

    def test_a_missing_tree_directory_fails(self):
        for part in impact.TREE_PARTS:
            with self.subTest(part=part):
                moved = self.release.parent / "moved"
                (self.release / part).rename(moved)
                self.assert_fails(f"has nothing in {part}")
                moved.rename(self.release / part)


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
    RELEASES = "/api/repos/omacom/omarchy/releases?per_page=100"
    NOTES = "/api/repos/omacom/omarchy/releases/tags/v4.5.0-rc2"

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
        """The trimmed release as GitHub packs it, which is without its notes."""
        (self.base / "target").rename(self.base / "small")
        shutil.copytree(NEW, self.base / "target")
        (self.base / "target" / impact.NOTES).unlink()
        return self.archive()

    def serve_notes(self):
        notes = (NEW / impact.NOTES).read_bytes()
        self.routes[self.NOTES] = (200, {}, json.dumps({"tag_name": "v4.5.0-rc2", "body": notes.decode()}).encode())
        return notes

    def serve(self, body, **headers):
        """GitHub redirects an archive to another host, and doesn't say its size."""
        self.routes[self.ARCHIVE] = (302, {"Location": self.CODELOAD}, b"")
        self.routes[self.CODELOAD] = (200, {k.replace("_", "-"): v for k, v in headers.items()}, body)

    def run_tag(self, *args):
        return self.run_argv("--root", str(OLD), "--home", str(self.home), "--channel", "stable", *args)

    def test_a_download_gives_the_report_of_the_same_release_on_disk(self):
        self.serve(self.real_archive())
        notes = self.serve_notes()
        code, out, err = self.run_tag("v4.5.0-rc2", "--all")
        self.assertEqual(err, "")
        self.assertEqual([path for path, _ in self.seen], [self.ARCHIVE, self.CODELOAD, self.NOTES])
        self.assertEqual((code, out), self.run_tag("--target", str(NEW), "--all")[:2])
        self.assertIn("Why: Move Calculator to Super + Shift + Q,", out)
        self.assertTrue((self.cache / "omaupdateimpact/v4.5.0-rc2/bin").is_dir())
        self.assertEqual((self.cache / "omaupdateimpact/v4.5.0-rc2" / impact.NOTES).read_bytes(), notes)

    def test_notes_that_cant_be_fetched_leave_the_report_without_reasons(self):
        self.serve(self.real_archive())
        self.routes[self.NOTES] = (500, {}, b"")
        code, out, err = self.run_tag("v4.5.0-rc2", "--all")
        self.assertEqual(code, self.run_tag("--target", str(NEW))[0])
        self.assertNotIn("Why:", out)
        self.assertEqual(err, "Couldn't fetch the release notes, so no finding says why: HTTP Error 500: Internal Server Error\n")
        self.assertFalse((self.cache / "omaupdateimpact/v4.5.0-rc2" / impact.NOTES).exists())
        self.seen.clear()
        notes = self.serve_notes()
        self.assertIn("Why:", self.run_tag("v4.5.0-rc2", "--all")[1])
        self.assertEqual([path for path, _ in self.seen], [self.NOTES])
        self.assertEqual((self.cache / "omaupdateimpact/v4.5.0-rc2" / impact.NOTES).read_bytes(), notes)

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

    def test_the_drift_watch_reads_the_newest_release_by_version(self):
        self.routes[self.RELEASES] = (200, {}, json.dumps([{"tag_name": "v4.0.6"}, {"tag_name": "v4.5.0-rc2"}]).encode())
        self.serve(self.real_archive())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = drift_watch.main([])
        self.assertEqual((code, out.getvalue()), (0, "v4.5.0-rc2 fits the parser.\n"))
        self.assertEqual([path for path, _ in self.seen], [self.RELEASES, self.ARCHIVE, self.CODELOAD])

    def test_the_drift_watch_finds_a_new_helper_in_a_download(self):
        self.routes[self.RELEASES] = (200, {}, json.dumps([{"tag_name": "v4.5.0-rc2"}]).encode())
        self.real_archive()
        with (self.base / "target/default/hypr/helpers.lua").open("a") as helpers:
            helpers.write("\nfunction o.bind_mystery(keys) end\n")
        self.serve(self.archive())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(drift_watch.main([]), 1)
        self.assertIn("o.bind_mystery", out.getvalue())

    def test_the_drift_watch_fails_when_the_list_has_no_release(self):
        self.routes[self.RELEASES] = (200, {}, b"[]")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(drift_watch.main([]), 1)
        self.assertIn("no usable release", out.getvalue())

    def test_the_drift_watch_fails_when_the_download_does(self):
        self.routes[self.RELEASES] = (200, {}, json.dumps([{"tag_name": "v4.5.0-rc2"}]).encode())
        with self.assertRaises(impact.urllib.error.HTTPError):
            drift_watch.main([])

    def test_a_rejected_token_is_named_and_never_printed(self):
        self.routes[self.LATEST] = (401, {}, b"")
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional-token"):
            result = self.run_tag()
        self.assert_download_failed(result)
        self.assertIn("GitHub rejected GITHUB_TOKEN", result[2])
        self.assertNotIn("fictional-token", result[2])

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
            (self.NOTES, "Bearer fictional-token"),
        ])

    def test_a_redirect_from_the_api_doesnt_carry_the_token(self):
        self.routes[self.LATEST] = (302, {"Location": "/elsewhere"}, b"")
        self.routes["/elsewhere"] = (200, {}, json.dumps({"tag_name": "v4.5.0-rc2"}).encode())
        self.serve(self.real_archive())
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional-token"):
            self.run_tag()
        self.assertEqual(self.seen[:2], [(self.LATEST, "Bearer fictional-token"), ("/elsewhere", None)])
