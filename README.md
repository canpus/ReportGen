# CYCT 出厂检测报告生成器

为长园长通（CYCT）生成固定格式的出厂检测报告（中文 / English / Русский），同时输出 docx 与 PDF，并管理历史报告。

- 界面：tkinter；报告：python-docx 按 `templates/` 中的版式生成；PDF：后台调用 Word（2013+）或 WPS（comtypes）。
- 数据：程序目录下 `data/`（SQLite 数据库、报告库、设置、自定义模板）。
- 使用说明见 [使用说明.txt](使用说明.txt)（随发布包分发）。

## 目录

| 路径 | 内容 |
|---|---|
| `src/cyct_report/` | 程序代码（核心逻辑与 `ui/` 界面分开） |
| `presets/terms.json` | 三语术语表 |
| `presets/standards/*.json` | 各标准的检测项、指标、测试方法与产品类型 |
| `templates/report_*.docx` | 三种语言的报告模板（页眉、页脚、页面设置） |
| `assets/` | 程序图标（由 `tools/make_icon.py` 生成） |
| `tools/` | 打包、模板生成、版式对照与界面冒烟脚本 |
| `tests/` | pytest 测试 |

主要模块：`presets`（标准库加载与检测项生成）、`docx_builder` / `docx_table` / `docx_text`（报告排版）、`office`（Word/WPS 后台转换）、`db`（SQLite）、`importer`（旧报告导入）、`service`（生成流程）、`checker`（实测值判定）、`search`（模糊搜索）。

## 开发

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
run.bat
```

- 版式对照：`python tools/render_sample.py work/render`，用样本数据生成中/英/俄报告及 PNG。
- 界面冒烟：`python tools/ui_smoke.py work/ui`，自动填写、生成、导入并截图。
- 重新生成模板：`python tools/make_templates.py <中文样本.docx> <英文样本.docx>`。
- 指标核对表：`python tools/export_checklist.py final/预置检测项核对表_v1.xlsx`，把预置库导出为 Excel 供质检核对；预置库修改后可重新导出。

## 打包

```bash
.venv\Scripts\python.exe tools/build.py
```

产物在 `dist/CYCT检测报告/`（exe + `presets/` + `templates/` + `assets/` + 使用说明）及同名 zip。当前体积：文件夹约 38 MB，zip 约 18 MB。
在新电脑上可运行 `CYCTReport.exe --selftest`，结果写入 `data/selftest/result.txt`，用于确认 Word/WPS 后台转换可用。

## 标准库格式

每个标准一个 JSON 文件，包含 `tables`（检测项表）和 `templates`（产品类型）：

- 分组行：`{"g": "{术语键}", "note": "...", "only": ["13A"]}`
- 检测项：`[名称, 条件, 单位, 指标, 测试方法, {"tc": ["50","HT"], "opt": true}]`
- 字段可写成：含 `{术语键}` 的文字；按 `cols` 顺序排列的列表（`null` 表示该类型不适用）；或 `{"zh":..,"en":..,"ru":..}`。
- 条件中的 `Tmax`、`Tmax95`（不超过 95 ℃）、`Tmax+20/80`（Tmax+20 且不低于 80 ℃）在界面中按填写的 Tmax 换算；`Tc` 按温度等级取 23 ℃ 或 Tmax（EN 12068）。
- 上下标：`10^14`、`R_S100`、Unicode 下标（`E₁₀₀/E₀`），报告中输出为真正的上下标。
- `templates[].parts` 可引用其他标准的表：`"en12068:t1"`。

## 标准来源

| 文件 | 依据 |
|---|---|
| `iso21809-3.json` | ISO 21809-3:2016 Table 10、12、16、17、18 |
| `en12068.json` | BS EN 12068:1999 Table 1、2 |
| `din30672.json` | DIN 30672:2000-12（沿用 EN 12068 指标，C 级取第三列，另加 5.2/6.2 条要求） |
| `gbt23257.json` | CYCT 现行 GB/T 23257-2017 热收缩带出货检测报告 |
| `gost-r-51164.json` | ГОСТ Р 51164-98 表 1（结构 14–17）、表 2 |
| `adnoc-ages-sp-07-006.json` | ADNOC AGES-SP-07-006 Rev.1 Table C、D |
| `pdo-sp-2389.json` | PDO SP-2389（2021）Table 13.1、14.1 |
| `gasco-dgs-1470-006.json` | GASCO DGS 1470-006 Rev 0 第 10.4.5 条 |
