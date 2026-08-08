import { useMemo, useState } from "react";
import { submitOnboarding } from "../api/client";
import { applyScreening } from "../lib/screening";

const GOALS = [
  { value: "fat_loss", label: "Fat loss" },
  { value: "muscle_gain", label: "Muscle gain" },
  { value: "strength", label: "Strength" },
  { value: "endurance", label: "Endurance" },
  { value: "general", label: "General fitness" },
];

const EQUIPMENT = [
  { value: "none", label: "None" },
  { value: "dumbbells", label: "Dumbbells" },
  { value: "barbell", label: "Barbell" },
  { value: "machines", label: "Machines / cables" },
  { value: "bands", label: "Resistance bands" },
  { value: "pullup_bar", label: "Pull-up bar" },
  { value: "full_gym", label: "Full gym" },
];

const INJURIES = [
  {value: "none", label: "None"},
  { value: "knee", label: "Knee" },
  { value: "lower_back", label: "Lower back" },
  { value: "shoulder", label: "Shoulder" },
  { value: "wrist", label: "Wrist" },
  { value: "ankle", label: "Ankle" },
];

const SAFETY_QUESTIONS = [
  { key: "under_18", label: "I am under 18" },
  { key: "pregnant_or_postpartum", label: "I am pregnant or postpartum" },
  { key: "cardiac_or_bp_condition", label: "I have a cardiac or blood-pressure condition" },
  { key: "diabetes", label: "I have diabetes" },
  { key: "eating_disorder_history", label: "I have a history of disordered eating" },
  { key: "chest_pain_on_exertion", label: "I get chest pain during exertion" },
];

const STEP_TITLES = ["Goal", "Training", "Equipment", "About you", "Safety check", "Consent"];

const initialProfile = {
  goal: "general",
  experience: "beginner",
  days_per_week: 3,
  session_minutes: 45,
  equipment: [],
  injuries: [],
  height_cm: 170,
  weight_kg: 70,
  age: 25,
  sex: "other",
  activity_level: 1.4,
  safety: {
    under_18: false,
    pregnant_or_postpartum: false,
    cardiac_or_bp_condition: false,
    diabetes: false,
    eating_disorder_history: false,
    chest_pain_on_exertion: false,
  },
};

function toggle(list, value) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

// Number inputs have no native form-level validation gate here (submit is a
// plain button click, not a <form onSubmit>), so min/max attributes alone
// are just spinner hints -- clamp on every change to actually keep the
// value in a sane human range.
function clamp(value, min, max) {
  if (Number.isNaN(value)) return min;
  return Math.min(max, Math.max(min, value));
}

// Tally marks, grouped in fives like a hand count -- steps done/active fill
// in, and a fifth mark strikes diagonally across its group of four.
function TallyProgress({ step, total }) {
  const groups = [];
  for (let i = 0; i < total; i += 4) {
    groups.push(Array.from({ length: Math.min(4, total - i) }, (_, k) => i + k));
  }
  return (
    <div className="tally" aria-hidden="true">
      {groups.map((group, gi) => (
        <span key={gi} className={`tally-group ${group.length === 4 && step > group[3] ? "struck" : ""}`}>
          {group.map((idx) => (
            <span key={idx} className={`tally-mark ${idx < step ? "done" : ""} ${idx === step ? "active" : ""}`} />
          ))}
        </span>
      ))}
    </div>
  );
}

export default function Onboarding({ onComplete }) {
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState(initialProfile);
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const screening = useMemo(() => applyScreening(profile.safety), [profile.safety]);

  const last = step === STEP_TITLES.length - 1;

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const plan = await submitOnboarding(profile);
      onComplete(plan);
    } catch (err) {
      setError(err.message || "Something went wrong submitting your profile.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="wizard">
      <TallyProgress step={step} total={STEP_TITLES.length} />
      <p className="eyebrow">
        Step {step + 1} of {STEP_TITLES.length}
      </p>
      <h1>{STEP_TITLES[step]}</h1>

      {step === 0 && (
        <div className="option-grid">
          {GOALS.map((g) => (
            <button
              key={g.value}
              type="button"
              className={`option ${profile.goal === g.value ? "selected" : ""}`}
              onClick={() => setProfile((p) => ({ ...p, goal: g.value }))}
            >
              {g.label}
            </button>
          ))}
        </div>
      )}

      {step === 1 && (
        <div className="field-stack">
          <label>
            Experience
            <select
              value={profile.experience}
              onChange={(e) => setProfile((p) => ({ ...p, experience: e.target.value }))}
            >
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
            </select>
          </label>
          <label>
            Days per week: {profile.days_per_week}
            <input
              type="range"
              min={2}
              max={6}
              value={profile.days_per_week}
              onChange={(e) => setProfile((p) => ({ ...p, days_per_week: Number(e.target.value) }))}
            />
          </label>
          <label>
            Session length
            <select
              value={profile.session_minutes}
              onChange={(e) => setProfile((p) => ({ ...p, session_minutes: Number(e.target.value) }))}
            >
              {[20, 30, 45, 60].map((m) => (
                <option key={m} value={m}>
                  {m} minutes
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {step === 2 && (
        <div className="field-stack">
          <p className="section-label">Equipment available</p>
          <div className="option-grid">
            {EQUIPMENT.map((eq) => {
              // "none" is a real Equipment value, but selecting it alongside
              // "barbell" etc. is a contradiction the backend won't catch --
              // keep the two mutually exclusive here instead.
              const isNone = eq.value === "none";
              return (
                <button
                  key={eq.value}
                  type="button"
                  className={`option ${profile.equipment.includes(eq.value) ? "selected" : ""}`}
                  onClick={() =>
                    setProfile((p) => ({
                      ...p,
                      equipment: isNone ? ["none"] : toggle(p.equipment.filter((v) => v !== "none"), eq.value),
                    }))
                  }
                >
                  {eq.label}
                </button>
              );
            })}
          </div>
          <p className="section-label">Any injuries to work around?</p>
          <div className="option-grid">
            {INJURIES.map((inj) => {
              // "none" isn't a real Injury value on the backend -- it just
              // means the list is empty, so it's never actually stored.
              const isNone = inj.value === "none";
              const isSelected = isNone ? profile.injuries.length === 0 : profile.injuries.includes(inj.value);
              return (
                <button
                  key={inj.value}
                  type="button"
                  className={`option ${isSelected ? "selected" : ""}`}
                  onClick={() =>
                    setProfile((p) => ({ ...p, injuries: isNone ? [] : toggle(p.injuries, inj.value) }))
                  }
                >
                  {inj.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="field-stack">
          <label>
            Height (cm)
            <input
              type="number"
              min={100}
              max={230}
              value={profile.height_cm}
              onChange={(e) => setProfile((p) => ({ ...p, height_cm: clamp(Number(e.target.value), 100, 230) }))}
            />
          </label>
          <label>
            Weight (kg)
            <input
              type="number"
              min={30}
              max={250}
              value={profile.weight_kg}
              onChange={(e) => setProfile((p) => ({ ...p, weight_kg: clamp(Number(e.target.value), 30, 250) }))}
            />
          </label>
          <label>
            Age
            <input
              type="number"
              min={13}
              max={90}
              value={profile.age}
              onChange={(e) => setProfile((p) => ({ ...p, age: clamp(Number(e.target.value), 13, 90) }))}
            />
          </label>
          <label>
            Sex
            <select value={profile.sex} onChange={(e) => setProfile((p) => ({ ...p, sex: e.target.value }))}>
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            Activity level outside training: {profile.activity_level.toFixed(1)}
            <input
              type="range"
              min={1.2}
              max={1.9}
              step={0.1}
              value={profile.activity_level}
              onChange={(e) => setProfile((p) => ({ ...p, activity_level: Number(e.target.value) }))}
            />
          </label>
        </div>
      )}

      {step === 4 && (
        <div className="field-stack">
          {SAFETY_QUESTIONS.map((q) => (
            <label key={q.key} className="checkbox-row">
              <input
                type="checkbox"
                checked={profile.safety[q.key]}
                onChange={(e) =>
                  setProfile((p) => ({ ...p, safety: { ...p.safety, [q.key]: e.target.checked } }))
                }
              />
              {q.label}
            </label>
          ))}
          {screening.message && (
            <div className={`screening-card ${screening.requires_clearance ? "warn" : "info"}`}>
              {screening.message}
            </div>
          )}
        </div>
      )}

      {step === 5 && (
        <div className="field-stack">
          <p className="consent-copy">
            We'll use your answers to build a training plan and, when you use the "Adjust" feature,
            to personalize it further with Gemini. Only an anonymized attribute bundle -- no name,
            no date of birth, no email -- is ever sent to Gemini. Your weight and injury history are
            encrypted at rest.
          </p>
          <label className="checkbox-row">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            I consent to plan generation and LLM-assisted personalization.
          </label>
          {error && <div className="screening-card warn">{error}</div>}
        </div>
      )}

      <div className="wizard-nav">
        <button type="button" className="btn" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
          Back
        </button>
        {!last && (
          <button type="button" className="btn primary" onClick={() => setStep((s) => s + 1)}>
            Next
          </button>
        )}
        {last && (
          <button type="button" className="btn primary" disabled={!consent || submitting} onClick={handleSubmit}>
            {submitting ? "Building your plan..." : "Get my plan"}
          </button>
        )}
      </div>
    </div>
  );
}
