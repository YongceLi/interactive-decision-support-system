'use client';

import { Vehicle } from '@/types/vehicle';

interface ItemDetailModalProps {
  item: Vehicle;
  onClose: () => void;
}

export default function ItemDetailModal({ item, onClose }: ItemDetailModalProps) {
  // Use Auto.dev image URL
  const primaryImage = item.image_url;
  const hasValidImage = primaryImage && !primaryImage.toLowerCase().includes('.svg');

  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-md flex items-center justify-center p-4 z-50">
      <div className="glass-dark rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="sticky top-0 glass-dark border-b border-slate-600/30 px-6 py-4 flex items-center justify-between z-10">
          <h2 className="text-2xl font-bold text-slate-100">
            {item.year} {item.make} {item.model}
          </h2>
          <button
            onClick={onClose}
            className="bg-gradient-to-r from-purple-500 to-blue-500 hover:from-purple-600 hover:to-blue-600 text-white px-6 py-2 rounded-xl transition-all duration-200 hover:scale-105 transform font-semibold shadow-lg flex items-center space-x-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            <span>Back</span>
          </button>
        </div>

        <div className="p-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Image Section */}
            <div className="space-y-4">
                      <div className="aspect-video bg-gradient-to-br from-slate-600 to-slate-700 rounded-xl overflow-hidden relative">
                        {hasValidImage ? (
                          <>
                            <img
                              src={primaryImage}
                              alt={`${item.year} ${item.make} ${item.model}`}
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                // Hide the image if it fails to load and show the emoji instead
                                const target = e.target as HTMLImageElement;
                                target.style.display = 'none';
                                const parent = target.parentElement;
                                if (parent && !parent.querySelector('.fallback-text')) {
                                  const fallback = document.createElement('div');
                                  fallback.className = 'fallback-text text-slate-400 text-lg absolute inset-0 flex items-center justify-center';
                                  fallback.innerHTML = '<div class="text-center px-4"><div class="text-lg font-medium">No Image Found</div></div>';
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
                            <div className="fallback-text text-slate-400 text-lg absolute inset-0 flex items-center justify-center">
                              <div className="text-center px-4">
                                <div className="text-lg font-medium">No Image Found</div>
                              </div>
                            </div>
                          </>
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-slate-400">
                            <div className="text-center px-4">
                              <div className="text-lg font-medium">No Image Found</div>
                            </div>
                          </div>
                        )}
                      </div>

              {/* Price and Key Info */}
              <div className="glass-card rounded-xl p-4">
                <div className="text-3xl font-bold text-green-400 mb-2">
                  {item.price ? `$${item.price.toLocaleString()}` : 'Check with dealership'}
                </div>
                {item.mileage && (
                  <div className="text-slate-300 mb-2">
                    <span className="font-medium text-slate-400">Mileage:</span> {typeof item.mileage === 'number' ? item.mileage.toLocaleString() : item.mileage} miles
                  </div>
                )}
                {item.location && (
                  <div className="text-slate-300">
                    <span className="font-medium text-slate-400">Location:</span> {item.location}
                  </div>
                )}
              </div>
            </div>

            {/* Details Section */}
            <div className="space-y-6">
              {/* Basic Info */}
              <div>
                <h3 className="text-lg font-semibold text-slate-100 mb-3">Item Information</h3>
                <div className="grid grid-cols-2 gap-4">
                  {item.trim && (
                    <div>
                      <span className="text-sm text-slate-400">Trim</span>
                      <div className="font-medium text-slate-200">{item.trim}</div>
                    </div>
                  )}
                  {item.body_style && (
                    <div>
                      <span className="text-sm text-slate-400">Body Style</span>
                      <div className="font-medium text-slate-200 capitalize">{item.body_style}</div>
                    </div>
                  )}
                  {item.engine && (
                    <div>
                      <span className="text-sm text-slate-400">Engine</span>
                      <div className="font-medium text-slate-200">{item.engine}</div>
                    </div>
                  )}
                  {item.transmission && (
                    <div>
                      <span className="text-sm text-slate-400">Transmission</span>
                      <div className="font-medium text-slate-200">{item.transmission}</div>
                    </div>
                  )}
                  {item.exterior_color && (
                    <div>
                      <span className="text-sm text-slate-400">Exterior Color</span>
                      <div className="font-medium text-slate-200">{item.exterior_color}</div>
                    </div>
                  )}
                  {item.interior_color && (
                    <div>
                      <span className="text-sm text-slate-400">Interior Color</span>
                      <div className="font-medium text-slate-200">{item.interior_color}</div>
                    </div>
                  )}
                  {item.doors && (
                    <div>
                      <span className="text-sm text-slate-400">Doors</span>
                      <div className="font-medium text-slate-200">{item.doors}</div>
                    </div>
                  )}
                  {item.seating_capacity && (
                    <div>
                      <span className="text-sm text-slate-400">Seating</span>
                      <div className="font-medium text-slate-200">{item.seating_capacity} passengers</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Fuel Economy */}
              {item.fuel_economy && (
                <div>
                  <h3 className="text-lg font-semibold text-slate-100 mb-3">Fuel Economy</h3>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center glass-card rounded-lg p-3">
                      <div className="text-2xl font-bold text-green-400">{item.fuel_economy.city}</div>
                      <div className="text-sm text-slate-400">City MPG</div>
                    </div>
                    <div className="text-center glass-card rounded-lg p-3">
                      <div className="text-2xl font-bold text-green-400">{item.fuel_economy.highway}</div>
                      <div className="text-sm text-slate-400">Highway MPG</div>
                    </div>
                    <div className="text-center glass-card rounded-lg p-3">
                      <div className="text-2xl font-bold text-green-400">{item.fuel_economy.combined}</div>
                      <div className="text-sm text-slate-400">Combined MPG</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Safety Rating */}
              {item.safety_rating && (
                <div>
                  <h3 className="text-lg font-semibold text-slate-100 mb-3">Safety Rating</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center glass-card rounded-lg p-3">
                      <div className="text-2xl font-bold text-green-400">{item.safety_rating.overall}</div>
                      <div className="text-sm text-slate-400">Overall Rating</div>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div>
                        <div className="text-lg font-semibold text-slate-200">{item.safety_rating.frontal}</div>
                        <div className="text-xs text-slate-400">Frontal</div>
                      </div>
                      <div>
                        <div className="text-lg font-semibold text-slate-200">{item.safety_rating.side}</div>
                        <div className="text-xs text-slate-400">Side</div>
                      </div>
                      <div>
                        <div className="text-lg font-semibold text-slate-200">{item.safety_rating.rollover}</div>
                        <div className="text-xs text-slate-400">Rollover</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Features */}
              {item.features && item.features.length > 0 && (
                <div>
                  <h3 className="text-lg font-semibold text-slate-100 mb-3">Features</h3>
                  <div className="flex flex-wrap gap-2">
                    {item.features.map((feature, index) => (
                      <span
                        key={index}
                        className="glass-card text-slate-200 px-3 py-1 rounded-full text-sm border border-slate-600/30"
                      >
                        {feature}
                      </span>
                    ))}
                  </div>
                </div>
              )}

                      {/* Additional Information */}
                      <div className="pt-6 border-t border-slate-600/30">
                        <div className="glass-card rounded-lg p-4">
                          <h3 className="text-lg font-semibold text-slate-100 mb-2">Item Information</h3>
                          <p className="text-slate-300 text-sm">
                            This item is available for viewing and test drives. Contact the dealer for more information about availability, financing options, and scheduling a test drive.
                            {item.location && (
                              <span className="block mt-2 text-slate-400">
                                Dealership location: {item.location}
                              </span>
                            )}
                            {item.carfax_url && (
                              <span className="block mt-3">
                                <a 
                                  href={item.carfax_url} 
                                  target="_blank" 
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center space-x-2 text-blue-400 hover:text-blue-300 transition-colors duration-200"
                                >
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                  </svg>
                                  <span>View CarFax Report</span>
                                </a>
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
