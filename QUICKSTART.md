# Quick Start Guide

This guide will help you get the `mindscape-ai-local-core` repository up and running quickly.

## Prerequisites

- Python 3.9 or higher
- Node.js 18 or higher
- npm or yarn

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/mindscape-ai-local-core.git
cd mindscape-ai-local-core
```

### 2. Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Install Frontend Dependencies

```bash
cd ../web-console
npm install
```

## Configuration

### Backend Configuration

Create a `.env` file in the `backend/` directory:

```bash
# LLM Provider (choose one)
OPENAI_API_KEY=your_openai_api_key
# or
ANTHROPIC_API_KEY=your_anthropic_api_key

# Database
DATABASE_PATH=./data/mindscape.db

# Server
HOST=0.0.0.0
PORT=8000
```

### Frontend Configuration

The frontend will automatically connect to the backend at `http://localhost:8000`.

## Running the Application

### Start Backend

```bash
cd backend
python -m app.main
```

The backend will start at `http://localhost:8000`.

### Start Frontend

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

### Frontend Issues

- **Cannot connect to backend**: Ensure backend is running on port 8000
- **Build errors**: Try `npm install` again or clear `node_modules/`

## Next Steps

- Read the [Architecture Documentation](docs/architecture/README.md)
- Explore the [API Documentation](docs/api/README.md)
- Check out [Contributing Guide](CONTRIBUTING.md)

## Getting Help

- Check [GitHub Issues](https://github.com/your-org/mindscape-ai-local-core/issues)
- Read the [Documentation](docs/README.md)
- Open a new issue for bugs or questions

Happy coding! 🚀

