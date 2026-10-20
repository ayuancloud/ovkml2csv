---
name: ovkml2csv
description: >-
  Convert Ovital Map (奥维互动地图) .ovkml files and plain .kml files into CSV
  tables that contain only the placemark name, longitude and latitude. Use this
  skill whenever the user supplies an .ovkml/.kml file, or asks to 把 ovkml/kml
  转成 csv、提取名称和经纬度、导出点位坐标、把奥维文件转成表格, or needs
  coordinates extracted from KML for spreadsheets, GIS import, Excel or
  downstream data processing. Handles BOM and GB18030/Big5 encoded exports,
  nested folders, Point/LineString/Polygon geometries, batch directories and
  coordinate-precision preservation.
---

# OVKML to CSV

Reduce an Ovital Map `.ovkml` (or any `.kml`) export to a flat CSV of
`name, longitude, latitude`.

## Key facts

- `.ovkml` is plain KML text; **never ask the user to rename the file**. The
  bundled script reads the `.ovkml` suffix directly.
- KML stores coordinates as `longitude,latitude,altitude`. The output keeps
  longitude first. Never swap the two columns.
- Coordinates are copied as text, so the original precision (e.g. 8 decimals)
  is preserved. Do not cast them to float and back.
- Altitude is discarded by default because most users only want name + 经纬度.

## Workflow

1. Locate the script. Prefer the copy inside this skill directory:
   `scripts/ovkml2csv.py` (relative to this `SKILL.md`). If the skill was
   installed from the repository, the identical file also exists at the
   repository root as `ovkml2csv.py`.
2. Run the converter on the user's file. Ask for the file path only if it was
   not provided; do not invent coordinates.

   ```bash
   python3 scripts/ovkml2csv.py "<input.ovkml>" -o "<output.csv>"
   ```

3. Verify the result before reporting: count the data rows, confirm the header
   is `名称,经度,纬度`, and spot-check that longitude is roughly 73–136 and
   latitude roughly 3–54 for data in China (values outside those ranges are a
   signal that the columns were read from an unexpected element).
4. Report the output path, the record count, and any skipped placemarks. Give
   the user a link to the produced CSV file.

## Command reference

```bash
# single file, CSV written next to the input as <name>.csv
python3 scripts/ovkml2csv.py 10.15.ovkml

# explicit output, English header
python3 scripts/ovkml2csv.py 10.15.ovkml -o 10.15.csv --header en

# whole directory, recursive, keep altitude
python3 scripts/ovkml2csv.py ./exports --recursive --altitude

# inspect without writing a file
python3 scripts/ovkml2csv.py 10.15.ovkml -o - --header en -q
```

| Option | Purpose |
| --- | --- |
| `-o, --output` | Output file or directory; `-` streams CSV to stdout |
| `--recursive` | Recurse into subdirectories when an input is a directory |
| `--header {zh,en,none}` | Header language, default `zh` (`名称,经度,纬度`) |
| `--altitude` | Add an altitude column |
| `--delimiter` | CSV delimiter, default `,` |
| `--quote-all` | Quote every field |
| `--input-encoding` | Force the input encoding instead of auto-detecting |
| `--output-encoding` | Output encoding, default `utf-8-sig` (Excel-friendly BOM) |
| `--strict` | Exit with code 3 when a placemark has no coordinate |
| `-q, --quiet` | Suppress the stderr summary |

Exit codes: `0` success, `1` read/parse failure or no input found, `3` strict
mode with skipped placemarks.

## Edge cases

- **Garbled Chinese names**: the export is not UTF-8. The script already tries
  UTF-8 (with/without BOM), UTF-16, GB18030 and Big5. Only pass
  `--input-encoding gbk` when auto-detection still produces mojibake.
- **Placemark without coordinates**: it is skipped, listed on stderr, and
  counted in the summary. Report skipped names to the user instead of silently
  dropping them.
- **LineString / Polygon / MultiGeometry**: the first coordinate tuple is used,
  which is the intended behaviour for "one point per row" output.
- **Empty `<name>`**: written as an empty cell; the placemark is still exported
  when a coordinate exists.
- **Coordinate reference system**: values are passed through untouched. When the
  file contains `<OvCoordType>`, mention the datum to the user; see
  [references/kml-format-notes.md](references/kml-format-notes.md) for what
  CGCS2000 / GCJ-02 / BD-09 mean and when a conversion is required.

## Do not

- Do not build a browser-based XSLT workflow; the bundled script replaces the
  legacy Firefox stylesheet approach.
- Do not add columns, reorder them, or rename headers unless the user asks.
- Do not edit the user's source `.ovkml` file; treat it as read-only input.
