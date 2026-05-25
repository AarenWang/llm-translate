# 长文档翻译工作流 V1.0 PRD

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 产品名称 | 长文档结构化翻译工作流 |
| 版本 | V1.0 |
| 文档类型 | PRD / Product Requirements Document |
| 目标用户 | 有长文档翻译需求的个人、团队、技术作者、译者、知识库维护者 |
| 核心目标 | 支持一本较长电子文档的可控、可恢复、一致性翻译 |
| 重点格式 | Markdown、TXT、DOCX，V1.0 优先 Markdown |
| 输出格式 | Markdown 译文版、原文译文对照版，后续扩展 DOCX / EPUB / PDF |

---

## 2. 背景与问题

用户希望翻译一本较长的电子文档，但普通大模型翻译存在明显问题：

1. 文档很长，一次无法放入模型上下文。
2. 翻译后容易丢失原始章节目录结构。
3. 术语、专有名词前后不统一。
4. 风格容易漂移，例如前半部分活泼，后半部分严肃。
5. 翻译过程不可控，失败后难以从失败位置继续。
6. 代码、引用、URL、参考文献、文件路径等不应翻译的内容容易被模型误翻。
7. 翻译完成后缺少自动校验机制，难以及时发现漏翻、格式破坏、术语错误等问题。

因此，本产品不是简单的“调用一次 LLM 翻译文档”，而是构建一套面向长文档的结构化翻译流水线。

核心原则：

> 模型只负责翻译自然语言文本；系统负责结构管理、切片管理、术语管理、风格管理、状态管理、不可翻译内容保护、质量校验与导出组装。

---

## 3. 产品目标

### 3.1 V1.0 目标

V1.0 需要完成一套可运行的长文档翻译 MVP，具备以下能力：

1. 支持上传或导入长文档。
2. 支持解析文档章节结构。
3. 支持按章节、段落进行结构化切片。
4. 支持用户指定术语表。
5. 支持统一翻译风格指南。
6. 支持不可翻译内容识别、占位符保护和恢复。
7. 支持分 chunk 翻译。
8. 支持翻译状态持久化。
9. 支持失败续跑。
10. 支持基础质量校验。
11. 支持导出译文版和原文译文对照版。

### 3.2 V1.0 不解决的问题

V1.0 暂不重点解决以下复杂场景：

1. 复杂 PDF 版面还原。
2. 图片 OCR 翻译。
3. EPUB 重新打包。
4. DOCX 高保真样式还原。
5. 多人协同审校。
6. 专业 CAT 工具级别的翻译记忆库。
7. 全自动学术级人工质量审校。
8. 跨模型质量对比。
9. 实时在线编辑器。

这些能力可作为 V1.1 / V2.0 方向。

---

## 4. 用户画像

### 4.1 技术文档翻译用户

这类用户需要翻译技术文档、开源项目文档、开发手册、论文解读材料等。

核心诉求：

- 代码不要被翻译。
- API、字段名、命令行、配置项不要被破坏。
- 技术术语保持一致。
- Markdown 结构保持稳定。
- 支持失败后继续翻译。

### 4.2 知识库维护者

这类用户需要把英文资料翻译成中文知识库。

核心诉求：

- 目录结构不能乱。
- 链接、引用、图片路径不能丢。
- 输出格式方便二次发布。
- 支持增量重翻。

### 4.3 译者或内容团队

这类用户更关注风格一致性和审校效率。

核心诉求：

- 可指定翻译风格。
- 可指定术语表。
- 可查看原文译文对照版。
- 可发现低质量 chunk。

---

## 5. 核心使用场景

### 5.1 场景一：翻译一本 Markdown 技术文档

用户上传一本 Markdown 文档，系统自动识别标题层级，按章节和段落切分，保护代码块、行内代码、URL、命令行、API 路径等内容，然后逐段翻译，最终导出完整 Markdown 译文。

### 5.2 场景二：用户指定术语翻译

用户上传术语表，例如：

| 原文 | 译文 |
|---|---|
| Agent | 智能体 |
| Context Engineering | 上下文工程 |
| Tool Call | 工具调用 |
| Translation Memory | 翻译记忆库 |

系统翻译时必须遵守术语表，翻译后校验是否出现不一致译法。

### 5.3 场景三：翻译失败后从失败位置继续

系统翻译到第三章时由于模型调用失败、网络错误或输出格式错误导致中断。用户下次继续执行时，系统只翻译未完成或失败的 chunk，不重复翻译已经完成的内容。

### 5.4 场景四：保护代码和引用内容

文档中包含代码块、命令行、参考文献和 URL，系统在翻译前将其替换为占位符，翻译后恢复，避免模型误翻或破坏格式。

### 5.5 场景五：导出对照版用于人工审校

翻译完成后，用户导出原文译文对照版，用于检查漏翻、错译、术语不一致和风格问题。

---

## 6. 产品范围

### 6.1 输入范围

V1.0 支持：

| 输入格式 | 支持优先级 | 说明 |
|---|---:|---|
| Markdown | P0 | V1.0 首选格式 |
| TXT | P1 | 结构弱，需要基础章节识别 |
| DOCX | P1 | 支持基础段落和标题解析 |
| HTML | P2 | 可后续扩展 |
| EPUB | P2 | 可后续扩展 |
| PDF | P3 | V1.0 暂不重点支持 |

### 6.2 输出范围

V1.0 支持：

| 输出格式 | 优先级 | 说明 |
|---|---:|---|
| Markdown 纯译文版 | P0 | 用于发布或二次编辑 |
| Markdown 原文译文对照版 | P0 | 用于审校 |
| 翻译日志 JSON | P1 | 用于排查问题 |
| 术语校验报告 | P1 | 用于检查术语一致性 |
| 质量校验报告 | P1 | 用于检查结构、占位符和格式 |

---

## 7. 整体业务流程

```text
1. 创建翻译项目
2. 上传或导入源文档
3. 解析文档结构
4. 生成内部 Document AST
5. 识别章节、标题、段落、表格、代码块、引用、链接等结构
6. 识别不可翻译内容
7. 生成保护占位符
8. 按章节和段落进行 chunk 切分
9. 用户配置目标语言、术语表、风格指南和保护规则
10. 可选：生成样章
11. 用户确认样章风格和术语
12. 批量翻译 chunk
13. 每个 chunk 保存翻译状态
14. 翻译后执行校验
15. 失败 chunk 自动重试或进入人工处理
16. 所有 chunk 完成后重新组装文档
17. 导出译文版和对照版
18. 生成翻译日志和质量报告
```

---

## 8. 功能需求

## 8.1 翻译项目管理

### 8.1.1 创建项目

用户可以创建一个翻译项目。

创建项目时需要填写：

| 字段 | 必填 | 说明 |
|---|---:|---|
| 项目名称 | 是 | 例如：GraphRAG 文档翻译 |
| 源语言 | 否 | 默认自动检测 |
| 目标语言 | 是 | V1.0 默认简体中文 |
| 输入格式 | 是 | Markdown / TXT / DOCX |
| 翻译风格 | 是 | 可选择或自定义 |
| 术语表 | 否 | 可上传或手工录入 |
| 不可翻译规则 | 否 | 默认启用系统规则 |

### 8.1.2 项目状态

项目状态包括：

```text
CREATED       已创建
PARSED        已解析
READY         已准备翻译
TRANSLATING   翻译中
PAUSED        已暂停
FAILED        翻译失败
VALIDATING    校验中
COMPLETED     翻译完成
EXPORTED      已导出
```

### 8.1.3 项目操作

V1.0 需要支持：

| 操作 | 说明 |
|---|---|
| 上传源文档 | 上传 Markdown / TXT / DOCX |
| 重新解析 | 源文档变化后重新解析 |
| 开始翻译 | 从 PENDING / FAILED chunk 开始 |
| 暂停翻译 | 暂停后保留进度 |
| 继续翻译 | 从未完成位置继续 |
| 重试失败项 | 只重试 FAILED chunk |
| 导出译文 | 输出完整译文 |
| 导出对照版 | 输出原文译文对照版 |

---

## 8.2 文档解析模块

### 8.2.1 目标

将原始电子文档解析成内部结构化文档模型，保留章节、标题、段落、列表、表格、代码块、引用、链接等结构信息。

### 8.2.2 Markdown 解析要求

V1.0 优先支持 Markdown，要求识别：

| 类型 | 示例 | 是否翻译 |
|---|---|---:|
| 标题 | `## Introduction` | 是 |
| 段落 | 普通文本 | 是 |
| 列表 | `- item` | 是 |
| 引用块 | `> quote` | 是，保留结构 |
| 代码块 | 三反引号代码块 | 否 |
| 行内代码 | \`user_id\` | 否 |
| 链接文本 | `[Docs](url)` | 可翻译 |
| 链接地址 | `https://...` | 否 |
| 图片 alt | `![Architecture](path)` | 可翻译 |
| 图片路径 | `./image.png` | 否 |
| 表格 | Markdown table | 部分翻译 |
| 脚注编号 | `[^1]` | 否 |

### 8.2.3 内部 Document AST

系统解析后生成内部结构，例如：

```json
{
  "document_id": "doc_001",
  "title": "Original Title",
  "blocks": [
    {
      "block_id": "b_001",
      "type": "heading",
      "level": 1,
      "source_text": "Introduction",
      "target_text": null
    },
    {
      "block_id": "b_002",
      "type": "paragraph",
      "source_text": "This is a paragraph.",
      "target_text": null
    }
  ]
}
```

### 8.2.4 验收标准

1. Markdown 标题层级可以被正确识别。
2. 代码块不会被误识别为普通段落。
3. 链接地址可以被识别并保护。
4. 图片路径可以被识别并保护。
5. 解析后可恢复原始 Markdown 的基本结构。

---

## 8.3 章节与目录结构管理

### 8.3.1 目标

系统需要保留原始文档的目录结构，翻译后输出文档应保持相同章节层级和顺序。

### 8.3.2 章节识别规则

Markdown 中根据标题级别识别：

```markdown
# Book Title
## Chapter 1
### Section 1.1
```

对应结构：

```text
Document
 ├── Chapter 1
 │    ├── Section 1.1
 │    └── Section 1.2
 └── Chapter 2
```

### 8.3.3 编号处理规则

章节编号不应完全交给模型自由生成。

例如：

```text
Chapter 3. The Bitter Lesson
```

系统应拆分为：

```json
{
  "chapter_number": "Chapter 3",
  "chapter_title": "The Bitter Lesson"
}
```

翻译时只翻译标题正文，导出时由系统组装编号。

### 8.3.4 验收标准

1. 翻译后标题数量与原文一致。
2. 标题层级与原文一致。
3. 标题顺序与原文一致。
4. 不出现章节编号丢失或重复。
5. 对照版中原文标题与译文标题可以一一对应。

---

## 8.4 文档切片 Chunking

### 8.4.1 目标

将长文档拆分为适合模型处理的 chunk，同时尽量保持语义完整。

### 8.4.2 切片原则

切片优先级：

```text
章节 > 小节 > 段落 > 列表项 > 句子
```

V1.0 切片规则：

1. chunk 不跨章节。
2. chunk 不打断代码块。
3. chunk 不打断表格。
4. chunk 不打断 Markdown 列表。
5. chunk 不打断引用块。
6. chunk 尽量以段落为边界。
7. chunk 大小应小于模型上下文限制。

### 8.4.3 Chunk 数据结构

```json
{
  "chunk_id": "ch_003_sec_002_chunk_004",
  "project_id": "project_001",
  "chapter_id": "ch_003",
  "block_ids": ["b_031", "b_032", "b_033"],
  "source_text": "...",
  "protected_text": "...",
  "target_text": null,
  "status": "PENDING",
  "retry_count": 0
}
```

### 8.4.4 验收标准

1. 每个 chunk 有唯一 ID。
2. 每个 chunk 可以追溯到原始 block。
3. chunk 不破坏 Markdown 代码块。
4. chunk 不破坏表格。
5. chunk 翻译失败后可以单独重试。

---

## 8.5 术语表管理

### 8.5.1 目标

系统需要支持用户指定术语翻译，并在翻译过程中保证术语一致。

### 8.5.2 术语表字段

| 字段 | 说明 |
|---|---|
| source_term | 原文术语 |
| target_term | 目标译文 |
| case_sensitive | 是否大小写敏感 |
| match_type | 精确匹配 / 模糊匹配 |
| priority | 优先级 |
| note | 备注 |

示例：

```json
{
  "source_term": "Agent",
  "target_term": "智能体",
  "case_sensitive": true,
  "match_type": "exact",
  "priority": 100,
  "note": "AI Agent 场景下使用智能体，不翻译为代理"
}
```

### 8.5.3 术语来源

V1.0 支持：

1. 用户手工录入。
2. CSV / JSON 上传。
3. 系统从文档中自动抽取候选术语，供用户确认。

### 8.5.4 术语优先级

```text
用户锁定术语 > 项目术语表 > 系统候选术语 > 模型默认翻译
```

### 8.5.5 验收标准

1. 用户可以新增、编辑、删除术语。
2. 翻译 Prompt 中会注入当前 chunk 相关术语。
3. 翻译后能检查术语是否被正确使用。
4. 发现术语不一致时，对应 chunk 标记为 NEED_REVIEW 或 FAILED。

---

## 8.6 风格指南管理

### 8.6.1 目标

保证长文档翻译风格前后一致。

### 8.6.2 风格配置项

| 字段 | 说明 |
|---|---|
| target_language | 目标语言，例如 zh-CN |
| tone | 语气，例如专业、清晰、克制 |
| audience | 目标读者 |
| sentence_style | 句式要求 |
| terminology_policy | 术语策略 |
| formatting_policy | 格式策略 |
| forbidden_rules | 禁止事项 |

示例：

```yaml
target_language: zh-CN
tone: 专业、清晰、克制、有解释性
audience: 有技术背景的中文读者
sentence_style:
  - 避免过度口语化
  - 避免网络流行语
  - 长句可以适度拆分
terminology_policy:
  - 技术术语必须遵守术语表
  - 专有名词首次出现可保留英文括号
formatting_policy:
  - 保留 Markdown 结构
  - 保留列表结构
  - 保留表格结构
forbidden_rules:
  - 不要随意增加原文没有的观点
  - 不要把解释性翻译扩展成评论
```

### 8.6.3 Prompt 注入策略

V1.0 不需要每次注入完整风格指南，可以注入压缩版：

```text
翻译风格：简体中文；专业、清晰、克制；面向技术读者；保留原文结构；技术术语按术语表；不要口语化、不要文学化、不要自行扩写。
```

### 8.6.4 验收标准

1. 用户可以选择或自定义风格指南。
2. 每次翻译 chunk 时都能关联风格指南版本。
3. 翻译日志中记录使用的风格指南版本。
4. 风格指南变更后，可识别受影响 chunk。

---

## 8.7 不可翻译内容保护

### 8.7.1 目标

系统需要识别并保护不应该被翻译的内容，避免模型误翻或破坏格式。

### 8.7.2 不可翻译内容类型

V1.0 默认保护：

| 类型 | 示例 | 处理策略 |
|---|---|---|
| 代码块 | Java / Python / SQL | 整体保护 |
| 行内代码 | `user_id` | 整体保护 |
| URL | `https://example.com` | 整体保护 |
| 文件路径 | `/etc/nginx/nginx.conf` | 整体保护 |
| 命令行 | `docker compose up -d` | 整体保护 |
| API 路径 | `POST /api/v1/orders` | 整体保护 |
| JSON/YAML key | `server.port` | 默认保护 |
| 数据库表名 | `payment_order` | 默认保护 |
| 字段名 | `created_at` | 默认保护 |
| 数学公式 | `E = mc^2` | 整体保护 |
| 引用编号 | `[12]`, `[^1]` | 整体保护 |
| 参考文献条目 | APA / IEEE 格式 | 默认整条保护 |
| 图片路径 | `./images/arch.png` | 保护路径 |
| Markdown 语法 | `##`, `**` | 保留结构 |

### 8.7.3 Markdown 链接处理

原文：

```markdown
See [OpenAI documentation](https://platform.openai.com/docs).
```

处理策略：

```text
链接文本：可翻译
链接地址：不可翻译
Markdown 结构：必须保留
```

译文示例：

```markdown
请参阅 [OpenAI 文档](https://platform.openai.com/docs)。
```

### 8.7.4 图片处理

原文：

```markdown
![System Architecture](./images/architecture.png)
```

处理策略：

```text
alt text：可翻译
图片路径：不可翻译
```

译文示例：

```markdown
![系统架构](./images/architecture.png)
```

### 8.7.5 参考文献处理

参考文献列表默认不翻译。

例如：

```text
[12] Vaswani, A., Shazeer, N., Parmar, N., et al. Attention Is All You Need. NeurIPS, 2017.
```

默认保持原文。

章节标题 `References` 可以翻译为 `参考文献`。

### 8.7.6 占位符保护机制

翻译前将不可翻译内容替换成占位符。

原文：

```markdown
Run `docker compose up -d` and open https://localhost:8080.
```

保护后：

```markdown
Run __INLINE_CODE_001__ and open __URL_001__.
```

翻译后：

```markdown
运行 __INLINE_CODE_001__ 并打开 __URL_001__。
```

恢复后：

```markdown
运行 `docker compose up -d` 并打开 https://localhost:8080。
```

### 8.7.7 占位符规则

占位符格式：

```text
__TYPE_INDEX__
```

示例：

```text
__CODE_BLOCK_001__
__INLINE_CODE_001__
__URL_001__
__REF_001__
__FILE_PATH_001__
__API_PATH_001__
```

### 8.7.8 占位符映射表

```json
{
  "__INLINE_CODE_001__": "`docker compose up -d`",
  "__URL_001__": "https://localhost:8080",
  "__REF_001__": "[12]"
}
```

### 8.7.9 保护规则优先级

```text
用户手工指定规则 > 结构化标签规则 > 术语表规则 > 不可翻译模式规则 > LLM 辅助判断 > 默认自然语言翻译
```

### 8.7.10 验收标准

1. 代码块不会被送入模型翻译。
2. 行内代码不会被翻译。
3. URL 不会被翻译或改写。
4. 图片路径不会被翻译或改写。
5. 引用编号不会被翻译或改写。
6. 参考文献条目默认不翻译。
7. 翻译前后占位符数量一致。
8. 占位符被删除、改写或新增时，系统能检测并报错。

---

## 8.8 翻译执行模块

### 8.8.1 目标

按 chunk 调用 LLM 进行翻译，并保存每个 chunk 的翻译结果和状态。

### 8.8.2 翻译 Prompt 模板

```text
你是一个专业文档翻译引擎。

任务：
将下面的英文内容翻译为简体中文。

翻译要求：
1. 保持原文含义完整，不遗漏，不扩写。
2. 保留 Markdown / 表格 / 列表结构。
3. 专业、清晰、克制，面向技术读者。
4. 术语必须遵守术语表。
5. 所有形如 __CODE_BLOCK_001__、__URL_001__、__REF_001__ 的占位符必须原样保留。
6. 不要翻译占位符。
7. 不要删除占位符。
8. 不要调整占位符顺序。
9. 不要输出解释，不要输出总结，只输出译文。

全书背景：
{{book_summary}}

前文摘要：
{{previous_summary}}

术语表：
{{glossary}}

风格指南：
{{style_guide}}

上一段译文结尾：
{{previous_target_tail}}

待翻译内容：
{{protected_source_text}}
```

### 8.8.3 上下文注入策略

V1.0 支持基础上下文注入：

1. 当前 chunk 原文。
2. 当前 chunk 相关术语。
3. 压缩版风格指南。
4. 上一个 chunk 的译文尾部。
5. 可选：本章摘要。

V1.0 暂不强制实现全书摘要和复杂 RAG 检索。

### 8.8.4 翻译状态

chunk 状态包括：

```text
PENDING        待翻译
PROTECTED      已完成不可翻译内容保护
TRANSLATING    翻译中
TRANSLATED     已翻译，未校验
VALIDATING     校验中
DONE           已完成
FAILED         失败
NEED_REVIEW    需要人工审阅
SKIPPED        跳过
```

### 8.8.5 重试策略

系统支持自动重试：

| 错误类型 | 策略 |
|---|---|
| 模型调用超时 | 自动重试 |
| 网络错误 | 自动重试 |
| 占位符缺失 | 自动重试一次，仍失败则 NEED_REVIEW |
| 输出为空 | 自动重试 |
| Markdown 格式严重损坏 | 标记 NEED_REVIEW |
| 术语不一致 | 标记 NEED_REVIEW 或自动重翻 |

默认最大重试次数：3 次。

### 8.8.6 验收标准

1. 每个 chunk 可独立翻译。
2. 翻译结果持久化保存。
3. 翻译失败不会影响已完成 chunk。
4. 支持从 FAILED / PENDING chunk 继续翻译。
5. 翻译日志记录模型名称、Prompt 版本、术语表版本、风格指南版本。

---

## 8.9 质量校验模块

### 8.9.1 目标

翻译完成后，对译文进行自动校验，发现格式、结构、术语、占位符等问题。

### 8.9.2 校验类型

V1.0 支持以下校验：

| 校验类型 | 说明 |
|---|---|
| 占位符校验 | 检查占位符是否丢失、改写、新增 |
| 结构校验 | 检查标题、列表、表格、代码块结构 |
| 术语校验 | 检查术语表中的译法是否一致 |
| 链接校验 | 检查 URL 是否保持不变 |
| 引用校验 | 检查引用编号是否保持不变 |
| 长度校验 | 检查译文是否异常过短或过长 |
| 空输出校验 | 检查模型是否返回空内容 |

### 8.9.3 占位符校验

检查项：

1. 原始 protected text 中的占位符集合。
2. 模型输出中的占位符集合。
3. 两者是否完全一致。
4. 占位符是否被改写。
5. 占位符是否重复。

示例失败报告：

```json
{
  "chunk_id": "chunk_003",
  "check_type": "PLACEHOLDER_CHECK",
  "status": "FAIL",
  "issues": [
    {
      "type": "MISSING_PLACEHOLDER",
      "placeholder": "__URL_001__"
    }
  ]
}
```

### 8.9.4 结构校验

检查项：

1. Markdown 标题标记是否保留。
2. 代码块围栏是否成对。
3. 表格列数是否一致。
4. 列表结构是否明显破坏。
5. 图片语法是否有效。
6. 链接语法是否有效。

### 8.9.5 术语校验

检查项：

1. 当前 chunk 出现了哪些术语。
2. 对应译文是否符合术语表。
3. 是否出现禁用译法。
4. 是否出现同一术语多个译法。

### 8.9.6 验收标准

1. 校验失败的 chunk 不进入 DONE 状态。
2. 校验失败时能记录失败原因。
3. 用户可以查看失败原因。
4. 用户可以选择重试失败 chunk。
5. 系统可以生成项目级质量报告。

---

## 8.10 失败续跑与状态恢复

### 8.10.1 目标

系统必须支持翻译中断后从失败位置继续，避免重复翻译已完成内容。

### 8.10.2 续跑规则

继续翻译时，系统默认处理以下状态：

```text
PENDING
FAILED
NEED_REVIEW 且用户选择重试
```

默认跳过：

```text
DONE
SKIPPED
```

### 8.10.3 典型场景

翻译到第三章失败：

```text
Chapter 1: DONE
Chapter 2: DONE
Chapter 3: FAILED
Chapter 4: PENDING
```

点击继续后：

```text
从 Chapter 3 的 FAILED chunk 开始继续
Chapter 1 / Chapter 2 不重复翻译
```

### 8.10.4 验收标准

1. 进程退出后，已完成 chunk 不丢失。
2. 系统重启后可以恢复项目状态。
3. 用户可以只重试失败 chunk。
4. 用户可以选择重翻指定章节。
5. 用户可以选择重新导出而不重新翻译。

---

## 8.11 导出模块

### 8.11.1 目标

将翻译完成后的 chunk 按原始文档结构重新组装，生成目标文档。

### 8.11.2 输出类型

V1.0 支持：

1. 纯译文 Markdown。
2. 原文译文对照 Markdown。
3. 翻译日志 JSON。
4. 校验报告 JSON / Markdown。

### 8.11.3 纯译文版

输出示例：

```markdown
# 第一章 引言

这是翻译后的正文。

```java
public class UserService {}
```
```

### 8.11.4 原文译文对照版

输出示例：

```markdown
## 原文

This is the original paragraph.

## 译文

这是原文段落的译文。

---
```

或者表格形式：

| 原文 | 译文 |
|---|---|
| This is the original paragraph. | 这是原文段落的译文。 |

### 8.11.5 验收标准

1. 导出文档章节顺序与原文一致。
2. 导出文档标题层级与原文一致。
3. 代码块、URL、引用编号等已恢复。
4. 对照版可以清晰展示原文和译文。
5. 未完成项目不能导出正式译文，但可以导出当前进度版本。

---

## 9. 页面与交互需求

## 9.1 项目列表页

显示字段：

| 字段 | 说明 |
|---|---|
| 项目名称 | 翻译项目名称 |
| 源文档 | 文件名 |
| 目标语言 | 例如简体中文 |
| 状态 | CREATED / TRANSLATING / COMPLETED |
| 总 chunk 数 | 文档切片数量 |
| 完成进度 | DONE / TOTAL |
| 失败数量 | FAILED 数量 |
| 创建时间 | 项目创建时间 |
| 更新时间 | 最近更新时间 |

支持操作：

1. 查看项目。
2. 继续翻译。
3. 重试失败。
4. 导出译文。
5. 删除项目。

---

## 9.2 项目详情页

展示：

1. 项目基本信息。
2. 文档结构树。
3. 翻译进度。
4. 失败 chunk 列表。
5. 术语表。
6. 风格指南。
7. 不可翻译保护统计。
8. 导出入口。

---

## 9.3 文档结构预览

显示原始文档目录树：

```text
# Title
  ## Chapter 1
    ### Section 1.1
    ### Section 1.2
  ## Chapter 2
```

支持查看每个章节的 chunk 数量和翻译状态。

---

## 9.4 术语表配置页

支持：

1. 手工新增术语。
2. CSV / JSON 导入术语。
3. 编辑术语译法。
4. 删除术语。
5. 锁定术语。
6. 查看术语命中次数。

---

## 9.5 风格指南配置页

支持：

1. 选择预设风格。
2. 自定义风格说明。
3. 查看当前 Prompt 压缩版本。
4. 保存风格指南版本。

---

## 9.6 不可翻译内容预览页

展示系统识别出的受保护内容：

| 类型 | 数量 |
|---|---:|
| 代码块 | 23 |
| 行内代码 | 182 |
| URL | 41 |
| 引用编号 | 96 |
| 文件路径 | 18 |
| API 路径 | 37 |

支持查看明细：

| 类型 | 原文 | 处理策略 |
|---|---|---|
| URL | `https://example.com` | 保留 |
| Code | `docker compose up -d` | 保留 |
| Ref | `[12]` | 保留 |

---

## 9.7 Chunk 审阅页

展示单个 chunk：

1. 原文。
2. 保护后的原文。
3. 译文。
4. 占位符映射。
5. 校验结果。
6. 错误信息。
7. 重试按钮。

---

## 10. 核心数据模型

## 10.1 translation_project

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 项目 ID |
| name | string | 项目名称 |
| source_file_name | string | 源文件名 |
| source_language | string | 源语言 |
| target_language | string | 目标语言 |
| status | string | 项目状态 |
| style_guide_id | string | 风格指南 ID |
| glossary_id | string | 术语表 ID |
| prompt_version | string | Prompt 版本 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

## 10.2 document_block

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | block ID |
| project_id | string | 项目 ID |
| parent_id | string | 父级 block |
| block_order | int | 顺序 |
| block_type | string | heading / paragraph / table / code_block |
| level | int | 标题级别 |
| source_text | text | 原文 |
| target_text | text | 译文 |
| metadata | json | 扩展信息 |

## 10.3 translation_chunk

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | chunk ID |
| project_id | string | 项目 ID |
| chapter_id | string | 章节 ID |
| chunk_order | int | chunk 顺序 |
| block_ids | json | 对应 block ID 列表 |
| source_text | text | 原文 |
| protected_text | text | 替换占位符后的文本 |
| target_text | text | 模型输出译文 |
| restored_text | text | 恢复占位符后的译文 |
| status | string | chunk 状态 |
| retry_count | int | 重试次数 |
| error_message | text | 错误信息 |
| model_name | string | 模型名称 |
| prompt_version | string | Prompt 版本 |
| glossary_version | string | 术语表版本 |
| style_guide_version | string | 风格指南版本 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

## 10.4 protected_span

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 受保护片段 ID |
| project_id | string | 项目 ID |
| chunk_id | string | chunk ID |
| placeholder | string | 占位符 |
| span_type | string | CODE_BLOCK / URL / REF 等 |
| original_text | text | 原始内容 |
| start_offset | int | 起始位置 |
| end_offset | int | 结束位置 |
| strategy | string | 保护策略 |

## 10.5 glossary_term

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 术语 ID |
| project_id | string | 项目 ID |
| source_term | string | 原文术语 |
| target_term | string | 目标译文 |
| case_sensitive | boolean | 是否大小写敏感 |
| match_type | string | exact / fuzzy |
| priority | int | 优先级 |
| note | text | 备注 |

## 10.6 validation_report

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 报告 ID |
| project_id | string | 项目 ID |
| chunk_id | string | chunk ID |
| check_type | string | 校验类型 |
| status | string | PASS / FAIL / WARNING |
| issues | json | 问题列表 |
| created_at | datetime | 创建时间 |

---

## 11. 状态机设计

## 11.1 项目状态机

```text
CREATED
  ↓
PARSED
  ↓
READY
  ↓
TRANSLATING
  ↓        ↘
VALIDATING  FAILED
  ↓          ↓
COMPLETED ← RETRY
  ↓
EXPORTED
```

## 11.2 Chunk 状态机

```text
PENDING
  ↓
PROTECTED
  ↓
TRANSLATING
  ↓
TRANSLATED
  ↓
VALIDATING
  ↓       ↘
DONE      FAILED
           ↓
         RETRY
           ↓
       TRANSLATING
```

特殊状态：

```text
NEED_REVIEW：自动处理失败，需要人工审阅
SKIPPED：用户选择跳过
```

---

## 12. Prompt 版本管理

V1.0 要求记录 Prompt 版本，但不要求复杂的 Prompt 管理平台。

每次翻译 chunk 时记录：

1. `prompt_version`
2. `style_guide_version`
3. `glossary_version`
4. `protection_policy_version`
5. `model_name`

这样后续可以解释为什么不同 chunk 的翻译效果不同。

---

## 13. 错误处理

## 13.1 错误类型

| 错误类型 | 说明 | 处理方式 |
|---|---|---|
| PARSE_ERROR | 文档解析失败 | 项目标记 FAILED |
| CHUNK_ERROR | 切片失败 | 项目标记 FAILED |
| PROTECTION_ERROR | 占位符保护失败 | chunk 标记 FAILED |
| MODEL_TIMEOUT | 模型超时 | 自动重试 |
| MODEL_EMPTY_OUTPUT | 模型返回空 | 自动重试 |
| PLACEHOLDER_MISSING | 占位符缺失 | 自动重试或 NEED_REVIEW |
| FORMAT_BROKEN | 格式破坏 | NEED_REVIEW |
| TERM_INCONSISTENT | 术语不一致 | NEED_REVIEW |
| EXPORT_ERROR | 导出失败 | 项目标记 FAILED |

## 13.2 错误展示

用户需要看到：

1. 哪个章节失败。
2. 哪个 chunk 失败。
3. 失败原因。
4. 是否可以重试。
5. 是否需要人工处理。

---

## 14. 非功能需求

## 14.1 可恢复性

系统必须保证：

1. 每个 chunk 翻译完成后立即持久化。
2. 进程退出不会丢失已完成结果。
3. 系统重启后可以恢复任务。
4. 用户可以从失败位置继续。

## 14.2 可追溯性

系统必须记录：

1. 原文 chunk。
2. 保护后的文本。
3. 模型输出。
4. 恢复后的译文。
5. 使用的术语表版本。
6. 使用的风格指南版本。
7. 使用的 Prompt 版本。
8. 校验结果。

## 14.3 一致性

系统必须保证：

1. 术语一致。
2. 风格尽量一致。
3. 章节结构一致。
4. 不可翻译内容保持一致。

## 14.4 可扩展性

系统设计需要预留：

1. 多输入格式支持。
2. 多输出格式支持。
3. 多模型支持。
4. 翻译记忆库支持。
5. 人工审校工作台。
6. 增量重翻。

---

## 15. V1.0 验收标准

## 15.1 功能验收

V1.0 完成后，应满足：

1. 可以创建一个翻译项目。
2. 可以上传 Markdown 文档。
3. 可以解析标题、段落、代码块、链接、图片、表格。
4. 可以按章节和段落切分 chunk。
5. 可以配置术语表。
6. 可以配置翻译风格。
7. 可以识别并保护代码块、行内代码、URL、引用编号等内容。
8. 可以逐 chunk 调用模型翻译。
9. 可以保存每个 chunk 的状态。
10. 可以失败后继续翻译。
11. 可以校验占位符是否完整。
12. 可以校验基础 Markdown 结构。
13. 可以导出完整 Markdown 译文。
14. 可以导出原文译文对照版。

## 15.2 质量验收

准备一份测试文档，包含：

1. 多级标题。
2. 普通段落。
3. 列表。
4. 代码块。
5. 行内代码。
6. URL。
7. Markdown 链接。
8. 图片路径。
9. 表格。
10. 引用编号。
11. 参考文献。
12. 术语重复出现。

验收要求：

1. 标题结构不丢失。
2. 代码块内容不被翻译。
3. URL 不被修改。
4. 引用编号不被修改。
5. 术语译法保持一致。
6. 失败后可以继续。
7. 输出 Markdown 可以正常渲染。

---

## 16. 测试用例建议

## 16.1 基础翻译测试

输入：包含 3 个章节的 Markdown 文档。

预期：

1. 系统识别 3 个章节。
2. 每个章节生成多个 chunk。
3. 翻译后章节顺序一致。
4. 导出译文可读。

## 16.2 术语一致性测试

术语表：

```text
Agent = 智能体
Context Engineering = 上下文工程
Tool Call = 工具调用
```

输入文档多次出现这些术语。

预期：

1. 译文中统一使用指定译法。
2. 不出现“代理”“上下文设计”“工具呼叫”等非指定译法。

## 16.3 不可翻译内容保护测试

输入包含：

```markdown
Run `docker compose up -d`.

```java
public class UserService {}
```

See [Docs](https://example.com/docs).
```

预期：

1. 行内代码保持原样。
2. Java 代码块保持原样。
3. URL 保持原样。
4. 链接文本可翻译。

## 16.4 失败续跑测试

模拟第 5 个 chunk 翻译失败。

预期：

1. 前 4 个 chunk 状态为 DONE。
2. 第 5 个 chunk 状态为 FAILED。
3. 继续翻译时从第 5 个 chunk 开始。
4. 前 4 个 chunk 不重复调用模型。

## 16.5 占位符异常测试

模拟模型输出时删除 `__URL_001__`。

预期：

1. 校验失败。
2. chunk 标记 FAILED 或 NEED_REVIEW。
3. 错误报告指出缺失占位符。

---

## 17. V1.1 / V2.0 规划

## 17.1 V1.1 可增强能力

1. 支持 DOCX 更完整的标题和样式解析。
2. 支持 HTML 输入输出。
3. 支持自动术语抽取和用户确认。
4. 支持样章确认流程。
5. 支持章节摘要生成。
6. 支持按章节重翻。
7. 支持术语变更后的影响分析。
8. 支持更完整的质量评分。

## 17.2 V2.0 可增强能力

1. 支持 EPUB 翻译和重新打包。
2. 支持 PDF 版面解析。
3. 支持图片 OCR 和图片文字翻译。
4. 支持多人协同审校。
5. 支持翻译记忆库。
6. 支持多模型质量对比。
7. 支持在线编辑器。
8. 支持人机协作审校工作台。
9. 支持完整 CAT 工具能力。

---

## 18. 核心设计原则总结

V1.0 的核心设计原则如下：

1. 不直接翻译整本书，而是先结构化解析。
2. 不按固定字数粗暴切分，而是按章节和语义单元切分。
3. 不让模型管理文档结构，而是由系统管理结构。
4. 不让模型自由处理术语，而是由术语表约束。
5. 不只靠 Prompt 保持风格，而是用风格指南和版本记录约束。
6. 不让模型看到不该翻译的内容，而是先做占位符保护。
7. 不把失败当成整本书失败，而是 chunk 级失败、chunk 级重试。
8. 不把翻译完成等同于交付完成，而是必须经过校验和导出。
9. 不追求 V1.0 大而全，而是先完成 Markdown 长文档翻译闭环。

---

## 19. 一句话定位

长文档翻译工作流 V1.0 是一套面向 Markdown / 技术文档的结构化翻译流水线，通过文档解析、语义切片、术语约束、风格约束、不可翻译内容保护、chunk 级状态管理和自动校验，实现长文档可控、可恢复、可追溯的一致性翻译。

