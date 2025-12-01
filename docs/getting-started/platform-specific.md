# Platform-Specific Installation Notes

This document provides platform-specific installation notes and troubleshooting tips for **Windows**, **macOS**, and **Linux**.

---

## Windows

### Prerequisites Installation

1. **Python 3.9+**
   - Download from [python.org](https://www.python.org/downloads/)
   - **Important**: Check "Add Python to PATH" during installation
   - Verify: Open Command Prompt and run `python --version`

2. **Git**
   - Download from [git-scm.com](https://git-scm.com/download/win)
   - Use default installation options
   - Verify: `git --version`

3. **Node.js** (optional, for frontend)
   - Download from [nodejs.org](https://nodejs.org/)
   - Use LTS version
   - Verify: `node --version`

### Installation Steps

#### Using Command Prompt

```cmd
REM 1. Clone repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

REM 2. Run setup script
scripts\setup.bat

REM 3. Activate virtual environment
cd backend
venv\Scripts\activate

REM 4. Start backend
uvicorn app.main:app --reload
```

#### Using PowerShell

```powershell
# 1. Clone repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. Run setup script
.\scripts\setup.bat

# 3. Activate virtual environment
cd backend
.\venv\Scripts\Activate.ps1

# If you get execution policy error:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 4. Start backend
uvicorn app.main:app --reload
```

### Windows-Specific Issues

#### Issue: PowerShell Execution Policy

**Error**: `cannot be loaded because running scripts is disabled on this system`

**Solution**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### Issue: Long Path Names

**Error**: File path too long

**Solution**:
```cmd
git config --global core.longpaths true
```

#### Issue: Antivirus Blocking

**Error**: Antivirus blocks Python scripts

**Solution**: Add exception for project directory in antivirus settings

---

## macOS

### Prerequisites Installation

#### Using Homebrew (Recommended)

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python

# Install Git (usually pre-installed)
brew install git

# Install Node.js (optional)
brew install node
```

#### Using Official Installers

1. **Python**: Download from [python.org](https://www.python.org/downloads/macos/)
2. **Git**: Usually pre-installed, or download from [git-scm.com](https://git-scm.com/download/mac)
3. **Node.js**: Download from [nodejs.org](https://nodejs.org/)

### Installation Steps

```bash
# 1. Clone repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. Run setup script
chmod +x scripts/setup.sh
./scripts/setup.sh

# 3. Activate virtual environment
cd backend
source venv/bin/activate

# 4. Start backend
uvicorn app.main:app --reload
```

### macOS-Specific Issues

#### Issue: Python Version

**Error**: `python` points to Python 2

**Solution**: Always use `python3` explicitly:
```bash
python3 -m venv venv
source venv/bin/activate
```

#### Issue: Permission Denied

**Error**: Permission denied when creating files

**Solution**: Grant Terminal full disk access:
1. System Preferences → Security & Privacy → Privacy
2. Select "Full Disk Access"
3. Add Terminal

#### Issue: Homebrew Python Path

**Error**: Python not found after Homebrew install

**Solution**: Add to PATH in `~/.zshrc` or `~/.bash_profile`:
```bash
export PATH="/opt/homebrew/bin:$PATH"
```

---

## Linux

### Prerequisites Installation

#### Ubuntu/Debian

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
sudo apt install nodejs npm  # Optional, for frontend
```

#### Fedora/RHEL

```bash
sudo dnf install python3 python3-pip git
sudo dnf install nodejs npm  # Optional, for frontend
```

#### Arch Linux

```bash
sudo pacman -S python python-pip git
sudo pacman -S nodejs npm  # Optional, for frontend
```

### Installation Steps

```bash
# 1. Clone repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. Run setup script
chmod +x scripts/setup.sh
./scripts/setup.sh

# 3. Activate virtual environment
cd backend
source venv/bin/activate

# 4. Start backend
uvicorn app.main:app --reload
```

### Linux-Specific Issues

#### Issue: Missing Build Dependencies

**Error**: `error: Microsoft Visual C++ 14.0 or greater is required` (on Windows) or build errors (on Linux)

**Solution**:

**Ubuntu/Debian**:
```bash
sudo apt install build-essential python3-dev
```

**Fedora/RHEL**:
```bash
sudo dnf groupinstall "Development Tools"
sudo dnf install python3-devel
```

#### Issue: Permission Denied

**Error**: Permission denied when creating database

**Solution**:
```bash
chmod 755 data/
chmod 644 data/*.db  # If database exists
```

#### Issue: Python Version

**Error**: `python` points to Python 2

**Solution**: Always use `python3` explicitly:
```bash
python3 -m venv venv
source venv/bin/activate
```

---

## Cross-Platform Testing

### Verify Installation (All Platforms)

```bash
# Check Python version
python --version  # or python3 --version

# Check virtual environment
which python  # Should point to venv/bin/python (macOS/Linux)
where python  # Should point to venv\Scripts\python.exe (Windows)

# Check dependencies
pip list

# Test database
python -m app.init_db

# Test backend
uvicorn app.main:app --reload
# Visit http://localhost:8000/docs
```

---

## Common Issues (All Platforms)

### Virtual Environment Not Activated

**Symptoms**: Import errors, wrong Python version

**Solution**: Always activate virtual environment before running:
- **macOS/Linux**: `source venv/bin/activate`
- **Windows**: `venv\Scripts\activate` (CMD) or `venv\Scripts\Activate.ps1` (PowerShell)

### Port Already in Use

**Symptoms**: `Address already in use` error

**Solution**:
- Change port in `.env`: `PORT=8001`
- Or stop the process:
  - **macOS/Linux**: `lsof -ti:8000 | xargs kill`
  - **Windows**: `netstat -ano | findstr :8000` then `taskkill /PID <pid> /F`

### Database Locked

**Symptoms**: Database locked errors

**Solution**:
- Close all connections to the database
- Check if another process is using the database
- Restart the application

---

## Getting Help

- **Documentation**: See [Installation Guide](./installation.md)
- **Issues**: Open an issue on GitHub with your platform information
- **FAQ**: Check [FAQ](../faq/README.md)

---

**Last updated**: 2025-12-02

