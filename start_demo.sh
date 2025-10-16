#!/bin/bash

# Start Demo Script for IDSS Agent Web Interface
# This script starts both the IDSS agent API server and the Next.js web interface

echo "🚀 Starting IDSS Agent Demo..."
echo "================================"

# Check if we're in the right directory
if [ ! -f "api/server.py" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Check if Python virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating Python virtual environment..."
source venv/bin/activate

# Install Python dependencies
echo "📥 Installing Python dependencies..."
pip install -r requirements.txt

# Check if Node.js dependencies are installed
if [ ! -d "web/node_modules" ]; then
    echo "📦 Installing Node.js dependencies..."
    cd web
    npm install
    cd ..
fi

# Create .env.local for web if it doesn't exist
if [ ! -f "web/.env.local" ]; then
    echo "⚙️  Creating web environment configuration..."
    cat > web/.env.local << EOF
# IDSS Agent API URL
IDSS_API_URL=http://localhost:8000

# Next.js Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF
fi

echo ""
echo "🌐 Starting services..."
echo "================================"

# Function to cleanup background processes
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $API_PID $WEB_PID 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start the IDSS API server in background
echo "🤖 Starting IDSS Agent API server on http://localhost:8000"
python api/server.py &
API_PID=$!

# Wait a moment for the API server to start
sleep 3

# Start the Next.js web interface
echo "🌐 Starting Next.js web interface on http://localhost:3000"
cd web
npm run dev &
WEB_PID=$!
cd ..

echo ""
echo "✅ Demo is running!"
echo "================================"
echo "🌐 Web Interface: http://localhost:3000"
echo "🤖 API Server:    http://localhost:8000"
echo "📚 API Docs:      http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for user to stop
wait
