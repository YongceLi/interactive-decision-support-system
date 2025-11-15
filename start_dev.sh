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

# Function to check if Neo4j is running
neo4j_running() {
    # Check if Neo4j bolt port (7687) is listening
    lsof -i :7687 >/dev/null 2>&1
}

# Function to start Neo4j
start_neo4j() {
    print_status "Checking Neo4j status..."
    
    if neo4j_running; then
        print_success "Neo4j is already running"
        return 0
    fi
    
    print_status "Neo4j is not running. Attempting to start..."
    
    # Try different methods to start Neo4j
    if command_exists neo4j; then
        # Neo4j installed via Homebrew or direct installation
        print_status "Starting Neo4j using 'neo4j start'..."
        neo4j start > /tmp/idss_neo4j.log 2>&1
        
        # Wait a bit for Neo4j to start
        sleep 5
        
        # Check if it started successfully
        if neo4j_running; then
            print_success "Neo4j started successfully"
            print_status "Neo4j logs: tail -f /tmp/idss_neo4j.log"
            return 0
        else
            print_warning "Neo4j may still be starting. Check logs: cat /tmp/idss_neo4j.log"
            print_warning "You may need to start Neo4j manually: neo4j start"
            return 1
        fi
    elif command_exists brew; then
        # Try Homebrew services
        print_status "Attempting to start Neo4j via Homebrew services..."
        if brew services list | grep -q neo4j; then
            brew services start neo4j > /tmp/idss_neo4j.log 2>&1
            sleep 5
            
            if neo4j_running; then
                print_success "Neo4j started successfully via Homebrew"
                return 0
            fi
        fi
    fi
    
    print_warning "Could not automatically start Neo4j"
    print_warning "Please start Neo4j manually:"
    print_warning "  - If installed via Homebrew: brew services start neo4j"
    print_warning "  - If installed directly: neo4j start"
    print_warning "  - Or visit: https://neo4j.com/docs/operations-manual/current/installation/"
    print_warning ""
    print_warning "The system will continue, but compatibility checking will be unavailable."
    return 1
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
    
    local PYTHON_CMD=""
    
    # Check for conda environment first
    if [ ! -z "$CONDA_DEFAULT_ENV" ]; then
        print_status "Using conda environment: $CONDA_DEFAULT_ENV"
        # Conda environment is already active, use it
        PYTHON_CMD="python"
    elif command_exists conda && [ ! -z "$CONDA_ENV_NAME" ]; then
        # Try to activate conda environment if specified
        print_status "Activating conda environment: $CONDA_ENV_NAME"
        source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null || true
        conda activate "$CONDA_ENV_NAME" 2>/dev/null && PYTHON_CMD="python" || {
            print_warning "Failed to activate conda environment '$CONDA_ENV_NAME', falling back to venv"
            PYTHON_CMD=""
        }
    fi
    
    # Fall back to venv if conda not available or not activated
    if [ -z "$PYTHON_CMD" ]; then
        # Check if virtual environment exists
        if [ ! -d "venv" ]; then
            print_error "Virtual environment not found. Please run 'python -m venv venv' first."
            print_error "Or activate your conda environment before running this script."
            exit 1
        fi
        
        # Activate virtual environment
        print_status "Using venv virtual environment"
        source venv/bin/activate
        PYTHON_CMD="python"
    fi
    
    # Check if requirements are installed
    if ! $PYTHON_CMD -c "import fastapi, uvicorn, jinja2, langgraph" 2>/dev/null; then
        print_warning "Installing Python dependencies..."
        pip install -r requirements.txt
    fi
    
    # Start the backend server using uvicorn directly for better control
    print_status "Starting FastAPI server on http://localhost:8000"
    $PYTHON_CMD -m uvicorn api.server:app --host 0.0.0.0 --port 8000 > /tmp/idss_backend.log 2>&1 &
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
    
    # Note: We don't stop Neo4j automatically as it may be used by other processes
    # Users can stop it manually with: neo4j stop or brew services stop neo4j
    
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
    
    # Start Neo4j (for compatibility checking)
    start_neo4j
    
    # Start backend server
    start_backend
    
    # Start frontend server
    start_frontend
    
    print_success "=============================================="
    print_success "All services are now running!"
    print_success "Backend API: http://localhost:8000"
    print_success "Frontend UI: http://localhost:3000"
    print_success "API Docs: http://localhost:8000/docs"
    if neo4j_running; then
        print_success "Neo4j: Running on bolt://localhost:7687"
    else
        print_warning "Neo4j: Not running (compatibility checking unavailable)"
    fi
    print_success "=============================================="
    print_status "Press Ctrl+C to stop both servers"
    print_status ""
    print_status "View backend logs: tail -f /tmp/idss_backend.log"
    print_status "View frontend logs: tail -f /tmp/idss_frontend.log"
    if neo4j_running; then
        print_status "View Neo4j logs: tail -f /tmp/idss_neo4j.log"
    fi
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
