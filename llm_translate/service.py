from __future__ import annotations

from dataclasses import asdict
import csv
import json
from pathlib import Path
import shutil
from uuid import uuid4

from .config import DEFAULT_STYLE_GUIDE, Settings
from .domain import (
    ChunkStatus,
    GlossaryTerm,
    ProjectStatus,
    TranslationChunk,
    TranslationProject,
)
from .formats import FormatContext, FormatRegistry, default_format_registry
from .llm import LLMProvider
from .prompt import PromptBuilder
from .protection import ProtectionEngine
from .storage import SQLiteStore
from .validation import ValidationEngine


class TranslationService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = SQLiteStore(settings.database_path)
        self.formats: FormatRegistry = default_format_registry(
            settings.soft_input_tokens,
            settings.max_input_tokens,
        )
        self.protection = ProtectionEngine()
        self.prompt_builder = PromptBuilder()
        self.validator = ValidationEngine()

    def init_db(self) -> None:
        self.store.init_db()

    def create_project(
        self,
        source_path: Path,
        name: str,
        target_language: str | None = None,
    ) -> TranslationProject:
        print(f"[CREATE_PROJECT] ========================================")
        print(f"[CREATE_PROJECT] 开始创建翻译项目")
        print(f"[CREATE_PROJECT] 源文件: {source_path}")
        print(f"[CREATE_PROJECT] 项目名称: {name}")
        print(f"[CREATE_PROJECT] 目标语言: {target_language or '默认'}")

        self.init_db()
        project_id = f"prj_{uuid4().hex[:12]}"
        print(f"[CREATE_PROJECT] 生成项目ID: {project_id}")

        project_dir = self.project_dir(project_id)
        source_dir = project_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        destination = source_dir / source_path.name
        print(f"[CREATE_PROJECT] 复制源文件: {source_path.name}")
        shutil.copyfile(source_path, destination)

        # 检测文件格式
        input_format = self.formats.detect_name(source_path)
        print(f"[CREATE_PROJECT] 检测到输入格式: {input_format}")

        target_language = target_language or self.settings.default_target_language
        print(f"[CREATE_PROJECT] 目标语言: {target_language}")

        project = TranslationProject(
            id=project_id,
            name=name,
            source_file_name=source_path.name,
            source_language=None,
            target_language=target_language,
            input_format=input_format,
            status=ProjectStatus.CREATED,
            prompt_version=self.settings.prompt_version,
            protection_policy_version=self.settings.protection_policy_version,
        )

        self.store.create_project(project)
        print(f"[CREATE_PROJECT] [OK] 项目创建完成")
        print(f"[CREATE_PROJECT] 项目目录: {project_dir}")
        print(f"[CREATE_PROJECT] ========================================")

        return project

    def parse_project(self, project_id: str) -> None:
        print(f"[PARSE_PROJECT] ========================================")
        print(f"[PARSE_PROJECT] 开始解析项目")
        print(f"[PARSE_PROJECT] 项目ID: {project_id}")

        project = self.store.get_project(project_id)
        print(f"[PARSE_PROJECT] 输入格式: {project.input_format}")
        print(f"[PARSE_PROJECT] 源文件: {project.source_file_name}")

        adapter = self.formats.get(project.input_format)
        context = self.format_context(project)

        print(f"[PARSE_PROJECT] 创建快照目录...")
        context.snapshot_dir.mkdir(parents=True, exist_ok=True)

        print(f"[PARSE_PROJECT] 正在解析文件...")
        blocks = adapter.parse(project, context)

        print(f"[PARSE_PROJECT] [OK] 解析完成，共 {len(blocks)} 个文档块")

        # 统计块类型
        block_types = {}
        for block in blocks:
            block_types[block.block_type] = block_types.get(block.block_type, 0) + 1

        print(f"[PARSE_PROJECT] 文档块类型统计:")
        for block_type, count in sorted(block_types.items()):
            print(f"[PARSE_PROJECT]   {block_type}: {count}")

        self.store.replace_blocks(project.id, blocks)
        self.store.update_project_status(project.id, ProjectStatus.PARSED)

        print(f"[PARSE_PROJECT] 项目状态更新为: PARSED")
        print(f"[PARSE_PROJECT] ========================================")

    def prepare_project(self, project_id: str) -> None:
        print(f"[PREPARE_PROJECT] ========================================")
        print(f"[PREPARE_PROJECT] 开始准备翻译")
        print(f"[PREPARE_PROJECT] 项目ID: {project_id}")

        blocks = self.store.list_blocks(project_id)
        if not blocks:
            raise ValueError("project has no parsed blocks; run parse first")

        print(f"[PREPARE_PROJECT] 已解析的文档块数: {len(blocks)}")

        project = self.store.get_project(project_id)
        adapter = self.formats.get(project.input_format)

        print(f"[PREPARE_PROJECT] 正在规划翻译分块...")
        chunks = adapter.plan_chunks(project_id, blocks)

        print(f"[PREPARE_PROJECT] [OK] 分块规划完成，共 {len(chunks)} 个翻译块")

        # 统计分块信息
        total_blocks_in_chunks = sum(len(chunk.block_ids) for chunk in chunks)
        avg_blocks_per_chunk = total_blocks_in_chunks / len(chunks) if chunks else 0

        print(f"[PREPARE_PROJECT] 分块统计:")
        print(f"[PREPARE_PROJECT]   总翻译块数: {len(chunks)}")
        print(f"[PREPARE_PROJECT]   总文档块数: {total_blocks_in_chunks}")
        print(f"[PREPARE_PROJECT]   平均每块文档数: {avg_blocks_per_chunk:.1f}")

        self.store.replace_chunks(project_id, chunks)

        # 保存分块快照
        snapshot_dir = self.project_dir(project_id) / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        chunks_file = snapshot_dir / "chunks.json"
        print(f"[PREPARE_PROJECT] 保存分块快照: {chunks_file}")
        chunks_file.write_text(
            json.dumps([asdict(chunk) for chunk in chunks], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        self.store.update_project_status(project_id, ProjectStatus.READY)
        print(f"[PREPARE_PROJECT] 项目状态更新为: READY")
        print(f"[PREPARE_PROJECT] ========================================")

    def import_glossary(self, project_id: str, glossary_path: Path) -> int:
        print(f"[IMPORT_GLOSSARY] ========================================")
        print(f"[IMPORT_GLOSSARY] 开始导入术语表")
        print(f"[IMPORT_GLOSSARY] 项目ID: {project_id}")
        print(f"[IMPORT_GLOSSARY] 术语表文件: {glossary_path}")
        print(f"[IMPORT_GLOSSARY] 文件格式: {glossary_path.suffix}")

        terms: list[GlossaryTerm] = []

        if glossary_path.suffix.lower() == ".json":
            print(f"[IMPORT_GLOSSARY] 解析JSON格式术语表...")
            data = json.loads(glossary_path.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else data.get("terms", [])
        else:
            print(f"[IMPORT_GLOSSARY] 解析CSV格式术语表...")
            with glossary_path.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

        print(f"[IMPORT_GLOSSARY] 发现 {len(rows)} 个术语条目")

        for row in rows:
            terms.append(
                GlossaryTerm(
                    id=f"gt_{uuid4().hex}",
                    project_id=project_id,
                    source_term=row["source_term"],
                    target_term=row["target_term"],
                    case_sensitive=str(row.get("case_sensitive", "true")).lower() != "false",
                    match_type=row.get("match_type", "exact"),
                    priority=int(row.get("priority", 100)),
                    locked=str(row.get("locked", "false")).lower() == "true",
                    note=row.get("note"),
                    version=row.get("version", self.settings.glossary_version),
                )
            )

        self.store.add_glossary_terms(terms)
        print(f"[IMPORT_GLOSSARY] [OK] 成功导入 {len(terms)} 个术语")

        # 统计术语信息
        case_sensitive_count = sum(1 for term in terms if term.case_sensitive)
        locked_count = sum(1 for term in terms if term.locked)

        print(f"[IMPORT_GLOSSARY] 术语统计:")
        print(f"[IMPORT_GLOSSARY]   总术语数: {len(terms)}")
        print(f"[IMPORT_GLOSSARY]   区分大小写: {case_sensitive_count}")
        print(f"[IMPORT_GLOSSARY]   锁定术语: {locked_count}")

        print(f"[IMPORT_GLOSSARY] ========================================")
        return len(terms)

    def translate_project(
        self,
        project_id: str,
        provider: LLMProvider,
        include_need_review: bool = False,
    ) -> None:
        print(f"[TRANSLATE_WORKFLOW] ========================================")
        print(f"[TRANSLATE_WORKFLOW] 开始翻译项目")
        print(f"[TRANSLATE_WORKFLOW] 项目ID: {project_id}")
        print(f"[TRANSLATE_WORKFLOW] ========================================")

        project = self.store.get_project(project_id)
        print(f"[PROJECT_INFO] 项目名称: {project.name}")
        print(f"[PROJECT_INFO] 源文件: {project.source_file_name}")
        print(f"[PROJECT_INFO] 目标语言: {project.target_language}")
        print(f"[PROJECT_INFO] 输入格式: {project.input_format}")

        statuses = {ChunkStatus.PENDING, ChunkStatus.FAILED}
        if include_need_review:
            statuses.add(ChunkStatus.NEED_REVIEW)
            print(f"[PROJECT_INFO] 包含需要审查的块")

        chunks = self.store.list_chunks(project_id, statuses=statuses)
        terms = self.store.list_glossary_terms(project_id)

        print(f"[GLOSSARY_INFO] 术语表条目数: {len(terms)}")
        print(f"[CHUNK_INFO] 待翻译块数: {len(chunks)}")

        self.store.update_project_status(project_id, ProjectStatus.TRANSLATING)
        print(f"[STATUS_UPDATE] 项目状态更新为: TRANSLATING")

        # 统计信息
        success_count = 0
        failed_count = 0
        skipped_count = 0

        print(f"[TRANSLATE_PROGRESS] 开始翻译各块...")
        print(f"[TRANSLATE_PROGRESS] ========================================")

        for index, chunk in enumerate(chunks, 1):
            total_chunks = len(chunks)
            progress_percent = (index - 1) / total_chunks * 100

            print(f"[CHUNK_{index:03d}] ========================================")
            print(f"[CHUNK_{index:03d}] 开始翻译块 {index}/{total_chunks} (进度: {progress_percent:.1f}%)")
            print(f"[CHUNK_{index:03d}] 块ID: {chunk.id}")
            print(f"[CHUNK_{index:03d}] 当前状态: {chunk.status.value}")
            print(f"[CHUNK_{index:03d}] 源文本长度: {len(chunk.source_text)} 字符")

            if chunk.status == ChunkStatus.PENDING:
                result = self._translate_chunk(project, chunk, provider, terms, index, total_chunks)
                if result == "success":
                    success_count += 1
                    print(f"[CHUNK_{index:03d}] [OK] 翻译成功")
                elif result == "failed":
                    failed_count += 1
                    print(f"[CHUNK_{index:03d}] [FAIL] 翻译失败")
                elif result == "skipped":
                    skipped_count += 1
                    print(f"[CHUNK_{index:03d}] - 跳过（已有有效翻译）")
            else:
                print(f"[CHUNK_{index:03d}] 状态不是PENDING，跳过处理")
                skipped_count += 1

            # 更新进度
            progress_percent = index / total_chunks * 100
            print(f"[CHUNK_{index:03d}] 进度: {progress_percent:.1f}% ({index}/{total_chunks})")
            print(f"[CHUNK_{index:03d}] ========================================")

            # 每翻译完一个块显示总体进度
            print(f"[TRANSLATE_PROGRESS] 总进度: {progress_percent:.1f}% | 成功: {success_count} | 失败: {failed_count} | 跳过: {skipped_count}")

        remaining = self.store.list_chunks(project_id, statuses={ChunkStatus.PENDING, ChunkStatus.FAILED})

        print(f"[TRANSLATE_PROGRESS] ========================================")
        print(f"[TRANSLATE_SUMMARY] 翻译完成")
        print(f"[TRANSLATE_SUMMARY] 总块数: {total_chunks}")
        print(f"[TRANSLATE_SUMMARY] 成功: {success_count}")
        print(f"[TRANSLATE_SUMMARY] 失败: {failed_count}")
        print(f"[TRANSLATE_SUMMARY] 跳过: {skipped_count}")
        print(f"[TRANSLATE_SUMMARY] 剩余待处理: {len(remaining)}")

        if remaining:
            self.store.update_project_status(project_id, ProjectStatus.FAILED)
            print(f"[STATUS_UPDATE] 项目状态更新为: FAILED")
        else:
            self.store.update_project_status(project_id, ProjectStatus.COMPLETED)
            print(f"[STATUS_UPDATE] 项目状态更新为: COMPLETED")

        print(f"[TRANSLATE_WORKFLOW] ========================================")
        print(f"[TRANSLATE_WORKFLOW] 项目翻译流程结束")
        print(f"[TRANSLATE_WORKFLOW] ========================================")

    def export_project(self, project_id: str) -> dict[str, Path]:
        print(f"[EXPORT_PROJECT] ========================================")
        print(f"[EXPORT_PROJECT] 开始导出翻译结果")
        print(f"[EXPORT_PROJECT] 项目ID: {project_id}")

        project = self.store.get_project(project_id)
        print(f"[EXPORT_PROJECT] 项目名称: {project.name}")

        adapter = self.formats.get(project.input_format)
        chunks = self.store.list_chunks(project_id)
        reports = self.store.list_validation_reports(project_id)

        print(f"[EXPORT_PROJECT] 翻译块数: {len(chunks)}")
        print(f"[EXPORT_PROJECT] 验证报告数: {len(reports)}")

        # 统计翻译状态
        status_counts = {}
        for chunk in chunks:
            status_counts[chunk.status.value] = status_counts.get(chunk.status.value, 0) + 1

        print(f"[EXPORT_PROJECT] 翻译状态统计:")
        for status, count in sorted(status_counts.items()):
            print(f"[EXPORT_PROJECT]   {status}: {count}")

        draft = any(chunk.status != ChunkStatus.DONE for chunk in chunks)
        blocks = self.store.list_blocks(project_id)

        print(f"[EXPORT_PROJECT] 开始导出文件...")
        print(f"[EXPORT_PROJECT] 导出模式: {'草稿模式' if draft else '正式模式'}")

        paths, reports, draft = adapter.export(
            project,
            self.format_context(project),
            blocks,
            chunks,
            reports,
            draft,
        )

        self._replace_format_reports(project_id, reports)

        print(f"[EXPORT_PROJECT] [OK] 导出完成")
        for key, path in paths.items():
            print(f"[EXPORT_PROJECT]   {key}: {path}")

        self.store.update_project_status(
            project_id,
            ProjectStatus.EXPORTED if not draft else self.store.get_project(project_id).status,
        )

        new_status = "EXPORTED" if not draft else project.status.value
        print(f"[EXPORT_PROJECT] 项目状态更新为: {new_status}")
        print(f"[EXPORT_PROJECT] ========================================")

        return paths

    def run(
        self,
        source_path: Path,
        name: str,
        provider: LLMProvider,
        target_language: str | None = None,
        glossary_path: Path | None = None,
    ) -> tuple[TranslationProject, dict[str, Path]]:
        print(f"[WORKFLOW] ========================================")
        print(f"[WORKFLOW] 开始完整翻译工作流")
        print(f"[WORKFLOW] 源文件: {source_path}")
        print(f"[WORKFLOW] 项目名称: {name}")
        print(f"[WORKFLOW] 目标语言: {target_language or '默认'}")
        print(f"[WORKFLOW] ========================================")

        # 步骤1: 创建项目
        print(f"[WORKFLOW_STEP] [1/6] 创建翻译项目...")
        project = self.create_project(source_path, name, target_language=target_language)
        print(f"[WORKFLOW_STEP] [1/6] [OK] 项目创建完成: {project.id}")

        # 步骤2: 导入术语表（如果提供）
        if glossary_path:
            print(f"[WORKFLOW_STEP] [2/6] 导入术语表...")
            term_count = self.import_glossary(project.id, glossary_path)
            print(f"[WORKFLOW_STEP] [2/6] [OK] 术语表导入完成: {term_count} 个术语")
        else:
            print(f"[WORKFLOW_STEP] [2/6] 跳过术语表导入（未提供）")

        # 步骤3: 解析项目
        print(f"[WORKFLOW_STEP] [3/6] 解析源文件...")
        self.parse_project(project.id)
        print(f"[WORKFLOW_STEP] [3/6] [OK] 文件解析完成")

        # 步骤4: 准备翻译
        print(f"[WORKFLOW_STEP] [4/6] 准备翻译分块...")
        self.prepare_project(project.id)
        print(f"[WORKFLOW_STEP] [4/6] [OK] 翻译准备完成")

        # 步骤5: 执行翻译
        print(f"[WORKFLOW_STEP] [5/6] 执行翻译...")
        self.translate_project(project.id, provider)
        print(f"[WORKFLOW_STEP] [5/6] [OK] 翻译执行完成")

        # 步骤6: 导出结果
        print(f"[WORKFLOW_STEP] [6/6] 导出翻译结果...")
        paths = self.export_project(project.id)
        print(f"[WORKFLOW_STEP] [6/6] [OK] 结果导出完成")

        for key, path in paths.items():
            print(f"[EXPORT_RESULT] {key}: {path}")

        print(f"[WORKFLOW] ========================================")
        print(f"[WORKFLOW] 完整翻译工作流完成")
        print(f"[WORKFLOW] 最终项目ID: {project.id}")
        print(f"[WORKFLOW] ========================================")

        return project, paths

    def _translate_chunk(
        self,
        project: TranslationProject,
        chunk: TranslationChunk,
        provider: LLMProvider,
        terms: list[GlossaryTerm],
        chunk_index: int = 0,
        total_chunks: int = 0,
    ) -> str:
        """翻译单个块，返回翻译结果状态。

        Args:
            project: 翻译项目
            chunk: 翻译块
            provider: LLM提供者
            terms: 术语表
            chunk_index: 当前块的索引（用于日志）
            total_chunks: 总块数（用于日志）

        Returns:
            翻译结果状态: "success", "failed", "skipped"
        """
        chunk_prefix = f"[CHUNK_{chunk_index:03d}]" if chunk_index > 0 else "[CHUNK]"

        print(f"{chunk_prefix} 开始翻译处理...")
        print(f"{chunk_prefix} 提供者: {provider.name}")
        print(f"{chunk_prefix} 模型: {provider.model_name}")

        last_error: str | None = None

        for attempt in range(chunk.retry_count, self.settings.max_retry_count + 1):
            chunk.retry_count = attempt
            print(f"{chunk_prefix} 尝试 #{attempt + 1}/{self.settings.max_retry_count + 1}")

            try:
                # 步骤1: 保护处理
                print(f"{chunk_prefix} [步骤1/6] 保护处理...")
                protected = self.protection.protect(project.id, chunk.id, chunk.source_text)
                chunk.protected_text = protected.protected_text
                chunk.status = ChunkStatus.PROTECTED
                self.store.upsert_chunk(chunk)
                self.store.replace_spans(chunk.id, protected.spans)
                print(f"{chunk_prefix} [步骤1/6] [OK] 保护处理完成，发现 {len(protected.spans)} 个保护段")

                # 步骤2: 构建提示
                print(f"{chunk_prefix} [步骤2/6] 构建翻译提示...")
                chapter_path = self.formats.get(project.input_format).chapter_path(chunk)
                document_format = self.formats.get(project.input_format).prompt_document_format()
                prompt = self.prompt_builder.build(
                    chunk=chunk,
                    target_language=project.target_language,
                    glossary_terms=terms,
                    style_guide=DEFAULT_STYLE_GUIDE,
                    chapter_path=chapter_path,
                    document_format=document_format,
                )
                print(f"{chunk_prefix} [步骤2/6] [OK] 提示构建完成")
                print(f"{chunk_prefix} 提示长度: {len(prompt.user)} 字符")

                # 步骤3: 开始翻译
                print(f"{chunk_prefix} [步骤3/6] 调用LLM翻译...")
                chunk.status = ChunkStatus.TRANSLATING
                self.store.upsert_chunk(chunk)
                print(f"{chunk_prefix} [步骤3/6] 状态更新为 TRANSLATING")

                # 实际的LLM调用
                output = provider.translate(prompt)
                print(f"{chunk_prefix} [步骤3/6] [OK] LLM调用完成")
                print(f"{chunk_prefix} 翻译结果长度: {len(output)} 字符")

                # 记录尝试
                self.store.add_attempt(
                    project_id=project.id,
                    chunk_id=chunk.id,
                    provider=provider.name,
                    model_name=provider.model_name,
                    prompt_preview=prompt.user,
                    response_preview=output,
                    status="OK",
                )
                print(f"{chunk_prefix} [步骤4/6] [OK] 翻译尝试已记录")

                # 步骤5: 保存翻译结果
                chunk.target_text = output
                chunk.model_name = provider.model_name
                chunk.status = ChunkStatus.TRANSLATED
                self.store.upsert_chunk(chunk)
                print(f"{chunk_prefix} [步骤5/6] [OK] 翻译结果已保存")

                # 步骤6: 恢复保护和验证
                print(f"{chunk_prefix} [步骤6/6] 恢复保护内容并验证...")
                chunk.restored_text = self.protection.restore(output, protected.spans)
                chunk.status = ChunkStatus.VALIDATING
                self.store.upsert_chunk(chunk)
                print(f"{chunk_prefix} [步骤6/6] 保护内容已恢复")

                # 验证翻译结果
                print(f"{chunk_prefix} 开始验证翻译结果...")
                report = self.validator.validate_chunk(chunk, terms)
                self.store.add_validation_report(report)

                if report.status == "PASS":
                    print(f"{chunk_prefix} [OK] 验证通过")
                    chunk.status = ChunkStatus.DONE
                    chunk.error_message = None
                    self.store.upsert_chunk(chunk)
                    print(f"{chunk_prefix} 状态更新为 DONE")
                    return "success"
                else:
                    print(f"{chunk_prefix} [WARN] 验证未完全通过")
                    issues_summary = "; ".join(issue["type"] for issue in report.issues)
                    print(f"{chunk_prefix} 问题: {issues_summary}")
                    last_error = issues_summary
                    # 继续尝试，除非是最后一次尝试

            except Exception as exc:
                error_message = str(exc)
                print(f"{chunk_prefix} [FAIL] 翻译过程出错: {error_message}")
                last_error = error_message

                # 记录错误尝试
                self.store.add_attempt(
                    project_id=project.id,
                    chunk_id=chunk.id,
                    provider=provider.name,
                    model_name=provider.model_name,
                    prompt_preview=chunk.protected_text or chunk.source_text,
                    response_preview=None,
                    status="ERROR",
                    error_message=last_error,
                )
                print(f"{chunk_prefix} 错误已记录到数据库")

                # 如果不是最后一次尝试，继续重试
                if attempt < self.settings.max_retry_count:
                    print(f"{chunk_prefix} 准备重试...")
                else:
                    print(f"{chunk_prefix} 已达到最大重试次数")

        # 所有尝试都失败
        print(f"{chunk_prefix} [FAIL] 所有翻译尝试均失败")
        chunk.status = ChunkStatus.FAILED
        chunk.error_message = last_error or "translation failed"
        self.store.upsert_chunk(chunk)
        print(f"{chunk_prefix} 状态更新为 FAILED")
        print(f"{chunk_prefix} 错误信息: {chunk.error_message}")

        return "failed"

    def source_path(self, project: TranslationProject) -> Path:
        return self.project_dir(project.id) / "source" / project.source_file_name

    def project_dir(self, project_id: str) -> Path:
        return self.settings.workspace_path / "projects" / project_id

    def artifact_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "artifacts"

    def format_context(self, project: TranslationProject) -> FormatContext:
        return FormatContext(
            project_dir=self.project_dir(project.id),
            artifact_dir=self.artifact_dir(project.id),
            source_path=self.source_path(project),
            snapshot_dir=self.project_dir(project.id) / "snapshots",
        )

    def _replace_format_reports(self, project_id: str, reports):
        existing = self.store.list_validation_reports(project_id)
        existing_ids = {report.id for report in existing}
        for report in reports:
            if report.id not in existing_ids:
                self.store.add_validation_report(report)
