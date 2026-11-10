// Library: weak-spot bars, source filters, problem cards and the session setup panel.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  api,
  type AssistantMode,
  type CategoryStat,
  type LibrarySettings,
  type ProblemCard,
  type SessionSummary,
  type Source,
} from "../api/client";
import { Badge, Button, errorText, INPUT, Loading, Notice, Panel } from "../components/ui";
import { CATEGORY_LABEL, percent, shortDate, SOURCE_LABEL } from "../lib/format";
import { Link, navigate } from "../router";

type SourceFilter = Source | "all";

function WeakSpots({ stats }: { stats: CategoryStat[] }) {
  const attempted = stats.some((s) => s.attempts > 0);
  return (
    <Panel title="Weak spots" aside={<span className="text-[12px] text-mute">miss rate</span>}>
      {!attempted && (
        <p className="mb-3 text-[13px] text-mute">
          No sessions graded yet. After each debrief, the categories you miss most show up here
          and get picked more often.
        </p>
      )}
      <ul className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
        {stats.map((s) => {
          const rate = s.miss_rate ?? 0;
          return (
            <li key={s.category} className="grid grid-cols-[9.5rem_1fr_5.5rem] items-center gap-3">
              <span className="truncate text-[13px]">{CATEGORY_LABEL[s.category]}</span>
              <span
                className="h-2 overflow-hidden rounded-full bg-raised"
                role="img"
                aria-label={
                  s.attempts > 0
                    ? `${CATEGORY_LABEL[s.category]}: missed ${s.misses} of ${s.attempts}`
                    : `${CATEGORY_LABEL[s.category]}: not attempted yet`
                }
              >
                <span
                  className="block h-full rounded-full bg-coral"
                  style={{ width: `${Math.round(rate * 100)}%` }}
                />
              </span>
              <span className="text-right font-mono text-[12px] text-mute">
                {s.attempts > 0 ? `${percent(s.miss_rate)} · ${s.misses}/${s.attempts}` : "no data"}
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function Card(props: { problem: ProblemCard; selected: boolean; onSelect: () => void }) {
  const p = props.problem;
  return (
    <button
      type="button"
      aria-pressed={props.selected}
      onClick={props.onSelect}
      className={`flex min-h-11 flex-col gap-2 rounded-lg border p-3 text-left transition ${
        props.selected ? "border-cyan bg-cyan/5" : "border-line bg-panel hover:border-mute/60"
      }`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-mono font-medium">{p.id}</span>
        <Badge tone={p.source === "swebench" ? "cyan" : "amber"}>{SOURCE_LABEL[p.source]}</Badge>
      </span>
      <span className="truncate text-[13px] text-mute">{p.origin_repo}</span>
      <span className="truncate font-mono text-[12px]" title={p.files.join("\n")}>
        {p.files.join(", ")}
      </span>
      <span className="flex items-center justify-between font-mono text-[12px] text-mute">
        <span>{p.lines} lines</span>
        <span>{p.attempts === 0 ? "not attempted" : `${p.attempts}× · ${shortDate(p.last_attempt_at)}`}</span>
      </span>
    </button>
  );
}

function Setup(props: { settings: LibrarySettings; selected: ProblemCard | null; source: SourceFilter }) {
  const { settings, selected, source } = props;
  const [mode, setMode] = useState<AssistantMode>("constrained");
  const [ctxCap, setCtxCap] = useState(String(settings.default_ctx_cap));
  const [budget, setBudget] = useState(String(settings.default_q_budget));
  const start = useMutation({
    mutationFn: () =>
      api.createSession({
        problem_id: selected?.id ?? null,
        source: selected || source === "all" ? null : source,
        mode,
        ctx_cap: Number(ctxCap),
        q_budget: Number(budget),
      }),
    onSuccess: (view) => navigate(`/session/${view.id}`),
  });
  const capOk = Number.isInteger(Number(ctxCap)) && Number(ctxCap) > 0;
  const budgetOk = Number.isInteger(Number(budget)) && Number(budget) >= 0;
  const constrained = mode === "constrained";

  return (
    <Panel title="Session setup">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          start.mutate();
        }}
      >
        <div>
          <p className="text-[12px] text-mute uppercase">Problem</p>
          <p className="mt-1">
            {selected ? (
              <>
                <span className="font-mono font-medium">{selected.id}</span>
                <span className="text-mute"> · {selected.origin_repo}</span>
              </>
            ) : (
              <>
                Picked for you
                <span className="text-mute">
                  {" "}
                  · weighted by your weak spots
                  {source !== "all" && `, from ${SOURCE_LABEL[source]}`}
                </span>
              </>
            )}
          </p>
        </div>

        <fieldset>
          <legend className="text-[12px] text-mute uppercase">Assistant</legend>
          <div className="mt-1 flex flex-col gap-2">
            {settings.modes.map((m) => {
              const realistic = m.mode === "realistic";
              const checked = mode === m.mode;
              return (
                <label
                  key={m.mode}
                  className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-md border px-3 py-2 ${
                    checked ? (realistic ? "border-amber bg-amber/5" : "border-cyan bg-cyan/5") : "border-line"
                  } ${m.available ? "" : "cursor-not-allowed opacity-50"}`}
                >
                  <input
                    type="radio"
                    name="mode"
                    className="mt-1 accent-current"
                    checked={checked}
                    disabled={!m.available}
                    onChange={() => setMode(m.mode)}
                  />
                  <span>
                    <span className={`font-medium ${realistic ? "text-amber" : "text-cyan"}`}>
                      {realistic ? "Realistic" : "Constrained"}
                    </span>
                    <span className="block text-[13px] text-mute">
                      {realistic
                        ? m.available
                          ? `${m.model}: sees the whole file, no budget.`
                          : "Needs a Gemini key and model in .env."
                        : `${m.model}: sees only the lines you select.`}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-mute uppercase">Context cap (tokens)</span>
            <input
              className={`${INPUT} font-mono`}
              inputMode="numeric"
              value={ctxCap}
              disabled={!constrained}
              aria-invalid={!capOk}
              onChange={(e) => setCtxCap(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-mute uppercase">Question budget</span>
            <input
              className={`${INPUT} font-mono`}
              inputMode="numeric"
              value={budget}
              disabled={!constrained}
              aria-invalid={!budgetOk}
              onChange={(e) => setBudget(e.target.value)}
            />
          </label>
        </div>

        <p className="text-[13px] text-mute">
          {settings.session_minutes} minutes on the server clock. You can submit late; it is
          flagged as overtime.
        </p>
        {start.isError && <Notice tone="coral">{errorText(start.error)}</Notice>}
        <Button
          type="submit"
          tone={constrained ? "cyan" : "amber"}
          disabled={start.isPending || !capOk || !budgetOk}
        >
          {start.isPending ? "Starting…" : "Start session"}
        </Button>
      </form>
    </Panel>
  );
}

function Recent({ sessions }: { sessions: SessionSummary[] }) {
  if (sessions.length === 0) return null;
  return (
    <Panel title="Recent sessions" bodyClassName="p-2">
      <ul>
        {sessions.slice(0, 8).map((s) => {
          const live = !s.submitted_at;
          return (
            <li key={s.id}>
              <Link
                to={live ? `/session/${s.id}` : `/debrief/${s.id}`}
                className="flex min-h-11 items-center justify-between gap-3 rounded-md px-2 hover:bg-raised"
              >
                <span>
                  <span className="font-mono">{s.problem_id}</span>
                  <span className="text-[13px] text-mute"> · {shortDate(s.started_at)}</span>
                </span>
                {live ? (
                  <Badge tone="amber">Resume</Badge>
                ) : s.graded ? (
                  <Badge tone="green">Debrief</Badge>
                ) : (
                  <Badge tone={s.grade_error ? "coral" : "mute"}>
                    {s.grade_error ? "Grading failed" : "Grading"}
                  </Badge>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

export default function Library() {
  const problems = useQuery({ queryKey: ["problems"], queryFn: api.problems });
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: api.sessions });
  const [source, setSource] = useState<SourceFilter>("all");
  const [freshOnly, setFreshOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const failed = [problems, stats, settings].find((q) => q.isError);
  if (failed) {
    return (
      <div className="p-6">
        <Notice tone="coral">{errorText(failed.error)}</Notice>
      </div>
    );
  }
  if (!problems.data || !stats.data || !settings.data) return <Loading />;

  const visible = problems.data.filter(
    (p) => (source === "all" || p.source === source) && (!freshOnly || p.attempts === 0),
  );
  const selected = visible.find((p) => p.id === selectedId) ?? null;
  const filters: { value: SourceFilter; label: string }[] = [
    { value: "all", label: "All sources" },
    { value: "swebench", label: SOURCE_LABEL.swebench },
    { value: "bugsinpy", label: SOURCE_LABEL.bugsinpy },
  ];

  return (
    <div className="mx-auto grid max-w-[1400px] gap-4 p-4 lg:grid-cols-[1fr_22rem]">
      <div className="flex min-w-0 flex-col gap-4">
        <WeakSpots stats={stats.data} />
        <Panel
          title={`Problems · ${visible.length}`}
          aside={
            <div className="flex flex-wrap items-center gap-2 py-1.5">
              <div role="group" aria-label="Source" className="flex gap-1">
                {filters.map((f) => (
                  <button
                    key={f.value}
                    type="button"
                    aria-pressed={source === f.value}
                    onClick={() => setSource(f.value)}
                    className={`min-h-11 rounded-md border px-3 text-[13px] ${
                      source === f.value
                        ? "border-cyan bg-cyan/10 text-cyan"
                        : "border-line text-mute hover:text-ink"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <label className="flex min-h-11 cursor-pointer items-center gap-2 px-1 text-[13px] text-mute">
                <input
                  type="checkbox"
                  className="size-4 accent-cyan"
                  checked={freshOnly}
                  onChange={(e) => setFreshOnly(e.target.checked)}
                />
                Not attempted
              </label>
            </div>
          }
        >
          {problems.data.length === 0 ? (
            <p className="text-mute">
              No problems are published yet. Build the corpus first:{" "}
              <code className="font-mono text-ink">
                uv run python -m corpus.build --tier 0 --source swebench --limit 20
              </code>
            </p>
          ) : visible.length === 0 ? (
            <p className="text-mute">No problems match these filters.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
        </Panel>
      </div>
      <aside className="flex flex-col gap-4">
        <Setup settings={settings.data} selected={selected} source={source} />
        <Recent sessions={sessions.data ?? []} />
      </aside>
    </div>
  );
}
