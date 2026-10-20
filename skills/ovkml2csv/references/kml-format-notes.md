# OVKML / KML format notes

Reference material for the `ovkml2csv` skill. Read only when a conversion needs
deeper inspection of the input file.

## Contents

1. [What an .ovkml file is](#what-an-ovkml-file-is)
2. [Element structure](#element-structure)
3. [Coordinate systems](#coordinate-systems)
4. [Encoding](#encoding)
5. [Inspecting a file by hand](#inspecting-a-file-by-hand)

## What an .ovkml file is

Ovital Map (奥维互动地图) exports `.ovkml`, which is standard KML 2.2 with an
extra `OvAttr` / `OvIcon` / `OvCoordType` annotation block per placemark. The
file is well-formed XML with the default namespace
`http://www.opengis.net/kml/2.2`, so a namespace-aware or local-name-based
parser reads it without modification. Renaming to `.kml` changes nothing but
the suffix — the bundled script therefore accepts `.ovkml` directly.

## Element structure

```xml
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>10.15</name>
    <Folder>                     <!-- folders nest arbitrarily deep -->
      <name>华阳河蓄滞洪区项目</name>
      <Placemark>
        <name>地表水监测点2</name>
        <OvAttr><OvIcon>4</OvIcon><OvIconNum>0</OvIconNum></OvAttr>
        <OvCoordType>CGCS2000</OvCoordType>
        <Point><coordinates>116.04872078,29.97812452,0</coordinates></Point>
      </Placemark>
    </Folder>
  </Document>
</kml>
```

- A folder name is *not* repeated inside each placemark; if grouping matters,
  walk the tree and track the enclosing `Folder` name, or export one CSV per
  folder.
- `<coordinates>` may hold several tuples separated by whitespace. Point
  geometries have exactly one; `LineString`, `LinearRing` and `Polygon` have
  many. The converter keeps the first tuple.
- Tuples are `longitude,latitude[,altitude]`, so the CSV column order is
  longitude first. Altitude is commonly `0`.
- Some exports wrap geometry inside `<MultiGeometry>`; searching for the first
  `coordinates` descendant anywhere in the placemark covers that case.

## Coordinate systems

`<OvCoordType>` states the datum of the stored numbers. The converter copies
values verbatim and never transforms them.

| Value | Meaning | Notes |
| --- | --- | --- |
| `WGS84` | GPS / KML standard | Directly usable in KML, GPS, most web maps |
| `CGCS2000` | China 2000 geodetic datum | Within roughly a metre of WGS84; treat as interchangeable for mapping |
| `GCJ-02` | "Mars" datum used by AMap/Tencent | Offset from WGS84 by tens to hundreds of metres; needs a datum shift |
| `BD-09` | Baidu datum | Offset again from GCJ-02; needs a datum shift |

When the user plans to load the CSV into a tool expecting WGS84 and the file
says `GCJ-02` or `BD-09`, state the offset explicitly and confirm the required
datum before doing any conversion; no shift is applied by this skill.

## Encoding

Ovital writes UTF-8 with a BOM (`EF BB BF`) in current versions. Older or
third-party exports can be GB18030, Big5 or UTF-16. The converter detects the
BOM, then tries UTF-8, GB18030 and Big5 in order. UTF-8 with BOM is detected
before UTF-16 so the `EF BB BF` prefix is never misread as a UTF-16 BOM.

## Inspecting a file by hand

```bash
# confirm it is XML and check for a BOM
file 10.15.ovkml

# count placemarks
grep -c '<Placemark>' 10.15.ovkml

# look at the first placemark block
grep -n -A 12 '<Placemark>' 10.15.ovkml | head -20

# check which datum is declared
grep -o '<OvCoordType>[^<]*' 10.15.ovkml | sort | uniq -c
```

Files with `<ScreenOverlay>` or `<NetworkLink>` blocks contain no placemarks and
produce an empty (header-only) CSV.
