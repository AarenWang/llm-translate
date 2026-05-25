from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, replace
from pathlib import Path
from dotenv import load_dotenv

from .config import Settings
from .llm import provider_from_name
from .service import TranslationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-translate")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--env", default=None, help="Environment file suffix (e.g., 'bigmode' loads .env-bigmode)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")
    sub.add_parser("list-projects")

    check_pdf = sub.add_parser("check-pdf")
    check_pdf.add_argument("source", type=Path)
    check_pdf.add_argument(
        "--fail-on-not-clean",
        action="store_true",
        help="Exit with status 2 when the PDF is not accepted for phase-1 translation.",
    )

    create = sub.add_parser("create")
    create.add_argument("source", type=Path)
    create.add_argument("--name", required=True)
    create.add_argument("--target-language", default=None)

    parse = sub.add_parser("parse")
    parse.add_argument("project_id")

    prepare = sub.add_parser("prepare")
    prepare.add_argument("project_id")

    glossary = sub.add_parser("import-glossary")
    glossary.add_argument("project_id")
    glossary.add_argument("glossary", type=Path)

    translate = sub.add_parser("translate")
    translate.add_argument("project_id")
    translate.add_argument("--provider", choices=["mock", "litellm", "deepseek"], default=None)
    translate.add_argument("--model", default=None)
    translate.add_argument("--api-base", default=None)
    translate.add_argument("--api-key", default=None)
    translate.add_argument("--include-need-review", action="store_true")

    export = sub.add_parser("export")
    export.add_argument("project_id")

    run = sub.add_parser("run")
    run.add_argument("source", type=Path)
    run.add_argument("--name", required=True)
    run.add_argument("--target-language", default=None)
    run.add_argument("--glossary", type=Path, default=None)
    run.add_argument("--provider", choices=["mock", "litellm", "deepseek"], default=None)
    run.add_argument("--model", default=None)
    run.add_argument("--api-base", default=None)
    run.add_argument("--api-key", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Load environment file based on --env parameter
    if args.env:
        env_file = f".env-{args.env}"
    else:
        env_file = ".env"

    # Load the environment file if it exists
    if Path(env_file).exists():
        load_dotenv(env_file, override=True)
        print(f"[INFO] Loaded environment from: {env_file}")
    else:
        print(f"[WARNING] Environment file not found: {env_file}")

    settings = Settings.from_env()
    if args.db:
        settings = replace(
            settings,
            database_path=args.db,
            workspace_path=args.workspace or settings.workspace_path,
        )
    elif args.workspace:
        settings = replace(
            settings,
            database_path=args.workspace / "translate.db",
            workspace_path=args.workspace,
        )

    service = TranslationService(settings)

    if args.command == "init-db":
        service.init_db()
        print(f"initialized database: {settings.database_path}")
        return 0

    if args.command == "list-projects":
        service.init_db()
        for project in service.store.list_projects():
            print(
                f"{project['id']} {project['status']} "
                f"{project['done_chunks'] or 0}/{project['total_chunks'] or 0} "
                f"{project['name']}"
            )
        return 0

    if args.command == "check-pdf":
        report = service.check_pdf_cleanliness(args.source)
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
        if args.fail_on_not_clean and not report.can_translate_phase1:
            return 2
        return 0

    if args.command == "create":
        project = service.create_project(args.source, args.name, args.target_language)
        print(project.id)
        return 0

    if args.command == "parse":
        service.parse_project(args.project_id)
        print("parsed")
        return 0

    if args.command == "prepare":
        service.prepare_project(args.project_id)
        print("ready")
        return 0

    if args.command == "import-glossary":
        count = service.import_glossary(args.project_id, args.glossary)
        print(f"imported {count} terms")
        return 0

    if args.command == "translate":
        provider = build_provider(args, settings)
        service.translate_project(args.project_id, provider, args.include_need_review)
        print("translated")
        return 0

    if args.command == "export":
        paths = service.export_project(args.project_id)
        for key, path in paths.items():
            print(f"{key}: {path}")
        return 0

    if args.command == "run":
        provider = build_provider(args, settings)
        project, paths = service.run(
            args.source,
            args.name,
            provider,
            target_language=args.target_language,
            glossary_path=args.glossary,
        )
        print(f"project: {project.id}")
        for key, path in paths.items():
            print(f"{key}: {path}")
        return 0

    raise AssertionError(f"unhandled command: {args.command}")


def build_provider(args: argparse.Namespace, settings: Settings):
    provider_name = args.provider or settings.llm_provider
    return provider_from_name(
        provider_name,
        model_name=args.model or settings.llm_model,
        api_base=args.api_base or settings.llm_api_base,
        api_key=args.api_key or settings.llm_api_key,
    )


if __name__ == "__main__":
    raise SystemExit(main())
