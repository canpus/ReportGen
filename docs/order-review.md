# 订单规格书审校台

质量工程师可以导入一单英文 PDF，逐项查看依据、确认要求、记录澄清问题，并为实验室导出空白 Excel。原有出厂报告程序仍从原入口启动。

## 启动

在含有 `tools/` 的 ReportGen 源码目录使用 Python 3.12。Windows PowerShell 命令如下。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-orders.txt
.\.venv\Scripts\python.exe tools/order_review.py serve --open
```

Linux 下使用同一组入口。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-orders.txt
.venv/bin/python tools/order_review.py serve --open
```

浏览器打开终端显示的本机地址。默认端口由系统分配。关闭终端或按 Ctrl+C 停止服务，订单和审校进度保存在本机。默认目录在 Windows 为 `%LOCALAPPDATA%\ReportGen\orders`，Linux 为 `${XDG_DATA_HOME:-~/.local/share}/ReportGen/orders`。可在子命令前加 `--data-dir 私有目录`。关闭服务后备份整个目录即可同时保留原件、数据库和版本记录。导出目录也应放在私有位置。

纯扫描页需要本机 Tesseract 及英语语言包，可用 `tesseract --list-langs` 检查是否有 `eng`。没有可用 OCR 或页面未识别到文本时，审校台会列出需人工核查的页。可以在图上框选、转录并确认，或登记 TQ。原生文本页直接提取。普通使用和本任务的私有评测均可完全离线。

## 审校一份订单

1. 点击「导入 PDF」，填写订单号、文号和版次。系统按原件计算 SHA-256，保留物理页、归一化坐标、文本和图像来源。相同订单双次导入同一文号、版次和字节内容会返回原记录。同文副本利用逐页渲染和文字签名识别。订单、版次或人工指定的对照版本不同，审校决定分别保存。
2. 「只读对照版本」默认采用文内明确的版本。合同另行指定 ISO 21809-3:2016 时，工程师可在导入时选定。对照结果保留版本来源、适用型别和表号。源文没有给出型别或有多个可用解释时，应核实适用范围。正式订单只读客户字段，基准出现在「引用与标准对照」中。
3. 右侧切换「条款」或「频次矩阵」。可按状态、部件、工况、PQT、PPT 或 Production 筛选。点击一行，左侧显示 180 DPI 原页和证据框。页码从 PDF 文件的第一页计为 1。点击页码或引用可以检查续页、脚注、方法来源。OCR 的上标、根号、比较符和横线尤其需要对照图像。
4. 「结构化字段与原位修订」可修改工程师对原件的解读。填写审核人和修订说明后点「保存修订」，再核对并确认。客户英文原文和几何证据独立保留，审计记录可展开查看初值、修改值、审核人及时间。同一行被另一浏览器修改后，重新选择文档以载入新版本。
5. 需要客户解释的项目点「登记待澄清」，填写问题及待答方。数值角色区分典型值、试验条件、合格限值及待定占位。红色告警或待核对的高风险符号必须有原页复核说明与明确确认，或转为 TQ。纯典型值没有合格限值。`By Agreement` 和横线在各阶段各自保留。
6. 发现漏项时点击「补录条款」，在左侧原页拖选矩形，按图转录英文。对识别失败的页面，确认所有补录项后再对整页做复核记录。如果整页没有检测要求，可勾选整页核查声明并写明依据。可随时翻页核查没有候选行的页面。
7. 点「导出订单」下载 ZIP。一个订单可登记多份文档，同一文号最近导入的版本用于当前导出。每次审校改变后的首次导出生成新的确认版；同一状态重复导出复用同一快照。普通待核对项目不会进入确认清单，导出摘要会显示遗漏的待核对项数。有未处理的 RED 或符号复核项时会显示阻断条目编号。

## 导出内容

| 文件 | 质量部和实验室可查看的内容 |
| --- | --- |
| `confirmed.json` | 已确认条款、各工况的三阶段频次、TQ、物理页与片段坐标、来源层级、文件哈希、确认版及审计历史 |
| `confirmed.xlsx` | 确认表、频次矩阵、TQ、证据、引用、文档索引及审计工作表。页码链接到证据行 |
| `laboratory.xlsx` | `Laboratory`、`Field inspection` 和 `Clarifications` 三张表。按部件、工况和阶段排列。客户原文锁定，条件与判据分列，待澄清和仅供参考项有明确标识 |

实验室填写浅黄色的 `Actual Test Result`、`Test Specimen/Date` 和 `Lab Judgement`。导出时这三列为空。两份 Excel 放在同一目录可跟随模板中的证据链接。工作表保护用于防止误编辑。

## 生成公开合成样例

运行 `python tests/orders/synthetic.py work/synthetic-fixtures` 会生成四份虚构 PDF。用 `workflow.pdf` 可练习两项确认和一项待澄清，用 `matrix.pdf` 可查看两个工况的三阶段频次。混合扫描样例在测试中有确定性 OCR 桩，界面使用本机配置的 OCR。

## CLI

以下在有订单依赖的 Python 环境运行。示例标识均为虚构。导入返回的文档 ID 和 `show` 返回的行 ID、版本用于审核。输出包含订单内容，请将终端输出保存在私有位置。

```sh
python tools/order_review.py --data-dir /private/orders import synthetic.pdf --order QA-DEMO --number SYN-1 --revision A
python tools/order_review.py --data-dir /private/orders list
python tools/order_review.py --data-dir /private/orders show DOCUMENT_ID
python tools/order_review.py --data-dir /private/orders review DOCUMENT_ID ROW_ID confirm --user Reviewer --version 0 --checked --note "Verified on the original page."
python tools/order_review.py --data-dir /private/orders review DOCUMENT_ID OTHER_ROW_ID clarify --version 0 --user Reviewer --question "Which limit applies?" --respondent "Document author"
python tools/order_review.py --data-dir /private/orders export QA-DEMO /private/exports
```

`review ... edit --changes '{"condition":"..."}' --note "..."` 保存结构化字段修订。成功后版本递增。CLI 非零退出码和网页状态消息会说明导入、并发保存或导出失败的原因。无秘密的解析配置见 [配置样例](order-review.example.yaml)。

## 可选解析器

将样例复制为仓库外的 `config.yaml`，用 `python tools/order_review.py --config /private/config.yaml serve --open` 启动。OCR 槽和结构化提取槽可各自指定本地规则或 OpenAI 兼容的视觉模型。OCR 接受逐词文本和归一化坐标，结构化提取只接受源片段 ID，并核对行、页和字段。接口采用 `/chat/completions`、图像输入、JSON 响应和温度 0。

默认关闭对外页图传输。配置本机模型可用回环地址。只有在有权传输该资料时才为外部 HTTPS 服务显式设置 `allow_external_pages: true`；届时被选页面及提取槽使用的文本会发给所配服务。密钥从配置指定的环境变量读取。私有配置、PDF、截图、数据库和导出文件应放在版本控制目录以外。

## 验证与适用范围

本地规则可定位表格和正文，并提示人工复核。复杂合并单元格、识别质量差的单位、公式和隐含引用仍需要核对原页。新版本或未收录的标准类型需要独立确认。读出的客户英文、工程师修订值和标准参考分别存储。Windows 目标机、外部模型及私有评测的实测范围见 [验证报告](order-review-validation.md)。
