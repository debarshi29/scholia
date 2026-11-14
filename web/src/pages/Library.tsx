// Library board: weak spots, source filter, problem cards and the session setup panel.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import {
  api,
  type AssistantMode,
  type CategoryStat,
  type LibrarySettings,
  type ProblemCard,
  type SessionSummary,
  type Source,
} from "../api/client";
import { ArrowRight, Check, Clock, Cloud, Cpu, FileCode, Layers, Mark, Target } from "../components/icons";
import {
  Bar,
  Button,
  Chip,
  errorText,
  Notice,
  Segmented,
  Skeleton,
  stagger,
} from "../components/ui";
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

function Header({ sessions }: { sessions: SessionSummary[] }) {
  const lastDebrief = sessions.find((s) => s.graded);
  const resume = sessions.find((s) => !s.submitted_at);
  return (
    <header className="topbar sticky top-0 z-20 flex min-h-16 items-center justify-between gap-4 px-6">
      <div className="flex items-center gap-3">
        <Mark className="size-8 drop-shadow-[0_6px_14px_rgb(92_200_232/0.45)]" />
        <span className="text-lg font-semibold tracking-tight">scholia</span>
        <span className="ml-2 hidden text-[13px] text-mute sm:inline">
          code comprehension practice
        </span>
      </div>
      <nav className="flex items-center gap-1.5">
        {resume && (
          <Link
            to={`/session/${resume.id}`}
            className="flex min-h-11 items-center gap-2 rounded-xl border border-amber/40 bg-amber/10 px-3.5 font-medium text-amber transition hover:bg-amber/20"
          >
            <span className="size-2 animate-pulse rounded-full bg-amber" />
            Resume {resume.problem_id}
          </Link>
        )}
        {lastDebrief && (
          <Link
            to={`/debrief/${lastDebrief.id}`}
            className="flex min-h-11 items-center rounded-xl px-3.5 text-mute transition hover:bg-white/5 hover:text-ink"
          >
            Last debrief
          </Link>
        )}
      </nav>
    </header>
  );
}

function WeakSpots({ stats }: { stats: CategoryStat[] }) {
  const seen = stats
    .filter((s) => s.attempts > 0)
    .sort((a, b) => (b.miss_rate ?? 0) - (a.miss_rate ?? 0));
  const graded = seen.reduce((n, s) => n + s.attempts, 0);
  return (
    <section className="surface rise px-6 py-5" style={stagger(1)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2.5 text-base font-semibold">
          <Target className="size-[18px] text-coral" />
          Your weak spots
        </h2>
        <p className="text-[13px] text-mute">
          {seen.length > 0
            ? `Share of key bugs you missed · ${plural(graded, "graded bug")}`
            : "Share of key bugs you missed"}
        </p>
      </div>
      {seen.length === 0 ? (
        <div className="mt-4 flex items-center gap-4 rounded-xl border border-dashed border-line px-4 py-3.5">
          <div className="flex shrink-0 flex-col gap-1.5" aria-hidden="true">
            <span className="block h-1.5 w-24 rounded-full bg-white/[0.07]" />
            <span className="block h-1.5 w-16 rounded-full bg-white/[0.07]" />
            <span className="block h-1.5 w-20 rounded-full bg-white/[0.07]" />
          </div>
          <p className="text-[13px] text-mute">
            Nothing graded yet. After your first debrief, the kinds of bug you miss most show up
            here, and problems that match them come first.
          </p>
        </div>
      ) : (
        <ul className="mt-4 flex flex-col gap-3">
          {seen.map((s) => {
            const rate = s.miss_rate ?? 0;
            return (
              <li key={s.category} className="grid grid-cols-[11.5rem_1fr_3rem] items-center gap-4">
                <span>{CATEGORY_LABEL[s.category]}</span>
                <Bar
                  value={rate}
                  tone={rateTone(rate)}
                  label={`${CATEGORY_LABEL[s.category]}: missed ${s.misses} of ${s.attempts}`}
                />
                <span className="text-right font-mono text-[13px] text-mute">{percent(rate)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Result({ p }: { p: ProblemCard }) {
  if (p.best_found != null && p.best_bugs != null) {
    const minutes = Math.max(1, Math.round((p.best_seconds ?? 0) / 60));
    const all = p.best_found === p.best_bugs;
    return (
      <Chip tone={all ? "green" : "amber"} dot>
        Best {p.best_found} of {plural(p.best_bugs, "bug")} · {minutes} min
      </Chip>
    );
  }
  return p.attempts > 0 ? (
    <Chip tone="amber" dot>
      Started, not finished
    </Chip>
  ) : (
    <Chip dot>Not attempted</Chip>
  );
}

function Card(props: {
  problem: ProblemCard;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const p = props.problem;
  const [repo, name] = problemTitle(p.origin_repo, p.files).split(": ");
  return (
    <button
      type="button"
      aria-pressed={props.selected}
      onClick={props.onSelect}
      style={stagger(props.index)}
      className={`surface surface-hover rise group relative flex flex-col gap-3 px-5 py-5 text-left ${
        props.selected ? "surface-selected" : ""
      }`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-mono text-[12.5px] text-mute">{p.id}</span>
        {props.selected ? (
          <span className="flex size-6 items-center justify-center rounded-full bg-cyan text-bg">
            <Check className="size-3.5" />
          </span>
        ) : (
          <Chip tone={p.source === "swebench" ? "cyan" : "amber"} mono>
            {SOURCE_LABEL[p.source]}
          </Chip>
        )}
      </span>
      <span className="min-w-0" title={p.files.join("\n")}>
        <span className="block truncate text-[12.5px] text-mute">{repo}</span>
        <span className="block truncate text-[19px] leading-snug font-semibold tracking-tight">
          {name ?? repo}
        </span>
      </span>
      <span className="flex items-center gap-2 text-[13px] text-mute">
        <FileCode className="size-4 shrink-0 opacity-70" />
        Python · {plural(p.files.length, "file")} · {p.lines} lines
      </span>
      <span className="mt-1 flex items-center justify-between gap-2">
        <Result p={p} />
        <ArrowRight className="size-4 -translate-x-1 text-cyan opacity-0 transition duration-200 group-hover:translate-x-0 group-hover:opacity-100" />
      </span>
    </button>
  );
}

function Stepper(props: {
  label: string;
  icon: ReactNode;
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
    "flex size-11 items-center justify-center rounded-xl border border-line bg-bg/70 text-lg transition enabled:hover:border-cyan/60 enabled:hover:text-cyan enabled:active:scale-95 disabled:cursor-not-allowed disabled:opacity-35";
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-3">
      <span className="flex items-center gap-2.5">
        <span className="text-mute">{props.icon}</span>
        {label}
      </span>
      <span className="flex items-center gap-1.5">
        <button
          type="button"
          className={button}
          aria-label={`Decrease ${label.toLowerCase()}`}
          disabled={disabled || value - step < min}
          onClick={() => onChange(value - step)}
        >
          −
        </button>
        <output className="w-[5.5rem] text-center font-mono text-[13.5px]" aria-live="polite">
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
    <aside className="surface rise sticky top-[5.5rem] h-fit px-6 py-6" style={stagger(2)}>
      <form
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          start.mutate();
        }}
      >
        <div key={selected?.id ?? "picked"} className="fade">
          <p className="eyebrow">Session setup</p>
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
            tone={constrained ? "cyan" : "amber"}
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
          <p key={mode} className="fade text-[13px] leading-relaxed text-mute">
            {constrained
              ? "A small local model with a tight window. You choose what it sees and spend a limited number of questions. Trains scoping and verification."
              : "A capable cloud model that sees the whole file, with no question limit. Trains checking an assistant that does not fail loudly."}
          </p>
        </div>

        <div className="flex flex-col gap-3.5 rounded-2xl border border-white/[0.05] bg-white/[0.03] px-4 py-4">
          <Stepper
            label="Context window"
            icon={<Layers />}
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
            icon={<Target />}
            value={budget}
            display={constrained ? String(budget) : "no limit"}
            step={1}
            min={0}
            max={50}
            disabled={!constrained}
            onChange={setBudget}
          />
          <div className="mt-1 flex items-center justify-between border-t border-white/[0.06] pt-3.5">
            <span className="flex items-center gap-2.5">
              <Clock className="size-4 text-mute" />
              Timer
            </span>
            <span className="font-mono text-amber">{settings.session_minutes}:00</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2.5">
              {constrained ? (
                <Cpu className="size-4 text-mute" />
              ) : (
                <Cloud className="size-4 text-mute" />
              )}
              Model
            </span>
            <span className="truncate font-mono text-[13px] text-mute">
              {info?.model} · {constrained ? "local" : "cloud"}
            </span>
          </div>
        </div>

        {start.isError && <Notice tone="coral">{errorText(start.error)}</Notice>}
        <Button
          type="submit"
          tone={constrained ? "cyan" : "amber"}
          className="group min-h-14 text-base"
          disabled={start.isPending}
        >
          {start.isPending ? "Starting…" : `Start ${settings.session_minutes}-minute session`}
          <ArrowRight className="size-[18px] transition-transform duration-200 group-hover:translate-x-1" />
        </Button>
        <p className="text-center text-[12.5px] text-mute">
          The answer key stays hidden until you submit your report.
        </p>
      </form>
    </aside>
  );
}

function LoadingBoard() {
  return (
    <div className="mx-auto grid max-w-[1500px] gap-6 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_24rem]">
      <div className="flex flex-col gap-6">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-28" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      </div>
      <Skeleton className="h-[30rem]" />
    </div>
  );
}

export default function Library() {
  const problems = useQuery({ queryKey: ["problems"], queryFn: api.problems });
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: api.sessions });
  const [source, setSource] = useState<SourceFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const header = <Header sessions={sessions.data ?? []} />;
  const failed = [problems, stats, settings].find((q) => q.isError);
  if (failed) {
    return (
      <>
        {header}
        <div className="mx-auto max-w-xl p-8">
          <Notice tone="coral">{errorText(failed.error)}</Notice>
        </div>
      </>
    );
  }
  if (!problems.data || !stats.data || !settings.data) {
    return (
      <>
        {header}
        <LoadingBoard />
      </>
    );
  }

  const all = problems.data;
  const visible = all.filter((p) => source === "all" || p.source === source);
  const selected = visible.find((p) => p.id === selectedId) ?? null;
  const count = (s: SourceFilter) => (s === "all" ? all.length : all.filter((p) => p.source === s).length);
  const filters: { value: SourceFilter; label: string }[] = [
    { value: "all", label: "All" },
    { value: "swebench", label: SOURCE_LABEL.swebench },
    { value: "bugsinpy", label: SOURCE_LABEL.bugsinpy },
  ];
  const projects = new Set(all.map((p) => p.origin_repo)).size;
  const attempted = all.filter((p) => p.attempts > 0).length;

  return (
    <>
      {header}
      <div className="mx-auto grid max-w-[1500px] gap-6 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <div className="rise">
            <h1 className="text-[2.5rem] leading-tight font-semibold tracking-tight">
              Pick a{" "}
              <span className="bg-gradient-to-r from-[#8fe3f8] to-cyan bg-clip-text text-transparent">
                problem
              </span>
            </h1>
            <p className="mt-2 max-w-2xl text-[15px] text-mute">
              Each one is a real file you have not seen, with a bug you have to find. Problems
              that match your weak spots come first.
            </p>
            <p className="mt-4 flex flex-wrap gap-2">
              <Chip>{plural(all.length, "problem")}</Chip>
              <Chip>{plural(projects, "project")}</Chip>
              <Chip tone={attempted > 0 ? "cyan" : "mute"}>{attempted} attempted</Chip>
            </p>
          </div>

          <WeakSpots stats={stats.data} />

          <div role="group" aria-label="Source" className="rise flex flex-wrap items-center gap-2" style={stagger(2)}>
            <span className="mr-2 text-[13px] text-mute">Source</span>
            {filters.map((f) => {
              const on = source === f.value;
              return (
                <button
                  key={f.value}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setSource(f.value)}
                  className={`flex min-h-11 items-center gap-2 rounded-full px-4 font-semibold transition duration-200 ${
                    on
                      ? "bg-gradient-to-b from-[#74d6f2] to-[#49b9dc] text-bg shadow-[0_8px_22px_-10px_rgb(92_200_232/0.8)]"
                      : "border border-line text-ink hover:border-mute/60 hover:bg-white/[0.04]"
                  }`}
                >
                  {f.label}
                  <span
                    className={`rounded-full px-1.5 py-0.5 font-mono text-[11.5px] leading-none ${
                      on ? "bg-bg/20" : "bg-white/[0.07] text-mute"
                    }`}
                  >
                    {count(f.value)}
                  </span>
                </button>
              );
            })}
          </div>

          {all.length === 0 ? (
            <Notice>
              No problems are published yet. Build the corpus first:{" "}
              <code className="font-mono text-ink">
                python -m corpus.build --tier 0 --source swebench --limit 20
              </code>
            </Notice>
          ) : (
            <div key={source} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {visible.map((p, i) => (
                <Card
                  key={p.id}
                  problem={p}
                  index={i + 3}
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
