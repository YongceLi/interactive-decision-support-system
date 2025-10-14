'use client';

import { Vehicle } from '@/types/vehicle';
import { useVehicleImages } from '@/hooks/useVehicleImages';

interface ItemGridProps {
  vehicles: Vehicle[];
  onItemSelect: (item: Vehicle) => void;
}

export default function ItemGrid({ vehicles, onItemSelect }: ItemGridProps) {
  return (
    <div className="h-full bg-stone-50">
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-stone-900 mb-2">
          Recommended Items
        </h2>
        <p className="text-stone-600">
          {vehicles.length} items found based on your preferences
        </p>
      </div>

      {vehicles.length === 0 ? (
        <div className="flex items-center justify-center h-64">
          <div className="text-center text-stone-500">
            <h3 className="text-lg font-medium mb-2">No items found</h3>
            <p className="text-sm">Try adjusting your search criteria or ask the agent for recommendations.</p>
            <p className="text-xs mt-2 text-stone-400">
              Only showing items with complete information matching your filters.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {vehicles.map((vehicle, index) => (
            <ItemCard 
              key={vehicle.id || `item-${index}`} 
              vehicle={vehicle} 
              onItemSelect={onItemSelect} 
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface ItemCardProps {
  vehicle: Vehicle;
  onItemSelect: (item: Vehicle) => void;
}

function ItemCard({ vehicle, onItemSelect }: ItemCardProps) {
  const { images, loading, error } = useVehicleImages(vehicle.vin);
  const displayImage = images[0]?.url || vehicle.image_url;

  return (
    <div
      onClick={() => onItemSelect(vehicle)}
      className="bg-white rounded-lg shadow-md hover:shadow-xl transition-all duration-300 cursor-pointer overflow-hidden border border-stone-200 hover:border-stone-300 hover:scale-105 transform flex flex-col h-full"
    >
      <div className="aspect-video bg-gray-200 relative">
        {loading ? (
          <div className="w-full h-full flex items-center justify-center text-gray-400">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-800 mx-auto mb-2"></div>
              <div className="text-sm">Loading image...</div>
            </div>
          </div>
        ) : displayImage ? (
          <img
            src={displayImage}
            alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`}
            className="w-full h-full object-cover"
            onError={(e) => {
              // Fallback to placeholder if image fails to load
              const target = e.target as HTMLImageElement;
              target.style.display = 'none';
              target.nextElementSibling?.classList.remove('hidden');
            }}
          />
        ) : null}
        
        <div className={`w-full h-full flex items-center justify-center text-gray-400 ${displayImage ? 'hidden' : ''}`}>
          <div className="text-center">
            <div className="text-sm">No Image Available</div>
          </div>
        </div>
        
        <div className="absolute top-2 right-2 bg-white px-2 py-1 rounded-full text-xs font-medium">
          {vehicle.year}
        </div>
      </div>
      
      <div className="p-4 flex-1 flex flex-col">
        <h3 className="font-semibold text-lg text-gray-900 mb-1">
          {vehicle.year} {vehicle.make} {vehicle.model}
        </h3>
        
        {vehicle.trim && (
          <p className="text-sm text-gray-600 mb-2">{vehicle.trim}</p>
        )}
        
        <div className="flex items-center justify-between mb-3">
          <span className="text-xl font-bold text-red-800">
            ${vehicle.price ? vehicle.price.toLocaleString() : 'Price N/A'}
          </span>
          {vehicle.mileage && (
            <span className="text-sm text-gray-500">
              {typeof vehicle.mileage === 'number' ? vehicle.mileage.toLocaleString() : vehicle.mileage} mi
            </span>
          )}
        </div>
        
        <div className="space-y-1 text-sm text-gray-600 flex-1">
          {vehicle.location && (
            <div className="flex items-center">
              <span className="mr-1">📍</span>
              {vehicle.location}
            </div>
          )}
          
          {vehicle.fuel_economy && (
            <div className="flex items-center">
              <span className="mr-1">⛽</span>
              {vehicle.fuel_economy.combined} MPG combined
            </div>
          )}
          
          {vehicle.safety_rating && (
            <div className="flex items-center">
              <span className="mr-1">🛡️</span>
              {vehicle.safety_rating.overall}/5 Safety Rating
            </div>
          )}
        </div>
        
        <div className="mt-4 pt-3 border-t border-stone-200">
          <button className="w-full bg-red-800 text-white py-2 px-4 rounded-lg hover:bg-red-900 transition-all duration-200 hover:scale-105 transform">
            View Details
          </button>
        </div>
      </div>
    </div>
  );
}