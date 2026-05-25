# PDF 文档翻译技术方案

## 1. 需求背景

PDF是最常见的文档格式之一，但其复杂性和多样性使得PDF翻译成为一项具有挑战性的任务。本设计方案针对PDF文档的特有问题，提供结构化的翻译解决方案。

### 1.1 核心需求
- 支持通过PDF检查的文档进行翻译
- 检查失败的文档提供明确的错误信息并退出
- 保持文档的逻辑结构和内容完整性
- 处理PDF特有的布局和格式问题

### 1.2 PDF翻译的挑战
PDF作为一种固定布局格式，与HTML、DOCX等结构化格式有本质区别：
- **固定布局 vs 流式布局**：PDF关注页面视觉效果，而非内容结构
- **阅读顺序 vs 提取顺序**：文本提取顺序可能与阅读顺序不一致
- **复杂排版**：多栏、浮动元素、覆盖层等增加解析难度
- **编码问题**：字体子集化导致CID字符、乱码等问题

## 2. PDF特有问题分析

### 2.1 布局结构问题

#### 2.1.1 多栏布局
**问题描述**：
- 学术论文、期刊常采用双栏或三栏布局
- 文本提取顺序通常是逐栏提取，而非逐行提取
- 导致提取的文本顺序与阅读顺序不一致

**解决方案**：
```python
class MultiColumnResolver:
    """多栏布局识别和重排序"""
    
    def detect_columns(self, page_blocks: list[TextBlock]) -> int:
        """基于文本块的x坐标分布识别栏数"""
        x_positions = [block.x0 for block in page_blocks]
        return self.cluster_x_positions(x_positions)
    
    def reorder_blocks(self, blocks: list[TextBlock], columns: int) -> list[TextBlock]:
        """将多栏文本块重新排序为阅读顺序"""
        if columns <= 1:
            return blocks
            
        # 按y坐标分组成行，每行内按x坐标排序
        rows = self.group_by_rows(blocks)
        sorted_blocks = []
        for row in rows:
            sorted_blocks.extend(sorted(row, key=lambda b: b.x0))
        return sorted_blocks
```

#### 2.1.2 页眉页脚干扰
**问题描述**：
- 页眉页脚在每个页面重复出现
- 包含页码、章节标题、文档标题等重复内容
- 影响翻译的连贯性和质量

**解决方案**：
```python
class HeaderFooterFilter:
    """页眉页脚识别和过滤"""
    
    def identify_repeating_elements(self, pages: list[PageInfo]) -> list[str]:
        """识别跨页面重复的文本模式"""
        all_headers = []
        for page in pages:
            page_headers = self.extract_top_bottom_elements(page)
            all_headers.extend(page_headers)
        
        # 统计高频重复文本
        repetition_count = Counter(all_headers)
        return [text for text, count in repetition_count.items() 
                if count >= len(pages) * 0.8]
    
    def filter_blocks(self, blocks: list[TextBlock], 
                      repeating_patterns: list[str]) -> list[TextBlock]:
        """过滤掉包含重复模式的文本块"""
        return [block for block in blocks 
                if not self.matches_repeating_pattern(block, repeating_patterns)]
```

#### 2.1.3 表格结构识别
**问题描述**：
- PDF表格没有明确的表格标记，只有视觉上的行列对齐
- 复杂表格（合并单元格、嵌套表格）难以识别
- 表格提取错误会严重影响翻译质量

**解决方案**：
```python
class TableDetector:
    """基于布局分析的表格检测"""
    
    def detect_tables(self, page: Page) -> list[TableRegion]:
        """检测页面中的表格区域"""
        # 方法1: 分析文本块的网格对齐模式
        grid_tables = self.detect_grid_aligned_tables(page)
        
        # 方法2: 检测线条元素（表格线）
        line_tables = self.detect_line_bordered_tables(page)
        
        # 合并两种方法的结果
        return self.merge_table_detections(grid_tables, line_tables)
    
    def extract_table_structure(self, region: TableRegion) -> Table:
        """从表格区域提取行列结构"""
        blocks = self.get_blocks_in_region(region)
        return self.build_table_from_blocks(blocks)
```

### 2.2 文本质量问题

#### 2.2.1 乱码和CID字符
**问题描述**：
- PDF字体子集化导致字符编码映射丢失
- 出现`(cid:123)`形式的CID标记
- 影响文本可读性和翻译准确性

**解决方案**：
```python
class CidResolver:
    """CID字符识别和处理"""
    
    def detect_cid_issues(self, text: str) -> CidReport:
        """检测CID字符问题"""
        cid_pattern = r'\(cid:\d+\)'
        cid_matches = re.findall(cid_pattern, text)
        return CidReport(
            cid_count=len(cid_matches),
            cid_ratio=len(cid_matches) / max(1, len(text.split())),
            severity=self.assess_severity(len(cid_matches), text)
        )
    
    def handle_cid_text(self, text: str) -> str:
        """处理包含CID的文本"""
        if self.has_critical_cid_issues(text):
            raise PdfTranslationError(
                "PDF contains critical CID encoding issues. "
                "Please use OCR or re-export the PDF."
            )
        return self.clean_cid_markers(text)
```

#### 2.2.2 跨页段落分割
**问题描述**：
- 一个段落可能跨越两页，在页面边界处被截断
- 句子可能在页面中间断开
- 影响翻译的上下文完整性

**解决方案**：
```python
class CrossPageMerger:
    """跨页内容重建"""
    
    def merge_cross_page_content(self, pages: list[PageContent]) -> list[ContentBlock]:
        """重建跨页的段落和句子"""
        merged_blocks = []
        pending_text = ""
        
        for i, page in enumerate(pages):
            page_text = page.text.strip()
            
            # 检查页面结尾是否是句子不完整
            if self.is_incomplete_ending(page_text) and i + 1 < len(pages):
                next_page_start = pages[i + 1].text.strip()
                
                # 检查下一页开头是否是小写字母（延续标志）
                if self.is_continuation(next_page_start):
                    # 合跨页内容
                    pending_text = page_text + " " + next_page_start
                    continue
            
            if pending_text:
                merged_blocks.append(ContentBlock(text=pending_text))
                pending_text = ""
            else:
                merged_blocks.append(ContentBlock(text=page_text))
        
        return merged_blocks
```

### 2.3 图像和特殊内容

#### 2.3.1 扫描PDF处理
**问题描述**：
- 扫描PDF本质是图像，无法直接提取文本
- 需要OCR识别，但OCR质量不稳定
- OCR结果可能包含大量错误

**解决方案**：
```python
class ScanPdfHandler:
    """扫描PDF识别和处理"""
    
    def detect_scanned_pdf(self, pdf_path: Path) -> bool:
        """检测是否为扫描PDF"""
        # 检查1: 文本内容极少
        # 检查2: 大量全页图像
        # 检查3: 高比例的图像页面
        return self.analyze_image_vs_text_ratio(pdf_path)
    
    def handle_scanned_pdf(self, pdf_path: Path) -> HandlingStrategy:
        """扫描PDF处理策略"""
        if self.detect_scanned_pdf(pdf_path):
            return HandlingStrategy(
                can_translate=False,
                reason="This appears to be a scanned PDF. OCR is required.",
                suggestion="Use OCR tools like Tesseract or Adobe Acrobat Export PDF."
            )
        return HandlingStrategy(can_translate=True)
```

#### 2.3.2 图像和图表过滤
**问题描述**：
- PDF中的图像、图表不应翻译
- 但图像周围的说明文字需要翻译
- 需要准确区分图像区域和文本区域

**解决方案**：
```python
class ImageFilter:
    """图像区域识别和过滤"""
    
    def identify_image_regions(self, page: Page) -> list[ImageRegion]:
        """识别页面中的图像区域"""
        images = []
        for image_info in page.get_images():
            bbox = image_info['bbox']
            images.append(ImageRegion(
                x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3],
                area=(bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            ))
        return images
    
    def filter_image_overlapped_text(self, blocks: list[TextBlock], 
                                     image_regions: list[ImageRegion]) -> list[TextBlock]:
        """过滤与图像重叠的文本块"""
        return [block for block in blocks 
                if not self.is_overlapped_with_images(block, image_regions)]
```

## 3. 架构设计

### 3.1 整体流程

```
PDF文档
    ↓
PDF检查 (PdfCleanlinessChecker)
    ↓
检查通过？
    ├─ 否 → 报告错误，退出
    └─ 是 ↓
PDF解析器 (PdfParser)
    ├─ 多栏解析
    ├─ 页眉页脚过滤  
    ├─ 表格识别
    └─ 跨页合并
    ↓
DocumentBlock[] (结构化内容)
    ↓
现有翻译流程
    ↓
导出策略
    ├─ Markdown (推荐)
    ├─ LaTeX (学术文档)
    └─ 简化PDF (保持基本格式)
```

### 3.2 分级处理策略

```python
class PdfProcessingStrategy:
    """基于检查结果的分级处理策略"""
    
    def get_strategy(self, report: PdfCleanlinessReport) -> ProcessingStrategy:
        """根据PDF检查报告确定处理策略"""
        
        if report.level == "VERY_CLEAN":
            return ProcessingStrategy(
                method="structured_extraction",
                preserve_formatting=True,
                handle_tables=True,
                export_format="markdown",
                confidence="high"
            )
        
        elif report.level == "CLEAN":
            return ProcessingStrategy(
                method="standard_extraction",
                preserve_formatting=True,
                handle_tables=True,
                export_format="markdown",
                confidence="medium"
            )
        
        elif report.level == "NEEDS_CLEANING":
            return ProcessingStrategy(
                method="conservative_extraction",
                preserve_formatting=False,
                handle_tables=False,
                export_format="plain_text",
                confidence="low",
                warnings=report.problems
            )
        
        else:  # NOT_RECOMMENDED or BROKEN
            raise PdfTranslationError(
                f"PDF is not suitable for translation: {report.problems}"
            )
```

### 3.3 文件结构

```
llm_translate/
├── parser/
│   └── pdf.py                    # 新增：PDF 解析器
├── formats/
│   └── pdf.py                    # 新增：PDF FormatAdapter
├── pdf_utils/                    # 新增：PDF 工具模块
│   ├── __init__.py
│   ├── layout.py                 # 布局分析（多栏、页眉页脚）
│   ├── tables.py                 # 表格检测和提取
│   ├── filters.py                # 内容过滤（图像、重复内容）
│   ├── cross_page.py             # 跨页内容处理
│   └── quality.py                # 文本质量检查
└── exporters/
    └── pdf_exporters.py          # 新增：PDF导出器
```

## 4. 核心组件设计

### 4.1 PDF解析器 (parser/pdf.py)

```python
class PdfParser:
    """PDF文档解析器"""
    
    def __init__(self):
        self.layout_resolver = MultiColumnResolver()
        self.header_footer_filter = HeaderFooterFilter()
        self.table_detector = TableDetector()
        self.cross_page_merger = CrossPageMerger()
        self.image_filter = ImageFilter()
    
    def parse(self, project_id: str, pdf_path: Path) -> PdfParseResult:
        """解析PDF文档"""
        # 1. 先进行PDF检查
        checker = PdfCleanlinessChecker()
        report = checker.check(pdf_path)
        
        if not report.can_translate_phase1:
            raise PdfTranslationError(
                f"PDF check failed: {report.problems}"
            )
        
        # 2. 根据检查结果选择处理策略
        strategy = self.get_processing_strategy(report)
        
        # 3. 执行结构化提取
        doc = self.open_pdf(pdf_path)
        pages_content = self.extract_all_pages(doc)
        
        # 4. 应用布局解析
        if strategy.handle_multi_column:
            pages_content = self.resolve_multi_column_layouts(pages_content)
        
        # 5. 过滤页眉页脚
        pages_content = self.filter_headers_footers(pages_content)
        
        # 6. 处理表格
        if strategy.handle_tables:
            tables = self.extract_tables(pages_content)
            pages_content = self.remove_table_regions(pages_content, tables)
        
        # 7. 合并跨页内容
        merged_blocks = self.merge_cross_page_content(pages_content)
        
        # 8. 转换为DocumentBlock
        blocks = self.convert_to_document_blocks(merged_blocks)
        
        return PdfParseResult(
            blocks=blocks,
            tables=tables,
            metadata=self.extract_metadata(doc),
            cleanliness_report=report
        )
```

### 4.2 PDF FormatAdapter (formats/pdf.py)

```python
class PdfFormatAdapter:
    """PDF格式适配器"""
    
    format_name = "pdf"
    
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in {'.pdf'}
    
    def parse(self, project: TranslationProject, 
              context: FormatContext) -> list[DocumentBlock]:
        """解析PDF文档"""
        parser = PdfParser()
        result = parser.parse(project.id, context.source_path)
        
        # 保存解析快照
        self.save_parse_snapshot(result, context)
        
        return result.blocks
    
    def export(self, project: TranslationProject, context: FormatContext,
               blocks: list[DocumentBlock], chunks: list[TranslationChunk],
               reports: list[ValidationReport], draft: bool) -> ExportResult:
        """导出翻译结果"""
        
        # 根据处理策略选择导出格式
        exporter = self.select_exporter(context)
        
        return exporter.export(
            project=project,
            context=context,
            blocks=blocks,
            chunks=chunks,
            reports=reports,
            draft=draft
        )
```

### 4.3 导出策略 (exporters/pdf_exporters.py)

```python
class PdfExporter(Protocol):
    """PDF导出器接口"""
    def export(self, ...) -> Path:
        ...


class MarkdownPdfExporter:
    """导出为Markdown格式（推荐）"""
    
    def export(self, project, context, blocks, chunks, reports, draft) -> Path:
        """导出为Markdown格式"""
        output_path = context.artifact_dir / f"{project.name}_translated.md"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for chunk in chunks:
                # 写入翻译内容
                for block in chunk.blocks:
                    if block.type == "heading":
                        f.write(f"{'#' * block.level} {block.translated_text}\n\n")
                    elif block.type == "paragraph":
                        f.write(f"{block.translated_text}\n\n")
                    # ... 其他类型处理
        
        return output_path


class SimplePdfExporter:
    """导出为简化PDF（保持基本格式）"""
    
    def export(self, project, context, blocks, chunks, reports, draft) -> Path:
        """使用reportlab生成简单的PDF"""
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        
        output_path = context.artifact_dir / f"{project.name}_translated.pdf"
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        
        story = []
        for chunk in chunks:
            for block in chunk.blocks:
                if block.type == "heading":
                    story.append(Paragraph(block.translated_text, self.heading_style))
                elif block.type == "paragraph":
                    story.append(Paragraph(block.translated_text, self.body_style))
                story.append(Spacer(1, 12))
        
        doc.build(story)
        return output_path
```

## 5. 错误处理和质量保证

### 5.1 检查失败处理

```python
def handle_pdf_check_failure(report: PdfCleanlinessReport) -> None:
    """处理PDF检查失败"""
    error_message = f"""
PDF Translation Error: {report.file}
Level: {report.level}
Score: {report.score:.1f}/100

Problems found:
"""
    for problem in report.problems:
        error_message += f"  - {problem}\n"
    
    error_message += f"""
Recommendations:
"""
    if report.garbled_ratio > 0.01:
        error_message += "  - PDF contains encoding issues. Try re-exporting from source.\n"
    if report.large_image_page_ratio > 0.35:
        error_message += "  - PDF appears to be scanned. OCR processing is required.\n"
    if report.suspected_multi_column_ratio > 0.30:
        error_message += "  - Multi-column layout detected. Manual review recommended.\n"
    
    print(error_message)
    sys.exit(1)
```

### 5.2 翻译质量监控

```python
class PdfTranslationMonitor:
    """PDF翻译质量监控"""
    
    def monitor_translation(self, report: PdfCleanlinessReport) -> TranslationQualityMetrics:
        """基于PDF检查报告预设翻译质量预期"""
        
        expected_quality = TranslationQualityMetrics(
            expected_accuracy=0.95 if report.level == "VERY_CLEAN" else 0.85,
            expected_formatting_loss=0.1 if report.large_image_page_ratio < 0.2 else 0.3,
            expected_table_accuracy=0.9 if report.suspected_multi_column_ratio < 0.2 else 0.7,
        )
        
        return expected_quality
```

## 6. 性能优化

### 6.1 增量处理
- 支持只处理修改过的页面
- 缓存解析结果避免重复计算

### 6.2 并行处理
- 多页面并行提取和分析
- 批量处理多个PDF文件

## 7. 测试策略

### 7.1 测试用例分类
1. **干净PDF**: 纯文本，单栏，无复杂格式
2. **学术论文**: 双栏，包含表格，引用格式
3. **技术文档**: 包含代码块，图表，多级标题
4. **扫描PDF**: 主要内容为图像
5. **编码问题PDF**: 包含CID字符，乱码

### 7.2 质量指标
- 文本提取准确率 > 95%
- 结构保持准确率 > 90%
- 翻译连通性保持率 > 95%

## 8. 使用示例

```bash
# PDF文档检查和翻译
python -m llm_translate.cli create "bitcoin.pdf" --name "Bitcoin Paper"

# 如果检查失败，会显示详细错误信息并退出
python -m llm_translate.cli create "scanned.pdf" --name "Scanned Doc"
# Error: PDF appears to be scanned. OCR is required.

# 检查通过后，正常执行翻译流程
python -m llm_translate.cli --env bigmodel run <project_id>

# 导出为Markdown格式
python -m llm_translate.cli export <project_id>
```

## 9. 未来扩展

### 9.1 OCR集成
- 集成Tesseract OCR引擎
- 支持扫描PDF的文本识别
- OCR质量评估和校正

### 9.2 高级格式保持
- 使用商业PDF库保持原始格式
- 精确的字体和布局重建
- 图表和公式的智能处理

### 9.3 多模态翻译
- 图像内容翻译（OCR + 翻译 + 图像生成）
- 表格智能重建
- 公式识别和翻译