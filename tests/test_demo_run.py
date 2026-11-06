"""demo/run's own logic, without a shell, Hyprland or grim."""

import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
loader = importlib.machinery.SourceFileLoader("demo_run", str(ROOT / "demo/run"))
spec = importlib.util.spec_from_loader("demo_run", loader)
run = importlib.util.module_from_spec(spec)
loader.exec_module(run)

MONITOR = {"name": "DP-9", "x": 0, "y": 0, "width": 2560, "height": 1600, "scale": 2}
PID = 4242


def hyprland(layer_height, reserved_top):
    """hyprctl's answers with your bar 26 high and the demo bar's layer below it."""
    def answer(what):
        if what == "layers":
            return {"DP-9": {"levels": {"2": [
                {"namespace": "omarchy-bar", "pid": 1, "x": 0, "y": 0, "w": 1280, "h": layer_height},
                {"namespace": "omarchy-bar", "pid": PID, "x": 0, "y": 26, "w": 1280, "h": layer_height},
            ]}}}
        return [dict(MONITOR, reserved=[0, reserved_top, 0, 0])]
    return answer


class DemoBar(unittest.TestCase):
    def test_a_bar_whose_layer_reaches_the_bottom_is_as_high_as_it_reserves(self):
        # Omarchy 4.5.0: the layer is the whole screen, and reserves only the bar.
        with mock.patch.object(run, "hypr", hyprland(800, 52)):
            self.assertEqual(run.demo_bar(PID, MONITOR), (26, 26))

    def test_a_bar_whose_layer_is_the_bar_is_as_high_as_its_layer(self):
        with mock.patch.object(run, "hypr", hyprland(26, 52)):
            self.assertEqual(run.demo_bar(PID, MONITOR), (26, 26))


class OpenFirst(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        (self.base / "omarchy/shell/plugins").mkdir(parents=True)
        self.document = json.loads((run.GOLDEN / "report.json").read_text())
        self.original = (ROOT / "plugin/Widget.qml").read_text()

    def widget(self, **options):
        home = self.base / "home"
        with mock.patch.object(run, "neighbours", return_value=[]):
            run.fictional_home(home, self.base / "omarchy", self.document, **options)
        return (home / ".config/omarchy/plugins" / run.manifest()["id"] / "plugin/Widget.qml").read_text()

    def test_the_copy_opens_the_first_finding_when_the_panel_opens(self):
        copy = self.widget(open_first=True)
        self.assertIn(run.OPEN_FIRST, copy)
        self.assertEqual(copy.replace(run.OPEN_FIRST, run.OPENED), self.original)

    def test_without_it_the_copy_is_the_plugin(self):
        self.assertEqual(self.widget(), self.original)

    def test_the_plugin_itself_is_unchanged(self):
        self.widget(open_first=True)
        self.assertEqual((ROOT / "plugin/Widget.qml").read_text(), self.original)
        self.assertEqual(self.original.count(run.OPENED), 1)


if __name__ == "__main__":
    unittest.main()
