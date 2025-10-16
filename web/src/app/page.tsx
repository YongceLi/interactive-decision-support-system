'use client';

import { useState, useEffect } from 'react';
import ChatBox from '@/components/ChatBox';
import RecommendationCarousel from '@/components/RecommendationCarousel';
import ItemDetailModal from '@/components/ItemDetailModal';
import FilterMenu from '@/components/FilterMenu';
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
  const [hasReceivedRecommendations, setHasReceivedRecommendations] = useState(false);
  const [currentFilters, setCurrentFilters] = useState<Record<string, unknown>>({});
  const [showDetails, setShowDetails] = useState(false);

  // Initialize with the agent's first message
  useEffect(() => {
    if (chatMessages.length === 0) {
      const initialMessage: ChatMessage = {
        id: 'initial',
        role: 'assistant',
        content: "Let's shop for your dream product. Tell me what you're looking for.",
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
        setHasReceivedRecommendations(true);
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

  const handleFilterChange = async (filters: Record<string, unknown>) => {
    setCurrentFilters(filters);
    
    // Create a message to send to the agent with the filter preferences
    const filterMessage = `Please find vehicles with these preferences: ${JSON.stringify(filters)}`;
    
    setIsLoading(true);

    try {
      // Send filter request to agent API
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: filterMessage,
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

      // Update vehicles - convert API format to our format
      if (data.vehicles && data.vehicles.length > 0) {
        const convertedVehicles = data.vehicles.map((apiVehicle: Record<string, unknown>) => {
          return idssApiService.convertVehicle(apiVehicle);
        });
        setVehicles(convertedVehicles);
        setHasReceivedRecommendations(true);
      }

    } catch (error) {
      console.error('Error applying filters:', error);
      
      // Add error message only if there's an error
      const errorMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Sorry, I ran into an issue applying your filters. Please try again.`,
        timestamp: new Date()
      };
      setChatMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleItemSelect = (vehicle: Vehicle) => {
    setSelectedItem(vehicle);
    setShowDetails(true);
  };

  // Find the index of the selected vehicle
  const getSelectedVehicleIndex = () => {
    if (!selectedItem) return 0;
    return vehicles.findIndex(v => v.id === selectedItem.id) + 1;
  };

  const handleBackToRecommendations = () => {
    setShowDetails(false);
    setSelectedItem(null);
  };

  // Get only the last 3 turns (6 messages max: user-agent-user-agent-user-agent)
  const getLastThreeTurns = () => {
    const maxMessages = 6; // 3 turns = 6 messages max
    return chatMessages.slice(-maxMessages);
  };

  const recentMessages = getLastThreeTurns();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700">
      <div className="h-screen flex flex-col">
        {/* Recommendations at the top or Details View */}
        {hasReceivedRecommendations && (
          <div className="flex-shrink-0 p-2 border-b border-slate-600/30">
            <div className="max-w-6xl mx-auto">
              {showDetails && selectedItem ? (
                <div className="glass-dark rounded-xl p-3 relative max-h-96 overflow-y-auto">
                  {/* Back Button */}
                  <button
                    onClick={handleBackToRecommendations}
                    className="absolute top-2 right-2 w-6 h-6 glass rounded-lg flex items-center justify-center hover:bg-slate-700/50 transition-all duration-200 z-10"
                  >
                    <svg className="w-3 h-3 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                  
                  {/* Vehicle Details */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 pr-8">
                    {/* Image */}
                    <div className="aspect-video bg-gradient-to-br from-slate-600 to-slate-700 rounded-lg flex items-center justify-center overflow-hidden relative">
                      {selectedItem.image_url ? (
                        <img
                          src={selectedItem.image_url}
                          alt={`${selectedItem.year} ${selectedItem.make} ${selectedItem.model}`}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="text-slate-400 text-center">
                          <svg className="w-8 h-8 mx-auto mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                          </svg>
                          <div className="text-xs">No Image Available</div>
                        </div>
                      )}
                      
                      {/* Number indicator */}
                      <div className="absolute bottom-0 right-0 w-8 h-8 glass-dark border border-slate-600/30 text-slate-200 rounded-lg flex items-center justify-center text-sm font-bold">
                        {getSelectedVehicleIndex()}
                      </div>
                    </div>
                    
                    {/* Details */}
                    <div className="space-y-1">
                      <div>
                        <h2 className="text-lg font-bold text-slate-100 mb-1">
                          {selectedItem.year} {selectedItem.make} {selectedItem.model}
                          {selectedItem.trim && ` ${selectedItem.trim}`}
                        </h2>
                      </div>
                      
                      {/* Key Info Grid */}
                      <div className="grid grid-cols-2 gap-1">
                        {selectedItem.price && (
                          <div className="glass rounded p-1">
                            <div className="text-slate-400 text-xs">Price</div>
                            <div className="text-sm font-bold text-green-400">
                              ${selectedItem.price.toLocaleString()}
                            </div>
                          </div>
                        )}
                        
                        {selectedItem.mileage && (
                          <div className="glass rounded p-1">
                            <div className="text-slate-400 text-xs">Mileage</div>
                            <div className="text-sm font-bold text-slate-200">
                              {typeof selectedItem.mileage === 'number' ? selectedItem.mileage.toLocaleString() : selectedItem.mileage} mi
                            </div>
                          </div>
                        )}
                      </div>
                      
                      {/* Location & Performance */}
                      <div className="grid grid-cols-1 gap-1">
                        {selectedItem.location && (
                          <div className="glass rounded p-1">
                            <div className="flex items-center">
                              <svg className="w-3 h-3 mr-1 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                              </svg>
                              <div className="text-slate-200 text-sm">
                                {selectedItem.location === '00' ? 'Unknown' : selectedItem.location}
                              </div>
                            </div>
                          </div>
                        )}
                        
                        {selectedItem.fuel_economy && (
                          <div className="glass rounded p-1">
                            <div className="flex items-center">
                              <svg className="w-3 h-3 mr-1 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                              </svg>
                              <div className="text-slate-200 text-sm">{selectedItem.fuel_economy.combined} MPG combined</div>
                            </div>
                          </div>
                        )}
                        
                        {selectedItem.safety_rating && (
                          <div className="glass rounded p-1">
                            <div className="flex items-center">
                              <svg className="w-3 h-3 mr-1 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                              </svg>
                              <div className="text-slate-200 text-sm">{selectedItem.safety_rating.overall}/5 Safety Rating</div>
                            </div>
                          </div>
                        )}
                      </div>
                      
                      {/* Vehicle Specs Grid */}
                      <div className="grid grid-cols-2 gap-1">
                        {selectedItem.body_style && (
                          <div className="glass rounded p-1">
                            <div className="text-slate-400 text-xs">Body</div>
                            <div className="text-slate-200 text-sm">{selectedItem.body_style}</div>
                          </div>
                        )}
                        
                        {selectedItem.engine && (
                          <div className="glass rounded p-1">
                            <div className="text-slate-400 text-xs">Engine</div>
                            <div className="text-slate-200 text-sm">{selectedItem.engine}</div>
                          </div>
                        )}
                        
                        {selectedItem.transmission && (
                          <div className="glass rounded p-1">
                            <div className="text-slate-400 text-xs">Transmission</div>
                            <div className="text-slate-200 text-sm">{selectedItem.transmission}</div>
                          </div>
                        )}
                        
                        {selectedItem.doors && (
                          <div className="glass rounded p-1">
                            <div className="text-slate-400 text-xs">Doors</div>
                            <div className="text-slate-200 text-sm">{selectedItem.doors}</div>
                          </div>
                        )}
                      </div>
                      
                      {/* Colors & Seating */}
                      <div className="grid grid-cols-2 gap-1">
                        {selectedItem.exterior_color && (
                          <div className="glass rounded p-1">
                            <div className="text-slate-400 text-xs">Exterior</div>
                            <div className="text-slate-200 text-sm">{selectedItem.exterior_color}</div>
                          </div>
                        )}
                        
                        {selectedItem.interior_color && (
                          <div className="glass rounded p-1">
                            <div className="text-slate-400 text-xs">Interior</div>
                            <div className="text-slate-200 text-sm">{selectedItem.interior_color}</div>
                          </div>
                        )}
                        
                        {selectedItem.seating_capacity && (
                          <div className="glass rounded p-1">
                            <div className="text-slate-400 text-xs">Seating</div>
                            <div className="text-slate-200 text-sm">{selectedItem.seating_capacity} seats</div>
                          </div>
                        )}
                      </div>
                      
                      {/* Features & Description */}
                      {selectedItem.features && selectedItem.features.length > 0 && (
                        <div className="glass rounded p-1">
                          <div className="text-slate-400 text-xs">Features</div>
                          <div className="text-slate-200 text-sm">{selectedItem.features.slice(0, 3).join(', ')}{selectedItem.features.length > 3 ? '...' : ''}</div>
                        </div>
                      )}
                      
                      {selectedItem.description && (
                        <div className="glass rounded p-1">
                          <div className="text-slate-400 text-xs">Description</div>
                          <div className="text-slate-200 text-sm">{selectedItem.description}</div>
                        </div>
                      )}
                      
                      {/* Dealer Info */}
                      {selectedItem.dealer_info && (
                        <div className="glass rounded p-1">
                          <div className="text-slate-400 text-xs">Dealer</div>
                          <div className="text-slate-200 text-sm">{selectedItem.dealer_info.name}</div>
                          {selectedItem.dealer_info.phone && (
                            <div className="text-slate-300 text-xs">{selectedItem.dealer_info.phone}</div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <RecommendationCarousel 
                  vehicles={vehicles} 
                  onItemSelect={handleItemSelect}
                  showPlaceholders={false}
                />
              )}
            </div>
          </div>
        )}

        {/* Chat Messages - Only last 3 turns */}
        <div className="flex-1 overflow-y-auto p-10 relative min-h-0">
          <div className="max-w-6xl mx-auto flex flex-col justify-end min-h-full space-y-6">
            {recentMessages.map((message) => (
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

      {/* Filter Menu */}
      <FilterMenu onFilterChange={handleFilterChange} />
    </div>
  );
}