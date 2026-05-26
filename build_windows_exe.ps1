param(
    [switch]$Clean,
    [string]$AppName = "LLMTranslate"
)

$ErrorActionPreference = "Stop"

if ($Clean) {
    Remove-Item -LiteralPath "build" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "dist\$AppName" -Recurse -Force -ErrorAction SilentlyContinue
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name $AppName `
    --collect-submodules llm_translate `
    --collect-submodules litellm `
    --collect-submodules tiktoken_ext `
    --collect-data litellm `
    --hidden-import sqlalchemy.sql.default_comparator `
    --hidden-import tiktoken_ext.openai_public `
    --hidden-import PySide6.QtSvg `
    --add-data ".env.example;." `
    "llm_translate\gui\main.py"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Built package: dist\$AppName\$AppName.exe"
