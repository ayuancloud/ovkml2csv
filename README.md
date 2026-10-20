# ovkml2csv

把奥维互动地图（Ovital Map）导出的 `.ovkml` 文件转换成 CSV，只保留**名称、经度、纬度**三列。

本项目同时是一个 **Codex 技能（Skill）**：把 `skills/ovkml2csv/` 目录安装到 Codex 的技能目录后，Codex 会自动识别 `.ovkml` / `.kml` 转 CSV 的需求并调用随附脚本。

- 无需手动把 `.ovkml` 改成 `.kml`，脚本直接读取 `.ovkml`
- 只用 Python 标准库，Python 3.8+ 即可运行，无第三方依赖
- 坐标按原文输出，不经过浮点转换，8 位小数等精度完整保留
- 自动识别 UTF-8（含 BOM）、UTF-16、GB18030、Big5 编码，中文名称不乱码
- 输出默认 `utf-8-sig`（带 BOM），Excel 双击打开不乱码

## 快速开始

```bash
git clone https://github.com/ayuancloud/ovkml2csv.git
cd ovkml2csv

# 转换单个文件，CSV 生成在同目录：10.15.ovkml -> 10.15.csv
python3 ovkml2csv.py 10.15.ovkml

# 指定输出文件与英文表头
python3 ovkml2csv.py 10.15.ovkml -o 10.15.csv --header en

# 批量转换整个目录（含子目录），并额外保留海拔列
python3 ovkml2csv.py ./exports --recursive --altitude

# 不写文件，直接看结果
python3 ovkml2csv.py 10.15.ovkml -o - --header en -q
```

输出示例：

```csv
名称,经度,纬度
地表水监测点2,116.04872078,29.97812452
地表水监测点1,116.10705614,29.89799163
```

## 参数说明

| 参数 | 说明 |
| --- | --- |
| `-o, --output` | 输出文件或目录；`-` 表示输出到标准输出（默认与输入同目录同名 `.csv`） |
| `--recursive` | 输入是目录时递归处理子目录 |
| `--header {zh,en,none}` | 表头语言，默认 `zh`（`名称,经度,纬度`）；`none` 不写表头 |
| `--altitude` | 额外输出海拔列 |
| `--delimiter` | CSV 分隔符，默认逗号 |
| `--quote-all` | 所有字段都加引号 |
| `--input-encoding` | 指定输入编码，默认自动识别 |
| `--output-encoding` | 输出编码，默认 `utf-8-sig` |
| `--strict` | 存在缺少坐标的点位时以退出码 3 结束 |
| `-q, --quiet` | 不输出转换摘要 |
| `--version` | 查看版本 |

退出码：`0` 成功，`1` 读取/解析失败或未找到输入文件，`3` `--strict` 模式下存在被跳过的点位。

## 作为 Codex 技能安装

技能的加载目录：

| 位置 | 作用范围 |
| --- | --- |
| `~/.codex/skills/` | 全局，所有项目可用 |
| `<项目目录>/.codex/skills/` | 仅当前项目 |

安装方式（任选一种）：

```bash
# 全局安装
mkdir -p ~/.codex/skills
cp -r skills/ovkml2csv ~/.codex/skills/

# 或安装到某个项目
mkdir -p /path/to/project/.codex/skills
cp -r skills/ovkml2csv /path/to/project/.codex/skills/
```

也可以直接在 Codex 里说“把 github.com/ayuancloud/ovkml2csv 的 skills/ovkml2csv 安装为技能”，由 `$skill-installer` 完成。

安装后，出现类似下面的请求时技能会自动生效：

- “把这个 `10.15.ovkml` 转成 CSV，只要名称和经纬度”
- “把奥维导出的点位文件导出成表格”
- “提取 KML 里所有点的经纬度”

## 项目结构

```
ovkml2csv/
├── ovkml2csv.py                        # 转换脚本（可直接运行，也可 import）
├── skills/ovkml2csv/                   # Codex 技能
│   ├── SKILL.md                        # 技能定义（name + description 触发元数据）
│   ├── agents/openai.yaml              # 技能在 UI 中的展示信息
│   ├── references/kml-format-notes.md  # OVKML/KML 格式与坐标系说明
│   └── scripts/ovkml2csv.py            # 与根目录脚本保持一致的随附副本
├── examples/示例点位.ovkml             # 示例输入（坐标为演示数据）
├── examples/expected/示例点位.csv      # 期望输出
├── tests/test_ovkml2csv.py             # 单元测试
├── ci/tests.yml                        # GitHub Actions 配置（可选启用）
└── tools/sync_skill_script.py          # 同步/校验技能脚本副本
```

技能需要自带脚本才能在单独安装后仍可用，因此 `skills/ovkml2csv/scripts/ovkml2csv.py` 是根目录脚本的副本。修改根脚本后执行：

```bash
python3 tools/sync_skill_script.py          # 复制到技能目录
python3 tools/sync_skill_script.py --check  # 校验两者是否一致（返回码非 0 表示不一致）
```

## 在代码中调用

```python
from ovkml2csv import convert_file, extract_records, parse_kml

result = convert_file("10.15.ovkml", "10.15.csv")
print(result.record_count, result.skipped)

records, skipped = extract_records(parse_kml(open("10.15.ovkml", encoding="utf-8-sig").read()))
print(records[0].name, records[0].longitude, records[0].latitude)
```

## 处理规则

- 逐个读取文件中的 `<Placemark>`，取 `<name>` 与第一个 `<coordinates>`
- KML 坐标顺序是 `经度,纬度,海拔`，CSV 输出顺序为 `名称,经度,纬度`（需要海拔时加 `--altitude`）
- `LineString` / `Polygon` / `MultiGeometry` 取第一个坐标点，保证“一行一个点位”
- 没有坐标的 `<Placemark>` 会被跳过，并在 stderr 与摘要中列出名称，不会静默丢弃
- 不修改原始文件；输入文件只读

## 坐标系说明

脚本按原文输出坐标，不做任何基准转换。奥维文件里的 `<OvCoordType>` 会标明基准：`WGS84` 可直接用于 GPS 与地图服务，`CGCS2000` 与 WGS84 差异约在米级，`GCJ-02`（高德/腾讯）与 `BD-09`（百度）与 WGS84 存在几十到数百米偏移，需要基准纠偏时请先确认目标基准。详见 [references/kml-format-notes.md](skills/ovkml2csv/references/kml-format-notes.md)。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

仓库在 `ci/tests.yml` 中提供了 GitHub Actions 配置（在 Python 3.8 / 3.10 / 3.12 上跑测试并做命令行冒烟测试）。
启用方式：把该文件复制到 `.github/workflows/tests.yml` 并提交即可。

## 致谢

早期思路参考了 [mick-schroeder/kml2csv](https://github.com/mick-schroeder/kml2csv) 的 XSLT 样式表方案（用 Firefox 解析 XSLT 后手工复制结果）；本项目用 Python 重写为可重复执行的命令行工具，并支持 `.ovkml` 后缀与中文编码。

## 许可证

[MIT](LICENSE)
