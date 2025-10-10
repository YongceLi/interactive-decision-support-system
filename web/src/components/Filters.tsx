'use client';

import { useState } from 'react';

interface FiltersProps {
  filters: Record<string, unknown>;
  onFilterChange: (filters: Record<string, unknown>) => void;
}

export default function Filters({ onFilterChange }: FiltersProps) {
  const [selectedFilters, setSelectedFilters] = useState<string[]>([]);
  const [mileageRange, setMileageRange] = useState<number>(100000);

  const predefinedFilters = [
    { id: 'new', label: 'New', color: 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300', selectedColor: 'bg-red-800 border-red-800 text-white shadow-md' },
    { id: 'used', label: 'Used', color: 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300', selectedColor: 'bg-stone-600 border-stone-600 text-white shadow-md' },
    { id: 'suv', label: 'SUV', color: 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300', selectedColor: 'bg-stone-600 border-stone-600 text-white shadow-md' },
    { id: 'sedan', label: 'Sedan', color: 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300', selectedColor: 'bg-stone-600 border-stone-600 text-white shadow-md' },
    { id: 'truck', label: 'Truck', color: 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300', selectedColor: 'bg-stone-600 border-stone-600 text-white shadow-md' },
    { id: 'electric', label: 'Electric', color: 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300', selectedColor: 'bg-green-700 border-green-700 text-white shadow-md' },
    { id: 'luxury', label: 'Luxury', color: 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300', selectedColor: 'bg-red-800 border-red-800 text-white shadow-md' },
    { id: 'family', label: 'Family', color: 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300', selectedColor: 'bg-green-700 border-green-700 text-white shadow-md' },
  ];

  const handleFilterToggle = (filterId: string) => {
    const newSelected = selectedFilters.includes(filterId)
      ? selectedFilters.filter(id => id !== filterId)
      : [...selectedFilters, filterId];
    
    setSelectedFilters(newSelected);
    
    // Convert to filter object for the agent
    const filterObject = newSelected.reduce((acc, id) => {
      switch (id) {
        case 'new':
          acc.year = '2023-2024';
          break;
        case 'used':
          acc.year = '2015-2023';
          break;
        case 'suv':
          acc.body_style = 'suv';
          break;
        case 'sedan':
          acc.body_style = 'sedan';
          break;
        case 'truck':
          acc.body_style = 'truck';
          break;
        case 'electric':
          acc.make = 'Tesla';
          break;
        case 'luxury':
          acc.price_min = 40000;
          break;
        case 'family':
          acc.seating_capacity = 5;
          break;
        // Make filters
        case 'toyota':
          acc.make = 'Toyota';
          break;
        case 'honda':
          acc.make = 'Honda';
          break;
        case 'ford':
          acc.make = 'Ford';
          break;
        case 'bmw':
          acc.make = 'BMW';
          break;
        case 'tesla':
          acc.make = 'Tesla';
          break;
        case 'subaru':
          acc.make = 'Subaru';
          break;
        // Model filters
        case 'camry':
          acc.model = 'Camry';
          break;
        case 'cr-v':
          acc.model = 'CR-V';
          break;
        case 'f-150':
          acc.model = 'F-150';
          break;
        case 'model-3':
          acc.model = 'Model 3';
          break;
        case 'x3':
          acc.model = 'X3';
          break;
        case 'outback':
          acc.model = 'Outback';
          break;
        // Price range filters
        case 'under30k':
          acc.price_max = 30000;
          break;
        case '30k-50k':
          acc.price_min = 30000;
          acc.price_max = 50000;
          break;
        case '50k-80k':
          acc.price_min = 50000;
          acc.price_max = 80000;
          break;
        case 'over80k':
          acc.price_min = 80000;
          break;
      }
      return acc;
    }, {} as Record<string, unknown>);

    // Add mileage filter
    if (mileageRange < 100000) {
      filterObject.mileage_max = mileageRange;
    }

    onFilterChange(filterObject);
  };

  const handleMileageChange = (value: number) => {
    setMileageRange(value);
    // Trigger filter update with current selections plus mileage
    const filterObject = selectedFilters.reduce((acc, id) => {
      switch (id) {
        case 'new':
          acc.year = '2023-2024';
          break;
        case 'used':
          acc.year = '2015-2023';
          break;
        case 'suv':
          acc.body_style = 'suv';
          break;
        case 'sedan':
          acc.body_style = 'sedan';
          break;
        case 'truck':
          acc.body_style = 'truck';
          break;
        case 'electric':
          acc.make = 'Tesla';
          break;
        case 'luxury':
          acc.price_min = 40000;
          break;
        case 'family':
          acc.seating_capacity = 5;
          break;
        case 'toyota':
          acc.make = 'Toyota';
          break;
        case 'honda':
          acc.make = 'Honda';
          break;
        case 'ford':
          acc.make = 'Ford';
          break;
        case 'bmw':
          acc.make = 'BMW';
          break;
        case 'tesla':
          acc.make = 'Tesla';
          break;
        case 'subaru':
          acc.make = 'Subaru';
          break;
        case 'camry':
          acc.model = 'Camry';
          break;
        case 'cr-v':
          acc.model = 'CR-V';
          break;
        case 'f-150':
          acc.model = 'F-150';
          break;
        case 'model-3':
          acc.model = 'Model 3';
          break;
        case 'x3':
          acc.model = 'X3';
          break;
        case 'outback':
          acc.model = 'Outback';
          break;
        case 'under30k':
          acc.price_max = 30000;
          break;
        case '30k-50k':
          acc.price_min = 30000;
          acc.price_max = 50000;
          break;
        case '50k-80k':
          acc.price_min = 50000;
          acc.price_max = 80000;
          break;
        case 'over80k':
          acc.price_min = 80000;
          break;
      }
      return acc;
    }, {} as Record<string, unknown>);

    if (value < 100000) {
      filterObject.mileage_max = value;
    }
    
    onFilterChange(filterObject);
  };

  return (
    <div className="p-6 h-full flex flex-col bg-stone-50">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-stone-900 mb-3">
          Smart Filters
        </h2>
        <p className="text-sm text-stone-600 leading-relaxed">
          Choose your preferences to find the perfect vehicle
        </p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto">
        <div className="grid grid-cols-2 gap-3">
          {predefinedFilters.map((filter) => (
            <button
              key={filter.id}
              onClick={() => handleFilterToggle(filter.id)}
              className={`
                px-4 py-3 rounded-lg border transition-all duration-200 font-medium text-sm hover:scale-105 transform
                ${selectedFilters.includes(filter.id)
                  ? filter.selectedColor
                  : filter.color
                }
              `}
            >
              {filter.label}
            </button>
          ))}
        </div>

        {/* Additional filters */}
        <div className="mt-6 space-y-4">
          {/* Mileage Slider */}
          <div className="bg-white p-5 rounded-lg border border-stone-200 shadow-sm hover:shadow-md transition-shadow duration-200">
            <label className="block text-sm font-semibold text-stone-900 mb-4">
              Max Mileage: {mileageRange.toLocaleString()} miles
            </label>
            <input
              type="range"
              min="0"
              max="200000"
              step="5000"
              value={mileageRange}
              onChange={(e) => handleMileageChange(Number(e.target.value))}
              className="w-full h-2 bg-stone-200 rounded-lg appearance-none cursor-pointer slider"
            />
            <div className="flex justify-between text-xs text-stone-500 mt-3">
              <span>0</span>
              <span>100K</span>
              <span>200K+</span>
            </div>
          </div>

          <div className="bg-white p-5 rounded-lg border border-stone-200 shadow-sm hover:shadow-md transition-shadow duration-200">
            <label className="block text-sm font-semibold text-stone-900 mb-4">Price Range</label>
            <div className="grid grid-cols-2 gap-3">
              <button 
                onClick={() => handleFilterToggle('under30k')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('under30k') 
                    ? 'bg-green-700 border-green-700 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Under $30K
              </button>
              <button 
                onClick={() => handleFilterToggle('30k-50k')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('30k-50k') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                $30K-$50K
              </button>
              <button 
                onClick={() => handleFilterToggle('50k-80k')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('50k-80k') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                $50K-$80K
              </button>
              <button 
                onClick={() => handleFilterToggle('over80k')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('over80k') 
                    ? 'bg-red-800 border-red-800 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Over $80K
              </button>
            </div>
          </div>

          <div className="bg-white p-5 rounded-lg border border-stone-200 shadow-sm hover:shadow-md transition-shadow duration-200">
            <label className="block text-sm font-semibold text-stone-900 mb-4">Make</label>
            <div className="grid grid-cols-2 gap-3">
              <button 
                onClick={() => handleFilterToggle('toyota')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('toyota') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Toyota
              </button>
              <button 
                onClick={() => handleFilterToggle('honda')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('honda') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Honda
              </button>
              <button 
                onClick={() => handleFilterToggle('ford')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('ford') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Ford
              </button>
              <button 
                onClick={() => handleFilterToggle('bmw')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('bmw') 
                    ? 'bg-red-800 border-red-800 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                BMW
              </button>
              <button 
                onClick={() => handleFilterToggle('tesla')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('tesla') 
                    ? 'bg-green-700 border-green-700 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Tesla
              </button>
              <button 
                onClick={() => handleFilterToggle('subaru')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('subaru') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Subaru
              </button>
            </div>
          </div>

          <div className="bg-white p-5 rounded-lg border border-stone-200 shadow-sm hover:shadow-md transition-shadow duration-200">
            <label className="block text-sm font-semibold text-stone-900 mb-4">Model</label>
            <div className="grid grid-cols-2 gap-3">
              <button 
                onClick={() => handleFilterToggle('camry')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('camry') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Camry
              </button>
              <button 
                onClick={() => handleFilterToggle('cr-v')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('cr-v') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                CR-V
              </button>
              <button 
                onClick={() => handleFilterToggle('f-150')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('f-150') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                F-150
              </button>
              <button 
                onClick={() => handleFilterToggle('model-3')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('model-3') 
                    ? 'bg-green-700 border-green-700 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Model 3
              </button>
              <button 
                onClick={() => handleFilterToggle('x3')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('x3') 
                    ? 'bg-red-800 border-red-800 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                X3
              </button>
              <button 
                onClick={() => handleFilterToggle('outback')}
                className={`px-3 py-2 text-sm rounded-lg border transition-all duration-200 font-medium ${
                  selectedFilters.includes('outback') 
                    ? 'bg-stone-600 border-stone-600 text-white shadow-sm' 
                    : 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100 hover:border-stone-300'
                }`}
              >
                Outback
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Active filters display */}
      {(selectedFilters.length > 0 || mileageRange < 100000) && (
        <div className="mt-8 pt-6 border-t border-stone-200">
          <h3 className="text-sm font-semibold text-stone-900 mb-4">
            Active Filters
          </h3>
          <div className="space-y-2">
            {selectedFilters.map((filterId) => {
              const filter = predefinedFilters.find(f => f.id === filterId);
              const makeFilters = ['toyota', 'honda', 'ford', 'bmw', 'tesla', 'subaru'];
              const modelFilters = ['camry', 'cr-v', 'f-150', 'model-3', 'x3', 'outback'];
              const priceFilters = ['under30k', '30k-50k', '50k-80k', 'over80k'];
              
              let displayLabel = filter?.label;
              if (makeFilters.includes(filterId)) {
                displayLabel = filterId.charAt(0).toUpperCase() + filterId.slice(1);
              } else if (modelFilters.includes(filterId)) {
                displayLabel = filterId === 'cr-v' ? 'CR-V' : 
                              filterId === 'f-150' ? 'F-150' : 
                              filterId === 'model-3' ? 'Model 3' :
                              filterId.charAt(0).toUpperCase() + filterId.slice(1);
              } else if (priceFilters.includes(filterId)) {
                displayLabel = filterId === 'under30k' ? 'Under $30K' :
                              filterId === '30k-50k' ? '$30K-$50K' :
                              filterId === '50k-80k' ? '$50K-$80K' :
                              filterId === 'over80k' ? 'Over $80K' : filterId;
              }
              
              return (
                <div key={filterId} className="flex items-center justify-between bg-stone-100 px-3 py-2 rounded-md border border-stone-200 hover:bg-stone-200 transition-colors duration-200">
                  <span className="text-sm text-stone-800 font-medium">
                    {displayLabel}
                  </span>
                  <button
                    onClick={() => handleFilterToggle(filterId)}
                    className="text-stone-500 hover:text-stone-700 text-lg font-bold ml-2"
                  >
                    ×
                  </button>
                </div>
              );
            })}
            {mileageRange < 100000 && (
              <div className="flex items-center justify-between bg-stone-100 px-3 py-2 rounded-md border border-stone-200 hover:bg-stone-200 transition-colors duration-200">
                <span className="text-sm text-stone-800 font-medium">
                  Max Mileage: {mileageRange.toLocaleString()} miles
                </span>
                <button
                  onClick={() => handleMileageChange(100000)}
                  className="text-stone-500 hover:text-stone-700 text-lg font-bold ml-2"
                >
                  ×
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
