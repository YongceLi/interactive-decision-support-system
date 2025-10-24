'use client';

import { useMemo, useState } from 'react';
import { SimulationTurnCard, type SimulationTurn } from '../components/SimulationTurn';

interface JudgePayload {
  score?: number;
  passes?: boolean;
  feedback?: string;
  reminder?: string;
}

interface PersonaFacets {
  family?: string;
  writing?: string;
  interaction?: string;
  intent?: string;
}

interface Thresholds {
  positive?: number;
  negative?: number;
}

interface SimulationResponse {
  seed_persona: string;
  max_steps: number;
  temperature?: number;
  model?: string;
  step?: number;
  stop_reason?: string;
  conversation_summary?: string;
  summary_version?: number;
  summary_notes?: string;
  rl_scores?: Thresholds;
  rl_thresholds?: Thresholds;
  rl_rationale?: string;
  last_judge?: JudgePayload | null;
  persona?: PersonaFacets;
  goal?: Record<string, unknown>;
  demo_snapshots?: SimulationTurn[];
}

const DEFAULT_PERSONA = `Married couple in Colorado with a toddler and a medium-sized dog. Mixed city/highway commute;
budget-conscious but safety-focused. Considering SUVs and hybrids; casually written messages with occasional typos;
asks clarifying questions and compares trims; intent: actively shopping.`;

export default function Page() {
  const [persona, setPersona] = useState<string>(DEFAULT_PERSONA);
  const [maxSteps, setMaxSteps] = useState<number>(8);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulationResponse | null>(null);

  const handleRun = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const response = await fetch('/api/simulate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ persona, maxSteps }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || 'Failed to run simulation');
      }

      const data = (await response.json()) as SimulationResponse;
      setResult(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
    } finally {
      setIsRunning(false);
    }
  };

  const judgeSummary = useMemo(() => {
    if (!result?.last_judge) {
      return null;
    }
    const { score, feedback } = result.last_judge;
    if (typeof score !== 'number' && !feedback) {
      return null;
    }
    return {
      score: typeof score === 'number' ? `${(score * 100).toFixed(0)}% alignment` : undefined,
      feedback: feedback || '',
    };
  }, [result?.last_judge]);

  const personaFacets = useMemo(() => {
    const facets = result?.persona;
    if (!facets) {
      return [];
    }
    return [
      { label: 'Family', value: facets.family },
      { label: 'Writing', value: facets.writing },
      { label: 'Interaction', value: facets.interaction },
      { label: 'Intent', value: facets.intent },
    ].filter(({ value }) => Boolean(value));
  }, [result?.persona]);

  const snapshots: SimulationTurn[] = useMemo(() => {
    return result?.demo_snapshots ?? [];
  }, [result?.demo_snapshots]);

  return (
    <main className="flex flex-col gap-10 px-6 py-10 lg:px-12">
      <header className="max-w-5xl space-y-4">
        <p className="text-sm uppercase tracking-[0.3em] text-slate-400">User Simulation Demo</p>
        <h1 className="text-4xl font-semibold tracking-tight text-slate-50 sm:text-5xl">
          Autonomous car-shopper persona in action
        </h1>
        <p className="text-lg text-slate-300">
          Configure the persona seed and maximum conversation length, then watch the user agent collaborate with the
          assistant, the summary keeper, and the alignment judge. The UI has no manual chat input—every turn is produced
          by the simulator.
        </p>
      </header>

      <section className="grid gap-8 lg:grid-cols-[minmax(320px,380px)_1fr] lg:items-start">
        <aside className="space-y-6 rounded-2xl border border-slate-700/60 bg-slate-900/60 p-6 shadow-xl">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Simulation controls</h2>
            <p className="mt-1 text-sm text-slate-400">
              Adjust the persona narrative or tweak the step budget. Conversations automatically stop when the RL scorer,
              judge, or UI criteria trigger an ending.
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-400" htmlFor="persona">
              Persona seed
            </label>
            <textarea
              id="persona"
              value={persona}
              onChange={(event) => setPersona(event.target.value)}
              className="h-40 w-full rounded-xl border border-slate-700 bg-slate-950/80 p-3 text-sm text-slate-100 shadow-inner focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
            />
          </div>

          <div className="space-y-2">
            <label className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-400" htmlFor="max-steps">
              <span>Max turns</span>
              <span className="text-slate-200">{maxSteps}</span>
            </label>
            <input
              id="max-steps"
              type="range"
              min={4}
              max={20}
              value={maxSteps}
              onChange={(event) => setMaxSteps(Number(event.target.value))}
              className="w-full"
            />
          </div>

          <button
            onClick={handleRun}
            disabled={isRunning}
            className="w-full rounded-xl bg-sky-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-600"
          >
            {isRunning ? 'Running simulation…' : 'Run simulation'}
          </button>

          {error ? (
            <p className="rounded-lg border border-rose-500/70 bg-rose-950/50 p-3 text-sm text-rose-100">
              {error}
            </p>
          ) : null}

          {result ? (
            <dl className="space-y-3 text-sm text-slate-300">
              <div>
                <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Stop reason</dt>
                <dd className="mt-1 text-slate-100">{result.stop_reason ?? 'Pending'}</dd>
              </div>
              <div>
                <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Steps used</dt>
                <dd className="mt-1 text-slate-100">{result.step ?? 0}</dd>
              </div>
              {judgeSummary ? (
                <div>
                  <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Judge feedback</dt>
                  <dd className="mt-1 text-slate-100">
                    {judgeSummary.score ? `${judgeSummary.score} · ` : ''}
                    {judgeSummary.feedback}
                  </dd>
                </div>
              ) : null}
              {personaFacets.length ? (
                <div>
                  <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Persona facets</dt>
                  <dd className="mt-1 space-y-1">
                    {personaFacets.map(({ label, value }) => (
                      <p key={label} className="text-slate-200">
                        <span className="font-semibold text-slate-100">{label}: </span>
                        {value}
                      </p>
                    ))}
                  </dd>
                </div>
              ) : null}
              {result.rl_scores ? (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Positive score</dt>
                    <dd className="mt-1 text-lg font-semibold text-emerald-300">
                      {typeof result.rl_scores.positive === 'number'
                        ? result.rl_scores.positive.toFixed(2)
                        : '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Negative score</dt>
                    <dd className="mt-1 text-lg font-semibold text-rose-300">
                      {typeof result.rl_scores.negative === 'number'
                        ? result.rl_scores.negative.toFixed(2)
                        : '—'}
                    </dd>
                  </div>
                </div>
              ) : null}
              {result.rl_rationale ? (
                <div>
                  <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">RL rationale</dt>
                  <dd className="mt-1 whitespace-pre-line text-slate-200/80">{result.rl_rationale}</dd>
                </div>
              ) : null}
            </dl>
          ) : null}
        </aside>

        <div className="space-y-8">
          {result ? (
            <section className="space-y-4">
              <div className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-6 shadow-xl">
                <h2 className="text-lg font-semibold text-slate-100">Conversation summary</h2>
                <p className="mt-2 text-sm text-slate-300/90">
                  {result.conversation_summary ?? 'Summary not available yet.'}
                </p>
                {result.summary_notes ? (
                  <p className="mt-3 text-xs text-slate-400">Latest delta: {result.summary_notes}</p>
                ) : null}
              </div>

              <div className="space-y-5">
                {snapshots.length ? (
                  snapshots.map((turn) => <SimulationTurnCard key={turn.step} turn={turn} />)
                ) : (
                  <p className="text-sm text-slate-400">Run the simulator to populate the timeline.</p>
                )}
              </div>
            </section>
          ) : (
            <section className="rounded-2xl border border-dashed border-slate-700/70 bg-slate-900/30 p-10 text-center text-sm text-slate-400">
              Launch a simulation to review the automatically generated conversation.
            </section>
          )}
        </div>
      </section>
    </main>
  );
}
