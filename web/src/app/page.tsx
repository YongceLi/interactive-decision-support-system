'use client';

import { useState, useRef } from 'react';
import Filters from '@/components/Filters';
import ChatBox from '@/components/ChatBox';
import CarGrid from '@/components/CarGrid';
import CarDetailModal from '@/components/CarDetailModal';
import { Vehicle } from '@/types/vehicle';
import { ChatMessage } from '@/types/chat';
import { idssApiService } from '@/services/api';

// Format agent response to remove quotes and convert dashes to bullet points
function formatAgentResponse(response: string): string {
  // Remove surrounding quotes if present
  let formatted = response.trim();
  if ((formatted.startsWith('"') && formatted.endsWith('"')) || 
      (formatted.startsWith("'") && formatted.endsWith("'"))) {
    formatted = formatted.slice(1, -1);
  }
  
  // Convert dashes to bullet points with proper indentation
  formatted = formatted.replace(/^- /gm, '\n\t• ');
  
  // Handle bullet point text wrapping - ensure wrapped text is also indented
  formatted = formatted.replace(/(\n\t• [^\n]+)/g, (match) => {
    // Split long bullet points into multiple lines with proper indentation
    const bulletText = match.replace(/\n\t• /, '');
    const words = bulletText.split(' ');
    let result = '\n\t• ';
    let currentLine = '';
    
    for (const word of words) {
      if (currentLine.length + word.length + 1 > 60) { // Wrap at ~60 chars
        result += currentLine.trim() + '\n\t  '; // Extra tab for continuation
        currentLine = word;
      } else {
        currentLine += (currentLine ? ' ' : '') + word;
      }
    }
    result += currentLine.trim();
    return result;
  });
  
  // Clean up any double newlines
  formatted = formatted.replace(/\n\n+/g, '\n\n');
  
  return formatted.trim();
}

export default function Home() {
  const [selectedCar, setSelectedCar] = useState<Vehicle | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hi! I\'m your vehicle search assistant. How can I help you find the perfect car today?',
      timestamp: new Date()
    }
  ]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [isLoading, setIsLoading] = useState(false);
  
  // Add refs for debouncing and canceling requests
  const filterTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleCarSelect = (car: Vehicle) => {
    setSelectedCar(car);
  };

  const handleCarClose = () => {
    setSelectedCar(null);
  };

  const handleFilterChange = (newFilters: Record<string, unknown>) => {
    setFilters(newFilters);
    
    // Cancel any pending filter requests
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    // Clear any existing timeout
    if (filterTimeoutRef.current) {
      clearTimeout(filterTimeoutRef.current);
    }
    
    // Debounce filter changes - wait 500ms before sending request
    filterTimeoutRef.current = setTimeout(async () => {
      // Convert filters to a natural language message for the agent
      const filterMessages = [];
      
      if (newFilters.year) {
        filterMessages.push(`I'm looking for vehicles from ${newFilters.year}`);
      }
      
      if (newFilters.body_style) {
        filterMessages.push(`I prefer ${newFilters.body_style} body style`);
      }
      
      if (newFilters.price_min || newFilters.price_max) {
        const priceRange = [];
        if (newFilters.price_min) priceRange.push(`$${newFilters.price_min.toLocaleString()}`);
        if (newFilters.price_max) priceRange.push(`$${newFilters.price_max.toLocaleString()}`);
        filterMessages.push(`My budget is ${priceRange.join(' to ')}`);
      }

      if (newFilters.mileage_max) {
        filterMessages.push(`maximum mileage of ${newFilters.mileage_max.toLocaleString()} miles`);
      }
      
      if (filterMessages.length > 0) {
        const message = `I'd like to update my preferences: ${filterMessages.join(', ')}.`;
        await handleChatMessage(message, true); // Pass true to hide user message
      }
    }, 500);
  };

  const handleChatMessage = async (message: string, hideUserMessage = false) => {
    // Add user message immediately (unless hidden for filter changes)
    if (!hideUserMessage) {
      const userMessage: ChatMessage = {
        id: Date.now().toString(),
        role: 'user',
        content: message,
        timestamp: new Date()
      };
      setChatMessages(prev => [...prev, userMessage]);
    }
    setIsLoading(true);

    // Create new abort controller for this request
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      // Send message to agent API
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message,
          session_id: sessionId,
        }),
        signal: abortController.signal, // Add abort signal
      });

      if (!response.ok) {
        // Handle empty response for cancelled requests
        if (response.status === 400) {
          try {
            const errorData = await response.json();
            if (errorData.error === 'Empty request body') {
              console.log('Request was cancelled - empty body');
              return;
            }
          } catch (e) {
            // Response might not be JSON for cancelled requests
            console.log('Request was cancelled - non-JSON response');
            return;
          }
        }
        
        const errorData = await response.json();
        throw new Error(`HTTP error! status: ${response.status} - ${errorData.error || 'Unknown error'}`);
      }

      const data = await response.json();
      
      // Update session ID
      if (data.session_id) {
        setSessionId(data.session_id);
      }

          // Add assistant response with formatting (single message)
          const formattedResponse = formatAgentResponse(data.response);
          const assistantMessage: ChatMessage = {
            id: (Date.now() + 1).toString(),
            role: 'assistant' as const,
            content: formattedResponse,
            timestamp: new Date()
          };
          setChatMessages(prev => [...prev, assistantMessage]);

          // Update vehicles - convert API format to our format
          if (data.vehicles && data.vehicles.length > 0) {
            const convertedVehicles = data.vehicles.map((apiVehicle: Record<string, unknown>) => {
              return idssApiService.convertVehicle(apiVehicle);
            });
            setVehicles(convertedVehicles);
          }

      // Update filters
      if (data.filters) {
        setFilters(data.filters);
      }

    } catch (error) {
      console.error('Error sending message:', error);
      
      // Don't show error message if request was aborted (user changed filters quickly)
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('Request was aborted - user changed filters quickly');
        return;
      }
      
      // Add detailed error message for other errors
      const errorMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Connection Error: Unable to reach the agent.`,
        timestamp: new Date()
      };
      setChatMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-stone-50">
      <div className="flex min-h-screen">
        {/* Left Sidebar - Filters */}
        <div className="w-80 bg-stone-100 border-r border-stone-300 flex flex-col min-h-screen">
          <Filters 
            filters={filters}
            onFilterChange={handleFilterChange}
          />
        </div>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-h-screen">
            {/* Chat Section */}
            <div className="h-[32rem] max-h-[32rem] border-b border-stone-300 bg-stone-50">
            <ChatBox 
              messages={chatMessages}
              onSendMessage={handleChatMessage}
              isLoading={isLoading}
            />
          </div>

          {/* Car Grid Section */}
          <div className="flex-1 p-6 bg-stone-50">
            <CarGrid 
              vehicles={vehicles}
              onCarSelect={handleCarSelect}
            />
          </div>
        </div>
      </div>

      {/* Car Detail Modal */}
      {selectedCar && (
        <CarDetailModal 
          car={selectedCar}
          onClose={handleCarClose}
        />
      )}
    </div>
  );
}