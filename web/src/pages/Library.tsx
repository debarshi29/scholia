// Library board: weak spots, source filter, problem cards and the session setup panel.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  api,
  type AssistantMode,
  type CategoryStat,
  type LibrarySettings,
  type ProblemCard,
  type Source,
} from "../api/client";
import { Button, errorText, Loading, Notice, Segmented } from "../components/ui";
import {
  CATEGORY_LABEL,
  percent,
  plural,
  problemTitle,
  rateTone,
  SOURCE_LABEL,
} from "../lib/format";
import { Link, navigate } from "../router";

type SourceFilter = Source | "all";

const BAR = { coral: "bg-coral", amber: "bg-amber", green: "bg-green" } as const;
const SOURCE_TEXT: Record<Source, string> = { swebench: "text-cyan", bugsinpy: "text-amber" };

function WeakSpots({ stats }: { stats: CategoryStat[] }) {
  const seen = stats
    .filter((s) => s.attempts > 0)
    .sort((a, b) => (b.miss_rate ?? 0) - (a.miss_rate ?? 0));
  const sessions = seen.reduce((n, s) => n + s.attempts, 0);
  return (
    <section className="rounded-xl border border-line bg-panel px-6 py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold">Your weak spots</h2>
        <p className="text-[13px] text-mute">
          {seen.length > 0
            ? `Share of key bugs you missed, ${plural(sessions, "graded bug")} so far`
            : "Share of key bugs you missed"}
        </p>
      </div>
      {seen.length === 0 ? (
        <p className="mt-3 text-mute">
          Nothing graded yet. After your first debrief, the kinds of bug you miss most show up
          here, and problems that match them come first.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-3.5">
          {seen.map((s) => {
            const rate = s.miss_rate ?? 0;
            return (
              <li key={s.category} className="grid grid-cols-[12rem_1fr_3rem] items-center gap-4">
                <span>{CATEGORY_LABEL[s.category]}</span>
                <span
                  className="h-1.5 overflow-hidden rounded-full bg-raised"
                  role="img"
                  aria-label={`${CATEGORY_LABEL[s.category]}: missed ${s.misses} of ${s.attempts}`}
                >
                  <span
                    className={`block h-full rounded-full ${BAR[rateTone(rate)]}`}
                    style={{ width: `${Math.max(rate * 100, rate > 0 ? 2 : 0)}%` }}
                  />
                </span>
                <span className="text-right font-mono text-[13px] text-mute">{percent(rate)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function result(p: ProblemCard): string {
  if (p.best_found != null && p.best_bugs != null) {
    const minutes = Math.max(1, Math.round((p.best_seconds ?? 0) / 60));
    return `Best ${p.best_found} of ${plural(p.best_bugs, "bug")} · ${minutes} min`;
  }
  return p.attempts > 0 ? "Started, not finished" : "Not attempted";
}

function Card(props: { problem: ProblemCard; selected: boolean; onSelect: () => void }) {
  const p = props.problem;
  return (
    <button
      type="button"
      aria-pressed={props.selected}
      onClick={props.onSelect}
      className={`flex flex-col gap-3 rounded-xl border px-6 py-5 text-left transition ${
        props.selected ? "border-cyan bg-raised" : "border-line bg-panel hover:border-mute/50"
      }`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-mono text-[13px] text-mute">{p.id}</span>
        <span
          className={`rounded bg-bg px-2 py-1 font-mono text-[12px] leading-none tracking-wider uppercase ${SOURCE_TEXT[p.source]}`}
        >
          {SOURCE_LABEL[p.source]}
        </span>
      </span>
      <span className="truncate text-lg font-semibold" title={p.files.join("\n")}>
        {problemTitle(p.origin_repo, p.files)}
      </span>
      <span className="text-[13px] text-mute">
        Python · {plural(p.files.length, "file")} · {p.lines} lines
      </span>
      <span className="text-[13px] text-mute">{result(p)}</span>
    </button>
  );
}

function Stepper(props: {
  label: string;
  value: number;
  display: string;
  step: number;
  min: number;
  max: number;
  disabled: boolean;
  onChange: (value: number) => void;
}) {
  const { label, value, step, min, max, disabled, onChange } = props;
  const button =
    "flex size-11 items-center justify-center rounded-lg border border-line bg-bg text-lg hover:border-mute/60 disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-3">
      <span>{label}</span>
      <span className="flex items-center gap-2">
        <button
          type="button"
          className={button}
          aria-label={`Decrease ${label.toLowerCase()}`}
          disabled={disabled || value - step < min}
          onClick={() => onChange(value - step)}
        >
          −
        </button>
        <output className="w-24 text-center font-mono" aria-live="polite">
          {props.display}
        </output>
        <button
          type="button"
          className={button}
          aria-label={`Increase ${label.toLowerCase()}`}
          disabled={disabled || value + step > max}
          onClick={() => onChange(value + step)}
        >
          +
        </button>
      </span>
    </div>
  );
}

function Setup(props: {
  settings: LibrarySettings;
  selected: ProblemCard | null;
  source: SourceFilter;
}) {
  const { settings, selected, source } = props;
  const [mode, setMode] = useState<AssistantMode>("constrained");
  const [ctxCap, setCtxCap] = useState(settings.default_ctx_cap);
  const [budget, setBudget] = useState(settings.default_q_budget);
  const constrained = mode === "constrained";
  const info = settings.modes.find((m) => m.mode === mode);
  const realistic = settings.modes.find((m) => m.mode === "realistic");
  const start = useMutation({
    mutationFn: () =>
      api.createSession({
        problem_id: selected?.id ?? null,
        source: selected || source === "all" ? null : source,
        mode,
        ctx_cap: ctxCap,
        q_budget: budget,
      }),
    onSuccess: (view) => navigate(`/session/${view.id}`),
  });

  return (
    <aside className="h-fit rounded-xl border border-line bg-panel px-7 py-7">
      <form
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          start.mutate();
        }}
      >
        <div>
          <p className="text-[12px] tracking-widest text-mute uppercase">Session setup</p>
          <h2 className="mt-2 text-xl font-semibold">
            {selected ? problemTitle(selected.origin_repo, selected.files) : "Picked for you"}
          </h2>
          <p className="mt-1 text-[13px] text-mute">
            {selected
              ? `${selected.id} · Python · ${plural(selected.files.length, "file")} · ${selected.lines} lines`
              : `Weighted by your weak spots${source === "all" ? "" : `, from ${SOURCE_LABEL[source]}`}. Or choose a card.`}
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <p className="font-semibold">Assistant</p>
          <Segmented
            label="Assistant mode"
            value={mode}
            onChange={setMode}
            options={[
              { value: "constrained", label: "Constrained" },
              {
                value: "realistic",
                label: "Realistic",
                disabled: !realistic?.available,
                title: realistic?.available ? undefined : "Needs a Gemini key and model in .env",
              },
            ]}
          />
          <p className="text-[13px] leading-relaxed text-mute">
            {constrained
              ? "A small local model with a tight window. You choose what it sees and spend a limited number of questions. Trains scoping and verification."
              : "A capable cloud model that sees the whole file, with no question limit. Trains checking an assistant that does not fail loudly."}
          </p>
        </div>

        <div className="flex flex-col gap-4 rounded-lg bg-raised px-5 py-5">
          <Stepper
            label="Context window"
            value={ctxCap}
            display={constrained ? `${ctxCap.toLocaleString()} tok` : "whole file"}
            step={512}
            min={512}
            max={32768}
            disabled={!constrained}
            onChange={setCtxCap}
          />
          <Stepper
            label="Questions"
            value={budget}
            display={constrained ? String(budget) : "no limit"}
            step={1}
            min={0}
            max={50}
            disabled={!constrained}
            onChange={setBudget}
          />
          <div className="flex items-center justify-between">
            <span>Timer</span>
            <span className="font-mono">{settings.session_minutes}:00</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span>Model</span>
            <span className="truncate font-mono text-[13px]">
              {info?.model} · {constrained ? "local" : "cloud"}
            </span>
          </div>
        </div>

        {start.isError && <Notice tone="coral">{errorText(start.error)}</Notice>}
        <Button type="submit" className="min-h-14 text-base font-semibold" disabled={start.isPending}>
          {start.isPending ? "Starting…" : `Start ${settings.session_minutes}-minute session`}
        </Button>
        <p className="text-[13px] text-mute">
          The answer key stays hidden until you submit your report.
        </p>
      </form>
    </aside>
  );
}

export default function Library() {
  const problems = useQuery({ queryKey: ["problems"], queryFn: api.problems });
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: api.sessions });
  const [source, setSource] = useState<SourceFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const lastDebrief = sessions.data?.find((s) => s.graded);
  const resume = sessions.data?.find((s) => !s.submitted_at);
  const header = (
    <header className="flex min-h-16 items-center justify-between gap-4 border-b border-line bg-panel px-6">
      <div className="flex items-baseline gap-5">
        <span className="font-mono text-lg text-cyan">scholia</span>
        <span className="text-[13px] text-mute">code comprehension practice</span>
      </div>
      <nav className="flex items-center gap-2">
        {resume && (
          <Link
            to={`/session/${resume.id}`}
            className="flex min-h-11 items-center rounded-md px-3 text-amber hover:bg-raised"
          >
            Resume {resume.problem_id}
          </Link>
        )}
        {lastDebrief && (
          <Link
            to={`/debrief/${lastDebrief.id}`}
            className="flex min-h-11 items-center rounded-md px-3 text-mute hover:bg-raised hover:text-ink"
          >
            Last debrief
          </Link>
        )}
      </nav>
    </header>
  );

  const failed = [problems, stats, settings].find((q) => q.isError);
  if (failed) {
    return (
      <>
        {header}
        <div className="p-6">
          <Notice tone="coral">{errorText(failed.error)}</Notice>
        </div>
      </>
    );
  }
  if (!problems.data || !stats.data || !settings.data) {
    return (
      <>
        {header}
        <Loading />
      </>
    );
  }

  const visible = problems.data.filter((p) => source === "all" || p.source === source);
  const selected = visible.find((p) => p.id === selectedId) ?? null;
  const filters: { value: SourceFilter; label: string }[] = [
    { value: "all", label: "All" },
    { value: "swebench", label: SOURCE_LABEL.swebench },
    { value: "bugsinpy", label: SOURCE_LABEL.bugsinpy },
  ];

  return (
    <>
      {header}
      <div className="mx-auto grid max-w-[1500px] gap-6 px-6 py-7 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <div>
            <h1 className="text-3xl font-semibold">Pick a problem</h1>
            <p className="mt-2 text-mute">
              Each one is a real file you have not seen, with a bug you have to find. Problems
              that match your weak spots come first.
            </p>
          </div>

          <WeakSpots stats={stats.data} />

          <div role="group" aria-label="Source" className="flex flex-wrap items-center gap-2.5">
            <span className="mr-1 text-[13px] text-mute">Source</span>
            {filters.map((f) => (
              <button
                key={f.value}
                type="button"
                aria-pressed={source === f.value}
                onClick={() => setSource(f.value)}
                className={`min-h-11 rounded-full px-5 font-semibold transition ${
                  source === f.value
                    ? "bg-cyan text-bg"
                    : "border border-line text-ink hover:border-mute/60"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {problems.data.length === 0 ? (
            <Notice>
              No problems are published yet. Build the corpus first:{" "}
              <code className="font-mono text-ink">
                python -m corpus.build --tier 0 --source swebench --limit 20
              </code>
            </Notice>
          ) : visible.length === 0 ? (
            <p className="text-mute">No problems from this source.</p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {visible.map((p) => (
                <Card
                  key={p.id}
                  problem={p}
                  selected={p.id === selected?.id}
                  onSelect={() => setSelectedId(p.id === selected?.id ? null : p.id)}
                />
              ))}
            </div>
          )}
        </div>
        <Setup settings={settings.data} selected={selected} source={source} />
      </div>
    </>
  );
}
