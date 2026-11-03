import argparse
import contextlib
import errno
import gzip
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
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


FIXTURES = Path(__file__).parent / "fixtures"
QMLLINT_OUTPUT = Path(__file__).parent / "fixtures/qmllint-6.12.0"
REAL_QMLLINT = impact.find_qmllint()[0]
# Answers --version as Qt 6 does, for a script in place of qmllint.
QT6_VERSION = '[ "$1" != --version ] || { echo "qmllint 6.12.0"; exit 0; }'


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
        self.assertEqual(findings[0].fix, 'Add hl.unbind("SUPER + M") above your binding, or choose another key.')

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
        self.assertEqual(findings[0].fix, 'Add hl.unbind("ALT + Alt_R") above your binding, or choose another key.')

    def test_a_clash_across_modifier_spellings(self):
        findings = compare("", 'o.bind("CONTROL + A", "New", "n")', 'o.bind("CTRL + A", "Mine", "m")')
        self.assertEqual(len(titles(findings, "attention")), 1)

    def test_a_fix_spells_the_keys_the_way_the_default_does(self):
        findings = compare("", 'o.bind("CONTROL + A", "New", "n")', 'o.bind("CTRL + A", "Mine", "m")')
        self.assertEqual(findings[0].fix, 'Add hl.unbind("CONTROL + A") above your binding, or choose another key.')

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

    def test_a_move_names_the_default_it_replaces(self):
        findings = compare(
            'o.bind("SUPER + A", "Calc", "c")\no.bind("SUPER + B", "Night", "n")',
            'o.bind("SUPER + B", "Calc", "c")',
        )
        self.assertEqual(titles(findings, "note")[0], 'Moved: "Calc" from SUPER + A to SUPER + B, replacing "Night".')
        self.assertFalse([title for title in titles(findings, "note") if " is now " in title])

    def test_a_move_names_what_takes_its_place(self):
        findings = compare('o.bind("SUPER + A", "Calc", "c")', 'o.bind("SUPER + B", "Calc", "c")\no.bind("SUPER + A", "Fresh", "f")')
        self.assertEqual(titles(findings, "note")[0], 'Moved: "Calc" from SUPER + A to SUPER + B. SUPER + A is now "Fresh".')
        self.assertFalse([title for title in titles(findings, "note") if "it was" in title])

    def test_a_merged_move_names_every_file_behind_it(self):
        current, target = impact.Parsed(), impact.Parsed()
        impact.parse_lua('o.bind("SUPER + A", "Calc", "c")', current, "old-a.lua")
        impact.parse_lua('o.bind("SUPER + B", "Night", "n")', current, "old-b.lua")
        impact.parse_lua('o.bind("SUPER + B", "Calc", "c")', target, "new-b.lua")
        impact.parse_lua('o.bind("SUPER + A", "Fresh", "f")', target, "new-a.lua")
        finding = impact.compare_bindings(current, target, impact.Parsed())[0]
        self.assertEqual(finding.evidence, ["new-a.lua", "new-b.lua", "old-a.lua", "old-b.lua"])

    def test_two_keys_that_swap_are_two_moves_and_nothing_else(self):
        findings = compare(
            'o.bind("SUPER + A", "Calc", "c")\no.bind("SUPER + B", "Night", "n")',
            'o.bind("SUPER + B", "Calc", "c")\no.bind("SUPER + A", "Night", "n")',
        )
        self.assertEqual(titles(findings, "note"), [
            'Moved: "Calc" from SUPER + A to SUPER + B.',
            'Moved: "Night" from SUPER + B to SUPER + A.',
        ])

    def test_a_default_that_moved_on_isnt_replaced(self):
        findings = compare(
            'o.bind("SUPER + A", "Calc", "c")\no.bind("SUPER + B", "Night", "n")',
            'o.bind("SUPER + B", "Calc", "c")\no.bind("SUPER + C", "Night", "n")',
        )
        self.assertEqual(titles(findings, "note"), [
            'Moved: "Calc" from SUPER + A to SUPER + B.',
            'Moved: "Night" from SUPER + B to SUPER + C.',
        ])

    def test_a_move_onto_your_key_says_nothing_about_the_old_default(self):
        findings = compare(
            'o.bind("SUPER + A", "Calc", "c")\no.bind("SUPER + B", "Night", "n")',
            'o.bind("SUPER + B", "Calc", "c")',
            'o.bind("SUPER + B", "Mine", "m")',
        )
        self.assertIn('Moved: "Calc" from SUPER + A to SUPER + B.', titles(findings, "note"))

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
        self.assertEqual(findings[0].fix, 'Add hl.unbind("CONTROL + W") too.')

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
            self.assertEqual(self.read({"1.sh": f"{command}\n"}), ({}, {("1.sh",)}), command)

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
            self.assertEqual(self.unread(f"{command}\n"), {("1.sh",)}, command)

    def test_a_removal_with_nothing_named_is_unknown(self):
        for command in ("list | xargs omarchy-pkg-drop", "pacman -Qdtq | sudo pacman -Rns -", "list | xargs sudo pacman -Rns --noconfirm"):
            self.assertEqual(self.unread(f"{command}\n"), {("1.sh",)}, command)

    def test_a_readable_package_beside_an_unreadable_one_is_kept(self):
        self.assertEqual(self.read({"1.sh": 'omarchy-pkg-drop a "$b"\n'}), ({"a": (False, "1.sh")}, {("1.sh",)}))

    def test_a_script_it_loses_its_place_in_is_unknown(self):
        for text in ("x='open\n", 'x="open\n', "cat <<EOF\nno end\n", "x=$(open\n", "if x; then\n", "fi\n", "y)\n", "x=${open\n", "[[ open\n", "case x in\n", "x=`open\nomarchy-pkg-drop a\n"):
            self.assertEqual(self.unread(text), {("1.sh",)}, text)

    def test_a_removal_comes_with_the_line_to_undo_it(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "migrations").mkdir()
            (target / "migrations/1.sh").write_text("omarchy-pkg-drop a\nif x; then omarchy-pkg-drop b; fi\n")
            certain, possible = impact.compare_packages(target, target, {"a", "b"}, {})
        self.assertEqual(certain.fix, "After the update, run omarchy pkg add a (aur-add for an AUR package).")
        self.assertEqual(possible.fix, "If it goes, run omarchy pkg add b (aur-add for an AUR package).")

    def test_every_unreadable_argument_is_one_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "migrations").mkdir()
            (target / "migrations/1.sh").write_text('omarchy-pkg-drop "$a" "$b"\nsudo pacman -Rns "${c[@]}"\n')
            findings = impact.compare_packages(target, target, set(), {})
        self.assertEqual([(finding.level, finding.evidence) for finding in findings], [("unknown", ["migrations/1.sh"])])

    def test_an_unreadable_migration_already_run_is_no_limit(self):
        self.assertEqual(self.read({"1.sh": 'omarchy-pkg-drop "$a"\n'}, ["1.sh"]), ({}, set()))

    def test_the_removals_of_a_real_release_stay_the_same(self):
        migrations = Path(__file__).parent / "fixtures/releases/v4.5.0-rc2/migrations"
        expected = {
            "brave-origin-beta-bin": (True, "1784510887.sh"),
            "cups-browsed": (False, "1788009111.sh"),
            "cups-pdf": (False, "1787815267.sh"),
            "dua-cli": (False, "1791345484.sh"),
            "dust": (False, "1780739888.sh"),
            "elsewhen": (False, "1790528634.sh"),
            "gnome-calculator": (False, "1785637426.sh"),
            "linux-n1x": (True, "1791077437.sh"),
            "linux-n1x-headers": (True, "1791077437.sh"),
            "omarchy-herdr": (False, "1786273938.sh"),
            "python-terminaltexteffects": (False, "1786355450.sh"),
            "satty": (False, "1788129995.sh"),
            "t3code-bin": (True, "1792345511.sh", "bin/omarchy-install-ai-t3-code"),
            "t3code-nightly-bin": (True, "1792345511.sh", "bin/omarchy-install-ai-t3-code"),
            "tensaku": (False, "1788129995.sh"),
            "tiny-dfr": (True, "1786137597.sh", "migrations/1785944594.sh"),
            "usbguard": (True, "1791769486.sh"),
            "yt6801-dkms": (True, "1788279117.sh"),
        }
        self.assertEqual(impact.package_changes(migrations, set()), (expected, {("1785351479.sh",)}))

    def test_a_missing_pacman_is_unknown(self):
        finding = impact.compare_packages(Path("target"), Path("home"), None, {})[0]
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
            finding = impact.compare_packages(target, target, {"a"}, {})[0]
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
        finding = impact.compare_packages(self.tree, self.tree, {"a"}, {})[0]
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

    def test_a_script_run_directly_is_read(self):
        (self.tree / "install/x.sh").write_text("omarchy-pkg-drop a\n")
        for command in ('"$OMARCHY_PATH/install/x.sh"', 'sudo "$OMARCHY_PATH/install/x.sh" go'):
            self.assertEqual(self.read(f"{command}\n"), ({"a": (True, "1.sh", "install/x.sh")}, set()), command)

    def test_a_copied_file_is_not_read(self):
        (self.tree / "install/x.sh").write_text("omarchy-pkg-drop a\n")
        (self.tree / "install/x.conf").write_text("it's a config file\n")
        for command in ('cp "$OMARCHY_PATH/install/x.sh" /tmp', 'sudo cp "$OMARCHY_PATH/install/x.conf" /tmp'):
            self.assertEqual(self.read(f"{command}\n"), ({}, set()), command)

    def test_a_subcommand_of_omarchy_reads_its_own_file(self):
        self.command("omarchy", "omarchy-pkg-drop z\n")
        self.command("omarchy-pkg-present", "omarchy-pkg-drop y\n")
        self.assertEqual(self.read("omarchy pkg present x\n"), ({"y": (True, "1.sh", "bin/omarchy-pkg-present")}, set()))

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
        self.assertEqual(self.read("omarchy-tool\n"), ({}, {("1.sh", "bin/omarchy-tool")}))

    def test_a_reached_file_that_loses_the_reader_is_unknown(self):
        self.command("omarchy-tool", "x='open\n")
        self.assertEqual(self.read("omarchy-tool\n"), ({}, {("1.sh", "bin/omarchy-tool")}))

    def test_an_unknown_in_a_reached_file_names_both_files(self):
        self.command("omarchy-tool", 'omarchy-pkg-drop "$1"\n')
        (self.tree / "migrations/1.sh").write_text("omarchy-tool\n")
        finding = impact.compare_packages(self.tree, self.tree, set(), {})[0]
        self.assertEqual((finding.level, finding.evidence), ("unknown", ["migrations/1.sh", "bin/omarchy-tool"]))
        self.assertEqual(finding.title, "Couldn't read what bin/omarchy-tool removes, called from migrations/1.sh, so check by hand.")

    def test_two_reached_files_are_one_finding(self):
        self.command("omarchy-one", 'omarchy-pkg-drop "$1"\n')
        self.command("omarchy-two", 'omarchy-pkg-drop "$1"\n')
        (self.tree / "migrations/1.sh").write_text('omarchy-two\nomarchy-one\nomarchy-pkg-drop "$x"\n')
        findings = impact.compare_packages(self.tree, self.tree, set(), {})
        self.assertEqual([finding.evidence for finding in findings], [["migrations/1.sh", "bin/omarchy-one", "bin/omarchy-two"]])
        self.assertIn("bin/omarchy-one and bin/omarchy-two remove,", findings[0].title)

    def test_a_python_file_that_names_a_removal_is_unknown(self):
        for line in ('run(["pacman", "-Rns", name])', 'run("omarchy-pkg-drop " + name)'):
            (self.tree / "bin/omarchy-tool").write_text(f"#!/usr/bin/python3\n{line}\n")
            self.assertEqual(self.read("omarchy-tool\n"), ({}, {("1.sh", "bin/omarchy-tool")}), line)

    def test_a_python_file_with_no_removal_gives_nothing(self):
        (self.tree / "bin/omarchy-tool").write_text("#!/usr/bin/python3\nprint('it isn\\'t $(shell')\n")
        self.assertEqual(self.read("omarchy-tool\n"), ({}, set()))

    def test_a_shebang_with_a_flag_is_shell(self):
        (self.tree / "bin/omarchy-tool").write_text("#!/bin/bash -p\nomarchy-pkg-drop a\n")
        self.assertEqual(self.read("omarchy-tool\n")[0], {"a": (True, "1.sh", "bin/omarchy-tool")})


class Edits(unittest.TestCase):
    """Pending migrations that look like they write your files."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "home"
        self.home.mkdir()
        (self.base / "target/migrations").mkdir(parents=True)
        self.ship("current", "config/app/app.conf", "colour = blue\n")
        self.ship("target", "config/app/app.conf", "colour = green\n")

    def ship(self, tree, name, text):
        path = self.base / tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def write(self, name, text="colour = red\n"):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def findings(self, migration, checked=None):
        (self.base / "target/migrations/1.sh").write_text(migration)
        return impact.compare_edits(self.base / "current", self.base / "target", self.home, {} if checked is None else checked)

    def notes(self, migration):
        return titles(self.findings(migration), "note")

    def unknown(self, migration):
        return titles(self.findings(migration), "unknown")

    def test_sed_on_a_file_you_changed_is_a_note_with_the_line(self):
        self.write(".config/app/app.conf")
        findings = self.findings("echo Recolour\nsed -i 's/blue/green/' ~/.config/app/app.conf\n")
        self.assertEqual([(f.check, f.level) for f in findings], [("edits", "note")])
        self.assertEqual(
            findings[0].title,
            "migrations/1.sh, line 2, looks like it edits ~/.config/app/app.conf, which differs from Omarchy's default.",
        )
        self.assertEqual(findings[0].evidence, ["migrations/1.sh:2", "~/.config/app/app.conf", "config/app/app.conf"])
        self.assertIn("omaforecast", findings[0].detail)

    def test_the_same_migration_on_an_unchanged_file_says_nothing(self):
        self.write(".config/app/app.conf", "colour = blue\n")
        self.assertEqual(self.findings("sed -i 's/blue/green/' ~/.config/app/app.conf\n"), [])

    def test_a_file_like_the_releases_default_is_unchanged_too(self):
        self.write(".config/app/app.conf", "colour = green\n")
        self.assertEqual(self.findings("sed -i 's/blue/green/' ~/.config/app/app.conf\n"), [])

    def test_a_file_you_dont_have_says_nothing(self):
        self.assertEqual(self.findings("sed -i 's/blue/green/' ~/.config/app/app.conf\n"), [])

    def test_a_migration_already_run_says_nothing(self):
        self.write(".config/app/app.conf")
        self.write(".local/state/omarchy/migrations/1.sh", "")
        self.assertEqual(self.findings("sed -i 's/blue/green/' ~/.config/app/app.conf\n"), [])

    def test_a_file_with_no_default_says_so(self):
        self.write(".config/other.conf")
        self.assertEqual(self.notes("sed -i s/a/b/ ~/.config/other.conf\n"), [
            "migrations/1.sh, line 1, looks like it edits ~/.config/other.conf, which Omarchy has no default for.",
        ])

    def test_a_launcher_is_compared_with_omarchys_applications(self):
        self.ship("current", "applications/Notes.desktop", "[Desktop Entry]\n")
        self.write(".local/share/applications/Notes.desktop", "[Desktop Entry]\n")
        self.assertEqual(self.findings("rm -f ~/.local/share/applications/Notes.desktop\n"), [])
        self.write(".local/share/applications/Notes.desktop", "[Desktop Entry]\nName=Mine\n")
        self.assertIn("which differs from Omarchy's default", self.notes("rm -f ~/.local/share/applications/Notes.desktop\n")[0])

    def test_sed_without_in_place_writes_nothing(self):
        self.write(".config/app/app.conf")
        self.assertEqual(self.findings("sed -n p ~/.config/app/app.conf\nsed -E 's/a/b/' ~/.config/app/app.conf\n"), [])

    def test_every_way_of_asking_sed_to_edit_in_place(self):
        self.write(".config/app/app.conf")
        for command in (
            "sed -i.bak 's/a/b/' ~/.config/app/app.conf",
            "sed -Ei 's/a/b/' ~/.config/app/app.conf",
            "sed --in-place -E 's/a/b/' ~/.config/app/app.conf",
            "sed -i --follow-symlinks -e 's/a/b/' -e 's/c/d/' ~/.config/app/app.conf",
            "sed -i -f fix.sed ~/.config/app/app.conf",
            "sudo sed -i --expression=s/a/b/ \"$HOME/.config/app/app.conf\"",
        ):
            with self.subTest(command):
                self.assertEqual(len(self.notes(command + "\n")), 1)

    def test_the_script_given_to_sed_isnt_a_file(self):
        self.write(".config/app/app.conf")
        self.assertEqual(self.findings("sed -i ~/.config/app/app.conf /dev/null\n"), [])

    def test_every_writer_counts(self):
        self.write(".config/app/app.conf")
        for command in (
            "printf 'a\\n' >~/.config/app/app.conf",
            "echo a >> ~/.config/app/app.conf",
            "cat >>\"$HOME/.config/app/app.conf\" <<'EOF'\nmore\nEOF",
            "jq . x &>~/.config/app/app.conf",
            "cp -f /usr/share/x ~/.config/app/app.conf",
            "install -Dm644 /usr/share/x ~/.config/app/app.conf",
            "install -m 0644 /usr/share/x ~/.config/app/app.conf",
            "mv /tmp/x ~/.config/app/app.conf",
            "echo a | tee -a ~/.config/app/app.conf",
        ):
            with self.subTest(command):
                self.assertEqual(self.notes(command + "\n"), [
                    "migrations/1.sh, line 1, looks like it edits ~/.config/app/app.conf, which differs from Omarchy's default.",
                ])

    def test_removing_and_moving_away_remove(self):
        self.write(".config/app/app.conf")
        for command in ("rm -f -- ~/.config/app/app.conf", "mv ~/.config/app/app.conf /tmp/old"):
            with self.subTest(command):
                self.assertIn("looks like it removes ~/.config/app/app.conf", self.notes(command + "\n")[0])

    def test_what_a_command_only_reads_isnt_written(self):
        self.write(".config/app/app.conf")
        text = (
            "cp ~/.config/app/app.conf /tmp/backup\ngrep -q x ~/.config/app/app.conf\n"
            "install -d ~/.config/app/app.conf\nwc <~/.config/app/app.conf\nx 2>&1 >&2\n"
        )
        self.assertEqual(self.findings(text), [])

    def test_comments_strings_and_heredocs_arent_writes(self):
        self.write(".config/app/app.conf")
        text = (
            "# rm ~/.config/app/app.conf\necho 'rm ~/.config/app/app.conf'\n"
            "cat <<EOF\nrm ~/.config/app/app.conf\nEOF\n"
        )
        self.assertEqual(self.findings(text), [])

    def test_a_variable_set_in_the_migration_is_followed(self):
        self.write(".config/app/app.conf")
        text = 'dir="$HOME/.config/app"\nconfig=$dir/app.conf\nif [[ -f $config ]]; then\n  sed -i s/a/b/ "$config"\nfi\n'
        self.assertEqual(self.findings(text)[0].evidence[0], "migrations/1.sh:4")

    def test_a_variable_set_in_a_function_is_followed(self):
        self.write(".config/app/app.conf")
        text = 'fix() {\n  local config="${XDG_CONFIG_HOME:-$HOME/.config}/app/app.conf"\n  sed -i s/a/b/ "$config"\n}\nfix\n'
        self.assertEqual(len(self.notes(text)), 1)

    def test_an_xdg_folder_takes_its_default(self):
        self.write(".config/app/app.conf")
        self.assertEqual(len(self.notes('sed -i s/a/b/ "${XDG_CONFIG_HOME:-$HOME/.config}/app/app.conf"\n')), 1)

    def test_a_loop_over_a_list_is_one_note_naming_each_file(self):
        self.write(".config/app/app.conf")
        self.write(".config/other.conf")
        text = 'for file in "$HOME"/.config/{app/app,other,missing}.conf; do\n  echo x >>"$file"\ndone\n'
        findings = self.findings(text)
        self.assertEqual(titles(findings, "note"), [
            "migrations/1.sh, line 2, looks like it edits 2 files of yours that aren't Omarchy's default.",
        ])
        self.assertTrue(findings[0].detail.startswith(
            "They are ~/.config/app/app.conf and ~/.config/other.conf. It may edit only some."
        ))
        self.assertEqual(findings[0].evidence, [
            "migrations/1.sh:2", "~/.config/app/app.conf", "config/app/app.conf", "~/.config/other.conf",
        ])

    def test_a_path_built_from_variables_is_unknown_not_skipped(self):
        for text in (
            'sed -i s/a/b/ "$1"\n',
            'rm -f "$HOME/.config/app/$(name)"\n',
            'file=$(find ~/.config -name app.conf)\nsed -i s/a/b/ "$file"\n',
            'while read -r file; do rm -f "$file"; done <list\n',
            'rm -f "$XDG_CONFIG_HOME/app/app.conf"\n',
            'echo x >"${file%/*}/app.conf"\n',
            "rm -f relative.conf\n",
        ):
            with self.subTest(text):
                findings = self.findings(text)
                self.assertEqual([(f.check, f.level) for f in findings], [("edits", "unknown")])
                self.assertEqual(findings[0].evidence, [f"migrations/1.sh:{text.count(chr(10))}"])
                self.assertIn("so check it by hand", findings[0].title)

    def test_an_unknown_names_each_line_once(self):
        findings = self.findings('rm -f "$1" "$2"\ntrue\nsed -i s/a/b/ "$1"\n')
        self.assertEqual(titles(findings, "unknown"), [
            "Couldn't tell which files migrations/1.sh writes on lines 1 and 3, so check it by hand.",
        ])

    def test_a_path_outside_your_home_is_not_yours(self):
        text = (
            "sed -i s/a/b/ /etc/app.conf\npolkit=/etc/pam.d/polkit-1\ncp \"$polkit\" \"$polkit.bak.$(date +%s)\"\n"
            'rm -f "/usr/share/applications/$name.desktop"\necho x >/dev/null\n'
        )
        self.assertEqual(self.findings(text), [])

    def test_sudo_with_a_path_only_known_when_it_runs_is_for_system_files(self):
        self.assertEqual(self.findings('sudo rm -f "$grant"\n'), [])

    def test_omarchys_state_and_caches_arent_yours(self):
        self.write(".local/state/omarchy/toggles/x.lua")
        self.write(".cache/app/x")
        text = 'rm -f ~/.local/state/omarchy/toggles/x.lua "$HOME/.local/state/omarchy/$1" ~/.cache/app/x\n'
        self.assertEqual(self.findings(text), [])

    def test_a_temporary_file_isnt_yours(self):
        self.write(".config/app/app.conf")
        text = 'tmp=$(mktemp)\njq . ~/.config/app/app.conf >"$tmp"\nmv "$tmp" ~/.config/app/app.conf\n'
        self.assertEqual(self.notes(text), [
            "migrations/1.sh, line 3, looks like it edits ~/.config/app/app.conf, which differs from Omarchy's default.",
        ])
        self.assertEqual(self.findings('staged=$(mktemp "$HOME/.config/app/app.conf.XXXXXX")\necho x >"$staged"\n'), [])

    def test_realpath_names_the_file_its_given(self):
        self.write(".config/app/app.conf")
        text = 'target=$(realpath ~/.config/app/app.conf)\nawk 1 "$target" >"$target.new" && cat "$target.new" >"$target"\n'
        self.assertEqual(len(self.notes(text)), 1)

    def test_a_wildcard_is_one_note_naming_the_files_you_changed(self):
        self.ship("current", "applications/Notes.desktop", "[Desktop Entry]\n")
        self.write(".local/share/applications/Notes.desktop", "[Desktop Entry]\n")
        self.write(".local/share/applications/Mine.desktop")
        self.write(".local/share/applications/Yours.desktop")
        text = 'for desktop in ~/.local/share/applications/*.desktop; do\n  echo x >>"$desktop"\ndone\n'
        findings = self.findings(text)
        self.assertEqual(titles(findings, "note"), [(
            "migrations/1.sh, line 2, looks like it edits files that match ~/.local/share/applications/*.desktop, "
            "and 2 of them aren't Omarchy's default."
        )])
        self.assertTrue(findings[0].detail.startswith("They are Mine.desktop and Yours.desktop, in ~/.local/share/applications."))
        self.assertEqual(findings[0].evidence, [
            "migrations/1.sh:2", "~/.local/share/applications/Mine.desktop", "~/.local/share/applications/Yours.desktop",
        ])

    def test_a_copy_into_a_folder_writes_the_file_of_that_name(self):
        self.write(".config/app/app.conf")
        for command in (
            'cp -f "$OMARCHY_PATH/config/app/app.conf" ~/.config/app/',
            'cp -f "$OMARCHY_PATH/config/app/app.conf" ~/.config/app',
            'source=/usr/share/x/app.conf\nmv "$source" "$HOME/.config/app"',
        ):
            with self.subTest(command):
                self.assertEqual(self.notes(command + "\n"), [(
                    f"migrations/1.sh, line {command.count(chr(10)) + 1}, looks like it edits ~/.config/app/app.conf, "
                    "which differs from Omarchy's default."
                )])

    def test_a_copy_into_a_folder_of_a_file_only_known_when_it_runs_is_unknown(self):
        self.write(".config/app/app.conf")
        self.assertEqual(len(self.unknown('cp "$1" ~/.config/app/\n')), 1)

    def test_many_lines_it_cant_tell_about_are_counted(self):
        findings = self.findings('rm "$1"\nrm "$2"\nrm "$3"\nrm "$4"\n')
        self.assertEqual(titles(findings, "unknown"), [
            "Couldn't tell which files migrations/1.sh writes on 4 of its lines, so check it by hand.",
        ])
        self.assertEqual(len(findings[0].evidence), 4)

    def test_a_write_behind_a_wrapper_function_is_read(self):
        self.write(".config/app/app.conf")
        wrapper = 'as_root() {\n  if (( EUID == 0 )); then\n    "$@"\n  else\n    sudo "$@"\n  fi\n}\n'
        self.assertEqual(self.notes(wrapper + "as_root rm -f ~/.config/app/app.conf\n"), [
            "migrations/1.sh, line 8, looks like it removes ~/.config/app/app.conf, which differs from Omarchy's default.",
        ])
        retry = 'retry() {\n  local times=$1\n  shift\n  "$@" || "$@"\n}\n'
        self.assertEqual(self.notes(retry + "retry 3 rm -f ~/.config/app/app.conf\n"), [
            "migrations/1.sh, line 6, looks like it removes ~/.config/app/app.conf, which differs from Omarchy's default.",
        ])

    def test_a_writer_behind_a_command_that_runs_its_arguments_is_read(self):
        self.write(".config/app/app.conf")
        for command in (
            "sudo -u someone rm -f ~/.config/app/app.conf",
            "env -u X Y=1 rm -f ~/.config/app/app.conf",
            "timeout -s KILL 10 rm -f ~/.config/app/app.conf",
            "nice -n 5 ionice -c 3 rm -f ~/.config/app/app.conf",
            "Y=1 /usr/bin/rm -f ~/.config/app/app.conf",
        ):
            with self.subTest(command):
                self.assertEqual(len(self.notes(command + "\n")), 1)

    def test_a_writers_name_anywhere_else_in_a_command_isnt_a_write(self):
        self.write(".bashrc")
        text = 'mise install node\nnotify-send "cp" "$HOME/.bashrc"\ngit mv a ~/.bashrc\nretry 3 rm -f ~/.bashrc\n'
        self.assertEqual(self.findings(text), [])

    def test_a_function_that_runs_sudo_counts_as_sudo(self):
        wrapper = 'as_root() {\n  sudo "$@"\n}\nfunction quietly { as_root "$@" >/dev/null; }\n'
        self.assertEqual(self.findings(wrapper + 'as_root rm -f "$1"\nquietly cp x "$2"\n'), [])

    def test_a_function_that_runs_its_arguments_without_sudo_isnt_sudo(self):
        self.assertEqual(len(self.unknown('run() { "$@"; }\nrun rm -f "$1"\n')), 1)

    def test_an_argument_holds_what_the_call_passes(self):
        self.write(".config/app/app.conf")
        fix = 'fix() {\n  local config="$1"\n  [[ -f $config ]] || return 0\n  sed -i s/a/b/ "$config"\n}\n'
        for call in ('fix "$HOME/.config/app/app.conf"', "fix ~/.config/app/app.conf", 'file=~/.config/app/app.conf\nfix "$file"'):
            with self.subTest(call):
                self.assertEqual(titles(self.findings(fix + call + "\n"), "note"), [
                    "migrations/1.sh, line 4, looks like it edits ~/.config/app/app.conf, which differs from Omarchy's default.",
                ])
        self.write(".config/app/app.conf", "colour = blue\n")
        self.assertEqual(self.findings(fix + "fix ~/.config/app/app.conf\n"), [])

    def test_each_argument_and_each_call_are_followed(self):
        self.write(".config/app/app.conf")
        self.write(".config/other.conf")
        text = (
            'put() { echo "$2" >>"$1"; }\nput ~/.config/app/app.conf x\nput ~/.config/missing.conf y\n'
            'gone() { rm -f "$@"; }\ngone ~/.config/other.conf\n'
        )
        self.assertEqual(self.notes(text), [
            "migrations/1.sh, line 1, looks like it edits ~/.config/app/app.conf, which differs from Omarchy's default.",
            "migrations/1.sh, line 4, looks like it removes ~/.config/other.conf, which Omarchy has no default for.",
        ])

    def test_a_function_called_for_several_files_of_yours_is_one_note(self):
        for name in ("one", "two", "three"):
            self.write(f".local/bin/{name}")
        self.write(".config/app/app.conf", "colour = blue\n")
        text = (
            'drop() {\n  [[ $(head -1 "$1") == "#wrapper" ]] && rm -f "$1"\n}\n'
            "drop ~/.local/bin/one\ndrop ~/.local/bin/two\ndrop ~/.local/bin/three\n"
            "drop ~/.local/bin/missing\ndrop ~/.config/app/app.conf\n"
        )
        findings = self.findings(text)
        self.assertEqual(titles(findings, "note"), [
            "migrations/1.sh, line 2, looks like it removes 3 files of yours that aren't Omarchy's default.",
        ])
        self.assertTrue(findings[0].detail.startswith(
            "They are ~/.local/bin/one, ~/.local/bin/three and ~/.local/bin/two. It may remove only some."
        ))

    def test_an_argument_passed_on_to_another_function_is_followed(self):
        self.write(".config/app/app.conf")
        text = (
            'replace() {\n  local target="$1"\n  cat "$tmp" >"$target"\n}\n'
            'fix() {\n  local file="$1"\n  [[ -f $file ]] || return 0\n  replace "$file" old new\n}\n'
            'for path in ~/.config/app/app.conf ~/.config/missing.conf; do\n  fix "$path"\ndone\n'
        )
        self.assertEqual(self.notes(text), [
            "migrations/1.sh, line 3, looks like it edits ~/.config/app/app.conf, which differs from Omarchy's default.",
        ])

    def test_an_argument_only_known_when_it_runs_is_unknown(self):
        fix = 'fix() {\n  sed -i s/a/b/ "$1"\n}\n'
        for call in ('fix "$(pick)"', "read -r file\nfix \"$file\"", 'fix "$1"', "fix", ""):
            with self.subTest(call):
                self.assertEqual(self.unknown(fix + call + "\n"), [
                    "Couldn't tell which files migrations/1.sh writes on line 2, so check it by hand.",
                ])
        self.assertEqual(len(self.unknown(fix + "fix /etc/app.conf\nfix \"$(pick)\"\n")), 1)

    def test_an_argument_a_call_leaves_out_takes_its_default(self):
        self.write(".config/app/app.conf")
        text = 'fix() { sed -i s/a/b/ "${2:-$HOME/.config/app/app.conf}"; }\nfix x\n'
        self.assertEqual(len(self.notes(text)), 1)

    def test_a_definition_isnt_a_call(self):
        for text in ('fix() {\n  rm -f "$1"\n}\n', 'function fix {\n  rm -f "$1"\n}\n', 'function fix() {\n  rm -f "$1"\n}\n'):
            with self.subTest(text):
                self.assertEqual(len(self.unknown(text)), 1)

    def test_after_a_shift_arguments_are_unknown(self):
        self.write(".config/app/app.conf")
        before = 'fix() {\n  local file=$1\n  shift\n  rm -f "$file"\n}\nfix ~/.config/app/app.conf x\n'
        self.assertEqual(len(self.notes(before)), 1)
        after = 'fix() {\n  shift\n  rm -f "$1"\n}\nfix x ~/.config/app/app.conf\n'
        self.assertEqual(len(self.unknown(after)), 1)
        looped = 'fix() {\n  while (( $# )); do\n    rm -f "$1"\n    shift\n  done\n}\nfix ~/.config/app/app.conf x\n'
        self.assertEqual(len(self.unknown(looped)), 1)
        reset = 'fix() {\n  set -- "$HOME/.x"\n  rm -f "$1"\n}\nfix ~/.config/app/app.conf\n'
        self.assertEqual(len(self.unknown(reset)), 1)

    def test_a_function_that_never_settles_is_unknown(self):
        text = 'deeper() {\n  rm -f "$1"\n  deeper "$1/x"\n}\ndeeper ~/.config\n'
        self.assertEqual(len(self.unknown(text)), 1)

    def test_a_pattern_is_cut_from_a_known_value(self):
        self.write(".config/app/app.conf")
        for word in (
            "${name##*/}", "${long#/usr/share/}", "${backup%.bak}", "${backup%%.*}.conf",
            '${dir#"$prefix"/}.conf', "${missing%x}app.conf",
        ):
            text = (
                "name=/usr/share/x/app.conf\nlong=/usr/share/app.conf\nbackup=app.conf.bak\n"
                f'dir=/usr/share/app\nprefix=/usr/share\nmissing=\nrm -f "$HOME/.config/app/{word}"\n'
            )
            with self.subTest(word):
                self.assertEqual(self.notes(text), [
                    "migrations/1.sh, line 7, looks like it removes ~/.config/app/app.conf, which differs from Omarchy's default.",
                ])

    def test_the_shortest_and_longest_matches_differ(self):
        self.assertEqual(impact.cut("a/b/c", "#", "*/"), "b/c")
        self.assertEqual(impact.cut("a/b/c", "##", "*/"), "c")
        self.assertEqual(impact.cut("a.b.c", "%", ".*"), "a.b")
        self.assertEqual(impact.cut("a.b.c", "%%", ".*"), "a")
        self.assertEqual(impact.cut("abc", "#", "x"), "abc")

    def test_a_pattern_it_cant_read_is_unknown(self):
        for word in ("${name##$(pick)}", "${name#$prefix}", '${name##"*"}', "${name/x/y}", "${name:1}"):
            with self.subTest(word):
                text = f'name=/usr/share/x/app.conf\nrm -f "$HOME/.config/app/{word}"\n'
                self.assertEqual(len(self.unknown(text)), 1)

    def test_a_command_that_only_prints_writes_nothing(self):
        self.write(".config/app/app.conf")
        self.assertEqual(self.findings("echo rm -f ~/.config/app/app.conf\ncommand -v rm\n"), [])

    def test_a_forced_link_onto_a_file_of_yours_is_a_note(self):
        self.write(".config/app/app.conf")
        for command in (
            'ln -sfn "$OMARCHY_PATH/config/app/app.conf" ~/.config/app/app.conf',
            'ln --force -s /usr/share/x/app.conf ~/.config/app/',
            'ln -sf /usr/share/x/app.conf ~/.config/app',
        ):
            with self.subTest(command):
                self.assertEqual(self.notes(command + "\n"), [
                    "migrations/1.sh, line 1, looks like it edits ~/.config/app/app.conf, which differs from Omarchy's default.",
                ])

    def test_a_link_without_force_writes_nothing(self):
        self.write(".config/app/app.conf")
        self.assertEqual(self.findings("ln -s /usr/share/x/app.conf ~/.config/app/app.conf\n"), [])

    def test_a_link_that_already_points_there_says_nothing(self):
        (self.home / ".claude/skills").mkdir(parents=True)
        (self.home / ".claude/skills/omarchy").symlink_to("/usr/share/omarchy/default/agents/skills/omarchy")
        text = 'ln -sfn "$OMARCHY_PATH/default/agents/skills/omarchy" ~/.claude/skills/omarchy\n'
        self.assertEqual(self.findings(text), [])
        self.assertEqual(len(self.notes(text.replace("agents/skills", "other"))), 1)

    def test_a_link_with_n_replaces_a_link_to_a_folder(self):
        (self.home / "skills").mkdir()
        (self.home / "current").symlink_to(self.home / "skills")
        self.assertEqual(self.notes("ln -sfn /usr/share/x ~/current\n"), [
            "migrations/1.sh, line 1, looks like it edits the folder ~/current.",
        ])

    def test_find_that_changes_what_it_finds_in_your_files_is_unknown(self):
        self.write(".config/app/app.conf")
        for command in ("find ~/.config/app -name '*.conf' -delete", "find ~/.config/app -type f -exec sed -i s/a/b/ {} +"):
            with self.subTest(command):
                self.assertEqual(self.unknown(command + "\n"), [
                    "Couldn't tell which files migrations/1.sh writes on line 1, so check it by hand.",
                ])

    def test_find_that_runs_a_command_that_writes_nothing_says_nothing(self):
        self.write(".config/app/app.conf")
        self.assertEqual(self.findings("find ~/.config/app -name x -exec grep -l foo {} +\n"), [])
        for command in ("-exec rm {} \\;", "-execdir sudo rm {} +", "-exec sh -c 'rm \"$1\"' _ {} \\;"):
            with self.subTest(command):
                self.assertEqual(len(self.unknown(f"find ~/.config/app -name x {command}\n")), 1)

    def test_find_elsewhere_or_only_listing_says_nothing(self):
        self.write(".config/app/app.conf")
        self.write(".local/state/omarchy/x.json")
        text = (
            "find ~/.config/app -name '*.conf'\nfind /etc/app -delete\nfind ~/.local/state/omarchy -delete\n"
            "find ~/.config/missing -delete\nsudo find \"$dir\" -delete\n"
        )
        self.assertEqual(self.findings(text), [])

    def test_a_folder_says_so(self):
        self.write(".config/app/app.conf")
        self.assertEqual(self.notes("rm -rf ~/.config/app\n"), ["migrations/1.sh, line 1, looks like it removes the folder ~/.config/app."])

    def test_a_migration_it_cant_read_is_unknown(self):
        self.assertEqual(self.unknown("echo 'never closed\n"), ["Couldn't read which files migrations/1.sh writes, so check it by hand."])

    def test_it_counts_the_migrations_it_read(self):
        (self.base / "target/migrations/2.sh").write_text('rm -f "$1"\n')
        (self.base / "target/migrations/3.sh").write_text("echo 'never closed\n")
        checked = {}
        findings = self.findings("true\n", checked)
        self.assertEqual(checked, {"edits": {"pendingMigrations": 2}})
        self.assertEqual([finding.partial for finding in findings], [True, True])

    def test_with_every_migration_unreadable_nothing_is_counted(self):
        checked = {}
        findings = self.findings("echo 'never closed\n", checked)
        self.assertEqual(checked, {})
        self.assertFalse(findings[0].partial)

    def test_a_redirect_is_not_a_package(self):
        self.assertEqual(impact.package_commands("omarchy-pkg-drop a >~/log 2>&1\n"), [("drop", ["a"], False)])


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

    def findings(self):
        return impact.compare_commands(self.base / "current", self.base / "target", self.home, {})

    def attention(self):
        return titles(self.findings(), "attention")

    def write(self, name, text="omarchy-gone\n"):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def ship(self, name, text):
        path = self.base / "current" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_finds_a_call_to_a_deleted_command(self):
        (self.hooks / "my.hook").write_text("omarchy-gone\nomarchy-gone again\n")
        self.assertEqual(len(self.attention()), 1)

    def test_a_call_names_the_file_behind_it(self):
        (self.hooks / "my.hook").write_text("omarchy-gone\n")
        findings = self.findings()
        self.assertEqual(findings[0].evidence, ["~/.config/omarchy/hooks/my.hook:1"])

    def test_a_call_names_every_line_behind_it(self):
        (self.hooks / "my.hook").write_text("start\nomarchy-gone\n# omarchy-gone\nomarchy-gone; omarchy-gone\n")
        findings = self.findings()
        self.assertEqual(findings[0].evidence, ["~/.config/omarchy/hooks/my.hook:2", "~/.config/omarchy/hooks/my.hook:4"])

    def test_line_numbers_count_what_an_editor_counts(self):
        (self.hooks / "my.hook").write_text("a\x0cb\u2028c\r\nomarchy-gone\n")
        self.assertEqual(self.findings()[0].evidence, ["~/.config/omarchy/hooks/my.hook:2"])

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
        self.write(".local/bin/tool.bak")
        self.assertEqual(self.attention(), [])

    def test_ignores_git_folders(self):
        self.write(".local/bin/.git/hooks/pre-commit")
        self.assertEqual(self.findings(), [])

    def test_finds_a_call_in_the_menu_extension(self):
        self.write(".config/omarchy/extensions/omarchy-menu.jsonc", '{\n  "tools": {"action": "omarchy-gone"}\n}\n')
        self.assertEqual(self.findings()[0].evidence, ["~/.config/omarchy/extensions/omarchy-menu.jsonc:2"])

    def test_ignores_comments_in_the_menu_extension(self):
        self.write(".config/omarchy/extensions/omarchy-menu.jsonc", '{\n  // "a": {"action": "omarchy-gone"}\n}\n')
        self.assertEqual(self.attention(), [])

    def test_finds_a_call_in_each_place(self):
        places = [
            ".config/omarchy/shell.json",
            ".config/omarchy/shell.toml",
            ".config/hypr/autostart.lua",
            ".config/omarchy/plugins/demo/Widget.qml",
            ".local/bin/tool",
            ".local/bin/tool.rb",
            ".local/bin/nested/tool",
            ".config/systemd/user/tool.service",
            ".config/systemd/user/tool.timer",
            ".config/systemd/user/tool.service.d/override.conf",
            ".local/share/applications/tool.desktop",
            ".local/share/applications/nested/tool.desktop",
            *impact.STARTUP_FILES,
        ]
        for name in places:
            with self.subTest(name):
                path = self.write(name)
                self.assertEqual(self.findings()[0].evidence, [f"~/{name}:1"])
                path.unlink()

    def test_the_old_folders_still_go_by_suffix(self):
        self.write(".config/omarchy/plugins/demo/README.md")
        self.write(".config/omarchy/hooks/post-update.d/tool.sample")
        self.assertEqual(self.attention(), [])

    def test_units_turned_on_by_a_link_are_not_read_through_it(self):
        package = self.write("../packaged/omarchy-thing.service")
        wants = self.home / ".config/systemd/user/default.target.wants"
        wants.mkdir(parents=True)
        (wants / "omarchy-thing.service").symlink_to(package)
        (wants / "gone.service").symlink_to(self.base / "missing.service")
        self.assertEqual(self.findings(), [])

    def test_an_unchanged_shipped_file_is_a_note(self):
        text = "#!/bin/bash\nomarchy-gone\n"
        self.ship("install/user/first-run/tool.hook", text)
        (self.hooks / "post-update.d").mkdir()
        (self.hooks / "post-update.d/tool.hook").write_text(text)
        findings = self.findings()
        self.assertEqual(titles(findings, "attention"), [])
        self.assertEqual(len(titles(findings, "note")), 1)
        self.assertIn("Omarchy's own", findings[0].text())
        self.assertEqual(
            findings[0].evidence,
            ["~/.config/omarchy/hooks/post-update.d/tool.hook:2", "install/user/first-run/tool.hook"],
        )

    def test_an_edited_copy_needs_attention(self):
        self.ship("install/user/first-run/tool.hook", "#!/bin/bash\nomarchy-gone\n")
        (self.hooks / "tool.hook").write_text("#!/bin/bash\nomarchy-gone\n# mine\n")
        self.assertEqual(len(self.attention()), 1)

    def test_an_edit_of_the_same_size_needs_attention(self):
        self.ship("install/user/first-run/tool.hook", "#!/bin/bash\nomarchy-gone a\n")
        (self.hooks / "tool.hook").write_text("#!/bin/bash\nomarchy-gone b\n")
        self.assertEqual(len(self.attention()), 1)

    def test_a_shipped_copy_only_counts_from_the_installed_tree(self):
        (self.base / "target/install").mkdir()
        (self.base / "target/install/tool.hook").write_text("omarchy-gone\n")
        (self.hooks / "tool.hook").write_text("omarchy-gone\n")
        self.assertEqual(len(self.attention()), 1)

    def test_a_folder_linked_to_itself_finishes(self):
        (self.hooks / "my.hook").write_text("omarchy-gone\n")
        (self.hooks / "again").symlink_to(self.hooks)
        (self.hooks / "more").symlink_to(".")
        self.assertEqual(len(self.attention()), 1)

    def test_folders_linked_to_each_other_finish(self):
        one, two = self.hooks / "one", self.hooks / "two"
        one.mkdir()
        two.mkdir()
        (two / "my.hook").write_text("omarchy-gone\n")
        for link in "abcdef":
            (one / link).symlink_to(two)
            (two / link).symlink_to(one)
        self.assertEqual(len(self.attention()), 1)

    def test_a_link_to_a_folder_above_finishes(self):
        (self.hooks / "my.hook").write_text("omarchy-gone\n")
        (self.hooks / "up").symlink_to(self.home)
        self.assertEqual(len(self.attention()), 1)

    def test_a_link_to_itself_is_unknown(self):
        (self.hooks / "loop").symlink_to(self.hooks / "loop")
        self.assertEqual(self.findings()[0].level, "unknown")

    def test_a_folder_reached_twice_is_read_once(self):
        (self.home / ".config/hypr").mkdir()
        (self.home / ".config/hypr/hooks").symlink_to(self.hooks)
        (self.hooks / "my.hook").write_text("omarchy-gone\n")
        self.assertEqual(len(self.attention()), 1)

    def test_a_folder_linked_from_a_suffix_folder_is_still_read_in_full(self):
        self.write(".local/bin/tool.rb")
        (self.home / ".config/hypr").mkdir()
        (self.home / ".config/hypr/scripts").symlink_to(self.home / ".local/bin")
        self.assertEqual(self.findings()[0].evidence, ["~/.local/bin/tool.rb:1"])

    def test_a_binary_file_is_skipped(self):
        (self.hooks / "tool").write_bytes(b"\x7fELF\0\xff omarchy-gone\n")
        self.write(".local/bin/tool").write_bytes(b"\0\xff omarchy-gone\n")
        self.assertEqual(self.findings(), [])

    def test_text_that_is_not_utf8_is_read(self):
        (self.hooks / "tool").write_bytes("# caf\xe9\nomarchy-gone\n".encode("latin-1"))
        self.assertEqual(len(self.attention()), 1)

    def test_a_very_large_file_is_unknown_and_named(self):
        (self.hooks / "big").write_text("omarchy-gone\n" * 2)
        with mock.patch.object(impact, "LARGEST_SCANNED", 10):
            finding = self.findings()[0]
        self.assertEqual((finding.level, finding.evidence), ("unknown", ["~/.config/omarchy/hooks/big"]))

    def test_a_very_large_binary_is_skipped(self):
        (self.hooks / "big").write_bytes(b"\0" + b"omarchy-gone\n" * 2)
        with mock.patch.object(impact, "LARGEST_SCANNED", 10):
            self.assertEqual(self.findings(), [])

    def test_a_pipe_is_unknown_and_not_read(self):
        os.mkfifo(self.hooks / "tool.hook")
        self.assertEqual(self.findings()[0].level, "unknown")

    def test_nothing_deleted_means_nothing_to_read(self):
        (self.base / "current/bin/omarchy-gone").unlink()
        (self.base / "current/bin/omarchy-gone-too").unlink()
        (self.hooks / "tool.hook").symlink_to(self.base / "missing")
        self.assertEqual(self.findings(), [])


class OwnFiles(unittest.TestCase):
    """The plugin is the whole repository, and its tests name deleted commands on purpose."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "home"
        self.plugins = self.home / ".config/omarchy/plugins"
        self.plugins.mkdir(parents=True)
        (self.base / "current/bin").mkdir(parents=True)
        (self.base / "target/bin").mkdir(parents=True)
        (self.base / "current/bin/omarchy-gone").touch()
        # A checkout of the tool somewhere else, so the real one plays no part.
        self.running = self.base / "running-checkout"
        for name, value in [("CHECKOUT", self.running), ("COMMAND", self.running / "bin/omaupdateimpact")]:
            patcher = mock.patch.object(impact, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def plugin(self, folder, plugin_id=None):
        """A plugin that calls the deleted command, with a manifest when it has an id."""
        (folder / "tests").mkdir(parents=True)
        (folder / "tests/test_calls.sh").write_text("omarchy-gone\n")
        (folder / "Panel.qml").write_text("Item {}\n")
        if plugin_id:
            (folder / "manifest.json").write_text(json.dumps({"schemaVersion": 1, "id": plugin_id}))
        return folder

    def commands(self):
        checked = {}
        findings = impact.compare_commands(self.base / "current", self.base / "target", self.home, checked)
        return [finding.evidence[0] for finding in findings], checked["commands"]["yourFiles"]

    def linted(self):
        checked = {}
        with mock.patch.object(impact, "lint", return_value=impact.Counter()) as lint, \
                mock.patch.object(impact, "find_qmllint", return_value=("/bin/true", [])):
            findings = impact.compare_plugins(Path("current"), Path("target"), self.home, checked)
        plugins = sorted({call.args[0].name for call in lint.call_args_list})
        return plugins, checked["plugins"]["linted"], findings

    def test_a_plugin_with_this_tools_id_isnt_read_or_linted(self):
        self.plugin(self.plugins / "ours", impact.PLUGIN_ID)
        self.assertEqual(self.commands(), ([], 0))
        self.assertEqual(self.linted(), ([], 0, []))

    @unittest.skipIf(os.geteuid() == 0, "root reads a denied folder")
    def test_a_plugin_that_cant_be_read_doesnt_stop_the_run_on_python_3_11(self):
        # Python 3.11's Path.is_file and is_dir raise on a denied stat, and newer ones
        # return False. The minimum is 3.11, so this test gives them 3.11's behaviour.
        def as_on_3_11(kind):
            def check(path):
                try:
                    return kind(os.stat(path).st_mode)
                except OSError as error:
                    if error.errno not in (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP):
                        raise
                    return False
            return check

        denied = self.plugin(self.plugins / "denied", impact.PLUGIN_ID)
        denied.chmod(0)
        self.addCleanup(denied.chmod, 0o755)
        with mock.patch.object(Path, "is_file", as_on_3_11(stat.S_ISREG)), \
                mock.patch.object(Path, "is_dir", as_on_3_11(stat.S_ISDIR)):
            own = impact.own_paths(self.home)
            findings = impact.compare_commands(self.base / "current", self.base / "target", self.home, {})
        # Its manifest can't be read, so it isn't left out, and the commands check says so.
        self.assertNotIn(impact.real_path(denied), own)
        self.assertEqual([(f.level, f.evidence) for f in findings], [("unknown", ["~/.config/omarchy/plugins/denied"])])

    def test_a_plugin_that_isnt_this_tool_beside_it_still_is(self):
        self.plugin(self.plugins / "ours", impact.PLUGIN_ID)
        self.plugin(self.plugins / "weather", "io.github.example.weather")
        self.assertEqual(self.commands(), (["~/.config/omarchy/plugins/weather/tests/test_calls.sh:1"], 3))
        plugins, linted, _ = self.linted()
        self.assertEqual((plugins, linted), (["weather"], 1))

    def test_this_tools_plugin_is_left_out_wherever_it_is_linked_from(self):
        (self.plugins / "ours").symlink_to(self.plugin(self.base / "elsewhere", impact.PLUGIN_ID))
        self.assertEqual(self.commands(), ([], 0))
        self.assertEqual(self.linted(), ([], 0, []))

    def test_the_running_checkout_with_this_tools_manifest_is_left_out_outside_the_plugins_folder(self):
        (self.home / ".config/hypr").mkdir()
        (self.home / ".config/hypr/dev").symlink_to(self.plugin(self.running, impact.PLUGIN_ID))
        self.assertEqual(self.commands(), ([], 0))

    def test_a_running_checkout_without_the_manifest_leaves_out_only_the_command(self):
        # As a copy in ~/.local/bin or a package in /usr/bin: the folder above bin/ is yours.
        self.plugin(self.running)
        (self.running / "bin").mkdir()
        (self.running / "bin/omaupdateimpact").write_text("omarchy-gone\n")
        (self.home / ".config/hypr").mkdir()
        (self.home / ".config/hypr/dev").symlink_to(self.running)
        self.assertEqual(self.commands(), (["~/.config/hypr/dev/tests/test_calls.sh:1"], 2))

    def test_a_manifest_that_is_a_pipe_isnt_opened(self):
        folder = self.plugins / "piped"
        folder.mkdir()
        os.mkfifo(folder / "manifest.json")
        answer = []
        reader = threading.Thread(target=lambda: answer.append(impact.is_own_plugin(folder)), daemon=True)
        reader.start()
        reader.join(5)
        waited = reader.is_alive()
        if waited:
            # Let the stuck read end, so the test can finish.
            os.close(os.open(folder / "manifest.json", os.O_WRONLY | os.O_NONBLOCK))
            reader.join(5)
        self.assertFalse(waited, "is_own_plugin waited on a pipe")
        self.assertEqual(answer, [False])

    def test_the_tools_own_files_are_left_out_wherever_they_are_linked_from(self):
        ours = self.plugin(self.plugins / "ours", impact.PLUGIN_ID)
        (self.running / "bin").mkdir(parents=True)
        (self.running / "bin/omaupdateimpact").write_text("omarchy-gone\n")
        (self.home / ".local/bin").mkdir(parents=True)
        # As install.sh links it, and a folder of the plugin's linked in from your config.
        (self.home / ".local/bin/omaupdateimpact").symlink_to(self.running / "bin/omaupdateimpact")
        (self.home / ".config/hypr").mkdir()
        (self.home / ".config/hypr/scripts").symlink_to(ours / "tests")
        (self.home / ".bashrc").symlink_to(ours / "tests/test_calls.sh")
        self.assertEqual(self.commands(), ([], 0))

    def test_a_manifest_it_cant_read_leaves_nothing_out(self):
        for name, manifest in [("broken", "{"), ("list", "[]"), ("deep", "[" * 100000), ("other", '{"id": 1}')]:
            self.plugin(self.plugins / name)
            (self.plugins / name / "manifest.json").write_text(manifest)
        evidence, read = self.commands()
        self.assertEqual((len(evidence), read), (4, 12))
        self.assertEqual(self.linted()[:2], (["broken", "deep", "list", "other"], 4))

    def test_a_checkout_that_holds_your_home_leaves_nothing_out(self):
        self.plugin(self.plugins / "weather")
        (self.base / "manifest.json").write_text(json.dumps({"id": impact.PLUGIN_ID}))
        with mock.patch.object(impact, "CHECKOUT", self.base):
            self.assertEqual(self.commands(), (["~/.config/omarchy/plugins/weather/tests/test_calls.sh:1"], 2))
            self.assertEqual(self.linted()[:2], (["weather"], 1))

    def test_a_plugin_with_this_tools_id_that_holds_your_home_leaves_nothing_out(self):
        (self.home / "manifest.json").write_text(json.dumps({"id": impact.PLUGIN_ID}))
        (self.plugins / "home").symlink_to(self.home)
        (self.home / ".config/hypr").mkdir()
        (self.home / ".config/hypr/autostart.lua").write_text('o.exec("omarchy-gone")\n')
        evidence, _ = self.commands()
        self.assertEqual(evidence, ["~/.config/hypr/autostart.lua:1"])


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
            original_find = impact.find_qmllint
            impact.find_qmllint = lambda: ("/bin/true", [])
            self.addCleanup(setattr, impact, "find_qmllint", original_find)
            findings = impact.compare_plugins(Path("current"), Path("target"), home, {})
            notes = titles(findings, "note")
            self.assertEqual(len(notes), 2)
            self.assertIn("1 new qmllint warning, such as a.qml: new", notes[0])
            self.assertEqual(
                [finding.evidence for finding in findings],
                [["~/.config/omarchy/plugins/demo/a.qml"], ["~/.config/omarchy/plugins"]],
            )

    def findings_without_qmllint(self, home):
        with mock.patch.object(impact.shutil, "which", return_value=None), \
                mock.patch.object(impact, "QMLLINT", "/nonexistent/qmllint"):
            return impact.compare_plugins(Path("current"), Path("target"), home, {})

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

    def test_two_new_warnings_are_plural(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".config/omarchy/plugins/demo").mkdir(parents=True)
            found = [impact.Counter(), impact.Counter({("a.qml", "new"): 2})]
            with mock.patch.object(impact, "lint", side_effect=found), \
                    mock.patch.object(impact, "find_qmllint", return_value=("/bin/true", [])):
                findings = impact.compare_plugins(Path("current"), Path("target"), home, {})
        self.assertIn("2 new qmllint warnings, such as", findings[0].title)


class Lint(unittest.TestCase):
    """lint() on a fictional plugin, with a script in place of qmllint."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "home"
        self.plugin = self.home / ".config/omarchy/plugins/demo"
        self.plugin.mkdir(parents=True)
        (self.plugin / "Demo.qml").write_text("import QtQuick\nItem {}\n")
        for tree in ["current", "target"]:
            (self.base / tree / "shell").mkdir(parents=True)

    def qmllint(self, script):
        path = self.base / "qmllint"
        path.write_text(f"#!/bin/sh\n{QT6_VERSION}\n{script}\n")
        path.chmod(0o755)
        return path

    def replay(self, name, code=0):
        """A qmllint that prints what the real one printed, on stderr like the real one."""
        return self.qmllint(f"cat '{QMLLINT_OUTPUT / name}' >&2\nexit {code}")

    def lint(self, qmllint, tree="current"):
        return impact.lint(self.plugin, self.base / tree / "shell", str(qmllint))

    def findings(self, qmllint):
        return self.checked(str(qmllint))[1]

    def checked(self, qmllint):
        checked = {}
        with mock.patch.object(impact.shutil, "which", return_value=qmllint), \
                mock.patch.object(impact, "QMLLINT", str(self.base / "missing")):
            findings = impact.compare_plugins(self.base / "current", self.base / "target", self.home, checked)
        return checked, findings

    def test_only_linted_plugins_are_counted(self):
        (self.plugin.parent / "gone").symlink_to(self.base / "missing")
        checked, findings = self.checked(str(self.qmllint("exit 0")))
        self.assertEqual(checked, {"plugins": {"linted": 1}})
        self.assertEqual([finding.partial for finding in findings if finding.level == "unknown"], [True])

    def test_nothing_linted_isnt_counted_and_didnt_run(self):
        checked, findings = self.checked(str(self.qmllint("kill -TERM $$")))
        self.assertEqual(checked, {})
        self.assertFalse(findings[0].partial)

    def test_no_qmllint_isnt_counted_and_didnt_run(self):
        checked, findings = self.checked(None)
        self.assertEqual(checked, {})
        self.assertFalse(findings[0].partial)

    def test_reads_real_warnings(self):
        self.assertEqual(self.lint(self.replay("current.txt")), {
            ("Demo.qml", "Unqualified access [unqualified]"): 1,
        })

    def test_a_warning_with_no_file_is_not_counted(self):
        self.assertEqual(self.lint(self.replay("release.txt")), {
            ("Demo.qml", 'Warnings occurred while importing module "qs.Palette": [import]'): 1,
            ("Demo.qml", "Unqualified access [unqualified]"): 2,
        })

    def test_info_lines_are_not_warnings(self):
        qmllint = self.qmllint("echo 'Info: /plugins/demo/Demo.qml:3:1: Unused import [unused-imports]' >&2")
        self.assertEqual(self.lint(qmllint), {})

    def test_warnings_from_a_failed_exit_still_count(self):
        warnings = self.lint(self.replay("syntax-error.txt", 255))
        self.assertEqual(warnings, {("Broken.qml", "Expected token `;' [syntax]"): 1})

    def test_new_warnings_between_real_runs(self):
        output = {"current": "current.txt", "target": "release.txt"}
        qmllint = self.qmllint(
            'case "$(readlink "$2/qs")" in\n'
            + "".join(f"  */{tree}/shell) cat '{QMLLINT_OUTPUT / name}' >&2 ;;\n" for tree, name in output.items())
            + "esac"
        )
        findings = self.findings(qmllint)
        self.assertEqual(len(titles(findings, "note")), 2)
        self.assertIn("demo: 2 new qmllint warnings, such as Demo.qml", findings[0].title)

    def assert_unknown(self, qmllint, reason):
        findings = self.findings(qmllint)
        self.assertEqual([finding.level for finding in findings], ["unknown"])
        self.assertEqual(findings[0].check, "plugins")
        self.assertIn("demo couldn't be linted", findings[0].title)
        self.assertIn(reason, findings[0].detail)
        self.assertEqual(findings[0].evidence, ["~/.config/omarchy/plugins/demo"])

    def test_a_failing_qmllint_is_unknown(self):
        self.assert_unknown(self.qmllint("exit 1"), "exited 1")

    def test_a_signal_is_unknown(self):
        self.assert_unknown(self.qmllint("kill -TERM $$"), "signal 15")

    def test_a_signal_is_unknown_even_with_warnings(self):
        qmllint = self.qmllint(f"cat '{QMLLINT_OUTPUT / 'current.txt'}' >&2\nkill -KILL $$")
        self.assert_unknown(qmllint, "signal 9")

    def test_a_failure_on_the_release_alone_is_unknown(self):
        qmllint = self.qmllint('case "$(readlink "$2/qs")" in\n  */target/shell) exit 1 ;;\nesac')
        self.assert_unknown(qmllint, "exited 1")

    def test_a_file_it_could_not_open_is_unknown_even_with_warnings(self):
        self.assert_unknown(self.replay("unreadable-file.txt", 255), "couldn't open Gone.qml")

    def test_a_qmllint_that_cant_start_is_unknown(self):
        qmllint = self.qmllint("")
        qmllint.chmod(0o644)
        with self.assertRaisesRegex(impact.LintFailed, "couldn't start"):
            self.lint(qmllint)

    def test_output_that_isnt_text_is_still_read(self):
        qmllint = self.qmllint(r"printf 'caf\351\n' >&2; cat '%s' >&2" % (QMLLINT_OUTPUT / "current.txt"))
        self.assertEqual(sum(self.lint(qmllint).values()), 1)

    def test_a_hanging_qmllint_is_stopped(self):
        pid = self.base / "pid"
        qmllint = self.qmllint(f"echo $$ > '{pid}'\nexec sleep 30")
        with mock.patch.object(impact, "LINT_TIMEOUT", 0.2):
            self.assert_unknown(qmllint, "ran past 0.2 seconds")
        self.assertFalse(Path("/proc", pid.read_text().strip()).exists())

    def test_one_failure_does_not_hide_another_plugin(self):
        other = self.plugin.parent / "other"
        other.mkdir()
        (other / "Other.qml").write_text("import QtQuick\nItem {}\n")
        findings = self.findings(self.qmllint('case "$PWD" in\n  */demo) exit 1 ;;\nesac'))
        self.assertEqual([finding.level for finding in findings], ["unknown", "note"])

    def test_a_plugin_that_is_a_broken_link_is_unknown(self):
        (self.plugin.parent / "gone").symlink_to("nowhere")
        findings = self.findings(self.qmllint("exit 0"))
        self.assertEqual([finding.level for finding in findings], ["unknown", "note"])
        self.assertIn("gone is a broken link", findings[0].title)
        self.assertEqual(findings[0].evidence, ["~/.config/omarchy/plugins/gone"])

    def test_a_broken_plugin_alone_is_unknown_with_no_closing_note(self):
        shutil.rmtree(self.plugin)
        (self.plugin.parent / "gone").symlink_to("nowhere")
        self.assertEqual([finding.level for finding in self.findings(self.qmllint("exit 0"))], ["unknown"])

    def test_a_broken_plugin_does_not_hide_a_missing_qmllint(self):
        (self.plugin.parent / "gone").symlink_to("nowhere")
        with mock.patch.object(impact.shutil, "which", return_value=None), \
                mock.patch.object(impact, "QMLLINT", "/nonexistent/qmllint"):
            findings = impact.compare_plugins(self.base / "current", self.base / "target", self.home, {})
        self.assertEqual(len(titles(findings, "unknown")), 2)
        self.assertIn("qmllint wasn't found", findings[0].title)
        self.assertIn("gone is a broken link", findings[1].title)

    def test_a_plain_file_is_not_a_plugin(self):
        (self.plugin.parent / "notes.txt").write_text("not a plugin")
        self.assertEqual([finding.level for finding in self.findings(self.qmllint("exit 0"))], ["note"])

    def assert_plugins_folder_unknown(self, reason):
        findings = self.findings(self.qmllint("exit 0"))
        self.assertEqual([finding.level for finding in findings], ["unknown"])
        self.assertEqual(findings[0].evidence, ["~/.config/omarchy/plugins"])
        self.assertIn(reason, findings[0].detail)

    def test_a_plugins_folder_that_is_a_broken_link_is_unknown(self):
        plugins = self.plugin.parent
        shutil.rmtree(plugins)
        plugins.symlink_to("nowhere")
        self.assert_plugins_folder_unknown("broken link")

    def test_a_plugins_folder_that_is_a_file_is_unknown(self):
        plugins = self.plugin.parent
        shutil.rmtree(plugins)
        plugins.write_text("not a folder")
        self.assert_plugins_folder_unknown("isn't a folder")

    @unittest.skipIf(os.geteuid() == 0, "root reads a denied folder")
    def test_a_denied_plugins_folder_is_unknown(self):
        plugins = self.plugin.parent
        plugins.chmod(0)
        self.addCleanup(plugins.chmod, 0o755)
        self.assert_plugins_folder_unknown("Permission denied")

    def test_no_plugins_folder_is_nothing_to_check(self):
        shutil.rmtree(self.plugin.parent)
        self.assertEqual(self.findings(self.qmllint("exit 0")), [])

    @unittest.skipIf(os.geteuid() == 0, "root reads a denied folder")
    def test_a_denied_folder_in_a_plugin_is_unknown(self):
        closed = self.plugin / "panel/closed"
        closed.mkdir(parents=True)
        closed.chmod(0)
        self.addCleanup(closed.chmod, 0o755)
        self.assert_unknown(self.qmllint("exit 0"), "demo/panel/closed couldn't be read: Permission denied")

    @unittest.skipIf(os.geteuid() == 0, "root reads a denied folder")
    def test_a_denied_plugin_is_unknown(self):
        self.plugin.chmod(0)
        self.addCleanup(self.plugin.chmod, 0o755)
        self.assert_unknown(self.qmllint("exit 0"), "demo couldn't be read: Permission denied")

    def test_a_linked_folder_is_linted(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "Linked.qml").touch()
        (self.plugin / "linked").symlink_to(outside)
        qmllint = self.qmllint('printf "%s\\n" "$@" > "$0.args"')
        self.lint(qmllint)
        self.assertIn(str(self.plugin / "linked/Linked.qml"), Path(f"{qmllint}.args").read_text())

    def test_git_is_not_linted(self):
        (self.plugin / ".git").mkdir()
        (self.plugin / ".git/Hook.qml").touch()
        qmllint = self.qmllint('printf "%s\\n" "$@" > "$0.args"')
        self.lint(qmllint)
        self.assertNotIn("Hook.qml", Path(f"{qmllint}.args").read_text())

    def new_warning_in(self, *names):
        """A qmllint that warns about these files in the plugin, on the release's shell only."""
        lines = "".join(f"  echo \"Warning: $PWD/{name}:1:1: gone [import]\" >&2\n" for name in names)
        return self.qmllint(f'if [ ! -d "$2/qs/Palette" ]; then\n{lines}fi')

    def test_evidence_names_a_file_in_a_subfolder(self):
        (self.base / "current/shell/Palette").mkdir()
        findings = self.findings(self.new_warning_in("panel/Demo.qml"))
        self.assertIn("such as panel/Demo.qml: gone", findings[0].title)
        self.assertEqual(findings[0].evidence, ["~/.config/omarchy/plugins/demo/panel/Demo.qml"])

    def test_two_files_with_one_name_stay_apart(self):
        warnings = self.lint(self.new_warning_in("a/Demo.qml", "b/Demo.qml"))
        self.assertEqual(warnings, {("a/Demo.qml", "gone [import]"): 1, ("b/Demo.qml", "gone [import]"): 1})

    def test_a_file_it_could_not_open_is_named_by_its_path_in_the_plugin(self):
        qmllint = self.qmllint('echo "Warning: $PWD/panel/Gone.qml:: Failed to open file" >&2\nexit 255')
        self.assert_unknown(qmllint, "couldn't open panel/Gone.qml")

    def test_no_qml_needs_no_lint(self):
        (self.plugin / "Demo.qml").unlink()
        self.assertEqual(self.lint("/bin/false"), {})

    def test_relative_trees_find_the_same_warnings_as_absolute_ones(self):
        (self.base / "current/shell/Palette").mkdir()
        qmllint = self.qmllint(
            'if [ ! -d "$2/qs/Palette" ]; then\n'
            "  echo 'Warning: /plugins/demo/Demo.qml:2:1: Palette is gone [import]' >&2\n"
            "fi"
        )
        with mock.patch.object(impact.shutil, "which", return_value=str(qmllint)):
            absolute = impact.compare_plugins(self.base / "current", self.base / "target", self.home, {})
            with contextlib.chdir(self.base):
                relative = impact.compare_plugins(Path("current"), Path("target"), self.home, {})
        self.assertIn("1 new qmllint warning, such as Demo.qml: Palette is gone", absolute[0].title)
        self.assertEqual(relative, absolute)


class PickingQmllint(unittest.TestCase):
    """find_qmllint() on scripts that stand for qmllint on PATH and at impact.QMLLINT."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "home"
        plugin = self.home / ".config/omarchy/plugins/demo"
        plugin.mkdir(parents=True)
        (plugin / "Demo.qml").write_text("import QtQuick\nItem {}\n")
        (self.base / "shell").mkdir()

    def script(self, name, version, lint="exit 1"):
        """A qmllint that does this for --version, and fails to lint unless told otherwise."""
        path = self.base / name
        path.write_text(f'#!/bin/sh\n[ "$1" != --version ] || {{ {version}; }}\n{lint}\n')
        path.chmod(0o755)
        return str(path)

    def says(self, name, version, lint="exit 1"):
        return self.script(name, f"echo '{version}'; exit 0", lint)

    def found(self, on_path, installed=None):
        with mock.patch.object(impact.shutil, "which", return_value=on_path), \
                mock.patch.object(impact, "QMLLINT", installed or str(self.base / "missing")):
            return impact.find_qmllint()

    def checked(self, on_path, installed=None):
        checked = {}
        with mock.patch.object(impact.shutil, "which", return_value=on_path), \
                mock.patch.object(impact, "QMLLINT", installed or str(self.base / "missing")):
            findings = impact.compare_plugins(self.base, self.base, self.home, checked)
        return checked, findings

    def test_qt6_and_newer_count(self):
        # 6.4.2 is what Ubuntu 24.04 prints in CI, and 6.12.0 is what Arch prints.
        for version in ["qmllint 6.4.2", "qmllint 6.12.0", "qmllint 7.0.0"]:
            with self.subTest(version):
                qmllint = self.says("qmllint", version)
                self.assertEqual(self.found(qmllint), (qmllint, []))

    def test_qt5_first_on_path_isnt_used_when_qt6_exists(self):
        older, newer = self.says("qt5", "qmllint 1.0"), self.says("qt6", "qmllint 6.12.0", lint="exit 0")
        self.assertEqual(self.found(older, newer)[0], newer)
        # Linting with the Qt 5 script would fail.
        self.assertEqual(self.checked(older, newer)[0], {"plugins": {"linted": 1}})

    def test_qt6_on_path_comes_first(self):
        first, second = self.says("first", "qmllint 6.12.0"), self.says("second", "qmllint 6.4.2")
        self.assertEqual(self.found(first, second), (first, []))

    def test_only_qt5_is_unknown_and_names_what_was_found(self):
        older = self.says("qmllint", "qmllint 1.0")
        checked, findings = self.checked(older)
        self.assertEqual(checked, {})
        self.assertEqual([finding.level for finding in findings], ["unknown"])
        self.assertFalse(findings[0].partial)
        self.assertEqual(findings[0].evidence, ["~/.config/omarchy/plugins"])
        self.assertIn("isn't from Qt 6", findings[0].title)
        self.assertEqual(findings[0].detail, f"Found {older} (qmllint 1.0).")

    def test_only_qt5_does_not_hide_a_broken_plugin(self):
        (self.home / ".config/omarchy/plugins/gone").symlink_to("nowhere")
        _, findings = self.checked(self.says("qmllint", "qmllint 1.0"))
        self.assertEqual(len(titles(findings, "unknown")), 2)

    def test_only_qt5_does_not_matter_without_plugins(self):
        shutil.rmtree(self.home / ".config/omarchy/plugins")
        self.assertEqual(self.checked(self.says("qmllint", "qmllint 1.0")), ({"plugins": {"linted": 0}}, []))

    def test_one_path_is_named_once(self):
        older = self.says("qmllint", "qmllint 1.0")
        self.assertEqual(self.found(older, older), (None, [(older, "qmllint 1.0")]))

    def test_both_are_named_when_neither_counts(self):
        first, second = self.says("first", "qmllint 1.0"), self.script("second", "exit 1")
        _, findings = self.checked(first, second)
        self.assertEqual(findings[0].detail, f"Found {first} (qmllint 1.0), {second} (no version it could read).")

    def test_a_path_in_home_is_shown_short(self):
        (self.home / "bin").mkdir()
        older = self.says("home/bin/qmllint", "qmllint 1.0")
        self.assertEqual(self.checked(older)[1][0].detail, "Found ~/bin/qmllint (qmllint 1.0).")

    def test_nothing_found_stays_not_found(self):
        self.assertEqual(self.found(None), (None, []))
        self.assertIn("qmllint wasn't found", self.checked(None)[1][0].title)

    def assert_doesnt_count(self, script):
        qmllint = self.script("qmllint", script)
        self.assertEqual(self.found(qmllint), (None, [(qmllint, "no version it could read")]))

    def test_a_version_that_fails_doesnt_count(self):
        self.assert_doesnt_count("echo 'qmllint 6.12.0'; exit 1")

    def test_a_version_killed_by_a_signal_doesnt_count(self):
        self.assert_doesnt_count("echo 'qmllint 6.12.0'; kill -TERM $$")

    def test_a_version_that_hangs_doesnt_count(self):
        with mock.patch.object(impact, "LINT_TIMEOUT", 0.2):
            self.assert_doesnt_count("exec sleep 30")

    def test_a_qmllint_that_cant_start_doesnt_count(self):
        qmllint = self.says("qmllint", "qmllint 6.12.0")
        Path(qmllint).chmod(0o644)
        self.assertEqual(self.found(qmllint), (None, [(qmllint, "no version it could read")]))

    def test_a_version_it_cant_read_doesnt_count(self):
        for output in [
            "",
            "qmllint",
            "qmllint 6",
            "qmllint six.twelve",
            "true (GNU coreutils) 9.4",
            "qmllint 6.12.0 and more",
            "not qmllint 6.12.0",
            "qmllint 6.12.0-\033[31m",
            f"qmllint {'9' * 5000}.0",
        ]:
            with self.subTest(output[:30]):
                self.assert_doesnt_count(f"printf '%b\\n' '{output}'; exit 0")

    def test_a_version_that_isnt_text_doesnt_count(self):
        self.assert_doesnt_count(r"printf 'qmllint 6\351\n'; exit 0")

    def test_a_version_on_stderr_doesnt_count(self):
        self.assert_doesnt_count("echo 'qmllint 6.12.0' >&2; exit 0")


@unittest.skipUnless(REAL_QMLLINT, "no qmllint from Qt 6 or newer is installed")
class RealQmllint(unittest.TestCase):
    """The fictional plugin through the real qmllint, when there is one."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.home = self.base / "home"
        plugin = self.home / ".config/omarchy/plugins/demo"
        plugin.mkdir(parents=True)
        shutil.copy(QMLLINT_OUTPUT / "plugin/Demo.qml", plugin)
        shutil.copytree(QMLLINT_OUTPUT / "shell", self.base / "current/shell")
        (self.base / "target/shell").mkdir(parents=True)

    def findings(self, current, target):
        with mock.patch.object(impact.shutil, "which", return_value=REAL_QMLLINT):
            return impact.compare_plugins(current, target, self.home, {})

    def test_a_module_the_release_removes_is_a_new_warning(self):
        findings = self.findings(self.base / "current", self.base / "target")
        self.assertIn("2 new qmllint warnings", findings[0].title)

    def test_evidence_names_a_file_in_a_subfolder(self):
        plugin = self.home / ".config/omarchy/plugins/demo"
        (plugin / "panel").mkdir()
        (plugin / "Demo.qml").rename(plugin / "panel/Demo.qml")
        findings = self.findings(self.base / "current", self.base / "target")
        self.assertEqual(findings[0].evidence, ["~/.config/omarchy/plugins/demo/panel/Demo.qml"])

    def test_two_files_with_one_name_stay_apart(self):
        plugin = self.home / ".config/omarchy/plugins/demo"
        for folder in ["a", "b"]:
            (plugin / folder).mkdir()
            shutil.copy(plugin / "Demo.qml", plugin / folder)
        (plugin / "Demo.qml").unlink()
        warnings = impact.lint(plugin, self.base / "target/shell", REAL_QMLLINT)
        self.assertEqual({file for file, _ in warnings}, {"a/Demo.qml", "b/Demo.qml"})

    def test_relative_trees_find_the_same_warnings_as_absolute_ones(self):
        absolute = self.findings(self.base / "current", self.base / "target")
        with contextlib.chdir(self.base):
            relative = self.findings(Path("current"), Path("target"))
        self.assertEqual(relative, absolute)


class Wrapping(unittest.TestCase):
    def test_a_command_isnt_split_at_a_hyphen(self):
        text = f"{'x' * 70} omarchy-voxtype-install calls"
        self.assertEqual(impact.wrapped(text), f"{'x' * 70}\nomarchy-voxtype-install calls")

    def test_a_name_past_the_width_isnt_split(self):
        name = "omarchy-" + "x" * 100
        self.assertEqual(impact.wrapped(f"a {name} b"), f"a\n{name}\nb")

    def test_a_line_to_copy_isnt_split_at_its_spaces(self):
        for line in ('hl.unbind("SUPER + CTRL + SHIFT + DOWN")', "omarchy pkg add fictional-editor"):
            text = f"{'x' * 70} {line} too"
            self.assertEqual(impact.wrapped(text), f"{'x' * 70}\n{line} too")


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
        os.environ.pop("NO_COLOR", None)
        # Reviewed findings come from the made-up home, not the developer's own config.
        os.environ.pop("XDG_CONFIG_HOME", None)
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
        out, err = (Terminal(), Terminal()) if self.terminal else (io.StringIO(), io.StringIO())
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

    def download(self, *responses, args=("v1.2.3",), notes=None, packages=frozenset()):
        """Run with each network request answered by the next response, and the notes by notes or a 404."""
        answers = iter(responses)

        def answer(request, timeout):
            if "/releases/tags/" in request.full_url:
                if notes is None:
                    raise refused(404)
                return io.BytesIO(json.dumps({"body": notes}).encode())
            response = next(answers)
            if isinstance(response, BaseException):
                raise response
            return response

        with mock.patch.object(impact.urllib.request, "urlopen", side_effect=answer), \
                mock.patch.object(impact, "installed_packages", return_value=packages):
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

    def test_an_edit_to_a_file_you_changed_is_a_note_and_exits_0(self):
        (self.home / ".config/app").mkdir(parents=True)
        (self.home / ".config/app/app.conf").write_text("mine\n")
        (self.base / "target/migrations/1.sh").write_text("sed -i s/a/b/ ~/.config/app/app.conf\n")
        code, out, _ = self.check("--all")
        self.assertEqual(code, 0)
        self.assertIn("migrations/1.sh, line 1, looks like it edits ~/.config/app/app.conf", " ".join(out.split()))
        self.assertIn("Nothing found", out)

    def test_a_write_it_cant_place_exits_3_and_names_the_line(self):
        (self.base / "target/migrations/1.sh").write_text('true\nrm -f "$1"\n')
        code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertIn("migrations/1.sh writes on line 2", out)
        self.assertIn("These checks ran in part: edits.", out)

    def test_a_missing_pacman_exits_3_and_never_says_nothing_found(self):
        empty = self.base / "empty"
        empty.mkdir()
        with mock.patch.dict(os.environ, PATH=str(empty)):
            code, out, _ = self.run_main("--target", str(self.base / "target"))
        self.assertEqual(code, 3)
        self.assertNotIn("nothing found", out.lower())
        self.assertEqual(out.splitlines()[-1], "These checks didn't run: packages.")

    def test_a_failing_qmllint_exits_3_and_names_the_plugin(self):
        plugin = self.home / ".config/omarchy/plugins/demo"
        plugin.mkdir(parents=True)
        (plugin / "Demo.qml").write_text("import QtQuick\nItem {}\n")
        qmllint = self.base / "qmllint"
        qmllint.write_text(f"#!/bin/sh\n{QT6_VERSION}\nexit 1\n")
        qmllint.chmod(0o755)
        with mock.patch.object(impact.shutil, "which", return_value=str(qmllint)):
            code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertIn("demo couldn't be linted", out)
        self.assertEqual(out.splitlines()[-1], "These checks didn't run: plugins.")
        self.assertNotIn("nothing found", out.lower())

    def test_only_a_qt5_qmllint_exits_3_and_never_says_nothing_found(self):
        plugin = self.home / ".config/omarchy/plugins/demo"
        plugin.mkdir(parents=True)
        (plugin / "Demo.qml").write_text("import QtQuick\nItem {}\n")
        qmllint = self.base / "qmllint"
        qmllint.write_text("#!/bin/sh\necho 'qmllint 1.0'\n")
        qmllint.chmod(0o755)
        with mock.patch.object(impact.shutil, "which", return_value=str(qmllint)), \
                mock.patch.object(impact, "QMLLINT", str(self.base / "missing")):
            code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertEqual(out.splitlines()[-1], "These checks didn't run: plugins.")
        self.assertNotIn("nothing found", out.lower())

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

    def test_what_was_checked_is_shown(self):
        (self.base / "target/migrations/1.sh").write_text("true\n")
        (self.base / "target/migrations/2.sh").write_text("true\n")
        self.assertIn(
            "Checked 1 default binding, 0 of yours, 2 pending migrations, no deleted commands, no plugins.",
            " ".join(self.check()[1].split()),
        )

    def test_migrations_already_run_arent_counted(self):
        (self.base / "target/migrations/1.sh").write_text("true\n")
        (self.base / "target/migrations/2.sh").write_text("true\n")
        state = self.home / ".local/state/omarchy/migrations"
        state.mkdir(parents=True)
        (state / "1.sh").touch()
        self.assertIn("1 pending migration,", self.check()[1])

    def test_a_check_that_didnt_run_isnt_listed_as_checked(self):
        out = " ".join(self.check(packages=None)[1].split())
        self.assertIn("0 pending migrations for file edits,", out)
        self.assertNotIn("for packages", out)

    def test_unreadable_migrations_arent_counted(self):
        (self.base / "target/migrations/1.sh").write_text('omarchy-pkg-drop "$a"\n')
        (self.base / "target/migrations/2.sh").write_text("true\n")
        out = " ".join(self.check(packages={"a"})[1].split())
        self.assertIn("1 pending migration for packages and 2 for file edits,", out)

    def test_a_removal_with_every_migration_unreadable_isnt_listed(self):
        (self.base / "target/migrations/1.sh").write_text('omarchy-pkg-drop "$a"\n')
        out = " ".join(self.check(packages={"a"})[1].split())
        self.assertIn("1 pending migration for file edits,", out)
        self.assertNotIn("for packages", out)

    def test_migrations_both_checks_read_are_counted_once(self):
        (self.base / "target/migrations/1.sh").write_text("omarchy-pkg-drop a\n")
        out = " ".join(self.check()[1].split())
        self.assertIn(", 1 pending migration, ", out)

    def test_a_migration_it_cant_read_beside_one_it_can_ran_in_part(self):
        (self.base / "target/migrations/1.sh").write_text('omarchy-pkg-drop "$a"\n')
        (self.base / "target/migrations/2.sh").write_text("true\n")
        code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertEqual(out.splitlines()[-1], "These checks ran in part: packages.")

    def test_notes_collapse_unless_all_is_given(self):
        for tree in ("current", "target"):
            (self.base / tree / "default/hypr/keys.lua").write_text('o.bind("SUPER + " .. key, "x", "y")')
        code, out, _ = self.check()
        self.assertEqual(code, 0)
        self.assertIn("Worth knowing: 1 note. Add --all to see them.", out)
        self.assertNotIn("computed", out)
        self.assertIn("Nothing found", out)

    def test_no_notes_means_no_line_about_them(self):
        self.assertNotIn("Worth knowing", self.check()[1])
        self.assertNotIn("Worth knowing", self.check("--all")[1])

    def test_a_check_that_didnt_run_is_named_beside_one_that_ran_in_part(self):
        (self.base / "target/default/hypr/helpers.lua").write_text("function o.bind_foo(keys) end")
        code, out, _ = self.check(packages=None)
        self.assertEqual(code, 3)
        self.assertEqual(
            out.splitlines()[-1], "These checks didn't run: packages. These checks ran in part: bindings."
        )

    def test_debug_shows_the_traceback(self):
        with mock.patch.object(impact, "compare_commands", side_effect=RuntimeError("broke")):
            code, _, err = self.check("--debug")
        self.assertEqual(code, 2)
        self.assertIn("Traceback", err)


class Json(ProgramCase):
    def document(self, *args, **kwargs):
        code, out, err = self.check("--json", *args, **kwargs)
        return code, json.loads(out), err

    def test_a_clean_run_is_a_clear_document(self):
        code, document, err = self.document()
        self.assertEqual((code, document["result"], err), (0, "clear", ""))
        self.assertEqual(document["schemaVersion"], 1)
        self.assertEqual(document["target"], {"name": "target", "prerelease": None})
        self.assertEqual({check["state"] for check in document["checks"].values()}, {"ran"})

    def test_stdout_holds_the_document_alone_even_when_something_else_prints(self):
        def stray(*args):
            print("stray")
            return []

        with mock.patch.object(impact, "compare_commands", side_effect=stray):
            code, out, err = self.check("--json")
        self.assertEqual(json.loads(out)["result"], "clear")
        self.assertEqual((code, err), (0, "stray\n"))

    def test_a_count_that_wasnt_looked_at_is_null_and_its_check_didnt_run(self):
        (self.home / ".config/hypr").mkdir(parents=True)
        (self.home / ".config/hypr/bindings.lua").symlink_to(self.base / "missing.lua")
        code, document, _ = self.document(packages=None)
        self.assertEqual((code, document["result"]), (3, "incomplete"))
        self.assertEqual(document["checks"]["bindings"], {"state": "didNotRun", "checked": {"defaults": 1, "yours": None}})
        self.assertEqual(document["checks"]["packages"], {"state": "didNotRun", "checked": {"pendingMigrations": None}})

    def test_no_deleted_commands_and_no_plugins_are_counted_as_zero(self):
        checks = self.document()[1]["checks"]
        self.assertEqual(checks["commands"]["checked"], {"deletedCommands": 0, "yourFiles": 0})
        self.assertEqual(checks["plugins"]["checked"], {"linted": 0})

    def test_a_check_that_ran_in_part_says_so(self):
        (self.base / "target/default/hypr/helpers.lua").write_text("function o.bind_foo(keys) end")
        code, document, _ = self.document()
        self.assertEqual((code, document["checks"]["bindings"]["state"]), (3, "ranInPart"))

    def test_a_finding_has_every_field(self):
        (self.base / "target/migrations/1.sh").write_text("omarchy-pkg-drop a\n")
        code, document, _ = self.document(packages={"a"})
        self.assertEqual((code, document["result"]), (1, "attention"))
        self.assertEqual(document["findings"], [{
            "id": impact.Finding("packages", "attention", "The update will remove a, which is installed here.", []).id,
            "check": "packages",
            "level": "attention",
            "title": "The update will remove a, which is installed here.",
            "evidence": ["migrations/1.sh"],
            "detail": "",
            "fix": "After the update, run omarchy pkg add a (aur-add for an AUR package).",
            "partial": False,
            "reason": None,
            "reviewed": False,
        }])

    def test_a_package_named_as_the_migration_spells_it_still_prints(self):
        # With more installed than removed, the name is the one read from the migration.
        (self.base / "target/migrations/1.sh").write_text("omarchy-pkg-drop a\n")
        code, document, _ = self.document(packages={"a", "b", "c"})
        self.assertEqual((code, [finding["title"] for finding in document["findings"]]), (
            1, ["The update will remove a, which is installed here."],
        ))

    def test_all_changes_nothing(self):
        for tree in ("current", "target"):
            (self.base / tree / "default/hypr/keys.lua").write_text('o.bind("SUPER + " .. key, "x", "y")')
        self.assertEqual(self.check("--json", "--all")[1], self.check("--json")[1])
        self.assertEqual(len(self.document()[1]["findings"]), 1)

    def test_a_crash_is_a_document_with_the_line_from_stderr(self):
        with mock.patch.object(impact, "compare_commands", side_effect=RuntimeError("broke\nbadly")):
            code, document, err = self.document()
        self.assertEqual(code, 2)
        self.assertEqual(document, {"schemaVersion": 1, "result": "failed", "reason": "Unexpected RuntimeError: broke badly"})
        self.assertEqual(err, "Unexpected RuntimeError: broke badly\n")

    def test_an_unusable_tree_is_a_document(self):
        shutil.rmtree(self.base / "target/shell")
        code, document, err = self.document()
        self.assertEqual((code, document["result"]), (2, "failed"))
        self.assertEqual(document["reason"] + "\n", err)

    def test_a_failed_download_is_a_document(self):
        with mock.patch.object(impact.urllib.request, "urlopen", side_effect=OSError("no network")):
            code, out, err = self.run_main("v1.2.3", "--json")
        self.assertEqual((code, json.loads(out)["reason"]), (2, "Couldn't download the release: no network"))
        self.assertEqual(err, "Couldn't download the release: no network\n")

    def test_progress_on_a_terminal_stays_on_stderr(self):
        self.terminal = True
        code, out, err = self.download(io.BytesIO(self.archive()), args=("v1.2.3", "--json"))
        self.assertEqual((code, json.loads(out)["target"]["name"]), (0, "v1.2.3"))
        self.assertIn("Downloading v1.2.3", err)

    def bad_usage(self, *args):
        """What argparse exits with, and prints, for bad usage."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.argv", ["omaupdateimpact", *args]), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as exit:
            impact.main()
        return exit.exception.code, out.getvalue(), err.getvalue()

    def test_bad_usage_is_a_document_when_json_was_asked_for(self):
        for flag in ("--json", "--js"):
            with self.subTest(flag=flag):
                code, out, err = self.bad_usage(flag, "--no-such-option")
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(out), {
                    "schemaVersion": 1, "result": "failed", "reason": "Bad usage: unrecognized arguments: --no-such-option",
                })
                self.assertIn("error: unrecognized arguments: --no-such-option", err)

    def test_bad_usage_without_json_is_text_only(self):
        code, out, err = self.bad_usage("--no-such-option")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("usage:", err)

    def test_json_is_asked_for_as_argparse_reads_it(self):
        for argv, wanted in (
            (["--json"], True), (["--j"], True), (["v1.2.3", "--jso"], True),
            ([], False), (["-j"], False), (["--"], False), (["--", "--json"], False), (["--jsonx"], False),
        ):
            with self.subTest(argv=argv):
                self.assertEqual(impact.wants_json(argv), wanted)


def change(text, number):
    """A line of release notes, as GitHub lists a change."""
    return f"- {text} by @fictional-dev in #{number}\r\n"


class Reasons(ProgramCase):
    """Fictional notes. The target drops fictional-editor, and you have it installed."""

    def setUp(self):
        super().setUp()
        self.migration("1.sh", 'echo "Replace Fictional Editor with Quill"\nomarchy-pkg-drop fictional-editor\n')

    def migration(self, name, text):
        (self.base / "target/migrations" / name).write_text(text)

    def notes(self, *lines):
        (self.base / "target" / impact.NOTES).write_text("".join(lines), newline="")

    def findings(self, *args, packages=frozenset({"fictional-editor"})):
        code, out, _ = self.check("--json", *args, packages=packages)
        return code, json.loads(out)["findings"]

    def reasons(self, **kwargs):
        return [finding["reason"] for finding in self.findings(**kwargs)[1]]

    def test_a_removal_takes_the_change_its_migration_describes(self):
        self.notes("## Deprecations\r\n\r\n", change("Replace Fictional Editor with Quill", 101))
        self.assertEqual(self.reasons(), [{
            "text": "Replace Fictional Editor with Quill",
            "reference": "#101",
            "evidence": f"{impact.NOTES}:3",
        }])
        out = " ".join(self.check(packages={"fictional-editor"})[1].split())
        self.assertIn(
            "The update will remove fictional-editor, which is installed here. [1354b03] "
            "Why: Replace Fictional Editor with Quill (#101). Fix: After the update", out
        )

    def test_the_description_matches_whatever_its_case_spacing_and_full_stop(self):
        self.notes(change("replace  fictional editor with quill.", 101))
        self.assertEqual(self.reasons()[0]["reference"], "#101")

    def test_a_change_listed_twice_is_one_change(self):
        line = change("Replace Fictional Editor with Quill", 101)
        self.notes("## Removals\r\n", line, "## Deprecations\r\n", line)
        self.assertEqual(self.reasons()[0]["evidence"], f"{impact.NOTES}:2")

    def test_a_change_that_names_the_package_is_its_reason(self):
        self.migration("1.sh", "omarchy-pkg-drop fictional-editor\n")
        for text in ("Retire fictional-editor", "Remove fictional-editor.", "Replace Fictional-editor with Quill"):
            with self.subTest(text=text):
                self.notes(change(text, 102))
                self.assertEqual(self.reasons()[0]["text"], text)

    def test_a_change_that_fixes_or_adds_the_package_isnt_why_it_goes(self):
        self.migration("1.sh", "omarchy-pkg-drop fictional-editor\n")
        for text in (
            "Fix fictional-editor crashing on start",
            "Add a theme to fictional-editor",
            "Speed up Fictional-editor",
            "Remove the old theme, which broke fictional-editor",
            "Make removing fictional-editor faster",
        ):
            with self.subTest(text=text):
                self.notes(change(text, 102))
                self.assertEqual(self.reasons(), [None])

    def test_a_longer_name_or_another_case_isnt_the_package(self):
        self.migration("1.sh", "omarchy-pkg-drop fictional-editor\n")
        for text in ("Retire fictional-editor-git", "Retire @fictional-editor", "Retire FICTIONAL-EDITOR", "Retire fictional-editor.app"):
            with self.subTest(text=text):
                self.notes(change(text, 102))
                self.assertEqual(self.reasons(), [None])

    def test_two_changes_that_name_it_give_no_reason(self):
        self.notes(change("Replace Fictional Editor with Quill", 101), change("Drop fictional-editor", 102))
        self.assertEqual(self.reasons(), [None])

    def test_a_finding_with_no_clear_match_gives_no_reason(self):
        self.notes(change("Replace Fictional Editor with Quill and Ink", 101), "- Replace Fictional Editor with Quill\r\n")
        self.assertEqual(self.reasons(), [None])
        self.assertNotIn("Why:", self.check(packages={"fictional-editor"})[1])

    def test_a_shortcut_takes_the_one_change_that_names_its_keys(self):
        (self.home / ".config/hypr").mkdir(parents=True)
        (self.home / ".config/hypr/bindings.lua").write_text('o.bind("SUPER + M", "Mail", "mail")')
        (self.base / "target/default/hypr/bindings.lua").write_text(
            'o.bind("SUPER + W", "Close", "close-it")\no.bind("SUPER + M", "Minimize", "min")'
        )
        for text, wanted in (
            ("Add `Super + M` to minimize a window", True),
            ("Add Win + m to minimize a window", True),
            ("Add Super + Shift + M to minimize a window", False),
            ("Add Super + MM to minimize a window", False),
        ):
            with self.subTest(text=text):
                self.notes(change(text, 104))
                self.assertEqual(self.reasons(packages=frozenset()), [{
                    "text": text, "reference": "#104", "evidence": f"{impact.NOTES}:1",
                } if wanted else None])

    def test_a_move_takes_the_one_change_that_names_either_key(self):
        (self.base / "current/default/hypr/bindings.lua").write_text('o.bind("SUPER + C", "Calc", "calc")')
        (self.base / "target/default/hypr/bindings.lua").write_text('o.bind("SUPER + SHIFT + C", "Calc", "calc")')
        self.notes(change("Move Calculator to Super + Shift + C", 105))
        _, findings = self.findings("--all", packages=frozenset())
        self.assertEqual(findings[0]["title"], 'Moved: "Calc" from SUPER + C to SUPER + SHIFT + C.')
        self.assertEqual(findings[0]["reason"]["reference"], "#105")

    def test_a_list_of_new_shortcuts_takes_no_reason(self):
        (self.base / "target/default/hypr/bindings.lua").write_text(
            'o.bind("SUPER + W", "Close", "close-it")\no.bind("SUPER + N", "Notes", "notes")'
        )
        self.notes(change("Add Super + N for notes", 106))
        self.assertEqual(self.reasons(packages=frozenset()), [None])

    def test_a_deleted_command_takes_the_one_change_that_names_it(self):
        (self.base / "current/bin/omarchy-sync-notes").write_text("#!/bin/bash\n")
        (self.home / ".local/bin").mkdir(parents=True)
        (self.home / ".local/bin/sync").write_text("#!/bin/sh\nomarchy-sync-notes\n")
        for text, wanted in (("Fold omarchy-sync-notes into omarchy-sync", True), ("Add omarchy-sync-notes-all", False)):
            with self.subTest(text=text):
                self.notes(change(text, 107))
                self.assertEqual(self.reasons(packages=frozenset())[0] is not None, wanted)

    def test_an_edit_takes_the_change_its_migration_describes(self):
        (self.home / ".config/app").mkdir(parents=True)
        (self.home / ".config/app/app.conf").write_text("mine\n")
        self.migration("1.sh", 'echo "Brighten the app theme"\nsed -i s/a/b/ ~/.config/app/app.conf\n')
        self.notes(change("Brighten the app theme", 108))
        self.assertEqual(self.reasons(packages=frozenset())[0]["reference"], "#108")

    def test_a_migration_that_doesnt_echo_first_says_nothing(self):
        for text in (
            '# Replace Fictional Editor with Quill\nomarchy-pkg-drop fictional-editor\n',
            'true\necho "Replace Fictional Editor with Quill"\nomarchy-pkg-drop fictional-editor\n',
            'echo "Replace Fictional Editor with $NAME"\nomarchy-pkg-drop fictional-editor\n',
            'echo "Replace Fictional Editor" "with Quill"\nomarchy-pkg-drop fictional-editor\n',
        ):
            with self.subTest(text=text):
                self.migration("1.sh", text)
                self.notes(change("Replace Fictional Editor with Quill", 101), change("Replace Fictional Editor with $NAME", 102))
                self.assertEqual(self.reasons(), [None])

    def test_a_line_that_isnt_a_listed_change_is_no_reason(self):
        self.notes(
            "Replace Fictional Editor with Quill by @fictional-dev in #101\r\n",
            "- Replace Fictional Editor with Quill (#101)\r\n",
            "- Replace Fictional Editor with Quill by fictional-dev in #101\r\n",
        )
        self.assertEqual(self.reasons(), [None])

    def test_an_unknown_takes_no_reason(self):
        self.migration("1.sh", 'echo "Replace Fictional Editor with Quill"\nomarchy-pkg-drop "${editors[@]}"\n')
        self.notes(change("Replace Fictional Editor with Quill", 101))
        self.assertEqual(self.reasons(), [None])

    def test_missing_notes_change_nothing_but_the_reasons(self):
        self.notes(change("Replace Fictional Editor with Quill", 101))
        with_notes = self.check("--json", packages={"fictional-editor"})
        (self.base / "target" / impact.NOTES).unlink()
        without = self.check("--json", packages={"fictional-editor"})
        self.assertEqual(with_notes[0], without[0])
        self.assertEqual(json.loads(without[1])["findings"][0]["reason"], None)
        self.assertEqual(
            json.loads(with_notes[1]) | {"findings": None}, json.loads(without[1]) | {"findings": None}
        )


class ReasonsFromRealNotes(unittest.TestCase):
    """v4.5.0-rc2's own notes, for packages a migration could remove."""

    def reason(self, package):
        finding = impact.Finding("packages", impact.ATTENTION, "", [], about=(("package", package),))
        impact.give_reasons([finding], FIXTURES / "releases/v4.5.0-rc2")
        return finding.reason and finding.reason.reference

    def test_a_package_a_change_only_mentions_takes_no_reason(self):
        for package in ("mpv", "docker", "file", "which", "neovim", "lua", "polkit", "tailscale", "clang", "gum"):
            with self.subTest(package=package):
                self.assertIsNone(self.reason(package))

    def test_a_package_a_change_removes_or_replaces_takes_it(self):
        self.assertEqual(self.reason("tensaku"), "#9446")
        self.assertEqual(self.reason("lazydocker"), "#14230")

    def test_dua_cli_still_takes_its_reason_through_its_migration(self):
        finding = impact.Finding(
            "packages", impact.ATTENTION, "", [],
            about=(("migration", "migrations/1791345484.sh"), ("package", "dua-cli")),
        )
        impact.give_reasons([finding], FIXTURES / "releases/v4.5.0-rc2")
        self.assertEqual(finding.reason.reference, "#14426")


class Notes(ProgramCase):
    """Fetching the notes along with a release, and keeping them in its folder."""

    INSTALLED = frozenset({"fictional-editor"})

    def setUp(self):
        super().setUp()
        (self.base / "target/migrations/1.sh").write_text('echo "Retire Fictional Editor"\nomarchy-pkg-drop fictional-editor\n')
        self.kept = self.cache / "omaupdateimpact/v1.2.3" / impact.NOTES

    def download(self, *args, notes=None):
        return super().download(io.BytesIO(self.archive()), args=("v1.2.3", *args), notes=notes, packages=self.INSTALLED)

    def answered(self, notes, *args):
        """Run with the archive, and the notes request answered by notes."""
        with mock.patch.object(impact.urllib.request, "urlopen", side_effect=[io.BytesIO(self.archive()), notes]), \
                mock.patch.object(impact, "installed_packages", return_value=self.INSTALLED):
            return self.run_main("v1.2.3", *args)

    def test_notes_are_kept_with_the_release_and_give_reasons(self):
        notes = "## Deprecations\r\n\r\n" + change("Retire Fictional Editor", 109)
        code, out, err = self.download(notes=notes)
        self.assertEqual((code, err), (1, ""))
        self.assertIn("Why: Retire Fictional Editor (#109).", out)
        self.assertEqual(self.kept.read_bytes(), notes.encode())

    def test_kept_notes_arent_fetched_again(self):
        self.download(notes=change("Retire Fictional Editor", 109))
        with mock.patch.object(impact.urllib.request, "urlopen") as urlopen, \
                mock.patch.object(impact, "installed_packages", return_value=self.INSTALLED):
            code, out, _ = self.run_main("v1.2.3")
        urlopen.assert_not_called()
        self.assertEqual(code, 1)
        self.assertIn("Why: Retire Fictional Editor (#109).", out)

    def test_a_cached_release_without_notes_fetches_only_the_notes(self):
        shutil.copytree(self.base / "target", self.cache / "omaupdateimpact/v1.2.3")
        with mock.patch.object(impact.urllib.request, "urlopen", return_value=io.BytesIO(b'{"body": "notes"}')) as urlopen, \
                mock.patch.object(impact, "installed_packages", return_value=self.INSTALLED):
            self.assertEqual(self.run_main("v1.2.3")[0], 1)
        self.assertEqual([call.args[0].full_url for call in urlopen.call_args_list], [
            "https://api.github.com/repos/omacom/omarchy/releases/tags/v1.2.3",
        ])
        self.assertEqual(self.kept.read_text(), "notes")

    def test_a_tag_with_no_release_or_no_notes_keeps_empty_notes(self):
        for notes in (lambda: refused(404), lambda: io.BytesIO(b'{"body": null}'), lambda: io.BytesIO(b"{}")):
            with self.subTest(notes=notes):
                shutil.rmtree(self.cache, ignore_errors=True)
                code, _, err = self.answered(notes())
                self.assertEqual((code, err), (1, ""))
                self.assertEqual(self.kept.read_text(), "")

    def test_notes_that_cant_be_fetched_change_nothing_but_the_reasons(self):
        document = json.loads(self.download("--json", notes=change("Retire Fictional Editor", 109))[1])
        self.assertEqual(document["findings"][0]["reason"]["reference"], "#109")
        document["findings"][0]["reason"] = None
        failures = (
            lambda: OSError("no network"), lambda: refused(500), lambda: refused(403, x_ratelimit_remaining="0"),
            lambda: io.BytesIO(b"not json"), lambda: io.BytesIO(b"[]"), lambda: io.BytesIO(b'{"body": 1}'),
        )
        for failure in failures:
            with self.subTest(failure=failure):
                shutil.rmtree(self.cache)
                code, out, err = self.answered(failure(), "--json")
                self.assertEqual((code, json.loads(out)), (1, document))
                self.assertTrue(err.startswith("Couldn't fetch the release notes, so no finding says why: "), err)
                self.assertEqual(len(err.splitlines()), 1)
                # Nothing is kept, not even part of the notes, so the next run asks again.
                self.assertEqual({path.name for path in self.kept.parent.iterdir()}, {"bin", "default", "migrations", "shell"})

    def test_a_target_folder_is_never_fetched_for(self):
        with mock.patch.object(impact.urllib.request, "urlopen") as urlopen:
            self.assertEqual(self.check("v1.2.3")[0], 0)
        urlopen.assert_not_called()


class Bindings(ProgramCase):
    def setUp(self):
        super().setUp()
        (self.home / ".config/hypr").mkdir(parents=True)
        self.bindings = self.home / ".config/hypr/bindings.lua"

    def assert_unreadable(self, checks="bindings"):
        code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertIn("bindings.lua couldn't be read", " ".join(out.split()))
        self.assertIn(f"These checks didn't run: {checks}.", out)

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
        self.assert_unreadable("bindings, plugins")

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
        self.assertIn("1 key bindings use computed keys", self.check("--all")[1])
        self.assertIn("Nothing found", out)

    def test_a_computed_key_of_the_users_exits_3(self):
        self.bindings.write_text('o.bind("SUPER + " .. key, "x", "y")')
        self.assertEqual(self.check()[0], 3)

    def test_a_computed_key_that_changed_ran_in_part(self):
        (self.base / "target/default/hypr/keys.lua").write_text('o.bind("SUPER + " .. key, "x", "y")')
        code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertEqual(out.splitlines()[-1], "These checks ran in part: bindings.")
        self.assertNotIn("Nothing found", out)

    def test_your_own_computed_key_ran_in_part(self):
        self.bindings.write_text('o.bind("SUPER + " .. key, "x", "y")')
        self.assertEqual(self.check()[1].splitlines()[-1], "These checks ran in part: bindings.")

    def test_an_unreadable_bindings_file_outranks_a_computed_key(self):
        self.bindings.symlink_to(self.base / "missing.lua")
        (self.base / "target/default/hypr/keys.lua").write_text('o.bind("SUPER + " .. key, "x", "y")')
        out = self.check()[1]
        self.assertEqual(out.splitlines()[-1], "These checks didn't run: bindings.")
        self.assertNotIn("of yours", out.splitlines()[1])

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


class UnreadableFiles(ProgramCase):
    def setUp(self):
        super().setUp()
        (self.base / "current/bin/omarchy-gone").touch()
        self.hooks = self.home / ".config/omarchy/hooks"
        self.hooks.mkdir(parents=True)

    def assert_unknown(self, shown, reason):
        code, out, _ = self.check()
        self.assertEqual(code, 3)
        self.assertIn(f"{shown} couldn't be read", " ".join(out.split()))
        self.assertIn(reason, " ".join(out.split()))
        self.assertIn("These checks didn't run: commands.", out)

    def test_a_broken_link_in_a_folder_is_unknown(self):
        (self.hooks / "tool.hook").symlink_to(self.base / "missing")
        self.assert_unknown("~/.config/omarchy/hooks/tool.hook", "It's a broken link")

    def test_a_broken_bashrc_is_unknown(self):
        (self.home / ".bashrc").symlink_to(self.base / "unmounted/.bashrc")
        self.assert_unknown("~/.bashrc", "It's a broken link")

    def test_a_broken_scanned_folder_is_unknown(self):
        self.hooks.rmdir()
        self.hooks.symlink_to(self.base / "unmounted")
        self.assert_unknown("~/.config/omarchy/hooks", "It's a broken link")

    def test_a_broken_new_folder_is_unknown(self):
        (self.home / ".local").mkdir()
        (self.home / ".local/bin").symlink_to(self.base / "unmounted")
        self.assert_unknown("~/.local/bin", "It's a broken link")

    def test_a_broken_link_above_a_single_file_is_unknown(self):
        (self.home / ".config/fish").symlink_to(self.base / "unmounted")
        self.assert_unknown("~/.config/fish/config.fish", "It's a broken link")

    def test_a_file_in_place_of_a_folder_is_unknown(self):
        self.hooks.rmdir()
        self.hooks.write_text("omarchy-gone\n")
        self.assert_unknown("~/.config/omarchy/hooks", "It isn't a folder")

    def test_a_folder_in_place_of_a_file_is_unknown(self):
        (self.home / ".bashrc").mkdir()
        self.assert_unknown("~/.bashrc", "It isn't a file")

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_a_denied_file_is_unknown(self):
        (self.hooks / "tool.hook").touch(mode=0)
        self.assert_unknown("~/.config/omarchy/hooks/tool.hook", "Permission denied")

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_a_denied_single_file_is_unknown(self):
        (self.home / ".zshrc").touch(mode=0)
        self.assert_unknown("~/.zshrc", "Permission denied")

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_a_denied_folder_inside_a_scanned_one_is_unknown(self):
        (self.hooks / "private").mkdir()
        (self.hooks / "private").chmod(0)
        self.addCleanup((self.hooks / "private").chmod, 0o755)
        self.assert_unknown("~/.config/omarchy/hooks/private", "Permission denied")

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_a_denied_scanned_folder_is_unknown(self):
        self.hooks.chmod(0)
        self.addCleanup(self.hooks.chmod, 0o755)
        self.assert_unknown("~/.config/omarchy/hooks", "Permission denied")

    def test_a_missing_file_or_folder_is_fine(self):
        self.hooks.rmdir()
        self.assertEqual(self.check()[0], 0)

    def test_a_call_outranks_an_unreadable_file(self):
        (self.hooks / "tool.hook").symlink_to(self.base / "missing")
        (self.hooks / "my.hook").write_text("omarchy-gone\n")
        code, out, _ = self.check()
        self.assertEqual(code, 1)
        self.assertIn("These checks ran in part: commands.", out)
        self.assertIn("1 of your files for 1 deleted command", " ".join(out.split()))

    def test_a_call_names_every_line_to_change(self):
        (self.hooks / "my.hook").write_text("omarchy-gone\n# omarchy-gone\nomarchy-gone again\n")
        self.assertIn("Fix: Change or remove lines 1, 3.", self.check()[1])

    def test_an_unchanged_shipped_file_exits_0(self):
        (self.base / "current/install").mkdir()
        (self.base / "current/install/tool.hook").write_text("omarchy-gone\n")
        (self.hooks / "tool.hook").write_text("omarchy-gone\n")
        code, out, _ = self.check("--all")
        self.assertEqual(code, 0)
        self.assertIn("Omarchy's own", " ".join(out.split()))
        self.assertIn("Nothing found", out)

    def test_an_edited_shipped_file_exits_1(self):
        (self.base / "current/install").mkdir()
        (self.base / "current/install/tool.hook").write_text("omarchy-gone\n")
        (self.hooks / "tool.hook").write_text("omarchy-gone --mine\n")
        self.assertEqual(self.check()[0], 1)


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

    def attention(self):
        (self.home / ".config/hypr").mkdir(parents=True)
        (self.home / ".config/hypr/bindings.lua").write_text('o.bind("SUPER + M", "Mail", "mail")')
        (self.base / "target/default/hypr/bindings.lua").write_text('o.bind("SUPER + M", "Minimize", "min")')
        return self.check()

    def test_a_terminal_gets_colour(self):
        out = self.attention()[1]
        self.assertIn("\033[1;31mNeeds attention\033[0m", out)
        self.assertIn("\033[1;32mFix:\033[0m", out)

    def test_colour_doesnt_change_where_lines_break(self):
        colour = self.attention()[1]
        self.terminal = False
        self.assertEqual(re.sub(r"\033\[[\d;]*m", "", colour), self.check()[1])

    def test_no_color_turns_it_off(self):
        with mock.patch.dict(os.environ, NO_COLOR="1"):
            self.assertNotIn("\033", self.attention()[1])

    def test_an_empty_no_color_changes_nothing(self):
        with mock.patch.dict(os.environ, NO_COLOR=""):
            self.assertIn("\033", self.attention()[1])

    def test_a_clean_result_is_coloured_too(self):
        self.assertIn("\033[1;32mNothing found that needs attention.\033[0m", self.check()[1])

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
        (self.cache / "omaupdateimpact/v1.2.0" / impact.NOTES).touch()
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



class Noticed(io.StringIO):
    """stderr that sets an event when a run says it is waiting."""

    def __init__(self, event):
        super().__init__()
        self.event = event

    def write(self, text):
        if "Waiting" in text:
            self.event.set()
        return super().write(text)


class Held(io.BytesIO):
    """An archive whose download doesn't start until the event is set."""

    def __init__(self, data, event):
        super().__init__(data)
        self.event = event

    def read(self, *args):
        self.event.wait(10)
        return super().read(*args)


class SharedCache(ProgramCase):
    """Two runs at once, as threads. A lock on a folder holds against another thread as against another process."""

    def setUp(self):
        super().setUp()
        (self.base / "target/migrations/1.sh").write_text("omarchy-pkg-drop a\n")
        self.data = self.archive()
        self.archives = []
        self.downloading, self.second, self.go = threading.Event(), threading.Event(), threading.Event()
        # With hold set, the first run to ask for the packages stops there until reading is done.
        self.hold, self.reading, self.done_reading = False, threading.Event(), threading.Event()
        self.stderr = Noticed(self.second)
        self.enterContext(mock.patch.object(impact.urllib.request, "urlopen", self.answer))
        self.enterContext(mock.patch.object(impact, "installed_packages", self.packages))
        self.enterContext(contextlib.redirect_stderr(self.stderr))
        self.pool = self.enterContext(ThreadPoolExecutor(2))
        # Before the pool shuts down, so a failed test doesn't leave a run waiting.
        self.addCleanup(self.go.set)
        self.addCleanup(self.done_reading.set)

    def answer(self, request, timeout):
        if "/releases/tags/" in request.full_url:
            raise refused(404)
        self.archives.append(request.full_url)
        if len(self.archives) > 1:
            self.second.set()
        self.downloading.set()
        return Held(self.data, self.go)

    def packages(self):
        if self.hold and not self.reading.is_set():
            self.reading.set()
            self.assertTrue(self.done_reading.wait(10))
        return {"a"}

    def start(self, tag):
        options = argparse.Namespace(
            tag=tag, channel=None, target=None, root=self.base / "current", home=self.home,
            ack=None, debug=False, all=False, json=False,
        )
        return self.pool.submit(impact.run, options)

    def cache_release(self, tag):
        shutil.copytree(self.base / "target", self.cache / "omaupdateimpact" / tag)
        (self.cache / "omaupdateimpact" / tag / impact.NOTES).touch()

    def cached(self):
        return sorted(path.name for path in (self.cache / "omaupdateimpact").iterdir())

    def test_two_runs_at_once_download_once_and_agree(self):
        first = self.start("v1.2.3")
        self.assertTrue(self.downloading.wait(10))
        second = self.start("v1.2.3")
        # The second run either waits for the cache or, without the lock, downloads too.
        self.assertTrue(self.second.wait(10))
        self.go.set()
        first, second = first.result(10), second.result(10)
        self.assertEqual(first["result"], "attention")
        self.assertEqual(second, first)
        self.assertEqual(len(self.archives), 1)
        self.assertEqual(self.stderr.getvalue(), "Another omaupdateimpact run is using the cache. Waiting for it to finish.\n")
        self.assertEqual(self.cached(), ["v1.2.3"])

    def test_a_release_being_read_isnt_pruned_under_it(self):
        self.go.set()
        self.cache_release("v1.0.0")
        self.cache_release("v1.1.0")
        self.hold = True
        # The packages are asked for after the bindings are read and before the migrations are.
        older = self.start("v1.0.0")
        self.assertTrue(self.reading.wait(10))
        self.assertEqual(self.start("v1.2.0").result(10)["result"], "attention")
        self.assertEqual(self.cached(), ["v1.0.0", "v1.1.0", "v1.2.0"])
        self.done_reading.set()
        self.assertEqual(older.result(10)["result"], "attention")
        # Once no run reads it, the next download prunes it.
        self.assertEqual(self.start("v1.3.0").result(10)["result"], "attention")
        self.assertEqual(self.cached(), ["v1.2.0", "v1.3.0"])

    def test_a_run_gives_up_on_a_cache_held_too_long(self):
        cache = self.cache / "omaupdateimpact"
        cache.mkdir(parents=True)
        with mock.patch.object(impact, "CACHE_WAIT", 0.3), impact.locked(cache, impact.fcntl.LOCK_EX):
            document = self.start("v1.2.3").result(10)
        self.assertEqual(document["result"], "failed")
        self.assertIn("another omaupdateimpact run held the cache", document["reason"])
        self.assertEqual(self.archives, [])

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
        for error in (refused(401), refused(403), refused(403, x_ratelimit_remaining="12"), refused(404), refused(500, retry_after="60")):
            with self.subTest(code=error.code):
                code, _, err = self.api_failure(error)
                self.assertEqual(code, 2)
                self.assertNotIn("rate limit", err)
                self.assertIn("Couldn't download the release: HTTP Error", err)


class Tokens(ProgramCase):
    def requests(self, *args):
        """What was sent for a stable run: the API request, the archive request, then the notes request."""
        answers = [io.BytesIO(b'{"tag_name": "v1.2.3"}'), io.BytesIO(self.archive()), io.BytesIO(b'{"body": ""}')]
        with mock.patch.object(impact.urllib.request, "urlopen", side_effect=answers) as urlopen, \
                mock.patch.object(impact, "installed_packages", return_value=set()):
            self.assertEqual(self.run_main("--channel", "stable")[0], 0)
        return [call.args[0] for call in urlopen.call_args_list]

    def test_github_token_goes_to_the_api_and_no_further(self):
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional"):
            listing, archive, notes = self.requests()
        self.assertEqual(listing.get_header("Authorization"), "Bearer fictional")
        self.assertEqual(listing.headers, {})
        self.assertFalse(archive.has_header("Authorization"))
        self.assertEqual(notes.get_header("Authorization"), "Bearer fictional")
        self.assertTrue(notes.full_url.startswith("https://api.github.com/"))

    def test_no_token_sends_no_header(self):
        for environment in ({}, {"GITHUB_TOKEN": ""}):
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment):
                listing, *_ = self.requests()
                self.assertFalse(listing.has_header("Authorization"))
                shutil.rmtree(self.cache)

    def test_a_token_with_a_trailing_newline_still_works(self):
        for token in ("fictional\n", "fictional\r\n", "  fictional "):
            with self.subTest(token=token), mock.patch.dict(os.environ, GITHUB_TOKEN=token):
                listing, *_ = self.requests()
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

    def test_a_rejected_token_is_named_and_never_printed(self):
        for flags in ((), ("--debug",)):
            with self.subTest(flags=flags), mock.patch.dict(os.environ, GITHUB_TOKEN="fictional"), \
                    mock.patch.object(impact.urllib.request, "urlopen", side_effect=refused(401)):
                code, out, err = self.run_main("--channel", "stable", *flags)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.endswith("Couldn't download the release: GitHub rejected GITHUB_TOKEN. Fix it or unset it.\n"))
                self.assertNotIn("fictional", err)

    def test_a_redirect_drops_the_token(self):
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional"):
            listing, *_ = self.requests()
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
        if "/releases/tags/" in url:
            raise refused(404)
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
        archives = [url for url in self.urls if "/archive/" in url]
        self.assertTrue(archives[-1].endswith(f"/archive/refs/tags/{tag}.tar.gz"), self.urls)

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
        for channel in ("edge", "dev", "unknown"):
            with self.subTest(channel=channel):
                self.on_channel(channel)
                code, out, err = self.fetch()
                self.assertEqual((code, out, self.urls), (2, "", []))
                self.assertEqual(len(err.splitlines()), 1)
                self.assertTrue(err.startswith("Can't pick a release: "), err)
                self.assertIn(f"the channel is {channel},", err)
                self.assertIn("Pass a tag", err)

    def test_a_mirror_and_packages_that_disagree_are_each_named(self):
        for channel, mirror, packages in (("stable / rc", "stable", "rc"), ("edge / unknown", "edge", "unknown")):
            with self.subTest(channel=channel):
                self.on_channel(channel)
                code, out, err = self.fetch()
                self.assertEqual((code, out, self.urls), (2, "", []))
                self.assertEqual(
                    err,
                    f"Can't pick a release: the mirror says {mirror} and the packages say {packages}, "
                    "so no one channel applies. Pass a tag, such as omaupdateimpact v4.5.0.\n",
                )

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
        self.assertEqual((code, [url.rsplit("/", 1)[-1] for url in self.urls]), (0, ["v2.0.0-rc1.tar.gz", "v2.0.0-rc1"]))
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

    def test_up_to_date_names_a_rejected_token_when_that_stopped_the_listing(self):
        self.on_channel("stable", version="1.2.3-1")
        self.listing_error = refused(401)
        with mock.patch.dict(os.environ, GITHUB_TOKEN="fictional"):
            code, out, _ = self.fetch(own_tree=True)
        self.assertEqual(code, 0)
        self.assertIn("Couldn't check for newer releases on other channels. GitHub rejected GITHUB_TOKEN.", out)
        self.assertNotIn("fictional", out)

    def test_up_to_date_is_a_document_with_the_newer_releases(self):
        self.on_channel("stable", version="1.2.2-1")
        code, out, err = self.fetch("v1.2.2", "--json", own_tree=True)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), {
            "schemaVersion": 1,
            "result": "noUpdate",
            "installed": "1.2.2-1",
            "channel": "stable",
            "target": {"name": "v1.2.2", "prerelease": False},
            "newer": [
                {"tag": "v2.0.0-rc2", "channel": "rc", "cached": False},
                {"tag": "v1.2.3", "channel": "stable", "cached": False},
            ],
            "newerProblem": None,
        })

    def test_up_to_date_says_which_newer_release_is_in_the_cache(self):
        # The plugin's Check button says a release downloads first, unless it is here.
        self.on_channel("stable", version="1.2.2-1")
        (self.cache / "omaupdateimpact/v1.2.3").mkdir(parents=True)
        document = json.loads(self.fetch("v1.2.2", "--json", own_tree=True)[1])
        self.assertEqual([(n["tag"], n["cached"]) for n in document["newer"]], [("v2.0.0-rc2", False), ("v1.2.3", True)])
        self.assertFalse(any("/archive/" in url for url in self.urls))

    @unittest.skipIf(os.geteuid() == 0, "root reads any folder")
    def test_a_cache_it_cant_look_in_counts_as_not_there(self):
        self.on_channel("stable", version="1.2.2-1")
        (self.cache / "omaupdateimpact/v1.2.3").mkdir(parents=True)
        self.cache.chmod(0)
        self.addCleanup(self.cache.chmod, 0o755)
        code, out, _ = self.fetch("v1.2.2", "--json", own_tree=True)
        self.assertEqual(code, 0)
        self.assertEqual([n["cached"] for n in json.loads(out)["newer"]], [False, False])

    def test_up_to_date_on_the_newest_release_names_no_newer_one(self):
        self.on_channel("rc", version="2.0.0rc2-1")
        document = json.loads(self.fetch("--json", own_tree=True)[1])
        self.assertEqual((document["newer"], document["newerProblem"]), ([], None))

    def test_up_to_date_with_no_listing_says_newer_is_unknown_and_why(self):
        self.on_channel("stable", version="1.2.3-1")
        self.listing_error = refused(403, x_ratelimit_remaining="0")
        code, out, _ = self.fetch("--json", own_tree=True)
        document = json.loads(out)
        self.assertEqual((code, document["result"], document["newer"]), (0, "noUpdate", None))
        self.assertTrue(document["newerProblem"].startswith(
            "Couldn't check for newer releases on other channels. GitHub's rate limit"
        ))

    def test_a_channel_without_tags_is_a_document(self):
        self.on_channel("edge")
        code, out, err = self.fetch("--json")
        self.assertEqual((code, json.loads(out)["reason"] + "\n"), (2, err))

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
