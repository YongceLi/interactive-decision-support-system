export interface SimulationTurn {
  step: number;
  user_text: string;
  assistant_text: string;
  actions: Array<Record<string, unknown>>;
  summary: string;
  scores?: { positive?: number; negative?: number };
  judge?: { score?: number; passes?: boolean; feedback?: string; reminder?: string } | null;
  rationale?: string | null;
}

function formatAction(action: Record<string, unknown>, index: number) {
  const type = typeof action.type === 'string' ? action.type : 'action';
  const label = typeof action.label === 'string' ? action.label : '';
  const details = { ...action };
  delete details.type;
  delete details.label;
  const detailEntries = Object.entries(details)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${key}: ${String(value)}`);

  return (
    <li key={`${type}-${index}`} className="text-sm text-slate-200/90">
      <span className="font-semibold text-sky-200">{type.toUpperCase()}</span>
      {label ? <span className="ml-2 text-slate-300">{label}</span> : null}
      {detailEntries.length ? (
        <div className="ml-3 mt-1 text-slate-300/80">{detailEntries.join(' • ')}</div>
      ) : null}
    </li>
  );
}

export function SimulationTurnCard({ turn }: { turn: SimulationTurn }) {
  return (
    <article className="rounded-xl border border-slate-700 bg-slate-900/70 p-5 shadow-lg backdrop-blur">
      <header className="flex items-center justify-between text-xs uppercase tracking-wide text-slate-400">
        <span>Turn {turn.step}</span>
        {turn.judge && typeof turn.judge.score === 'number' ? (
          <span className="font-semibold text-emerald-300">
            Alignment: {(turn.judge.score * 100).toFixed(0)}%
          </span>
        ) : null}
      </header>

      <div className="mt-4 space-y-4 text-sm leading-relaxed">
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-rose-300">User Agent</h3>
          <p className="mt-1 whitespace-pre-line text-slate-100">{turn.user_text}</p>
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-sky-300">Assistant</h3>
          <p className="mt-1 whitespace-pre-line text-slate-100">{turn.assistant_text}</p>
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-amber-200">UI Actions</h3>
          {turn.actions && turn.actions.length ? (
            <ul className="mt-1 space-y-2">{turn.actions.map(formatAction)}</ul>
          ) : (
            <p className="mt-1 text-slate-400">No UI changes planned.</p>
          )}
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-indigo-200">Summary Slice</h3>
          <p className="mt-1 text-slate-200/90">{turn.summary}</p>
        </section>

        {turn.rationale ? (
          <section className="rounded-lg border border-slate-700/80 bg-slate-900/80 p-3 text-xs text-slate-200/90">
            <div className="font-semibold uppercase tracking-wide text-slate-300/80">Rescoring Rationale</div>
            <p className="mt-1 whitespace-pre-line">{turn.rationale}</p>
          </section>
        ) : null}

        <section className="grid grid-cols-2 gap-4 text-xs text-slate-300">
          <div>
            <div className="font-semibold uppercase tracking-wide text-emerald-300/90">Positive</div>
            <div className="mt-1 text-lg font-semibold text-emerald-200">
              {turn.scores && typeof turn.scores.positive === 'number'
                ? turn.scores.positive.toFixed(2)
                : '—'}
            </div>
          </div>
          <div>
            <div className="font-semibold uppercase tracking-wide text-rose-300/90">Negative</div>
            <div className="mt-1 text-lg font-semibold text-rose-200">
              {turn.scores && typeof turn.scores.negative === 'number'
                ? turn.scores.negative.toFixed(2)
                : '—'}
            </div>
          </div>
        </section>

        {turn.judge && !turn.judge.passes && turn.judge.reminder ? (
          <section className="rounded-lg border border-rose-400/60 bg-rose-950/50 p-3 text-xs text-rose-100">
            <div className="font-semibold uppercase tracking-wide">Judge Reminder</div>
            <p className="mt-1 whitespace-pre-line">{turn.judge.reminder}</p>
          </section>
        ) : null}
      </div>
    </article>
  );
}
