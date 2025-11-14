'use client';

import { CompatibilityResult as CompatibilityResultType } from '@/types/chat';

interface CompatibilityResultProps {
  result: CompatibilityResultType;
}

export default function CompatibilityResult({ result }: CompatibilityResultProps) {
  const { compatible, explanation, part1_name, part2_name, compatibility_types, error } = result;

  if (error) {
    return (
      <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
        <div className="flex items-start">
          <svg className="w-5 h-5 text-yellow-600 mt-0.5 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div className="flex-1">
            <h3 className="text-base font-semibold text-yellow-800 mb-1">Compatibility Check Unavailable</h3>
            <p className="text-sm text-yellow-700">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-4 p-4 bg-white border rounded-lg shadow-sm">
      {/* Header */}
      <div className="flex items-center mb-3 pb-3 border-b border-[#8b959e]/30">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center mr-3 ${
          compatible ? 'bg-green-100' : 'bg-red-100'
        }`}>
          {compatible ? (
            <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          )}
        </div>
        <div className="flex-1">
          <h3 className={`text-lg font-bold ${
            compatible ? 'text-green-700' : 'text-red-700'
          }`}>
            {compatible ? 'Compatible' : 'Not Compatible'}
          </h3>
          {(part1_name || part2_name) && (
            <p className="text-sm text-[#8b959e] mt-1">
              {part1_name && part2_name ? `${part1_name} ↔ ${part2_name}` : part1_name || part2_name}
            </p>
          )}
        </div>
      </div>

      {/* Explanation */}
      <div className="mb-3">
        <p className="text-base text-black">{explanation}</p>
      </div>

      {/* Compatibility Types */}
      {compatibility_types && compatibility_types.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[#8b959e]/30">
          <p className="text-sm text-[#8b959e] mb-2">Compatibility Types:</p>
          <div className="flex flex-wrap gap-2">
            {compatibility_types.map((type, idx) => (
              <span
                key={idx}
                className="px-3 py-1 bg-[#750013]/10 text-[#750013] text-xs font-medium rounded-full"
              >
                {type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

