# HTML 网页核心内容抽取翻译技术方案

## 1. 需求背景

为了支持对网页文档的翻译功能，需要从 HTML 文件中提取核心正文内容，去除导航、页脚、广告等噪声内容，然后调用现有的翻译流程进行翻译。

### 1.1 核心需求
- 支持从本地 HTML 文件提取核心正文内容
- 保留文档结构（标题、段落、列表、表格等）
- 与现有翻译系统无缝集成
- 架构设计支持后续快速集成 Playwright 渲染

### 1.2 测试用例
- 测试文件：`C:\Users\wangr\Downloads\Context Engineering for Personalization - State Management with Long-Term Memory Notes.html`
- 来源：OpenAI 开发者文档
- 特点：现代网页结构，包含导航、侧边栏等噪声内容

## 2. 技术选型

### 2.1 HTML 核心内容抽取库选择

基于 `docs/html-requirement.md` 的分析，选择 **Trafilatura** 作为主要的内容抽取库：

| 库 | 选择理由 | 
|---|---|
| **Trafilatura** | ✅ 准确率高，支持工程化<br>✅ 输出结构化数据（title, author, date, text）<br>✅ 支持多种配置参数<br>✅ 社区活跃，文档完善 |
| readability-lxml | ❌ 对复杂页面效果不如 Trafilatura |
| newspaper4k | ❌ 主要针对新闻文章，适用范围有限 |

### 2.2 架构设计原则

```
本地 HTML 文件
    ↓
HTML FormatAdapter.detect()
    ↓
HTML Parser (Trafilatura)
    ↓
DocumentBlock[] (结构化内容)
    ↓
现有翻译流程 (Chunking → Translation → Export)
    ↓
翻译结果输出
```

### 2.3 扩展性设计

虽然当前版本只支持本地 HTML 文件，但架构设计考虑了未来扩展：

```python
# 接口抽象，支持多种 HTML 获取方式
class HTMLContentFetcher(Protocol):
    def fetch(self, source: str) -> str:
        ...

class LocalHTMLFetcher:
    """本地文件系统获取"""
    pass

class URLFetcher:
    """通过 URL 直接获取（静态网页）"""
    pass

class PlaywrightFetcher:
    """通过 Playwright 渲染获取（动态网页）"""
    pass
```

## 3. 详细设计

### 3.1 文件结构

```
llm_translate/
├── parser/
│   ├── __init__.py
│   ├── markdown.py
│   ├── docx.py
│   ├── html.py              # 新增：HTML 解析器
│   └── ...
├── formats/
│   ├── base.py
│   ├── markdown.py
│   ├── docx.py
│   ├── html.py              # 新增：HTML FormatAdapter
│   └── registry.py
├── html_utils/              # 新增：HTML 工具模块
│   __init__.py
│   ├── fetcher.py           # HTML 内容获取器
│   ├── extractor.py         # 核心内容提取器
│   └── structure.py         # HTML 结构解析器
```

### 3.2 核心组件设计

#### 3.2.1 HTML 内容获取器 (`html_utils/fetcher.py`)

```python
from __future__ import annotations
from pathlib import Path
from typing import Protocol

class HTMLContentFetcher(Protocol):
    """HTML 内容获取器接口"""
    
    def fetch(self, source: str) -> str:
        """获取 HTML 内容"""
        ...

class LocalHTMLFetcher:
    """本地 HTML 文件获取器"""
    
    def fetch(self, source: str) -> str:
        """从本地文件系统读取 HTML 文件"""
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"HTML file not found: {source}")
        return path.read_text(encoding="utf-8")

class URLFetcher:
    """URL 获取器（静态网页）"""
    
    def fetch(self, source: str) -> str:
        """通过 URL 获取静态网页内容"""
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        }
        response = requests.get(source, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
```

#### 3.2.2 核心内容提取器 (`html_utils/extractor.py`)

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import trafilatura

@dataclass(frozen=True)
class ExtractedContent:
    """提取的网页核心内容"""
    title: str | None
    author: str | None
    date: str | None
    text: str
    raw_html: str
    metadata: dict[str, Any]

class HTMLContentExtractor:
    """HTML 核心内容提取器"""
    
    def __init__(
        self,
        include_comments: bool = False,
        include_tables: bool = True,
        favor_precision: bool = True,
    ):
        self.include_comments = include_comments
        self.include_tables = include_tables
        self.favor_precision = favor_precision
    
    def extract(self, html: str, url: str | None = None) -> ExtractedContent:
        """从 HTML 中提取核心内容"""
        # 使用 trafilatura 进行结构化提取
        result = trafilatura.bare_extraction(
            html,
            url=url,
            include_comments=self.include_comments,
            include_tables=self.include_tables,
            favor_precision=self.favor_precision,
        )
        
        if not result or not result.get("text"):
            # 如果结构化提取失败，使用基本的文本提取
            text = trafilatura.extract(
                html,
                include_comments=self.include_comments,
                include_tables=self.include_tables,
                favor_precision=self.favor_precision,
            )
            return ExtractedContent(
                title=None,
                author=None,
                date=None,
                text=text or "",
                raw_html=html,
                metadata={},
            )
        
        return ExtractedContent(
            title=result.get("title"),
            author=result.get("author"),
            date=result.get("date"),
            text=result["text"],
            raw_html=html,
            metadata={
                "language": result.get("language"),
                "url": result.get("url"),
                "hostname": result.get("hostname"),
                "description": result.get("description"),
                "categories": result.get("categories"),
                "tags": result.get("tags"),
            },
        )
```

#### 3.2.3 HTML 结构解析器 (`html_utils/structure.py`)

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import re
from bs4 import BeautifulSoup
from ..domain import DocumentBlock

class HTMLStructureParser:
    """HTML 结构解析器，将提取的文本转换为 DocumentBlock"""
    
    HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')
    LIST_RE = re.compile(r'^\s*[-*+]\s+')
    CODE_RE = re.compile(r'^```(\w*)\s*$', re.MULTILINE)
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.blocks: list[DocumentBlock] = []
        self.order = 0
        self.heading_stack: dict[int, str] = {}
    
    def parse(self, content: str, metadata: dict[str, Any] | None = None) -> list[DocumentBlock]:
        """解析提取的文本内容为结构化 DocumentBlock"""
        lines = content.splitlines()
        index = 0
        
        while index < len(lines):
            line = lines[index]
            
            if not line.strip():
                index += 1
                continue
            
            # 识别标题（如果内容包含 markdown 格式）
            heading_match = self.HEADING_RE.match(line)
            if heading_match:
                marker, title = heading_match.groups()
                self._add_heading(line, len(marker), metadata)
                index += 1
                continue
            
            # 识别列表
            if self.LIST_RE.match(line):
                start = index
                while index < len(lines) and self.LIST_RE.match(lines[index]):
                    index += 1
                self._add_block("list", "\n".join(lines[start:index]), metadata)
                continue
            
            # 识别代码块
            if "```" in line:
                code_match = self.CODE_RE.search(line, index)
                if code_match:
                    start = index
                    index += 1
                    while index < len(lines) and "```" not in lines[index]:
                        index += 1
                    if index < len(lines):
                        index += 1
                    language = code_match.group(1) or None
                    self._add_code_block("\n".join(lines[start:index]), language, metadata)
                    continue
            
            # 处理段落
            start = index
            index += 1
            while index < len(lines):
                current = lines[index]
                if not current.strip() or self._starts_block(current):
                    break
                index += 1
            
            self._add_block("paragraph", "\n".join(lines[start:index]), metadata)
        
        return self.blocks
    
    def _add_heading(self, text: str, level: int, metadata: dict[str, Any] | None):
        """添加标题块"""
        block_id = f"{self.project_id}_h_{len(self.blocks) + 1:06d}"
        parent_id = self._get_parent_id(level)
        
        self.heading_stack[level] = block_id
        # 清除更深层级的标题
        for existing_level in list(self.heading_stack):
            if existing_level > level:
                del self.heading_stack[existing_level]
        
        self.blocks.append(DocumentBlock(
            id=block_id,
            project_id=self.project_id,
            parent_id=parent_id,
            block_order=self.order,
            block_type="heading",
            level=level,
            source_text=text,
            metadata=metadata or {},
        ))
        self.order += 1
    
    def _add_block(self, block_type: str, text: str, metadata: dict[str, Any] | None):
        """添加普通块"""
        block_id = f"{self.project_id}_p_{len(self.blocks) + 1:06d}"
        parent_id = self._get_latest_parent()
        
        self.blocks.append(DocumentBlock(
            id=block_id,
            project_id=self.project_id,
            parent_id=parent_id,
            block_order=self.order,
            block_type=block_type,
            level=None,
            source_text=text,
            metadata=metadata or {},
        ))
        self.order += 1
    
    def _add_code_block(self, text: str, language: str | None, metadata: dict[str, Any] | None):
        """添加代码块"""
        block_id = f"{self.project_id}_c_{len(self.blocks) + 1:06d}"
        parent_id = self._get_latest_parent()
        
        enhanced_metadata = metadata.copy() if metadata else {}
        enhanced_metadata["language"] = language
        
        self.blocks.append(DocumentBlock(
            id=block_id,
            project_id=self.project_id,
            parent_id=parent_id,
            block_order=self.order,
            block_type="code_block",
            level=None,
            source_text=text,
            metadata=enhanced_metadata,
        ))
        self.order += 1
    
    def _starts_block(self, line: str) -> bool:
        """判断是否是块的开始"""
        return bool(
            self.HEADING_RE.match(line) or
            self.LIST_RE.match(line) or
            "```" in line
        )
    
    def _get_parent_id(self, level: int) -> str | None:
        """获取父级 ID"""
        candidates = [
            (candidate_level, block_id)
            for candidate_level, block_id in self.heading_stack.items()
            if candidate_level < level
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]
    
    def _get_latest_parent(self) -> str | None:
        """获取最新的父级 ID"""
        if not self.heading_stack:
            return None
        nearest_level = max(self.heading_stack)
        return self.heading_stack[nearest_level]
```

#### 3.2.4 HTML 解析器 (`parser/html.py`)

```python
from __future__ import annotations
from pathlib import Path
from ..domain import DocumentBlock
from ..html_utils.fetcher import LocalHTMLFetcher
from ..html_utils.extractor import HTMLContentExtractor
from ..html_utils.structure import HTMLStructureParser

class HTMLParser:
    """HTML 文档解析器"""
    
    def __init__(
        self,
        include_comments: bool = False,
        include_tables: bool = True,
        favor_precision: bool = True,
    ):
        self.fetcher = LocalHTMLFetcher()
        self.extractor = HTMLContentExtractor(
            include_comments=include_comments,
            include_tables=include_tables,
            favor_precision=favor_precision,
        )
    
    def parse(self, project_id: str, html_path: str) -> list[DocumentBlock]:
        """解析 HTML 文件"""
        # 1. 获取 HTML 内容
        html_content = self.fetcher.fetch(html_path)
        
        # 2. 提取核心内容
        extracted = self.extractor.extract(html_content)
        
        # 3. 解析文档结构
        structure_parser = HTMLStructureParser(project_id)
        blocks = structure_parser.parse(
            extracted.text,
            metadata={
                "title": extracted.title,
                "author": extracted.author,
                "date": extracted.date,
                "source": html_path,
                **extracted.metadata,
            }
        )
        
        return blocks
```

#### 3.2.5 HTML FormatAdapter (`formats/html.py`)

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import FormatAdapter, FormatContext
from ..domain import (
    DocumentBlock,
    TranslationChunk,
    TranslationProject,
    ValidationReport,
)
from ..chunking import conservative_chunking_strategy
from ..parser.html import HTMLParser


class HTMLFormatAdapter(FormatAdapter):
    """HTML 文档格式适配器"""

    format_name = "html"

    def __init__(
        self,
        soft_input_tokens: int = 2200,
        max_input_tokens: int = 3000,
        include_comments: bool = False,
        include_tables: bool = True,
        favor_precision: bool = True,
    ):
        self.soft_input_tokens = soft_input_tokens
        self.max_input_tokens = max_input_tokens
        self.parser = HTMLParser(
            include_comments=include_comments,
            include_tables=include_tables,
            favor_precision=favor_precision,
        )

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in [".html", ".htm"]

    def parse(
        self, project: TranslationProject, context: FormatContext
    ) -> list[DocumentBlock]:
        html_path = str(context.source_path)
        return self.parser.parse(project.project_id, html_path)

    def plan_chunks(
        self, project_id: str, blocks: list[DocumentBlock]
    ) -> list[TranslationChunk]:
        return conservative_chunking_strategy(
            project_id,
            blocks,
            self.soft_input_tokens,
            self.max_input_tokens,
        )

    def prompt_document_format(self) -> str:
        return """The document is in HTML format with the following structure:
- Headings marked with # symbols (1-6 levels)
- Paragraphs as plain text
- Lists starting with - * or +
- Code blocks enclosed in triple backticks (```)

Preserve the heading hierarchy and markdown formatting in your translation."""

    def chapter_path(self, chunk: TranslationChunk) -> str | None:
        return None

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> tuple[dict[str, Path], list[ValidationReport], bool]:
        # 导出为 Markdown 格式
        from .markdown import MarkdownFormatAdapter
        
        markdown_adapter = MarkdownFormatAdapter(
            self.soft_input_tokens,
            self.max_input_tokens,
        )
        
        return markdown_adapter.export(
            project,
            context,
            blocks,
            chunks,
            reports,
            draft,
        )
```

### 3.3 依赖配置

在 `pyproject.toml` 中添加依赖：

```toml
dependencies = [
    # ... 现有依赖
    "trafilatura>=1.6.0",
    "beautifulsoup4>=4.12.0",
    "requests>=2.31.0",
]

# 可选依赖（用于未来扩展）
[project.optional-dependencies]
playwright = [
    "playwright>=1.40.0",
]
```

### 3.4 集成到注册表

修改 `formats/registry.py`：

```python
from .html import HTMLFormatAdapter

def default_format_registry(
    soft_input_tokens: int = 2200,
    max_input_tokens: int = 3000,
) -> FormatRegistry:
    return FormatRegistry(
        [
            MarkdownFormatAdapter(soft_input_tokens, max_input_tokens),
            HTMLFormatAdapter(soft_input_tokens, max_input_tokens),  # 新增
            IpynbFormatAdapter(soft_input_tokens, max_input_tokens),
            EpubFormatAdapter(soft_input_tokens, max_input_tokens),
            DocxFormatAdapter(soft_input_tokens, max_input_tokens),
        ]
    )
```

## 4. 实现计划

### Phase 1: 核心功能实现（当前）
- [x] 技术方案设计
- [ ] 实现 HTMLContentExtractor
- [ ] 实现 HTMLStructureParser
- [ ] 实现 HTMLParser
- [ ] 实现 HTMLFormatAdapter
- [ ] 集成到 FormatRegistry
- [ ] 编写单元测试

### Phase 2: 测试与优化
- [ ] 使用提供的测试文件进行端到端测试
- [ ] 性能测试与优化
- [ ] 边缘情况处理
- [ ] 文档完善

### Phase 3: 扩展功能（未来）
- [ ] 支持 URL 直接输入
- [ ] 集成 Playwright 渲染
- [ ] 支持批量处理
- [ ] 支持更多 HTML 内容类型

## 5. 测试方案

### 5.1 单元测试

```python
# tests/html/test_extractor.py
def test_html_content_extractor_basic():
    """测试基本内容提取"""
    html = """
    <html>
        <head><title>Test Document</title></head>
        <body>
            <nav>Navigation</nav>
            <main>
                <h1>Main Title</h1>
                <p>Main content paragraph</p>
            </main>
            <footer>Footer content</footer>
        </body>
    </html>
    """
    extractor = HTMLContentExtractor()
    result = extractor.extract(html)
    
    assert result.title == "Test Document"
    assert "Main content paragraph" in result.text
    assert "Navigation" not in result.text

# tests/html/test_parser.py
def test_html_parser_structure():
    """测试 HTML 结构解析"""
    parser = HTMLParser()
    blocks = parser.parse("test_project", "test.html")
    
    assert len(blocks) > 0
    assert any(b.block_type == "heading" for b in blocks)
    assert any(b.block_type == "paragraph" for b in blocks)
```

### 5.2 集成测试

```python
# tests/integration/test_html_workflow.py
def test_html_translation_workflow():
    """测试 HTML 翻译完整流程"""
    # 使用提供的测试文件
    html_path = "C:/Users/wangr/Downloads/Context Engineering for Personalization - State Management with Long-Term Memory Notes.html"
    
    # 创建翻译项目
    project = create_project_from_html(html_path)
    
    # 验证内容提取
    assert len(project.blocks) > 0
    
    # 验证分块
    chunks = plan_translation_chunks(project)
    assert len(chunks) > 0
    
    # 验证翻译
    translated = translate_chunks(chunks)
    assert len(translated) == len(chunks)
```

### 5.3 手动测试

使用 CLI 工具测试：

```bash
# 单个 HTML 文件翻译
python -m llm_translate.cli translate "C:/Users/wangr/Downloads/test.html" --target-language zh-CN

# 批量处理
python -m llm_translate.cli batch-translate ./html_files/ --target-language zh-CN
```

## 6. 性能考虑

### 6.1 处理大文件
- 使用流式处理避免内存溢出
- 对大 HTML 文件进行分块处理
- 实现进度反馈机制

### 6.2 缓存策略
- 缓存提取结果避免重复处理
- 实现增量翻译支持

### 6.3 错误处理
- 文件编码问题处理
- 损坏的 HTML 文件处理
- 网络超时处理（URL 模式）

## 7. 未来扩展

### 7.1 Playwright 集成

```python
class PlaywrightHTMLFetcher:
    """使用 Playwright 渲染动态网页"""
    
    def fetch(self, source: str) -> str:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(source, wait_until="networkidle", timeout=30000)
            html = page.content()
            browser.close()
            return html

# 使用策略模式选择获取器
class HTMLFetcherFactory:
    @staticmethod
    def create(use_playwright: bool = False) -> HTMLContentFetcher:
        if use_playwright:
            return PlaywrightHTMLFetcher()
        elif source.startswith("http"):
            return URLFetcher()
        else:
            return LocalHTMLFetcher()
```

### 7.2 支持更多输出格式
- 导出为 PDF
- 导出为 Word 文档
- 保留原始 HTML 结构的翻译版本

## 8. 文档更新

### 8.1 用户文档
在 `README.md` 中添加 HTML 翻译使用说明：

```markdown
## HTML 网页翻译

支持从本地 HTML 文件提取核心内容并进行翻译：

```bash
# 翻译 HTML 文件
python -m llm_translate.cli translate document.html

# 指定输出语言
python -m llm_translate.cli translate document.html --target-language zh-CN
```

功能特性：
- 自动提取网页核心正文内容
- 去除导航、页脚、广告等噪声
- 保留文档结构和格式
- 支持复杂网页和长文档
```

### 8.2 API 文档
为新增的类和方法添加 docstring 和类型注解。

## 9. 风险评估

| 风险 | 影响 | 缓解措施 |
|-----|------|----------|
| Trafilatura 提取不准确 | 高 | 实现多种提取策略回退机制 |
| 性能问题（大文件） | 中 | 实现流式处理和进度反馈 |
| 编码问题 | 中 | 支持多种编码检测和转换 |
| 复杂网页结构 | 低 | 后期集成 Playwright 渲染 |

## 10. 总结

本技术方案设计了一个可扩展的 HTML 网页核心内容抽取和翻译功能，具有以下特点：

1. **模块化设计**：各组件职责清晰，易于维护和测试
2. **扩展性强**：支持快速集成 Playwright 等高级功能
3. **用户体验好**：自动化程度高，处理结果准确
4. **工程化标准**：遵循现有代码规范，无缝集成

通过 Trafilatura 的强大内容提取能力，配合现有的翻译流程，能够高效地完成 HTML 文档的翻译工作。