const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Foundation pass has no /api/exercises lookup yet, so exercise cards show
// a humanized version of the id (e.g. "chest_compound" -> "Chest Compound")
// rather than the real catalog name/image. Swapping in the real name comes
// with the exercise-catalog endpoint in a later pass.
function humanize(id) {
  return id
    .split(/[_-]/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

function formatDate(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return `${DAY_NAMES[d.getDay()]} ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
}

export default function Today({ plan, onAdjust }) {
  const today = plan.days[0];
  const rest = plan.days.slice(1);
  const isGemini = plan.generated_by === "gemini_refined";

  return (
    <div className="today">
      <div className="today-head">
        <p className="eyebrow" style={{ marginBottom: 0 }}>
          Week of {formatDate(plan.week_start)}
        </p>
        <span className={`badge ${isGemini ? "gemini" : ""}`}>
          {isGemini ? "Gemini-refined" : "Deterministic"}
        </span>
      </div>
      <h1>{today.type === "rest" ? "Rest day" : today.focus ? `${humanize(today.focus)} day` : "Today"}</h1>

      <div className="ledger-card">
        {today.type === "workout" ? (
          <>
            <p className="session-meta">
              ~{today.est_minutes} min &middot; {today.blocks.length} exercises
            </p>
            <div className="exercise-list">
              {today.blocks.map((b) => (
                <div className="exercise-row" key={b.exercise_id}>
                  <span className="exercise-name">{humanize(b.exercise_id)}</span>
                  <span className="exercise-figures">
                    {b.sets}&times;{b.rep_low}-{b.rep_high} @RIR{b.rir} &middot; {b.rest_seconds}s
                  </span>
                  {b.note && <span className="exercise-note">{b.note}</span>}
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="rest-note">Scheduled recovery. Your streak stays intact.</p>
        )}
      </div>

      {today.type === "workout" && (
        <div className="today-actions">
          <button type="button" className="btn primary">
            Start
          </button>
          <button type="button" className="link-action">
            I've only got 10 minutes
          </button>
        </div>
      )}

      <button type="button" className="link-action" onClick={onAdjust}>
        Something different about today? Adjust the plan &rarr;
      </button>

      <h2 className="week-heading">This week</h2>
      <div className="week-pills">
        {[today, ...rest].map((d) => (
          <div key={d.date} className={`pill ${d.type}`}>
            <span className="pill-day">{formatDate(d.date)}</span>
            <span className="pill-type">{d.type === "workout" ? humanize(d.focus ?? "") : "Rest"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
