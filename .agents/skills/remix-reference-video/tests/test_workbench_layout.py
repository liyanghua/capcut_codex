from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "src/remix_reference_video/static/review_workbench.css").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "src/remix_reference_video/templates/review_workbench.html").read_text(encoding="utf-8")
TEMPLATE_STYLE = re.search(r"<style>(.*?)</style>", TEMPLATE, flags=re.S).group(1)

_RULE_PATTERN = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _rules(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for selectors, body in _RULE_PATTERN.findall(text):
        result.setdefault(selectors.strip(), body)
    return result


def _declarations(body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in body.split(";"):
        if ":" in part:
            property_name, value = part.split(":", 1)
            result[property_name.strip()] = value.strip()
    return result


def _find_rule(rules: dict[str, str], selector: str) -> dict[str, str]:
    for selectors, body in rules.items():
        if selector in {item.strip() for item in selectors.split(",")}:
            return _declarations(body)
    return {}
class WorkbenchLayoutContractTests(unittest.TestCase):
    def test_three_column_shell_and_main_stage_can_shrink_without_overflow(self) -> None:
        rules = _rules(CSS)
        shell = _find_rule(rules, ".app-shell")
        self.assertEqual(shell.get("height"), "calc(100vh - 56px)")
        self.assertEqual(shell.get("min-height"), "0")
        main_stage = _find_rule(rules, ".main-stage")
        self.assertEqual(main_stage.get("overflow-y"), "auto")
        self.assertEqual(main_stage.get("overflow-x"), "hidden")
        self.assertEqual(main_stage.get("min-height"), "0")
        self.assertEqual(
            main_stage.get("grid-template-rows"),
            "auto minmax(280px,1fr) auto auto auto auto",
        )
        self.assertEqual(main_stage.get("gap"), "10px")

    def test_timeline_scrolls_inside_its_panel(self) -> None:
        rules = _rules(CSS)
        canvas = _find_rule(rules, ".timeline-canvas")
        self.assertEqual(canvas.get("position"), "relative")
        self.assertEqual(canvas.get("overflow-x"), "auto")
        track = _find_rule(rules, ".track-lane")
        self.assertEqual(track.get("position"), "relative")

    def test_preview_uses_container_bounds_instead_of_fixed_video_height(self) -> None:
        rules = _rules(CSS)
        preview = _find_rule(rules, ".preview-stage")
        self.assertEqual(preview.get("height"), "100%")
        self.assertEqual(preview.get("min-height"), "0")
        self.assertEqual(preview.get("max-height"), "100%")
        self.assertNotIn("56vh", TEMPLATE)
        holder = _find_rule(rules, "#preview-media")
        self.assertEqual(holder.get("width"), "100%")
        self.assertEqual(holder.get("height"), "100%")
        self.assertEqual(holder.get("overflow"), "hidden")
        self.assertEqual(holder.get("max-width"), "100%")
        self.assertEqual(holder.get("max-height"), "100%")
        template_rules = _rules(TEMPLATE_STYLE)
        video = _find_rule(template_rules, ".preview-stage video")
        self.assertEqual(video.get("height"), "100%")
        self.assertEqual(video.get("aspect-ratio"), "9/16")
        self.assertEqual(video.get("object-fit"), "contain")
        self.assertNotIn("clamp", video.get("height", ""))
        image = _find_rule(template_rules, ".preview-stage img")
        self.assertEqual(image.get("height"), "auto")
        self.assertEqual(image.get("object-fit"), "contain")

    def test_narrow_viewport_stacks_columns_without_internal_scroll_overflow(self) -> None:
        block = re.search(r"@media \(max-width:820px\)\{(.*)", CSS, flags=re.S)
        self.assertIsNotNone(block, "responsive media rules must exist")
        body = block.group(1)
        self.assertIn("grid-template-columns:1fr", body)
        self.assertIn("height:auto", body)
        self.assertIn("overflow:visible", body)
        self.assertIn(".main-stage{order:1;", body)
        self.assertIn(".decision-rail{order:2}", body)
        self.assertIn(".story-rail{order:3}", body)
        mobile_rules = _rules(body)
        mobile_main = _find_rule(mobile_rules, ".main-stage")
        self.assertEqual(mobile_main.get("grid-template-rows"), "auto")
        self.assertEqual(mobile_main.get("height"), "auto")
        self.assertEqual(mobile_main.get("overflow"), "visible")
        mobile_preview = _find_rule(mobile_rules, ".preview-stage")
        self.assertEqual(mobile_preview.get("height"), "min(70vh,640px)")
        self.assertEqual(mobile_preview.get("min-height"), "280px")
        self.assertEqual(mobile_preview.get("max-height"), "640px")
        self.assertEqual(mobile_preview.get("aspect-ratio"), "9/16")
        self.assertEqual(mobile_preview.get("width"), "auto")
        self.assertEqual(mobile_preview.get("max-width"), "100%")
        self.assertEqual(mobile_preview.get("justify-self"), "center")


if __name__ == "__main__":
    unittest.main()
