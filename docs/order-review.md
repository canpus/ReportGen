# 订单规格书审校台

质量工程师可以导入客户的英文 PDF，逐条核对检测项目、条件、方法、合格判据、抽样、频次及失败处置。桌面版在本机保存原件、修订记录和订单快照。原有出厂报告程序继续使用原入口。

## 启动桌面版

**Windows 便携包**解压到当前用户有写权限的目录，双击 `ReportGen/Start-ReportGen.bat`。包内带 Python、Tcl/Tk、PDF 与 Excel 组件及图标。程序在同级 `private/` 中保存配置、原件和 SQLite，在 `exports/` 中保存交付物。备份时先关闭窗口，再复制这两个目录。搬到另一 Windows 用户账户后需重新填写 API 密钥。

**源码版**使用带 Tk 的 Python。Linux 图形会话需要 X11 或 XWayland 以及支持中文字体的 Tk。以下命令在仓库根目录执行。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-orders.txt
.venv/bin/python tools/order_desktop.py --data-dir /private/orders
```

Windows 源码版可使用 `py -3.12 -m venv .venv`，将上述解释器替换为 `.venv\Scripts\python.exe`。省略数据目录时使用当前用户的 ReportGen 订单目录。原有 Web 审校入口为 `python tools/order_review.py serve --open`。

## 导入与 API 配置

1. 普通原生文本 PDF 可直接点「导入 PDF」。填写订单号、文号和版次，可先本地预览任意物理页。默认桌面配置使用本地确定性规则。
2. 需要图像识别时打开「API 设置」，启用视觉解析，输入服务地址、模型及认证信息。地址可填 `192.168.1.20:8000`、内网 HTTP、外部 HTTPS 或完整的兼容服务路径。标准认证使用 Authorization 和 Bearer，自定义认证头可自行填写。点「测试连接」会发送一条文本请求，再点「保存配置」。
3. 每个非回环服务都需要勾选「允许向此服务发送筛选后的规格书页」。系统按页筛选可读出的检测表和正文，跳过可识别的封面、目录、修订记录。纯图片页缺少本地文本时，先用导入窗口预览，再输入经授权的物理页范围，例如 `4,6-8`。显式页码决定本次允许发送的全集。其余页仍会做本地规则扫描。服务接收所选页的彩色图像及本页文字提示。
4. 视觉服务可按行返回原文和字段，区域可选。解析器接受纯 JSON 和 Markdown JSON 代码块。无区域的图像证据定位到整页。未能转录、接口超时或响应截断均逐页登记待核查。可以框选补录或登记待澄清。
5. 导入按内容哈希和文档版本登记。同一订单、文号、版次、文件的重复导入会打开既有审校进度。同文副本共享适用的审校记录。需要重新核验新发规格书时登记其新版本。

密钥保存在私有配置 `api.json`。Windows 使用当前用户 DPAPI，Linux 使用仅当前用户可读写的文件。包含客户信息的原件、截图、导出和配置均应保存在私有位置。

## 对照原页审校

- 选择清单中的一项，左侧跳到 PDF 物理页并框出相应证据。可以拖动分隔线、翻页、输入页码、放大，放大后拖动视图检查表格另一侧。右侧展示限值、条件、方法、英文原文、告警、脚注和引用。状态下拉框与查找框可按检测项、工况、部件、阶段或条目编号筛选。
- **确认**时填写审核人。涉及 RED、比较符、根号、指数或视觉转录时，勾选已核对并写明依据。标准比对结果只在参考区域出现。数值高温选用 Tmax 基准时，还需核实该工况是否为适用的最高温度。
- **修订**允许就地修改结构化字段并登记依据。原文和初值保留，审计中可见修改人、时间及变化。仅典型值、待定占位和阶段横线继续保留其业务语义。
- **待澄清**需要问题和待答方。**排除非检测项**需要审核人和原因，适用于目录条目、行政要求等噪声。已排除项可通过状态筛选重新打开；重新确认或修订均产生新的审计事件。整页尚未识别时，排除需要额外确认已核实整页无检测要求。原页确有要求时可框选补录。
- **导出订单**生成一个确认版目录。未处置的 RED 或 CHECK 会指明阻断条目，普通未审候选会在摘要中计数。相同状态重复导出复用同一快照。

## 导出文件

| 文件 | 使用方与内容 |
| --- | --- |
| `confirmed.json` | 质量部留档。已确认条款、三阶段频次、TQ、排除记录、来源、原页区域、版本及审计 |
| `confirmed.xlsx` | 质量部核查。页码链接到本工作簿证据行，另含文档、频次、澄清、参考及审计工作表 |
| `laboratory.xlsx` | 可单独发送给实验室。按实验室、现场和澄清分表，显示客户原文、文号、版次、物理页、条件、方法、限值和处置 |

实验室填写浅黄色的 `Actual Test Result`、`Test Specimen/Date` 和 `Lab Judgement`。导出时三列均为空。工作表保护锁定客户英文和执行条件，页码为普通可读文字。空缺限值、典型值和待澄清项均有单独表示。

## CLI 与合成练习

```sh
python tests/orders/synthetic.py work/synthetic-fixtures
python tools/order_review.py --data-dir /private/orders import work/synthetic-fixtures/workflow.pdf --order QA-DEMO --number SYN-1 --revision A
python tools/order_review.py --data-dir /private/orders list
python tools/order_review.py --data-dir /private/orders show DOCUMENT_ID
python tools/order_review.py --data-dir /private/orders review DOCUMENT_ID ROW_ID confirm --version 0 --user Reviewer --checked --note "Verified on the source page."
python tools/order_review.py --data-dir /private/orders review DOCUMENT_ID OTHER_ID clarify --version 0 --user Reviewer --question "Which criterion applies?" --respondent "Design"
python tools/order_review.py --data-dir /private/orders review DOCUMENT_ID NOISE_ID exclude --version 0 --user Reviewer --note "Archive instruction."
python tools/order_review.py --data-dir /private/orders export QA-DEMO /private/exports
```

替换上例文档、条目编号与当前行版本。`review ... edit --changes '{"condition":"..."}' --note "..."` 保存修订。CLI 可通过 `--config /private/config.yaml` 独立设置可选 OCR 槽与视觉抽取槽，通过 `import ... --vision-pages 4,6-8` 限定页码。可选 Tesseract 使用本机已有的可执行文件，桌面版默认使用本地规则与可选 API。[配置样例](order-review.example.yaml)

## 从源码构建 Windows ZIP

构建机使用 CPython 3.12。Linux 需要 msitools 的 `msiextract`，Windows 使用系统的 MSI 管理提取功能。以下命令校验固定来源及 SHA-256，组装完整运行时并检查 ZIP 大小与完整性。依赖缓存和发布物写入已忽略的 `work/`。

```sh
python tools/build_orders_portable.py
```

Linux 桌面实测、合成验收结果与目标机复核范围见[本轮验证报告](order-desktop-validation.md)。此前对提取通道与匿名私有样本的核查见[首期验证记录](order-review-validation.md)。
