import { useEffect, useState } from "react";

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

function BmiCard({ bmi }) {
  if (!bmi) return null;
  const atTarget = Math.abs(bmi.weight_kg - bmi.target_weight_kg) < 0.1;
  return (
    <div className="bmi-card">
      <div className="bmi-figure">
        <span className="bmi-value">{bmi.bmi}</span>
        <span className={`bmi-category ${bmi.category}`}>{bmi.category}</span>
      </div>
      <div className="bmi-details">
        <span>
          {bmi.weight_kg} kg at {bmi.height_cm} cm
        </span>
        <span>
          {atTarget
            ? "At target weight"
            : `Target: ${bmi.target_weight_kg} kg`}{" "}
          &middot; {bmi.target_note}
        </span>
      </div>
    </div>
  );
}

export default function Today({ plan, bmi, onAdjust, justUpdated, onDismissUpdate }) {
  const today = plan.days[0];
  const rest = plan.days.slice(1);
  const isGemini = plan.generated_by === "gemini_refined";

  const swaps = today.blocks.filter((b) => b.swap_reason);

  // Client-side only for now -- there's no session_logs table yet (Layer 5
  // adaptation is a later pass), so neither of these persists across a
  // reload. They're still real UX, not placeholders: the 10-minute cut
  // mirrors the spec's "first compound, fewer sets" minimum-viable session,
  // and the checklist is what "Start" should actually do instead of nothing.
  const [tenMinute, setTenMinute] = useState(false);
  const [started, setStarted] = useState(false);
  const [completed, setCompleted] = useState(() => new Set());

  // A new day's plan shouldn't inherit yesterday's checked-off state.
  useEffect(() => {
    setStarted(false);
    setCompleted(new Set());
    setTenMinute(false);
  }, [today.date, plan.plan_id]);

  function toggleDone(exerciseId) {
    setCompleted((prev) => {
      const next = new Set(prev);
      if (next.has(exerciseId)) {
        next.delete(exerciseId);
      } else {
        next.add(exerciseId);
      }
      return next;
    });
  }

  const displayBlocks =
    tenMinute && today.blocks.length > 0
      ? [{ ...today.blocks[0], sets: Math.min(today.blocks[0].sets, 2) }]
      : today.blocks;

  const allDone = started && displayBlocks.length > 0 && displayBlocks.every((b) => completed.has(b.exercise_id));

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

      {justUpdated && (
        <div className="update-banner">
          <div className="update-banner-text">
            <strong>Plan updated.</strong>{" "}
            {isGemini
              ? swaps.length > 0
                ? `${swaps.length} exercise${swaps.length > 1 ? "s" : ""} changed today.`
                : "Your coach adjusted the plan."
              : "Gemini didn't respond in time, so your last working plan carried forward instead."}
          </div>
          <button type="button" className="update-banner-dismiss" onClick={onDismissUpdate} aria-label="Dismiss">
            &times;
          </button>
        </div>
      )}

      <h1>{today.type === "rest" ? "Rest day" : today.focus ? `${humanize(today.focus)} day` : "Today"}</h1>

      <BmiCard bmi={bmi} />

      <div className="ledger-card">
        {today.type === "workout" ? (
          <>
            <p className="session-meta">
              ~{tenMinute ? Math.min(today.est_minutes, 10) : today.est_minutes} min &middot;{" "}
              {displayBlocks.length} exercise{displayBlocks.length === 1 ? "" : "s"}
              {tenMinute && " · 10-minute version"}
            </p>
            <div className="exercise-list">
              {displayBlocks.map((b) => {
                const isDone = completed.has(b.exercise_id);
                return (
                  <div
                    key={b.exercise_id}
                    className={`exercise-row ${started ? "checkable" : ""} ${isDone ? "done" : ""}`}
                    onClick={started ? () => toggleDone(b.exercise_id) : undefined}
                    role={started ? "checkbox" : undefined}
                    aria-checked={started ? isDone : undefined}
                    tabIndex={started ? 0 : undefined}
                    onKeyDown={
                      started
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              toggleDone(b.exercise_id);
                            }
                          }
                        : undefined
                    }
                  >
                    <span className="exercise-main">
                      {started && (
                        <span className={`exercise-check ${isDone ? "checked" : ""}`} aria-hidden="true" />
                      )}
                      <span className="exercise-name">
                        {humanize(b.exercise_id)}
                        {justUpdated && b.swap_reason && <span className="swapped-tag">Swapped</span>}
                      </span>
                    </span>
                    <span className="exercise-figures">
                      {b.sets}&times;{b.rep_low}-{b.rep_high} @RIR{b.rir} &middot; {b.rest_seconds}s
                    </span>
                    {b.swap_reason && <span className="exercise-note swap">{b.swap_reason}</span>}
                    {b.note && <span className="exercise-note">{b.note}</span>}
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <p className="rest-note">Scheduled recovery. Your streak stays intact.</p>
        )}
      </div>

      {today.type === "workout" && (
        <div className="today-actions">
          {!started ? (
            <>
              <button type="button" className="btn primary" onClick={() => setStarted(true)}>
                Start
              </button>
              <button type="button" className="link-action" onClick={() => setTenMinute((v) => !v)}>
                {tenMinute ? "Show the full session" : "I've only got 10 minutes"}
              </button>
            </>
          ) : (
            <>
              <p className="session-progress">
                {allDone
                  ? "All done for today."
                  : `${completed.size} of ${displayBlocks.length} checked off -- tap an exercise as you finish it.`}
              </p>
              <button
                type="button"
                className="link-action"
                onClick={() => {
                  setStarted(false);
                  setCompleted(new Set());
                }}
              >
                Reset checklist
              </button>
            </>
          )}
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
