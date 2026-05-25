# 长文档结构化翻译工作流 V1.0 实施计划

## 1. 计划目标

本文档基于 [PRD-V1.0.md](PRD-V1.0.md) 与 [DESIGN-V1.0.md](DESIGN-V1.0.md)，拆解 V1.0 的研发实施计划、里程碑、任务边界、验收标准与风险控制。

V1.0 交付目标：

1. 打通 Markdown 长文档翻译闭环。
2. 支持结构解析、chunk 切片、不可翻译内容保护、模型翻译、质量校验、失败续跑和导出。
3. 提供基础工作台页面或 CLI/API 能力，至少能完成端到端验收。
4. 保留 TXT / DOCX、翻译记忆库、在线审校等后续扩展入口。

## 2. 研发策略

### 2.1 优先级原则

```text
P0: Markdown 端到端闭环必须完成
P1: 可观测、可恢复、可审阅能力补齐
P2: TXT / DOCX 基础适配与体验增强
```

### 2.2 迭代方式

采用“纵向切片优先”的方式：

1. 先完成最小可运行流水线：导入 Markdown -> 解析 -> 切片 -> mock 翻译 -> 导出。
2. 再替换 mock 翻译为真实模型调用。
3. 再补占位符保护、术语、风格、校验、续跑。
4. 最后补 UI 工作台、报告、异常处理和验收样例。

这样每个阶段都有可运行产物，便于持续验证。

## 3. 里程碑总览

| 里程碑 | 目标 | 主要交付物 | 建议周期 |
|---|---|---|---|
| M0 | 工程骨架与基础约定 | 项目结构、配置、数据库迁移、开发脚本 | 2-3 天 |
| M1 | Markdown 解析与 AST | Parser、DocumentBlock、章节树预览 | 4-5 天 |
| M2 | Chunking 与项目状态 | Chunker、状态机、续跑查询 | 4-5 天 |
| M3 | 保护引擎与恢复 | ProtectedSpan、占位符替换/恢复、基础校验 | 5-6 天 |
| M4 | 翻译执行链路 | Prompt Builder、LLM Adapter、重试、持久化 | 5-7 天 |
| M5 | 质量校验与报告 | 校验器、ValidationReport、质量报告导出 | 4-6 天 |
| M6 | 导出与对照版 | translated.md、bilingual.md、日志 JSON | 3-4 天 |
| M7 | 工作台/API/CLI 完善 | 项目页、chunk 审阅、术语/风格配置 | 6-8 天 |
| M8 | 验收、修复与发布 | 验收样例、测试报告、发布说明 | 4-5 天 |

完整 V1.0 预计 6-8 个研发周，具体取决于 UI 范围、模型供应商接入方式和 DOCX/TXT 是否进入首版验收。

## 4. M0 工程骨架

### 4.1 目标

建立可持续开发的工程基础，明确模块边界和本地运行方式。

### 4.2 任务

1. 确定技术栈：后端框架、前端框架、数据库、Markdown AST 库、模型 SDK。
2. 建立目录结构：

```text
src/
  api/
  application/
  domain/
  parser/
  chunking/
  protection/
  prompt/
  llm/
  validation/
  export/
  storage/
  ui/
tests/
fixtures/
```

3. 建立配置管理：
   - 数据库路径。
   - 项目工作目录。
   - 模型供应商配置。
   - 默认 chunk token 限制。
   - 默认重试次数。
4. 建立数据库迁移机制。
5. 增加最小健康检查与开发启动脚本。

### 4.3 验收标准

1. 本地可启动服务或 CLI。
2. 数据库可初始化。
3. 测试命令可运行。
4. 配置缺失时有明确错误提示。

## 5. M1 Markdown 解析与 AST

### 5.1 目标

将 Markdown 文档解析为稳定的 DocumentBlock 列表，并生成章节结构。

### 5.2 任务

1. 引入 Markdown AST 解析库。
2. 实现 `MarkdownParser`：
   - 标题。
   - 段落。
   - 列表。
   - 引用块。
   - 代码块。
   - 行内代码。
   - 链接。
   - 图片。
   - 表格。
3. 实现 block 归一化：
   - block_id 生成。
   - block_order 生成。
   - parent_id / heading 层级关系。
   - metadata 记录。
4. 实现章节编号识别：
   - `Chapter 3. Title`
   - `3.1 Title`
   - `第 3 章 标题`
5. 提供章节树查询接口。
6. 保存 ast 快照到 `snapshots/ast.json`。

### 5.3 测试

1. 解析多级标题。
2. 解析包含代码块的文档，代码块不被拆为普通段落。
3. 解析链接和图片，地址进入 metadata。
4. 解析表格，记录列数和行数。

### 5.4 验收标准

1. 标题数量、层级、顺序与原文一致。
2. 代码块、表格、列表、引用可识别。
3. 每个 block 有稳定 ID 与顺序。
4. 可展示文档结构树。

## 6. M2 Chunking 与状态机

### 6.1 目标

按章节和语义边界生成可翻译 chunk，并支持 chunk 级状态管理。

### 6.2 任务

1. 实现 `ChunkingEngine`：
   - 输入 DocumentBlock。
   - 输出 TranslationChunk。
   - 按章节优先切分。
   - 不打断代码块、表格、列表、引用。
2. 实现 token 估算器。
3. 实现 chunk 大小配置：
   - soft limit。
   - hard limit。
4. 实现 project 状态机：
   - CREATED。
   - PARSED。
   - READY。
   - TRANSLATING。
   - PAUSED。
   - FAILED。
   - VALIDATING。
   - COMPLETED。
   - EXPORTED。
5. 实现 chunk 状态机：
   - PENDING。
   - PROTECTED。
   - TRANSLATING。
   - TRANSLATED。
   - VALIDATING。
   - DONE。
   - FAILED。
   - NEED_REVIEW。
   - SKIPPED。
6. 实现续跑查询：
   - 默认处理 PENDING / FAILED。
   - 用户确认后处理 NEED_REVIEW。
7. 保存 `snapshots/chunks.json`。

### 6.3 测试

1. chunk 不跨一级章节。
2. chunk 不切断代码块。
3. chunk 不切断 Markdown 表格。
4. 失败 chunk 可单独查询和重试。

### 6.4 验收标准

1. 每个 chunk 能追踪回 block_ids。
2. chunk_order 全项目稳定。
3. 可从 FAILED / PENDING 继续执行。
4. DONE / SKIPPED 默认不重复执行。

## 7. M3 不可翻译内容保护

### 7.1 目标

在模型调用前保护代码、URL、路径、引用编号等不应翻译内容，并在翻译后可靠恢复。

### 7.2 任务

1. 实现 `ProtectionEngine`。
2. 支持保护类型：
   - 代码块。
   - 行内代码。
   - URL。
   - Markdown 链接地址。
   - 图片路径。
   - 文件路径。
   - 命令行。
   - API 路径。
   - 引用编号。
   - 数学公式。
3. 实现占位符生成规则：

```text
__LT_{TYPE}_{GLOBAL_SEQUENCE}__
```

4. 保存 `protected_span`。
5. 实现占位符恢复。
6. 实现占位符集合校验。
7. 实现保护内容预览统计。

### 7.3 测试

1. 行内代码保持原样。
2. Java / Python / SQL 代码块保持原样。
3. Markdown 链接文本可翻译，URL 保持原样。
4. 图片 alt 可翻译，图片路径保持原样。
5. 模拟模型删除占位符，校验失败。

### 7.4 验收标准

1. 每个 protected span 有唯一占位符。
2. protected_text 可用于模型调用。
3. restored_text 可恢复全部保护内容。
4. 占位符缺失、重复、改写会被检测到。

## 8. M4 翻译执行链路

### 8.1 目标

接入真实或可替换的模型调用链路，完成 chunk 级翻译、重试和状态持久化。

### 8.2 任务

1. 实现 `LLMProvider` 接口：

```text
translate(input) -> output
```

2. 实现至少一个真实模型适配器。
3. 实现 mock 模型适配器，用于测试和本地验收。
4. 实现 `PromptBuilder`：
   - 风格指南注入。
   - 当前 chunk 相关术语注入。
   - 章节路径注入。
   - 保护规则注入。
5. 实现 `TranslationRunner`：
   - 选择待处理 chunk。
   - 执行保护。
   - 构造 prompt。
   - 调用模型。
   - 保存 target_text。
   - 进入校验。
6. 实现自动重试：
   - 超时。
   - 空输出。
   - 临时模型错误。
   - 占位符缺失可重试一次。
7. 保存 `translation_attempt`。

### 8.3 测试

1. mock 模型可完成端到端翻译。
2. 模型超时后按配置重试。
3. 重试次数超过上限后 chunk 进入 FAILED。
4. 每次模型调用记录版本和 attempt。

### 8.4 验收标准

1. 可从 READY 状态开始翻译。
2. 每个 chunk 状态变化可追踪。
3. 失败后再次执行不会重翻 DONE chunk。
4. prompt_version、model_name、glossary_version、style_guide_version 被记录。

## 9. M5 质量校验与报告

### 9.1 目标

建立交付前质量门禁，发现格式破坏、占位符缺失、术语不一致等问题。

### 9.2 任务

1. 实现 `ValidationEngine`。
2. chunk 级校验：
   - 占位符集合。
   - 空输出。
   - URL 一致。
   - 引用编号一致。
   - Markdown 基础结构。
   - 表格列数。
   - 术语一致性。
   - 长度异常。
3. 项目级校验：
   - 标题数量和层级。
   - chunk 完成率。
   - 失败/待审阅统计。
   - 术语聚合报告。
4. 实现 `validation_report` 保存。
5. 实现 Markdown / JSON 报告生成。

### 9.3 测试

1. 占位符缺失检测。
2. 表格列数不一致检测。
3. 指定术语未使用检测。
4. URL 被改写检测。
5. 异常短译文检测。

### 9.4 验收标准

1. 校验失败的 chunk 不进入 DONE。
2. 用户能看到失败原因。
3. 项目完成前可查看质量报告。
4. 报告可导出为 JSON 和 Markdown。

## 10. M6 导出模块

### 10.1 目标

生成 V1.0 要求的全部交付物。

### 10.2 任务

1. 实现 `MarkdownExporter`。
2. 生成纯译文版：

```text
artifacts/translated.md
```

3. 生成原文译文对照版：

```text
artifacts/bilingual.md
```

4. 生成翻译日志：

```text
artifacts/translation-log.json
```

5. 生成校验报告：

```text
artifacts/validation-report.json
artifacts/validation-report.md
```

6. 记录 `export_artifact`。
7. 支持正式版和进度版导出。

### 10.3 测试

1. 导出标题层级与原文一致。
2. 代码块、URL、引用编号已恢复。
3. 对照版原文和译文一一对应。
4. 未完成项目只能导出进度版。

### 10.4 验收标准

1. translated.md 可正常 Markdown 渲染。
2. bilingual.md 可用于人工审校。
3. translation-log.json 可追踪 chunk、模型、prompt、版本和错误。
4. validation-report.md 可读。

## 11. M7 工作台 / API / CLI 完善

### 11.1 目标

提供可操作的产品入口，让用户完成创建项目、配置、翻译、审阅和导出。

### 11.2 任务

1. 项目列表：
   - 项目名称。
   - 源文档。
   - 目标语言。
   - 状态。
   - 总 chunk 数。
   - 完成进度。
   - 失败数。
   - 创建/更新时间。
2. 项目详情：
   - 基本信息。
   - 文档结构树。
   - 翻译进度。
   - 失败 chunk 列表。
   - 术语表。
   - 风格指南。
   - 保护内容统计。
   - 导出入口。
3. 术语表配置：
   - 手工新增。
   - CSV / JSON 导入。
   - 编辑。
   - 删除。
   - 锁定。
   - 命中次数。
4. 风格指南配置：
   - 预设选择。
   - 自定义规则。
   - 压缩 prompt 预览。
   - 保存版本。
5. 保护内容预览：
   - 类型统计。
   - 明细查看。
6. Chunk 审阅：
   - 原文。
   - protected_text。
   - target_text。
   - restored_text。
   - protected span 映射。
   - 校验结果。
   - 重试按钮。
   - 人工编辑译文。

### 11.3 验收标准

1. 用户能从 UI 或 CLI 完成端到端流程。
2. 用户能看到失败原因并重试。
3. 用户能导入术语并看到校验结果。
4. 用户能导出译文版和对照版。

## 12. M8 验收与发布

### 12.1 目标

用真实样例完成 V1.0 验收，修复高优先级缺陷，形成可发布版本。

### 12.2 任务

1. 准备标准验收 Markdown 文档，包含：
   - 多级标题。
   - 普通段落。
   - 列表。
   - 代码块。
   - 行内代码。
   - URL。
   - Markdown 链接。
   - 图片路径。
   - 表格。
   - 引用编号。
   - 参考文献。
   - 重复术语。
2. 准备术语表：

```text
Agent = 智能体
Context Engineering = 上下文工程
Tool Call = 工具调用
Translation Memory = 翻译记忆库
```

3. 执行验收用例：
   - 基础翻译。
   - 术语一致性。
   - 不可翻译内容保护。
   - 失败续跑。
   - 占位符异常。
4. 修复 P0 / P1 缺陷。
5. 编写发布说明。
6. 冻结 V1.0 范围。

### 12.3 发布门禁

1. P0 用例全部通过。
2. 无阻塞级崩溃。
3. 所有 DONE chunk 均通过占位符校验。
4. Markdown 导出可渲染。
5. 失败续跑用例通过。
6. 翻译日志和校验报告可导出。

## 13. 任务拆分清单

### 13.1 后端 / 核心引擎

| 编号 | 任务 | 优先级 |
|---|---|---|
| BE-001 | 项目、block、chunk、span、report 数据表 | P0 |
| BE-002 | 项目 CRUD 与文件上传 | P0 |
| BE-003 | Markdown Parser | P0 |
| BE-004 | 章节树构建 | P0 |
| BE-005 | Chunking Engine | P0 |
| BE-006 | Protection Engine | P0 |
| BE-007 | Prompt Builder | P0 |
| BE-008 | LLM Adapter | P0 |
| BE-009 | Translation Runner | P0 |
| BE-010 | Retry / Resume | P0 |
| BE-011 | Validation Engine | P0 |
| BE-012 | Export Engine | P0 |
| BE-013 | Translation Attempt Log | P1 |
| BE-014 | Project Event Log | P1 |
| BE-015 | TXT Parser 基础适配 | P2 |
| BE-016 | DOCX Parser 基础适配 | P2 |

### 13.2 前端 / 工作台

| 编号 | 任务 | 优先级 |
|---|---|---|
| FE-001 | 项目列表页 | P0 |
| FE-002 | 创建项目页 | P0 |
| FE-003 | 项目详情页 | P0 |
| FE-004 | 文档结构预览 | P0 |
| FE-005 | 翻译进度与状态展示 | P0 |
| FE-006 | 失败 chunk 列表与重试 | P0 |
| FE-007 | 术语表配置页 | P1 |
| FE-008 | 风格指南配置页 | P1 |
| FE-009 | 保护内容预览页 | P1 |
| FE-010 | Chunk 审阅页 | P1 |
| FE-011 | 导出产物下载入口 | P0 |

### 13.3 测试 / 质量

| 编号 | 任务 | 优先级 |
|---|---|---|
| QA-001 | Markdown fixture 文档 | P0 |
| QA-002 | Parser 单元测试 | P0 |
| QA-003 | Chunker 单元测试 | P0 |
| QA-004 | Protection 单元测试 | P0 |
| QA-005 | Validator 单元测试 | P0 |
| QA-006 | Exporter 单元测试 | P0 |
| QA-007 | Mock LLM 集成测试 | P0 |
| QA-008 | 失败续跑集成测试 | P0 |
| QA-009 | 真实模型冒烟测试 | P1 |
| QA-010 | UI 端到端验收测试 | P1 |

## 14. 依赖与前置决策

需要在 M0 阶段确认：

1. 后端语言与框架。
2. 前端是否进入 V1.0 必交付，还是先以 CLI/API 作为 MVP。
3. 模型供应商与鉴权方式。
4. Markdown AST 解析库。
5. token 估算库。
6. SQLite 是否满足首版部署形态。
7. DOCX / TXT 是否列入 V1.0 验收范围。

## 15. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| Markdown 结构复杂，手写解析容易漏场景 | 结构破坏 | 使用成熟 AST 库，保留 raw metadata |
| 模型改写占位符 | 导出错误 | 占位符强校验，失败自动重试，仍失败转 NEED_REVIEW |
| chunk 过大导致模型失败 | 翻译中断 | token 估算 + hard limit + 二次切分 |
| 术语校验误报 | 审阅负担 | V1.0 先 exact match，fuzzy 标为 WARNING |
| 风格不一致 | 译文质量波动 | 风格指南版本化，章节顺序翻译，必要时注入前文摘要 |
| 失败续跑重复翻译 | 成本增加 | DONE / SKIPPED 默认跳过，attempt 单独记录 |
| UI 范围膨胀 | 延期 | 先保证项目详情、进度、失败重试、导出四个主路径 |
| DOCX 高保真难度高 | 范围失控 | V1.0 仅保留基础段落/标题，复杂样式后置 |

## 16. 验收矩阵

| PRD 要求 | 验收方式 | 负责模块 |
|---|---|---|
| 支持上传 Markdown | 上传 fixture 并创建项目 | Project API / UI |
| 解析章节结构 | 检查章节树和 block 数量 | Parser |
| 结构化切片 | 检查 chunk 与 block_ids | Chunker |
| 指定术语表 | 导入术语并翻译重复术语 | Glossary / Prompt / Validator |
| 风格指南 | 保存风格并检查 prompt 版本 | StyleGuide / Prompt |
| 不可翻译内容保护 | 代码、URL、引用保持原样 | Protection |
| 分 chunk 翻译 | mock/真实模型翻译多个 chunk | Runner |
| 状态持久化 | 中断后重启查看状态 | Storage |
| 失败续跑 | 模拟第 5 个 chunk 失败后续跑 | Runner |
| 基础质量校验 | 注入占位符缺失和术语错误 | Validator |
| 导出译文版 | 生成 translated.md 并渲染 | Exporter |
| 导出对照版 | 生成 bilingual.md | Exporter |

## 17. V1.0 完成定义

满足以下条件即可判定 V1.0 完成：

1. Markdown 长文档端到端流程可运行。
2. 标准验收文档通过解析、切片、保护、翻译、校验、导出。
3. 失败续跑可以从失败 chunk 继续。
4. 代码块、行内代码、URL、图片路径、引用编号不会被模型破坏后静默交付。
5. 术语表能影响 prompt，并能在译后校验。
6. 导出物包含译文版、对照版、日志和质量报告。
7. 核心模块具备单元测试，端到端流程具备集成测试。
8. 已知缺陷有分级记录，P0 缺陷清零。

