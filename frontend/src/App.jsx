import { useEffect, useState } from "react";
import { deleteMe, fetchBmiSummary, fetchCurrentPlan } from "./api/client";
import Adjust from "./pages/Adjust";
import DebugValidations from "./pages/DebugValidations";
import Onboarding from "./pages/Onboarding";
import Today from "./pages/Today";
import "./App.css";

function Masthead({ onReset, onDebug }) {
  return (
    <header className="masthead">
      <span className="wordmark">
        Coach Log
        <small>the plan that survives you missing a day</small>
      </span>
      {(onReset || onDebug) && (
        <span className="masthead-links">
          {onDebug && (
            <button type="button" className="reset-demo-btn" onClick={onDebug}>
              Validator log
            </button>
          )}
          {onReset && (
            <button type="button" className="reset-demo-btn" onClick={onReset}>
              Reset demo
            </button>
          )}
        </span>
      )}
    </header>
  );
}

export default function App() {
  const [plan, setPlan] = useState(null);
  const [bmi, setBmi] = useState(null);
  const [checking, setChecking] = useState(true);
  const [view, setView] = useState("today"); // "today" | "adjust" | "debug" (onboarding shows whenever plan is null)
  const [justUpdated, setJustUpdated] = useState(false);
  const [resetting, setResetting] = useState(false);

  async function handleReset() {
    if (!window.confirm("Delete this user and start onboarding fresh? This can't be undone.")) return;
    setResetting(true);
    try {
      await deleteMe();
    } catch {
      // No profile to delete, or already gone -- fine either way, fall through to onboarding.
    } finally {
      setPlan(null);
      setBmi(null);
      setView("today");
      setJustUpdated(false);
      setResetting(false);
    }
  }

  useEffect(() => {
    fetchCurrentPlan()
      .then(setPlan)
      .catch(() => setPlan(null))
      .finally(() => setChecking(false));
  }, []);

  // Weight/height don't change via /plan/adjust, so this only needs to
  // re-run when a plan first appears (onboarding, or after a reset).
  useEffect(() => {
    if (!plan) {
      setBmi(null);
      return;
    }
    fetchBmiSummary()
      .then(setBmi)
      .catch(() => setBmi(null));
  }, [plan]);

  if (checking) {
    return (
      <main className="shell">
        <Masthead />
        <p className="eyebrow">Loading...</p>
      </main>
    );
  }

  if (!plan) {
    return (
      <main className="shell">
        <Masthead />
        {resetting && <p className="eyebrow">Resetting...</p>}
        <Onboarding
          onComplete={(newPlan) => {
            setPlan(newPlan);
            setView("today");
          }}
        />
      </main>
    );
  }

  return (
    <main className="shell">
      <Masthead onReset={handleReset} onDebug={() => setView("debug")} />
      {view === "adjust" && (
        <Adjust
          onDone={(newPlan) => {
            setPlan(newPlan);
            setJustUpdated(true);
            setView("today");
          }}
          onCancel={() => setView("today")}
        />
      )}
      {view === "debug" && <DebugValidations onBack={() => setView("today")} />}
      {view === "today" && (
        <Today
          plan={plan}
          bmi={bmi}
          onAdjust={() => setView("adjust")}
          justUpdated={justUpdated}
          onDismissUpdate={() => setJustUpdated(false)}
        />
      )}
    </main>
  );
}
