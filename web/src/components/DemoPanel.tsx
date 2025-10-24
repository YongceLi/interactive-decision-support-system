"use client";

import { useMemo } from 'react';
import { Vehicle } from '@/types/vehicle';

interface DemoPanelProps {
  enabled: boolean;
  onToggle: () => void;
  summary: string;
  recentMessages: { role: string; content: string }[];
  filters: Record<string, unknown>;
  favoritesCount: number;
  vehicles: Vehicle[];
  selectedVehicle?: Vehicle | null;
  showDetails: boolean;
  showFavorites: boolean;
}

function formatFilters(filters: Record<string, unknown>): string {
  const entries = Object.entries(filters || {});
  if (!entries.length) {
    return 'None applied';
  }
  return entries
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
    .join(' • ');
}

function vehicleLabel(vehicle: Vehicle): string {
  const pieces = [vehicle.year?.toString(), vehicle.make, vehicle.model].filter(Boolean).join(' ');
  const extras: string[] = [];
  if (vehicle.price) {
    extras.push(`$${vehicle.price.toLocaleString()}`);
  }
  if (vehicle.mileage) {
    extras.push(`${typeof vehicle.mileage === 'number' ? vehicle.mileage.toLocaleString() : vehicle.mileage} mi`);
  }
  return extras.length ? `${pieces} — ${extras.join(' · ')}` : pieces;
}

export default function DemoPanel({
  enabled,
  onToggle,
  summary,
  recentMessages,
  filters,
  favoritesCount,
  vehicles,
  selectedVehicle,
  showDetails,
  showFavorites,
}: DemoPanelProps) {
  const uiStatus = useMemo(() => {
    const status: string[] = [];
    status.push(showDetails ? 'Detail modal open' : 'Detail modal closed');
    status.push(showFavorites ? 'Favorites gallery open' : 'Favorites gallery hidden');
    status.push(favoritesCount ? `${favoritesCount} saved` : 'No favorites yet');
    return status.join(' • ');
  }, [showDetails, showFavorites, favoritesCount]);

  const vehiclePreview = vehicles.slice(0, 3).map(vehicleLabel);

  const transcript = useMemo(() => {
    if (!recentMessages.length) {
      return 'No conversation yet';
    }
    return recentMessages
      .map(msg => `${msg.role === 'assistant' ? 'Assistant' : 'User'}: ${msg.content}`)
      .join('\n');
  }, [recentMessages]);

  return (
    <div className="fixed bottom-6 right-6 z-[60] flex flex-col items-end space-y-3">
      <button
        onClick={onToggle}
        className={`px-4 py-2 rounded-full text-sm font-semibold shadow-lg transition-all duration-200 border ${
          enabled
            ? 'bg-emerald-500/90 border-emerald-300 text-white hover:bg-emerald-500'
            : 'bg-slate-800/70 border-slate-600 text-slate-200 hover:bg-slate-700'
        }`}
      >
        {enabled ? 'Demo mode: ON' : 'Demo mode: OFF'}
      </button>

      {enabled && (
        <div className="w-[22rem] max-h-[26rem] glass-dark border border-slate-600/40 rounded-2xl p-4 shadow-2xl overflow-y-auto space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-100 tracking-wide uppercase">Conversation summary</h3>
            <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
              {summary || 'Summary agent has not produced output yet.'}
            </p>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-slate-100 tracking-wide uppercase">Recent transcript</h3>
            <pre className="text-[0.7rem] text-slate-300 leading-snug whitespace-pre-wrap bg-slate-800/60 rounded-lg p-2 border border-slate-700/60">
              {transcript}
            </pre>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-slate-100 tracking-wide uppercase">UI status</h3>
            <p className="text-xs text-slate-300 leading-relaxed">{uiStatus}</p>
            <p className="text-xs text-slate-400 mt-2">
              Active filters: {formatFilters(filters)}
            </p>
            <p className="text-xs text-slate-400 mt-1">
              Top carousel: {vehiclePreview.length ? vehiclePreview.join(' | ') : 'waiting for recommendations'}
            </p>
            {selectedVehicle && (
              <p className="text-xs text-emerald-300 mt-1">
                Viewing: {vehicleLabel(selectedVehicle)}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
