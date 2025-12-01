@echo off
REM Mindscape AI Local Core - Setup Script for Windows
REM This script helps initialize the project for local development

echo ========================================
echo   Mindscape AI Local Core - Setup
echo ========================================
echo.

REM Check Python
echo Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9+ from python.org
    exit /b 1
)
python --version
echo [OK] Python found
echo.

REM Check Node.js (optional)
echo Checking Node.js (optional for frontend)...
node --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Node.js not found. Frontend will not be available.
    echo          Install Node.js 18+ if you want to use the web console.
) else (
    node --version
    echo [OK] Node.js found
)
echo.

REM Create data directory
echo Creating data directory...
if not exist "data" mkdir data
echo [OK] Data directory created
echo.

REM Create .env file if it doesn't exist
if not exist ".env" (
    echo Creating .env file from template...
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [OK] .env file created
        echo [NOTE] Please edit .env and add your API keys (OPENAI_API_KEY or ANTHROPIC_API_KEY)
    ) else (
        echo [WARNING] .env.example not found. Creating basic .env...
        (
            echo # LLM Provider API Keys (at least one is required^)
            echo OPENAI_API_KEY=your-openai-api-key-here
            echo # ANTHROPIC_API_KEY=your-anthropic-api-key-here
            echo.
            echo # Application Settings
            echo DEFAULT_LOCALE=en
        ) > .env
        echo [OK] Basic .env file created
    )
) else (
    echo [OK] .env file already exists
)
echo.

REM Install Python dependencies
echo Installing Python dependencies...
cd backend

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    echo [OK] Virtual environment created
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip --quiet

echo Installing dependencies...
pip install -r requirements.txt --quiet
echo [OK] Python dependencies installed

cd ..

REM Install frontend dependencies (if Node.js is available)
node --version >nul 2>&1
if not errorlevel 1 (
    if exist "web-console" (
        echo Installing frontend dependencies...
        cd web-console
        call npm install --silent
        echo [OK] Frontend dependencies installed
        cd ..
    ) else (
        echo [WARNING] web-console directory not found. Skipping frontend setup.
    )
)

REM Initialize database
echo Initializing database...
cd backend
python -m app.init_db
echo [OK] Database initialized
cd ..

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Next steps:
echo   1. Edit .env file and add your LLM API key
echo   2. Start backend: cd backend ^&^& venv\Scripts\activate ^&^& uvicorn app.main:app --reload
if exist "web-console" (
    echo   3. Start frontend: cd web-console ^&^& npm run dev
)
echo.
echo For more information, see:
echo   - Installation Guide: docs\getting-started\installation.md
echo   - Quick Start: docs\getting-started\quick-start.md
echo.

pause

