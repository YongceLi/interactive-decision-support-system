/* eslint-disable @next/next/no-img-element */

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

const mileageFormatter = new Intl.NumberFormat('en-US');

export interface VehicleSummary {
  vehicle?: {
    year?: number;
    make?: string;
    model?: string;
    trim?: string;
  } | null;
  retailListing?: {
    price?: number;
    miles?: number;
    city?: string;
    state?: string;
    vdp?: string | null;
  } | null;
  photos?: {
    retail?: string[] | null;
  } | null;
}

export interface CompletionReview {
  should_end?: boolean;
  confidence?: number;
  reason?: string;
}

export interface SimulationTurn {
  step: number;
  user_text: string;
  assistant_text: string;
  actions: Array<Record<string, unknown>>;
  summary: string;
  scores?: { positive?: number; negative?: number };
  judge?: { score?: number; passes?: boolean; feedback?: string; reminder?: string } | null;
  rationale?: string | null;
  quick_replies?: string[] | null;
  vehicles?: VehicleSummary[] | null;
  completion_review?: CompletionReview | null;
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

function VehicleCardList({ vehicles }: { vehicles?: VehicleSummary[] | null }) {
  if (!vehicles || vehicles.length === 0) {
    return (
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-indigo-200">Vehicle Listings</h3>
        <p className="mt-1 text-slate-400">No vehicles available for this turn.</p>
      </section>
    );
  }

  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-indigo-200">Vehicle Listings</h3>
      <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {vehicles.slice(0, 3).map((vehicle, idx) => {
          const details = vehicle.vehicle ?? {};
          const listing = vehicle.retailListing ?? {};
          const photoUrl = vehicle.photos?.retail?.[0] ?? null;
          const title = [details.year, details.make, details.model].filter(Boolean).join(' ');
          const subtitle = details.trim ? `${details.trim}` : '';
          const priceLabel = typeof listing.price === 'number' ? currencyFormatter.format(listing.price) : '—';
          const mileageLabel = typeof listing.miles === 'number' ? `${mileageFormatter.format(listing.miles)} mi` : '—';
          const location = [listing.city, listing.state].filter(Boolean).join(', ');

          return (
            <article
              key={idx}
              className="overflow-hidden rounded-xl border border-slate-700/70 bg-slate-900/80 shadow"
            >
              <div className="h-36 w-full bg-slate-800/60">
                {photoUrl ? (
                  <img src={photoUrl} alt={title || `Vehicle ${idx + 1}`} className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-slate-400">
                    No image available
                  </div>
                )}
              </div>
              <div className="space-y-2 p-4 text-sm text-slate-200/90">
                <div>
                  <div className="font-semibold text-slate-100">{title || `Vehicle ${idx + 1}`}</div>
                  {subtitle ? <div className="text-xs text-slate-400">{subtitle}</div> : null}
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-emerald-300">{priceLabel}</span>
                  <span className="text-xs text-slate-400">{mileageLabel}</span>
                </div>
                {location ? <div className="text-xs text-slate-400">{location}</div> : null}
                {listing.vdp ? (
                  <a
                    href={listing.vdp}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center justify-center rounded-lg border border-sky-400/60 px-3 py-1 text-xs font-semibold text-sky-200 hover:bg-sky-500/10"
                  >
                    View Details
                  </a>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function QuickRepliesList({ options }: { options?: string[] | null }) {
  if (!options || options.length === 0) {
    return null;
  }
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-indigo-200">Quick Replies</h3>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((reply, idx) => (
          <span
            key={`${reply}-${idx}`}
            className="rounded-lg border border-slate-600/60 bg-slate-800/70 px-3 py-1 text-xs text-slate-100"
          >
            {reply}
          </span>
        ))}
      </div>
    </section>
  );
}

function CompletionReviewCard({ review }: { review?: CompletionReview | null }) {
  if (!review) {
    return null;
  }
  return (
    <section className="rounded-lg border border-emerald-500/40 bg-emerald-950/30 p-3 text-xs text-emerald-100">
      <div className="font-semibold uppercase tracking-wide text-emerald-200/90">Completion Judge</div>
      <div className="mt-1 flex flex-wrap items-center gap-4">
        <span>
          Should end: <strong>{review.should_end ? 'Yes' : 'No'}</strong>
        </span>
        {typeof review.confidence === 'number' ? (
          <span>Confidence: {(review.confidence * 100).toFixed(0)}%</span>
        ) : null}
      </div>
      {review.reason ? <p className="mt-2 whitespace-pre-line leading-relaxed">{review.reason}</p> : null}
    </section>
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

        <VehicleCardList vehicles={turn.vehicles} />

        <QuickRepliesList options={turn.quick_replies} />

        {/* <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-indigo-200">Summary Slice</h3>
          <p className="mt-1 text-slate-200/90">{turn.summary}</p>
        </section> */}

        {turn.rationale ? (
          <section className="rounded-lg border border-slate-700/80 bg-slate-900/80 p-3 text-xs text-slate-200/90">
            <div className="font-semibold uppercase tracking-wide text-slate-300/80">Emotion Rationale</div>
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

        <CompletionReviewCard review={turn.completion_review} />

        {/* {turn.judge && !turn.judge.passes && turn.judge.reminder ? (
          <section className="rounded-lg border border-rose-400/60 bg-rose-950/50 p-3 text-xs text-rose-100">
            <div className="font-semibold uppercase tracking-wide">Judge Reminder</div>
            <p className="mt-1 whitespace-pre-line">{turn.judge.reminder}</p>
          </section>
        ) : null} */}
      </div>
    </article>
  );
}
