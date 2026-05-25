@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================
echo    LLM Translate
echo ============================================
echo.

:input_file
set /p INPUT_FILE="Input file path: "

if "%INPUT_FILE%"=="" (
    echo [ERROR] Input file path cannot be empty!
    goto :input_file
)

if not exist "%INPUT_FILE%" (
    echo [ERROR] File does not exist: %INPUT_FILE%
    goto :input_file
)

echo [OK] Found file: %INPUT_FILE%
echo.

set /p PROJECT_NAME="Project name (default: translate_project): "
if "%PROJECT_NAME%"=="" set PROJECT_NAME=translate_project

set /p TARGET_LANG="Target language (default: zh-CN): "
if "%TARGET_LANG%"=="" set TARGET_LANG=zh-CN

echo.
echo Environment:
echo   Leave empty: .env
echo   bigmodel:    .env-bigmodel
set /p ENV_SUFFIX="Environment suffix (default: empty): "

if "%ENV_SUFFIX%"=="" (
    set ENV_CMD=
    set ENV_NAME=.env
) else (
    set ENV_CMD=--env !ENV_SUFFIX!
    set ENV_NAME=.env-!ENV_SUFFIX!
)

echo.
echo Provider:
echo   Leave empty: use provider from %ENV_NAME%
echo   mock/litellm/deepseek: override provider
set /p PROVIDER="Provider override (default: empty): "

if "%PROVIDER%"=="" (
    set PROVIDER_CMD=
) else (
    set PROVIDER_CMD=--provider %PROVIDER%
)

echo.
set /p GLOSSARY="Glossary CSV/JSON path (default: empty): "
if "%GLOSSARY%"=="" (
    set GLOSSARY_CMD=
) else (
    if not exist "%GLOSSARY%" (
        echo [ERROR] Glossary file does not exist: %GLOSSARY%
        pause
        exit /b 1
    )
    set GLOSSARY_CMD=--glossary "%GLOSSARY%"
)

echo.
echo [INFO] Configuration:
echo   Input:    %INPUT_FILE%
echo   Project:  %PROJECT_NAME%
echo   Target:   %TARGET_LANG%
echo   Env:      %ENV_NAME%
if "%PROVIDER%"=="" (
    echo   Provider: from environment
) else (
    echo   Provider: %PROVIDER%
)
if "%GLOSSARY%"=="" (
    echo   Glossary: none
) else (
    echo   Glossary: %GLOSSARY%
)
echo.

set /p CONFIRM="Start translation? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo [CANCEL] Translation cancelled.
    pause
    exit /b 0
)

echo.
echo [START] Starting translation...
echo.

if defined ENV_CMD (
    python -m llm_translate.cli !ENV_CMD! run "%INPUT_FILE%" --name "%PROJECT_NAME%" --target-language "%TARGET_LANG%" !PROVIDER_CMD! !GLOSSARY_CMD!
) else (
    python -m llm_translate.cli run "%INPUT_FILE%" --name "%PROJECT_NAME%" --target-language "%TARGET_LANG%" !PROVIDER_CMD! !GLOSSARY_CMD!
)

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Translation completed!
) else (
    echo.
    echo [ERROR] Translation failed (error code: %ERRORLEVEL%)
)

echo.
pause
