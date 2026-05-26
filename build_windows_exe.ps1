param(
    [switch]$Clean,
    [string]$AppName = "LLMTranslate",
    [switch]$Full
)

$ErrorActionPreference = "Stop"

if ($Clean) {
    Remove-Item -LiteralPath "build" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "dist\$AppName" -Recurse -Force -ErrorAction SilentlyContinue
}

$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onedir",
    "--name", $AppName,
    "--collect-submodules", "llm_translate",
    "--collect-submodules", "litellm",
    "--collect-submodules", "tiktoken_ext",
    "--collect-data", "litellm",
    "--hidden-import", "sqlalchemy.sql.default_comparator",
    "--hidden-import", "tiktoken_ext.openai_public",
    "--hidden-import", "PySide6.QtSvg",
    "--icon", "assets\app_icon.ico",
    "--add-data", ".env.example;.",
    "--add-data", "assets\app_icon.ico;assets"
)

if (-not $Full) {
    $excludedModules = @(
        "cv2",
        "pygame",
        "matplotlib",
        "matplotlib.backends",
        "pandas",
        "pytest",
        "py",
        "IPython",
        "jupyter",
        "notebook",
        "fastapi",
        "uvicorn",
        "starlette",
        "llm_translate.web",
        "tkinter",
        "_tkinter",
        "torch",
        "cupy",
        "dask",
        "botocore",
        "boto3",
        "sagemaker"
    )

    foreach ($module in $excludedModules) {
        $pyInstallerArgs += @("--exclude-module", $module)
    }
}

$pyInstallerArgs += "llm_translate\gui\main.py"

python @pyInstallerArgs

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$packagePath = "dist\$AppName"
$sizeBytes = (Get-ChildItem -LiteralPath $packagePath -Recurse -File | Measure-Object Length -Sum).Sum
$sizeMb = [math]::Round($sizeBytes / 1MB, 2)

Write-Host ""
Write-Host "Built package: dist\$AppName\$AppName.exe"
Write-Host "Package size: $sizeMb MB"
if (-not $Full) {
    Write-Host "Profile: slim (use -Full for untrimmed dependency collection)"
} else {
    Write-Host "Profile: full"
}
