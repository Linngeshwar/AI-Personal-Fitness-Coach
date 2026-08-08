import { useState } from "react";
import { adjustPlan } from "../api/client";

const EXAMPLES = [
  "shoulder's sore, only got 25 minutes today",
  "traveling, hotel gym with just dumbbells",
  "feeling strong, push me harder today",
  "skip today, exams this week",
];

export default function Adjust({ onDone, onCancel }) {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit() {
    if (!text.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const plan = await adjustPlan(text.trim());
      onDone(plan);
    } catch (err) {
      setError(err.message || "Couldn't reach the coach. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="adjust">
      <p className="eyebrow">Adjust</p>
      <h1>What's different about today?</h1>

      <textarea
        className="adjust-textarea"
        placeholder="Tell it like you'd tell a coach..."
        value={text}
        onChange={(e) => setText(e.target.value)}
        autoFocus
      />
      <p className="adjust-hint">
        Gemini reads this and proposes changes within your existing equipment and injuries -- a
        validator checks every change before it reaches you, and if anything goes wrong your last
        working plan ships instead.
      </p>

      <div className="example-chips">
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" className="example-chip" onClick={() => setText(ex)}>
            {ex}
          </button>
        ))}
      </div>

      {error && <div className="screening-card warn" style={{ marginTop: 16 }}>{error}</div>}

      <div className="adjust-actions">
        <button type="button" className="btn" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
        <button type="button" className="btn primary" onClick={handleSubmit} disabled={submitting || !text.trim()}>
          {submitting ? "Rewriting your plan..." : "Update my plan"}
        </button>
      </div>
    </div>
  );
}
