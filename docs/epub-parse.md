# EPUB 解析库选型与容错方案

## 1. 结论

如果目标是“容错解析并翻译真实世界 EPUB”，建议不要只依赖单个库，而是采用分层组合：

```text
EbookLib
  负责 EPUB 容器、OPF、manifest、spine、资源读取

BeautifulSoup + html5lib
  负责容错解析章节 HTML/XHTML

lxml
  作为快速路径或较规范 XHTML 的结构处理工具

zipfile
  作为最终 fallback，直接读取 EPUB zip 内部文件
```

推荐首选组合：

```text
EbookLib + BeautifulSoup + html5lib
```

性能优化策略：

```text
优先尝试 lxml
  -> 如果解析失败或结构异常
  -> fallback 到 html5lib
```

## 2. 为什么不只用一个库

EPUB 本质上是一个 ZIP 容器，内部包含：

1. `mimetype`
2. `META-INF/container.xml`
3. OPF package document
4. spine 阅读顺序
5. XHTML/HTML 章节文件
6. CSS、图片、字体等静态资源
7. nav/toc 文件

真实 EPUB 文件常见问题：

1. OPF 或 manifest 不规范。
2. spine 中的章节顺序与实际文件结构不完全一致。
3. 章节 XHTML 不是严格 XML。
4. HTML 标签未闭合、嵌套错误。
5. 编码声明不准确。
6. 图片、CSS、字体资源路径不标准。
7. EPUB2/EPUB3 结构差异。

因此比较稳的做法是：

1. 用 EPUB 专用库处理容器和书籍结构。
2. 用 HTML 容错解析器处理章节内容。
3. 对异常文件保留 zip 级 fallback。

## 3. 推荐库

## 3.1 EbookLib

用途：

1. 打开 EPUB。
2. 读取 EPUB2 / EPUB3。
3. 获取 manifest item。
4. 获取 spine 顺序。
5. 读取 XHTML 章节内容。
6. 读取图片、CSS 等资源。
7. 后续可用于写回 EPUB。

优点：

1. 使用面较广。
2. API 简单。
3. 支持 EPUB2 / EPUB3。
4. 适合做 EPUB 容器层处理。

不足：

1. 对坏 HTML/XHTML 的章节内容解析不是它的核心强项。
2. 写回复杂 EPUB 时仍需要谨慎处理资源、manifest、spine。

建议定位：

```text
EbookLib 负责 EPUB 容器和书籍结构，不负责复杂 HTML 容错清洗。
```

## 3.2 BeautifulSoup + html5lib

用途：

1. 解析章节 HTML/XHTML。
2. 容错处理不规范标签。
3. 提取可翻译文本节点。
4. 保留 HTML 标签结构。
5. 保护链接、图片、代码、表格等结构。

优点：

1. `html5lib` 非常宽容。
2. 解析方式接近浏览器。
3. 适合处理真实世界中不严格的 HTML。
4. BeautifulSoup API 易用。

不足：

1. `html5lib` 比 `lxml` 慢。
2. 解析后可能规范化 HTML 结构，导致回写 diff 较大。
3. 不适合做高保真 XML 序列化。

建议定位：

```text
当章节 HTML/XHTML 不规范时，用 BeautifulSoup(html5lib) 作为容错解析路径。
```

## 3.3 lxml

用途：

1. 快速解析规范 XHTML/HTML。
2. 做节点级遍历。
3. 做结构化替换。
4. 做较高性能的批量章节处理。

优点：

1. 快。
2. 对 HTML 有一定容错能力。
3. XPath / etree 能力强。

不足：

1. 对特别坏的 HTML，容错能力不如 html5lib。
2. C 扩展依赖可能带来安装复杂度。

建议定位：

```text
lxml 作为快速路径；遇到解析失败或结构异常时 fallback 到 html5lib。
```

## 3.4 zipfile

用途：

1. 作为底层 fallback。
2. 直接读取 EPUB 内部文件。
3. 调试损坏或非标准 EPUB。
4. 在写回时精确控制 zip 条目。

优点：

1. Python 标准库，无额外依赖。
2. 可绕过上层库限制。
3. 适合排查容器结构问题。

不足：

1. 需要自己处理 OPF、spine、路径解析。
2. 写回 EPUB 时容易破坏规范。

建议定位：

```text
zipfile 只作为 fallback 和调试工具，不作为首选业务抽象。
```

## 4. 推荐解析流程

```text
1. 使用 EbookLib 打开 EPUB
2. 读取 OPF / manifest / spine
3. 按 spine 顺序找到正文 XHTML item
4. 读取每个 XHTML item 的 bytes
5. 解码内容
6. 优先用 lxml 解析
7. 如果失败或发现结构异常，fallback 到 BeautifulSoup(html5lib)
8. 提取可翻译文本节点
9. 保护不可翻译内容
10. 生成 chunk
11. 翻译后回写对应文本节点
12. 保留图片、CSS、字体、metadata 等资源
13. 重新打包 EPUB
14. 用 epubcheck 或内部校验确认产物可用
```

## 5. 示例代码

```python
from ebooklib import epub
from ebooklib import ITEM_DOCUMENT
from bs4 import BeautifulSoup


def iter_epub_documents(path: str):
    book = epub.read_epub(path)
    for item in book.get_items():
        if item.get_type() != ITEM_DOCUMENT:
            continue
        raw = item.get_content()
        html = raw.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html5lib")
        yield item, soup
```

更推荐在实际工程中按 spine 顺序读取，而不是简单遍历所有 document item：

```python
from ebooklib import epub


def iter_spine_documents(path: str):
    book = epub.read_epub(path)
    manifest = {item.get_id(): item for item in book.get_items()}

    for item_id, _linear in book.spine:
        item = manifest.get(item_id)
        if item is None:
            continue
        html = item.get_content().decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html5lib")
        yield item, soup
```

## 6. 与当前翻译系统的集成建议

当前系统已经有：

1. Markdown parser
2. IPYNB parser
3. chunking
4. protection
5. prompt builder
6. LLM provider
7. validation
8. exporter

EPUB 支持建议新增：

```text
llm_translate/parser/epub.py
llm_translate/exporter_epub.py
tests/test_epub_pipeline.py
fixtures/sample.epub
```

## 6.1 Parser 设计

新增 `EpubParser`：

```python
class EpubParser:
    def parse(self, project_id: str, epub_path: Path) -> list[DocumentBlock]:
        ...
```

解析输出建议：

```json
{
  "format": "epub",
  "item_id": "chapter_001",
  "href": "text/chapter001.xhtml",
  "spine_index": 3,
  "node_path": "html/body/section/p[2]",
  "tag": "p",
  "translatable": true
}
```

建议翻译粒度：

1. 标题节点：`h1` ~ `h6`
2. 段落节点：`p`
3. 列表项：`li`
4. 表格文本：`td` / `th`
5. 引用：`blockquote`
6. 图片 alt/title：P1 支持

默认不翻译：

1. `script`
2. `style`
3. `code`
4. `pre`
5. `kbd`
6. `samp`
7. URL、文件路径、锚点
8. 图片 src
9. CSS class/id

## 6.2 Chunking 设计

EPUB chunk 不应按纯文本粗暴切分。

建议优先级：

```text
spine item / chapter
  -> section
  -> paragraph/list/table block
  -> sentence fallback
```

chunk metadata 应保留：

```json
{
  "format": "epub",
  "href": "text/chapter001.xhtml",
  "spine_index": 3,
  "node_ids": ["n_0001", "n_0002"]
}
```

## 6.3 Protection 设计

EPUB 章节是 HTML/XHTML，保护重点包括：

1. HTML 标签结构。
2. `href`。
3. `src`。
4. `id` / anchor。
5. CSS class。
6. inline code。
7. code block。
8. footnote reference。
9. math / MathML。
10. SVG。

建议策略：

```text
模型只看到可翻译文本节点和占位符。
不要让模型直接修改完整 HTML。
```

## 6.4 Exporter 设计

导出 EPUB 时：

1. 以原始 EPUB 为模板。
2. 只替换已翻译文本节点。
3. 保留 OPF、manifest、spine、metadata。
4. 保留 CSS、图片、字体等资源。
5. 重新写入修改后的 XHTML item。
6. 重新打包 EPUB。

输出：

```text
artifacts/translated.epub
artifacts/translated.md
artifacts/bilingual.md
artifacts/translation-log.json
artifacts/validation-report.md
```

## 6.5 Validation 设计

EPUB 校验至少包括：

1. EPUB zip 可打开。
2. `mimetype` 存在且正确。
3. `container.xml` 存在。
4. OPF 可解析。
5. manifest item 数量不变。
6. spine 顺序不变。
7. 资源文件不丢失。
8. XHTML 文件可解析。
9. 链接 href 不变。
10. 图片 src 不变。
11. code/pre 内容不变。
12. 章节数量不变。

如果环境允许，可集成外部 `epubcheck` 做最终验证。

## 7. 依赖建议

建议加入：

```toml
dependencies = [
  "EbookLib>=0.18",
  "beautifulsoup4>=4.12",
  "html5lib>=1.1",
  "lxml>=5.0"
]
```

如果希望安装更轻：

```text
P0: EbookLib + beautifulsoup4 + html5lib
P1: 增加 lxml 作为性能优化路径
```

## 8. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| EPUB 内 XHTML 不规范 | 解析失败 | lxml 失败后 fallback 到 html5lib |
| 回写后 HTML diff 很大 | 难以审计 | 节点级替换，不整章重排 |
| 链接或图片路径被翻译 | 资源损坏 | 属性级保护和校验 |
| CSS/脚本被修改 | EPUB 渲染异常 | script/style/code/pre 默认跳过 |
| 章节顺序错乱 | 阅读体验损坏 | 严格按 spine 处理并校验 |
| EPUB 重新打包不规范 | 阅读器打不开 | 保持 mimetype 规则，必要时 epubcheck |
| MathML/SVG 被破坏 | 技术书籍内容损坏 | P0 默认整体保护 |

## 9. 推荐优先级

P0：

1. 读取 EPUB。
2. 按 spine 顺序解析 XHTML。
3. 提取标题、段落、列表项文本。
4. 跳过 code/pre/script/style。
5. 翻译文本节点。
6. 回写 XHTML。
7. 导出 translated.epub。
8. 基础结构校验。

P1：

1. 图片 alt/title 翻译。
2. footnote/endnote 识别。
3. MathML/SVG 保护。
4. lxml 快速路径。
5. epubcheck 集成。
6. 双语 EPUB 输出。

P2：

1. 版式复杂 EPUB 高保真校验。
2. 章节级审校 UI。
3. 术语影响分析。
4. 增量重翻。
