# Development Server Scripts

This project includes scripts to easily start both the backend API server and frontend Next.js server simultaneously.

## Quick Start

### Option 1: Use the Shell Script (macOS/Linux)
```bash
./start_dev.sh
```

### Option 2: Use the Batch Script (Windows)
```cmd
start_dev.bat
```

### Option 3: Use npm Script
```bash
cd web
npm run dev:full
```

## What the Scripts Do

1. **Clean up existing processes** on ports 8000 and 3000
2. **Start the backend server** (FastAPI) on http://localhost:8000
3. **Start the frontend server** (Next.js) on http://localhost:3000
4. **Handle graceful shutdown** when you press Ctrl+C

## Manual Setup (if scripts don't work)

### Backend Server
```bash
# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate.bat  # Windows

# Install dependencies (if needed)
pip install -r requirements.txt

# Start server
python api/server.py
```

### Frontend Server
```bash
cd web

# Install dependencies (if needed)
npm install

# Start server
npm run dev
```

## Access Points

- **Frontend UI**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## Troubleshooting

### Port Already in Use
The scripts automatically kill existing processes on ports 8000 and 3000. If you still get port conflicts:

```bash
# Kill processes manually
lsof -ti :8000 | xargs kill -9  # macOS/Linux
lsof -ti :3000 | xargs kill -9  # macOS/Linux

# Or on Windows
netstat -aon | findstr :8000
taskkill /f /pid <PID>
```

### Virtual Environment Issues
```bash
# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate.bat  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Node.js Issues
```bash
# Install Node.js dependencies
cd web
npm install
```
