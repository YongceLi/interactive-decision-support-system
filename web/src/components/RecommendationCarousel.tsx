'use client';

import { useState, useEffect, useRef } from 'react';
import { Vehicle } from '@/types/vehicle';

interface RecommendationCarouselProps {
  vehicles: Vehicle[];
}

interface ViewTimeData {
  vehicleId: string;
  startTime: number;
  totalTime: number;
}

export default function RecommendationCarousel({ vehicles }: RecommendationCarouselProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);
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
    setCurrentIndex((prev) => (prev + 1) % vehicles.length);
    
    setTimeout(() => setIsAnimating(false), 300);
  };

  const prevVehicle = () => {
    if (vehicles.length === 0 || isAnimating) return;
    
    setIsAnimating(true);
    setCurrentIndex((prev) => (prev - 1 + vehicles.length) % vehicles.length);
    
    setTimeout(() => setIsAnimating(false), 300);
  };

  if (vehicles.length === 0) {
    return null; // Don't show anything when no vehicles
  }

  const currentVehicle = vehicles[currentIndex];

  return (
    <div className="relative w-full">
      {/* Header */}
      <div className="mb-4 text-center">
        <h3 className="text-lg font-semibold text-slate-200 mb-1">Recommendations</h3>
        <p className="text-sm text-slate-400">
          {vehicles.length} {vehicles.length === 1 ? 'option' : 'options'} found
        </p>
      </div>

      {/* Carousel Container */}
      <div className="relative flex items-center justify-center">
        {/* Left Arrow */}
        <button
          onClick={prevVehicle}
          disabled={isAnimating || vehicles.length <= 1}
          className="absolute left-0 z-10 w-12 h-12 rounded-full glass-dark border border-slate-600/30 flex items-center justify-center hover:bg-slate-700/50 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed -translate-x-6"
        >
          <svg className="w-6 h-6 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {/* Vehicle Card */}
        <div className={`transition-all duration-300 ${isAnimating ? 'opacity-50 scale-95' : 'opacity-100 scale-100'}`}>
          <div className="glass-card rounded-2xl p-6 w-[500px] shadow-2xl">
            {/* Vehicle Image */}
            <div className="aspect-[4/3] bg-gradient-to-br from-slate-600 to-slate-700 rounded-xl mb-4 flex items-center justify-center overflow-hidden">
              {currentVehicle.image_url ? (
                <img
                  src={currentVehicle.image_url}
                  alt={`${currentVehicle.year} ${currentVehicle.make} ${currentVehicle.model}`}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="text-slate-400 text-6xl">🚗</div>
              )}
            </div>

            {/* Vehicle Info */}
            <div className="space-y-3">
              <h4 className="text-xl font-bold text-slate-100 mb-3">
                {currentVehicle.year} {currentVehicle.make} {currentVehicle.model}
              </h4>
              
              <div className="grid grid-cols-2 gap-4 text-sm">
                {currentVehicle.price && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Price:</span>
                    <span className="font-semibold text-green-400">
                      ${currentVehicle.price.toLocaleString()}
                    </span>
                  </div>
                )}
                
                {currentVehicle.mileage && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Mileage:</span>
                    <span className="text-slate-300">{currentVehicle.mileage.toLocaleString()} mi</span>
                  </div>
                )}
                
                {currentVehicle.location && (
                  <div className="flex justify-between col-span-2">
                    <span className="text-slate-400">Location:</span>
                    <span className="text-slate-300">{currentVehicle.location}</span>
                  </div>
                )}
              </div>

              {/* Action Button */}
              <button className="w-full bg-gradient-to-r from-purple-500 to-blue-500 text-white py-3 rounded-xl font-medium hover:from-purple-600 hover:to-blue-600 transition-all duration-200 shadow-lg hover:shadow-xl mt-4">
                View Details
              </button>
            </div>
          </div>
        </div>

        {/* Right Arrow */}
        <button
          onClick={nextVehicle}
          disabled={isAnimating || vehicles.length <= 1}
          className="absolute right-0 z-10 w-12 h-12 rounded-full glass-dark border border-slate-600/30 flex items-center justify-center hover:bg-slate-700/50 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed translate-x-6"
        >
          <svg className="w-6 h-6 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* Counter */}
      <div className="text-center mt-4">
        <span className="text-sm text-slate-400 font-medium">
          {currentIndex + 1} of {vehicles.length}
        </span>
      </div>
    </div>
  );
}
