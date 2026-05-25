# 翻译工具架构设计

## 1. 目标

当前工具已经支持 Markdown 和 Jupyter Notebook (`.ipynb`) 翻译，下一步准备支持 EPUB。

为了避免每新增一种格式就在主流程里增加大量 `if input_format == ...` 分支，后续架构应演进为：

```text
公共翻译内核 + 格式插件
```

核心原则：

1. 公共流程只理解抽象文档单元。
2. 格式插件负责解析、切片、保护、回写和格式级校验。
3. Markdown、IPYNB、EPUB 共用项目状态、chunk 状态、LLM 调用、术语表、重试、日志和报告。
4. 每种格式保留自己的结构特点和质量校验。

## 2. 总体流程

```text
Input File
  -> FormatAdapter.detect()
  -> FormatAdapter.parse()
  -> DocumentIR
  -> ChunkPlanner
  -> ProtectionPolicy
  -> PromptBuilder
  -> LLMProvider
  -> Validator
  -> FormatAdapter.export()
  -> Artifacts
```

公共层负责：

1. 项目创建与状态机。
2. chunk 状态机。
3. SQLite / SQLAlchemy 持久化。
4. DeepSeek / LiteLLM 调用。
5. glossary 注入。
6. style guide 注入。
7. retry / resume。
8. translation attempt log。
9. 通用 placeholder 校验。
10. artifact / report 生成。

格式层负责：

1. 如何解析结构。
2. 哪些内容可翻译。
3. 哪些内容必须保护。
4. 如何切 chunk 最合理。
5. 如何回写。
6. 如何做格式完整性校验。

## 3. FormatAdapter 抽象

建议新增统一格式适配器接口：

```python
class FormatAdapter:
    format_name: str

    def supports(self, path: Path) -> bool:
        ...

    def parse(self, project, source_path: Path) -> DocumentIR:
        ...

    def plan_chunks(self, document: DocumentIR, limits: ChunkLimits) -> list[TranslationChunk]:
        ...

    def build_prompt_context(self, chunk, document) -> FormatPromptContext:
        ...

    def validate_chunk(self, chunk) -> list[Issue]:
        ...

    def validate_artifact(self, original, exported) -> list[Issue]:
        ...

    def export(self, project, document, chunks, reports) -> dict[str, Path]:
        ...
```

服务层不应继续写大量格式分支：

```python
if project.input_format == "markdown":
    ...
elif project.input_format == "ipynb":
    ...
elif project.input_format == "epub":
    ...
```

应改为：

```python
adapter = registry.get(project.input_format)
document = adapter.parse(project, source_path)
chunks = adapter.plan_chunks(document, limits)
...
paths = adapter.export(project, document, chunks, reports)
```

## 4. FormatRegistry

新增格式注册表：

```python
class FormatRegistry:
    def __init__(self, adapters: list[FormatAdapter]):
        self.adapters = adapters

    def detect(self, path: Path) -> FormatAdapter:
        for adapter in self.adapters:
            if adapter.supports(path):
                return adapter
        raise ValueError(f"unsupported input format: {path.suffix}")

    def get(self, input_format: str) -> FormatAdapter:
        ...
```

这样后续新增 DOCX / HTML / EPUB / PDF 时，只需要新增 adapter，不需要污染主流程。

## 5. DocumentIR

当前的 `DocumentBlock` 可以升级为更通用的中间表示：

```python
@dataclass
class DocumentNode:
    id: str
    project_id: str
    format: str
    node_type: str
    translatable: bool
    source_text: str
    order: int
    parent_id: str | None
    metadata: dict
```

不同格式映射示例：

```text
Markdown
  heading / paragraph / list / table / code_block

IPYNB
  notebook_markdown_cell / notebook_code_cell / notebook_raw_cell

EPUB
  epub_chapter / epub_heading / epub_paragraph / epub_list_item / epub_table_cell
```

公共 chunk 只引用 node id：

```python
@dataclass
class TranslationChunk:
    block_ids: list[str]
    source_text: str
    metadata: dict
```

`metadata` 用于格式回写，例如 EPUB：

```json
{
  "format": "epub",
  "href": "text/chapter001.xhtml",
  "spine_index": 3,
  "node_paths": ["html/body/section/p[2]"]
}
```

## 6. ProtectionPolicy

当前 protection 偏 Markdown。后续建议拆成公共保护和格式保护：

```python
class ProtectionPolicy:
    def protect(self, chunk) -> ProtectionResult:
        ...

    def restore(self, text: str, spans: list[ProtectedSpan]) -> str:
        ...
```

公共保护：

1. URL
2. inline code
3. file path
4. API path
5. placeholder

Markdown 保护：

1. fenced code
2. markdown link target
3. image path
4. table separator

IPYNB 保护：

1. HTML tag / block
2. attachment reference

EPUB 保护：

1. HTML attributes
2. anchor id
3. image src
4. MathML
5. SVG
6. footnote refs
7. code / pre block

关键原则：

```text
EPUB 最好不要把完整 HTML 交给模型。
应只提取可翻译文本节点，让模型处理自然语言文本。
```

## 7. PromptBuilder

PromptBuilder 可以保留公共模板，但接收格式上下文：

```python
@dataclass
class FormatPromptContext:
    format: str
    unit_name: str
    constraints: list[str]
    structure_hint: str
```

EPUB prompt 约束示例：

```text
当前内容来自 EPUB 的 XHTML 正文文本节点。
只翻译自然语言。
不要输出 HTML。
不要添加解释。
保留占位符。
保持术语一致。
```

Notebook prompt 约束示例：

```text
当前内容来自 Jupyter Notebook 的 markdown cell。
不要输出 JSON。
不要添加或删除 cell。
保留 Markdown / HTML 结构。
```

## 8. EPUB Adapter 设计

EPUB 不是长 Markdown，而是一个有 spine、manifest、OPF 元数据、XHTML 章节和静态资源的书籍容器。

EPUB adapter 应专门处理：

### 8.1 解析

```text
EbookLib 读取容器、manifest、spine
BeautifulSoup/html5lib 容错解析 XHTML
按 spine 顺序生成 DocumentNode
```

可翻译节点：

```text
h1-h6
p
li
blockquote
td/th
figcaption
```

默认不翻译：

```text
pre
code
script
style
svg
math
a.href
img.src
id/class/data-* attributes
```

### 8.2 Chunk 策略

```text
chapter
  -> section
  -> paragraph/list/table cell
```

chunk metadata：

```json
{
  "format": "epub",
  "href": "text/chapter001.xhtml",
  "spine_index": 3,
  "node_ids": ["n_0001", "n_0002"]
}
```

### 8.3 回写

```text
以原 EPUB 为模板
只替换文本节点
保留 OPF、manifest、spine、metadata
保留 CSS、图片、字体等资源
重新打包 translated.epub
```

### 8.4 校验

至少校验：

1. zip 可打开。
2. `mimetype` 正确。
3. `container.xml` 存在。
4. OPF 可解析。
5. manifest item 数量不变。
6. spine 顺序不变。
7. 章节数量不变。
8. 资源文件不丢失。
9. XHTML 可解析。
10. `href` 不变。
11. `src` 不变。
12. `code/pre` 内容不变。

如环境允许，可集成外部 `epubcheck` 做最终校验。

## 9. 性能策略

EPUB 可能比 Markdown/IPYNB 大得多，因此需要提前设计性能：

### 9.1 解析缓存

1. 保存 `DocumentIR` snapshot。
2. 保存 chapter hash。
3. 源文件不变时不重复 parse。

### 9.2 增量翻译

1. chunk source hash 不变且已有 DONE 结果时跳过。
2. glossary/style 变化时只标记受影响 chunk。

### 9.3 合理并发

1. Markdown/IPYNB 可以串行或小并发。
2. EPUB 可按 chapter 并发。
3. 同一 chapter 内建议保持顺序。

### 9.4 文本节点级处理

EPUB 不传完整 HTML，只传文本节点组合。

好处：

1. token 少。
2. 格式损坏概率低。
3. 回写更可控。

### 9.5 资源零拷贝

1. 图片、CSS、字体不进入 DB。
2. 只保留资源路径和 hash。
3. 导出时从原 EPUB 模板复制。

### 9.6 批量数据库写入

1. parse/chunk 阶段批量 insert。
2. chunk 状态更新保持单 chunk 原子提交。

## 10. 目标目录结构

建议逐步演进为：

```text
llm_translate/
  formats/
    base.py
    registry.py
    markdown.py
    ipynb.py
    epub.py
  protection/
    base.py
    markdown.py
    ipynb.py
    epub.py
  application/
    service.py
    runner.py
  export/
    common.py
  validation/
    common.py
    epub.py
```

当前代码还处于 MVP 形态，可以逐步迁移，不需要一次性大爆炸重构。

## 11. 推荐重构路线

### 第一步：抽象 FormatAdapter

目标：

1. 把现有 Markdown / IPYNB 迁到 adapter。
2. 业务行为保持不变。
3. 测试保持全绿。

### 第二步：实现 EpubAdapter

目标：

1. parse EPUB -> DocumentIR。
2. chunk -> translate -> export translated.epub。
3. 增加 EPUB fixture 和端到端测试。

### 第三步：质量和性能增强

目标：

1. source hash / chunk hash。
2. 并发 runner。
3. epubcheck。
4. 增量重翻。

## 12. 架构判断

不要一边直接加 EPUB，一边继续在 `TranslationService` 中堆格式判断。

原因：

1. EPUB 的格式特性比 Markdown/IPYNB 更复杂。
2. 如果不先抽象 adapter，EPUB 会把 service、chunking、protection、exporter、validation 都进一步耦合。
3. 后续 DOCX/HTML/PDF 会更难接。

推荐路线：

```text
先做轻量架构调整
  -> 把 Markdown/IPYNB 迁到 FormatAdapter
  -> 保持现有测试全绿
  -> 再开发 EPUB
```

但不建议做大规模目录重构后再开始 EPUB。更好的方式是：

```text
小步重构公共接口
  -> 迁移现有格式
  -> 立即用 EPUB 需求验证抽象是否合理
```

也就是：

```text
先调整架构，再开发 EPUB；
但架构调整只做 EPUB 所必需的最小适配器化，不做过度设计。
```
