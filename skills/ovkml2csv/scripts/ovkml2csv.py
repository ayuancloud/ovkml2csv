#!/usr/bin/env python3
"""Convert Ovital Map `.ovkml` / KML files into CSV.

The tool reads every ``<Placemark>`` in the file, keeps only the placemark
name and its coordinate, and writes a flat CSV table. Longitude and latitude
are copied verbatim from the KML so no precision is lost. Altitude is dropped
unless ``--altitude`` is requested.

Only the Python standard library is used, so the script runs anywhere with
Python 3.8+.

Typical usage::

    python3 ovkml2csv.py 10.15.ovkml
    python3 ovkml2csv.py 10.15.ovkml -o 10.15.csv --header en
    python3 ovkml2csv.py ./exports --recursive
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

__version__ = "1.0.0"

PROGRAM = "ovkml2csv"

#: File suffixes recognised as input, matched case-insensitively.
INPUT_SUFFIXES = (".ovkml", ".kml")

#: Column headers per language. ``none`` writes no header row at all.
HEADERS = {
    "zh": ("名称", "经度", "纬度", "海拔"),
    "en": ("name", "longitude", "latitude", "altitude"),
    "none": (),
}

#: Encodings tried in order when the input encoding is not given explicitly.
FALLBACK_INPUT_ENCODINGS = ("utf-8", "gb18030", "big5")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_STRICT = 3


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlacemarkRecord:
    """A single placemark reduced to name + coordinate."""

    name: str
    longitude: str
    latitude: str
    altitude: Optional[str] = None

    def as_row(self, include_altitude: bool = False) -> List[str]:
        row = [self.name, self.longitude, self.latitude]
        if include_altitude:
            row.append(self.altitude or "")
        return row


@dataclass
class ConversionResult:
    """Outcome of converting one input file."""

    source: Path
    output: Optional[Path]
    records: List[PlacemarkRecord] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    input_encoding: str = ""

    @property
    def record_count(self) -> int:
        return len(self.records)


class ConversionError(Exception):
    """Raised when an input file cannot be read or parsed."""


# --------------------------------------------------------------------------- #
# KML parsing
# --------------------------------------------------------------------------- #
def _local_name(tag: str) -> str:
    """Return the tag name without its XML namespace."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _element_text(element: Optional[ET.Element]) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _first_child(element: ET.Element, name: str) -> Optional[ET.Element]:
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def decode_kml_bytes(data: bytes, encoding: Optional[str] = None) -> Tuple[str, str]:
    """Decode raw KML bytes, honouring BOMs and Chinese legacy encodings."""
    if encoding:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            raise ConversionError(
                f"无法使用 {encoding} 解码文件（第 {exc.start} 字节）"
            ) from exc

    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"

    for candidate in FALLBACK_INPUT_ENCODINGS:
        try:
            return data.decode(candidate), candidate
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace"), "utf-8(replace)"


def parse_kml(text: str) -> ET.Element:
    """Parse KML text into an element tree root."""
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise ConversionError(f"XML 解析失败：{exc}") from exc


def iter_placemarks(root: ET.Element) -> Iterator[ET.Element]:
    """Yield every ``Placemark`` element in document order."""
    for element in root.iter():
        if _local_name(element.tag) == "Placemark":
            yield element


def parse_coordinate(value: str) -> Optional[Tuple[str, str, str]]:
    """Split a KML ``<coordinates>`` value into ``(lon, lat, alt)``.

    KML stores coordinates as ``longitude,latitude,altitude`` and allows
    several tuples separated by whitespace. Only the first tuple is used;
    values stay as text to preserve the original precision.
    """
    tokens = value.split()
    if not tokens:
        return None
    parts = tokens[0].split(",")
    if len(parts) < 2:
        return None
    longitude, latitude = parts[0].strip(), parts[1].strip()
    if not longitude or not latitude:
        return None
    altitude = parts[2].strip() if len(parts) > 2 else ""
    return longitude, latitude, altitude


def extract_records(
    root: ET.Element,
    include_altitude: bool = False,
    fallback_name: str = "",
) -> Tuple[List[PlacemarkRecord], List[str]]:
    """Extract name + coordinate for every placemark.

    Returns the records plus the labels of placemarks that carried no usable
    coordinate (which are skipped rather than guessed).
    """
    records: List[PlacemarkRecord] = []
    skipped: List[str] = []

    for placemark in iter_placemarks(root):
        name = _element_text(_first_child(placemark, "name")) or fallback_name

        coordinate_element: Optional[ET.Element] = None
        for descendant in placemark.iter():
            if _local_name(descendant.tag) == "coordinates":
                coordinate_element = descendant
                break

        coordinate = parse_coordinate(_element_text(coordinate_element))
        if coordinate is None:
            skipped.append(name or "<未命名>")
            continue

        longitude, latitude, altitude = coordinate
        records.append(
            PlacemarkRecord(
                name=name,
                longitude=longitude,
                latitude=latitude,
                altitude=altitude if include_altitude else None,
            )
        )

    return records, skipped


# --------------------------------------------------------------------------- #
# CSV writing
# --------------------------------------------------------------------------- #
def headers_for(header: str, include_altitude: bool = False) -> List[str]:
    names = HEADERS[header]
    if not names:
        return []
    return list(names[:3] + (names[3:4] if include_altitude else ()))


def write_csv(
    records: Iterable[PlacemarkRecord],
    handle: io.TextIOBase,
    header: str = "zh",
    delimiter: str = ",",
    include_altitude: bool = False,
    quote_all: bool = False,
) -> None:
    """Write records as CSV into an already opened text handle."""
    writer = csv.writer(
        handle,
        delimiter=delimiter,
        quoting=csv.QUOTE_ALL if quote_all else csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )
    columns = headers_for(header, include_altitude)
    if columns:
        writer.writerow(columns)
    for record in records:
        writer.writerow(record.as_row(include_altitude))


def render_csv(records: Iterable[PlacemarkRecord], **kwargs) -> str:
    """Render records to a CSV string (used by tests and ``-o -``)."""
    buffer = io.StringIO()
    write_csv(records, buffer, **kwargs)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# File level conversion
# --------------------------------------------------------------------------- #
def convert_file(
    source: Path,
    output: Optional[Path],
    *,
    input_encoding: Optional[str] = None,
    output_encoding: str = "utf-8-sig",
    header: str = "zh",
    delimiter: str = ",",
    include_altitude: bool = False,
    quote_all: bool = False,
) -> ConversionResult:
    """Convert one ``.ovkml`` / ``.kml`` file into a CSV file."""
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise ConversionError(f"无法读取 {source}：{exc}") from exc

    text, used_encoding = decode_kml_bytes(data, input_encoding)
    root = parse_kml(text)
    records, skipped = extract_records(root, include_altitude=include_altitude)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output.open("w", encoding=output_encoding, newline="") as handle:
                write_csv(
                    records,
                    handle,
                    header=header,
                    delimiter=delimiter,
                    include_altitude=include_altitude,
                    quote_all=quote_all,
                )
        except OSError as exc:
            raise ConversionError(f"无法写入 {output}：{exc}") from exc

    return ConversionResult(
        source=source,
        output=output,
        records=records,
        skipped=skipped,
        input_encoding=used_encoding,
    )


def default_output_path(source: Path) -> Path:
    """``10.15.ovkml`` -> ``10.15.csv`` (kept next to the input file)."""
    return source.with_suffix(".csv")


def collect_inputs(paths: Sequence[Path], recursive: bool = False) -> List[Path]:
    """Expand files and directories into a sorted list of KML inputs."""
    collected: List[Path] = []
    for path in paths:
        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            for candidate in sorted(iterator):
                if candidate.is_file() and candidate.suffix.lower() in INPUT_SUFFIXES:
                    collected.append(candidate)
        elif path.is_file():
            collected.append(path)
        else:
            raise ConversionError(f"路径不存在：{path}")
    return collected


# --------------------------------------------------------------------------- #
# Command line interface
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "把奥维互动地图导出的 .ovkml / .kml 文件转换为 CSV，"
            "只保留名称、经度、纬度。无需手动改后缀。"
        ),
        epilog=(
            "示例：\n"
            f"  {PROGRAM} 10.15.ovkml\n"
            f"  {PROGRAM} 10.15.ovkml -o 10.15.csv --header en\n"
            f"  {PROGRAM} ./exports --recursive --altitude\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("inputs", nargs="+", type=Path, help=".ovkml / .kml 文件或目录")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="输出文件或目录；单个输入时可用 '-' 输出到标准输出（默认与输入同目录同名 .csv）",
    )
    parser.add_argument("--recursive", action="store_true", help="递归处理子目录")
    parser.add_argument(
        "--header",
        choices=sorted(HEADERS),
        default="zh",
        help="表头语言：zh（默认）、en 或 none（不写表头）",
    )
    parser.add_argument("--altitude", action="store_true", help="额外输出海拔列")
    parser.add_argument("--delimiter", default=",", help="CSV 分隔符，默认逗号")
    parser.add_argument("--quote-all", action="store_true", help="所有字段都加引号")
    parser.add_argument("--input-encoding", help="输入文件编码，默认自动识别（UTF-8/GB18030/Big5）")
    parser.add_argument(
        "--output-encoding",
        default="utf-8-sig",
        help="输出文件编码，默认 utf-8-sig（带 BOM，Excel 直接双击不乱码）",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="存在缺少坐标的点位时以退出码 3 结束",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="不输出转换摘要")
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {__version__}")
    return parser


def _log(message: str, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr)


def _resolve_output_target(
    output: Optional[Path],
    inputs: Sequence[Path],
) -> Tuple[Optional[Path], bool]:
    """Return ``(target, is_directory)`` for the requested output path."""
    if output is None:
        return None, False
    if str(output) == "-":
        return None, False
    if len(inputs) > 1 or (inputs and inputs[0].is_dir()):
        return output, True
    if output.is_dir():
        return output, True
    return output, False


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        inputs = collect_inputs(args.inputs, recursive=args.recursive)
    except ConversionError as exc:
        print(f"{PROGRAM}: 错误：{exc}", file=sys.stderr)
        return EXIT_ERROR

    if not inputs:
        print(f"{PROGRAM}: 错误：未找到任何 .ovkml / .kml 文件", file=sys.stderr)
        return EXIT_ERROR

    to_stdout = args.output is not None and str(args.output) == "-"
    if to_stdout and len(inputs) > 1:
        print(f"{PROGRAM}: 错误：输出到标准输出时只能有一个输入文件", file=sys.stderr)
        return EXIT_ERROR

    target, target_is_dir = _resolve_output_target(args.output, inputs)

    total_records = 0
    total_skipped = 0
    failures: List[str] = []

    for source in inputs:
        if to_stdout:
            destination: Optional[Path] = None
        elif target is None:
            destination = default_output_path(source)
        elif target_is_dir:
            destination = target / default_output_path(source).name
        else:
            destination = target

        try:
            result = convert_file(
                source,
                destination,
                input_encoding=args.input_encoding,
                output_encoding=args.output_encoding,
                header=args.header,
                delimiter=args.delimiter,
                include_altitude=args.altitude,
                quote_all=args.quote_all,
            )
        except ConversionError as exc:
            failures.append(f"{source}: {exc}")
            print(f"{PROGRAM}: 失败：{exc}", file=sys.stderr)
            continue

        total_records += result.record_count
        total_skipped += len(result.skipped)

        if to_stdout:
            sys.stdout.write(
                render_csv(
                    result.records,
                    header=args.header,
                    delimiter=args.delimiter,
                    include_altitude=args.altitude,
                    quote_all=args.quote_all,
                )
            )
            _log(f"{source} -> 标准输出：{result.record_count} 条记录", args.quiet)
        else:
            _log(
                f"{source} -> {result.output}：{result.record_count} 条记录"
                f"（输入编码 {result.input_encoding}）",
                args.quiet,
            )

        for label in result.skipped:
            _log(f"  跳过无坐标点位：{label}", args.quiet)

    _log(
        f"完成：{len(inputs) - len(failures)} 个文件，{total_records} 条记录"
        + (f"，跳过 {total_skipped} 条" if total_skipped else ""),
        args.quiet,
    )

    if failures:
        return EXIT_ERROR
    if args.strict and total_skipped:
        return EXIT_STRICT
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
