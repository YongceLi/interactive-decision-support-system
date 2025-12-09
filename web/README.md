# UI Documentation

## Table of Contents

1. [Running the Demo](#running-the-demo)
2. [Frontend Architecture](#frontend-architecture)

---

## Running the Demo

### Prerequisites

Before running the demo, ensure you have the following installed:

- **Node.js** (v18 or higher) and npm
- **Python** (3.10 or higher)
- **Neo4j** (for compatibility checking features)

### Installation Steps

#### 1. Install Python Dependencies

Create a virtual environment and install required packages:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt
```

Required Python packages include:
- FastAPI and Uvicorn for the backend API server
- LangGraph and LangChain for the agent system
- Neo4j driver for knowledge graph connectivity
- SQLAlchemy for database operations
- Jinja2 for prompt templating
- Additional dependencies listed in `requirements.txt`

#### 2. Install Node.js Dependencies

Navigate to the web directory and install frontend dependencies:

```bash
cd web
npm install
cd ..
```

The frontend uses Next.js 15.5.4, React 19.1.0, Tailwind CSS 4, and TypeScript 5.

#### 3. Configure Environment Variables

Create a `.env` file in the project root directory. Copy `.env.example` as a template:

```bash
cp .env.example .env
```

Edit `.env` and set the following required variables:

- `OPENAI_API_KEY`: Your OpenAI API key for LLM functionality
- `NEO4J_URI`: Neo4j connection URI (default: `bolt://localhost:7687` or `neo4j+s://` for Aura)
- `NEO4J_USER`: Neo4j username (default: `neo4j`)
- `NEO4J_PASSWORD`: Your Neo4j password

Optional variables:
- `RAPIDAPI_KEY`: Your RapidAPI key (only needed for populating the local database via dataset builder script)
- `TAVILY_API_KEY`: For analytical agent web search
- `IDSS_API_URL`: Backend API URL (default: `http://localhost:8000`)
- `NEXT_PUBLIC_API_URL`: Public API URL for frontend (default: `http://localhost:8000`)
- `AUTODEV_API_KEY`: Optional, for legacy vehicle image support (not used for PC parts)

#### 4. Start Neo4j (Optional but Recommended)

Neo4j is required for compatibility checking features. The startup script will attempt to start Neo4j automatically, but you can also start it manually:

**Using Docker (recommended):**
```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:latest
```

**Using Homebrew (macOS):**
```bash
brew services start neo4j
```

**Direct installation:**
```bash
neo4j start
```

**For Neo4j Aura (cloud):**
- No local installation needed
- Use the connection URI from your Aura dashboard
- Format: `neo4j+s://<instance-id>.databases.neo4j.io`

Verify Neo4j is running by checking port 7687:
```bash
lsof -i :7687
```

#### 5. Run the Development Servers

Use the provided startup script to launch both backend and frontend servers:

```bash
./start_dev.sh
```

The script will:
- Clean up any existing processes on ports 8000 and 3000
- Attempt to start Neo4j if not already running
- Start the FastAPI backend server on port 8000
- Start the Next.js frontend server on port 3000
- Monitor both servers and handle graceful shutdown on Ctrl+C

### Accessing the Application

Once both servers are running:

- **Frontend UI**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs (Swagger UI)
- **Neo4j Browser**: http://localhost:7474 (if Neo4j is running locally)

### Viewing Logs

The startup script redirects logs to temporary files:

- **Backend logs**: `tail -f /tmp/idss_backend.log`
- **Frontend logs**: `tail -f /tmp/idss_frontend.log`
- **Neo4j logs**: `tail -f /tmp/idss_neo4j.log`

Alternatively, logs are displayed in the terminal where the script is running.

### Stopping the Servers

Press `Ctrl+C` in the terminal running `start_dev.sh`. The script will:
- Stop the backend server
- Stop the frontend server
- Clean up processes on ports 8000 and 3000
- Note: Neo4j is not automatically stopped (it may be used by other processes)

### Troubleshooting

**Port Already in Use:**
```bash
# Kill processes manually
lsof -ti :8000 | xargs kill -9  # Backend
lsof -ti :3000 | xargs kill -9  # Frontend
```

**Virtual Environment Issues:**
```bash
# Recreate virtual environment
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Node.js Dependencies:**
```bash
cd web
rm -rf node_modules package-lock.json
npm install
```

**Neo4j Connection Issues:**
- Verify Neo4j is running: `docker ps | grep neo4j` or `neo4j status`
- Check credentials in `.env` file match Neo4j configuration
- Test connection: `cypher-shell -u neo4j -p your-password`
- For Aura: Verify connection URI format (`neo4j+s://` for secure)

**Missing Environment Variables:**
- Ensure `.env` file exists in project root
- Verify all required variables are set (check startup script output for warnings)

---

## Frontend Architecture

### Technology Stack

The frontend is built with modern web technologies:

- **Next.js 15.5.4**: React framework with App Router, server-side rendering, and API routes
- **React 19.1.0**: UI library with hooks and component-based architecture
- **TypeScript 5**: Type-safe JavaScript with static type checking
- **Tailwind CSS 4**: Utility-first CSS framework for styling
- **ESLint**: Code linting and quality checks

### Project Structure

```
web/
├── src/
│   ├── app/                    # Next.js App Router pages and API routes
│   │   ├── api/               # API route handlers (proxies to backend)
│   │   │   ├── chat/          # Chat endpoint proxy
│   │   │   │   ├── route.ts   # Standard chat endpoint
│   │   │   │   └── stream/    # Streaming chat endpoint (SSE)
│   │   │   └── vehicle-images/# Image proxy endpoint (legacy)
│   │   ├── page.tsx           # Main application page
│   │   ├── layout.tsx         # Root layout component
│   │   └── globals.css        # Global styles
│   ├── components/            # React components
│   │   ├── ChatBox.tsx        # Chat interface component
│   │   ├── ItemGrid.tsx       # Product grid display
│   │   ├── ItemDetailModal.tsx# Product detail modal
│   │   ├── FilterMenu.tsx     # Filter sidebar
│   │   ├── ComparisonTable.tsx# Comparison table component
│   │   ├── CompatibilityResult.tsx # Compatibility check display
│   │   ├── FavoritesPage.tsx  # Favorites management
│   │   └── RecommendationCarousel.tsx # Product carousel
│   ├── services/              # Service layer
│   │   ├── api.ts             # API client service
│   │   └── logging.ts         # Logging service
│   ├── types/                 # TypeScript type definitions
│   │   ├── chat.ts            # Chat-related types
│   │   └── vehicle.ts         # Product types (legacy naming)
│   ├── hooks/                 # Custom React hooks
│   │   ├── useVehicleImages.ts
│   │   └── useVerboseLoading.ts
│   └── utils/                 # Utility functions
│       └── verboseLoading.ts
├── package.json               # Node.js dependencies
├── tsconfig.json             # TypeScript configuration
├── eslint.config.mjs         # ESLint configuration
└── postcss.config.mjs        # PostCSS configuration
```

### Component Architecture

#### Main Page (`src/app/page.tsx`)

The main page component orchestrates the entire application:

- **State Management**: Uses React hooks (`useState`, `useEffect`) for local state
- **Session Management**: Maintains session ID for conversation continuity
- **Message Handling**: Processes user messages and agent responses
- **Streaming Support**: Handles Server-Sent Events (SSE) for real-time updates
- **Product Display**: Manages product recommendations and filtering
- **UI Layout**: Coordinates chat interface, product grid, filters, and modals

Key features:
- Real-time streaming responses via SSE
- Markdown parsing for agent responses
- Progress indicators during agent processing
- Compatibility result rendering
- Comparison table display

#### API Routes (`src/app/api/`)

Next.js API routes act as proxies to the backend FastAPI server:

**`/api/chat/route.ts`**: Standard chat endpoint
- Forwards POST requests to backend `/chat` endpoint
- Handles error responses and status codes
- Returns JSON responses

**`/api/chat/stream/route.ts`**: Streaming chat endpoint
- Forwards POST requests to backend `/chat/stream` endpoint
- Passes through Server-Sent Events (SSE) stream
- Maintains streaming headers (`text/event-stream`, `no-cache`)

**`/api/vehicle-images/route.ts`**: Image proxy endpoint (legacy)
- Fetches product images from external APIs
- Handles CORS and authentication
- Returns image data with appropriate headers
- Note: Currently used for legacy vehicle image support, may be deprecated

#### Components

**ChatBox** (`components/ChatBox.tsx`):
- Displays conversation messages
- Handles user input and message sending
- Renders markdown-formatted agent responses
- Supports quick replies and suggested follow-ups

**ItemGrid** (`components/ItemGrid.tsx`):
- Displays products in a responsive grid layout
- Shows product cards with images, titles, prices
- Handles product selection for detail view

**ItemDetailModal** (`components/ItemDetailModal.tsx`):
- Modal dialog for product details
- Displays full product specifications
- Shows compatibility information
- Handles favorite/unfavorite actions

**FilterMenu** (`components/FilterMenu.tsx`):
- Sidebar filter interface
- Price range, category, brand filters
- Applies filters to product display

**ComparisonTable** (`components/ComparisonTable.tsx`):
- Renders tabular product comparisons
- Displays attributes side-by-side
- Supports dynamic column generation

**CompatibilityResult** (`components/CompatibilityResult.tsx`):
- Displays compatibility check results
- Shows compatible/incompatible status
- Lists compatibility types (socket, PCIe, RAM, etc.)
- Provides explanations for compatibility decisions

### Backend API Integration

#### API Service (`services/api.ts`)

The API service provides a client interface to the backend:

- **Session Management**: Maintains session ID across requests
- **Request Formatting**: Converts frontend data structures to API format
- **Response Parsing**: Converts API responses to frontend types
- **Error Handling**: Manages API errors and network failures

#### Communication Flow

1. **User Input**: User types message in chat interface
2. **Frontend API Route**: Message sent to `/api/chat/stream` (Next.js API route)
3. **Backend Proxy**: Next.js route forwards to backend `/chat/stream` endpoint
4. **Backend Processing**: FastAPI server processes message through agent system
5. **Streaming Response**: Backend streams progress updates and final response via SSE
6. **Frontend Rendering**: Frontend receives stream, updates UI in real-time
7. **Product Display**: Products, compatibility results, and comparison tables rendered

#### LLM Chat Response Parsing

The frontend handles LLM responses with custom parsing:

**Markdown Parsing** (`parseMarkdown` function):
- Converts markdown syntax to HTML
- Supports headings (`#`, `##`, `###`)
- Supports bold text (`**text**`, `*text*`)
- Supports links (`[text](url)`)
- Supports bullet lists (`•`, `-`, `*`)
- Handles line breaks and paragraph formatting

**Response Formatting** (`formatAgentResponse` function):
- Removes surrounding quotes from responses
- Normalizes bullet point formatting
- Cleans up whitespace and newlines
- Ensures proper markdown structure

**Streaming Response Handling** (`handleStreamingResponse` function):
- Reads Server-Sent Events stream
- Parses `event:` and `data:` lines
- Handles `progress` events for loading indicators
- Processes `complete` events for final responses
- Manages `error` events for error handling

**Response Structure**:
```typescript
{
  response: string;              // Agent's text response
  products: Product[];          // Recommended products
  filters: Record<string, any>;   // Applied filters
  preferences: Record<string, any>; // User preferences
  session_id: string;             // Session identifier
  interviewed: boolean;           // Interview completion status
  quick_replies?: string[];        // Quick reply options
  suggested_followups?: string[]; // Suggested follow-up questions
  comparison_table?: ComparisonTable; // Comparison data
  compatibility_result?: CompatibilityResult; // Compatibility check result
}
```

### Styling

**Tailwind CSS**: Utility-first CSS framework
- Responsive design with breakpoint utilities
- Color system with custom brand colors
- Spacing and layout utilities
- Component styling with utility classes

**Global Styles** (`globals.css`):
- Base styles and CSS variables
- Custom color definitions
- Typography settings
- Reset and normalization

### Performance Optimizations

- **Streaming Responses**: Real-time updates without full page reloads
- **Lazy Loading**: Components loaded on demand
- **Image Optimization**: Next.js image optimization
- **Code Splitting**: Automatic code splitting by Next.js
- **Caching**: API response caching where appropriate

### For production deployment:

1. **Build Frontend**: `cd web && npm run build`
2. **Start Production Server**: `npm start` in `web/` directory
3. **Configure Environment**: Set production environment variables
4. **Reverse Proxy**: Configure nginx or similar for routing
5. **HTTPS**: Enable SSL/TLS certificates
6. **CORS**: Configure CORS settings for production domain
