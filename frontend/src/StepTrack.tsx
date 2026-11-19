import { useCssVar } from "./hooks";
import { stepStates, type StepState } from "./steps";
import type { Job } from "./types";

const STATE_WORD: Record<StepState, string> = {
  todo: "not started",
  active: "running",
  done: "done",
  failed: "stopped",
};

function Segment({ state, progress }: { state: StepState; progress: number }) {
  const ref = useCssVar<HTMLSpanElement>("--fill", `${Math.min(100, Math.max(0, progress))}%`);
  return (
    <span className="track-seg" data-state={state}>
      {state === "active" && <span className="track-fill" ref={ref} />}
    </span>
  );
}

/** The four pipeline steps as segments. `large` adds a label under each. */
export function StepTrack({ job, large = false }: { job: Job; large?: boolean }) {
  const steps = stepStates(job);
  const description = steps
    .map((s) => `${s.label} ${s.state === "active" ? `${Math.round(s.progress)}%` : STATE_WORD[s.state]}`)
    .join(", ");

  if (!large) {
    return (
      <span className="track" role="img" aria-label={description}>
        {steps.map((s) => (
          <Segment key={s.label} state={s.state} progress={s.progress} />
        ))}
      </span>
    );
  }
  return (
    <ol className="track-lg" aria-label="Steps">
      {steps.map((s) => (
        <li key={s.label} className="track-step" data-state={s.state}>
          <Segment state={s.state} progress={s.progress} />
          <span>
            {s.label}
            <span className="visually-hidden">, {STATE_WORD[s.state]}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
