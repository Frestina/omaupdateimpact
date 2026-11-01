import contextlib
import gzip
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from email.message import Message
from http.client import IncompleteRead
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

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
        bind = parse('o.bind("SUPER + W", "Close", "close-it")').binds["SUPER + W"][0]
        self.assertEqual((bind.description, bind.command), ("Close", "close-it"))

    def test_key_order_and_case_do_not_matter(self):
        self.assertIn("SUPER + SHIFT + A", parse('o.bind("shift + super + a", "x", "y")').binds)

    def test_skips_comments_but_not_strings(self):
        parsed = parse('-- o.bind("SUPER + A", "x", "y")\no.bind("SUPER + B", "a -- b", "y")')
        self.assertEqual(list(parsed.binds), ["SUPER + B"])
        self.assertEqual(parsed.binds["SUPER + B"][0].description, "a -- b")

    def test_skips_block_comments(self):
        self.assertEqual(parse('--[[ o.bind("SUPER + A", "x", "y") ]]').binds, {})

    def test_reads_a_call_over_several_lines(self):
        self.assertIn("SUPER + A", parse('o.bind(\n  "SUPER + A",\n  "x",\n  fn(1, 2)\n)').binds)

    def test_expands_toggles(self):
        bind = parse('o.bind_toggle("SUPER + N", "Night", "nightlight")').binds["SUPER + N"][0]
        self.assertEqual(bind.command, "omarchy-toggle-nightlight")

    def test_rebind_counts_as_unbind_and_bind(self):
        parsed = parse('o.rebind("SUPER + A", "x", "y")')
        self.assertIn("SUPER + A", parsed.unbinds)
        self.assertIn("SUPER + A", parsed.binds)

    def test_reads_description_from_hl_bind(self):
        bind = parse('hl.bind("SUPER + A", act(), { description = "Do it" })').binds["SUPER + A"][0]
        self.assertEqual(bind.description, "Do it")

    def test_counts_computed_keys(self):
        parsed = parse('o.bind("SUPER + " .. n, "x", "y")')
        self.assertEqual((parsed.binds, len(parsed.unread)), ({}, 1))

    def test_keeps_the_expression_of_a_computed_key(self):
        self.assertEqual(parse('o.bind("SUPER + " .. n, "x", "y")').unread[0].expression, '"SUPER + "..n')

    def test_spacing_is_not_part_of_a_computed_key(self):
        one, other = parse('o.bind( "SUPER + "  ..\n n, "x", "y")'), parse('o.bind("SUPER + "..n, "x", "y")')
        self.assertEqual(one.unread[0].expression, other.unread[0].expression)

    def test_a_computed_unbind_is_not_the_same_as_a_computed_bind(self):
        one, other = parse('hl.unbind("SUPER + " .. n)'), parse('o.bind("SUPER + " .. n, "x", "y")')
        self.assertNotEqual(one.unread[0].expression, other.unread[0].expression)

    def test_reads_bind_hold(self):
        binds = parse('o.bind_hold("F9", "Start", "rec start", "Stop", "rec stop")').binds["F9"]
        self.assertEqual(
            [(bind.description, bind.command) for bind in binds], [("Start", "rec start"), ("Stop", "rec stop")]
        )

    def test_a_computed_key_in_bind_hold_counts_once(self):
        parsed = parse('o.bind_hold("F" .. n, "Start", "a", "Stop", "b")')
        self.assertEqual((parsed.binds, len(parsed.unread)), ({}, 1))

    def test_press_and_release_on_one_chord_survive(self):
        parsed = parse('o.bind("F9", "Start", "a")\no.bind("F9", "Stop", "b", { release = true })')
        self.assertEqual([bind.description for bind in parsed.binds["F9"]], ["Start", "Stop"])

    def test_an_unbind_removes_the_binds_before_it(self):
        parsed = parse('o.bind("SUPER + A", "x", "y")\nhl.unbind("SUPER + A")')
        self.assertEqual(parsed.binds, {})

    def test_an_unbind_leaves_the_binds_after_it(self):
        self.assertIn("SUPER + A", parse('hl.unbind("SUPER + A")\no.bind("SUPER + A", "x", "y")').binds)

    def test_an_unbind_removes_press_and_release_together(self):
        self.assertEqual(parse('o.bind_hold("F9", "a", "b", "c", "d")\nhl.unbind("F9")').binds, {})

    def test_a_rebind_replaces_what_was_there(self):
        parsed = parse('o.bind("SUPER + A", "x", "y")\no.rebind("SUPER + A", "New", "z")')
        self.assertEqual([bind.description for bind in parsed.binds["SUPER + A"]], ["New"])

    def test_an_unbind_ignores_spaces_and_case(self):
        self.assertEqual(parse('o.bind("ALT + Alt_R", "x", "y")\nhl.unbind("alt+ALT_R")').binds, {})

    def test_an_unbind_goes_by_the_text_and_not_the_chord(self):
        # Hyprland's removeKeybind compares the text the bind was written with.
        for keys in ("CONTROL + A", "SHIFT + SUPER + A"):
            with self.subTest(keys):
                chord = impact.normalize_keys(keys)
                bound = {"CONTROL + A": "CTRL + A", "SHIFT + SUPER + A": "SUPER + SHIFT + A"}[keys]
                self.assertIn(chord, parse(f'o.bind("{bound}", "x", "y")\nhl.unbind("{keys}")').binds)

    def test_unbinding_all_removes_every_bind_so_far(self):
        parsed = parse('o.bind("SUPER + A", "x", "y")\nhl.unbind("all")\no.bind("SUPER + B", "x", "y")')
        self.assertEqual(list(parsed.binds), ["SUPER + B"])

    def test_only_lowercase_all_removes_every_bind(self):
        self.assertIn("SUPER + A", parse('o.bind("SUPER + A", "x", "y")\nhl.unbind("ALL")').binds)

    def test_every_modifier_spelling_is_the_same_key(self):
        for spelled, chord in (
            ("CONTROL + A", "CTRL + A"),
            ("MOD1 + A", "ALT + A"),
            ("WIN + A", "SUPER + A"),
            ("LOGO + A", "SUPER + A"),
            ("MOD4 + A", "SUPER + A"),
            ("META + A", "SUPER + A"),
        ):
            with self.subTest(spelled):
                self.assertEqual(impact.normalize_keys(spelled), chord)

    def test_every_modifier_sorts_ahead_of_the_key(self):
        self.assertEqual(impact.normalize_keys("MOD5 + CAPS + MOD3 + MOD2 + A"), "CAPS + MOD2 + MOD3 + MOD5 + A")

    def test_a_key_named_like_a_modifier_is_still_a_key(self):
        self.assertEqual(impact.normalize_keys("ALT + Alt_R"), "ALT + ALT_R")

    def test_reads_a_table_command_as_one_value(self):
        bind = parse('o.bind("SUPER + A", "x", { webapp = "https://a.example/?b,c", focus = true })').binds[
            "SUPER + A"
        ][0]
        self.assertEqual(bind.command, '{webapp="https://a.example/?b,c",focus=true}')

    def test_the_layout_of_a_table_command_does_not_matter(self):
        one = parse('o.bind("SUPER + A", "x", { webapp = "https://a.example" })').binds["SUPER + A"][0]
        other = parse('o.bind("SUPER + A", "x", {\n  webapp="https://a.example",\n})').binds["SUPER + A"][0]
        self.assertEqual(one.command, other.command)

    def test_a_string_in_a_table_keeps_its_spaces(self):
        bind = parse('o.bind("SUPER + A", "x", { tui = "a  b" })').binds["SUPER + A"][0]
        self.assertIn('"a  b"', bind.command)

    def test_reads_long_strings_as_literals(self):
        for text, command in (
            ("[[run it]]", "run it"),
            ("[[\nrun it]]", "run it"),
            ("""[[say "it's, fine"]]""", """say "it's, fine\""""),
            ("[==[a ]] b]==]", "a ]] b"),
        ):
            with self.subTest(text):
                bind = parse(f'o.bind("SUPER + A", "x", {text})').binds["SUPER + A"][0]
                self.assertEqual(bind.command, command)

    def test_reads_a_long_string_key(self):
        self.assertIn("SUPER + A", parse('o.bind([[SUPER + A]], "x", "y")').binds)

    def test_an_unclosed_long_string_is_not_a_literal(self):
        self.assertIsNone(impact.literal("[[run it"))

    def test_skips_block_comments_over_several_lines(self):
        for opened, closed in (("--[[", "]]"), ("--[==[", "]==]")):
            with self.subTest(opened):
                text = f'{opened}\no.bind("SUPER + A", "x", "y")\n{closed}\no.bind("SUPER + B", "x", "y")'
                self.assertEqual(list(parse(text).binds), ["SUPER + B"])

    def test_skips_block_comments_with_levels(self):
        self.assertEqual(parse('--[==[ ]] o.bind("SUPER + A", "x", "y") ]==]').binds, {})

    def test_a_long_string_may_hold_a_comment_marker(self):
        bind = parse('o.bind("SUPER + A", "x", [==[a -- b]==])').binds["SUPER + A"][0]
        self.assertEqual(bind.command, "a -- b")


class BindingHelpers(unittest.TestCase):
    def helpers(self, text):
        parsed = impact.Parsed()
        impact.parse_helpers(text, parsed, "default/hypr/helpers.lua")
        return parsed.helpers

    def test_names_a_helper_with_no_rule(self):
        self.assertEqual(
            self.helpers("function o.bind_foo(keys)\nend"), {"o.bind_foo": "default/hypr/helpers.lua"}
        )

    def test_finds_other_ways_to_define_a_helper(self):
        for text in (
            "o.bind_foo = function(keys) end",
            "o.bind_foo = local_bind",
            "function o:bind_foo(keys) end",
            "function o.keys.bind_foo(keys) end",
            "function o.keyBind(keys) end",
        ):
            with self.subTest(text):
                self.assertEqual(len(self.helpers(text)), 1)

    def test_every_helper_in_a_release_has_a_rule(self):
        text = """
        function o.bind(keys) end
        function o.rebind(keys) end
        function o.bind_toggle(keys) end
        function o.bind_hold(keys) end
        function o.preinstalled_bindings_enabled() end
        function o.launch(command) end
        """
        self.assertEqual(self.helpers(text), {})

    def test_tables_of_binds_are_not_helpers(self):
        self.assertEqual(self.helpers("o.bind_commands = {}\no.bind_expressions = {}\no.bind_commands[f] = c"), {})

    def test_a_helper_in_a_comment_is_not_a_helper(self):
        self.assertEqual(self.helpers("-- function o.bind_foo(keys)"), {})

    def test_an_unknown_helper_is_unknown_and_named(self):
        parsed = impact.Parsed()
        impact.parse_helpers("function o.bind_foo(keys) end", parsed, "default/hypr/helpers.lua")
        findings = impact.compare_bindings(impact.Parsed(), parsed, impact.Parsed())
        self.assertIn("o.bind_foo", titles(findings, "unknown")[0])
        self.assertEqual(findings[0].evidence, ["default/hypr/helpers.lua"])

    def test_a_helper_only_in_the_installed_tree_is_unknown(self):
        current = impact.Parsed()
        impact.parse_helpers("function o.bind_foo(keys) end", current, "default/hypr/helpers.lua")
        findings = impact.compare_bindings(current, impact.Parsed(), impact.Parsed())
        self.assertIn("o.bind_foo", titles(findings, "unknown")[0])

    def test_a_helper_in_both_versions_is_one_finding(self):
        current, target = impact.Parsed(), impact.Parsed()
        impact.parse_helpers("function o.bind_foo(keys) end", current, "default/hypr/helpers.lua")
        impact.parse_helpers("function o.bind_foo(keys) end", target, "default/hypr/helpers.lua")
        self.assertEqual(len(impact.compare_bindings(current, target, impact.Parsed())), 1)


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

    def test_an_unchanged_computed_key_is_a_note(self):
        computed = 'o.bind("SUPER + " .. n, "x", "y")'
        findings = compare(computed, computed)
        self.assertEqual(titles(findings, "unknown"), [])
        self.assertIn("1 key bindings", titles(findings, "note")[0])

    def test_a_computed_call_in_both_versions_counts_once(self):
        computed = 'o.bind("SUPER + " .. n, "x", "y")\nhl.bind(key:upper(), act(), {})'
        self.assertIn("2 key bindings", titles(compare(computed, computed), "note")[0])

    def test_a_computed_key_may_change_file_and_action(self):
        current, target = impact.Parsed(), impact.Parsed()
        impact.parse_lua('o.bind("SUPER + " .. n, "x", "y")', current, "default/hypr/old.lua")
        impact.parse_lua('o.bind("SUPER + " .. n, "z", "w")', target, "default/hypr/new.lua")
        findings = impact.compare_bindings(current, target, impact.Parsed())
        self.assertEqual(titles(findings, "unknown"), [])
        self.assertEqual(findings[0].evidence, ["default/hypr/new.lua", "default/hypr/old.lua"])

    def test_a_changed_computed_key_is_unknown(self):
        findings = compare('o.bind("SUPER + " .. n, "x", "y")', 'o.bind("SUPER + ALT + " .. n, "x", "y")')
        self.assertEqual(len(titles(findings, "unknown")), 2)
        self.assertEqual(titles(findings, "note"), [])
        self.assertIn('"SUPER + ALT + "..n', titles(findings, "unknown")[1])

    def test_a_new_computed_key_is_unknown(self):
        self.assertEqual(len(titles(compare("", 'o.bind("SUPER + " .. n, "x", "y")'), "unknown")), 1)

    def test_a_second_call_with_the_same_key_is_unknown(self):
        computed = 'o.bind("SUPER + " .. n, "x", "y")\n'
        findings = compare(computed, computed * 2)
        self.assertEqual(len(titles(findings, "unknown")), 1)
        self.assertIn("1 key bindings", titles(findings, "note")[0])

    def test_a_computed_key_of_the_users_is_unknown(self):
        findings = compare("", "", 'o.bind("SUPER + " .. n, "x", "y")')
        self.assertIn('"SUPER + "..n', titles(findings, "unknown")[0])

    def test_a_computed_unbind_of_the_users_is_unknown(self):
        self.assertEqual(len(titles(compare("", "", 'hl.unbind("SUPER + " .. n)'), "unknown")), 1)

    def test_a_computed_key_of_the_users_names_its_file(self):
        user = impact.Parsed()
        impact.parse_lua('o.bind("SUPER + " .. n, "x", "y")', user, "~/.config/hypr/bindings.lua")
        finding = impact.compare_bindings(impact.Parsed(), impact.Parsed(), user)[0]
        self.assertEqual(finding.evidence, ["~/.config/hypr/bindings.lua"])

    def test_a_press_and_release_moved_to_bind_hold_has_not_gone(self):
        current = """
        o.bind("F9", "Start dictation (push-to-talk)", "voxtype record start")
        o.bind("F9", "Stop dictation (push-to-talk)", "voxtype record stop", { release = true })
        """
        target = """
        o.bind_hold("F9", "Start dictation (push-to-talk)", "omarchy-dictation start",
          "Stop dictation (push-to-talk)", "omarchy-dictation stop")
        """
        self.assertEqual(compare(current, target), [])

    def test_a_clash_with_a_modifier_key(self):
        target = 'o.bind_hold("ALT + Alt_R", "Start", "a", "Stop", "b", { ignore_mods = true })'
        findings = compare("", target, 'o.bind("ALT + Alt_R", "Mine", "m")')
        self.assertIn("ALT + ALT_R", titles(findings, "attention")[0])
        self.assertIn("Start / Stop", titles(findings, "attention")[0])
        self.assertEqual(findings[0].fix, 'Add hl.unbind("ALT + Alt_R") or choose another key.')

    def test_a_clash_across_modifier_spellings(self):
        findings = compare("", 'o.bind("CONTROL + A", "New", "n")', 'o.bind("CTRL + A", "Mine", "m")')
        self.assertEqual(len(titles(findings, "attention")), 1)

    def test_a_fix_spells_the_keys_the_way_the_default_does(self):
        findings = compare("", 'o.bind("CONTROL + A", "New", "n")', 'o.bind("CTRL + A", "Mine", "m")')
        self.assertEqual(findings[0].fix, 'Add hl.unbind("CONTROL + A") or choose another key.')

    def test_a_fix_names_each_way_a_default_is_spelled(self):
        target = 'o.bind("CONTROL + A", "New", "n")\no.bind("CTRL + A", "Other", "o")'
        findings = compare("", target, 'o.bind("CTRL + A", "Mine", "m")')
        self.assertIn('hl.unbind("CONTROL + A") and hl.unbind("CTRL + A")', findings[0].fix)

    def test_an_unbind_spelled_differently_does_not_hide_a_clash(self):
        user = 'hl.unbind("CTRL + A")\no.bind("CTRL + A", "Mine", "m")'
        findings = compare("", 'o.bind("CONTROL + A", "New", "n")', user)
        self.assertEqual(len(titles(findings, "attention")), 1)

    def test_an_unbind_of_one_spelling_leaves_the_other_clashing(self):
        target = 'o.bind("CONTROL + A", "New", "n")\no.bind("CTRL + A", "Other", "o")'
        user = 'hl.unbind("CTRL + A")\no.bind("CTRL + A", "Mine", "m")'
        self.assertEqual(len(titles(compare("", target, user), "attention")), 1)

    def test_a_shortcut_that_was_never_turned_off_does_not_come_back(self):
        findings = compare(
            'o.bind("CTRL + Q", "Calc", "c")', 'o.bind("CTRL + W", "Calc", "c")', 'hl.unbind("CONTROL + Q")'
        )
        self.assertEqual(titles(findings, "attention"), [])

    def test_a_press_alone_is_not_a_press_and_release_pair(self):
        current = 'o.bind_hold("F9", "Start", "a", "Stop", "b")'
        findings = compare(current, 'o.bind("F9", "Start", "a")')
        self.assertIn('F9 is now "Start", it was "Start / Stop".', titles(findings, "note"))

    def test_a_press_that_becomes_a_press_and_release_pair_is_a_change(self):
        findings = compare('o.bind("F9", "Start", "a")', 'o.bind_hold("F9", "Start", "a", "Stop", "b")')
        self.assertIn('F9 is now "Start / Stop", it was "Start".', titles(findings, "note"))

    def test_a_removed_default_you_turned_off_is_not_listed_as_removed(self):
        findings = compare('o.bind("SUPER + Q", "Calc", "c")', "", 'hl.unbind("SUPER + Q")')
        self.assertEqual(
            titles(findings, "note"), ["SUPER + Q: your unbind no longer does anything, the default is gone."]
        )

    def test_no_replaces_note_on_a_chord_you_did_not_turn_off(self):
        findings = compare(
            'o.bind("CTRL + A", "Old", "o")',
            'o.bind("CONTROL + A", "New", "n")',
            'hl.unbind("CTRL + A")\no.bind("CTRL + A", "Mine", "m")',
        )
        self.assertEqual(len(titles(findings, "attention")), 1)
        self.assertEqual(titles(findings, "note"), [])

    def test_a_default_that_unbinds_its_own_key_is_gone(self):
        findings = compare('o.bind("SUPER + Q", "Calc", "c")', 'o.bind("SUPER + Q", "Calc", "c")\nhl.unbind("SUPER + Q")')
        self.assertIn('Default shortcuts removed: SUPER + Q ("Calc").', titles(findings, "note"))

    def test_a_default_rebind_is_a_new_action(self):
        target = 'o.bind("SUPER + Q", "Calc", "c")\no.rebind("SUPER + Q", "Quit", "q")'
        findings = compare('o.bind("SUPER + Q", "Calc", "c")', target)
        self.assertIn('SUPER + Q is now "Quit", it was "Calc".', titles(findings, "note"))

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

    def test_unbinding_both_ends_of_a_move_keeps_it_off(self):
        findings = compare(
            'o.bind("SUPER + Q", "Calc", "c")',
            'o.bind("SUPER + SHIFT + Q", "Calc", "c")',
            'hl.unbind("SUPER + Q")\nhl.unbind("SUPER + SHIFT + Q")',
        )
        self.assertEqual(titles(findings, "attention"), [])
        self.assertEqual(titles(findings, "note"), ['Moved: "Calc" from SUPER + Q to SUPER + SHIFT + Q.'])

    def test_a_shortcut_comes_back_when_its_new_keys_are_unbound_in_another_spelling(self):
        findings = compare(
            'o.bind("SUPER + Q", "Calc", "c")',
            'o.bind("SUPER + SHIFT + Q", "Calc", "c")',
            'hl.unbind("SUPER + Q")\nhl.unbind("SHIFT + SUPER + Q")',
        )
        self.assertIn("comes back", titles(findings, "attention")[0])

    def test_the_moved_fix_spells_the_keys_the_way_the_default_does(self):
        findings = compare(
            'o.bind("CTRL + Q", "Calc", "c")', 'o.bind("CONTROL + W", "Calc", "c")', 'hl.unbind("CTRL + Q")'
        )
        self.assertEqual(findings[0].fix, "Unbind CONTROL + W too.")

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
    def read(self, migrations, already_run=()):
        with tempfile.TemporaryDirectory() as directory:
            for name, text in migrations.items():
                (Path(directory) / name).write_text(text)
            return impact.package_changes(Path(directory), set(already_run))

    def changes(self, migrations, already_run=()):
        return self.read(migrations, already_run)[0]

    def script(self, text):
        return self.changes({"1.sh": text})

    def unread(self, text):
        return self.read({"1.sh": text})[1]

    def test_reads_drops(self):
        self.assertEqual(self.script("omarchy-pkg-drop a b >/dev/null\n"), {"a": (False, "1.sh"), "b": (False, "1.sh")})

    def test_an_if_makes_a_drop_conditional(self):
        self.assertEqual(self.script("if x; then\n  omarchy-pkg-drop a\nfi\n"), {"a": (True, "1.sh")})

    def test_a_drop_on_one_line_inside_an_if_is_conditional(self):
        self.assertEqual(self.script("if x; then omarchy-pkg-drop f; fi\n"), {"f": (True, "1.sh")})

    def test_indentation_says_nothing(self):
        self.assertEqual(self.script("if x; then\nomarchy-pkg-drop a\nfi\n  omarchy-pkg-drop b\n"), {"a": (True, "1.sh"), "b": (False, "1.sh")})

    def test_after_an_if_a_drop_is_certain(self):
        self.assertEqual(self.script("if x; then y; fi\nomarchy-pkg-drop a\n"), {"a": (False, "1.sh")})

    def test_after_and_a_drop_is_conditional(self):
        self.assertEqual(self.script("x && omarchy-pkg-drop b\n"), {"b": (True, "1.sh")})

    def test_after_or_a_drop_is_conditional(self):
        self.assertEqual(self.script("x || omarchy-pkg-drop b\n"), {"b": (True, "1.sh")})

    def test_and_carries_over_a_line_break(self):
        self.assertEqual(self.script("x &&\n  omarchy-pkg-drop b\n"), {"b": (True, "1.sh")})

    def test_a_new_command_ends_an_and(self):
        self.assertEqual(self.script("x && y; omarchy-pkg-drop a\nx && y\nomarchy-pkg-drop b\n"), {"a": (False, "1.sh"), "b": (False, "1.sh")})

    def test_a_drop_before_and_or_or_is_certain(self):
        self.assertEqual(self.script("omarchy-pkg-drop a && echo ok\nomarchy-pkg-drop b || true\n"), {"a": (False, "1.sh"), "b": (False, "1.sh")})

    def test_a_group_after_and_is_conditional(self):
        self.assertEqual(self.script("x && { omarchy-pkg-drop a; omarchy-pkg-drop b; }\n"), {"a": (True, "1.sh"), "b": (True, "1.sh")})

    def test_a_plain_group_is_certain(self):
        self.assertEqual(self.script("{ omarchy-pkg-drop a; }\n(omarchy-pkg-drop b)\n"), {"a": (False, "1.sh"), "b": (False, "1.sh")})

    def test_a_loop_is_conditional(self):
        self.assertEqual(self.script("while x; do\n  omarchy-pkg-drop a\ndone\n"), {"a": (True, "1.sh")})

    def test_a_loop_list_is_not_a_command(self):
        self.assertEqual(self.read({"1.sh": "for x in fi done if; do y; done\nomarchy-pkg-drop a\n"}), ({"a": (False, "1.sh")}, set()))

    def test_arithmetic_is_not_a_block(self):
        text = "for ((i = 0; i < 3; i++)); do\n  y\ndone\nif ((x > 0)); then y; fi\nomarchy-pkg-drop a\n"
        self.assertEqual(self.read({"1.sh": text}), ({"a": (False, "1.sh")}, set()))

    def test_an_elif_is_conditional(self):
        self.assertEqual(self.script("if x; then y\nelif z; then\n  omarchy-pkg-drop a\nelse\n  omarchy-pkg-drop b\nfi\n"), {"a": (True, "1.sh"), "b": (True, "1.sh")})

    def test_a_case_is_conditional(self):
        text = 'case "$x" in\n  a|b) omarchy-pkg-drop c ;;\n  *)\n    omarchy-pkg-drop d\n    ;;\nesac\nomarchy-pkg-drop e\n'
        self.assertEqual(self.script(text), {"c": (True, "1.sh"), "d": (True, "1.sh"), "e": (False, "1.sh")})

    def test_a_case_on_one_line(self):
        self.assertEqual(self.read({"1.sh": "case x in a) omarchy-pkg-drop c;; esac\n"}), ({"c": (True, "1.sh")}, set()))

    def test_a_function_is_conditional(self):
        self.assertEqual(self.script("old() {\n  omarchy-pkg-drop a\n}\nfunction older {\n  omarchy-pkg-drop b\n}\nold\n"), {"a": (True, "1.sh"), "b": (True, "1.sh")})

    def test_a_substitution_runs(self):
        self.assertEqual(self.script('log=$(omarchy-pkg-drop a 2>&1)\necho "$(omarchy-pkg-drop b)"\necho `omarchy-pkg-drop c`\n'), {"a": (False, "1.sh"), "b": (False, "1.sh"), "c": (False, "1.sh")})

    def test_a_substitution_in_a_substitution_runs(self):
        self.assertEqual(self.script('echo "$(x "$(omarchy-pkg-drop a)")"\n'), {"a": (False, "1.sh")})

    def test_a_substitution_after_and_is_conditional(self):
        self.assertEqual(self.script("x && log=$(omarchy-pkg-drop a)\n"), {"a": (True, "1.sh")})

    def test_process_substitution_runs(self):
        self.assertEqual(self.script("while read -r x; do y; done < <(omarchy-pkg-drop a)\n"), {"a": (True, "1.sh")})

    def test_a_list_continued_with_a_backslash(self):
        self.assertEqual(self.script("omarchy-pkg-drop a \\\n  b \\\n  c\n"), {"a": (False, "1.sh"), "b": (False, "1.sh"), "c": (False, "1.sh")})

    def test_a_redirect_is_not_a_package(self):
        self.assertEqual(self.script("omarchy-pkg-drop a 2>/dev/null\n"), {"a": (False, "1.sh")})

    def test_every_redirect_is_dropped(self):
        for redirect in (">/dev/null", "> /dev/null", ">>log", "2>&1", "&>/dev/null", "&>>log", "</dev/null", '<<<"$x"', "2> err"):
            self.assertEqual(self.read({"1.sh": f"omarchy-pkg-drop a {redirect}\n"}), ({"a": (False, "1.sh")}, set()), redirect)

    def test_a_heredoc_is_not_a_command(self):
        for opening, closing in (("<<EOF", "EOF"), ("<<'EOF'", "EOF"), ('<<"EOF"', "EOF"), ("<<-EOF", "\tEOF")):
            text = f"cat {opening}\nomarchy-pkg-drop a\n{closing}\nomarchy-pkg-drop b\n"
            self.assertEqual(self.script(text), {"b": (False, "1.sh")}, opening)

    def test_a_heredoc_in_a_substitution_is_not_a_command(self):
        text = "x=$(cat <<'PY'\nprint(')\nomarchy-pkg-drop a\nPY\n)\nomarchy-pkg-drop b\n"
        self.assertEqual(self.read({"1.sh": text}), ({"b": (False, "1.sh")}, set()))

    def test_a_shift_is_not_a_heredoc(self):
        self.assertEqual(self.script("((x = 1 << 3))\ny=$((1 << 3))\nomarchy-pkg-drop a\n"), {"a": (False, "1.sh")})

    def test_text_is_not_a_command(self):
        text = (
            "# omarchy-pkg-drop a\n"
            "echo omarchy-pkg-drop b\n"
            'echo "remove it with: omarchy-pkg-drop c"\n'
            "x='omarchy-pkg-drop d'\n"
            "grep omarchy-pkg-drop file\n"
            "command -v omarchy-pkg-drop\n"
            '[[ -x omarchy-pkg-drop ]] && [ -x omarchy-pkg-drop ]\n'
            "command -V omarchy-pkg-drop\n"
            "printf '%s\\n' omarchy-pkg-drop e\n"
            "pacman -Q omarchy-pkg-drop-f\n"
        )
        self.assertEqual(self.read({"1.sh": text}), ({}, set()))

    def test_an_array_is_not_a_command(self):
        self.assertEqual(self.read({"1.sh": "words=(if for\n  # it's a list\n  'a)' omarchy-pkg-drop\n)\nomarchy-pkg-drop a\n"}), ({"a": (False, "1.sh")}, set()))

    def test_a_comment_ends_the_list(self):
        self.assertEqual(self.script("omarchy-pkg-drop a # b\n"), {"a": (False, "1.sh")})

    def test_a_quoted_package_is_read(self):
        self.assertEqual(self.script("omarchy-pkg-drop \"a\" 'b'\n"), {"a": (False, "1.sh"), "b": (False, "1.sh")})

    def test_a_hash_inside_a_word_is_no_comment(self):
        self.assertEqual(self.script('x=${#y[@]} z=a#b omarchy-pkg-drop a\n'), {"a": (False, "1.sh")})

    def test_reads_pacman_removals(self):
        for command in ("pacman -R a", "pacman -Rns a", "sudo pacman -Rns --noconfirm a", "pacman --noconfirm -Rdd a", "pacman --remove a", "sudo -n pacman -Rs a", "yay -Rns a", "paru -R a", "as_root pacman -Rns a", "pacman -Rns -- a"):
            self.assertEqual(self.read({"1.sh": f"{command}\n"}), ({"a": (False, "1.sh")}, set()), command)

    def test_a_command_given_by_path_counts(self):
        for command in ("sudo /usr/bin/pacman -Rns a", "$OMARCHY_PATH/bin/omarchy-pkg-drop a", '"$OMARCHY_PATH/bin/omarchy-pkg-drop" a', '"${OMARCHY_PATH}/bin/omarchy-pkg-drop" a'):
            self.assertEqual(self.read({"1.sh": f"{command}\n"}), ({"a": (False, "1.sh")}, set()), command)

    def test_the_omarchy_command_reaches_the_helpers(self):
        self.assertEqual(self.script("omarchy pkg drop a\n"), {"a": (False, "1.sh")})
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n", "2.sh": "omarchy pkg add a\n"}), {})
        self.assertEqual(self.read({"1.sh": "omarchy theme set a\n"}), ({}, set()))

    def test_plain_command_runs_what_it_names(self):
        for command in ("command omarchy-pkg-drop a", "command sudo pacman -Rns a"):
            self.assertEqual(self.read({"1.sh": f"{command}\n"}), ({"a": (False, "1.sh")}, set()), command)

    def test_a_removal_in_a_string_is_unknown(self):
        for command in ("bash -c 'omarchy-pkg-drop a'", "sudo sh -c 'pacman -Rns a'", 'eval "omarchy-pkg-drop a"', "bash -lc 'yay -R a'", "bash -c 'omarchy pkg drop a'"):
            self.assertEqual(self.read({"1.sh": f"{command}\n"}), ({}, {"1.sh"}), command)

    def test_a_string_with_no_removal_is_no_limit(self):
        for command in ("bash -c 'pacman -Q a'", "eval \"$x\"", "echo bash -c 'omarchy-pkg-drop a'", 'echo "it holds: omarchy-pkg-drop a"'):
            self.assertEqual(self.read({"1.sh": f"{command}\n"}), ({}, set()), command)

    def test_an_apostrophe_in_quoted_expansions_is_a_letter(self):
        text = 'echo "${x:-it\'s}"\nomarchy-pkg-drop a\necho "${y:-that\'s}"\n'
        self.assertEqual(self.read({"1.sh": text}), ({"a": (False, "1.sh")}, set()))

    def test_an_unquoted_expansion_keeps_its_quotes(self):
        self.assertEqual(self.read({"1.sh": "value=${value#'boot():'}\nomarchy-pkg-drop a\n"}), ({"a": (False, "1.sh")}, set()))

    def test_other_pacman_commands_are_not_removals(self):
        for command in ("pacman -Qq a", "sudo pacman -S a", "pacman -Syu", "sudo pacman -D --asexplicit a", "pacman -Rs --print a", "pacman -Rsp a", "pacman -R --print-format %n a", "sudo pacman-key --list-keys a"):
            self.assertEqual(self.read({"1.sh": f"{command}\n"}), ({}, set()), command)

    def test_skips_migrations_already_run(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n"}, ["1.sh"]), {})

    def test_a_later_add_cancels_a_drop(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n", "2.sh": "omarchy-pkg-add a\n"}), {})

    def test_a_later_aur_add_cancels_a_drop(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n", "2.sh": "omarchy-pkg-aur-add a\n"}), {})

    def test_a_drop_after_an_add_stands(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-add a\n", "2.sh": "omarchy-pkg-drop a\n"}), {"a": (False, "2.sh")})

    def test_a_conditional_add_leaves_a_possible_removal(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n", "2.sh": "x && omarchy-pkg-add a\n"}), {"a": (True, "1.sh")})

    def test_a_certain_drop_stays_certain_after_a_conditional_one(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n", "2.sh": "x && omarchy-pkg-drop a\n"}), {"a": (False, "1.sh")})

    def test_a_certain_add_still_cancels_after_both(self):
        self.assertEqual(self.changes({"1.sh": "omarchy-pkg-drop a\n", "2.sh": "x && omarchy-pkg-drop a\n", "3.sh": "omarchy-pkg-add a\n"}), {})

    def test_an_add_with_a_variable_is_no_limit(self):
        self.assertEqual(self.read({"1.sh": 'omarchy-pkg-add "$kernel"\n'}), ({}, set()))

    def test_an_argument_it_cant_read_is_unknown(self):
        for command in ('omarchy-pkg-drop "$pkg"', 'sudo pacman -Rns "${targets[@]}"', "omarchy-pkg-drop $(list)", "omarchy-pkg-drop a-*", "omarchy-pkg-drop a{b,c}"):
            self.assertEqual(self.unread(f"{command}\n"), {"1.sh"}, command)

    def test_a_removal_with_nothing_named_is_unknown(self):
        for command in ("list | xargs omarchy-pkg-drop", "pacman -Qdtq | sudo pacman -Rns -", "list | xargs sudo pacman -Rns --noconfirm"):
            self.assertEqual(self.unread(f"{command}\n"), {"1.sh"}, command)

    def test_a_readable_package_beside_an_unreadable_one_is_kept(self):
        self.assertEqual(self.read({"1.sh": 'omarchy-pkg-drop a "$b"\n'}), ({"a": (False, "1.sh")}, {"1.sh"}))

    def test_a_script_it_loses_its_place_in_is_unknown(self):
        for text in ("x='open\n", 'x="open\n', "cat <<EOF\nno end\n", "x=$(open\n", "if x; then\n", "fi\n", "y)\n", "x=${open\n", "[[ open\n", "case x in\n", "x=`open\nomarchy-pkg-drop a\n"):
            self.assertEqual(self.unread(text), {"1.sh"}, text)

    def test_every_unreadable_argument_is_one_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "migrations").mkdir()
            (target / "migrations/1.sh").write_text('omarchy-pkg-drop "$a" "$b"\nsudo pacman -Rns "${c[@]}"\n')
            findings = impact.compare_packages(target, target, set())
        self.assertEqual([(finding.level, finding.evidence) for finding in findings], [("unknown", ["migrations/1.sh"])])

    def test_an_unreadable_migration_already_run_is_no_limit(self):
        self.assertEqual(self.read({"1.sh": 'omarchy-pkg-drop "$a"\n'}, ["1.sh"]), ({}, set()))

    def test_the_removals_of_a_real_release_stay_the_same(self):
        migrations = Path(__file__).parent / "fixtures/v4.5.0-rc2-migrations"
        expected = {
            "dua-cli": (False, "1791345484.sh"),
            "elsewhen": (False, "1790528634.sh"),
            "linux-n1x": (True, "1791077437.sh"),
            "linux-n1x-headers": (True, "1791077437.sh"),
            "satty": (False, "1788129995.sh"),
            "tensaku": (False, "1788129995.sh"),
            "usbguard": (True, "1791769486.sh"),
            "yt6801-dkms": (True, "1788279117.sh"),
        }
        self.assertEqual(impact.package_changes(migrations, set()), (expected, set()))

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


class ReachedFiles(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tree = Path(directory.name) / "tree"
        (self.tree / "bin").mkdir(parents=True)
        (self.tree / "migrations").mkdir()
        (self.tree / "install").mkdir()

    def command(self, name, text):
        (self.tree / "bin" / name).write_text(f"#!/bin/bash\n{text}")

    def read(self, text, already_run=()):
        (self.tree / "migrations/1.sh").write_text(text)
        return impact.package_changes(self.tree / "migrations", set(already_run))

    def test_a_removal_in_a_command_may_happen_and_names_both_files(self):
        self.command("omarchy-tool", "omarchy-pkg-drop a\n")
        self.assertEqual(self.read("omarchy-tool\n"), ({"a": (True, "1.sh", "bin/omarchy-tool")}, set()))

    def test_the_finding_names_both_files(self):
        self.command("omarchy-tool", "omarchy-pkg-drop a\n")
        (self.tree / "migrations/1.sh").write_text("omarchy-tool\n")
        finding = impact.compare_packages(self.tree, self.tree, {"a"})[0]
        self.assertEqual(finding.evidence, ["migrations/1.sh", "bin/omarchy-tool"])
        self.assertIn("may remove a", finding.title)

    def test_a_command_given_by_path_is_followed(self):
        self.command("omarchy-tool", "omarchy-pkg-drop a\n")
        self.assertEqual(self.read('"$OMARCHY_PATH/bin/omarchy-tool" go\n')[0], {"a": (True, "1.sh", "bin/omarchy-tool")})

    def test_a_command_reached_through_a_command_is_followed(self):
        self.command("omarchy-first", "omarchy-second\n")
        self.command("omarchy-second", "omarchy-pkg-drop a\n")
        self.assertEqual(self.read("omarchy-first\n"), ({"a": (True, "1.sh", "bin/omarchy-second")}, set()))

    def test_a_loop_of_commands_finishes(self):
        self.command("omarchy-first", "omarchy-second\nomarchy-first\n")
        self.command("omarchy-second", "omarchy-first\nomarchy-pkg-drop a\n")
        self.assertEqual(self.read("omarchy-first\n")[0], {"a": (True, "1.sh", "bin/omarchy-second")})

    def test_a_migration_that_sources_itself_finishes(self):
        self.assertEqual(self.read('source "$OMARCHY_PATH/migrations/1.sh"\nomarchy-pkg-drop a\n'), ({"a": (False, "1.sh")}, set()))

    def test_the_helpers_are_not_read(self):
        self.command("omarchy-pkg-drop", 'pacman -Rns "${installed[@]}"\n')
        self.assertEqual(self.read("omarchy-pkg-drop a\n"), ({"a": (False, "1.sh")}, set()))

    def test_a_command_only_looked_up_is_not_followed(self):
        self.command("omarchy-tool", "omarchy-pkg-drop a\n")
        self.assertEqual(self.read("command -v omarchy-tool\necho omarchy-tool\n"), ({}, set()))

    def test_a_sourced_script_is_read(self):
        (self.tree / "install/x.sh").write_text("omarchy-pkg-drop a\n")
        for command in ('source "$OMARCHY_PATH/install/x.sh"', '. "$OMARCHY_PATH/install/x.sh"', 'sudo bash "$OMARCHY_PATH/install/x.sh"', 'source "${OMARCHY_PATH}/install/x.sh"'):
            self.assertEqual(self.read(f"{command}\n"), ({"a": (True, "1.sh", "install/x.sh")}, set()), command)

    def test_a_copied_script_is_not_read(self):
        (self.tree / "install/x.sh").write_text("omarchy-pkg-drop a\n")
        self.assertEqual(self.read('cp "$OMARCHY_PATH/install/x.sh" /tmp\n'), ({}, set()))

    def test_a_sourced_migration_already_run_counts(self):
        (self.tree / "migrations/0.sh").write_text("omarchy-pkg-drop a\n")
        found = self.read('source "$OMARCHY_PATH/migrations/0.sh"\n', ["0.sh"])
        self.assertEqual(found, ({"a": (True, "1.sh", "migrations/0.sh")}, set()))

    def test_a_file_outside_the_tree_is_not_read(self):
        (self.tree.parent / "outside.sh").write_text("omarchy-pkg-drop a\n")
        self.assertEqual(self.read('source "$OMARCHY_PATH/../outside.sh"\n'), ({}, set()))

    def test_an_add_in_a_reached_file_cancels_nothing(self):
        self.command("omarchy-tool", "omarchy-pkg-add a\n")
        self.assertEqual(self.read("omarchy-pkg-drop a\nomarchy-tool\n")[0], {"a": (False, "1.sh")})

    def test_a_reached_drop_keeps_a_certain_drop_certain(self):
        self.command("omarchy-tool", "omarchy-pkg-drop a\n")
        self.assertEqual(self.read("omarchy-pkg-drop a\nomarchy-tool\n")[0], {"a": (False, "1.sh")})

    def test_a_certain_add_cancels_a_reached_drop(self):
        self.command("omarchy-tool", "omarchy-pkg-drop a\n")
        self.assertEqual(self.read("omarchy-tool\nomarchy-pkg-add a\n")[0], {})

    def test_a_hidden_argument_in_a_reached_file_is_unknown(self):
        self.command("omarchy-tool", 'omarchy-pkg-drop "$1"\n')
        self.assertEqual(self.read("omarchy-tool\n"), ({}, {"1.sh"}))

    def test_a_reached_file_that_loses_the_reader_is_unknown(self):
        self.command("omarchy-tool", "x='open\n")
        self.assertEqual(self.read("omarchy-tool\n"), ({}, {"1.sh"}))

    def test_a_python_file_that_names_a_removal_is_unknown(self):
        for line in ('run(["pacman", "-Rns", name])', 'run("omarchy-pkg-drop " + name)'):
            (self.tree / "bin/omarchy-tool").write_text(f"#!/usr/bin/python3\n{line}\n")
            self.assertEqual(self.read("omarchy-tool\n"), ({}, {"1.sh"}), line)

    def test_a_python_file_with_no_removal_gives_nothing(self):
        (self.tree / "bin/omarchy-tool").write_text("#!/usr/bin/python3\nprint('it isn\\'t $(shell')\n")
        self.assertEqual(self.read("omarchy-tool\n"), ({}, set()))

    def test_a_shebang_with_a_flag_is_shell(self):
        (self.tree / "bin/omarchy-tool").write_text("#!/bin/bash -p\nomarchy-pkg-drop a\n")
        self.assertEqual(self.read("omarchy-tool\n")[0], {"a": (True, "1.sh", "bin/omarchy-tool")})


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


class Terminal(io.StringIO):
    def isatty(self):
        return True


def refused(code, **headers):
    """An HTTP error from GitHub, as urllib raises it."""
    message = Message()
    for name, value in headers.items():
        message[name.replace("_", "-")] = value
    return HTTPError("https://github.invalid/", code, "Refused", message, io.BytesIO())


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
        os.environ.pop("GITHUB_TOKEN", None)
        self.terminal = False

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
        out, err = io.StringIO(), Terminal() if self.terminal else io.StringIO()
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

    def test_a_removal_it_cant_read_exits_3_and_names_the_migration(self):
        (self.base / "target/migrations/1.sh").write_text('sudo pacman -Rns "${targets[@]}"\n')
        code, out, _ = self.check(packages={"a"})
        self.assertEqual(code, 3)
        self.assertIn("migrations/1.sh", out)
        self.assertIn("These checks didn't run: packages.", out)
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


class Bindings(ProgramCase):
    def setUp(self):
        super().setUp()
        (self.home / ".config/hypr").mkdir(parents=True)
        self.bindings = self.home / ".config/hypr/bindings.lua"

    def assert_unreadable(self):
        code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertIn("bindings.lua couldn't be read", " ".join(out.split()))
        self.assertIn("These checks didn't run: bindings.", out)

    def test_no_bindings_file_is_fine(self):
        self.assertEqual(self.check()[0], 0)

    def test_a_broken_link_is_unknown(self):
        self.bindings.symlink_to(self.base / "missing.lua")
        self.assert_unreadable()

    def test_a_broken_link_above_the_file_is_unknown(self):
        self.bindings.parent.rmdir()
        self.bindings.parent.symlink_to(self.base / "unmounted")
        self.assert_unreadable()

    def test_a_broken_link_further_up_is_unknown(self):
        config = self.home / ".config"
        self.bindings.parent.rmdir()
        config.rmdir()
        config.symlink_to(self.base / "unmounted")
        self.assert_unreadable()

    def test_a_link_to_a_folder_with_no_bindings_is_fine(self):
        config = self.home / ".config"
        self.bindings.parent.rmdir()
        config.rmdir()
        (self.base / "dotfiles").mkdir()
        config.symlink_to(self.base / "dotfiles")
        self.assertEqual(self.check()[0], 0)

    def test_no_hypr_folder_is_fine(self):
        self.bindings.parent.rmdir()
        self.assertEqual(self.check()[0], 0)

    def test_unbinding_both_ends_of_a_move_exits_0(self):
        (self.base / "current/default/hypr/bindings.lua").write_text('o.bind("SUPER + Q", "Calc", "c")')
        (self.base / "target/default/hypr/bindings.lua").write_text('o.bind("SUPER + SHIFT + Q", "Calc", "c")')
        self.bindings.write_text('hl.unbind("SUPER + Q")\nhl.unbind("SUPER + SHIFT + Q")')
        self.assertEqual(self.check()[0], 0)

    def test_a_folder_is_unknown(self):
        self.bindings.mkdir()
        self.assert_unreadable()

    def test_a_pipe_is_unknown_and_not_read(self):
        os.mkfifo(self.bindings)
        self.assert_unreadable()

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_a_denied_file_is_unknown(self):
        self.bindings.touch(mode=0)
        self.assert_unreadable()

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_a_denied_folder_is_unknown(self):
        self.bindings.touch()
        self.bindings.parent.chmod(0)
        self.addCleanup(self.bindings.parent.chmod, 0o755)
        self.assert_unreadable()

    def test_a_link_to_a_file_is_read(self):
        real = self.base / "real.lua"
        real.write_text('o.bind("SUPER + M", "Mail", "mail")')
        self.bindings.symlink_to(real)
        (self.base / "target/default/hypr/bindings.lua").write_text('o.bind("SUPER + M", "Minimize", "min")')
        self.assertEqual(self.check()[0], 1)

    def test_a_changed_computed_key_exits_3(self):
        (self.base / "target/default/hypr/keys.lua").write_text('o.bind("SUPER + " .. key, "x", "y")')
        code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertIn("It could land on one of your keys.", " ".join(out.split()))

    def test_an_unchanged_computed_key_exits_0(self):
        for tree in ("current", "target"):
            (self.base / tree / "default/hypr/keys.lua").write_text('o.bind("SUPER + " .. key, "x", "y")')
        code, out, _ = self.check()
        self.assertEqual(code, 0)
        self.assertIn("1 key bindings use computed keys", out)

    def test_a_computed_key_of_the_users_exits_3(self):
        self.bindings.write_text('o.bind("SUPER + " .. key, "x", "y")')
        self.assertEqual(self.check()[0], 3)

    def test_an_unknown_helper_exits_3(self):
        (self.base / "target/default/hypr/helpers.lua").write_text("function o.bind_foo(keys) end")
        code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertIn("o.bind_foo", out)

    def test_a_helper_outside_helpers_lua_is_found(self):
        (self.base / "target/default/hypr/keys.lua").write_text("function o.bind_foo(keys) end")
        self.assertEqual(self.check()[0], 3)

    def test_a_clash_still_exits_1_beside_an_unknown(self):
        self.bindings.write_text('o.bind("SUPER + M", "Mail", "mail")\no.bind("SUPER + " .. key, "x", "y")')
        (self.base / "target/default/hypr/bindings.lua").write_text('o.bind("SUPER + M", "Minimize", "min")')
        self.assertEqual(self.check()[0], 1)

    def test_dictation_from_a_release_candidate_has_not_gone(self):
        (self.base / "current/default/hypr/voxtype.lua").write_text(
            """
            o.bind("SUPER + CTRL + X", "Toggle dictation", "voxtype record toggle")
            o.bind("F9", "Start dictation (push-to-talk)", "voxtype record start")
            o.bind("F9", "Stop dictation (push-to-talk)", "voxtype record stop", { release = true })
            """
        )
        (self.base / "target/default/hypr/dictation.lua").write_text(
            """
            if backend and not o.cmd_missing(backend) then
              o.bind("SUPER + CTRL + X", "Toggle dictation", "omarchy-dictation toggle")
              o.bind_hold("F9", "Start dictation (push-to-talk)", "omarchy-dictation start", "Stop dictation (push-to-talk)", "omarchy-dictation stop")
              -- A modifier's mask changes between its press and release.
              o.bind_hold("ALT + Alt_R", "Start dictation (push-to-talk)", "omarchy-dictation start", "Stop dictation (push-to-talk)", "omarchy-dictation stop", { ignore_mods = true })
            end
            """
        )
        self.bindings.write_text('o.bind("ALT + Alt_R", "Mine", "mine")')
        code, out, _ = self.check()
        out = " ".join(out.split())
        self.assertEqual(code, 1)
        self.assertNotIn("removed", out)
        self.assertIn("ALT + ALT_R: your", out)


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


    def test_a_download_is_quiet_when_stderr_is_not_a_terminal(self):
        self.assertEqual(self.download(io.BytesIO(self.archive()))[2], "")


class Terminals(ProgramCase):
    def setUp(self):
        super().setUp()
        self.terminal = True

    def test_a_download_says_what_it_is_fetching_and_how_much(self):
        code, out, err = self.download(io.BytesIO(self.archive()))
        self.assertEqual(code, 0)
        self.assertIn("Downloading v1.2.3", err)
        self.assertRegex(err, r"\d MB\n$")
        self.assertNotIn("Downloading", out)

    def test_a_failed_download_ends_the_progress_line(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.side_effect = IncompleteRead(b"")
        code, _, err = self.download(response)
        self.assertEqual(code, 2)
        self.assertTrue(err.splitlines()[-1].startswith("Couldn't download the release"))


class Tags(ProgramCase):
    def test_good_tags_are_accepted(self):
        for tag in ("v1.2.3", "v4.5.0-rc2", "v10.20.30-rc11"):
            with self.subTest(tag=tag):
                self.assertTrue(impact.TAG.fullmatch(tag))

    def test_a_bad_tag_exits_2_before_the_network_or_the_cache(self):
        bad = (
            "../../x", "v1.2.3/../../x", "main", "1.2.3", "v1.2", "v1.2.3rc1", "v1.2.3-beta1",
            "v1.2.3-rc", "v1.2.3\n", "v\u0661.2.3", ".", "..",
        )
        for tag in bad:
            with self.subTest(tag=tag), mock.patch.object(impact.urllib.request, "urlopen") as urlopen:
                code, out, err = self.run_main(tag)
                self.assertEqual((code, out), (2, ""))
                self.assertEqual(len(err.splitlines()), 1)
                self.assertIn("isn't a release tag", err)
                urlopen.assert_not_called()
                self.assertFalse(self.cache.exists())

    def test_a_bad_tag_is_refused_with_target_too(self):
        code, _, err = self.check("../../x")
        self.assertEqual(code, 2)
        self.assertIn("isn't a release tag", err)

    def test_a_bad_tag_from_the_api_is_never_a_cache_path(self):
        for body in (b'{"tag_name": "../../x"}', b'{"tag_name": "v1.2.3/../.."}'):
            with self.subTest(body=body):
                self.assert_download_failed(self.download(io.BytesIO(body), args=("--channel", "stable")))
        self.assertFalse((self.base / "x").exists())

    def test_the_listing_skips_tags_of_another_shape(self):
        listing = io.BytesIO(b'[{"tag_name": "v9.9.9/x"}, {"tag_name": "9.9.9"}, {"tag_name": "v1.2.3"}]')
        code, out, _ = self.download(listing, io.BytesIO(self.archive()), args=("--channel", "rc"))
        self.assertEqual(code, 0)
        self.assertIn("-> v1.2.3 ", out)


class Cache(ProgramCase):
    def fetch_all(self, *tags):
        for tag in tags:
            self.assertEqual(self.download(io.BytesIO(self.archive()), args=(tag,))[0], 0)

    def cached(self):
        return sorted(path.name for path in (self.cache / "omaupdateimpact").iterdir())

    def test_a_third_release_prunes_the_oldest(self):
        self.fetch_all("v1.0.0", "v1.1.0", "v1.2.0")
        self.assertEqual(self.cached(), ["v1.1.0", "v1.2.0"])

    def test_oldest_goes_by_version_not_by_order_of_download(self):
        self.fetch_all("v1.2.0", "v1.0.0", "v1.1.0")
        self.assertEqual(self.cached(), ["v1.1.0", "v1.2.0"])

    def test_a_final_release_outranks_its_candidates(self):
        self.fetch_all("v1.2.0-rc9", "v1.2.0", "v1.2.0-rc10")
        self.assertEqual(self.cached(), ["v1.2.0", "v1.2.0-rc10"])

    def test_an_older_release_being_checked_is_kept(self):
        self.fetch_all("v1.1.0", "v1.2.0", "v1.0.0")
        self.assertEqual(self.cached(), ["v1.0.0", "v1.2.0"])

    def test_a_failed_download_prunes_nothing(self):
        self.fetch_all("v1.0.0", "v1.1.0")
        self.download(io.BytesIO(b"broken"), args=("v1.2.0",))
        self.assertEqual(self.cached(), ["v1.0.0", "v1.1.0"])

    def test_a_cached_release_prunes_nothing(self):
        self.fetch_all("v1.0.0", "v1.1.0")
        shutil.copytree(self.base / "target", self.cache / "omaupdateimpact/v1.2.0")
        with mock.patch.object(impact.urllib.request, "urlopen") as urlopen, \
                mock.patch.object(impact, "installed_packages", return_value=set()):
            self.assertEqual(self.run_main("v1.2.0")[0], 0)
        urlopen.assert_not_called()
        self.assertEqual(self.cached(), ["v1.0.0", "v1.1.0", "v1.2.0"])

    def test_only_releases_are_pruned(self):
        self.fetch_all("v1.0.0", "v1.1.0")
        (self.cache / "omaupdateimpact/notes").mkdir()
        self.fetch_all("v1.2.0")
        self.assertEqual(self.cached(), ["notes", "v1.1.0", "v1.2.0"])

    def test_a_link_in_the_cache_is_removed_but_not_followed(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "file").touch()
        cache = self.cache / "omaupdateimpact"
        cache.mkdir(parents=True)
        (cache / "v0.9.0").symlink_to(outside)
        self.fetch_all("v1.0.0", "v1.1.0")
        self.assertEqual(self.cached(), ["v1.0.0", "v1.1.0"])
        self.assertTrue((outside / "file").exists())

    def test_nothing_is_left_in_scratch(self):
        self.fetch_all("v1.0.0", "v1.1.0", "v1.2.0")
        self.assertFalse([name for name in self.cached() if not impact.TAG.fullmatch(name)])

    def test_an_empty_xdg_cache_home_uses_the_home_cache(self):
        with mock.patch.dict(os.environ, XDG_CACHE_HOME=""):
            self.assertEqual(self.download(io.BytesIO(self.archive()))[0], 0)
        self.assertTrue((self.home / ".cache/omaupdateimpact/v1.2.3/bin").is_dir())
        self.assertFalse(Path("omaupdateimpact").exists())

    def test_an_unset_xdg_cache_home_uses_the_home_cache(self):
        del os.environ["XDG_CACHE_HOME"]
        self.assertEqual(self.download(io.BytesIO(self.archive()))[0], 0)
        self.assertTrue((self.home / ".cache/omaupdateimpact/v1.2.3/bin").is_dir())


class RateLimits(ProgramCase):
    def api_failure(self, error):
        return self.download(error, args=("--channel", "stable"))

    def assert_limited(self, result, advice):
        code, out, err = result
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, f"Couldn't download the release: GitHub's rate limit is used up. {advice}\n")

    def test_a_403_with_no_requests_left_says_so(self):
        self.assert_limited(self.api_failure(refused(403, x_ratelimit_remaining="0")), "Try again later, or set GITHUB_TOKEN.")

    def test_a_429_and_a_retry_after_say_so_too(self):
        for error in (refused(429, x_ratelimit_remaining="0"), refused(403, retry_after="60"), refused(429, retry_after="60")):
            with self.subTest(code=error.code):
                self.assert_limited(self.api_failure(error), "Try again later, or set GITHUB_TOKEN.")

    def test_a_token_that_is_already_set_is_not_suggested(self):
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional"):
            self.assert_limited(self.api_failure(refused(403, x_ratelimit_remaining="0")), "Try again later.")

    def test_the_archive_is_not_helped_by_a_token(self):
        self.assert_limited(self.download(refused(429, retry_after="60")), "Try again later.")

    def test_other_refusals_stay_as_they_are(self):
        for error in (refused(403), refused(403, x_ratelimit_remaining="12"), refused(404), refused(500, retry_after="60")):
            with self.subTest(code=error.code):
                code, _, err = self.api_failure(error)
                self.assertEqual(code, 2)
                self.assertNotIn("rate limit", err)
                self.assertIn("Couldn't download the release: HTTP Error", err)


class Tokens(ProgramCase):
    def requests(self, *args):
        """What was sent for a stable run: the API request, then the archive request."""
        answers = [io.BytesIO(b'{"tag_name": "v1.2.3"}'), io.BytesIO(self.archive())]
        with mock.patch.object(impact.urllib.request, "urlopen", side_effect=answers) as urlopen, \
                mock.patch.object(impact, "installed_packages", return_value=set()):
            self.assertEqual(self.run_main("--channel", "stable")[0], 0)
        return [call.args[0] for call in urlopen.call_args_list]

    def test_github_token_goes_to_the_api_and_no_further(self):
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional"):
            listing, archive = self.requests()
        self.assertEqual(listing.get_header("Authorization"), "Bearer fictional")
        self.assertEqual(listing.headers, {})
        self.assertFalse(archive.has_header("Authorization"))

    def test_no_token_sends_no_header(self):
        for environment in ({}, {"GITHUB_TOKEN": ""}):
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment):
                listing, _ = self.requests()
                self.assertFalse(listing.has_header("Authorization"))
                shutil.rmtree(self.cache)

    def test_a_token_with_a_trailing_newline_still_works(self):
        for token in ("fictional\n", "fictional\r\n", "  fictional "):
            with self.subTest(token=token), mock.patch.dict(os.environ, GITHUB_TOKEN=token):
                listing, _ = self.requests()
                self.assertEqual(listing.get_header("Authorization"), "Bearer fictional")
                shutil.rmtree(self.cache)

    def test_a_token_a_header_cannot_carry_is_never_printed(self):
        for token in ("fictional\nsecret", "fictional\r\nsecret", "fictional secret", "fictional\u00e9secret"):
            for flags in ((), ("--debug",)):
                with self.subTest(token=token, flags=flags), mock.patch.dict(os.environ, GITHUB_TOKEN=token), \
                        mock.patch.object(impact.urllib.request, "urlopen") as urlopen:
                    code, out, err = self.run_main("--channel", "stable", *flags)
                    self.assertEqual((code, out), (2, ""))
                    self.assertTrue(err.endswith("Couldn't download the release: GITHUB_TOKEN holds characters a request header can't carry\n"))
                    self.assertNotIn("fictional", err)
                    self.assertNotIn("secret", err)
                    urlopen.assert_not_called()
                    if not flags:
                        self.assertEqual(len(err.splitlines()), 1)

    def test_a_redirect_drops_the_token(self):
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional"):
            listing, _ = self.requests()
        followed = impact.urllib.request.HTTPRedirectHandler().redirect_request(
            listing, None, 302, "Found", {}, "https://elsewhere.invalid/",
        )
        self.assertFalse(followed.has_header("Authorization"))


class ReleasesApi(ProgramCase):
    def test_the_newest_tag_is_downloaded(self):
        api, archive = io.BytesIO(b'[{"tag_name": "v1.2.3"}]'), io.BytesIO(self.archive())
        self.assertEqual(self.download(api, archive, args=("--channel", "rc"))[0], 0)

    def test_bad_answers_exit_2(self):
        bodies = {
            "rc": (b"", b"not json", b"\xff", b"[]", b"{}", b"[1]", b"[{}]", b'[{"tag_name": null}]', b'[{"tag_name": "x"}]'),
            "stable": (b"", b"not json", b"\xff", b"[]", b"[1]", b"{}", b'{"tag_name": null}', b'{"tag_name": 1}'),
        }
        for channel, answers in bodies.items():
            for body in answers:
                with self.subTest(channel=channel, body=body):
                    self.assert_download_failed(self.download(io.BytesIO(body), args=("--channel", channel)))


def releases(*tags):
    return json.dumps([{"tag_name": tag} for tag in tags]).encode()


class Channels(ProgramCase):
    """Fictional releases: stable is v1.2.3, and v2.0.0-rc2 is the newest of all."""

    def setUp(self):
        super().setUp()
        self.latest = b'{"tag_name": "v1.2.3"}'
        self.listing = releases("v2.0.0-rc2", "v2.0.0-rc1", "v1.2.3", "v1.2.2")
        self.listing_error = None

    def stub(self, version, channel):
        directory = self.base / "stub"
        directory.mkdir(exist_ok=True)
        for name, line in (("omarchy-version", version), ("omarchy-version-channel", channel)):
            command = directory / name
            command.write_text(f"#!/bin/sh\n{line}\n")
            command.chmod(0o755)
        patcher = mock.patch.dict(os.environ, PATH=f"{directory}:{os.environ['PATH']}")
        patcher.start()
        self.addCleanup(patcher.stop)

    def on_channel(self, channel, version="1.0.0-1"):
        self.stub(f'echo "{version}"', f'echo "{channel}"')

    def answer(self, request, *args, **kwargs):
        url = request.full_url
        self.urls.append(url)
        if url.endswith("/releases/latest"):
            return io.BytesIO(self.latest)
        if "/releases?" in url:
            if self.listing_error:
                raise self.listing_error
            return io.BytesIO(self.listing)
        return io.BytesIO(self.archive())

    def fetch(self, *args, own_tree=False, packages=frozenset()):
        """Run against the fictional API, keeping the URLs it was asked for in self.urls."""
        self.urls = []
        with mock.patch.object(impact.urllib.request, "urlopen", side_effect=self.answer), \
                mock.patch.object(impact, "installed_packages", return_value=packages):
            if own_tree:
                with mock.patch.dict(os.environ, OMARCHY_PATH=str(self.base / "current")):
                    return self.run_argv("--home", str(self.home), *args)
            return self.run_main(*args)

    def assert_downloaded(self, tag):
        self.assertTrue(self.urls[-1].endswith(f"/archive/refs/tags/{tag}.tar.gz"), self.urls)

    def test_stable_takes_the_latest_stable_release(self):
        self.on_channel("stable")
        code, out, _ = self.fetch()
        self.assertEqual(code, 0)
        self.assertTrue(self.urls[0].endswith("/releases/latest"))
        self.assert_downloaded("v1.2.3")
        self.assertIn("-> v1.2.3 (stable channel, not a prerelease).", out.splitlines()[0])

    def test_rc_takes_the_newest_release(self):
        self.on_channel("rc")
        code, out, _ = self.fetch()
        self.assertEqual(code, 0)
        self.assert_downloaded("v2.0.0-rc2")
        self.assertIn("-> v2.0.0-rc2 (rc channel, prerelease).", out.splitlines()[0])

    def test_rc_goes_by_version_when_a_stable_patch_comes_later(self):
        self.on_channel("rc")
        self.listing = releases("v1.2.4", "v2.0.0-rc2", "v1.2.3")
        self.fetch()
        self.assert_downloaded("v2.0.0-rc2")

    def test_rc_takes_the_final_release_over_its_candidates(self):
        self.on_channel("rc")
        self.listing = releases("v2.0.0-rc2", "v2.0.0", "v2.0.0-rc1")
        self.fetch()
        self.assert_downloaded("v2.0.0")

    def test_a_channel_without_tags_exits_2_and_asks_for_one(self):
        for channel in ("edge", "dev", "unknown", "stable / rc"):
            with self.subTest(channel=channel):
                self.on_channel(channel)
                code, out, err = self.fetch()
                self.assertEqual((code, out, self.urls), (2, "", []))
                self.assertEqual(len(err.splitlines()), 1)
                self.assertTrue(err.startswith("Can't pick a release: "), err)
                self.assertIn(f"the channel is {channel},", err)
                self.assertIn("Pass a tag", err)

    def test_a_failing_channel_command_counts_as_unknown(self):
        self.stub('echo "1.0.0-1"', "exit 1")
        code, _, err = self.fetch()
        self.assertEqual(code, 2)
        self.assertIn("the channel is unknown,", err)

    def test_a_dev_checkout_is_the_dev_channel_whatever_its_mirrors_say(self):
        self.on_channel("stable", version="dev (abc1234)")
        code, _, err = self.fetch()
        self.assertEqual((code, self.urls), (2, []))
        self.assertIn("the channel is dev,", err)

    def test_channel_flag_overrides_the_system(self):
        self.on_channel("edge")
        self.assertEqual(self.fetch("--channel", "rc")[0], 0)
        self.assert_downloaded("v2.0.0-rc2")

    def test_channel_flag_can_name_a_channel_without_tags(self):
        self.on_channel("stable")
        code, _, err = self.fetch("--channel", "edge")
        self.assertEqual((code, self.urls), (2, []))
        self.assertIn("Pass a tag", err)

    def test_a_tag_overrides_the_channel(self):
        self.on_channel("stable")
        code, out, _ = self.fetch("v2.0.0-rc1", "--channel", "rc")
        self.assertEqual((code, len(self.urls)), (0, 1))
        self.assert_downloaded("v2.0.0-rc1")
        self.assertIn("-> v2.0.0-rc1 (rc channel, prerelease).", out.splitlines()[0])

    def test_a_tag_works_on_a_channel_without_tags(self):
        self.on_channel("edge")
        code, out, _ = self.fetch("v1.2.3")
        self.assertEqual(code, 0)
        self.assertIn("(edge channel, not a prerelease)", out.splitlines()[0])

    def test_a_target_directory_works_on_a_channel_without_tags(self):
        self.on_channel("edge")
        code, out, _ = self.fetch("--target", str(self.base / "target"))
        self.assertEqual((code, self.urls), (0, []))
        self.assertIn("-> target (edge channel, can't tell if it's a prerelease).", out.splitlines()[0])

    def test_up_to_date_exits_0_and_names_the_newer_rc(self):
        self.on_channel("stable", version="1.2.3-1")
        code, out, err = self.fetch(own_tree=True)
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0], "Omarchy 1.2.3-1 is already v1.2.3 (stable channel, not a prerelease). There is no update.")
        self.assertEqual(lines[1:], ["Newer on the rc channel: v2.0.0-rc2. To check it: omaupdateimpact v2.0.0-rc2"])

    def test_up_to_date_downloads_nothing(self):
        self.on_channel("stable", version="1.2.3-1")
        self.fetch(own_tree=True)
        self.assertFalse(any("/archive/" in url for url in self.urls))
        self.assertFalse(self.cache.exists())

    def test_up_to_date_on_the_newest_release_names_nothing_else(self):
        self.on_channel("rc", version="2.0.0rc2-1")
        code, out, _ = self.fetch(own_tree=True)
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            ["Omarchy 2.0.0rc2-1 is already v2.0.0-rc2 (rc channel, prerelease). There is no update."],
        )

    def test_up_to_date_on_rc_ignores_an_older_stable_patch(self):
        self.on_channel("rc", version="2.0.0rc2-1")
        self.listing = releases("v1.2.4", "v2.0.0-rc2")
        self.assertEqual(len(self.fetch(own_tree=True)[1].splitlines()), 1)

    def test_an_explicit_tag_that_is_installed_names_both_newer_releases(self):
        self.on_channel("stable", version="1.2.2-1")
        code, out, _ = self.fetch("v1.2.2", own_tree=True)
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines()[1:],
            [
                "Newer on the rc channel: v2.0.0-rc2. To check it: omaupdateimpact v2.0.0-rc2",
                "Newer on the stable channel: v1.2.3. To check it: omaupdateimpact v1.2.3",
            ],
        )

    def test_a_newer_stable_release_is_named_once(self):
        self.on_channel("stable", version="1.2.2-1")
        self.listing = releases("v1.2.3", "v1.2.2")
        out = self.fetch("v1.2.2", own_tree=True)[1]
        self.assertEqual(out.splitlines()[1:], ["Newer on the stable channel: v1.2.3. To check it: omaupdateimpact v1.2.3"])

    def test_an_unreadable_installed_version_matches_no_release(self):
        for version, tag in (('echo "dev (abc1234)"', "v1.2.3"), ("exit 1", "v1.2.2")):
            with self.subTest(version=version):
                self.stub(version, 'echo "stable"')
                code, out, _ = self.fetch(tag, own_tree=True)
                self.assertEqual(code, 0)
                self.assert_downloaded(tag)
                self.assertNotIn("There is no update", out)

    def test_a_candidate_a_final_release_replaced_is_not_named(self):
        self.on_channel("stable", version="1.2.2-1")
        self.listing = releases("v1.2.3", "v1.2.3-rc1", "v1.2.2")
        out = self.fetch("v1.2.2", own_tree=True)[1]
        self.assertNotIn("rc1", out)

    def test_up_to_date_still_exits_0_when_the_listing_fails_and_says_so(self):
        self.on_channel("stable", version="1.2.3-1")
        self.listing_error = OSError("no network")
        code, out, _ = self.fetch(own_tree=True)
        self.assertEqual(code, 0)
        self.assertIn("Couldn't check for newer releases", out)

    def test_up_to_date_names_the_rate_limit_when_that_stopped_the_listing(self):
        self.on_channel("stable", version="1.2.3-1")
        self.listing_error = refused(403, x_ratelimit_remaining="0")
        code, out, _ = self.fetch(own_tree=True)
        self.assertEqual(code, 0)
        self.assertIn("Couldn't check for newer releases on other channels. GitHub's rate limit", out)

    def test_a_tree_given_by_hand_is_compared_even_at_the_same_version(self):
        (self.base / "target/migrations/1.sh").write_text("omarchy-pkg-drop a\n")
        self.on_channel("stable", version="1.2.3-1")
        code, out, _ = self.fetch(packages={"a"})
        self.assertEqual(code, 1)
        self.assertNotIn("no update", out)

    def test_a_target_given_by_hand_is_compared_even_at_the_same_version(self):
        (self.base / "target/migrations/1.sh").write_text("omarchy-pkg-drop a\n")
        self.on_channel("stable", version="1.2.3-1")
        code, out, _ = self.fetch("--target", str(self.base / "target"), "v1.2.3", own_tree=True, packages={"a"})
        self.assertEqual(code, 1)
        self.assertNotIn("no update", out)

    def test_the_channel_command_in_a_tree_is_never_run(self):
        marker = self.base / "ran"
        for name in ("current", "target"):
            command = self.base / name / "bin/omarchy-version-channel"
            command.write_text(f"#!/bin/sh\ntouch {marker}\n")
            command.chmod(0o755)
        with mock.patch.dict(os.environ, PATH=str(self.base / "nowhere")):
            out = self.check()[1]
        self.assertIn("(unknown channel,", out.splitlines()[0])
        self.assertFalse(marker.exists())


class Versions(unittest.TestCase):
    def test_a_package_and_its_tag_count_as_the_same_version(self):
        for package, tag in (
            ("4.0.6-1", "v4.0.6"),
            ("4.0.6-2", "v4.0.6"),
            ("1:4.0.6-1", "v4.0.6"),
            ("4.5.0rc2-1", "v4.5.0-rc2"),
        ):
            with self.subTest(package=package):
                self.assertEqual(impact.version_key(package), impact.version_key(tag))

    def test_different_releases_stay_different(self):
        for package, tag in (("4.0.6-1", "v4.0.6-rc1"), ("4.0.6-1", "v4.0.60"), ("4.5.0rc2-1", "v4.5.0-rc1")):
            with self.subTest(package=package, tag=tag):
                self.assertNotEqual(impact.version_key(package), impact.version_key(tag))

    def test_a_dev_or_unknown_version_has_no_key(self):
        for version in ("dev (abc1234)", "dev", "dev.abc1234-1", "unknown", ""):
            with self.subTest(version=version):
                self.assertIsNone(impact.version_key(version))

    def test_a_candidate_sorts_before_its_final_release(self):
        tags = ["v4.0.6", "v4.5.0", "v4.5.0-rc10", "v4.5.0-rc2"]
        self.assertEqual(sorted(tags, key=impact.version_key), ["v4.0.6", "v4.5.0-rc2", "v4.5.0-rc10", "v4.5.0"])

    def test_whether_a_name_is_a_prerelease(self):
        self.assertEqual(
            [impact.is_prerelease(name) for name in ("v4.5.0-rc2", "v4.0.6", "my-tree")], [True, False, None]
        )


if __name__ == "__main__":
    unittest.main()
