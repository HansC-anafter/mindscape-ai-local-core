# Quick Start Guide

This guide will help you get the `mindscape-ai-local-core` repository up and running quickly.

## 🚀 Fastest Way: Docker (Recommended)

**You can start the system immediately after cloning - no configuration required!**

### Prerequisites

- **Docker Desktop** installed and running ([Download Docker](https://docs.docker.com/get-docker/))
- At least **4GB RAM** available for Docker

### Quick Start Steps

**Windows PowerShell:**
```powershell
# 1. Clone the repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. Start all services (includes Docker health check)
.\scripts\start.ps1
```

**Linux/macOS:**
```bash
# 1. Clone the repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. Start all services (includes Docker health check)
./scripts/start.sh
```

**Or manually:**
```bash
# 1. Clone the repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. Start all services
docker compose up -d

# 3. Check service status
docker compose ps

# 4. View logs (optional)
docker compose logs -f
```

> **Note**: The start scripts automatically check if Docker Desktop is running and provide clear instructions if it's not available.

### Access the Application

- **Web Console**: http://localhost:8300
- **Backend API**: http://localhost:8200
- **API Documentation**: http://localhost:8200/docs

> **💡 Important**: API keys are **optional** for initial startup. The system will start successfully without them. You can configure API keys later through the web interface at http://localhost:8300/settings. Some AI features will be unavailable until API keys are configured.

### Optional: Configure API Keys

If you want to configure API keys before starting (optional):

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your API keys:
   ```bash
   OPENAI_API_KEY=your_openai_api_key_here
   # or
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

3. Restart services:
   ```bash
   docker compose restart backend
   ```

---

## 📦 Manual Installation (Alternative)

If you prefer to run without Docker:

### Prerequisites

- Python 3.9 or higher
- Node.js 18 or higher
- npm or yarn

### Installation Steps

#### 1. Clone the Repository

```bash
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
```

#### 2. Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

#### 3. Install Frontend Dependencies

```bash
cd ../web-console
npm install
```

#### 4. Configure Environment (Optional)

Create a `.env` file in the project root (or use `.env.example` as a template):

```bash
# LLM Provider (optional - can be configured later via web UI)
OPENAI_API_KEY=your_openai_api_key
# or
ANTHROPIC_API_KEY=your_anthropic_api_key

# Database
DATABASE_PATH=./data/mindscape.db

# Server
HOST=0.0.0.0
PORT=8200
```

#### 5. Start Backend

```bash
cd backend
python -m app.main
```

The backend will start at `http://localhost:8200`.

#### 6. Start Frontend

In a new terminal:

```bash
cd web-console
npm run dev
```

The frontend will start at `http://localhost:3000`.

## First Steps

1. **Open the application**: Visit http://localhost:3000
2. **Create a workspace**: Click "New Workspace" to create your first workspace
3. **Start chatting**: Type a message to begin interacting with Mindscape AI

## Troubleshooting

### Backend Issues

- **Port already in use**: Change the `PORT` in `.env` file
- **Database errors**: Ensure the `data/` directory exists and is writable
- **LLM API errors**: Check your API key in `.env` file


## Next Steps

- Read the [Architecture Documentation](docs/architecture/README.md)
- Explore the [API Documentation](docs/api/README.md)
- Check out [Contributing Guide](CONTRIBUTING.md)

## Getting Help

- Check [GitHub Issues](https://github.com/HansC-anafter/mindscape-ai-local-core/issues)
- Read the [Documentation](docs/README.md)
- Open a new issue for bugs or questions

Happy coding! 🚀

