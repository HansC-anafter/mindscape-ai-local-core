# Installation Guide

This guide will help you install and set up Mindscape AI Local Core on **Windows**, **macOS**, and **Linux**.

## Prerequisites

### Required (All Platforms)

- **Python 3.9+** (3.11+ recommended)
- **pip** (Python package manager, usually included with Python)
- **SQLite** (included with Python)
- **Git** (for cloning the repository)

### Platform-Specific Prerequisites

#### Windows
- **Python**: Download from [python.org](https://www.python.org/downloads/) or use Microsoft Store
- **Git**: Download from [git-scm.com](https://git-scm.com/download/win)
- **Command Prompt** or **PowerShell** (included with Windows)

#### macOS
- **Python**: Usually pre-installed, or install via [Homebrew](https://brew.sh/): `brew install python`
- **Git**: Usually pre-installed, or install via Homebrew: `brew install git`
- **Terminal** (included with macOS)

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

#### Linux (Fedora/RHEL)
```bash
sudo dnf install python3 python3-pip git
```

### Optional (for frontend)

- **Node.js 18+** and **npm** (if using web console)
  - **Windows/macOS**: Download from [nodejs.org](https://nodejs.org/)
  - **Linux**: `sudo apt install nodejs npm` (Ubuntu/Debian) or `sudo dnf install nodejs npm` (Fedora)

### LLM Provider API Key

You need an API key from at least one LLM provider:

- **OpenAI API key** (recommended) - Supports GPT-4, GPT-3.5-turbo, etc.
- **Anthropic API key** (alternative) - Supports Claude 3 models
- **Google Vertex AI** (alternative) - Supports Gemini models

> **Note**: See [LLM Provider Configuration Guide](../guides/llm-providers.md) for detailed setup instructions.

## Installation Steps

### 1. Clone the Repository

**All Platforms:**
```bash
git clone https://github.com/your-org/mindscape-ai-local-core.git
cd mindscape-ai-local-core
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/your-org/mindscape-ai-local-core.git
cd mindscape-ai-local-core
```

### 2. Create Virtual Environment (Recommended)

**macOS/Linux:**
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate
```

**Windows (Command Prompt):**
```cmd
REM Create virtual environment
python -m venv venv

REM Activate virtual environment
venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\Activate.ps1
```

> **Note**: If PowerShell execution policy prevents activation, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 3. Install Backend Dependencies

**All Platforms:**
```bash
cd backend
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

**macOS/Linux:**
```bash
# Copy environment template
cp ../.env.example ../.env

# Edit .env and add your API key
# Use your preferred text editor:
nano ../.env
# or
vim ../.env
# or
code ../.env  # if using VS Code
```

**Windows (Command Prompt):**
```cmd
REM Copy environment template
copy ..\\.env.example ..\\.env

REM Edit .env using notepad
notepad ..\\.env
```

**Windows (PowerShell):**
```powershell
# Copy environment template
Copy-Item ..\.env.example ..\.env

# Edit .env using notepad
notepad ..\.env
```

Add your API key to `.env`:
```env
OPENAI_API_KEY=sk-your-api-key-here
# or
ANTHROPIC_API_KEY=sk-ant-your-api-key-here
```

### 5. Initialize Database

**All Platforms:**
```bash
python -m app.init_db
```

This will create the SQLite database at `data/mindscape.db`.

### 6. (Optional) Install Frontend Dependencies

If you want to use the web console:

**All Platforms:**
```bash
cd ../web-console
npm install
```

## Running

### Start Backend

**All Platforms:**
```bash
cd backend
uvicorn app.main:app --reload
```

The backend will be available at `http://localhost:8000`.

**Alternative (using Python module):**
```bash
cd backend
python -m app.main
```

### Start Frontend (Optional)

**All Platforms:**
```bash
cd web-console
npm run dev
```

The frontend will be available at `http://localhost:3000`.

## Verify Installation

1. **Check backend**: Visit `http://localhost:8000/docs` to see the API documentation
2. **Check frontend**: Visit `http://localhost:3000` to access the web interface

## Platform-Specific Notes

### Windows

- **Path Separators**: Use backslashes (`\`) in paths, or forward slashes (`/`) work too
- **Line Endings**: Git should handle this automatically, but if you see issues, check `.gitattributes`
- **Permissions**: Make sure you have write permissions to the `data/` directory

### macOS

- **Python Version**: macOS may have an older Python version. Use `python3` explicitly
- **Permissions**: You may need to grant Terminal full disk access for file operations

### Linux

- **Python Package Manager**: Use `python3` and `pip3` explicitly
- **Permissions**: You may need `sudo` for system-wide Python packages, but prefer virtual environments
- **Database Permissions**: Ensure the `data/` directory is writable

## Troubleshooting

### Common Issues

#### 1. Import errors

**Problem**: `ModuleNotFoundError` or import errors

**Solution**:
- Make sure virtual environment is activated
- Reinstall dependencies: `pip install -r requirements.txt`
- Check Python version: `python --version` (should be 3.9+)

#### 2. Database errors

**Problem**: Database file not found or permission errors

**Solution**:
- Run `python -m app.init_db` to initialize database
- Check `data/` directory exists and is writable
- On Linux/macOS: `chmod 755 data/`

#### 3. API key errors

**Problem**: LLM API calls fail

**Solution**:
- Check `.env` file exists in project root
- Verify API key is set correctly (no extra spaces)
- Test API key with provider's API directly

#### 4. Port already in use

**Problem**: `Address already in use` error

**Solution**:
- Change port in `.env`: `PORT=8001`
- Or stop the process using the port:
  - **Linux/macOS**: `lsof -ti:8000 | xargs kill`
  - **Windows**: `netstat -ano | findstr :8000` then `taskkill /PID <pid> /F`

#### 5. Virtual environment activation fails (Windows PowerShell)

**Problem**: `ExecutionPolicy` error

**Solution**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Platform-Specific Issues

#### Windows

- **Long Paths**: Enable long path support in Git: `git config --global core.longpaths true`
- **Antivirus**: Some antivirus software may block Python scripts. Add exception if needed

#### macOS

- **Python Version**: If `python` points to Python 2, use `python3` explicitly
- **Homebrew Python**: If using Homebrew Python, ensure it's in PATH

#### Linux

- **Missing Dependencies**: Install build essentials:
  ```bash
  # Ubuntu/Debian
  sudo apt install build-essential python3-dev

  # Fedora/RHEL
  sudo dnf groupinstall "Development Tools"
  sudo dnf install python3-devel
  ```

### Getting Help

- Check [FAQ](../faq/README.md)
- Open an issue on GitHub
- Check [Troubleshooting Guide](../troubleshooting/README.md)

---

**Next Steps**: See [Quick Start Guide](./quick-start.md) to get started using Mindscape AI Local Core.

