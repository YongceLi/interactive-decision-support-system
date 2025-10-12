'use client';

import { Vehicle } from '@/types/vehicle';

interface CarDetailModalProps {
  car: Vehicle;
  onClose: () => void;
}

export default function CarDetailModal({ car, onClose }: CarDetailModalProps) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between z-10 shadow-sm">
          <h2 className="text-2xl font-bold text-gray-900">
            {car.year} {car.make} {car.model}
          </h2>
          <button
            onClick={onClose}
            className="bg-red-800 hover:bg-red-900 text-white px-6 py-2 rounded-lg transition-all duration-200 hover:scale-105 transform font-semibold shadow-md flex items-center space-x-2"
          >
            <span>←</span>
            <span>Back</span>
          </button>
        </div>

        <div className="p-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Image Section */}
            <div className="space-y-4">
              <div className="aspect-video bg-gray-200 rounded-lg overflow-hidden">
                {car.image_url ? (
                  <img
                    src={car.image_url}
                    alt={`${car.year} ${car.make} ${car.model}`}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-400">
                    <div className="text-center">
                      <div className="text-lg">No Image Available</div>
                    </div>
                  </div>
                )}
              </div>

              {/* Price and Key Info */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="text-3xl font-bold text-red-800 mb-2">
                  ${car.price ? car.price.toLocaleString() : 'Price N/A'}
                </div>
                {car.mileage && (
                  <div className="text-gray-600 mb-2">
                    <span className="font-medium">Mileage:</span> {typeof car.mileage === 'number' ? car.mileage.toLocaleString() : car.mileage} miles
                  </div>
                )}
                {car.location && (
                  <div className="text-gray-600">
                    <span className="font-medium">Location:</span> {car.location}
                  </div>
                )}
              </div>
            </div>

            {/* Details Section */}
            <div className="space-y-6">
              {/* Basic Info */}
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-3">Vehicle Information</h3>
                <div className="grid grid-cols-2 gap-4">
                  {car.trim && (
                    <div>
                      <span className="text-sm text-gray-500">Trim</span>
                      <div className="font-medium">{car.trim}</div>
                    </div>
                  )}
                  {car.body_style && (
                    <div>
                      <span className="text-sm text-gray-500">Body Style</span>
                      <div className="font-medium capitalize">{car.body_style}</div>
                    </div>
                  )}
                  {car.engine && (
                    <div>
                      <span className="text-sm text-gray-500">Engine</span>
                      <div className="font-medium">{car.engine}</div>
                    </div>
                  )}
                  {car.transmission && (
                    <div>
                      <span className="text-sm text-gray-500">Transmission</span>
                      <div className="font-medium">{car.transmission}</div>
                    </div>
                  )}
                  {car.exterior_color && (
                    <div>
                      <span className="text-sm text-gray-500">Exterior Color</span>
                      <div className="font-medium">{car.exterior_color}</div>
                    </div>
                  )}
                  {car.interior_color && (
                    <div>
                      <span className="text-sm text-gray-500">Interior Color</span>
                      <div className="font-medium">{car.interior_color}</div>
                    </div>
                  )}
                  {car.doors && (
                    <div>
                      <span className="text-sm text-gray-500">Doors</span>
                      <div className="font-medium">{car.doors}</div>
                    </div>
                  )}
                  {car.seating_capacity && (
                    <div>
                      <span className="text-sm text-gray-500">Seating</span>
                      <div className="font-medium">{car.seating_capacity} passengers</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Fuel Economy */}
              {car.fuel_economy && (
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Fuel Economy</h3>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center bg-gray-50 rounded-lg p-3">
                      <div className="text-2xl font-bold text-red-800">{car.fuel_economy.city}</div>
                      <div className="text-sm text-gray-500">City MPG</div>
                    </div>
                    <div className="text-center bg-gray-50 rounded-lg p-3">
                      <div className="text-2xl font-bold text-red-800">{car.fuel_economy.highway}</div>
                      <div className="text-sm text-gray-500">Highway MPG</div>
                    </div>
                    <div className="text-center bg-gray-50 rounded-lg p-3">
                      <div className="text-2xl font-bold text-red-800">{car.fuel_economy.combined}</div>
                      <div className="text-sm text-gray-500">Combined MPG</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Safety Rating */}
              {car.safety_rating && (
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Safety Rating</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center bg-gray-50 rounded-lg p-3">
                      <div className="text-2xl font-bold text-red-800">{car.safety_rating.overall}</div>
                      <div className="text-sm text-gray-500">Overall Rating</div>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div>
                        <div className="text-lg font-semibold">{car.safety_rating.frontal}</div>
                        <div className="text-xs text-gray-500">Frontal</div>
                      </div>
                      <div>
                        <div className="text-lg font-semibold">{car.safety_rating.side}</div>
                        <div className="text-xs text-gray-500">Side</div>
                      </div>
                      <div>
                        <div className="text-lg font-semibold">{car.safety_rating.rollover}</div>
                        <div className="text-xs text-gray-500">Rollover</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Features */}
              {car.features && car.features.length > 0 && (
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Features</h3>
                  <div className="flex flex-wrap gap-2">
                    {car.features.map((feature, index) => (
                      <span
                        key={index}
                        className="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm"
                      >
                        {feature}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Additional Information */}
              <div className="pt-6 border-t border-gray-200">
                <div className="bg-gray-50 rounded-lg p-4">
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Vehicle Information</h3>
                  <p className="text-gray-600 text-sm">
                    This vehicle is available for viewing and test drives. Contact the dealer for more information about availability, financing options, and scheduling a test drive.
                    {car.location && (
                      <span className="block mt-2 text-gray-500">
                        Dealership location: {car.location}
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
