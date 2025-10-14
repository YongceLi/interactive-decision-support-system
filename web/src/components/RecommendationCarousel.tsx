'use client';

import { useState, useEffect, useRef } from 'react';
import { Vehicle } from '@/types/vehicle';

interface RecommendationCarouselProps {
  vehicles: Vehicle[];
  onItemSelect?: (vehicle: Vehicle) => void;
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

export default function RecommendationCarousel({ vehicles, onItemSelect }: RecommendationCarouselProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);
  const [animationDirection, setAnimationDirection] = useState<'left' | 'right' | null>(null);
  const [viewTimes, setViewTimes] = useState<Record<string, number>>({});
  const startTimeRef = useRef<number>(Date.now());
  const isIdleRef = useRef<boolean>(false);

  // Reset to first item when new vehicles are loaded
  useEffect(() => {
    if (vehicles.length > 0) {
      setCurrentIndex(0);
    }
  }, [vehicles]);

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
    setCurrentIndex((prev) => (prev + 1) % vehicles.length);
    
    setTimeout(() => {
      setIsAnimating(false);
      setAnimationDirection(null);
    }, 500);
  };

  const prevVehicle = () => {
    if (vehicles.length === 0 || isAnimating) return;
    
    setIsAnimating(true);
    setAnimationDirection('left');
    setCurrentIndex((prev) => (prev - 1 + vehicles.length) % vehicles.length);
    
    setTimeout(() => {
      setIsAnimating(false);
      setAnimationDirection(null);
    }, 500);
  };

  // Create placeholder cards if no vehicles
  const showPlaceholder = vehicles.length === 0;
  
  const currentVehicle = !showPlaceholder ? vehicles[currentIndex] : null;

  // Get the 3 cards to display (current, next, previous)
  const getDisplayCards = (): DisplayCard[] => {
    if (showPlaceholder) {
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
    <div className="relative w-full">
      {/* Header */}
      <div className="mb-4 text-center">
        <h3 className="text-lg font-semibold text-slate-200 mb-1">Recommendations For You</h3>
        <p className="text-sm text-slate-400">
          {showPlaceholder ? 'Waiting for your preferences' : `${vehicles.length} ${vehicles.length === 1 ? 'option' : 'options'} found`}
        </p>
      </div>

      {/* Carousel Container */}
      <div className="relative flex items-center justify-center">
        {/* Left Arrow */}
        <button
          onClick={prevVehicle}
          disabled={isAnimating || vehicles.length <= 1 || showPlaceholder}
          className="absolute left-0 z-10 w-10 h-10 rounded-full glass-dark border border-slate-600/30 flex items-center justify-center hover:bg-slate-700/50 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed -translate-x-6"
        >
          <svg className="w-5 h-5 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
              <div className="glass-card rounded-xl p-4 w-[300px] shadow-2xl">
                {card.isPlaceholder ? (
                  /* Placeholder Card Content */
                  <>
                            <div className="aspect-[3/2] bg-gradient-to-br from-slate-600 to-slate-700 rounded-lg mb-3 flex items-center justify-center overflow-hidden">
                              <div className="text-slate-400 text-sm opacity-50 text-center px-2">No Image Found</div>
                            </div>
                    <div className="space-y-2">
                      <h4 className="text-sm font-bold text-slate-400 mb-2 leading-tight">
                        Tell us what you want
                      </h4>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-slate-500">Price:</span>
                          <span className="text-slate-500">---</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Mileage:</span>
                          <span className="text-slate-500">---</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Location:</span>
                          <span className="text-slate-500">---</span>
                        </div>
                      </div>
                      <button 
                        disabled
                        className="w-full bg-slate-600 text-slate-400 py-2 rounded-lg text-xs font-medium cursor-not-allowed mt-3"
                      >
                        Get Recommendations
                      </button>
                    </div>
                  </>
        ) : (
          /* Real Item Card Content */
          <VehicleCard vehicle={card.vehicle} onItemSelect={onItemSelect} />
        )}
                      </div>
                    </div>
                  ))}
                </div>

        {/* Right Arrow */}
        <button
          onClick={nextVehicle}
          disabled={isAnimating || vehicles.length <= 1 || showPlaceholder}
          className="absolute right-0 z-10 w-10 h-10 rounded-full glass-dark border border-slate-600/30 flex items-center justify-center hover:bg-slate-700/50 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed translate-x-6"
        >
          <svg className="w-5 h-5 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* Counter */}
      <div className="text-center mt-4">
        <span className="text-sm text-slate-400 font-medium">
          {showPlaceholder ? '0 of 0' : `${currentIndex + 1} of ${vehicles.length}`}
        </span>
      </div>
    </div>
  );
}

// VehicleCard component
function VehicleCard({ vehicle, onItemSelect }: { vehicle: Vehicle; onItemSelect?: (vehicle: Vehicle) => void }) {
  // Use Auto.dev image URL
  const primaryImage = vehicle.image_url;
  const hasValidImage = primaryImage && !primaryImage.toLowerCase().includes('.svg');

  return (
    <>
      <div className="aspect-[3/2] bg-gradient-to-br from-slate-600 to-slate-700 rounded-lg mb-3 flex items-center justify-center overflow-hidden relative">
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
                                      fallback.className = 'fallback-text text-slate-400 text-sm absolute inset-0 flex items-center justify-center text-center px-2';
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
            <div className="fallback-text text-slate-400 text-sm absolute inset-0 flex items-center justify-center text-center px-2">
              No Image Found
            </div>
          </>
        ) : (
          <div className="text-slate-400 text-sm flex items-center justify-center text-center px-2">
            No Image Found
          </div>
        )}
      </div>
      
      <div className="space-y-2">
        <h4 className="text-sm font-bold text-slate-100 mb-2 leading-tight">
          {vehicle.year} {vehicle.make} {vehicle.model}
        </h4>
        
        <div className="space-y-1 text-xs">
          {vehicle.price && (
            <div className="flex justify-between">
              <span className="text-slate-400">Price:</span>
              <span className="font-semibold text-green-400">
                ${vehicle.price.toLocaleString()}
              </span>
            </div>
          )}
          
          {vehicle.mileage && (
            <div className="flex justify-between">
              <span className="text-slate-400">Mileage:</span>
              <span className="text-slate-300">{vehicle.mileage.toLocaleString()} mi</span>
            </div>
          )}
          
          {vehicle.location && (
            <div className="flex justify-between">
              <span className="text-slate-400">Location:</span>
              <span className="text-slate-300 text-right max-w-[140px] truncate">{vehicle.location}</span>
            </div>
          )}
        </div>

        <button 
          onClick={() => onItemSelect?.(vehicle)}
          className="w-full bg-gradient-to-r from-purple-500 to-blue-500 text-white py-2 rounded-lg text-xs font-medium hover:from-purple-600 hover:to-blue-600 transition-all duration-200 shadow-lg hover:shadow-xl mt-3"
        >
          View Details
        </button>
      </div>
    </>
  );
}
