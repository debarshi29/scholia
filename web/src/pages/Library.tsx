// Library (home): a spotlight row that reshuffles, weak spots, and every problem as a
// compact tile, grouped by bug category or by project, with the session setup panel.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import {
  api,
  type AssistantMode,
  type BugCategory,
  type CategoryStat,
  type LibrarySettings,
  type ProblemCard,
  type SessionSummary,
  type Source,
} from "../api/client";
import {
  ArrowRight,
  Clock,
  Cloud,
  Cpu,
  Layers,
  Mark,
  Refresh,
  Target,
} from "../components/icons";
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
  CATEGORIES,
  CATEGORY_LABEL,
  percent,
  plural,
  problemTitle,
  rateTone,
  SOURCE_LABEL,
} from "../lib/format";
import { Link, navigate } from "../router";

type SourceFilter = Source | "all";
type Grouping = "category" | "project";

const SHUFFLE_SECONDS = 12;
const SPOTLIGHT = 3;

function Header({ sessions }: { sessions: SessionSummary[] }) {
  const lastDebrief = sessions.find((s) => s.graded);
  const resume = sessions.find((s) => !s.submitted_at);
  return (
    <header className="topbar sticky top-0 z-20 flex min-h-12 items-center justify-between gap-4 px-5">
      <div className="flex items-center gap-3">
        <Mark className="size-6" />
        <span className="text-[15px] font-semibold tracking-tight">scholia</span>
        <span className="ml-2 hidden text-[13px] text-mute sm:inline">
          code comprehension practice
        </span>
      </div>
      <nav className="flex items-center gap-1.5">
        {resume && (
          <Link
            to={`/session/${resume.id}`}
            className="flex min-h-9 items-center gap-2 rounded-md border border-amber/40 bg-amber/10 px-3.5 font-medium text-amber transition hover:bg-amber/20"
          >
            <span className="size-2 animate-pulse rounded-full bg-amber" />
            Resume {resume.problem_id}
          </Link>
        )}
        {lastDebrief && (
          <Link
            to={`/debrief/${lastDebrief.id}`}
            className="flex min-h-9 items-center rounded-md px-3.5 text-mute transition hover:bg-white/5 hover:text-ink"
          >
            Last debrief
          </Link>
        )}
      </nav>
    </header>
  );
}

// ---- small helpers ----

const AVATAR = [
  "bg-cyan/15 text-cyan",
  "bg-amber/15 text-amber",
  "bg-green/15 text-green",
  "bg-coral/15 text-coral",
  "bg-[#b79cf2]/15 text-[#b79cf2]",
];

function repoName(p: ProblemCard): string {
  return p.origin_repo.split("/").pop() ?? p.origin_repo;
}

function fileName(p: ProblemCard): string {
  return problemTitle(p.origin_repo, p.files).split(": ")[1] ?? repoName(p);
}

/** A stable colour per project, so the same repo looks the same everywhere. */
function avatarTone(repo: string): string {
  let h = 0;
  for (const ch of repo) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR[h % AVATAR.length] ?? AVATAR[0]!;
}

function Avatar({ p, large }: { p: ProblemCard; large?: boolean }) {
  const name = repoName(p).replace(/[^a-zA-Z]/g, "");
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-md font-mono font-semibold uppercase ${
        large ? "size-8 text-sm" : "size-8 text-[12px]"
      } ${avatarTone(p.origin_repo)}`}
    >
      {name.slice(0, 2) || "py"}
    </span>
  );
}

function status(p: ProblemCard): { text: string; dot: string; tone: string } {
  if (p.best_found != null && p.best_bugs != null) {
    const minutes = Math.max(1, Math.round((p.best_seconds ?? 0) / 60));
    const all = p.best_found === p.best_bugs;
    return {
      text: `${p.best_found}/${p.best_bugs} · ${minutes} min`,
      dot: all ? "bg-green" : "bg-amber",
      tone: all ? "text-green" : "text-amber",
    };
  }
  return p.attempts > 0
    ? { text: "in progress", dot: "bg-amber", tone: "text-amber" }
    : { text: "new", dot: "bg-mute/50", tone: "text-mute" };
}

/** Deterministic pseudo-random order for a given tick (pure, so safe during render). */
function shuffled<T>(items: T[], seed: number): T[] {
  let a = (seed * 2654435761 + 0x9e3779b9) >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(next() * (i + 1));
    [out[i], out[j]] = [out[j]!, out[i]!];
  }
  return out;
}

// ---- spotlight ----

function Spotlight(props: {
  problems: ProblemCard[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [tick, setTick] = useState(1);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setTick((n) => n + 1), SHUFFLE_SECONDS * 1000);
    return () => clearInterval(t);
  }, [paused, tick]);

  // Prefer problems not tried yet; fall back to everything.
  const fresh = props.problems.filter((p) => p.attempts === 0);
  const pool = fresh.length >= SPOTLIGHT ? fresh : props.problems;
  const picks = shuffled(pool, tick).slice(0, SPOTLIGHT);
  if (picks.length === 0) return null;

  return (
    <section
      aria-label="Spotlight"
      className="rise"
      style={stagger(1)}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-3 text-base font-semibold">
          Spotlight
          <span className="text-[12.5px] font-normal text-mute">
            {paused ? "paused while you look" : `random picks, reshuffled every ${SHUFFLE_SECONDS} s`}
          </span>
        </h2>
        <div className="flex items-center gap-3">
          <span className="bar-track hidden h-1 w-28 sm:block" aria-hidden="true">
            <span
              key={tick}
              className="countdown"
              style={{
                animationDuration: `${SHUFFLE_SECONDS}s`,
                animationPlayState: paused ? "paused" : "running",
              }}
            />
          </span>
          <button
            type="button"
            onClick={() => setTick((n) => n + 1)}
            className="flex min-h-9 items-center gap-2 rounded-md border border-line px-3.5 text-[13px] font-medium text-mute transition hover:border-cyan/50 hover:text-cyan"
          >
            <Refresh className="size-4" />
            Shuffle
          </button>
        </div>
      </div>
      <div key={tick} className="grid gap-4 md:grid-cols-3">
        {picks.map((p, i) => {
          const on = p.id === props.selectedId;
          return (
            <button
              key={p.id}
              type="button"
              aria-pressed={on}
              onClick={() => props.onSelect(p.id)}
              style={stagger(i)}
              className={`surface surface-hover rise group relative flex flex-col gap-2.5 overflow-hidden px-3.5 py-3 text-left ${
                on ? "surface-selected" : ""
              }`}
            >
              <span className="flex items-center gap-3.5">
                <Avatar p={p} large />
                <span className="min-w-0">
                  <span className="block truncate text-[12.5px] text-mute">{repoName(p)}</span>
                  <span className="block truncate text-[15px] leading-tight font-semibold">
                    {fileName(p)}
                  </span>
                </span>
              </span>
              <span className="flex items-center justify-between gap-2 text-[12.5px] text-mute">
                <span className="font-mono">
                  {p.id} · {p.lines} lines
                </span>
                <span className="flex items-center gap-1.5 font-medium text-cyan opacity-0 transition duration-200 group-hover:opacity-100">
                  {on ? "Selected" : "Select"}
                  <ArrowRight className="size-4" />
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

// ---- weak spots ----

function WeakSpots({ stats }: { stats: CategoryStat[] }) {
  const seen = stats
    .filter((s) => s.attempts > 0)
    .sort((a, b) => (b.miss_rate ?? 0) - (a.miss_rate ?? 0));
  if (seen.length === 0) return null;
  const graded = seen.reduce((n, s) => n + s.attempts, 0);
  return (
    <section className="surface rise px-4 py-4" style={stagger(2)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2.5 text-base font-semibold">
          <Target className="size-[18px] text-coral" />
          Your weak spots
        </h2>
        <p className="text-[13px] text-mute">
          Share of key bugs you missed · {plural(graded, "graded bug")}
        </p>
      </div>
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
    </section>
  );
}

// ---- tiles and groups ----

function Tile(props: { problem: ProblemCard; selected: boolean; onSelect: () => void }) {
  const p = props.problem;
  const s = status(p);
  return (
    <button
      type="button"
      aria-pressed={props.selected}
      onClick={props.onSelect}
      title={`${p.id} · ${p.files.join(", ")}`}
      className={`tile flex min-h-[3.25rem] items-center gap-2.5 px-2.5 py-2 text-left ${
        props.selected ? "tile-selected" : ""
      }`}
    >
      <Avatar p={p} />
      <span className="min-w-0 flex-1">
        <span className="block truncate leading-snug font-semibold">{fileName(p)}</span>
        <span className="block truncate text-[12.5px] text-mute">
          {repoName(p)} · {p.lines} lines
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1 font-mono text-[11.5px]">
        <span className="text-mute/80">{p.id}</span>
        <span className={`flex items-center gap-1.5 ${s.tone}`}>
          <span className={`size-1.5 rounded-full ${s.dot}`} />
          {s.text}
        </span>
      </span>
    </button>
  );
}

interface Group {
  key: string;
  label: string;
  note: ReactNode;
  problems: ProblemCard[];
}

function groupProblems(problems: ProblemCard[], by: Grouping, stats: CategoryStat[]): Group[] {
  if (by === "project") {
    const map = new Map<string, ProblemCard[]>();
    for (const p of problems) map.set(repoName(p), [...(map.get(repoName(p)) ?? []), p]);
    return [...map.entries()]
      .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
      .map(([name, list]) => ({ key: name, label: name, note: null, problems: list }));
  }
  const rate = new Map(stats.map((s) => [s.category, s]));
  const groups: Group[] = [];
  for (const category of CATEGORIES) {
    const list = problems.filter((p) => p.categories.includes(category as BugCategory));
    if (list.length === 0) continue;
    const s = rate.get(category);
    groups.push({
      key: category,
      label: CATEGORY_LABEL[category],
      note:
        s && s.attempts > 0 ? (
          <Chip tone={rateTone(s.miss_rate ?? 0)} dot>
            you miss {percent(s.miss_rate)}
          </Chip>
        ) : null,
      problems: list,
    });
  }
  // Weakest categories first, then the biggest groups.
  const missed = (g: Group) => rate.get(g.key as BugCategory)?.miss_rate ?? -1;
  return groups.sort((a, b) => missed(b) - missed(a) || b.problems.length - a.problems.length);
}

// ---- setup panel ----

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
    "flex size-8 items-center justify-center rounded-md border border-line bg-bg/70 text-base transition enabled:hover:border-cyan/60 enabled:hover:text-cyan enabled:active:scale-95 disabled:cursor-not-allowed disabled:opacity-35";
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-3">
      <span className="flex items-center gap-2.5">
        <span className="text-mute">{props.icon}</span>
        <span className="whitespace-nowrap">{label}</span>
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
        <output className="w-[5.5rem] text-center font-mono text-[13px] whitespace-nowrap" aria-live="polite">
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
    <aside className="surface rise sticky top-[4.5rem] h-fit px-4 py-4" style={stagger(2)}>
      <form
        className="flex flex-col gap-4"
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
              : `Weighted by your weak spots${source === "all" ? "" : `, from ${SOURCE_LABEL[source]}`}. Or choose a problem.`}
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

        <div className="flex flex-col gap-3 rounded-lg border border-line px-3 py-3">
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
          className="group min-h-10 text-sm"
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
    <div className="mx-auto grid max-w-[1500px] gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_21rem]">
      <div className="flex flex-col gap-6">
        <Skeleton className="h-10 w-72" />
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 9 }, (_, i) => (
            <Skeleton key={i} className="h-[4.25rem]" />
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
  const [grouping, setGrouping] = useState<Grouping>("category");
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
  const selected = all.find((p) => p.id === selectedId) ?? null;
  const toggle = (id: string) => setSelectedId((current) => (current === id ? null : id));
  const count = (s: SourceFilter) =>
    s === "all" ? all.length : all.filter((p) => p.source === s).length;
  const filters: { value: SourceFilter; label: string }[] = [
    { value: "all", label: "All" },
    { value: "swebench", label: SOURCE_LABEL.swebench },
    { value: "bugsinpy", label: SOURCE_LABEL.bugsinpy },
  ];
  const projects = new Set(all.map((p) => p.origin_repo)).size;
  const attempted = all.filter((p) => p.attempts > 0).length;
  const groups = groupProblems(visible, grouping, stats.data);

  return (
    <>
      {header}
      <div className="mx-auto grid max-w-[1500px] gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="flex min-w-0 flex-col gap-5">
          <div className="rise flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl leading-tight font-semibold tracking-tight">
                Pick a{" "}
                <span className="text-cyan">
                  problem
                </span>
              </h1>
              <p className="mt-1 max-w-2xl text-[13px] text-mute">
                Each one is a real file you have not seen, with a bug you have to find.
              </p>
            </div>
            <p className="flex flex-wrap gap-2">
              <Chip>{plural(all.length, "problem")}</Chip>
              <Chip>{plural(projects, "project")}</Chip>
              <Chip tone={attempted > 0 ? "cyan" : "mute"}>{attempted} attempted</Chip>
            </p>
          </div>

          {all.length === 0 ? (
            <Notice>
              No problems are published yet. Build the corpus first:{" "}
              <code className="font-mono text-ink">
                python -m corpus.build --tier 0 --source swebench --limit 20
              </code>
            </Notice>
          ) : (
            <>
              <Spotlight problems={all} selectedId={selectedId} onSelect={toggle} />
              <WeakSpots stats={stats.data} />

              <section className="rise flex flex-col gap-4" style={stagger(3)}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div role="group" aria-label="Source" className="flex flex-wrap items-center gap-2">
                    {filters.map((f) => {
                      const on = source === f.value;
                      return (
                        <button
                          key={f.value}
                          type="button"
                          aria-pressed={on}
                          onClick={() => setSource(f.value)}
                          className={`flex min-h-9 items-center gap-2 rounded-md px-3 text-[13px] font-medium transition duration-150 ${
                            on
                              ? "bg-gradient-to-b from-[#74d6f2] to-[#49b9dc] text-bg "
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
                  <div className="flex items-center gap-3">
                    <span className="text-[13px] text-mute">Group by</span>
                    <div className="w-60">
                      <Segmented
                        label="Group problems by"
                        value={grouping}
                        onChange={setGrouping}
                        compact
                        options={[
                          { value: "category", label: "Bug category" },
                          { value: "project", label: "Project" },
                        ]}
                      />
                    </div>
                  </div>
                </div>

                <div key={`${source}-${grouping}`} className="fade flex flex-col gap-6">
                  {groups.map((g) => (
                    <section key={g.key} aria-label={g.label}>
                      <h3 className="mb-2.5 flex items-center gap-3">
                        <span className="font-semibold">{g.label}</span>
                        <span className="rounded-full bg-white/[0.07] px-2 py-0.5 font-mono text-[11.5px] leading-none text-mute">
                          {g.problems.length}
                        </span>
                        {g.note}
                        <span className="h-px flex-1 bg-white/[0.06]" aria-hidden="true" />
                      </h3>
                      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                        {g.problems.map((p) => (
                          <Tile
                            key={p.id}
                            problem={p}
                            selected={p.id === selectedId}
                            onSelect={() => toggle(p.id)}
                          />
                        ))}
                      </div>
                    </section>
                  ))}
                  {groups.length === 0 && <p className="text-mute">No problems from this source.</p>}
                </div>
              </section>
            </>
          )}
        </div>
        <Setup settings={settings.data} selected={selected} source={source} />
      </div>
    </>
  );
}
