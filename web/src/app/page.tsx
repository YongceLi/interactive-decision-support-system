'use client';

import { useState, useEffect } from 'react';
import ChatBox from '@/components/ChatBox';
import RecommendationCarousel from '@/components/RecommendationCarousel';
import ItemDetailModal from '@/components/ItemDetailModal';
import FilterMenu from '@/components/FilterMenu';
import FavoritesPage from '@/components/FavoritesPage';
import { Vehicle } from '@/types/vehicle';
import { ChatMessage } from '@/types/chat';
import { idssApiService } from '@/services/api';
import { LoggingService } from '@/services/logging';
import { useVerboseLoading } from '@/hooks/useVerboseLoading';

// Format agent response to remove quotes and convert to proper markdown
function formatAgentResponse(response: string): string {
  // Remove surrounding quotes if present
  let formatted = response.trim();
  if ((formatted.startsWith('"') && formatted.endsWith('"')) || 
      (formatted.startsWith("'") && formatted.endsWith("'"))) {
    formatted = formatted.slice(1, -1);
  }
  
  // Convert dashes and asterisks to proper bullet points (keep on same line)
  formatted = formatted.replace(/^[\s]*[-*][\s]+/gm, '• ');
  
  // Clean up any double newlines
  formatted = formatted.replace(/\n\n+/g, '\n\n');
  
  return formatted.trim();
}

// Simple markdown parser for chat messages
function parseMarkdown(text: string): string {
  let html = text;
  
  // Remove exclamation marks before "photos"
  html = html.replace(/!+\s*([Pp]hotos?)/g, '$1');
  
  // Convert bold text **text** or *text* to <strong>
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<strong>$1</strong>');
  
  // Convert headings ### Heading to <h3>
  html = html.replace(/^### (.*$)/gm, '<h3 class="text-lg font-bold mb-0 mt-0">$1</h3>');
  html = html.replace(/^## (.*$)/gm, '<h2 class="text-xl font-bold mb-0 mt-0">$1</h2>');
  html = html.replace(/^# (.*$)/gm, '<h1 class="text-2xl font-bold mb-0 mt-0">$1</h1>');
  
  // Convert links [text](url) to <a>
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-blue-400 hover:text-blue-300 underline" target="_blank" rel="noopener noreferrer">$1</a>');
  
  // Convert bullet points • to proper list items
  html = html.replace(/^• (.*$)/gm, '<li class="mb-2">$1</li>');
  
  // Wrap consecutive list items in <ul>
  html = html.replace(/(<li class="mb-2">.*<\/li>(\s*<li class="mb-2">.*<\/li>)*)/g, '<ul class="list-none space-y-2">$1</ul>');
  
  // Remove line breaks between list items
  html = html.replace(/<\/li>\s*\n\s*<li/g, '</li><li');
  
  // Wrap the first non-list, non-empty line in a paragraph with margin-bottom
  // This targets the first line that doesn't start with '<' (i.e., not an HTML tag)
  html = html.replace(/^([^\n<].*?)\n/, '<p class="mb-2">$1</p>\n');
  
  // Convert line breaks to <br> for non-list content
  html = html.replace(/\n(?!<)/g, '<br>');
  
  // Remove extra <br> tags immediately before <ul> tags (to remove blank lines before bullet lists)
  html = html.replace(/(<br>)+<ul/g, '<ul');
  
  // Remove extra <br> tags immediately after </ul> tags (to remove blank lines after bullet lists)
  // Handle cases with whitespace and multiple <br> tags
  html = html.replace(/<\/ul>\s*(<br>)+/g, '</ul>');
  
  return html;
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
  const [detailViewStartTime, setDetailViewStartTime] = useState<number | null>(null);
  const [favorites, setFavorites] = useState<Vehicle[]>([]);
  const [showFavorites, setShowFavorites] = useState(false);
  
  const { currentMessage, start, stop, setProgressMessage } = useVerboseLoading();

  // Load favorites from localStorage on mount
  useEffect(() => {
    const savedFavorites = localStorage.getItem('favorites');
    if (savedFavorites) {
      try {
        setFavorites(JSON.parse(savedFavorites));
      } catch (e) {
        console.error('Error loading favorites:', e);
      }
    }
  }, []);

  // Save favorites to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('favorites', JSON.stringify(favorites));
  }, [favorites]);

  const toggleFavorite = (vehicle: Vehicle) => {
    setFavorites(prev => {
      const isFavorite = prev.some(v => v.id === vehicle.id);
      if (isFavorite) {
        return prev.filter(v => v.id !== vehicle.id);
      } else {
        return [...prev, vehicle];
      }
    });
  };

  const isFavorite = (vehicleId: string) => {
    return favorites.some(v => v.id === vehicleId);
  };

  // Initialize with the agent's first message
  useEffect(() => {
    if (chatMessages.length === 0) {
      const initialMessage: ChatMessage = {
        id: 'initial',
        role: 'assistant',
        content: "Welcome to your personal shopping assistant! Let's find your ideal match. What are you looking for?",
        timestamp: new Date()
      };
      setChatMessages([initialMessage]);
    }
  }, [chatMessages.length]);

  // Helper function to handle streaming response
  const handleStreamingResponse = async (response: Response) => {
    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('No response body');
    }

    let buffer = '';
    let currentEventType = '';
    let hasCompleted = false;
    let finalData: any = null;

    while (true) {
      const { done, value } = await reader.read();
      
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        
        if (line.startsWith('event:')) {
          currentEventType = line.substring(6).trim();
          
          if (currentEventType === 'complete') {
            hasCompleted = true;
          }
        } else if (line.startsWith('data:')) {
          const dataStr = line.substring(5).trim();
          
          if (currentEventType === 'progress') {
            try {
              const progressData = JSON.parse(dataStr);
              if (progressData.description) {
                setProgressMessage(progressData.description);
              }
            } catch (e) {
              console.error('Error parsing progress data:', e);
            }
          } else if (currentEventType === 'complete' && hasCompleted) {
            try {
              finalData = JSON.parse(dataStr);
            } catch (e) {
              console.error('Error parsing complete data:', e);
            }
          } else if (currentEventType === 'error') {
            try {
              const errorData = JSON.parse(dataStr);
              throw new Error(errorData.error || 'Unknown error');
            } catch (e) {
              console.error('Error parsing error data:', e);
            }
          }
        }
      }
    }

    return finalData;
  };

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
    start(); // Start verbose loading

    try {
      // Send message to streaming endpoint
      const response = await fetch('/api/chat/stream', {
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

      // Handle streaming response
      const data = await handleStreamingResponse(response);
      
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
      stop(); // Stop verbose loading
    }
  };

  const handleFilterChange = async (filters: Record<string, unknown>) => {
    setCurrentFilters(filters);
    
    // Create a message to send to the agent with the filter preferences
    const filterMessage = `Please find vehicles with these preferences: ${JSON.stringify(filters)}`;
    
    setIsLoading(true);
    start(); // Start verbose loading

    try {
      // Send filter request to streaming endpoint
      const response = await fetch('/api/chat/stream', {
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

      // Handle streaming response
      const data = await handleStreamingResponse(response);
      
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
      stop(); // Stop verbose loading
    }
  };

  const handleItemSelect = async (vehicle: Vehicle) => {
    setSelectedItem(vehicle);
    setShowDetails(true);
    setDetailViewStartTime(Date.now());
    
    // Log the vehicle view event
    if (sessionId) {
      await LoggingService.logVehicleView(sessionId, vehicle.id, vehicle.vin);
    }
  };

  const handleItemSelectSync = (vehicle: Vehicle) => {
    handleItemSelect(vehicle);
  };

  // Find the index of the selected vehicle
  const getSelectedVehicleIndex = () => {
    if (!selectedItem) return 0;
    return vehicles.findIndex(v => v.id === selectedItem.id) + 1;
  };

  const handleBackToRecommendations = async () => {
    // Log the duration spent viewing details
    if (sessionId && selectedItem && detailViewStartTime) {
      const duration = Date.now() - detailViewStartTime;
      await LoggingService.logCustomEvent(sessionId, 'vehicle_detail_duration', {
        vehicle_id: selectedItem.id,
        vin: selectedItem.vin || 'unknown',
        duration_ms: duration,
        duration_seconds: Math.round(duration / 1000)
      });
    }
    
    setShowDetails(false);
    setSelectedItem(null);
    setDetailViewStartTime(null);
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
        {/* Recommendations at the top or Details View or Favorites */}
        {(hasReceivedRecommendations || showFavorites) && (
          <div className="flex-shrink-0 p-1 border-b border-slate-600/30 h-[50%]">
            <div className="max-w-6xl mx-auto h-full">
              {showFavorites ? (
                <div className="glass-dark rounded-xl p-2 relative overflow-hidden h-full">
                  <FavoritesPage
                    favorites={favorites}
                    onToggleFavorite={toggleFavorite}
                    isFavorite={isFavorite}
                    onItemSelect={handleItemSelectSync}
                    onClose={() => setShowFavorites(false)}
                  />
                </div>
              ) : showDetails && selectedItem ? (
                <div className="glass-dark rounded-xl p-2 relative overflow-y-auto h-full">
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
                <div className="h-full">
                  <RecommendationCarousel 
                    vehicles={vehicles} 
                    onItemSelect={handleItemSelectSync}
                    showPlaceholders={false}
                    onToggleFavorite={toggleFavorite}
                    isFavorite={isFavorite}
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Chat Messages - Only last 3 turns */}
        <div className={`${(hasReceivedRecommendations || showFavorites) ? 'h-[40%]' : 'flex-1'} flex-shrink-0 overflow-y-auto p-12 relative min-h-0`}>
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
                    <div 
                      className="text-sm leading-relaxed chat-message prose prose-invert max-w-none"
                      dangerouslySetInnerHTML={{ __html: parseMarkdown(message.content) }}
                    />
                  </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="glass-dark p-4 rounded-2xl">
                  <div className="flex items-center space-x-3">
                    <span className="text-sm text-slate-300/80 backdrop-blur-sm relative overflow-hidden">
                      <span className="loading-ripple">{currentMessage}</span>
                    </span>
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce"></div>
                      <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                      <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Chat Input */}
        <div className={`${(hasReceivedRecommendations || showFavorites) ? 'h-[10%]' : ''} flex-shrink-0 border-t border-slate-600/30 glass-dark flex items-center px-8 py-6`}>
          <div className="w-3/4 mx-auto my-autoitems-center justify-center py-6">
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

      {/* Favorites Button */}
      <button
        onClick={() => setShowFavorites(!showFavorites)}
        className="fixed top-20 left-6 w-12 h-12 glass-dark border border-slate-600/30 rounded-xl flex items-center justify-center hover:bg-slate-700/50 transition-all duration-200 shadow-lg z-50"
        title={showFavorites ? "Hide Favorites" : "View Favorites"}
      >
        <svg 
          className={`w-6 h-6 ${favorites.length > 0 ? 'text-red-500 fill-red-500' : 'text-slate-300'}`}
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
        </svg>
      </button>

    </div>
  );
}