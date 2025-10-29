'use client';

import { useMemo, useState } from 'react';
import {
  SimulationTurnCard,
  type SimulationTurn,
  type VehicleSummary,
  type CompletionReview,
} from '../components/SimulationTurn';

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
  discount_factor?: number;
  last_judge?: JudgePayload | null;
  persona?: PersonaFacets;
  goal?: Record<string, unknown>;
  history?: Array<Record<string, unknown>> | null;
  quick_replies?: string[] | null;
  completion_review?: CompletionReview | null;
  demo_snapshots?: SimulationTurn[];
}

type StreamTurnEvent = {
  step?: number;
  user_text: string;
  assistant_text: string;
  actions?: Array<Record<string, unknown>>;
  summary?: string;
  scores?: Thresholds;
  judge?: JudgePayload | null;
  rationale?: string | null;
  quick_replies?: string[] | null;
  completion_review?: CompletionReview | null;
  vehicles?: VehicleSummary[] | null;
};

type StreamEvent =
  | { type: 'turn'; data: StreamTurnEvent }
  | {
      type: 'rl_init';
      data: {
        thresholds?: Thresholds;
        scores?: Thresholds;
        discount?: number;
        notes?: string;
      };
    }
  | { type: 'complete'; data: SimulationResponse }
  | { type: 'error'; data?: { message?: string } };

const DEFAULT_PERSONA = `Married couple in Colorado with a toddler and a medium-sized dog. Mixed city/highway commute;
budget-conscious but safety-focused. Considering SUVs and hybrids; casually written messages with occasional typos;
asks clarifying questions and compares trims; intent: actively shopping.`;

export default function Page() {
  const [persona, setPersona] = useState<string>(DEFAULT_PERSONA);
  const [maxSteps, setMaxSteps] = useState<number>(8);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulationResponse | null>(null);
  const [turns, setTurns] = useState<SimulationTurn[]>([]);
  const [rlInfo, setRlInfo] = useState<{
    thresholds?: Thresholds;
    scores?: Thresholds;
    discount?: number;
    notes?: string;
  } | null>(null);

  const handleRun = async () => {
    setIsRunning(true);
    setError(null);
    setResult(null);
    setTurns([]);
    setRlInfo(null);

    try {
      const response = await fetch('/api/simulate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ persona, maxSteps }),
      });

      if (!response.ok || !response.body) {
        let message = 'Failed to run simulation';
        try {
          const payload = await response.json();
          message = payload?.error || message;
        } catch (parseError) {
          // Ignore JSON parsing failures and use fallback message
        }
        throw new Error(message);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const processLine = (line: string) => {
        if (!line) {
          return;
        }
        try {
          const event = JSON.parse(line) as StreamEvent;
          switch (event.type) {
            case 'turn':
              setTurns((prev) => {
                const nextTurn: SimulationTurn = {
                  step: event.data.step ?? prev.length + 1,
                  user_text: event.data.user_text,
                  assistant_text: event.data.assistant_text,
                  actions: event.data.actions ?? [],
                  summary: event.data.summary ?? '',
                  scores: event.data.scores,
                  judge: event.data.judge ?? null,
                  rationale: event.data.rationale ?? null,
                  quick_replies: event.data.quick_replies ?? null,
                  completion_review: event.data.completion_review ?? null,
                  vehicles: event.data.vehicles ?? null,
                };
                return [...prev, nextTurn];
              });
              if (event.data.scores) {
                setRlInfo((prev) => ({
                  ...(prev ?? {}),
                  scores: event.data.scores,
                }));
              }
              break;
            case 'rl_init':
              setRlInfo({
                thresholds: event.data.thresholds,
                scores: event.data.scores,
                discount: event.data.discount,
                notes: event.data.notes,
              });
              break;
            case 'complete':
              setResult(event.data);
              if (event.data.demo_snapshots?.length) {
                setTurns(event.data.demo_snapshots);
              }
              setRlInfo((prev) => ({
                ...(prev ?? {}),
                thresholds: event.data.rl_thresholds ?? prev?.thresholds,
                scores: event.data.rl_scores ?? prev?.scores,
                discount: event.data.discount_factor ?? prev?.discount,
                notes: event.data.rl_rationale ?? prev?.notes,
              }));
              break;
            case 'error':
              setError(event.data?.message ?? 'Simulation error');
              break;
            default:
              break;
          }
        } catch (parseError) {
          console.warn('Failed to parse simulation event', parseError, line);
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n');
        buffer = parts.pop() ?? '';
        for (const part of parts) {
          processLine(part.trim());
        }
      }

      const trailing = buffer.trim();
      if (trailing) {
        processLine(trailing);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
    } finally {
      setIsRunning(false);
    }
  };

  const latestJudge = useMemo(() => {
    if (result?.last_judge) {
      return result.last_judge;
    }
    for (let index = turns.length - 1; index >= 0; index -= 1) {
      const judge = turns[index]?.judge;
      if (judge) {
        return judge;
      }
    }
    return null;
  }, [result?.last_judge, turns]);

  const judgeSummary = useMemo(() => {
    if (!latestJudge) {
      return null;
    }
    const { score, feedback } = latestJudge;
    if (typeof score !== 'number' && !feedback) {
      return null;
    }
    return {
      score: typeof score === 'number' ? `${(score * 100).toFixed(0)}% alignment` : undefined,
      feedback: feedback || '',
    };
  }, [latestJudge]);

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
    if (turns.length) {
      return turns;
    }
    return result?.demo_snapshots ?? [];
  }, [turns, result?.demo_snapshots]);

  const stopReason = result?.stop_reason ?? (turns.length ? (isRunning ? 'Running…' : 'In progress') : 'Pending');
  const stepsUsed = result?.step ?? turns.length;
  const rlThresholds = rlInfo?.thresholds ?? result?.rl_thresholds ?? undefined;
  const rlScores = rlInfo?.scores ?? result?.rl_scores ?? undefined;
  const rlNotes = rlInfo?.notes ?? result?.rl_rationale ?? undefined;

  return (
    <main className="flex flex-col gap-10 px-6 py-10 lg:px-12">
      <header className="max-w-5xl space-y-4">
        <p className="text-sm uppercase tracking-[0.3em] text-slate-400">User Simulation Demo</p>
      </header>

      <section className="grid gap-8 lg:grid-cols-[minmax(320px,380px)_1fr] lg:items-start">
        <aside className="space-y-6 rounded-2xl border border-slate-700/60 bg-slate-900/60 p-6 shadow-xl">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Simulation controls</h2>
            <p className="mt-1 text-sm text-slate-400">
              Adjust the persona narrative or tweak the step budget. Conversations automatically stop when the emotion threshold got passed, 
              or maximum step is reached.
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

          <dl className="space-y-3 text-sm text-slate-300">
            <div>
              <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Stop reason</dt>
              <dd className="mt-1 text-slate-100">{stopReason}</dd>
            </div>
            <div>
              <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Steps used</dt>
              <dd className="mt-1 text-slate-100">{stepsUsed}</dd>
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
            {rlThresholds ? (
              <div>
                <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Emotion Score Thresholds</dt>
                <dd className="mt-1 text-slate-100 space-y-1">
                  <div>Positive: {rlThresholds.positive?.toFixed(2) ?? '—'}</div>
                  <div>Negative: {rlThresholds.negative?.toFixed(2) ?? '—'}</div>
                </dd>
              </div>
            ) : null}
            {rlScores ? (
              <div>
                <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Current Emotion Scores</dt>
                <dd className="mt-1 text-slate-100 space-y-1">
                  <div>Positive: {rlScores.positive?.toFixed(2) ?? '—'}</div>
                  <div>Negative: {rlScores.negative?.toFixed(2) ?? '—'}</div>
                </dd>
              </div>
            ) : null}
            {rlNotes ? (
              <div>
                <dt className="font-semibold uppercase tracking-wide text-xs text-slate-500">Emotion notes</dt>
                <dd className="mt-1 whitespace-pre-line text-slate-200/80">{rlNotes}</dd>
              </div>
            ) : null}
          </dl>
        </aside>

        <div className="space-y-8">
          {result ? (
            <section className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-6 shadow-xl">
              <h2 className="text-lg font-semibold text-slate-100">Conversation summary</h2>
              <p className="mt-2 text-sm text-slate-300/90">
                {result.conversation_summary ?? 'Summary not available yet.'}
              </p>
              {result.summary_notes ? (
                <p className="mt-3 text-xs text-slate-400">Latest delta: {result.summary_notes}</p>
              ) : null}
            </section>
          ) : null}

          <section className="space-y-5 rounded-2xl border border-slate-700/60 bg-slate-900/40 p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-slate-100">Simulation Timeline</h2>
            {snapshots.length ? (
              snapshots.map((turn, index) => (
                <SimulationTurnCard key={turn.step ?? index} turn={turn} />
              ))
            ) : (
              <p className="text-sm text-slate-400">Run the simulator to populate the timeline.</p>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}
