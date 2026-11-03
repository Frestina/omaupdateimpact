"""The plugin: its manifest, and what plugin/State.js makes of every document.

The plugin holds no rules. State.js only reads the command's --json and exit code,
so these tests run it under node on the command's own golden documents. They skip
when node isn't installed. CI lints the QML itself, with tests/lint-plugin.
"""

import copy
import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.golden import GOLDEN
from tests.test_omaupdateimpact import impact

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / "plugin"
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
NODE = shutil.which("node")
VALIDATE = shutil.which("omarchy-plugin-validate") or (
    "/usr/share/omarchy/bin/omarchy-plugin-validate"
    if Path("/usr/share/omarchy/bin/omarchy-plugin-validate").exists() else None
)


def golden(name):
    """A golden document as the command prints it, and the exit code that goes with it."""
    text = (GOLDEN / f"{name}.json").read_text()
    return text, impact.RESULTS[json.loads(text)["result"]]


def run(stdout, exit_code, stderr="", started=True):
    return {"call": "fromRun", "args": [{"started": started, "exitCode": exit_code, "stdout": stdout, "stderr": stderr}]}


def views(*calls):
    """What State.js returns for each call, from node."""
    result = subprocess.run(
        [NODE, str(ROOT / "tests/plugin_state.js")], input=json.dumps(calls),
        capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(result.stdout)


def view(stdout, exit_code, stderr=""):
    return views(run(stdout, exit_code, stderr))[0]


class Manifest(unittest.TestCase):
    def test_the_id_is_the_commands(self):
        self.assertEqual(MANIFEST["id"], impact.PLUGIN_ID)

    def test_every_id_in_the_qml_is_the_commands(self):
        # The widget's module, the service it looks up and the IPC target all use it.
        for path in PLUGIN.glob("*.qml"):
            for found in re.findall(r'"(io\.github\.[^"]+)"', path.read_text()):
                with self.subTest(path.name):
                    self.assertEqual(found, impact.PLUGIN_ID)

    def test_the_version_is_the_commands(self):
        self.assertEqual(MANIFEST["version"], impact.__version__)

    def test_a_service_and_a_bar_widget(self):
        self.assertEqual(MANIFEST["kinds"], ["service", "bar-widget"])
        self.assertEqual(MANIFEST["entryPoints"], {"service": "plugin/Service.qml", "barWidget": "plugin/Widget.qml"})
        for entry in MANIFEST["entryPoints"].values():
            self.assertTrue((ROOT / entry).is_file(), entry)

    def test_the_one_setting(self):
        widget = MANIFEST["barWidget"]
        self.assertEqual(widget["defaults"], {"checkEveryHours": 6})
        [setting] = widget["schema"]
        self.assertEqual((setting["key"], setting["min"], setting["max"], setting["defaultValue"]),
                         ("checkEveryHours", 0, 168, 6))

    def test_the_service_runs_the_bundled_command(self):
        service = (PLUGIN / "Service.qml").read_text()
        self.assertIn('Qt.resolvedUrl("../bin/omaupdateimpact")', service)
        self.assertTrue((PLUGIN / "../bin/omaupdateimpact").resolve() == impact.COMMAND)
        self.assertIn('proc.command = [root.command, "--json"]', service)

    def test_text_is_plain(self):
        # Findings carry paths and lines from your files, never markup.
        for path in PLUGIN.glob("*.qml"):
            text = path.read_text()
            with self.subTest(path.name):
                self.assertEqual(len(re.findall(r"\b(?:Text|TextEdit) \{", text)),
                                 len(re.findall(r"textFormat: Text(?:Edit)?\.PlainText", text)))

    def test_no_links_in_the_repository(self):
        # omarchy plugin validate refuses a plugin with one, outside .git.
        links = []
        for folder, folders, files in os.walk(ROOT):
            folders[:] = [name for name in folders if name != ".git"]
            links += [Path(folder, name) for name in folders + files if Path(folder, name).is_symlink()]
        self.assertEqual(links, [])

    @unittest.skipUnless(VALIDATE, "omarchy plugin validate isn't installed")
    def test_omarchy_plugin_validate(self):
        result = subprocess.run([VALIDATE, str(ROOT)], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(NODE, "node isn't installed")
class States(unittest.TestCase):
    """Every exit code has a state, from the command's own documents."""

    def test_every_golden_document_and_exit_code(self):
        names = sorted(path.stem for path in GOLDEN.glob("*.json"))
        self.assertEqual({golden(name)[1] for name in names}, {0, 1, 2, 3})
        expected = {
            "clear": ("quiet", "", "muted", "v1.3.0: nothing needs attention"),
            "no-update": ("quiet", "", "muted", "Omarchy v1.3.0 is up to date"),
            "report": ("attention", "3", "warning", "v1.3.0: 3 things need attention"),
            "reviewed": ("attention", "2", "warning", "v1.3.0: 2 things need attention"),
            "failed": ("unknown", "?", "text", "Couldn't check\nCan't pick a release: the channel is edge"),
            "incomplete": ("unknown", "?", "text", "Couldn't check v1.3.0\nSome checks didn't run in full: packages."),
        }
        self.assertEqual(sorted(expected), names)
        for name, found in zip(names, views(*(run(*golden(name)) for name in names))):
            with self.subTest(name):
                state, mark, colour, tooltip = expected[name]
                self.assertEqual((found["state"], found["mark"], found["colour"]), (state, mark, colour))
                self.assertTrue(found["tooltip"].startswith(tooltip), found["tooltip"])

    def test_the_panel_of_a_report(self):
        found = view(*golden("report"))
        self.assertEqual((found["installed"], found["release"], found["channel"]), ("1.2.3-1", "v1.3.0", "stable"))
        self.assertEqual([f["id"] for f in found["attention"]], ["9d67629", "1354b03", "b2c1f5a"])
        # Each keeps every field: title, detail, reason, fix, evidence and id.
        self.assertEqual(found["attention"][1]["reason"]["reference"], "#101")
        self.assertTrue(all(f["fix"] for f in found["attention"]))
        self.assertEqual(found["limits"], [{"check": "packages", "words": "ran in part"}])
        self.assertEqual([f["id"] for f in found["unknowns"]], ["e1c345b"])
        self.assertEqual([f["id"] for f in found["notes"]], ["60d484f", "e2e0746"])
        self.assertEqual(found["reviewed"], 0)
        self.assertEqual(found["problem"], "")

    def test_a_reviewed_finding_is_only_counted(self):
        found = view(*golden("reviewed"))
        self.assertEqual([f["id"] for f in found["attention"]], ["1354b03", "b2c1f5a"])
        self.assertEqual(found["reviewed"], 1)

    def test_incomplete_lists_what_didnt_run(self):
        found = view(*golden("incomplete"))
        # Its one pending migration can't be read, so the packages check compared nothing.
        self.assertEqual(found["limits"], [{"check": "packages", "words": "didn't run"}])
        self.assertEqual(len(found["unknowns"]), 1)
        self.assertEqual(found["attention"], [])
        self.assertIn("packages", found["problem"])

    def test_failed_shows_the_reason(self):
        text, code = golden("failed")
        self.assertEqual(view(text, code)["problem"], json.loads(text)["reason"])

    def test_no_update_names_newer_releases(self):
        found = view(*golden("no-update"))
        self.assertEqual(found["newer"], [{"tag": "v1.4.0-rc1", "channel": "rc"}])
        self.assertEqual(found["attention"], [])

    def test_newer_releases_that_couldnt_be_fetched(self):
        doc = json.loads(golden("no-update")[0])
        doc["newer"], doc["newerProblem"] = None, "Couldn't check for newer releases on other channels."
        found = view(json.dumps(doc), 0)
        self.assertEqual(found["newer"], [])
        self.assertEqual(found["newerProblem"], doc["newerProblem"])

    def test_an_exit_code_that_disagrees_is_unknown(self):
        calls, cases = [], []
        for path in sorted(GOLDEN.glob("*.json")):
            text, right = golden(path.stem)
            for code in (0, 1, 2, 3, 4, 127, -1):
                if code != right:
                    calls.append(run(text, code))
                    cases.append((path.stem, code))
        for case, found in zip(cases, views(*calls)):
            with self.subTest(case):
                self.assertEqual((found["state"], found["mark"]), ("unknown", "?"))
                self.assertIn(f"It exited {case[1]}", found["problem"])

    def test_output_that_cant_be_read_is_unknown(self):
        report, _ = golden("report")
        cases = {
            "nothing": ("", 1),
            "not json": ("Checking v1.3.0…", 0),
            "two documents": (report + report, 1),
            "a list": ("[]", 0),
            "schema 2": (report.replace('"schemaVersion": 1', '"schemaVersion": 2'), 1),
            "schema as text": (report.replace('"schemaVersion": 1', '"schemaVersion": "1"'), 1),
            "a result it doesn't know": (report.replace('"result": "attention"', '"result": "fine"'), 1),
        }
        found = views(*(run(text, code, "Traceback\nValueError: fictional") for text, code in cases.values()))
        for name, result in zip(cases, found):
            with self.subTest(name):
                self.assertEqual((result["state"], result["mark"], result["colour"]), ("unknown", "?", "text"))
                self.assertTrue(result["problem"].endswith("It said: ValueError: fictional"), result["problem"])

    def test_a_command_that_didnt_start_is_unknown(self):
        [found] = views(run("", -1, started=False))
        self.assertEqual(found["state"], "unknown")
        self.assertIn("couldn't start", found["problem"])

    def test_a_document_that_doesnt_add_up_is_never_clear(self):
        clear = json.loads(golden("clear")[0])
        report = json.loads(golden("report")[0])
        in_part = copy.deepcopy(clear)
        in_part["checks"]["plugins"]["state"] = "ranInPart"
        with_unknown = copy.deepcopy(clear)
        with_unknown["findings"] = [report["findings"][3]]
        all_reviewed = copy.deepcopy(report)
        for finding in all_reviewed["findings"]:
            finding["reviewed"] = finding["level"] == "attention"
        attention_said_clear = dict(copy.deepcopy(report), result="clear")
        no_checks = copy.deepcopy(clear)
        del no_checks["checks"]["edits"]
        cases = {
            "clear, with a check in part": (in_part, 0),
            "clear, with an unknown": (with_unknown, 0),
            "attention, all reviewed": (all_reviewed, 1),
            "clear, with attention": (attention_said_clear, 0),
            "clear, a check missing": (no_checks, 0),
            "incomplete, every check ran": (dict(copy.deepcopy(clear), result="incomplete"), 3),
        }
        for name, found in zip(cases, views(*(run(json.dumps(doc), code) for doc, code in cases.values()))):
            with self.subTest(name):
                self.assertEqual(found["state"], "unknown")
                self.assertIn("doesn't add up", found["problem"])

    def test_before_the_first_check(self):
        waiting, asked, no_service = views(
            {"call": "notChecked", "args": [False]},
            {"call": "notChecked", "args": [True]},
            {"call": "noService", "args": []},
        )
        self.assertEqual((waiting["state"], waiting["mark"], waiting["tooltip"]), ("notChecked", "…", "Checking…"))
        self.assertEqual(asked["tooltip"], "Not checked yet")
        self.assertEqual((no_service["state"], no_service["mark"]), ("unknown", "?"))
        self.assertIn("no service", no_service["problem"])

    def test_a_long_stderr_line_is_cut(self):
        found = view("", 1, "x" * 5000)
        self.assertLess(len(found["problem"]), 600)


if __name__ == "__main__":
    unittest.main()
