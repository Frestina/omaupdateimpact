import contextlib
import gzip
import importlib.machinery
import importlib.util
import io
import os
import shutil
import tarfile
import tempfile
import unittest
from http.client import IncompleteRead
from pathlib import Path
from unittest import mock

path = Path(__file__).parent.parent / "bin/omaupdateimpact"
loader = importlib.machinery.SourceFileLoader("impact", str(path))
spec = importlib.util.spec_from_loader("impact", loader)
impact = importlib.util.module_from_spec(spec)
loader.exec_module(impact)


def parse(text):
    parsed = impact.Parsed()
    impact.parse_lua(text, parsed)
    return parsed


def compare(current, target, user=""):
    return impact.compare_bindings(parse(current), parse(target), parse(user))


def titles(findings, level):
    return [finding.title for finding in findings if finding.level == level]


class ParseLua(unittest.TestCase):
    def test_reads_a_bind(self):
        bind = parse('o.bind("SUPER + W", "Close", "close-it")').binds["SUPER + W"]
        self.assertEqual((bind.description, bind.command), ("Close", "close-it"))

    def test_key_order_and_case_do_not_matter(self):
        self.assertIn("SUPER + SHIFT + A", parse('o.bind("shift + super + a", "x", "y")').binds)

    def test_skips_comments_but_not_strings(self):
        parsed = parse('-- o.bind("SUPER + A", "x", "y")\no.bind("SUPER + B", "a -- b", "y")')
        self.assertEqual(list(parsed.binds), ["SUPER + B"])
        self.assertEqual(parsed.binds["SUPER + B"].description, "a -- b")

    def test_skips_block_comments(self):
        self.assertEqual(parse('--[[ o.bind("SUPER + A", "x", "y") ]]').binds, {})

    def test_reads_a_call_over_several_lines(self):
        self.assertIn("SUPER + A", parse('o.bind(\n  "SUPER + A",\n  "x",\n  fn(1, 2)\n)').binds)

    def test_expands_toggles(self):
        bind = parse('o.bind_toggle("SUPER + N", "Night", "nightlight")').binds["SUPER + N"]
        self.assertEqual(bind.command, "omarchy-toggle-nightlight")

    def test_rebind_counts_as_unbind_and_bind(self):
        parsed = parse('o.rebind("SUPER + A", "x", "y")')
        self.assertIn("SUPER + A", parsed.unbinds)
        self.assertIn("SUPER + A", parsed.binds)

    def test_reads_description_from_hl_bind(self):
        bind = parse('hl.bind("SUPER + A", act(), { description = "Do it" })').binds["SUPER + A"]
        self.assertEqual(bind.description, "Do it")

    def test_counts_computed_keys(self):
        parsed = parse('o.bind("SUPER + " .. n, "x", "y")')
        self.assertEqual((parsed.binds, len(parsed.unread)), ({}, 1))


class CompareBindings(unittest.TestCase):
    def test_flags_a_clash_with_a_new_default(self):
        findings = compare("", 'o.bind("SUPER + M", "Minimize", "min")', 'o.bind("SUPER + M", "Mail", "mail")')
        self.assertEqual(len(titles(findings, "attention")), 1)
        self.assertIn("clash", titles(findings, "attention")[0])
        self.assertEqual(findings[0].fix, 'Add hl.unbind("SUPER + M") or choose another key.')

    def test_a_clash_names_the_files_behind_it(self):
        target, user = impact.Parsed(), impact.Parsed()
        impact.parse_lua('o.bind("SUPER + M", "Minimize", "min")', target, "default/hypr/tiling.lua")
        impact.parse_lua('o.bind("SUPER + M", "Mail", "mail")', user, "~/.config/hypr/bindings.lua")
        findings = impact.compare_bindings(impact.Parsed(), target, user)
        self.assertEqual(findings[0].evidence, ["default/hypr/tiling.lua", "~/.config/hypr/bindings.lua"])

    def test_computed_keys_are_a_note(self):
        findings = compare('o.bind("SUPER + " .. n, "x", "y")', "")
        self.assertEqual(titles(findings, "unknown"), [])
        self.assertIn("1 key bindings", titles(findings, "note")[0])

    def test_no_clash_when_the_user_unbinds_first(self):
        user = 'hl.unbind("SUPER + M")\no.bind("SUPER + M", "Mail", "mail")'
        findings = compare("", 'o.bind("SUPER + M", "Minimize", "min")', user)
        self.assertEqual(titles(findings, "attention"), [])

    def test_no_clash_when_the_default_is_unchanged(self):
        same = 'o.bind("SUPER + M", "Minimize", "min")'
        self.assertEqual(titles(compare(same, same, 'o.bind("SUPER + M", "Mail", "mail")'), "attention"), [])

    def test_reports_a_moved_shortcut(self):
        findings = compare('o.bind("SUPER + Q", "Calc", "c")', 'o.bind("SUPER + SHIFT + Q", "Calc", "c")')
        self.assertIn('Moved: "Calc" from SUPER + Q to SUPER + SHIFT + Q.', titles(findings, "note"))

    def test_a_turned_off_shortcut_that_moves_comes_back(self):
        findings = compare(
            'o.bind("SUPER + Q", "Calc", "c")',
            'o.bind("SUPER + SHIFT + Q", "Calc", "c")',
            'hl.unbind("SUPER + Q")',
        )
        self.assertIn("comes back", titles(findings, "attention")[0])

    def test_a_shortcut_that_comes_back_names_the_files_behind_it(self):
        current, target, user = impact.Parsed(), impact.Parsed(), impact.Parsed()
        impact.parse_lua('o.bind("SUPER + Q", "Calc", "c")', current, "default/hypr/old.lua")
        impact.parse_lua('o.bind("SUPER + SHIFT + Q", "Calc", "c")', target, "default/hypr/new.lua")
        impact.parse_lua('hl.unbind("SUPER + Q")', user, "~/.config/hypr/bindings.lua")
        finding = impact.compare_bindings(current, target, user)[0]
        self.assertEqual(
            finding.evidence, ["~/.config/hypr/bindings.lua", "default/hypr/new.lua", "default/hypr/old.lua"]
        )

    def test_every_note_names_the_files_behind_it(self):
        current, target, user = impact.Parsed(), impact.Parsed(), impact.Parsed()
        old, new, mine = "default/hypr/old.lua", "default/hypr/new.lua", "~/.config/hypr/bindings.lua"
        impact.parse_lua(
            """
            o.bind("SUPER + A", "Calc", "c")
            o.bind("SUPER + N", "Night", "n")
            o.bind("SUPER + G", "Gone", "g")
            o.bind("SUPER + U", "Unbound", "u")
            o.bind("SUPER + R", "Old", "r")
            """,
            current,
            old,
        )
        impact.parse_lua(
            """
            o.bind("SUPER + B", "Calc", "c")
            o.bind("SUPER + N", "Network", "w")
            o.bind("SUPER + F", "Fresh", "f")
            o.bind("SUPER + R", "Newer", "q")
            """,
            target,
            new,
        )
        impact.parse_lua(
            'hl.unbind("SUPER + U")\nhl.unbind("SUPER + R")\no.bind("SUPER + R", "Mine", "m")', user, mine
        )
        findings = impact.compare_bindings(current, target, user)
        self.assertEqual(
            [finding.evidence for finding in findings],
            [[new, mine], [mine, old], [new, old], [new, old], [new], [old]],
        )

    def test_computed_keys_name_their_files_once(self):
        current, target = impact.Parsed(), impact.Parsed()
        computed = 'o.bind("SUPER + " .. n, "x", "y")'
        impact.parse_lua(computed, current, "default/hypr/tiling.lua")
        impact.parse_lua(computed, target, "default/hypr/tiling.lua")
        finding = impact.compare_bindings(current, target, impact.Parsed())[0]
        self.assertEqual(finding.evidence, ["default/hypr/tiling.lua"])

    def test_reports_a_shortcut_taken_over_by_another_action(self):
        findings = compare('o.bind("SUPER + N", "Night", "n")', 'o.bind("SUPER + N", "Network", "w")')
        self.assertIn('SUPER + N is now "Network", it was "Night".', titles(findings, "note"))

    def test_reworded_description_with_the_same_command_is_not_a_change(self):
        self.assertEqual(compare('o.bind("SUPER + N", "Old", "n")', 'o.bind("SUPER + N", "New", "n")'), [])


class Packages(unittest.TestCase):
    def changes(self, migrations, already_run=()):
        with tempfile.TemporaryDirectory() as directory:
            for name, text in migrations.items():
                (Path(directory) / name).write_text(text)
            return impact.package_changes(Path(directory), set(already_run))

    def test_reads_drops(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a b >/dev/null\n"}), {"a": (False, "1.sh"), "b": (False, "1.sh")})

    def test_indented_drop_is_conditional(self):
        self.assertEqual(self.changes({"1.sh": "if x; then\n  omarchy-pkg-drop a\nfi\n"}), {"a": (True, "1.sh")})

    def test_skips_migrations_already_run(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n"}, ["1.sh"]), {})

    def test_a_later_add_cancels_a_drop(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n", "2.sh": "omarchy-pkg-add a\n"}), {})

    def test_ignores_shell_variables(self):
        self.assertEqual(self.changes({"1.sh": 'omarchy-pkg-drop "$pkg"\n'}), {})

    def test_a_missing_pacman_is_unknown(self):
        finding = impact.compare_packages(Path("target"), Path("home"), None)[0]
        self.assertEqual((finding.check, finding.level), ("packages", "unknown"))

    def test_a_failing_pacman_counts_as_missing(self):
        error = impact.subprocess.CalledProcessError(1, "pacman")
        with mock.patch.object(impact.subprocess, "run", side_effect=error):
            self.assertIsNone(impact.installed_packages())

    def test_a_removal_names_its_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "migrations").mkdir()
            (target / "migrations/1.sh").write_text("omarchy-pkg-drop a\n")
            finding = impact.compare_packages(target, target, {"a"})[0]
        self.assertEqual((finding.level, finding.evidence), ("attention", ["migrations/1.sh"]))


class Commands(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "home"
        self.hooks = self.home / ".config/omarchy/hooks"
        self.hooks.mkdir(parents=True)
        (self.base / "current/bin").mkdir(parents=True)
        (self.base / "target/bin").mkdir(parents=True)
        (self.base / "current/bin/omarchy-gone").touch()
        (self.base / "current/bin/omarchy-gone-too").touch()
        (self.base / "target/bin/omarchy-gone-too").touch()

    def attention(self):
        findings = impact.compare_commands(self.base / "current", self.base / "target", self.home)
        return titles(findings, "attention")

    def test_finds_a_call_to_a_deleted_command(self):
        (self.hooks / "my.hook").write_text("omarchy-gone\nomarchy-gone again\n")
        self.assertEqual(len(self.attention()), 1)

    def test_a_call_names_the_file_behind_it(self):
        (self.hooks / "my.hook").write_text("omarchy-gone\n")
        findings = impact.compare_commands(self.base / "current", self.base / "target", self.home)
        self.assertEqual(findings[0].evidence, ["~/.config/omarchy/hooks/my.hook"])

    def test_a_line_starting_with_a_flag_is_not_a_comment(self):
        (self.hooks / "my.hook").write_text("    --exec omarchy-gone\n")
        self.assertEqual(len(self.attention()), 1)

    def test_ignores_comments(self):
        (self.hooks / "my.hook").write_text("# omarchy-gone\n")
        (self.hooks / "my.lua").write_text("-- omarchy-gone\n")
        self.assertEqual(self.attention(), [])

    def test_ignores_commands_that_stay(self):
        (self.hooks / "my.hook").write_text("omarchy-gone-too\n")
        self.assertEqual(self.attention(), [])

    def test_ignores_backups(self):
        (self.hooks / "my.lua.bak.123").write_text("omarchy-gone\n")
        self.assertEqual(self.attention(), [])


class Plugins(unittest.TestCase):
    def test_reports_only_new_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".config/omarchy/plugins/demo").mkdir(parents=True)
            warnings = {"current/shell": ["old"], "target/shell": ["old", "new"]}
            original = impact.lint
            impact.lint = lambda plugin, shell, qmllint: impact.Counter(
                ("a.qml", w) for w in warnings["/".join(shell.parts[-2:])]
            )
            self.addCleanup(setattr, impact, "lint", original)
            original_which = impact.shutil.which
            impact.shutil.which = lambda name: "/bin/true"
            self.addCleanup(setattr, impact.shutil, "which", original_which)
            findings = impact.compare_plugins(Path("current"), Path("target"), home)
            notes = titles(findings, "note")
            self.assertEqual(len(notes), 2)
            self.assertIn("1 new qmllint warnings, such as a.qml: new", notes[0])
            self.assertEqual(
                [finding.evidence for finding in findings],
                [["~/.config/omarchy/plugins/demo/a.qml"], ["~/.config/omarchy/plugins"]],
            )

    def findings_without_qmllint(self, home):
        with mock.patch.object(impact.shutil, "which", return_value=None), \
                mock.patch.object(impact, "QMLLINT", "/nonexistent/qmllint"):
            return impact.compare_plugins(Path("current"), Path("target"), home)

    def test_a_missing_qmllint_is_unknown_when_there_are_plugins(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".config/omarchy/plugins/demo").mkdir(parents=True)
            finding = self.findings_without_qmllint(home)[0]
        self.assertEqual((finding.check, finding.level), ("plugins", "unknown"))
        self.assertEqual(finding.evidence, ["~/.config/omarchy/plugins"])

    def test_a_missing_qmllint_does_not_matter_without_plugins(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".config/omarchy/plugins").mkdir(parents=True)
            self.assertEqual(self.findings_without_qmllint(home), [])


class ProgramCase(unittest.TestCase):
    """Runs main() on small fictional trees."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.tree("current", 'o.bind("SUPER + W", "Close", "close-it")')
        self.tree("target", 'o.bind("SUPER + W", "Close", "close-it")')
        self.cache = self.base / "cache"
        patcher = mock.patch.dict(os.environ, XDG_CACHE_HOME=str(self.cache))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tree(self, name, bindings):
        root = self.base / name
        for part in impact.TREE_PARTS:
            (root / part).mkdir(parents=True)
            (root / part / "keep").touch()
        (root / "default/hypr/bindings.lua").write_text(bindings)
        return root

    def run_main(self, *args):
        return self.run_argv("--root", str(self.base / "current"), "--home", str(self.home), *args)

    def run_argv(self, *args):
        argv = ["omaupdateimpact", *args]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.argv", argv), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = impact.main()
        return code, out.getvalue(), err.getvalue()

    def check(self, *args, packages=frozenset()):
        with mock.patch.object(impact, "installed_packages", return_value=packages):
            return self.run_main("--target", str(self.base / "target"), *args)

    def archive(self):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as tar:
            tar.add(self.base / "target", arcname="omarchy-1.2.3")
        return output.getvalue()

    def download(self, *responses, args=("v1.2.3",)):
        """Run with each network request answered by the next response."""
        with mock.patch.object(impact.urllib.request, "urlopen", side_effect=responses), \
                mock.patch.object(impact, "installed_packages", return_value=set()):
            return self.run_main(*args)

    def assert_download_failed(self, result):
        code, out, err = result
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(len(err.splitlines()), 1)
        self.assertIn("Couldn't download the release", err)
        self.assertEqual(list(self.cache.glob("*/*")), [])


class Program(ProgramCase):
    def test_a_clean_run_exits_0(self):
        code, out, _ = self.check()
        self.assertEqual(code, 0)
        self.assertIn("Nothing found", out)

    def test_something_that_needs_attention_exits_1(self):
        (self.base / "target/migrations/1.sh").write_text("omarchy-pkg-drop a\n")
        code, out, _ = self.check(packages={"a"})
        self.assertEqual(code, 1)
        self.assertNotIn("Nothing found", out)

    def test_a_missing_pacman_exits_3_and_never_says_nothing_found(self):
        empty = self.base / "empty"
        empty.mkdir()
        with mock.patch.dict(os.environ, PATH=str(empty)):
            code, out, _ = self.run_main("--target", str(self.base / "target"))
        self.assertEqual(code, 3)
        self.assertNotIn("nothing found", out.lower())
        self.assertEqual(out.splitlines()[-1], "These checks didn't run: packages.")

    def test_attention_outranks_unknown(self):
        (self.home / ".config/hypr").mkdir(parents=True)
        (self.home / ".config/hypr/bindings.lua").write_text('o.bind("SUPER + M", "Mail", "mail")')
        (self.base / "target/default/hypr/bindings.lua").write_text('o.bind("SUPER + M", "Minimize", "min")')
        code, out, _ = self.check(packages=None)
        self.assertEqual(code, 1)
        self.assertIn("These checks didn't run: packages.", out)

    def test_an_exception_in_a_check_exits_2_on_one_line(self):
        with mock.patch.object(impact, "compare_commands", side_effect=RuntimeError("broke\nbadly")):
            code, out, err = self.check()
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, "Unexpected RuntimeError: broke badly\n")

    def test_no_home_directory_exits_2_on_one_line(self):
        trees = ("--root", str(self.base / "current"), "--target", str(self.base / "target"))
        with mock.patch.object(impact.Path, "home", side_effect=RuntimeError("no home directory")):
            code, out, err = self.run_argv(*trees)
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, "Unexpected RuntimeError: no home directory\n")

    def test_debug_shows_the_traceback(self):
        with mock.patch.object(impact, "compare_commands", side_effect=RuntimeError("broke")):
            code, _, err = self.check("--debug")
        self.assertEqual(code, 2)
        self.assertIn("Traceback", err)


class Trees(ProgramCase):
    def setUp(self):
        super().setUp()
        self.root = self.base / "current"
        self.target = self.base / "target"
        self.empty = self.base / "empty"
        self.empty.mkdir()

    def compare(self, root, target):
        return self.run_argv("--root", str(root), "--target", str(target), "--home", str(self.home))

    def assert_refused(self, result, *names):
        code, out, err = result
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(len(err.splitlines()), 1)
        self.assertTrue(err.startswith("Can't compare: "), err)
        for name in names:
            self.assertIn(name, err)

    def test_a_good_pair_of_trees_is_accepted(self):
        self.assertEqual(self.check()[0], 0)

    def test_a_missing_or_empty_root_exits_2(self):
        for tree in (self.base / "nonexistent", self.empty):
            with self.subTest(tree=tree):
                self.assert_refused(self.compare(tree, self.target), str(tree), "installed", *impact.TREE_PARTS)

    def test_a_missing_or_empty_target_exits_2(self):
        for tree in (self.base / "nonexistent", self.empty):
            with self.subTest(tree=tree):
                self.assert_refused(self.compare(self.root, tree), str(tree), "release", *impact.TREE_PARTS)

    def test_both_trees_missing_exits_2(self):
        missing = self.base / "nonexistent"
        self.assert_refused(self.compare(missing, missing), str(missing))

    def test_a_file_is_not_a_tree(self):
        path = self.base / "file"
        path.touch()
        self.assert_refused(self.compare(path, self.target), str(path))

    def test_names_only_the_part_that_is_missing(self):
        for part in impact.TREE_PARTS:
            with self.subTest(part=part):
                tree = self.tree(f"without-{part.replace('/', '-')}", 'o.bind("SUPER + W", "Close", "close-it")')
                shutil.rmtree(tree / part)
                result = self.compare(self.root, tree)
                self.assert_refused(result, f"nothing in {part}.")

    def test_a_part_with_nothing_in_it_counts_as_missing(self):
        for part in ("bin", "migrations", "shell"):
            with self.subTest(part=part):
                tree = self.tree(f"hollow-{part}", 'o.bind("SUPER + W", "Close", "close-it")')
                (tree / part / "keep").unlink()
                self.assert_refused(self.compare(self.root, tree), f"nothing in {part}.")

    def test_a_bad_root_stops_before_the_download(self):
        with mock.patch.object(impact.urllib.request, "urlopen") as urlopen:
            result = self.run_argv("--root", str(self.base / "nonexistent"), "--home", str(self.home), "v1.2.3")
        self.assert_refused(result, "installed")
        urlopen.assert_not_called()

    def test_a_downloaded_release_must_be_usable_too(self):
        shutil.rmtree(self.target / "shell")
        self.assert_refused(self.download(io.BytesIO(self.archive())), "release", "nothing in shell.")

    def test_no_readable_bindings_exits_2(self):
        unreadable = {
            "no bindings": "",
            "only comments": '-- o.bind("SUPER + W", "Close", "close-it")',
            "only computed keys": 'o.bind("SUPER + " .. n, "x", "y")',
            "a format it doesn't know": 'o.key("SUPER + W", "Close", "close-it")',
        }
        for reason, text in unreadable.items():
            with self.subTest(reason=reason):
                tree = self.tree(f"unreadable-{len(reason)}", text)
                self.assert_refused(self.compare(tree, self.target), str(tree), "installed", "bindings")
                self.assert_refused(self.compare(self.root, tree), str(tree), "release", "bindings")

    def test_no_lua_files_exits_2(self):
        (self.target / "default/hypr/bindings.lua").unlink()
        self.assert_refused(self.compare(self.root, self.target), "release", "bindings")

    def test_bindings_in_the_helpers_file_do_not_count(self):
        (self.target / "default/hypr/bindings.lua").rename(self.target / "default/hypr/helpers.lua")
        self.assert_refused(self.compare(self.root, self.target), "release", "bindings")


class InstalledTree(ProgramCase):
    def run_with(self, *args, **environment):
        target = ("--target", str(self.base / "target"), "--home", str(self.home))
        with mock.patch.dict(os.environ, environment), \
                mock.patch.object(impact, "INSTALLED", str(self.base / "fallback")), \
                mock.patch.object(impact, "installed_packages", return_value=set()):
            if "OMARCHY_PATH" not in environment:
                os.environ.pop("OMARCHY_PATH", None)
            return self.run_argv(*target, *args)

    def test_omarchy_path_is_used_when_set(self):
        self.assertEqual(self.run_with(OMARCHY_PATH=str(self.base / "current"))[0], 0)

    def test_omarchy_path_is_what_gets_refused(self):
        code, _, err = self.run_with(OMARCHY_PATH=str(self.base / "nowhere"))
        self.assertEqual(code, 2)
        self.assertIn(str(self.base / "nowhere"), err)

    def test_without_omarchy_path_it_falls_back(self):
        code, _, err = self.run_with()
        self.assertEqual(code, 2)
        self.assertIn(str(self.base / "fallback"), err)

    def test_an_empty_omarchy_path_falls_back(self):
        code, _, err = self.run_with(OMARCHY_PATH="")
        self.assertEqual(code, 2)
        self.assertIn(str(self.base / "fallback"), err)

    def test_root_overrides_omarchy_path(self):
        root = str(self.base / "current")
        self.assertEqual(self.run_with("--root", root, OMARCHY_PATH=str(self.base / "nowhere"))[0], 0)


class InstalledVersion(ProgramCase):
    def stub(self, script):
        directory = self.base / "stub"
        directory.mkdir()
        command = directory / "omarchy-version"
        command.write_text(f"#!/bin/sh\n{script}\n")
        command.chmod(0o755)
        return str(directory)

    def first_line(self, path):
        with mock.patch.dict(os.environ, PATH=path):
            return self.check()[1].splitlines()[0]

    def test_shows_what_omarchy_version_says(self):
        self.assertIn("Omarchy 4.0.6-1 ->", self.first_line(self.stub("echo 4.0.6-1")))

    def test_keeps_a_dev_version_whole(self):
        self.assertIn("Omarchy dev (abc1234) ->", self.first_line(self.stub('echo "dev (abc1234)"')))

    def test_a_failing_command_is_unknown(self):
        self.assertIn("Omarchy unknown ->", self.first_line(self.stub("exit 1")))

    def test_no_output_is_unknown(self):
        self.assertIn("Omarchy unknown ->", self.first_line(self.stub("true")))

    def test_a_missing_command_is_unknown(self):
        self.assertIn("Omarchy unknown ->", self.first_line(str(self.base / "nowhere")))

    def test_the_copy_in_a_tree_is_never_run(self):
        marker = self.base / "ran"
        for name in ("current", "target"):
            command = self.base / name / "bin/omarchy-version"
            command.write_text(f"#!/bin/sh\ntouch {marker}\n")
            command.chmod(0o755)
        self.assertIn("Omarchy unknown ->", self.first_line(str(self.base / "nowhere")))
        self.assertFalse(marker.exists())


class Downloads(ProgramCase):
    def test_a_good_archive_is_used(self):
        code, _, err = self.download(io.BytesIO(self.archive()))
        self.assertEqual((code, err), (0, ""))
        self.assertTrue((self.cache / "omaupdateimpact/v1.2.3/bin").is_dir())

    def test_a_truncated_archive_exits_2(self):
        data = self.archive()
        self.assert_download_failed(self.download(io.BytesIO(data[: len(data) // 2])))

    def test_a_corrupt_archive_exits_2(self):
        data = b"\x1f\x8b\x08\x00" + bytes(6) + b"\xff" * 64
        self.assert_download_failed(self.download(io.BytesIO(data)))

    def test_a_bad_checksum_exits_2(self):
        data = self.archive()
        self.assert_download_failed(self.download(io.BytesIO(data[:-8] + bytes(8))))

    def test_a_page_instead_of_an_archive_exits_2(self):
        self.assert_download_failed(self.download(io.BytesIO(b"<html>Not here</html>")))

    def test_an_empty_download_exits_2(self):
        self.assert_download_failed(self.download(io.BytesIO(b"")))

    def test_a_tar_error_exits_2(self):
        data = gzip.compress(b"not a tar file " * 100)
        self.assert_download_failed(self.download(io.BytesIO(data)))

    def test_an_archive_without_a_release_exits_2(self):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as tar:
            tar.add(self.base / "target/default/hypr/bindings.lua", arcname="bindings.lua")
        self.assert_download_failed(self.download(io.BytesIO(output.getvalue())))

    def test_a_dropped_connection_exits_2(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.side_effect = IncompleteRead(b"")
        self.assert_download_failed(self.download(response))


class ReleasesApi(ProgramCase):
    def test_the_newest_tag_is_downloaded(self):
        api, archive = io.BytesIO(b'[{"tag_name": "v1.2.3"}]'), io.BytesIO(self.archive())
        self.assertEqual(self.download(api, archive, args=())[0], 0)

    def test_bad_answers_exit_2(self):
        for body in (b"", b"not json", b"\xff", b"[]", b"{}", b"[1]", b"[{}]", b'[{"tag_name": null}]'):
            with self.subTest(body=body):
                self.assert_download_failed(self.download(io.BytesIO(body), args=()))


if __name__ == "__main__":
    unittest.main()
