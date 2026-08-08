import { useEffect, useState } from "react";
import { fetchCurrentPlan } from "./api/client";
import Adjust from "./pages/Adjust";
import Onboarding from "./pages/Onboarding";
import Today from "./pages/Today";
import "./App.css";

function Masthead() {
  return (
    <header className="masthead">
      <span className="wordmark">
        Coach Log
        <small>the plan that survives you missing a day</small>
      </span>
    </header>
  );
}

export default function App() {
  const [plan, setPlan] = useState(null);
  const [checking, setChecking] = useState(true);
  const [view, setView] = useState("today"); // "today" | "adjust" (onboarding shows whenever plan is null)

  useEffect(() => {
    fetchCurrentPlan()
      .then(setPlan)
      .catch(() => setPlan(null))
      .finally(() => setChecking(false));
  }, []);

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
      <Masthead />
      {view === "adjust" ? (
        <Adjust
          onDone={(newPlan) => {
            setPlan(newPlan);
            setView("today");
          }}
          onCancel={() => setView("today")}
        />
      ) : (
        <Today plan={plan} onAdjust={() => setView("adjust")} />
      )}
    </main>
  );
}
