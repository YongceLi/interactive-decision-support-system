# Interactive Decision Support System (IDSS)

An intelligent conversational AI assistant designed to help users discover and evaluate PC components and electronics through natural dialogue. The system employs a supervisor-based multi-agent architecture built on LangGraph, orchestrating specialized agents to deliver personalized product recommendations with compatibility checking via a Neo4j knowledge graph.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Installation and Setup](#installation-and-setup)
3. [Project Structure](#project-structure)
4. [System Architecture](#system-architecture)
5. [Knowledge Graph System](#knowledge-graph-system)
6. [Local Database](#local-database)
7. [Running the Application](#running-the-application)
8. [Testing](#testing)
9. [Configuration](#configuration)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

- **Python 3.10+** (3.13 recommended)
- **Node.js 18+** and npm
- **Neo4j** (for compatibility checking - optional but recommended)
- **OpenAI API Key** (required for LLM functionality)

### Quick Setup

```bash
# 1. Clone repository
git clone <repository-url>
cd interactive-decision-support-system

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install frontend dependencies
cd web && npm install && cd ..

# 4. Create .env file (see Environment Variables section)
cp .env.example .env
# Edit .env and add your API keys

# 5. Start Neo4j (optional but recommended)
# Using Docker:
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password neo4j:latest

# 6. Build the knowledge graph (if using PC parts)
python scripts/kg/build_kg_from_augmented.py

# 7. Start the application
./start_dev.sh
```

The application will be available at:
- **Frontend UI**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474 (if Neo4j is running)

---

## Installation and Setup

### Python Environment Setup

**Option 1: Using Conda (Recommended)**
```bash
conda create -n idss python=3.10
conda activate idss
pip install -r requirements.txt
```

**Option 2: Using venv**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Node.js Setup

```bash
cd web
npm install
cd ..
```

### Neo4j Setup

Neo4j is required for PC parts compatibility checking. The system will work without it, but compatibility features will be unavailable.

#### Option 1: Docker (Recommended)

```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:latest
```

#### Option 2: Homebrew (macOS)

```bash
brew install neo4j
brew services start neo4j
```

#### Option 3: Direct Installation

1. Download from https://neo4j.com/download/
2. Extract and run: `./bin/neo4j start`
3. Access Neo4j Browser at http://localhost:7474

#### Option 4: Neo4j Aura Cloud

1. Navigate to https://console.neo4j.io/
2. Create a free account
3. Create a database instance
4. Copy connection details to `.env` file

**Verify Neo4j is running:**
```bash
lsof -i :7687  # Should show Neo4j process
cypher-shell -u neo4j -p your-password  # Test connection
```

### Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
# Required: OpenAI API Key
OPENAI_API_KEY=your-openai-api-key-here

# Required: Neo4j Connection (for PC parts compatibility)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password

# For Neo4j Aura Cloud, use:
# NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
# NEO4J_USER=neo4j
# NEO4J_PASSWORD=your-aura-password

# Optional: Tavily API Key (for analytical agent web search)
TAVILY_API_KEY=your-tavily-api-key-here

# Optional: RapidAPI Key (only needed for populating database via dataset builder)
RAPIDAPI_KEY=your-rapidapi-key-here

# Optional: Auto.dev API Key (legacy, not currently used)
AUTODEV_API_KEY=your-autodev-api-key-here

# Optional: Backend API URL (defaults to http://localhost:8000)
IDSS_API_URL=http://localhost:8000

# Optional: Frontend API URL (defaults to http://localhost:8000)
NEXT_PUBLIC_API_URL=http://localhost:8000

# Optional: PC Parts Database Path (defaults to data/pc_parts.db)
PC_PARTS_DB=data/pc_parts.db
```

### Database Setup

The system uses two databases:

1. **Local SQLite Database** (`data/pc_parts.db`): Product catalog with prices, sellers, ratings
2. **Neo4j Knowledge Graph**: Compatibility relationships between PC components

#### Building the Local Database

The local database is populated using the dataset builder script:

```bash
python dataset_builder/fetch_pc_parts_dataset.py \
    --db-path data/pc_parts.db \
    --limit 1000
```

This script:
- Fetches products from RapidAPI Shopping API
- Normalizes product data
- Stores in SQLite with deduplication
- Supports multiple categories (CPU, GPU, motherboard, PSU, RAM, storage, case, cooling, etc.)

**Note**: The dataset builder requires a RapidAPI key. Once populated, the recommendation system uses the local database directly without requiring RapidAPI access.

#### Building the Knowledge Graph

See [Knowledge Graph System](#knowledge-graph-system) section for detailed instructions.

---

## Project Structure

```
interactive-decision-support-system/
│
├── idss_agent/                     # Core agent system
│   ├── core/
│   │   ├── agent.py                # Main entry point
│   │   ├── supervisor.py           # Supervisor orchestration
│   │   └── request_analyzer.py     # Mode delegation
│   │
│   ├── workflows/
│   │   └── interview.py            # Interview workflow
│   │
│   ├── agents/
│   │   ├── analytical.py           # Analytical ReAct agent
│   │   ├── discovery.py            # Product presentation
│   │   └── general.py              # General conversation
│   │
│   ├── processing/
│   │   ├── semantic_parser.py      # Filter extraction
│   │   ├── recommendation.py      # Product search engine
│   │   ├── recommendation_method1.py  # Method 1: Local DB + vector ranking + MMR
│   │   ├── recommendation_method2.py  # Method 2: Web search + parallel queries
│   │   ├── vector_ranker.py        # Similarity ranking
│   │   ├── diversification.py     # MMR diversification
│   │   ├── compatibility.py        # Compatibility helper functions
│   │   └── proactive_responses.py  # Proactive response generation
│   │
│   ├── tools/
│   │   ├── local_electronics_store.py  # SQLite interface
│   │   ├── kg_compatibility.py         # Neo4j knowledge graph queries
│   │   ├── pc_build.py                 # PC build configuration tools
│   │   ├── mcp_kg_server.py            # MCP server wrapper
│   │   └── zipcode_lookup.py           # Geographic lookup
│   │
│   ├── state/
│   │   └── schema.py               # State type definitions
│   │
│   └── utils/
│       ├── config.py               # Configuration management
│       ├── logger.py                # Logging utilities
│       ├── prompts.py               # Template rendering
│       └── conversation_logger.py   # Conversation logging
│
├── api/                            # FastAPI backend
│   ├── server.py                   # API server
│   └── models.py                   # Request/response models
│
├── web/                            # Next.js frontend
│   └── src/
│       ├── app/                    # Next.js App Router
│       │   ├── api/                # API route proxies
│       │   ├── page.tsx            # Main application page
│       │   └── layout.tsx          # Root layout
│       ├── components/             # React components
│       │   ├── ChatBox.tsx         # Chat interface
│       │   ├── ItemGrid.tsx        # Product grid
│       │   ├── ItemDetailModal.tsx # Product detail modal
│       │   ├── FilterMenu.tsx      # Filter sidebar
│       │   ├── ComparisonTable.tsx  # Comparison table
│       │   ├── CompatibilityResult.tsx  # Compatibility display
│       │   └── FavoritesPage.tsx   # Favorites management
│       ├── services/                # Service layer
│       │   ├── api.ts              # API client
│       │   └── logging.ts          # Logging service
│       ├── types/                  # TypeScript types
│       └── hooks/                  # Custom React hooks
│
├── config/
│   ├── agent_config.yaml           # System configuration
│   └── prompts/                    # Jinja2 templates
│       ├── semantic_parser.j2
│       ├── interview_system.j2
│       ├── discovery.j2
│       ├── analytical.j2
│       └── general.j2
│
├── data/
│   ├── pc_parts.db                 # SQLite product database
│   ├── pc_parts_augmented.db       # Augmented database with validated attributes
│   ├── compatibility_cache.db      # Cached scraped compatibility data
│   └── kg_backups/                 # Knowledge graph backups
│
├── dataset_builder/
│   ├── fetch_pc_parts_dataset.py   # Database population script
│   ├── pc_parts_attributes.json   # Attribute definitions per product type
│   └── pc_parts_schema.sql         # Database schema
│
├── scripts/
│   ├── kg/
│   │   ├── build_kg_from_augmented.py  # Build Neo4j KG from augmented DB
│   │   ├── augment_pc_parts_db.py      # Augment database with scraped attributes
│   │   ├── llm_extractor.py            # LLM-based attribute extraction
│   │   └── validate_reviewed_attributes.py  # Validate attributes
│   ├── test_recommendation.py      # Test recommendation engine
│   ├── test_recommendation_methods.py  # Test recommendation methods
│   └── demo.py                     # Demo/testing script
│
├── tests/                          # Test suites
│   └── test_kg_compatibility.py    # Knowledge graph compatibility tests
│
├── start_dev.sh                    # Development server startup script
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variables template
└── README.md                       # This file
```

---

## System Architecture

### Supervisor Agent

The supervisor agent serves as the central orchestrator, analyzing each user message to determine appropriate agent activation and response coordination.

```
User Message
    ↓
Request Analyzer
    │ - Intent Classification
    │ - Mode Detection
    │ - Analytical Question Extraction
    ↓
Semantic Parser
    │ - Filter/State Extraction
    │ - Implicit Preference Inference
    ↓
Supervisor Decision Engine
    │ - Agent Selection
    │ - Sub-Agent/Mode Delegation
    ↓
Sub-Agent Execution
    │ - Interview Workflow
    │ - Analytical Agent
    │ - Discovery Agent
    │ - Search/Recommendation
    │ - General Conversation
    ↓
Response Synthesis
    │ - Multi-Mode Integration
    │ - Output Formatting
    ↓
Unified Response to User
```

### Sub-Agent Components

#### Interview Workflow
**Purpose**: Systematic requirement gathering through guided conversation

**Implementation**: `workflows/interview.py`

**Capabilities**:
- Context-aware question generation based on missing information
- Structured preference extraction (budget, usage patterns, priorities)
- Automatic recommendation trigger upon completion
- Configurable question limit (default: 3 turns)

**Output**: Extracted filters and implicit preferences stored in state

#### Analytical Agent
**Purpose**: Research-backed insights and product comparisons

**Implementation**: `agents/analytical.py`

**Architecture**: ReAct agent with tool access including:
- Local database product search
- Neo4j knowledge graph compatibility queries
- Web search (Tavily API)
- Product detail lookup

**Capabilities**:
- Comparative analysis between products
- Compatibility checking for PC parts
- Market research and technical specifications
- Structured comparison table generation

**Output**: Analytical insights with source citations

#### Discovery Agent
**Purpose**: Conversational presentation of product recommendations

**Implementation**: `agents/discovery.py`

**Capabilities**:
- Natural language product presentation
- Context-aware follow-up questions
- Avoids redundant questions from interview phase
- Personalized recommendations based on user preferences

**Output**: Engaging product descriptions with actionable questions

#### Search/Recommendation Engine
**Purpose**: Product discovery through semantic matching and knowledge graph queries

**Implementation**: `processing/recommendation.py`

**Pipeline**:
1. **Query Routing**: Detects PC parts queries → uses Neo4j knowledge graph; other electronics → uses SQLite
2. **Filter Application**: Applies user constraints (brand, price, attributes)
3. **Consumer Filtering**: Filters out professional/workstation products, prioritizes consumer options
4. **Product Deduplication**: Removes duplicates by product ID
5. **Vector Similarity Ranking**: Ranks by relevance to user preferences
6. **Multi-dimensional Sorting**: Price, rating, relevance

**Features**:
- Automatic Neo4j/SQLite routing based on product type
- Progressive fallback strategy
- Configurable result limits (default: 20 products)
- Consumer-focused filtering (excludes professional/workstation products)

---

## Knowledge Graph System

### Overview

The knowledge graph system stores PC component products as nodes in Neo4j and creates typed compatibility relationships as edges. The system uses validated attributes from the augmented database to build accurate compatibility relationships.

### Graph Structure

**Node Labels**: `PCProduct` with type-specific labels (`:CPU`, `:GPU`, `:RAM`, etc.)

**Node Properties**:
- Core: `slug`, `name`, `product_type`, `brand`, `model`, `series`
- Pricing: `price`, `price_min`, `price_max`, `price_avg`
- Attributes: `socket`, `pcie_version`, `ram_standard`, `wattage`, `form_factor`, `chipset`, `vram`, `tdp`, etc.
- Metadata: `namespace`, `seller`, `rating`, `rating_count`, `imageurl`

**Compatibility Relationship Types**:
1. **SOCKET_COMPATIBLE_WITH**: CPU ↔ Motherboard (socket matching)
2. **RAM_COMPATIBLE_WITH**: RAM ↔ Motherboard (DDR standard matching)
3. **MEMORY_COMPATIBLE_WITH**: CPU ↔ RAM (memory controller compatibility)
4. **INTERFACE_COMPATIBLE_WITH**: Motherboard ↔ GPU (PCIe version compatibility)
5. **ELECTRICAL_COMPATIBLE_WITH**: PSU ↔ GPU/CPU (power requirements)
6. **FORM_FACTOR_COMPATIBLE_WITH**: Case ↔ Motherboard (physical size)
7. **THERMAL_COMPATIBLE_WITH**: Cooler ↔ CPU (socket + TDP capacity)

### Building the Knowledge Graph

The knowledge graph is built from the augmented database (`pc_parts_augmented.db`) which contains validated attributes from multiple sources.

#### Step 1: Augment the Database

First, augment the base database with validated attributes:

```bash
# Basic augmentation (copies data, no scraping)
python scripts/kg/augment_pc_parts_db.py --copy-only

# Full augmentation with LLM extraction (recommended)
python scripts/kg/augment_pc_parts_db.py --use-llm

# Limit for testing
python scripts/kg/augment_pc_parts_db.py --use-llm --limit 100
```

**What it does**:
- Reads products from `pc_parts.db`
- Creates `pc_parts_augmented.db` with base schema
- Scrapes attributes from multiple sources (Newegg, Amazon, Wikipedia, Manufacturer)
- Validates attributes using cross-source validation (requires at least 2 sources to agree)
- Stores validated attributes with source tracking, timestamps, and confidence scores
- Tags products for manual review if no manufacturer source is found

**Database Schema**:
- `pc_parts_augmented`: Main products table (same as `pc_parts` plus `needs_manual_review` flag)
- `product_attributes_augmented`: All attribute extractions from all sources
- `validated_attributes`: Validated attributes (agreed upon by at least 2 sources)
- `manufacturer_map`: Manufacturer documentation URL patterns

**Validation Rules**:
- Cross-source validation: At least 2 sources must agree on an attribute value
- Source priority: Manufacturer > Wikipedia > Retailers
- Manual review: Products without manufacturer sources are tagged

#### Step 2: Build Knowledge Graph from Augmented Database

Build the Neo4j knowledge graph from the augmented database:

```bash
# Build and replace entire graph
python scripts/kg/build_kg_from_augmented.py

# With custom Neo4j connection
python scripts/kg/build_kg_from_augmented.py \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password your-password

# Limit for testing
python scripts/kg/build_kg_from_augmented.py --limit 100
```

**What it does**:
- Loads products from `pc_parts_augmented.db`
- Merges attributes from:
  - Individual table columns
  - `base_attributes` JSON column
  - `validated_attributes` table (validated attributes take precedence)
- Creates `PCProduct` nodes in Neo4j with type-specific labels (`:CPU`, `:GPU`, etc.)
- Creates `ProductType` nodes and `HAS_TYPE` relationships
- Creates compatibility edges based on attribute matching:
  - Socket compatibility (CPU ↔ Motherboard)
  - RAM compatibility (RAM ↔ Motherboard, CPU ↔ RAM)
  - PCIe compatibility (GPU ↔ Motherboard)
  - Power compatibility (PSU ↔ GPU/CPU)
  - Form factor compatibility (Case ↔ Motherboard)
  - Thermal compatibility (Cooler ↔ CPU)
- Replaces entire graph (purges existing nodes first)

**Output**: Neo4j graph with product nodes and compatibility relationships

**Time**: ~2-5 minutes for 900+ products

### Querying the Knowledge Graph

The system automatically uses the knowledge graph for PC parts queries:

- **Recommendation queries** for PC parts automatically query Neo4j
- **Compatibility checking** uses Neo4j for PC components
- **PC build queries** use iterative knowledge graph traversal

**Example Cypher Queries**:

```cypher
// Find compatible GPUs for a motherboard
MATCH (mb:PCProduct {slug: "asus-rog-strix-z790-e"})-[r:INTERFACE_COMPATIBLE_WITH]-(gpu:PCProduct)
WHERE gpu.product_type = "gpu"
RETURN gpu.name, gpu.price_avg, r.board_pcie, r.gpu_requirement
ORDER BY gpu.price_avg ASC
LIMIT 10

// Find compatible PSUs for a GPU
MATCH (gpu:PCProduct {slug: "nvidia-rtx-4090"})-[r:ELECTRICAL_COMPATIBLE_WITH]-(psu:PCProduct)
WHERE psu.product_type = "psu"
RETURN psu.name, psu.wattage, r.margin_watts, r.psu_watts, r.required_watts
ORDER BY psu.price_avg ASC
LIMIT 10

// Check compatibility between two parts
MATCH (p1:PCProduct {slug: "intel-core-i9-13900k"})-[r]-(p2:PCProduct {slug: "asus-rog-strix-z790-e"})
RETURN type(r) AS relationship_type, p1.name, p2.name, r
```

### Viewing the Knowledge Graph

**Neo4j Browser**:
1. Ensure Neo4j is running
2. Navigate to http://localhost:7474
3. Log in with credentials
4. Run Cypher queries to explore the graph

**For Neo4j Aura**:
1. Log in to https://console.neo4j.io/
2. Select your database instance
3. Click "Open with Neo4j Browser"

---

## Local Database

### Database Schema

The system uses SQLite databases for product storage:

**Main Database: `data/pc_parts.db`**
- Product catalog with prices, sellers, ratings
- Used for non-PC parts and as fallback for PC parts

**Augmented Database: `data/pc_parts_augmented.db`**
- Enhanced version with validated attributes
- Used as source for knowledge graph building
- Contains cross-validated attributes from multiple sources

**Compatibility Cache: `data/compatibility_cache.db`**
- Cached scraped compatibility data
- Used during knowledge graph building

### Database Access

Products are queried through `LocalElectronicsStore` class:

**Location**: `idss_agent/tools/local_electronics_store.py`

**Methods**:
- `search_products()`: Search with filters (part_type, brand, price, attributes, etc.)
- `get_product_by_id()`: Get detailed product information

**Query Features**:
- Text search on product name, model, series
- Filter by part type, brand, price range, seller
- Technical specification filters (socket, VRAM, wattage, form factor, etc.)
- Pagination support

---

## Running the Application

### Using the Startup Script (Recommended)

The `start_dev.sh` script automates starting all services:

```bash
./start_dev.sh
```

**What it does**:
- Cleans up existing processes on ports 8000 and 3000
- Attempts to start Neo4j if not already running
- Starts FastAPI backend server on port 8000
- Starts Next.js frontend server on port 3000
- Monitors both servers and handles graceful shutdown on Ctrl+C

**Access Points**:
- Frontend UI: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474

**Viewing Logs**:
```bash
tail -f /tmp/idss_backend.log    # Backend logs
tail -f /tmp/idss_frontend.log   # Frontend logs
tail -f /tmp/idss_neo4j.log      # Neo4j logs
```

### Manual Startup

**Backend**:
```bash
python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
```

**Frontend**:
```bash
cd web
npm run dev
```

### Single Turn vs Multi-Turn

**Single Turn (Testing)**:
Use the test script for isolated recommendation testing:
```bash
python scripts/test_recommendation.py "I need a gaming CPU under $300"
```

**Multi-Turn (Full UI)**:
1. Start the application: `./start_dev.sh`
2. Open http://localhost:3000 in your browser
3. Chat with the agent through the web interface
4. The system maintains conversation state across turns
5. Use filters, favorites, and compatibility checking features

---

## Testing

### Recommendation Engine Test

Test the recommendation pipeline in isolation:

```bash
# Basic usage
python scripts/test_recommendation.py "I want a mid-range gaming CPU under $300"

# Save to file
python scripts/test_recommendation.py "I need DDR5 RAM for gaming" > results.json
```

**Output**: JSON with extracted filters, search parameters, and recommended products.

### Recommendation Methods Test

Test different recommendation methods:

```bash
python scripts/test_recommendation_methods.py
```

### Knowledge Graph Compatibility Test

Test Neo4j compatibility checking:

```bash
python -m pytest tests/test_kg_compatibility.py -v
```

**Note**: Requires Neo4j to be running and configured in `.env`.

### Demo Script

Run the interactive demo:

```bash
python scripts/demo.py
```

---

## Configuration

### System Configuration (`config/agent_config.yaml`)

#### Model Selection

```yaml
models:
  intent_classifier: gpt-4o-mini
  semantic_parser: gpt-4o-mini
  interview: gpt-4o
  discovery: gpt-4o
  analytical: gpt-4o
  general: gpt-4o-mini
```

#### System Limits

```yaml
limits:
  max_recommended_items: 20
  max_conversation_history: 10
  max_interview_questions: 3
  top_products_to_show: 3
  web_search_max_results: 3
```

#### Feature Flags

```yaml
features:
  enable_quick_replies: true
  enable_streaming: true
```

---

## Troubleshooting

### Port Already in Use

```bash
# Kill processes manually
lsof -ti :8000 | xargs kill -9  # Backend
lsof -ti :3000 | xargs kill -9  # Frontend
```

### Neo4j Connection Issues

- Verify Neo4j is running: `docker ps | grep neo4j` or `neo4j status`
- Check credentials in `.env` file match Neo4j configuration
- Test connection: `cypher-shell -u neo4j -p your-password`
- For Aura: Verify connection URI format (`neo4j+s://` for secure)

### Missing Environment Variables

- Ensure `.env` file exists in project root
- Verify all required variables are set (check startup script output for warnings)
- Required: `OPENAI_API_KEY`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`

### Knowledge Graph Issues

- Verify graph is built: Check Neo4j for `PCProduct` nodes
- Check product slugs match between database and knowledge graph
- Verify compatibility relationships exist: Run Cypher queries in Neo4j Browser
- Check logs for Neo4j connection errors

### Database Issues

- Verify `data/pc_parts.db` exists
- Check database permissions
- Rebuild database if corrupted: `python dataset_builder/fetch_pc_parts_dataset.py`

### Frontend Issues

- Clear browser cache
- Check browser console for errors
- Verify backend API is running on port 8000
- Check `NEXT_PUBLIC_API_URL` in `.env` matches backend URL

### Database Augmentation Details

The augmentation process enriches the base database with validated attributes:

**Sources**:
- Newegg product pages
- Amazon product listings
- Wikipedia technical specifications
- Manufacturer official documentation

**Validation Process**:
1. Extract attributes from each source
2. Cross-validate: At least 2 sources must agree on a value
3. Apply source priority: Manufacturer > Wikipedia > Retailers
4. Store validated attributes with confidence scores
5. Tag products for manual review if no manufacturer source found

**Attribute Storage**:
- `base_attributes` JSON: Original attributes from source database
- `validated_attributes` table: Cross-validated attributes with source tracking
- Attributes parsed at KG creation time from both sources

**Source Priority** (higher = more trusted):
- Manufacturer official: 100
- Manufacturer official (LLM): 95
- Wikipedia: 80
- Wikipedia (LLM): 75
- Newegg: 60
- Newegg (LLM): 55
- Amazon: 50
- Amazon (LLM): 45

---

## Additional Resources

- **API Documentation**: See `api/README.md` for detailed API reference
- **UI Documentation**: See `web/README.md` for frontend architecture
- **Changelog**: See `CHANGELOG.md` for version history

---
