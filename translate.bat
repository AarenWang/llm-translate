@echo off
setlocal enabledelayedexpansion

REM ============================================
REM LLM Translate Interactive Translation Script
REM ============================================

echo.
echo ============================================
echo    LLM Translate - Interactive Translation
echo ============================================
echo.

REM Get input file (required)
set /p INPUT_FILE="Please enter the file path to translate: "

if "%INPUT_FILE%"=="" (
    echo [ERROR] Input file path cannot be empty!
    pause
    exit /b 1
)

if not exist "%INPUT_FILE%" (
    echo [ERROR] File does not exist: %INPUT_FILE%
    pause
    exit /b 1
)

echo [OK] Input file: %INPUT_FILE%
echo.

REM Optional: Project name
set /p PROJECT_NAME="Enter project name (default: auto_generate): "
if "%PROJECT_NAME%"=="" set PROJECT_NAME=auto_generate

REM Optional: Target language
set /p TARGET_LANG="Enter target language (default: zh-CN): "
if "%TARGET_LANG%"=="" set TARGET_LANG=zh-CN

REM Optional: LLM provider
echo.
echo Available providers: mock, litellm, deepseek
set /p PROVIDER="Enter LLM provider (default: deepseek): "
if "%PROVIDER%"=="" set PROVIDER=deepseek

REM Optional: Model name
set /p MODEL="Enter model name (default: use config): "
if "%MODEL%"=="" set MODEL=use_config

REM Optional: Environment file suffix
set /p ENV_SUFFIX="Enter env file suffix (default: none): "
if "%ENV_SUFFIX%"=="" set ENV_SUFFIX=none

REM Optional: Glossary file
set /p GLOSSARY="Enter glossary file path (optional, press Enter to skip): "

REM Optional: Database path
set /p DB_PATH="Enter database path (default: .llm_translate/translate.db): "
if "%DB_PATH%"=="" set DB_PATH=.llm_translate\translate.db

REM Optional: Workspace path
set /p WORKSPACE="Enter workspace path (default: .llm_translate/projects): "
if "%WORKSPACE%"=="" set WORKSPACE=.llm_translate\projects

echo.
echo ============================================
echo    Translation Configuration Summary
echo ============================================
echo Input File: %INPUT_FILE%
echo Project Name: %PROJECT_NAME%
echo Target Language: %TARGET_LANG%
echo LLM Provider: %PROVIDER%
echo Model: %MODEL%
echo Environment: %ENV_SUFFIX%
echo Glossary: %GLOSSARY%
echo Database: %DB_PATH%
echo Workspace: %WORKSPACE%
echo ============================================
echo.

set /p CONFIRM="Start translation? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo [CANCEL] Translation cancelled.
    pause
    exit /b 0
)

echo.
echo [START] Starting translation process...
echo.

REM Build the command
set COMMAND=python -m llm_translate.cli --db "%DB_PATH%" --workspace "%WORKSPACE%"

REM Add env parameter if specified
if not "%ENV_SUFFIX%"=="none" (
    set COMMAND=%COMMAND% --env %ENV_SUFFIX%
)

REM Add run command
set COMMAND=%COMMAND% run "%INPUT_FILE%" --name "%PROJECT_NAME%" --target-language "%TARGET_LANG%" --provider %PROVIDER%

REM Add model if specified
if not "%MODEL%"=="use_config" (
    set COMMAND=%COMMAND% --model "%MODEL%"
)

REM Add glossary if specified
if not "%GLOSSARY%"=="" (
    set COMMAND=%COMMAND% --glossary "%GLOSSARY%"
)

echo [COMMAND] Executing: %COMMAND%
echo.

REM Execute the command
%COMMAND%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Translation completed successfully!
) else (
    echo.
    echo [ERROR] Translation failed with error code: %ERRORLEVEL%
)

echo.
pause