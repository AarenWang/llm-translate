# IPYNB 翻译实现设计

## 1. 目标

在当前 Markdown 翻译闭环基础上，新增 Jupyter Notebook (`.ipynb`) 输入与输出能力。

首版目标不是把 Notebook 当成普通 Markdown 拼接后翻译，而是保留 Notebook 的 JSON 结构，只翻译安全范围内的自然语言内容，并将译文回写为新的 `.ipynb` 文件。

P0 交付能力：

1. 支持导入 `.ipynb` 文件。
2. 解析 Notebook cell 结构。
3. 默认只翻译 `markdown` cell。
4. 默认完整保留 `code` cell、outputs、execution_count、metadata、attachments。
5. 支持 chunk 级状态、失败续跑、校验和导出。
6. 导出翻译后的 `.ipynb`。
7. 同时导出 Markdown 译文和原文/译文对照 Markdown，便于审校。

非目标：

1. P0 不翻译 code cell 中的代码、字符串、注释和 docstring。
2. P0 不重排 cell，不执行 Notebook，不清理 outputs。
3. P0 不对图片 OCR，也不翻译 base64 附件内容。
4. P0 不保证复杂 HTML output 内文翻译。

## 2. 关键设计原则

1. Notebook 结构由系统管理，LLM 只处理 markdown cell 的自然语言。
2. cell 是 P0 的最小翻译与回写单位，避免模型输出后难以拆回多个 cell。
3. code cell、output、metadata、attachments 默认不可翻译。
4. 导出时以原始 Notebook JSON 为模板，只替换已完成 markdown cell 的 `source`。
5. 任何结构校验失败都不能生成正式 `.ipynb`，只能生成 draft。

## 3. IPYNB 文件结构要点

Notebook 是 JSON 文档，核心结构如下：

```json
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": ["# Title\n", "Some text"]
    },
    {
      "cell_type": "code",
      "execution_count": 1,
      "metadata": {},
      "outputs": [],
      "source": ["print('hello')"]
    }
  ],
  "metadata": {},
  "nbformat": 4,
  "nbformat_minor": 5
}
```

实现时需要注意：

1. `source` 可能是字符串，也可能是字符串数组。
2. `attachments` 可能出现在 markdown cell 中，需要原样保留。
3. cell 可能有 `id` 字段，也可能没有。
4. code cell 的 `outputs` 可能包含大量 JSON、HTML、图片 base64，不能交给模型。
5. Notebook 顶层 metadata 需要原样保留。

## 4. 模块改造方案

### 4.1 Parser Adapter

新增文件：

```text
llm_translate/parser/ipynb.py
```

新增类：

```python
class IpynbParser:
    def parse(self, project_id: str, notebook_json: dict) -> list[DocumentBlock]:
        ...
```

P0 解析策略：

1. 遍历 `cells`。
2. markdown cell 生成一个可翻译 `DocumentBlock`。
3. code/raw cell 生成不可翻译 block 或只存入 snapshot，不进入 translation chunk。
4. markdown cell 的 `source` 统一 normalize 为字符串。
5. 记录足够回写的信息到 `metadata`。

建议的 `DocumentBlock.metadata`：

```json
{
  "format": "ipynb",
  "cell_index": 3,
  "cell_id": "optional-existing-cell-id",
  "cell_type": "markdown",
  "source_kind": "list",
  "source_line_count": 8,
  "attachments_present": true,
  "heading_level": 2,
  "heading_text": "Background"
}
```

`source_kind` 用于尽量保持原始 `source` 形态：

1. 原来是字符串，导出时写回字符串。
2. 原来是数组，导出时可写回数组，按换行拆分并保留换行符。

### 4.2 Project Source Snapshot

当前项目目录已经有：

```text
.llm_translate/projects/{project_id}/source/original.xxx
.llm_translate/projects/{project_id}/snapshots/
```

IPYNB 需要额外保存：

```text
snapshots/notebook.original.json
snapshots/notebook.cells.json
```

用途：

1. `notebook.original.json` 作为导出回写模板。
2. `notebook.cells.json` 保存 cell 索引、类型、id、是否可翻译等摘要。
3. 失败续跑时不重新解析原始文件即可恢复上下文。

### 4.3 Chunking

P0 推荐策略：一个 markdown cell 对应一个 chunk。

原因：

1. 回写简单，模型输出直接写回对应 cell。
2. 失败定位清楚，用户可以看到哪个 cell 失败。
3. 避免多个 cell 合并翻译后无法可靠拆分。

chunk metadata 可通过 block metadata 间接获得：

```json
{
  "block_ids": ["prj_xxx_b_000012"],
  "chapter_id": "nearest-heading-block-id",
  "source_text": "markdown cell source"
}
```

后续 P1 可优化为“小 markdown cell 批量 chunk”，但需要引入不可翻译的 cell boundary placeholder，例如：

```text
__LT_CELL_BOUNDARY_000001__
```

P0 不做批量合并，优先保证正确性。

### 4.4 Protection Engine

Notebook markdown cell 内仍然使用当前 Markdown 保护规则：

1. code fence
2. inline code
3. URL
4. Markdown link target
5. image path
6. reference id
7. file path
8. API path

额外规则：

1. markdown cell `attachments` 不进入 `source_text`，只在导出模板中保留。
2. embedded HTML 中的属性值，例如 `<img src="...">`，至少保护 URL 与路径。
3. badge/image HTML 建议 P0 作为整段 HTML 标签保护，避免模型破坏标签。

可新增 span 类型：

```text
HTML_TAG
IPYNB_ATTACHMENT_REF
```

其中 `HTML_TAG` 的 P0 策略可以保守一些：整段标签不翻译。

### 4.5 Prompt Builder

Prompt 可复用当前结构，但需要加入 Notebook 场景说明：

```text
当前内容来自 Jupyter Notebook 的 markdown cell。
只翻译自然语言文本。
不要增加或删除 Markdown 结构。
不要翻译或改写占位符、代码、URL、图片路径、HTML 标签属性。
输出只包含该 cell 的译文 Markdown。
```

如果 cell 标题层级可识别，将 chapter path 注入 prompt：

```text
Notebook / Section / Subsection
```

### 4.6 LLM Provider

无需为 IPYNB 单独新增 provider。

继续使用当前统一 LLM adapter：

```text
MockLLMProvider
DeepSeekProvider
LiteLLMProvider
```

但建议给 Notebook 翻译增加更严格的重试条件：

1. 空输出重试。
2. placeholder 缺失重试。
3. HTML 标签破坏重试。
4. Markdown code fence 奇数重试。

### 4.7 Validation

新增 Notebook 项目级校验：

1. cell 数量不变。
2. cell 顺序不变。
3. 每个 cell 的 `cell_type` 不变。
4. code cell 的 `source` 不变。
5. code cell 的 `outputs` 不变。
6. code cell 的 `execution_count` 不变。
7. metadata 不变。
8. attachments 不变。
9. markdown cell 中的占位符全部恢复。
10. 导出的 `.ipynb` 可被 JSON 解析。
11. `nbformat` / `nbformat_minor` 不变。

新增 chunk 级校验：

1. placeholder 集合一致。
2. 输出非空。
3. Markdown fence 成对。
4. HTML 标签基础有效。
5. 链接和图片目标不变。
6. 术语一致。

新增 report 类型：

```text
NOTEBOOK_STRUCTURE
NOTEBOOK_CELL_INTEGRITY
```

### 4.8 Exporter

新增文件：

```text
llm_translate/exporter_ipynb.py
```

或在现有 exporter 中新增：

```python
class IpynbExporter:
    def export_ipynb(project, original_notebook, blocks, chunks) -> Path:
        ...
```

导出产物：

```text
artifacts/translated.ipynb
artifacts/translated.draft.ipynb
artifacts/translated.md
artifacts/bilingual.md
artifacts/translation-log.json
artifacts/validation-report.json
artifacts/validation-report.md
```

正式导出条件：

1. 所有可翻译 markdown cell 对应 chunk 均为 `DONE`。
2. Notebook 结构校验通过。
3. JSON 序列化成功。

draft 导出规则：

1. 已完成 markdown cell 写入译文。
2. 未完成 markdown cell 保留原文，并追加标记注释。
3. code/output/metadata 仍然不变。

draft cell 标记示例：

```markdown
<!-- TRANSLATION_PENDING: prj_xxx_c_000003 -->

Original content...
```

### 4.9 CLI 改造

当前命令：

```powershell
python -m llm_translate.cli run input.md --name demo
```

支持 `.ipynb` 后保持命令不变：

```powershell
python -m llm_translate.cli run notebook.ipynb --name notebook-zh
```

需要改造 `_input_format`：

```python
if suffix == ".ipynb":
    return "ipynb"
```

可新增选项：

```text
--translate-code-comments
```

P0 默认不启用。

### 4.10 Storage / Domain

现有表结构基本可复用。

需要最小调整：

1. `translation_project.input_format` 支持 `ipynb`。
2. `document_block.block_type` 增加：
   - `notebook_markdown_cell`
   - `notebook_code_cell`
   - `notebook_raw_cell`
3. `document_block.metadata` 记录 cell 回写信息。
4. `export_artifact` 表目前还未实现，后续可补，用于记录 `translated.ipynb`。

P0 不需要新增专门的 notebook 表。

如果后续要做更复杂的 Notebook 审校 UI，可新增：

```text
notebook_cell
```

字段：

```text
id
project_id
cell_index
cell_id
cell_type
source_hash
metadata_hash
outputs_hash
translatable
block_id
```

但 P0 暂不需要。

## 5. 实施步骤

### M1: 解析与快照

1. 新增 `IpynbParser`。
2. 增加 `.ipynb` input format 识别。
3. 创建项目时保存原始 `.ipynb`。
4. parse 阶段读取 JSON，生成 blocks。
5. 保存 `snapshots/notebook.original.json` 和 `snapshots/notebook.cells.json`。
6. 增加 parser 单元测试。

验收：

1. 能解析 markdown/code/raw cell。
2. markdown cell 生成可翻译 block。
3. code cell 不进入待翻译 chunk。
4. cell index、cell id、source kind 记录完整。

### M2: Chunk 与翻译

1. chunker 针对 `ipynb` 采用 one markdown cell per chunk。
2. prompt 加 Notebook 场景说明。
3. runner 支持 ipynb 项目。
4. 失败续跑仍按 PENDING / FAILED chunk 执行。

验收：

1. 每个 markdown cell 一个 chunk。
2. code cell 不调用 LLM。
3. DeepSeek/mock provider 均可运行。

### M3: 导出 translated.ipynb

1. 新增 `IpynbExporter`。
2. 读取原始 notebook JSON。
3. 将 DONE chunk 的 `restored_text` 写回对应 markdown cell。
4. 保留 code/output/metadata/attachments。
5. 生成 `translated.ipynb` 或 `translated.draft.ipynb`。

验收：

1. 输出 `.ipynb` 可被 JSON 解析。
2. cell 数量和顺序不变。
3. code cell 完全不变。
4. markdown cell 已被替换为译文。

### M4: 校验与报告

1. 新增 Notebook 结构校验。
2. 报告中展示 markdown/code/raw cell 数量。
3. 报告中展示失败 cell index。
4. 对 HTML 标签和附件引用增加基础校验。

验收：

1. 结构破坏会阻止正式导出。
2. code cell 变化会被检测到。
3. attachments 变化会被检测到。

## 6. 测试计划

### 6.1 Fixtures

新增：

```text
fixtures/sample.ipynb
fixtures/sample-with-attachments.ipynb
fixtures/sample-with-html.ipynb
```

sample 内容应覆盖：

1. markdown 标题。
2. 普通 markdown 段落。
3. markdown 列表。
4. markdown 表格。
5. markdown link。
6. markdown image。
7. HTML badge 或 `<img>`。
8. code cell。
9. code outputs。
10. notebook metadata。

### 6.2 单元测试

1. `IpynbParser` 解析 cell。
2. source list/string normalize。
3. markdown cell chunk 生成。
4. code cell 不生成 chunk。
5. exporter 保持 code cell 不变。
6. exporter 保持 outputs 不变。
7. notebook structure validator。

### 6.3 集成测试

1. mock provider 端到端翻译 `.ipynb`。
2. 模拟一个 chunk 失败后续跑。
3. 模拟 placeholder 缺失。
4. 导出 translated.ipynb 后重新 JSON parse。
5. 对比原始与导出 notebook 的 code cell hash。

## 7. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 多个 markdown cell 合并后无法可靠拆回 | 回写错误 | P0 一个 markdown cell 一个 chunk |
| 模型破坏 HTML 标签 | Notebook 渲染异常 | P0 对 HTML 标签整体保护 |
| source list/string 形态变化 | diff 噪音 | metadata 记录 source_kind，导出尽量保持 |
| outputs 很大 | DB 或 prompt 膨胀 | outputs 不进入 block/chunk，只留在原始 JSON 模板 |
| attachments base64 很大 | 性能/存储压力 | 不复制进 block metadata，只在原始 JSON 中保留 |
| markdown cell 很长 | 单 chunk 过大 | P1 支持 cell 内子块切分，P0 先报 NEED_REVIEW 或二次拆分 |
| code 注释也想翻译 | 可能破坏代码 | P1 通过显式参数启用，并用 AST/注释提取策略 |

## 8. P1 扩展方向

1. markdown cell 内按 Markdown AST 子块切分。
2. 小 markdown cell 批量 chunk，并通过 cell boundary placeholder 拆回。
3. 可选翻译 code cell 注释和 docstring。
4. 支持输出双语 Notebook：
   - markdown cell 下方追加译文 cell。
   - 或原文/译文折叠显示。
5. 支持清理或保留 outputs 的导出选项。
6. 支持 Notebook 审校 UI，按 cell 展示原文、译文、状态和错误。

## 9. 建议的首版接口行为

命令：

```powershell
python -m llm_translate.cli run "D:\path\notebook.ipynb" --name notebook-zh
```

输出：

```text
.llm_translate/projects/{project_id}/artifacts/translated.ipynb
.llm_translate/projects/{project_id}/artifacts/bilingual.md
.llm_translate/projects/{project_id}/artifacts/translation-log.json
.llm_translate/projects/{project_id}/artifacts/validation-report.md
```

默认行为：

1. 翻译 markdown cell。
2. 跳过 code/raw cell。
3. 保留 outputs。
4. 保留 metadata。
5. 保留 attachments。

## 10. 最小代码改动清单

```text
llm_translate/parser/ipynb.py          新增 IPYNB parser
llm_translate/service.py              parse/prepare/export 分支支持 ipynb
llm_translate/chunking.py             ipynb one-cell-per-chunk 策略
llm_translate/exporter.py             或新增 exporter_ipynb.py
llm_translate/validation.py           Notebook 结构校验
llm_translate/cli.py                  .ipynb input format 支持
tests/test_ipynb_pipeline.py          新增端到端测试
fixtures/sample.ipynb                 新增测试 fixture
```

推荐先实现 P0，不急于翻译 code 注释。Notebook 的价值在于结构和可执行性，首版最重要的是“翻译后仍然是一个安全可打开、代码未被污染的 Notebook”。
