'use client';

import { ComparisonTable as ComparisonTableType } from '@/types/chat';

interface ComparisonTableProps {
  comparison: ComparisonTableType;
}

export default function ComparisonTable({ comparison }: ComparisonTableProps) {
  const { headers, rows } = comparison;
  
  // First header is "Attribute", rest are vehicle names
  const vehicleNames = headers.slice(1);

  return (
    <div className="mt-4">
      <div className="flex gap-4 overflow-x-auto pb-2">
        {vehicleNames.map((vehicleName, vehicleIdx) => (
          <div 
            key={vehicleIdx} 
            className="flex-shrink-0 w-80 glass-dark rounded-xl p-4 border border-slate-600/30 hover:border-purple-500/50 transition-all"
          >
            {/* Vehicle Name Header */}
            <h3 className="text-lg font-bold text-slate-100 mb-4 text-center pb-3 border-b border-slate-600/30">
              {vehicleName}
            </h3>
            
            {/* Attributes */}
            <div className="space-y-3">
              {rows.map((row, rowIdx) => (
                <div key={rowIdx} className="space-y-1">
                  <div className="text-xs text-slate-400 font-medium">
                    {row[0]}
                  </div>
                  <div className="text-sm text-slate-200 font-semibold">
                    {row[vehicleIdx + 1]}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
