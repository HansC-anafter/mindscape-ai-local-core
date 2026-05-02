# Platform-Specific Installation Notes

This page lists platform-specific notes for running Mindscape AI Local Core.

## Windows

Use Docker Desktop with the Linux container engine.

Recommended startup:

```powershell
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
.\scripts\start.ps1
```

If PowerShell blocks scripts, run:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Or run the startup helper with an execution-policy bypass:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Avoid cloning the repository into `C:\Windows\System32`, `Program Files`, or other protected system directories. Use a user-owned path such as:

```powershell
C:\Users\<you>\Documents\mindscape-ai-local-core
C:\Projects\mindscape-ai-local-core
D:\Projects\mindscape-ai-local-core
```

If path length causes Git checkout problems, enable long paths:

```cmd
git config --global core.longpaths true
```

## macOS

Use Docker Desktop or another Docker engine that supports Compose v2.

Recommended startup:

```bash
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
./scripts/start.sh
```

The startup helper can configure host-side companion processes and then start Compose services. For container-only startup, use:

```bash
docker compose up -d
```

On macOS, the helper starts Compose with the `control-plane` profile after the host-side checks complete.

On Apple Silicon, make sure Docker Desktop has enough memory assigned for the default service set.

## Linux

Install Docker Engine and the Compose v2 plugin for your distribution.

Recommended startup:

```bash
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
./scripts/start.sh
```

If your user is not in the Docker group, either use `sudo docker` for manual commands or configure Docker permissions according to your distribution's guidance.

The startup helper can configure systemd services for host-side companion processes when supported. For container-only startup, use:

```bash
docker compose up -d
```

On Linux, the helper starts Compose with the `control-plane` profile after the host-side checks complete.

## Optional Local Inference

The Docker configuration points Ollama URLs at `http://host.docker.internal:11434` by default. Install and run Ollama on the host only when you want local Ollama-backed models.

If your Docker engine does not provide `host.docker.internal`, set `OLLAMA_HOST` and `OLLAMA_BASE_URL` in `.env` to a reachable host address.

## Platform-Neutral Checks

After startup, verify:

```bash
docker compose ps
```

Then open:

- `http://localhost:8300`
- `http://localhost:8200/healthz`
- `http://localhost:8200/docs`
