# IDSS Agent Web Interface

A Next.js web interface for testing and simulating the Interactive Decision Support System (IDSS) agent for vehicle recommendations.

## Features

- **Interactive Chat Interface**: Chat with the IDSS agent to discuss vehicle preferences
- **Smart Filters**: Pre-defined filter buttons that communicate with the agent
- **Vehicle Grid**: Display recommended vehicles in an attractive grid layout
- **Detailed Car Views**: Click on any vehicle to see comprehensive details
- **Real-time Updates**: Agent responses update both chat and vehicle recommendations
- **Responsive Design**: Works on desktop and mobile devices

## Getting Started

### Prerequisites

1. Make sure the IDSS agent API server is running on `http://localhost:8000`
2. Node.js 18+ and npm installed

### Installation

1. Install dependencies:
```bash
npm install
```

2. Set up environment variables:
Create a `.env.local` file in the web directory:
```bash
# IDSS Agent API URL
IDSS_API_URL=http://localhost:8000

# Next.js Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
```

3. Start the development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser

## Usage

### Chat Interface
- Type your vehicle preferences and questions in the chat box
- The agent will respond with recommendations and questions


### Filters
- Click on pre-defined filter buttons (New, Used, SUV, Sedan)
- Filters automatically communicate with the agent to refine recommendations
- Active filters are displayed below the filter buttons

### Vehicle Grid
- View recommended vehicles in an organized grid
- Each card shows key information: price, mileage, location, fuel economy, safety rating
- Click "View Details" to see comprehensive vehicle information

### Vehicle Details
- Detailed modal with all vehicle specifications
- Safety ratings, fuel economy, features, and dealer information

## Architecture

### API Integration
- Proxies requests to the IDSS agent API running on port 8000
- Handles session management automatically
- Converts agent responses to vehicle data format


## Development

### Project Structure
```
src/
├── app/
│   ├── api/chat/route.ts    # API proxy to IDSS agent
│   └── page.tsx             # Main application page
├── components/
│   ├── Filters.tsx          # Filter sidebar component
│   ├── ChatBox.tsx          # Chat interface component
│   ├── CarGrid.tsx          # Vehicle grid component
│   └── CarDetailModal.tsx   # Vehicle detail modal
├── types/
│   ├── vehicle.ts           # Vehicle data types
│   └── chat.ts              # Chat message types
└── services/
    └── api.ts               # API service utilities
```

## Troubleshooting

### Agent Not Responding
- Check that the IDSS API server is running on port 8000
- Verify environment variables are set correctly
- Check browser console for API errors
