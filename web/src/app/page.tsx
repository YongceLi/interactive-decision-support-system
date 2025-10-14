'use client';

import { useState, useEffect } from 'react';
import ChatBox from '@/components/ChatBox';
import RecommendationCarousel from '@/components/RecommendationCarousel';
import ItemDetailModal from '@/components/ItemDetailModal';
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
  
  // Clean up any double newlines
  formatted = formatted.replace(/\n\n+/g, '\n\n');
  
  return formatted.trim();
}

export default function Home() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedItem, setSelectedItem] = useState<Vehicle | null>(null);

  // Initialize with the agent's first message
  useEffect(() => {
    if (chatMessages.length === 0) {
      const initialMessage: ChatMessage = {
        id: 'initial',
        role: 'assistant',
        content: "Let's shop for your dream item. Tell me what you're looking for.",
        timestamp: new Date()
      };
      setChatMessages([initialMessage]);
    }
  }, [chatMessages.length]);

  const handleChatMessage = async (message: string) => {
    // Add user message immediately
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date()
    };
    setChatMessages(prev => [...prev, userMessage]);
    
    setIsLoading(true);

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
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(`HTTP error! status: ${response.status} - ${errorData.error || 'Unknown error'}`);
      }

      const data = await response.json();
      
      // Update session ID
      if (data.session_id) {
        setSessionId(data.session_id);
      }

      // Add assistant response with formatting
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

    } catch (error) {
      console.error('Error sending message:', error);
      
      // Add error message
      const errorMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Sorry, I ran into an issue. Mind trying again?`,
        timestamp: new Date()
      };
      setChatMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700">
      <div className="h-screen flex flex-col">
        {/* Chat Messages with Floating Cards */}
        <div className="flex-1 overflow-y-auto p-6 relative">
          <div className="max-w-6xl mx-auto space-y-6 relative">
            {chatMessages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                  <div
                    className={`max-w-[80%] p-4 rounded-2xl ${
                      message.role === 'user'
                        ? 'bg-gradient-to-r from-purple-500 to-blue-500 text-white'
                        : 'glass-dark text-slate-100'
                    }`}
                  >
                    <p className="text-sm leading-relaxed" dangerouslySetInnerHTML={{
                      __html: message.content.replace(/\*([^*]+)\*/g, '<em>$1</em>')
                    }} />
                  </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="glass-dark p-4 rounded-2xl">
                  <div className="flex space-x-2">
                    <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                    <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                  </div>
                </div>
              </div>
            )}

            {/* Recommendation Cards */}
            {vehicles.length > 0 && (
              <div className="mt-8 relative">
                <RecommendationCarousel 
                  vehicles={vehicles} 
                  onItemSelect={setSelectedItem}
                />
              </div>
            )}
          </div>
        </div>

        {/* Chat Input */}
        <div className="border-t border-slate-600/30 glass-dark p-6">
          <div className="max-w-6xl mx-auto">
            <ChatBox
              messages={[]}
              onSendMessage={handleChatMessage}
              isLoading={isLoading}
            />
          </div>
        </div>
      </div>

      {/* Item Detail Modal */}
      {selectedItem && (
        <ItemDetailModal 
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </div>
  );
}