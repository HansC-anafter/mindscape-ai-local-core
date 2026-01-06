# Troubleshooting Guide

This document provides solutions for common issues when installing and running Mindscape AI Local Core.

---

## Docker Issues

### Error: Access Denied When Creating Data Directory

**Error Message**:
```
Error response from daemon: mkdir C:\WINDOWS\system32\mindscape-ai-local-core\data: Access is denied.
```

**Cause**:
The project was cloned into a Windows system directory (e.g., `C:\WINDOWS\system32\`). System directories require administrator privileges, and Docker cannot create files there without elevated permissions.

**Solution**:

1. **Move the project to a user directory**:
   ```powershell
   # Close PowerShell/terminal
   # Move the entire 'mindscape-ai-local-core' folder to one of these locations:
   # - C:\Users\YourUsername\Documents\mindscape-ai-local-core
   # - C:\Projects\mindscape-ai-local-core
   # - D:\Projects\mindscape-ai-local-core
   ```

2. **Open PowerShell in the new location**:
   ```powershell
   cd C:\Projects\mindscape-ai-local-core
   ```

3. **Run the start script again**:
   ```powershell
   .\scripts\start.ps1
   ```

**Prevention**:
- Always clone the repository to a user directory, not a system directory
- The start script now automatically detects and warns if the project is in a system directory
- Recommended clone locations:
  - `C:\Users\YourUsername\Documents\`
  - `C:\Projects\`
  - `D:\Projects\`

**Note**: Even if you run PowerShell as Administrator, it's not recommended to run the project from system directories. User directories are safer and don't require elevated privileges.

---

### Error: Docker Daemon Not Running

**Error Message**:
```
Docker daemon is not running
```

**Solution**:

1. **Start Docker Desktop**:
   - Open Docker Desktop from the Start Menu
   - Wait for it to fully start (the Docker icon in the system tray should be steady)

2. **Verify Docker is running**:
   ```powershell
   docker info
   ```

3. **If Docker Desktop won't start**:
   - Check if virtualization is enabled in BIOS
   - Ensure WSL 2 is installed and updated
   - Restart your computer

---

### Error: Port Already in Use

**Error Message**:
```
Bind for 0.0.0.0:8200 failed: port is already allocated
```

**Solution**:

1. **Find the process using the port**:
   ```powershell
   # Windows PowerShell
   netstat -ano | findstr :8200
   ```

2. **Stop the process**:
   ```powershell
   # Replace <PID> with the process ID from step 1
   taskkill /PID <PID> /F
   ```

3. **Or change the port** in `docker-compose.yml`:
   ```yaml
   ports:
     - "8201:8200"  # Change 8200 to 8201
   ```

---

### Error: Environment Variables Not Set

**Warning Message**:
```
level=warning msg="The \"OPENAI_API_KEY\" variable is not set. Defaulting to a blank string."
```

**Solution**:

1. **Create a `.env` file** in the project root:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

2. **Or set environment variables** before running:
   ```powershell
   $env:OPENAI_API_KEY="your_openai_api_key_here"
   $env:ANTHROPIC_API_KEY="your_anthropic_api_key_here"
   .\scripts\start.ps1
   ```

**Note**: API keys are optional but recommended. The application will work without them, but LLM features will be disabled.

---

## PowerShell Issues

### Error: Execution Policy Restricted

**Error Message**:
```
PowerShell execution policy is 'Restricted'
```

**Solution**:

1. **Run PowerShell as Administrator** (one-time setup):
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

2. **Or run the script with bypass**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
   ```

---

### Error: Script Path Not Found

**Error Message**:
```
cd:找不到'C:\WINDOWS\system32\mindscape-ai-local-core\mindscape-ai-local-core'路徑,因為它不存在。
```

**Cause**: The script is trying to navigate to a nested directory that doesn't exist. This usually happens when:
1. The project is in a system directory
2. The script's path resolution is incorrect

**Solution**:
1. Move the project to a user directory (see "Access Denied" section above)
2. Ensure you're running the script from the project root:
   ```powershell
   cd C:\Projects\mindscape-ai-local-core
   .\scripts\start.ps1
   ```

---

## Installation Issues

### Error: Git Clone Failed

**Error Message**:
```
fatal: could not read Username for 'https://github.com'
```

**Solution**:

1. **Use HTTPS with personal access token**:
   ```powershell
   git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
   ```

2. **Or use SSH** (if you have SSH keys set up):
   ```powershell
   git clone git@github.com:HansC-anafter/mindscape-ai-local-core.git
   ```

---

### Error: Long Path Names (Windows)

**Error Message**:
```
Filename too long
```

**Solution**:

1. **Enable long path support**:
   ```cmd
   git config --global core.longpaths true
   ```

2. **Or enable Windows long path support** (requires admin):
   - Open Group Policy Editor (`gpedit.msc`)
   - Navigate to: Computer Configuration → Administrative Templates → System → Filesystem
   - Enable "Enable Win32 long paths"

---

## Service-Specific Issues

### Backend Service Not Starting (Unhealthy)

**Symptoms**: Backend container shows "unhealthy" status or fails to start

**Solution**:

1. **Check detailed logs**:
   ```powershell
   docker compose logs backend
   ```

2. **Common causes and solutions**:

   **a. Health check timeout** (most common):
   - Backend may need more time to start
   - Wait 1-2 minutes and check again: `docker compose ps`
   - If still unhealthy, check logs for startup errors

   **b. Port 8200 already in use**:
   ```powershell
   # Check if port is in use
   netstat -ano | findstr :8200

   # Stop the process using the port (replace <PID> with process ID)
   taskkill /PID <PID> /F

   # Or change the port in docker-compose.yml
   ```

   **c. Database connection issues**:
   - Ensure PostgreSQL container is healthy: `docker compose ps postgres`
   - Check PostgreSQL logs: `docker compose logs postgres`
   - Wait for PostgreSQL to be fully ready before starting backend

   **d. Missing environment variables**:
   - API keys are optional, but check for other required variables
   - Review `.env` file if you have one

3. **Restart the service**:
   ```powershell
   docker compose restart backend
   ```

4. **Rebuild and restart** (if code changes were made):
   ```powershell
   docker compose up -d --build backend
   ```

5. **Check health endpoint manually**:
   ```powershell
   # Wait for container to start, then check health
   docker compose exec backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8200/health')"
   ```

---

### Error: ModuleNotFoundError in Backend

**Error Message**:
```
ModuleNotFoundError: No module named 'backend.app.models.runtime_environment'
ModuleNotFoundError: No module named 'backend.app.services.stores.control_profile_store'
...
```

**Cause**:
This error occurs when files exist in your local development environment but are not tracked by Git. When you clone the repository fresh, these files are missing, causing import errors.

**Why this happens**:
- **Local development**: Uses volume mount (`./backend:/app/backend:rw`), so even untracked files are accessible
- **Fresh clone**: Files not in Git are missing, causing `ModuleNotFoundError`

**Solution**:

1. **Ensure you're using the latest code**:
   ```powershell
   git pull origin master
   ```

2. **Rebuild the Docker image**:
   ```powershell
   docker compose down
   docker compose up -d --build
   ```

3. **If the error persists**, check if you're on the latest commit:
   ```powershell
   git log --oneline -5
   ```

**Prevention**:
- All core files are now tracked in Git (as of 2026-01-06)
- If you add new files, ensure they're added to Git immediately
- See [Git Tracking Issues Documentation](./git-tracking-issues-2026-01-06.md) for details

**Note**: This issue was systematically fixed on 2026-01-06. All 16 core files that were missing have been added to Git tracking.

---

### Frontend Service Not Starting

**Symptoms**: Frontend container exits or shows unhealthy status

**Solution**:

1. **Check logs**:
   ```powershell
   docker compose logs frontend
   ```

2. **Common causes**:
   - Node.js build errors
   - Missing dependencies
   - Port conflicts

3. **Rebuild the frontend**:
   ```powershell
   docker compose up -d --build frontend
   ```

---

### PostgreSQL Service Not Starting

**Symptoms**: Postgres container exits or shows unhealthy status

**Solution**:

1. **Check logs**:
   ```powershell
   docker compose logs postgres
   ```

2. **Check volume permissions**:
   ```powershell
   docker volume inspect mindscape-ai-local-core_postgres_data
   ```

3. **Reset PostgreSQL data** (⚠️ **WARNING**: This will delete all data):
   ```powershell
   docker compose down -v
   docker compose up -d postgres
   ```

---

## Getting More Help

### Check Service Status

```powershell
docker compose ps
```

### View Logs

```powershell
# All services
docker compose logs

# Specific service
docker compose logs backend
docker compose logs frontend

# Follow logs in real-time
docker compose logs -f
```

### Restart Services

```powershell
# Restart all services
docker compose restart

# Restart specific service
docker compose restart backend
```

### Stop and Remove Containers

```powershell
# Stop containers
docker compose stop

# Stop and remove containers (keeps volumes)
docker compose down

# Stop and remove containers and volumes (⚠️ deletes data)
docker compose down -v
```

---

## Additional Resources

- [Installation Guide](./installation.md)
- [Platform-Specific Notes](./platform-specific.md)
- [Docker Deployment Guide](./docker.md)
- [Git Tracking Issues Documentation](./git-tracking-issues-2026-01-06.md) - Detailed record of ModuleNotFoundError fixes
- [GitHub Issues](https://github.com/HansC-anafter/mindscape-ai-local-core/issues)

---

**Last updated**: 2026-01-06

