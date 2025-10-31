'use client';

import { useState, useEffect } from 'react';

interface FilterMenuProps {
  onFilterChange: (filters: Record<string, unknown>) => void;
  onOpenChange?: (isOpen: boolean) => void;
}

interface FilterState {
  brands: string[];
  mileage: number;
  priceRange: { min: number; max: number };
  condition: 'new' | 'used' | 'both';
  carTypes: string[];
  fuelTypes: string[];
}

const BRANDS = [
  'Toyota', 'Honda', 'Ford', 'Chevrolet', 'BMW', 'Mercedes-Benz', 
  'Audi', 'Tesla', 'Subaru', 'Nissan', 'Hyundai', 'Kia', 'Volkswagen', 'Mazda'
];

const CAR_TYPES = [
  'Sedan', 'SUV', 'Truck', 'Hatchback', 'Coupe', 'Convertible', 'Wagon', 'Van'
];

const FUEL_TYPES = [
  'Gasoline', 'Hybrid', 'Electric', 'Diesel', 'Plug-in Hybrid'
];

export default function FilterMenu({ onFilterChange, onOpenChange }: FilterMenuProps) {
  const [isOpen, setIsOpen] = useState(false);

  // Notify parent when filter state changes
  useEffect(() => {
    onOpenChange?.(isOpen);
  }, [isOpen, onOpenChange]);
  const [filters, setFilters] = useState<FilterState>({
    brands: [],
    mileage: 200000,
    priceRange: { min: 0, max: 200000 },
    condition: 'both',
    carTypes: [],
    fuelTypes: []
  });
  const [lastAppliedFilters, setLastAppliedFilters] = useState<FilterState>({
    brands: [],
    mileage: 200000,
    priceRange: { min: 0, max: 200000 },
    condition: 'both',
    carTypes: [],
    fuelTypes: []
  });

  const handleBrandToggle = (brand: string) => {
    setFilters(prev => ({
      ...prev,
      brands: prev.brands.includes(brand)
        ? prev.brands.filter(b => b !== brand)
        : [...prev.brands, brand]
    }));
  };

  const handleCarTypeToggle = (type: string) => {
    setFilters(prev => ({
      ...prev,
      carTypes: prev.carTypes.includes(type)
        ? prev.carTypes.filter(t => t !== type)
        : [...prev.carTypes, type]
    }));
  };

  const handleFuelTypeToggle = (type: string) => {
    setFilters(prev => ({
      ...prev,
      fuelTypes: prev.fuelTypes.includes(type)
        ? prev.fuelTypes.filter(t => t !== type)
        : [...prev.fuelTypes, type]
    }));
  };

  const handleMileageChange = (value: number) => {
    setFilters(prev => ({ ...prev, mileage: value }));
  };

  const handlePriceRangeChange = (field: 'min' | 'max', value: number) => {
    setFilters(prev => ({
      ...prev,
      priceRange: { ...prev.priceRange, [field]: value }
    }));
  };

  const handleConditionChange = (condition: 'new' | 'used' | 'both') => {
    setFilters(prev => ({ ...prev, condition }));
  };

  const buildFilterObject = (): Record<string, unknown> => {
    const filterObject: Record<string, unknown> = {};

    if (filters.brands.length > 0) {
      filterObject.make = filters.brands;
    }

    if (filters.mileage < 200000) {
      filterObject.mileage_max = filters.mileage;
    }

    if (filters.priceRange.min > 0) {
      filterObject.price_min = filters.priceRange.min;
    }

    if (filters.priceRange.max < 200000) {
      filterObject.price_max = filters.priceRange.max;
    }

    if (filters.condition !== 'both') {
      if (filters.condition === 'new') {
        filterObject.year = '2023-2024';
      } else {
        filterObject.year = '2015-2023';
      }
    }

    if (filters.carTypes.length > 0) {
      filterObject.body_style = filters.carTypes;
    }

    if (filters.fuelTypes.length > 0) {
      filterObject.fuel_type = filters.fuelTypes;
    }

    return filterObject;
  };

  const handleApplyFilters = () => {
    const filterObject = buildFilterObject();
    onFilterChange(filterObject);
    // Update the last applied filters to match current filters
    setLastAppliedFilters(filters);
  };

  const clearAllFilters = () => {
    setFilters({
      brands: [],
      mileage: 200000,
      priceRange: { min: 0, max: 200000 },
      condition: 'both',
      carTypes: [],
      fuelTypes: []
    });
    // Also clear the last applied filters
    setLastAppliedFilters({
      brands: [],
      mileage: 200000,
      priceRange: { min: 0, max: 200000 },
      condition: 'both',
      carTypes: [],
      fuelTypes: []
    });
  };

  const hasActiveFilters = () => {
    return filters.brands.length > 0 ||
           filters.mileage < 200000 ||
           filters.priceRange.min > 0 ||
           filters.priceRange.max < 200000 ||
           filters.condition !== 'both' ||
           filters.carTypes.length > 0 ||
           filters.fuelTypes.length > 0;
  };

  const hasChanges = () => {
    return JSON.stringify(filters) !== JSON.stringify(lastAppliedFilters);
  };

  return (
    <>
      {/* Hamburger Menu Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed top-6 left-6 z-50 w-14 h-14 bg-white rounded-xl border border-[#8b959e]/40 flex items-center justify-center hover:border-[#8b959e] hover:shadow-md transition-all duration-200 shadow-sm"
      >
        <div className="flex flex-col space-y-1.5">
          <div className="w-6 h-0.5 bg-[#8b959e] rounded"></div>
          <div className="w-6 h-0.5 bg-[#8b959e] rounded"></div>
          <div className="w-6 h-0.5 bg-[#8b959e] rounded"></div>
        </div>
      </button>

      {/* Overlay - only covers the area not occupied by the menu */}
      {isOpen && (
        <div
          className="fixed top-0 left-80 right-0 bottom-0 bg-black/20 z-40"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Filter Menu */}
      <div
        className={`fixed top-0 left-0 h-full w-80 bg-white border-r border-[#8b959e]/30 z-50 transform transition-transform duration-300 ease-in-out shadow-lg ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="p-6 h-full flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-black">Filters</h2>
            <button
              onClick={() => setIsOpen(false)}
              className="w-10 h-10 bg-white rounded-lg flex items-center justify-center hover:bg-[#8b959e]/10 transition-all duration-200 border border-[#8b959e]/40"
            >
              <svg className="w-5 h-5 text-[#8b959e]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Filter Content */}
          <div className="flex-1 overflow-y-auto space-y-6">
            {/* Car Brands */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Brand</h3>
              <div className="grid grid-cols-2 gap-2">
                {BRANDS.map(brand => (
                  <button
                    key={brand}
                    onClick={() => handleBrandToggle(brand)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      filters.brands.includes(brand)
                        ? 'bg-[#ff1323] text-white shadow-sm'
                        : 'bg-white border border-[#8b959e]/40 text-black hover:border-[#8b959e] hover:bg-[#8b959e]/5'
                    }`}
                  >
                    {brand}
                  </button>
                ))}
              </div>
            </div>

            {/* Condition */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Condition</h3>
              <div className="grid grid-cols-3 gap-2">
                {(['new', 'used', 'both'] as const).map(condition => (
                  <button
                    key={condition}
                    onClick={() => handleConditionChange(condition)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      filters.condition === condition
                        ? 'bg-[#ff1323] text-white shadow-sm'
                        : 'bg-white border border-[#8b959e]/40 text-black hover:border-[#8b959e] hover:bg-[#8b959e]/5'
                    }`}
                  >
                    {condition.charAt(0).toUpperCase() + condition.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Car Types */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Car Type</h3>
              <div className="grid grid-cols-2 gap-2">
                {CAR_TYPES.map(type => (
                  <button
                    key={type}
                    onClick={() => handleCarTypeToggle(type)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      filters.carTypes.includes(type)
                        ? 'bg-[#ff1323] text-white shadow-sm'
                        : 'bg-white border border-[#8b959e]/40 text-black hover:border-[#8b959e] hover:bg-[#8b959e]/5'
                    }`}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>

            {/* Fuel Types */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Fuel Type</h3>
              <div className="grid grid-cols-2 gap-2">
                {FUEL_TYPES.map(type => (
                  <button
                    key={type}
                    onClick={() => handleFuelTypeToggle(type)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      filters.fuelTypes.includes(type)
                        ? 'bg-[#ff1323] text-white shadow-sm'
                        : 'bg-white border border-[#8b959e]/40 text-black hover:border-[#8b959e] hover:bg-[#8b959e]/5'
                    }`}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>

            {/* Mileage */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">
                Max Mileage: {filters.mileage.toLocaleString()} miles
              </h3>
              <input
                type="range"
                min="0"
                max="200000"
                step="5000"
                value={filters.mileage}
                onChange={(e) => handleMileageChange(Number(e.target.value))}
                className="w-full h-2 bg-[#8b959e]/30 rounded-lg appearance-none cursor-pointer slider"
              />
              <div className="flex justify-between text-sm text-[#8b959e] mt-2">
                <span>0</span>
                <span>100K</span>
                <span>200K+</span>
              </div>
            </div>

            {/* Price Range */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Price Range</h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm text-[#8b959e] mb-1">Min Price</label>
                  <input
                    type="number"
                    min="0"
                    max="200000"
                    step="1000"
                    value={filters.priceRange.min}
                    onChange={(e) => handlePriceRangeChange('min', Number(e.target.value))}
                    className="w-full px-3 py-2 bg-white border border-[#8b959e]/40 rounded-lg text-black text-base focus:outline-none focus:ring-2 focus:ring-[#ff1323]/20 focus:border-[#ff1323]"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="block text-sm text-[#8b959e] mb-1">Max Price</label>
                  <input
                    type="number"
                    min="0"
                    max="200000"
                    step="1000"
                    value={filters.priceRange.max}
                    onChange={(e) => handlePriceRangeChange('max', Number(e.target.value))}
                    className="w-full px-3 py-2 bg-white border border-[#8b959e]/40 rounded-lg text-black text-base focus:outline-none focus:ring-2 focus:ring-[#ff1323]/20 focus:border-[#ff1323]"
                    placeholder="200000"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Footer Actions */}
          <div className="pt-6 border-t border-[#8b959e]/30 space-y-3">
            <button
              onClick={handleApplyFilters}
              disabled={!hasChanges()}
              className={`w-full py-3 px-4 rounded-xl font-semibold text-base transition-all duration-200 ${
                hasChanges()
                  ? 'bg-gradient-to-r from-[#ff1323] to-[#ff1323]/70 text-white hover:from-[#ff1323]/70 hover:to-[#ff1323] shadow-sm hover:shadow-md'
                  : 'bg-white border border-[#8b959e]/40 text-[#8b959e] cursor-not-allowed'
              }`}
            >
              Apply Filters
            </button>
            <button
              onClick={clearAllFilters}
              className="w-full py-2 px-4 bg-white border border-[#8b959e]/40 rounded-xl text-black hover:border-[#8b959e] hover:bg-[#8b959e]/5 transition-all duration-200 text-base font-medium"
            >
              Clear All
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
