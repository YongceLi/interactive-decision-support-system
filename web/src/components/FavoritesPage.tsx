'use client';

import { Vehicle } from '@/types/vehicle';

interface FavoritesPageProps {
  favorites: Vehicle[];
  onToggleFavorite: (vehicle: Vehicle) => void;
  isFavorite: (vehicleId: string) => boolean;
  onItemSelect: (vehicle: Vehicle) => void;
  onClose: () => void;
}

export default function FavoritesPage({ favorites, onToggleFavorite, isFavorite, onItemSelect, onClose }: FavoritesPageProps) {
  const primaryImage = (vehicle: Vehicle) => vehicle.image_url;
  const hasValidImage = (vehicle: Vehicle) => {
    const img = primaryImage(vehicle);
    return img && !img.toLowerCase().includes('.svg');
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 px-2 pl-20 pt-2">
        <h1 className="text-xl font-bold text-slate-200">Favorites</h1>
        <button
          onClick={onClose}
          className="w-8 h-8 glass-dark border border-slate-600/30 rounded-lg flex items-center justify-center hover:bg-slate-700/50 transition-all duration-200"
        >
          <svg className="w-4 h-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto px-2 pl-20">
        {favorites.length === 0 ? (
          <div className="text-center py-12">
            <svg className="w-12 h-12 mx-auto mb-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
            <p className="text-slate-400 text-sm">No favorites yet</p>
            <p className="text-slate-500 text-xs mt-1">Start liking vehicles to see them here</p>
          </div>
        ) : (
          <div className="flex items-center justify-start gap-4 h-full">
              {favorites.map((vehicle) => (
                <div
                  key={vehicle.id}
                  className="glass-card rounded-xl p-4 w-[250px] h-full max-h-[300px] shadow-2xl flex flex-col overflow-hidden hover:shadow-2xl transition-all duration-200"
                >
                  {/* Image */}
                  <div className="aspect-[3/2] bg-gradient-to-br from-slate-600 to-slate-700 rounded-lg mb-3 flex items-center justify-center overflow-hidden relative">
                    {hasValidImage(vehicle) ? (
                      <>
                        <img
                          src={primaryImage(vehicle)}
                          alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`}
                          className="w-full h-full object-cover"
                          onError={(e) => {
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
                        />
                        <div className="fallback-text text-slate-400 text-sm absolute inset-0 flex items-center justify-center text-center px-2">
                          No Image Found
                        </div>
                      </>
                    ) : (
                      <div className="text-slate-400 text-sm flex items-center justify-center text-center px-2">
                        No Image Found
                      </div>
                    )}
                    
                    {/* Heart button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(vehicle);
                      }}
                      className="absolute top-2 left-2 w-8 h-8 glass-dark border border-slate-600/30 rounded-full flex items-center justify-center hover:bg-slate-700/50 transition-all duration-200 z-20"
                    >
                      <svg 
                        className={`w-5 h-5 transition-all duration-200 ${isFavorite(vehicle.id) ? 'text-red-500 fill-red-500' : 'text-slate-300'}`}
                        fill="none" 
                        stroke="currentColor" 
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                      </svg>
                    </button>
                  </div>

                  {/* Content */}
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
                      onClick={() => onItemSelect(vehicle)}
                      className="w-full bg-gradient-to-r from-purple-500 to-blue-500 text-white py-2 rounded-lg text-xs font-medium hover:from-purple-600 hover:to-blue-600 transition-all duration-200 shadow-lg hover:shadow-xl mt-3"
                    >
                      View Details
                    </button>
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}

