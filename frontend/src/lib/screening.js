// Client-side mirror of backend/rules/screening.py's apply_screening().
// Used only to show the screening card live during onboarding, before the
// profile is ever submitted -- the backend re-applies the same rule
// server-side and that result, not this one, is what's actually persisted.
export function applyScreening(safety) {
  if (safety.under_18 || safety.pregnant_or_postpartum || safety.eating_disorder_history) {
    return {
      nutrition_enabled: false,
      requires_clearance: false,
      message: "We won't set calorie targets for you. Talk to a doctor or dietitian.",
      volume_cap: 0.7,
    };
  }
  if (safety.chest_pain_on_exertion || safety.cardiac_or_bp_condition) {
    return {
      nutrition_enabled: true,
      requires_clearance: true,
      message: "Check with a doctor before starting a new training program.",
      volume_cap: 1.0,
    };
  }
  return { nutrition_enabled: true, requires_clearance: false, message: null, volume_cap: 1.0 };
}
