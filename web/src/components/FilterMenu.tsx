'use client';

import { useState, useEffect } from 'react';

interface FilterMenuProps {
  onFilterChange: (filters: Record<string, unknown>) => void;
  onOpenChange?: (isOpen: boolean) => void;
}

interface FilterState {
  brands: string[];
  retailers: string[];
  categories: string[];
  condition: 'new' | 'refurbished' | 'used' | 'any';
  priceRange: { min: number; max: number };
}

const BRANDS = [
  'Apple',
  'Samsung',
  'Google',
  'Microsoft',
  'Sony',
  'LG',
  'Dell',
  'HP',
  'Lenovo',
  'ASUS',
  'Acer',
  'Razer'
];

const RETAILERS = [
  'Amazon',
  'Best Buy',
  'Walmart',
  'Target',
  'Newegg',
  'eBay'
];

const CATEGORIES = [
  'Smartphone',
  'Laptop',
  'Tablet',
  'Smartwatch',
  'Headphones',
  'Console',
  'Monitor',
  'Accessory'
];

export default function FilterMenu({ onFilterChange, onOpenChange }: FilterMenuProps) {
  const [isOpen, setIsOpen] = useState(false);

  // Notify parent when filter state changes
  useEffect(() => {
    onOpenChange?.(isOpen);
  }, [isOpen, onOpenChange]);
  const [filters, setFilters] = useState<FilterState>({
    brands: [],
    retailers: [],
    categories: [],
    condition: 'any',
    priceRange: { min: 0, max: 4000 }
  });
  const [lastAppliedFilters, setLastAppliedFilters] = useState<FilterState>({
    brands: [],
    retailers: [],
    categories: [],
    condition: 'any',
    priceRange: { min: 0, max: 4000 }
  });

  const toggleSelection = (list: 'brands' | 'retailers' | 'categories', value: string) => {
    setFilters(prev => ({
      ...prev,
      [list]: prev[list].includes(value)
        ? prev[list].filter((item: string) => item !== value)
        : [...prev[list], value]
    }));
  };

  const handlePriceRangeChange = (field: 'min' | 'max', value: number) => {
    const normalized = Math.max(0, Math.min(10000, value));
    setFilters(prev => ({
      ...prev,
      priceRange: { ...prev.priceRange, [field]: normalized }
    }));
  };

  const handleConditionChange = (condition: FilterState['condition']) => {
    setFilters(prev => ({ ...prev, condition }));
  };

  const buildFilterObject = (): Record<string, unknown> => {
    const filterObject: Record<string, unknown> = {};

    if (filters.brands.length > 0) {
      filterObject.make = filters.brands.join(', ');
    }

    if (filters.categories.length > 0) {
      filterObject.category = filters.categories.join(', ');
    }

    if (filters.retailers.length > 0) {
      filterObject.seller = filters.retailers.join(', ');
    }

    if (filters.priceRange.min > 0) {
      filterObject.price_min = filters.priceRange.min;
    }

    if (filters.priceRange.max < 4000) {
      filterObject.price_max = filters.priceRange.max;
    }

    if (filters.condition !== 'any') {
      filterObject.condition = filters.condition;
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
    const reset: FilterState = {
      brands: [],
      retailers: [],
      categories: [],
      condition: 'any',
      priceRange: { min: 0, max: 4000 }
    };
    setFilters(reset);
    setLastAppliedFilters(reset);
  };

  const hasActiveFilters = () => {
    return (
      filters.brands.length > 0 ||
      filters.retailers.length > 0 ||
      filters.categories.length > 0 ||
      filters.condition !== 'any' ||
      filters.priceRange.min > 0 ||
      filters.priceRange.max < 4000
    );
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
          <div className="w-6 h-0.5 bg-[#750013] rounded"></div>
          <div className="w-6 h-0.5 bg-[#750013] rounded"></div>
          <div className="w-6 h-0.5 bg-[#750013] rounded"></div>
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
        <div className="p-4 h-full flex flex-col">
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
            {/* Brands */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Brand</h3>
              <div className="grid grid-cols-2 gap-2">
                {BRANDS.map(brand => (
                  <button
                    key={brand}
                    onClick={() => toggleSelection('brands', brand)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      filters.brands.includes(brand)
                        ? 'bg-[#750013] text-white shadow-sm'
                        : 'bg-white border border-[#8b959e]/40 text-black hover:border-[#8b959e] hover:bg-[#8b959e]/5'
                    }`}
                  >
                    {brand}
                  </button>
                ))}
              </div>
            </div>

            {/* Category */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Category</h3>
              <div className="grid grid-cols-2 gap-2">
                {CATEGORIES.map(category => (
                  <button
                    key={category}
                    onClick={() => toggleSelection('categories', category)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      filters.categories.includes(category)
                        ? 'bg-[#750013] text-white shadow-sm'
                        : 'bg-white border border-[#8b959e]/40 text-black hover:border-[#8b959e] hover:bg-[#8b959e]/5'
                    }`}
                  >
                    {category}
                  </button>
                ))}
              </div>
            </div>

            {/* Retailer */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Retailer</h3>
              <div className="grid grid-cols-2 gap-2">
                {RETAILERS.map(retailer => (
                  <button
                    key={retailer}
                    onClick={() => toggleSelection('retailers', retailer)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      filters.retailers.includes(retailer)
                        ? 'bg-[#750013] text-white shadow-sm'
                        : 'bg-white border border-[#8b959e]/40 text-black hover:border-[#8b959e] hover:bg-[#8b959e]/5'
                    }`}
                  >
                    {retailer}
                  </button>
                ))}
              </div>
            </div>

            {/* Condition */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Condition</h3>
              <div className="grid grid-cols-2 gap-2">
                {(['new', 'refurbished', 'used', 'any'] as const).map(condition => (
                  <button
                    key={condition}
                    onClick={() => handleConditionChange(condition)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      filters.condition === condition
                        ? 'bg-[#750013] text-white shadow-sm'
                        : 'bg-white border border-[#8b959e]/40 text-black hover:border-[#8b959e] hover:bg-[#8b959e]/5'
                    }`}
                  >
                    {condition === 'any'
                      ? 'Any'
                      : condition.charAt(0).toUpperCase() + condition.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Price Range */}
            <div>
              <h3 className="text-base font-semibold text-black mb-3">Price Range (USD)</h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm text-[#8b959e] mb-1">Min Price</label>
                  <input
                    type="number"
                    min="0"
                    max="10000"
                    step="10"
                    value={filters.priceRange.min}
                    onChange={(e) => handlePriceRangeChange('min', Number(e.target.value))}
                    className="w-full px-3 py-2 bg-white border border-[#8b959e]/40 rounded-lg text-black text-base focus:outline-none focus:ring-2 focus:ring-[#750013]/20 focus:border-[#750013]"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="block text-sm text-[#8b959e] mb-1">Max Price</label>
                  <input
                    type="number"
                    min="0"
                    max="10000"
                    step="10"
                    value={filters.priceRange.max}
                    onChange={(e) => handlePriceRangeChange('max', Number(e.target.value))}
                    className="w-full px-3 py-2 bg-white border border-[#8b959e]/40 rounded-lg text-black text-base focus:outline-none focus:ring-2 focus:ring-[#750013]/20 focus:border-[#750013]"
                    placeholder="4000"
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
                  ? 'bg-gradient-to-r from-[#750013] to-[#750013]/70 text-white hover:from-[#750013]/70 hover:to-[#750013] shadow-sm hover:shadow-md'
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
