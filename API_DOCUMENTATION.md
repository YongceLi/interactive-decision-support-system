# IDSS API Documentation

**Version:** 1.0.0
**Base URL:** `http://localhost:8000`
**Protocol:** HTTP/REST with Server-Sent Events (SSE) support

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Base URL & Headers](#base-url--headers)
4. [Response Format](#response-format)
5. [Error Handling](#error-handling)
6. [Endpoints](#endpoints)
   - [Health Check](#health-check)
   - [Chat](#chat)
   - [Chat Stream](#chat-stream)
   - [Session Management](#session-management)
   - [Event Tracking](#event-tracking)
7. [Data Models](#data-models)
8. [Interactive Elements](#interactive-elements)
9. [Code Examples](#code-examples)

---

## Overview

The Interactive Decision Support System (IDSS) API provides conversational AI capabilities for vehicle shopping assistance. The system uses intent-based routing to provide personalized recommendations, answer analytical questions, and guide users through an interview process.

### Key Features

- **Intent-based routing** (buying, browsing, research, general)
- **Conversational interview** for understanding user needs
- **Real-time vehicle recommendations** from Auto.dev API
- **Analytical queries** with access to safety and fuel economy databases
- **Interactive elements** (quick replies and suggested follow-ups)
- **Server-Sent Events** for real-time progress updates
- **Session management** for conversation continuity

---

## Authentication

Currently, the API does not require authentication. All endpoints are publicly accessible on the local network.

> **Note:** For production deployment, implement proper authentication mechanisms (API keys, OAuth, etc.).

---

## Base URL & Headers

### Base URL
```
http://localhost:8000
```

### Recommended Headers
```http
Content-Type: application/json
Accept: application/json
```

For streaming endpoints:
```http
Content-Type: application/json
Accept: text/event-stream
```

---

## Response Format

### Standard JSON Response

All non-streaming endpoints return JSON responses with the following structure:

```json
{
  "response": "string",
  "vehicles": [],
  "filters": {},
  "preferences": {},
  "session_id": "string",
  "interviewed": false,
  "quick_replies": ["string"] | null,
  "suggested_followups": ["string"]
}
```

### Server-Sent Events (SSE) Format

Streaming endpoints use SSE with the following event types:

- `progress`: Progress updates during execution
- `complete`: Final response with full data
- `error`: Error information

---

## Error Handling

### Error Response Format

```json
{
  "detail": "Error message description"
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid input parameters |
| 404 | Not Found - Resource does not exist |
| 500 | Internal Server Error |

---

## Endpoints

### Health Check

Check if the API server is running.

#### Request

```http
GET /
```

#### Response

```json
{
  "status": "online",
  "service": "IDSS API",
  "version": "1.0.0"
}
```

#### Example

```bash
curl http://localhost:8000/
```

---

### Chat

Send a message to the conversational agent and receive a response with vehicle recommendations.

#### Request

```http
POST /chat
Content-Type: application/json
```

**Body Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | User's message or query |
| `session_id` | string | No | Session ID for conversation continuity. If not provided, a new session is created. |

#### Request Body Example

```json
{
  "message": "I want a reliable SUV under $30k",
  "session_id": "optional-session-id"
}
```

#### Response

**Status Code:** `200 OK`

**Response Body:**

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | AI-generated response text |
| `vehicles` | array | List of recommended vehicles (up to 20) |
| `filters` | object | Extracted explicit search filters |
| `preferences` | object | Inferred implicit preferences |
| `session_id` | string | Session ID for subsequent requests |
| `interviewed` | boolean | Whether interview process is complete |
| `quick_replies` | array\|null | Short answer options (1-5 words, 2-4 options) for direct questions |
| `suggested_followups` | array | Suggested next user inputs (short phrases, 3-5 options) |

#### Response Example

```json
{
  "response": "I found 15 reliable SUVs under $30k. The 2022 Honda CR-V stands out with excellent reliability ratings and great fuel economy. Would you prefer a hybrid or traditional gas engine?",
  "vehicles": [
    {
      "vehicle": {
        "vin": "1HGCV1F16JA123456",
        "year": 2022,
        "make": "Honda",
        "model": "CR-V",
        "trim": "EX",
        "bodyStyle": "SUV",
        "engine": "1.5L 4Cyl Turbo",
        "transmission": "CVT",
        "exteriorColor": "White",
        "interiorColor": "Black",
        "mileage": 15234
      },
      "retailListing": {
        "price": 28990,
        "miles": 15234,
        "city": "Los Angeles",
        "state": "CA",
        "zip": "90001",
        "dealer": "Honda of Downtown LA",
        "vdp": "https://example.com/vehicle/123",
        "carfaxUrl": "https://carfax.com/..."
      },
      "photos": {
        "retail": [
          "https://api.auto.dev/photos/retail/1HGCV1F16JA123456-1.jpg"
        ]
      }
    }
  ],
  "filters": {
    "body_style": "SUV",
    "price": "0-30000"
  },
  "preferences": {
    "priorities": ["reliability"],
    "budget_sensitivity": "moderate"
  },
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "interviewed": false,
  "quick_replies": ["Hybrid", "Traditional gas", "Either works"],
  "suggested_followups": [
    "Show me hybrids",
    "I want good gas mileage",
    "What about safety?",
    "Show cheaper options"
  ]
}
```

#### Example Request

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I want a reliable SUV under $30k"
  }'
```

---

### Chat Stream

Send a message and receive real-time progress updates via Server-Sent Events (SSE).

#### Request

```http
POST /chat/stream
Content-Type: application/json
Accept: text/event-stream
```

**Body Parameters:** Same as `/chat` endpoint

#### Response

**Status Code:** `200 OK`
**Content-Type:** `text/event-stream`

**Event Types:**

1. **progress** - Execution progress updates

```
event: progress
data: {"step_id": "intent_classification", "description": "Classifying user intent", "status": "in_progress"}

event: progress
data: {"step_id": "intent_classification", "description": "Intent classified", "status": "completed"}
```

2. **complete** - Final response (same structure as `/chat` endpoint)

```
event: complete
data: {"response": "...", "vehicles": [...], "session_id": "...", ...}
```

3. **error** - Error information

```
event: error
data: {"error": "Error message", "detail": "Detailed error information"}
```

#### Progress Steps by Mode

**Buying Mode (Not Interviewed):**
1. Understanding your request
2. Routing to buying mode
3. Extracting preferences
4. Conducting interview
5. Searching for vehicles
6. Presenting recommendations
7. Complete

**Discovery Mode:**
1. Understanding your request
2. Routing to discovery mode
3. Analyzing search criteria
4. Searching for vehicles
5. Presenting vehicles
6. Complete

**Analytical Mode:**
1. Understanding your request
2. Routing to analytical mode
3. Parsing question context
4. Executing tools
5. Synthesizing answer
6. Complete

#### Example Request

```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": "Show me Honda Civic"
  }'
```

---

### Session Management

#### Get Session State

Retrieve current state for a session.

```http
GET /session/{session_id}
```

**Response:**

```json
{
  "session_id": "string",
  "filters": {},
  "preferences": {},
  "vehicles": [],
  "conversation_history": []
}
```

#### Reset Session

Reset or create a new session.

```http
POST /session/reset
Content-Type: application/json
```

**Request Body:**

```json
{
  "session_id": "optional-session-id"
}
```

**Response:**

```json
{
  "session_id": "new-or-reset-session-id",
  "status": "reset"
}
```

#### Delete Session

Delete a session.

```http
DELETE /session/{session_id}
```

**Response:**

```json
{
  "status": "deleted",
  "session_id": "deleted-session-id"
}
```

#### List Sessions

Get all active sessions.

```http
GET /sessions
```

**Response:**

```json
{
  "active_sessions": 3,
  "session_ids": ["id1", "id2", "id3"]
}
```

---

### Event Tracking

Track user interactions with vehicles for analytics.

#### Log Event

```http
POST /session/{session_id}/event
Content-Type: application/json
```

**Request Body:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `event_type` | string | Yes | Type of event (see event types below) |
| `data` | object | Yes | Event-specific data |
| `timestamp` | string | No | ISO timestamp (auto-generated if not provided) |

**Event Types:**

- `vehicle_click` - User clicked on a vehicle
- `vehicle_view` - User viewed vehicle details
- `photo_view` - User viewed vehicle photos
- `link_click` - User clicked on external link
- Custom event types

**Request Example:**

```json
{
  "event_type": "vehicle_click",
  "data": {
    "vin": "1HGCV1F16JA123456",
    "vehicle_index": 0,
    "year": 2022,
    "make": "Honda",
    "model": "CR-V"
  }
}
```

**Response:**

```json
{
  "status": "logged",
  "event_id": 0,
  "timestamp": "2025-10-24T10:00:00.000000"
}
```

#### Retrieve Events

Get all events for a session, optionally filtered by type.

```http
GET /session/{session_id}/events?event_type={optional_type}
```

**Response:**

```json
{
  "session_id": "string",
  "events": [
    {
      "event_type": "vehicle_click",
      "data": {},
      "timestamp": "2025-10-24T10:00:00.000000"
    }
  ],
  "total": 1
}
```

---

## Data Models

### Vehicle Object

```typescript
{
  vehicle: {
    vin: string;
    year: number;
    make: string;
    model: string;
    trim?: string;
    bodyStyle?: string;
    engine?: string;
    transmission?: string;
    exteriorColor?: string;
    interiorColor?: string;
    mileage?: number;
    doors?: number;
    seating_capacity?: number;
  };
  retailListing: {
    price: number;
    miles: number;
    city: string;
    state: string;
    zip: string;
    dealer: string;
    vdp?: string;
    carfaxUrl?: string;
  };
  photos?: {
    retail: string[];
    exterior: string[];
    interior: string[];
  };
  history?: {
    accidents: boolean;
    accidentCount: number;
    ownerCount: number;
    usageType: string;
  };
}
```

### Filters Object

```typescript
{
  make?: string;          // "Toyota" or "Toyota,Honda"
  model?: string;         // "Camry" or "Camry,Accord"
  year?: string;          // "2020" or "2018-2020"
  trim?: string;
  body_style?: string;    // "sedan" or "suv,truck"
  engine?: string;
  transmission?: string;
  exterior_color?: string;
  interior_color?: string;
  doors?: number;
  seating_capacity?: number;
  price?: string;         // "20000-30000"
  state?: string;         // "CA"
  mileage?: string;       // "0-50000"
  zip?: string;
  search_radius?: number;
  features?: string[];
}
```

### Preferences Object

```typescript
{
  priorities?: string[];           // ["safety", "fuel_efficiency"]
  lifestyle?: string;              // "family-oriented"
  budget_sensitivity?: string;     // "moderate"
  brand_affinity?: string[];       // ["Toyota", "Honda"]
  concerns?: string[];             // ["maintenance costs"]
  usage_patterns?: string;         // "daily commute"
  notes?: string;
}
```

---

## Interactive Elements

The API provides two types of interactive elements to enhance user experience:

### Quick Replies

Short answer options (1-5 words, 2-4 options) that appear when the AI asks a direct question.

**Purpose:** Allow users to quickly answer questions by clicking instead of typing.

**Examples:**
- Budget questions: `["Under $20k", "$20k-$30k", "$30k+"]`
- Body style: `["Sedan", "SUV", "Truck", "Hatchback"]`
- Yes/No: `["Yes", "No", "Maybe"]`

**When to Display:** Only when `quick_replies` is not `null`

### Suggested Follow-ups

Short phrases (3-5 options) representing what the user might want to say or ask next.

**Purpose:** Help users continue the conversation by suggesting common next steps.

**Examples:**
- `["Show me hybrids", "What about safety?", "Compare top 3"]`
- `["I want a sedan", "Show cheaper options", "Tell me more"]`
- `["Check fuel economy", "Compare performance", "Show alternatives"]`

**When to Display:** Always present (array may be empty but field is always included)

### Implementation Guidelines

1. **Quick Replies:**
   - Display as pill-shaped buttons below the AI message
   - On click, send the selected text as the user's next message
   - Hide after user makes a selection

2. **Suggested Follow-ups:**
   - Display as chips/buttons in a separate section
   - Keep visible even after selection
   - Can click multiple times to explore different paths

---

## Code Examples

### Python

#### Basic Chat Request

```python
import requests

BASE_URL = "http://localhost:8000"

response = requests.post(
    f"{BASE_URL}/chat",
    json={
        "message": "I want a Honda Civic"
    }
)

data = response.json()
print(f"AI Response: {data['response']}")
print(f"Vehicles Found: {len(data['vehicles'])}")
print(f"Quick Replies: {data['quick_replies']}")
print(f"Suggested Follow-ups: {data['suggested_followups']}")
```

#### Streaming Chat with SSE

```python
import requests
import json

response = requests.post(
    f"{BASE_URL}/chat/stream",
    json={"message": "Show me SUVs"},
    stream=True
)

event_type = None
for line in response.iter_lines(decode_unicode=True):
    if not line:
        continue

    if line.startswith('event:'):
        event_type = line.split(':', 1)[1].strip()
    elif line.startswith('data:'):
        data = json.loads(line.split(':', 1)[1])

        if event_type == 'progress':
            print(f"Progress: {data['description']}")
        elif event_type == 'complete':
            print(f"Complete! Found {len(data['vehicles'])} vehicles")
        elif event_type == 'error':
            print(f"Error: {data['error']}")
```

### JavaScript/TypeScript

#### Basic Chat Request

```javascript
const BASE_URL = 'http://localhost:8000';

async function sendMessage(message, sessionId = null) {
  const response = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
    }),
  });

  const data = await response.json();
  return data;
}

// Usage
const result = await sendMessage('I want a reliable SUV');
console.log('AI Response:', result.response);
console.log('Quick Replies:', result.quick_replies);
console.log('Suggested Follow-ups:', result.suggested_followups);
console.log('Vehicles:', result.vehicles.length);
```

#### Streaming with EventSource

```javascript
function streamChat(message, sessionId = null) {
  const url = new URL(`${BASE_URL}/chat/stream`);

  fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify({ message, session_id: sessionId }),
  }).then(response => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let eventType = null;

    function processStream() {
      reader.read().then(({ done, value }) => {
        if (done) return;

        const text = decoder.decode(value);
        const lines = text.split('\n');

        lines.forEach(line => {
          if (line.startsWith('event:')) {
            eventType = line.split(':')[1].trim();
          } else if (line.startsWith('data:')) {
            const data = JSON.parse(line.split('data:')[1]);

            if (eventType === 'progress') {
              console.log('Progress:', data.description);
            } else if (eventType === 'complete') {
              console.log('Complete!', data);
            } else if (eventType === 'error') {
              console.error('Error:', data.error);
            }
          }
        });

        processStream();
      });
    }

    processStream();
  });
}
```

### cURL

#### Send a Chat Message

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I want a Toyota Camry under $25k in California"
  }'
```

#### Stream Chat with Progress

```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": "Show me Honda Civic"
  }'
```

#### Reset Session

```bash
curl -X POST http://localhost:8000/session/reset \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "existing-session-id"
  }'
```

#### Log an Event

```bash
curl -X POST http://localhost:8000/session/abc123/event \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "vehicle_click",
    "data": {
      "vin": "1HGCV1F16JA123456",
      "vehicle_index": 0
    }
  }'
```

---

## Rate Limiting

Currently, there are no rate limits enforced. For production deployment, implement appropriate rate limiting based on your infrastructure and usage patterns.

---

## Changelog

### Version 1.0.0 (2025-10-24)

**Added:**
- Initial API release
- Chat and streaming chat endpoints
- Session management
- Event tracking
- Interactive elements (quick replies and suggested follow-ups)
- Intent-based routing (buying, browsing, research, general)
- Real-time progress updates via SSE
