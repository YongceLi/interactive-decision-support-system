'use client';

import { useState } from 'react';

interface FilterMenuOverlayProps {
  onClose: () => void;
}

export default function FilterMenuOverlay({ onClose }: FilterMenuOverlayProps) {
  const [selectedBrands, setSelectedBrands] = useState<string[]>([]);
  const [selectedCondition, setSelectedCondition] = useState<string>('both');
  const [selectedCarTypes, setSelectedCarTypes] = useState<string[]>([]);
  const [maxMileage, setMaxMileage] = useState<number>(200000);
  const [minPrice, setMinPrice] = useState<number>(0);
  const [maxPrice, setMaxPrice] = useState<number>(200000);

  const brands = [
    'Toyota', 'Honda', 'Ford', 'Chevrolet', 'BMW', 'Mercedes-Benz',
    'Audi', 'Tesla', 'Subaru', 'Nissan', 'Hyundai', 'Kia',
    'Volkswagen', 'Mazda'
  ];

  const carTypes = [
    'Sedan', 'SUV', 'Truck', 'Hatchback', 'Coupe', 'Convertible'
  ];

  const handleBrandToggle = (brand: string) => {
    setSelectedBrands(prev => 
      prev.includes(brand) 
        ? prev.filter(b => b !== brand)
        : [...prev, brand]
    );
  };

  const handleCarTypeToggle = (carType: string) => {
    setSelectedCarTypes(prev => 
      prev.includes(carType) 
        ? prev.filter(c => c !== carType)
        : [...prev, carType]
    );
  };

  const handleApplyFilters = () => {
    // TODO: Implement filter application logic
    console.log('Applying filters:', {
      brands: selectedBrands,
      condition: selectedCondition,
      carTypes: selectedCarTypes,
      maxMileage,
      minPrice,
      maxPrice
    });
    onClose();
  };

  const handleClearAll = () => {
    setSelectedBrands([]);
    setSelectedCondition('both');
    setSelectedCarTypes([]);
    setMaxMileage(200000);
    setMinPrice(0);
    setMaxPrice(200000);
  };

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />
      
      {/* Sidebar */}
      <div 
        className="absolute left-0 top-0 h-full w-96 bg-slate-800 transform transition-transform duration-300 ease-in-out overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-600">
          <h2 className="text-xl font-bold text-white">Filters</h2>
          <button
            onClick={onClose}
            className="w-8 h-8 bg-slate-700 border border-slate-500 rounded-full flex items-center justify-center hover:bg-slate-600 transition-colors"
          >
            <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="h-full overflow-y-auto pb-32">
          <div className="p-6 space-y-6">
          {/* Brand Section */}
          <div>
            <h3 className="text-white font-semibold mb-4">Brand</h3>
            <div className="grid grid-cols-2 gap-2">
              {brands.map((brand) => (
                <button
                  key={brand}
                  onClick={() => handleBrandToggle(brand)}
                  className={`px-3 py-2 rounded-lg border text-sm font-medium transition-all duration-200 ${
                    selectedBrands.includes(brand)
                      ? 'bg-blue-600 border-blue-500 text-white'
                      : 'bg-slate-700 border-slate-500 text-white hover:bg-slate-600'
                  }`}
                >
                  {brand}
                </button>
              ))}
            </div>
          </div>

          {/* Condition Section */}
          <div>
            <h3 className="text-white font-semibold mb-4">Condition</h3>
            <div className="space-y-2">
              {['New', 'Used', 'Both'].map((condition) => (
                <button
                  key={condition}
                  onClick={() => setSelectedCondition(condition.toLowerCase())}
                  className={`w-full px-3 py-2 rounded-lg border text-sm font-medium transition-all duration-200 ${
                    selectedCondition === condition.toLowerCase()
                      ? 'bg-gradient-to-r from-purple-500 to-blue-500 border-transparent text-white'
                      : 'bg-slate-700 border-slate-500 text-white hover:bg-slate-600'
                  }`}
                >
                  {condition}
                </button>
              ))}
            </div>
          </div>

          {/* Car Type Section */}
          <div>
            <h3 className="text-white font-semibold mb-4">Car Type</h3>
            <div className="grid grid-cols-2 gap-2">
              {carTypes.map((carType) => (
                <button
                  key={carType}
                  onClick={() => handleCarTypeToggle(carType)}
                  className={`px-3 py-2 rounded-lg border text-sm font-medium transition-all duration-200 ${
                    selectedCarTypes.includes(carType)
                      ? 'bg-blue-600 border-blue-500 text-white'
                      : 'bg-slate-700 border-slate-500 text-white hover:bg-slate-600'
                  }`}
                >
                  {carType}
                </button>
              ))}
            </div>
          </div>

          {/* Max Mileage Section */}
          <div>
            <h3 className="text-white font-semibold mb-4">Max Mileage: {maxMileage.toLocaleString()} miles</h3>
            <input
              type="range"
              min="0"
              max="200000"
              step="5000"
              value={maxMileage}
              onChange={(e) => setMaxMileage(Number(e.target.value))}
              className="w-full h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer slider"
            />
            <div className="flex justify-between text-xs text-slate-400 mt-2">
              <span>0</span>
              <span>100K</span>
              <span>200K+</span>
            </div>
          </div>

          {/* Price Range Section */}
          <div>
            <h3 className="text-white font-semibold mb-4">Price Range</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Min Price</label>
                <input
                  type="number"
                  value={minPrice}
                  onChange={(e) => setMinPrice(Number(e.target.value))}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Max Price</label>
                <input
                  type="number"
                  value={maxPrice}
                  onChange={(e) => setMaxPrice(Number(e.target.value))}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-500 rounded-lg text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
            </div>
          </div>
          </div>
        </div>

        {/* Action Buttons - Fixed at bottom */}
        <div className="absolute bottom-0 left-0 right-0 p-6 border-t border-slate-600 bg-slate-800 space-y-3">
          <button
            onClick={handleApplyFilters}
            className="w-full bg-slate-700 border border-slate-500 text-white py-3 rounded-lg font-medium hover:bg-slate-600 transition-colors"
          >
            Apply Filters
          </button>
          <button
            onClick={handleClearAll}
            className="w-full bg-slate-700 border border-slate-500 text-white py-3 rounded-lg font-medium hover:bg-slate-600 transition-colors flex items-center justify-center space-x-2"
          >
            <div className="w-6 h-6 bg-slate-600 border border-slate-400 rounded-full flex items-center justify-center">
              <span className="text-xs font-bold text-white">N</span>
            </div>
            <span>Clear All</span>
          </button>
        </div>
      </div>
    </div>
  );
}
