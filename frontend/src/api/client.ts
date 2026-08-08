// Thin typed fetch wrapper. Types here mirror backend/schemas/*.py field-for-field
// by hand for now; swapping to generated openapi-typescript types is a good
// follow-up once the API surface stops changing every pass.

export type Goal = "fat_loss" | "muscle_gain" | "strength" | "endurance" | "general";
export type Experience = "beginner" | "intermediate" | "advanced";
export type Equipment =
  | "none"
  | "dumbbells"
  | "barbell"
  | "machines"
  | "bands"
  | "pullup_bar"
  | "full_gym";
export type Injury = "knee" | "lower_back" | "shoulder" | "wrist" | "ankle";

export interface SafetyFlags {
  under_18: boolean;
  pregnant_or_postpartum: boolean;
  cardiac_or_bp_condition: boolean;
  diabetes: boolean;
  eating_disorder_history: boolean;
  chest_pain_on_exertion: boolean;
}

export interface UserProfile {
  goal: Goal;
  experience: Experience;
  days_per_week: number;
  session_minutes: 20 | 30 | 45 | 60;
  equipment: Equipment[];
  injuries: Injury[];
  height_cm: number;
  weight_kg: number;
  age: number;
  sex: "male" | "female" | "other";
  activity_level: number;
  safety: SafetyFlags;
}

export interface PlanBlock {
  exercise_id: string;
  order: number;
  sets: number;
  rep_low: number;
  rep_high: number;
  rest_seconds: number;
  rir: number;
  note: string | null;
  swap_reason: string | null;
}

export interface PlanDay {
  date: string;
  type: "workout" | "rest" | "active_recovery";
  focus: string | null;
  est_minutes: number;
  blocks: PlanBlock[];
}

export interface Plan {
  plan_id: string;
  user_id: string;
  week_start: string;
  generated_by: "deterministic" | "gemini_refined";
  volume_multiplier: number;
  days: PlanDay[];
}

const BASE = "/api";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function submitOnboarding(profile: UserProfile): Promise<Plan> {
  return request<Plan>("/onboarding", { method: "POST", body: JSON.stringify(profile) });
}

export function fetchCurrentPlan(): Promise<Plan> {
  return request<Plan>("/plan/current");
}

export function adjustPlan(text: string): Promise<Plan> {
  return request<Plan>("/plan/adjust", { method: "POST", body: JSON.stringify({ text }) });
}

export function deleteMe(): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>("/me", { method: "DELETE" });
}

export { ApiError };
