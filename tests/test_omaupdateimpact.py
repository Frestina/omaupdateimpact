import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path

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
    report = impact.Report()
    impact.compare_bindings(parse(current), parse(target), parse(user), report)
    return report


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
        self.assertEqual((parsed.binds, parsed.unread), ({}, 1))


class CompareBindings(unittest.TestCase):
    def test_flags_a_clash_with_a_new_default(self):
        report = compare("", 'o.bind("SUPER + M", "Minimize", "min")', 'o.bind("SUPER + M", "Mail", "mail")')
        self.assertEqual(len(report.attention), 1)
        self.assertIn("clash", report.attention[0])

    def test_no_clash_when_the_user_unbinds_first(self):
        user = 'hl.unbind("SUPER + M")\no.bind("SUPER + M", "Mail", "mail")'
        report = compare("", 'o.bind("SUPER + M", "Minimize", "min")', user)
        self.assertEqual(report.attention, [])

    def test_no_clash_when_the_default_is_unchanged(self):
        same = 'o.bind("SUPER + M", "Minimize", "min")'
        self.assertEqual(compare(same, same, 'o.bind("SUPER + M", "Mail", "mail")').attention, [])

    def test_reports_a_moved_shortcut(self):
        report = compare('o.bind("SUPER + Q", "Calc", "c")', 'o.bind("SUPER + SHIFT + Q", "Calc", "c")')
        self.assertIn('Moved: "Calc" from SUPER + Q to SUPER + SHIFT + Q.', report.notes)

    def test_a_turned_off_shortcut_that_moves_comes_back(self):
        report = compare(
            'o.bind("SUPER + Q", "Calc", "c")',
            'o.bind("SUPER + SHIFT + Q", "Calc", "c")',
            'hl.unbind("SUPER + Q")',
        )
        self.assertIn("comes back", report.attention[0])

    def test_reports_a_shortcut_taken_over_by_another_action(self):
        report = compare('o.bind("SUPER + N", "Night", "n")', 'o.bind("SUPER + N", "Network", "w")')
        self.assertIn('SUPER + N is now "Network", it was "Night".', report.notes)

    def test_reworded_description_with_the_same_command_is_not_a_change(self):
        report = compare('o.bind("SUPER + N", "Old", "n")', 'o.bind("SUPER + N", "New", "n")')
        self.assertEqual((report.attention, report.notes), ([], []))


class Packages(unittest.TestCase):
    def changes(self, migrations, already_run=()):
        with tempfile.TemporaryDirectory() as directory:
            for name, text in migrations.items():
                (Path(directory) / name).write_text(text)
            return impact.package_changes(Path(directory), set(already_run))

    def test_reads_drops(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a b >/dev/null\n"}), {"a": False, "b": False})

    def test_indented_drop_is_conditional(self):
        self.assertEqual(self.changes({"1.sh": "if x; then\n  omarchy-pkg-drop a\nfi\n"}), {"a": True})

    def test_skips_migrations_already_run(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n"}, ["1.sh"]), {})

    def test_a_later_add_cancels_a_drop(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n", "2.sh": "omarchy-pkg-add a\n"}), {})

    def test_ignores_shell_variables(self):
        self.assertEqual(self.changes({"1.sh": 'omarchy-pkg-drop "$pkg"\n'}), {})


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
        report = impact.Report()
        impact.compare_commands(self.base / "current", self.base / "target", self.home, report)
        return report.attention

    def test_finds_a_call_to_a_deleted_command(self):
        (self.hooks / "my.hook").write_text("omarchy-gone\n")
        self.assertEqual(len(self.attention()), 1)

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
            report = impact.Report()
            impact.compare_plugins(Path("current"), Path("target"), home, report)
            self.assertEqual(len(report.notes), 1)
            self.assertIn("1 new qmllint warnings, such as a.qml: new", report.notes[0])


if __name__ == "__main__":
    unittest.main()
