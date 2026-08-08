import { useEffect, useState } from "react";
import { fetchRejectedPlans } from "../api/client";

function formatTimestamp(iso) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export default function DebugValidations({ onBack }) {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchRejectedPlans()
      .then(setEntries)
      .catch((err) => setError(err.message || "Couldn't load the validator log."));
  }, []);

  return (
    <div className="debug">
      <p className="eyebrow">Validator log</p>
      <h1>The model never gets the last word</h1>
      <p className="consent-copy debug-intro">
        Every plan Gemini proposes still has to pass Layer 4 before it reaches you. This is every
        plan it rejected outright -- swaps the repair step couldn't fix -- and exactly which rule
        caught it.
      </p>

      {error && <div className="screening-card warn">{error}</div>}

      {entries === null && !error && <p className="eyebrow">Loading...</p>}

      {entries && entries.length === 0 && (
        <div className="screening-card">
          Nothing rejected yet. Either every Gemini-refined plan so far has passed validation
          cleanly, or the repair step has fixed everything it's caught before it got this far.
        </div>
      )}

      {entries && entries.length > 0 && (
        <div className="debug-list">
          {entries.map((entry) => (
            <div className="debug-entry" key={entry.id}>
              <div className="debug-entry-head">
                <span className="debug-entry-time">{formatTimestamp(entry.created_at)}</span>
                <span className="badge">fell back to deterministic</span>
              </div>
              <ul className="debug-violations">
                {entry.violations.map((v, i) => (
                  <li key={i}>
                    <span className="debug-rule">{v.rule}</span>
                    <span className="debug-detail">{v.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <button type="button" className="link-action debug-back" onClick={onBack}>
        &larr; Back to today
      </button>
    </div>
  );
}
