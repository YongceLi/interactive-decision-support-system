#!/bin/bash

# Interactive Decision Support System - Development Server Script
# This script starts both the backend API server and frontend Next.js server

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a port is in use
port_in_use() {
    lsof -i :$1 >/dev/null 2>&1
}

# Function to kill processes on specific ports
cleanup_ports() {
    print_status "Cleaning up existing processes on ports 8000 and 3000..."
    
    if port_in_use 8000; then
        print_warning "Port 8000 is in use. Attempting to kill existing process..."
        lsof -ti :8000 | xargs kill -9 2>/dev/null || true
    fi
    
    if port_in_use 3000; then
        print_warning "Port 3000 is in use. Attempting to kill existing process..."
        lsof -ti :3000 | xargs kill -9 2>/dev/null || true
    fi
    
    sleep 2
}

# Function to start backend server
start_backend() {
    print_status "Starting backend API server..."
    
    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        print_error "Virtual environment not found. Please run 'python -m venv venv' first."
        exit 1
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Check if requirements are installed
    if ! python -c "import fastapi, uvicorn" 2>/dev/null; then
        print_warning "Installing Python dependencies..."
        pip install -r requirements.txt
    fi
    
    # Start the backend server using uvicorn directly for better control
    print_status "Starting FastAPI server on http://localhost:8000"
    uvicorn api.server:app --host 0.0.0.0 --port 8000 > /tmp/idss_backend.log 2>&1 &
    BACKEND_PID=$!
    
    # Wait a moment for server to start
    sleep 3
    
    # Check if backend started successfully
    if kill -0 $BACKEND_PID 2>/dev/null; then
        print_success "Backend server started successfully (PID: $BACKEND_PID)"
        print_status "Backend logs: tail -f /tmp/idss_backend.log"
    else
        print_error "Failed to start backend server"
        print_error "Check logs: cat /tmp/idss_backend.log"
        exit 1
    fi
}

# Function to start frontend server
start_frontend() {
    print_status "Starting frontend Next.js server..."
    
    # Check if Node.js is installed
    if ! command_exists node; then
        print_error "Node.js is not installed. Please install Node.js first."
        exit 1
    fi
    
    # Check if npm is installed
    if ! command_exists npm; then
        print_error "npm is not installed. Please install npm first."
        exit 1
    fi
    
    # Navigate to web directory
    cd web
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        print_warning "Installing Node.js dependencies..."
        npm install
    fi
    
    # Start the frontend server
    print_status "Starting Next.js server on http://localhost:3000"
    npm run dev > /tmp/idss_frontend.log 2>&1 &
    FRONTEND_PID=$!
    
    # Go back to root directory
    cd ..
    
    # Wait a moment for server to start
    sleep 3
    
    # Check if frontend started successfully
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        print_success "Frontend server started successfully (PID: $FRONTEND_PID)"
        print_status "Frontend logs: tail -f /tmp/idss_frontend.log"
    else
        print_error "Failed to start frontend server"
        print_error "Check logs: cat /tmp/idss_frontend.log"
        exit 1
    fi
}

# Function to handle cleanup on exit
cleanup() {
    print_status "Shutting down servers..."
    
    if [ ! -z "$BACKEND_PID" ]; then
        print_status "Stopping backend server (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null || true
        sleep 1
        # Force kill if still running
        kill -9 $BACKEND_PID 2>/dev/null || true
        print_success "Backend server stopped"
    fi
    
    if [ ! -z "$FRONTEND_PID" ]; then
        print_status "Stopping frontend server (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID 2>/dev/null || true
        sleep 1
        # Force kill if still running
        kill -9 $FRONTEND_PID 2>/dev/null || true
        print_success "Frontend server stopped"
    fi
    
    # Clean up any remaining processes
    cleanup_ports
    
    print_success "All servers stopped. Goodbye!"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Main execution
main() {
    print_status "Starting Interactive Decision Support System..."
    print_status "=============================================="
    
    # Clean up any existing processes
    cleanup_ports
    
    # Start backend server
    start_backend
    
    # Start frontend server
    start_frontend
    
    print_success "=============================================="
    print_success "Both servers are now running!"
    print_success "Backend API: http://localhost:8000"
    print_success "Frontend UI: http://localhost:3000"
    print_success "API Docs: http://localhost:8000/docs"
    print_success "=============================================="
    print_status "Press Ctrl+C to stop both servers"
    print_status ""
    print_status "View backend logs: tail -f /tmp/idss_backend.log"
    print_status "View frontend logs: tail -f /tmp/idss_frontend.log"
    print_status ""
    
    # Wait for background jobs
    while true; do
        # Check if both processes are still running
        if ! kill -0 $BACKEND_PID 2>/dev/null; then
            print_error "Backend server crashed!"
            cleanup
            exit 1
        fi
        
        if ! kill -0 $FRONTEND_PID 2>/dev/null; then
            print_error "Frontend server crashed!"
            cleanup
            exit 1
        fi
        
        sleep 2
    done
}

# Check if we're in the right directory
if [ ! -f "requirements.txt" ] || [ ! -d "web" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

# Run main function
main
