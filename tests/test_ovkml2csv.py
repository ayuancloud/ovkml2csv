#!/usr/bin/env python3
"""Tests for the ovkml2csv converter.

Run with::

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "ovkml2csv.py"
SKILL_SCRIPT = REPO_ROOT / "skills" / "ovkml2csv" / "scripts" / "ovkml2csv.py"
EXAMPLE_OVKML = REPO_ROOT / "examples" / "示例点位.ovkml"
EXAMPLE_EXPECTED = REPO_ROOT / "examples" / "expected" / "示例点位.csv"


def load_module():
    spec = importlib.util.spec_from_file_location("ovkml2csv", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ovkml2csv"] = module
    spec.loader.exec_module(module)
    return module


mod = load_module()

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<Folder>
<name>项目一</name>
<Placemark>
  <name>点位甲</name>
  <OvCoordType>CGCS2000</OvCoordType>
  <Point><coordinates>116.04872078,29.97812452,0</coordinates></Point>
</Placemark>
<Placemark>
  <name>点位乙</name>
  <Point><coordinates>116.10705614,29.89799163,15.5</coordinates></Point>
</Placemark>
<Placemark>
  <name>没有坐标的点</name>
</Placemark>
<Placemark>
  <name>折线</name>
  <LineString><coordinates>117.1,31.1,0 117.2,31.2,0</coordinates></LineString>
</Placemark>
</Folder>
</Document>
</kml>
"""


def records_from(text: str, **kwargs):
    root = mod.parse_kml(text)
    return mod.extract_records(root, **kwargs)


class ParsingTests(unittest.TestCase):
    def test_extracts_name_and_coordinate(self):
        records, skipped = records_from(SAMPLE)
        self.assertEqual(skipped, ["没有坐标的点"])
        self.assertEqual(
            [(r.name, r.longitude, r.latitude) for r in records[:2]],
            [
                ("点位甲", "116.04872078", "29.97812452"),
                ("点位乙", "116.10705614", "29.89799163"),
            ],
        )

    def test_longitude_comes_before_latitude(self):
        records, _ = records_from(SAMPLE)
        for record in records:
            # Values in China: longitude 73-136, latitude 3-54.
            self.assertTrue(73 <= float(record.longitude) <= 136, record.longitude)
            self.assertTrue(3 <= float(record.latitude) <= 54, record.latitude)

    def test_precision_is_preserved(self):
        records, _ = records_from(SAMPLE)
        self.assertEqual(records[0].longitude, "116.04872078")
        self.assertEqual(records[0].latitude, "29.97812452")

    def test_altitude_kept_only_on_request(self):
        records, _ = records_from(SAMPLE)
        self.assertIsNone(records[0].altitude)
        records, _ = records_from(SAMPLE, include_altitude=True)
        self.assertEqual(records[0].altitude, "0")
        self.assertEqual(records[1].altitude, "15.5")

    def test_linestring_uses_first_tuple(self):
        records, _ = records_from(SAMPLE)
        self.assertEqual(records[-1].name, "折线")
        self.assertEqual(records[-1].longitude, "117.1")
        self.assertEqual(records[-1].latitude, "31.1")

    def test_empty_name_is_kept_as_empty_cell(self):
        text = SAMPLE.replace("<name>点位甲</name>", "<name></name>")
        records, _ = records_from(text)
        self.assertEqual(records[0].name, "")

    def test_screen_overlay_only_file_yields_no_records(self):
        text = '<?xml version="1.0"?><kml><Document><ScreenOverlay/></Document></kml>'
        records, skipped = records_from(text)
        self.assertEqual((records, skipped), ([], []))


class EncodingTests(unittest.TestCase):
    def test_utf8_bom_detected(self):
        data = SAMPLE.encode("utf-8-sig")
        text, encoding = mod.decode_kml_bytes(data)
        self.assertEqual(encoding, "utf-8-sig")
        self.assertIn("点位甲", text)

    def test_gb18030_auto_detected(self):
        data = SAMPLE.encode("gb18030")
        text, encoding = mod.decode_kml_bytes(data)
        self.assertEqual(encoding, "gb18030")
        self.assertIn("点位甲", text)

    def test_utf16_bom_detected(self):
        data = SAMPLE.encode("utf-16")
        text, encoding = mod.decode_kml_bytes(data)
        self.assertEqual(encoding, "utf-16")
        self.assertIn("点位甲", text)

    def test_explicit_encoding_is_respected(self):
        data = SAMPLE.encode("gb18030")
        text, encoding = mod.decode_kml_bytes(data, "gb18030")
        self.assertEqual(encoding, "gb18030")
        self.assertIn("点位甲", text)


class CsvFormattingTests(unittest.TestCase):
    def test_default_header_is_chinese(self):
        records, _ = records_from(SAMPLE)
        csv_text = mod.render_csv(records)
        self.assertTrue(csv_text.startswith("名称,经度,纬度\n"))
        self.assertIn("点位甲,116.04872078,29.97812452\n", csv_text)

    def test_english_header_and_altitude(self):
        records, _ = records_from(SAMPLE, include_altitude=True)
        csv_text = mod.render_csv(records, header="en", include_altitude=True)
        self.assertTrue(csv_text.startswith("name,longitude,latitude,altitude\n"))
        self.assertIn("点位乙,116.10705614,29.89799163,15.5\n", csv_text)

    def test_no_header(self):
        records, _ = records_from(SAMPLE)
        csv_text = mod.render_csv(records, header="none")
        self.assertFalse(csv_text.startswith("名称"))
        self.assertEqual(len(csv_text.strip().splitlines()), len(records))

    def test_custom_delimiter_and_quote_all(self):
        records, _ = records_from(SAMPLE)
        csv_text = mod.render_csv(records, delimiter=";", quote_all=True)
        self.assertTrue(csv_text.startswith('"名称";"经度";"纬度"\n'))

    def test_comma_inside_name_is_quoted(self):
        text = SAMPLE.replace("<name>点位甲</name>", "<name>点位,甲</name>")
        records, _ = records_from(text)
        csv_text = mod.render_csv(records)
        self.assertIn('"点位,甲",116.04872078,29.97812452\n', csv_text)


class FileConversionTests(unittest.TestCase):
    def test_default_output_path(self):
        self.assertEqual(
            mod.default_output_path(Path("/tmp/10.15.ovkml")).name, "10.15.csv"
        )
        self.assertEqual(
            mod.default_output_path(Path("/tmp/10.15.KML")).name, "10.15.csv"
        )

    def test_convert_file_writes_utf8_sig_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "10.15.ovkml"
            src.write_bytes(SAMPLE.encode("utf-8-sig"))
            dst = Path(tmp) / "out.csv"
            result = mod.convert_file(src, dst)
            self.assertEqual(result.record_count, 3)
            self.assertEqual(result.skipped, ["没有坐标的点"])
            raw = dst.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            lines = raw.decode("utf-8-sig").strip().splitlines()
            self.assertEqual(lines[0], "名称,经度,纬度")
            self.assertEqual(lines[1], "点位甲,116.04872078,29.97812452")

    def test_convert_without_output_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.ovkml"
            src.write_text(SAMPLE, encoding="utf-8")
            result = mod.convert_file(src, None)
            self.assertIsNone(result.output)
            self.assertEqual(result.record_count, 3)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["a.ovkml"])

    def test_collect_inputs_directory_and_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.ovkml").write_text(SAMPLE, encoding="utf-8")
            (root / "ignore.txt").write_text("x", encoding="utf-8")
            nested = root / "sub"
            nested.mkdir()
            (nested / "b.kml").write_text(SAMPLE, encoding="utf-8")

            flat = mod.collect_inputs([root])
            self.assertEqual([p.name for p in flat], ["a.ovkml"])

            deep = mod.collect_inputs([root], recursive=True)
            self.assertEqual([p.name for p in deep], ["a.ovkml", "b.kml"])

    def test_example_matches_expected_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "示例点位.csv"
            mod.convert_file(EXAMPLE_OVKML, dst)
            self.assertEqual(
                dst.read_text(encoding="utf-8-sig"),
                EXAMPLE_EXPECTED.read_text(encoding="utf-8-sig"),
            )


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_cli_writes_default_output_next_to_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "10.15.ovkml"
            src.write_bytes(SAMPLE.encode("utf-8-sig"))
            proc = self.run_cli(str(src))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = Path(tmp) / "10.15.csv"
            self.assertTrue(out.is_file())
            self.assertIn("3 条记录", proc.stderr)

    def test_cli_stdout_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "10.15.ovkml"
            src.write_text(SAMPLE, encoding="utf-8")
            proc = self.run_cli(str(src), "-o", "-", "--header", "en", "-q")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(proc.stdout.startswith("name,longitude,latitude\n"))
            self.assertEqual(proc.stderr, "")

    def test_cli_strict_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "10.15.ovkml"
            src.write_text(SAMPLE, encoding="utf-8")
            proc = self.run_cli(str(src), "-q", "--strict")
            self.assertEqual(proc.returncode, mod.EXIT_STRICT)

    def test_cli_missing_path_fails(self):
        proc = self.run_cli("/nonexistent/path.ovkml")
        self.assertEqual(proc.returncode, mod.EXIT_ERROR)
        self.assertIn("路径不存在", proc.stderr)

    def test_cli_directory_batch_with_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "in"
            src_dir.mkdir()
            (src_dir / "a.ovkml").write_text(SAMPLE, encoding="utf-8")
            (src_dir / "b.ovkml").write_text(SAMPLE, encoding="utf-8")
            out_dir = root / "out"
            proc = self.run_cli(str(src_dir), "-o", str(out_dir), "-q")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                sorted(p.name for p in out_dir.iterdir()), ["a.csv", "b.csv"]
            )


class RepositoryTests(unittest.TestCase):
    def test_skill_script_is_in_sync_with_root_script(self):
        self.assertTrue(SKILL_SCRIPT.is_file(), "missing bundled skill script")
        self.assertEqual(MODULE_PATH.read_bytes(), SKILL_SCRIPT.read_bytes())

    def test_skill_frontmatter_is_valid(self):
        skill_md = REPO_ROOT / "skills" / "ovkml2csv" / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---\n")[1]
        self.assertIn("name: ovkml2csv", frontmatter)
        self.assertIn("description:", frontmatter)

    def test_skill_directory_is_named_after_skill(self):
        self.assertEqual(SKILL_SCRIPT.parent.parent.name, "ovkml2csv")


if __name__ == "__main__":
    unittest.main()
