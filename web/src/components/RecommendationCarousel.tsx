'use client';

import { useState, useEffect, useRef } from 'react';
import { Vehicle } from '@/types/vehicle';

interface RecommendationCarouselProps {
  vehicles: Vehicle[];
  onItemSelect?: (vehicle: Vehicle) => void;
  showPlaceholders?: boolean;
  onToggleFavorite?: (vehicle: Vehicle) => void;
  isFavorite?: (vehicleId: string) => boolean;
  currentIndex?: number;
  onIndexChange?: (index: number) => void;
}

interface ViewTimeData {
  vehicleId: string;
  startTime: number;
  totalTime: number;
}

type DisplayCard = {
  position: number;
  isCenter: boolean;
  isPlaceholder: true;
} | {
  vehicle: Vehicle;
  position: number;
  isCenter: boolean;
  isPlaceholder: false;
};

export default function RecommendationCarousel({ vehicles, onItemSelect, showPlaceholders = false, onToggleFavorite, isFavorite, currentIndex: controlledIndex, onIndexChange }: RecommendationCarouselProps) {
  const [internalIndex, setInternalIndex] = useState(0);
  const currentIndex = controlledIndex !== undefined ? controlledIndex : internalIndex;
  const setCurrentIndex = (index: number) => {
    if (controlledIndex !== undefined && onIndexChange) {
      onIndexChange(index);
    } else {
      setInternalIndex(index);
    }
  };
  const [isAnimating, setIsAnimating] = useState(false);
  const [animationDirection, setAnimationDirection] = useState<'left' | 'right' | null>(null);
  const [viewTimes, setViewTimes] = useState<Record<string, number>>({});
  const startTimeRef = useRef<number>(Date.now());
  const isIdleRef = useRef<boolean>(false);

  // Reset to first item when new vehicles are loaded (only if not controlled externally)
  useEffect(() => {
    if (vehicles.length > 0 && controlledIndex === undefined) {
      setCurrentIndex(0);
    }
  }, [vehicles, controlledIndex]);

  // Track viewing time for each vehicle
  useEffect(() => {
    if (vehicles.length === 0) return;

    const currentVehicle = vehicles[currentIndex];
    if (!currentVehicle) return;

    startTimeRef.current = Date.now();

    // Check for user activity to detect idle state
    const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
    let lastActivity = Date.now();

    const updateActivity = () => {
      lastActivity = Date.now();
      isIdleRef.current = false;
    };

    const checkIdle = () => {
      const now = Date.now();
      if (now - lastActivity > 30000) { // 30 seconds of inactivity
        isIdleRef.current = true;
      }
    };

    // Add event listeners
    activityEvents.forEach(event => {
      document.addEventListener(event, updateActivity);
    });

    // Check for idle every 5 seconds
    const idleInterval = setInterval(checkIdle, 5000);

    // Cleanup function to save time when component unmounts or vehicle changes
    return () => {
      const endTime = Date.now();
      const viewDuration = endTime - startTimeRef.current;
      
      // Only count time if user wasn't idle
      if (!isIdleRef.current && viewDuration > 1000) { // At least 1 second of active viewing
        setViewTimes(prev => ({
          ...prev,
          [currentVehicle.id]: (prev[currentVehicle.id] || 0) + viewDuration
        }));

        // Send tracking data to analytics endpoint (you can implement this)
        console.log(`User viewed ${currentVehicle.make} ${currentVehicle.model} for ${viewDuration}ms`);
      }

      // Remove event listeners
      activityEvents.forEach(event => {
        document.removeEventListener(event, updateActivity);
      });
      clearInterval(idleInterval);
    };
  }, [currentIndex, vehicles]);

  const nextVehicle = () => {
    if (vehicles.length === 0 || isAnimating) return;
    
    setIsAnimating(true);
    setAnimationDirection('right');
    const newIndex = (currentIndex + 1) % vehicles.length;
    setCurrentIndex(newIndex);
    
    setTimeout(() => {
      setIsAnimating(false);
      setAnimationDirection(null);
    }, 500);
  };

  const prevVehicle = () => {
    if (vehicles.length === 0 || isAnimating) return;
    
    setIsAnimating(true);
    setAnimationDirection('left');
    const newIndex = (currentIndex - 1 + vehicles.length) % vehicles.length;
    setCurrentIndex(newIndex);
    
    setTimeout(() => {
      setIsAnimating(false);
      setAnimationDirection(null);
    }, 500);
  };

  // Use the showPlaceholders prop to determine if we should show placeholder cards
  const currentVehicle = !showPlaceholders ? vehicles[currentIndex] : null;

  // Get the 3 cards to display (current, next, previous)
  const getDisplayCards = (): DisplayCard[] => {
    if (showPlaceholders) {
      // Return 3 placeholder cards
      return [
        { position: -1, isCenter: false, isPlaceholder: true },
        { position: 0, isCenter: true, isPlaceholder: true },
        { position: 1, isCenter: false, isPlaceholder: true }
      ];
    }
    
    const cards: DisplayCard[] = [];
    for (let i = -1; i <= 1; i++) {
      const index = (currentIndex + i + vehicles.length) % vehicles.length;
      cards.push({
        vehicle: vehicles[index],
        position: i,
        isCenter: i === 0,
        isPlaceholder: false
      });
    }
    return cards;
  };

  const displayCards = getDisplayCards();

  return (
    <div className="relative w-full h-full flex flex-col">
      {/* Carousel Container */}
      <div className="relative flex items-center justify-center flex-1 overflow-hidden">
        {/* Left Arrow */}
        <button
          onClick={prevVehicle}
          disabled={isAnimating || vehicles.length <= 1 || showPlaceholders}
          className="absolute left-0 z-10 w-12 h-12 rounded-full bg-white border border-[#8b959e]/40 flex items-center justify-center hover:bg-[#8b959e]/5 transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed shadow-sm"
        >
          <svg className="w-6 h-6 text-[#ff1323]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {/* Three Item Cards */}
        <div className="flex items-center justify-center space-x-4">
          {displayCards.map((card, idx) => (
            <div
              key={card.isPlaceholder ? `placeholder-${idx}` : `${card.vehicle.id}-${idx}`}
              className={`transition-all duration-500 ease-out ${
                card.isCenter
                  ? 'transform rotate-0 translate-x-0 scale-100 z-10'
                  : card.position === -1
                    ? 'transform rotate-2 translate-x-2 scale-95 opacity-70 z-0'
                    : 'transform -rotate-2 -translate-x-2 scale-95 opacity-70 z-0'
              } ${
                isAnimating && card.isCenter
                  ? 'transform -rotate-8 -translate-x-4 scale-90 z-10'
                  : ''
              }`}
            >
              <div className="bg-white rounded-xl p-4 w-[280px] h-full max-h-[360px] border border-[#8b959e]/30 shadow-sm flex flex-col overflow-hidden">
                {card.isPlaceholder ? (
                  /* Placeholder Card Content */
                  <>
                            <div className="aspect-[3/2] bg-gradient-to-br from-[#ff1323]/30 to-white rounded-lg mb-3 flex items-center justify-center overflow-hidden">
                              <div className="text-[#8b959e] text-base opacity-50 text-center px-2">Future Recommendations</div>
                            </div>
                    <div className="space-y-2">
                      <h4 className="text-lg font-bold text-[#8b959e] mb-2 leading-tight">
                        Your recommendations will appear here
                      </h4>
                      <div className="space-y-1 text-base">
                        <div className="flex justify-between">
                          <span className="text-[#8b959e]">Price:</span>
                          <span className="text-[#8b959e]">---</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#8b959e]">Mileage:</span>
                          <span className="text-[#8b959e]">---</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#8b959e]">Location:</span>
                          <span className="text-[#8b959e]">---</span>
                        </div>
                      </div>
                      <button 
                        disabled
                        className="w-full bg-[#8b959e]/30 text-[#8b959e] py-2 rounded-lg text-base font-medium cursor-not-allowed mt-3"
                      >
                        Get Recommendations
                      </button>
                    </div>
                  </>
        ) : (
          /* Real Item Card Content */
          <VehicleCard 
            vehicle={card.vehicle} 
            onItemSelect={onItemSelect} 
            index={(currentIndex + card.position + vehicles.length) % vehicles.length + 1}
            isCenter={card.isCenter}
            onToggleFavorite={onToggleFavorite}
            isFavorite={isFavorite}
          />
        )}
                      </div>
                    </div>
                  ))}
                </div>

        {/* Right Arrow */}
        <button
          onClick={nextVehicle}
          disabled={isAnimating || vehicles.length <= 1 || showPlaceholders}
          className="absolute right-0 z-10 w-12 h-12 rounded-full bg-white border border-[#8b959e]/40 flex items-center justify-center hover:bg-[#8b959e]/5 transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed shadow-sm"
        >
          <svg className="w-6 h-6 text-[#ff1323]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}

// VehicleCard component
function VehicleCard({ vehicle, onItemSelect, index, isCenter, onToggleFavorite, isFavorite }: { 
  vehicle: Vehicle; 
  onItemSelect?: (vehicle: Vehicle) => void;
  index?: number;
  isCenter?: boolean;
  onToggleFavorite?: (vehicle: Vehicle) => void;
  isFavorite?: (vehicleId: string) => boolean;
}) {
  // Use Auto.dev image URL
  const primaryImage = vehicle.image_url;
  const hasValidImage = primaryImage && !primaryImage.toLowerCase().includes('.svg');

  return (
      <>
      <div className="aspect-[3/2] bg-gradient-to-br from-[#ff1323]/30 to-white rounded-lg mb-3 flex items-center justify-center overflow-hidden relative">
        {hasValidImage ? (
          <>
            <img
              src={primaryImage}
              alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`}
              className="w-full h-full object-cover"
              onError={(e) => {
                // Hide the image if it fails to load and show the emoji instead
                const target = e.target as HTMLImageElement;
                target.style.display = 'none';
                const parent = target.parentElement;
                                    if (parent && !parent.querySelector('.fallback-text')) {
                                      const fallback = document.createElement('div');
                                      fallback.className = 'fallback-text text-[#8b959e] text-base absolute inset-0 flex items-center justify-center text-center px-2';
                                      fallback.textContent = 'No Image Found';
                                      parent.appendChild(fallback);
                                    }
              }}
              onLoad={(e) => {
                // Hide fallback text when image loads successfully
                const target = e.target as HTMLImageElement;
                const parent = target.parentElement;
                const fallback = parent?.querySelector('.fallback-text');
                if (fallback) {
                  fallback.remove();
                }
              }}
            />
            {/* Show fallback text initially, will be hidden when image loads */}
            <div className="fallback-text text-[#8b959e] text-base absolute inset-0 flex items-center justify-center text-center px-2">
              No Image Found
            </div>
          </>
        ) : (
            <div className="text-[#8b959e] text-base flex items-center justify-center text-center px-2">
              No Image Found
            </div>
        )}
        
        {/* Heart button */}
        {onToggleFavorite && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleFavorite(vehicle);
            }}
            className="absolute top-2 left-2 w-8 h-8 bg-white border border-[#8b959e]/40 rounded-full flex items-center justify-center hover:border-[#ff1323] hover:shadow-md transition-all duration-200 z-20 shadow-sm"
          >
            <svg 
              className={`w-5 h-5 transition-all duration-200 ${isFavorite && isFavorite(vehicle.id) ? 'text-[#ff1323] fill-[#ff1323]' : 'text-[#8b959e]'}`}
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
          </button>
        )}
        
        {/* Number indicator - show on all cards */}
        {index && (
          <div className="absolute bottom-0 right-0 w-8 h-8 bg-white border border-[#ff1323] text-[#ff1323] rounded-lg flex items-center justify-center text-base font-bold shadow-sm">
            {index}
          </div>
        )}
      </div>
      
      <div className="space-y-2">
            <h4 className="text-lg font-bold text-black mb-2 leading-tight">
          {vehicle.year} {vehicle.make} {vehicle.model}
        </h4>
        
        <div className="space-y-1 text-base">
          {vehicle.price && (
            <div className="flex justify-between">
              <span className="text-[#8b959e]">Price:</span>
              <span className="font-bold text-black">
                ${vehicle.price.toLocaleString()}
              </span>
            </div>
          )}
          
          {vehicle.mileage && (
            <div className="flex justify-between">
              <span className="text-[#8b959e]">Mileage:</span>
              <span className="text-black">{vehicle.mileage.toLocaleString()} mi</span>
            </div>
          )}
          
          {vehicle.location && (
            <div className="flex justify-between">
              <span className="text-[#8b959e]">Location:</span>
              <span className="text-black text-right max-w-[160px] truncate">{vehicle.location}</span>
            </div>
          )}
        </div>

        <button
          onClick={() => onItemSelect && onItemSelect(vehicle)}
          className="w-full bg-[#ff1323] text-white py-2 rounded-lg text-base font-medium hover:bg-[#e01120] transition-all duration-200 shadow-sm hover:shadow-md mt-3"
        >
          View Details
        </button>
      </div>
    </>
  );
}
