// Debrief board: five stat tiles, the answer key against your report, what the assistant
// told you, judge notes and what the session changes. The server returns none of this
// until the session is submitted and graded.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  api,
  ApiError,
  type Debrief as DebriefData,
  type DebriefAudit,
  type DebriefBug,
  type DebriefFinding,
  type OutcomeStatus,
} from "../api/client";
import DiffView from "../components/DiffView";
import { ArrowLeft, ArrowRight, Chevron, Refresh } from "../components/icons";
import {
  Bar,
  Button,
  Chip,
  errorText,
  Loading,
  Notice,
  Skeleton,
  stagger,
  type Tone,
} from "../components/ui";
import {
  baseName,
  CATEGORY_LABEL,
  clock,
  lref,
  percent,
  plural,
  problemTitle,
  rateTone,
  SOURCE_LABEL,
  VERDICT_LABEL,
} from "../lib/format";
import { Link, navigate } from "../router";

type Ink = Tone | "ink";

const TEXT: Record<Ink, string> = {
  cyan: "text-cyan",
  amber: "text-amber",
  coral: "text-coral",
  green: "text-green",
  ink: "text-ink",
  mute: "text-mute",
};
const ACCENT: Record<Ink, string> = {
  cyan: "from-cyan/70",
  amber: "from-amber/70",
  coral: "from-coral/70",
  green: "from-green/70",
  ink: "from-white/25",
  mute: "from-white/15",
};

const STATUS: Record<OutcomeStatus, { label: string; tone: Tone }> = {
  found: { label: "Found · full", tone: "green" },
  partial: { label: "Found · partial", tone: "amber" },
  ungraded: { label: "Found · ungraded", tone: "mute" },
  missed: { label: "Missed", tone: "coral" },
  extra: { label: "Extra", tone: "mute" },
};

function Tile(props: { index: number; label: string; value: ReactNode; note: ReactNode; tone: Ink }) {
  return (
    <div className="surface rise relative overflow-hidden px-5 py-5" style={stagger(props.index)}>
      <span
        aria-hidden="true"
        className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r to-transparent ${ACCENT[props.tone]}`}
      />
      <p className="text-[13px] text-mute">{props.label}</p>
      <p
        className={`mt-3 font-mono text-[2.4rem] leading-none font-medium tracking-tight ${TEXT[props.tone]}`}
      >
        {props.value}
      </p>
      <p className="mt-3.5 text-[12.5px] text-mute">{props.note}</p>
    </div>
  );
}

function Card(props: {
  index: number;
  title: string;
  note?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`surface rise px-6 py-6 ${props.className ?? ""}`}
      style={stagger(props.index)}
    >
      <h2 className="text-lg font-semibold">{props.title}</h2>
      {props.note && <p className="mt-1 text-[13px] text-mute">{props.note}</p>}
      <div className="mt-4">{props.children}</div>
    </section>
  );
}

function More(props: { label: string; children: ReactNode }) {
  return (
    <details className="group mt-1">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1.5 text-[13px] text-cyan transition hover:brightness-125 [&::-webkit-details-marker]:hidden">
        <Chevron className="size-4 -rotate-90 transition-transform duration-200 group-open:rotate-0" />
        {props.label}
      </summary>
      <div className="fade pb-1">{props.children}</div>
    </details>
  );
}

const ROW =
  "grid grid-cols-[9rem_minmax(0,1fr)_auto] items-start gap-4 border-t border-white/[0.06] px-2 py-4 transition-colors hover:bg-white/[0.02]";

function BugRow({ bug }: { bug: DebriefBug }) {
  const f = bug.finding;
  const s = STATUS[bug.status];
  return (
    <li className={ROW}>
      <span className="font-mono text-[12.5px] text-mute">
        {baseName(bug.file)} {lref(bug.line_from, bug.line_to)}
      </span>
      <div className="min-w-0">
        <p className="leading-relaxed">{bug.mechanism}</p>
        <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[12.5px] text-mute">
          {CATEGORY_LABEL[bug.category]}
          {bug.assisted && <Chip tone="cyan">a question covered these lines</Chip>}
        </p>
        {f && (
          <More label="Your finding and the judge's scores">
            <div className="rounded-xl border border-line border-l-[3px] border-l-coral bg-bg/70 p-3.5">
              <p className="font-mono text-[12px] text-mute">
                You flagged {baseName(f.file)} {lref(f.line_from, f.line_to)} ·{" "}
                {CATEGORY_LABEL[f.category]}
              </p>
              <p className="mt-1.5 whitespace-pre-wrap">{f.explanation}</p>
              {f.fix && <p className="mt-1 whitespace-pre-wrap text-mute">Fix: {f.fix}</p>}
              <p className="mt-2.5 flex gap-2">
                <Chip mono>mechanism {bug.judge_mechanism ?? "–"}/2</Chip>
                <Chip mono>fix {bug.judge_fix ?? "–"}/2</Chip>
              </p>
            </div>
          </More>
        )}
      </div>
      <div className="flex flex-col items-end gap-1.5">
        <Chip tone={s.tone} dot>
          {s.label}
        </Chip>
        {bug.fix?.submitted && (
          <Chip tone={bug.fix.on_target && !bug.fix.syntax_error ? "green" : "amber"} mono>
            your fix{" "}
            {bug.fix.judge_fix !== null ? `${bug.fix.judge_fix}/2` : bug.fix.on_target ? "on the bug" : "elsewhere"}
          </Chip>
        )}
      </div>
    </li>
  );
}

function ExtraRow({ f }: { f: DebriefFinding }) {
  return (
    <li className={ROW}>
      <span className="font-mono text-[12.5px] text-mute">
        {baseName(f.file)} {lref(f.line_from, f.line_to)}
      </span>
      <div className="min-w-0">
        <p className="leading-relaxed whitespace-pre-wrap">Your note: {f.explanation}</p>
        <p className="mt-1.5 text-[12.5px] text-mute">
          Not in the answer key. It may still be a fair point; it is not counted as a bug.
        </p>
      </div>
      <Chip dot>Extra</Chip>
    </li>
  );
}

function Told({ a }: { a: DebriefAudit }) {
  const tone: Tone = a.verdict === "wrong" ? "coral" : a.verdict === "correct" ? "green" : "mute";
  const where = a.file
    ? a.line_from && a.line_to
      ? `${baseName(a.file)} ${lref(a.line_from, a.line_to)}`
      : baseName(a.file)
    : "whole problem";
  return (
    <li className="border-t border-white/[0.06] py-4">
      <p className="flex items-center justify-between gap-3">
        <span className="font-mono text-[12.5px] text-mute">
          Q{a.seq} · {where}
          {a.tokens != null ? ` · ${a.tokens.toLocaleString()} tok` : ""}
        </span>
        <Chip tone={tone} dot>
          {a.verdict ? VERDICT_LABEL[a.verdict] : "Not audited"}
        </Chip>
      </p>
      <p className="mt-2.5 leading-relaxed">
        {a.rationale || (a.verdict ? "" : "The judge gave no valid label for this answer.")}
      </p>
      {a.relied_on && (
        <p className="mt-1.5 text-coral">You relied on it: the bug on these lines got past you.</p>
      )}
      <More label="Question and answer">
        <p className="whitespace-pre-wrap text-[13px]">
          <span className="text-mute">You: </span>
          {a.question}
        </p>
        <p className="mt-2 whitespace-pre-wrap text-[13px]">
          <span className="text-mute">Assistant: </span>
          {a.reply}
        </p>
      </More>
    </li>
  );
}

function Changes({ d, index }: { d: DebriefData; index: number }) {
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const weakest = (stats.data ?? [])
    .filter((s) => (s.miss_rate ?? 0) > 0)
    .sort((a, b) => (b.miss_rate ?? 0) - (a.miss_rate ?? 0))
    .slice(0, 2)
    .map((s) => CATEGORY_LABEL[s.category].toLowerCase());
  const rate = (misses: number, attempts: number) => (attempts ? misses / attempts : null);
  return (
    <Card index={index} title="What this changes">
      {d.stats_delta.length === 0 ? (
        <p className="text-mute">No change recorded.</p>
      ) : (
        <ul className="flex flex-col gap-3.5">
          {d.stats_delta.map((r) => {
            const before = rate(r.misses_before, r.attempts_before);
            const after = rate(r.misses_after, r.attempts_after) ?? 0;
            return (
              <li key={r.category} className="grid grid-cols-[10.5rem_1fr_6.5rem] items-center gap-4">
                <span>{CATEGORY_LABEL[r.category]}</span>
                <Bar value={after} tone={rateTone(after)} />
                <span className="text-right font-mono text-[12.5px] text-mute">
                  {before === null ? "new" : percent(before).replace("%", "")} →{" "}
                  <span className="text-ink">{percent(after)}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-5 text-[13px] leading-relaxed text-mute">
        {weakest.length > 0
          ? `Next picks weight toward ${weakest.join(" bugs, then ")} bugs.`
          : "Nothing missed so far, so the next pick is an even draw over problems you have not tried."}
      </p>
      <Link
        to="/"
        className="mt-5 flex min-h-12 items-center justify-center gap-2 rounded-xl border border-cyan/60 font-semibold text-cyan transition duration-200 hover:-translate-y-px hover:border-cyan hover:bg-cyan/10"
      >
        See the next picks
      </Link>
    </Card>
  );
}

function Report({ d, id }: { d: DebriefData; id: string }) {
  const queryClient = useQueryClient();
  const regrade = useMutation({
    mutationFn: () => api.regrade(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["debrief", id] }),
  });
  const next = useMutation({
    mutationFn: () => api.createSession({ mode: d.session.mode }),
    onSuccess: (view) => navigate(`/session/${view.id}`),
  });

  const t = d.totals;
  const matched = d.bugs.filter((b) => b.status !== "missed");
  const unassisted = matched.filter((b) => !b.assisted).length;
  const needsJudge = t.ungraded > 0 || d.audits.some((a) => a.verdict == null);
  const notes = d.bugs.filter((b) => b.judge_notes).map((b) => b.judge_notes);
  const files = [...new Set(d.bugs.map((b) => b.file))];
  const allFound = matched.length === t.bugs;

  return (
    <div className="min-h-full">
      <header className="topbar sticky top-0 z-20 flex flex-wrap items-center justify-between gap-4 px-5 py-2.5">
        <div className="flex min-w-0 items-center gap-4">
          <Link
            to="/"
            className="flex min-h-11 items-center gap-1.5 rounded-xl px-2.5 text-mute transition hover:bg-white/5 hover:text-ink"
          >
            <ArrowLeft className="size-4" />
            Library
          </Link>
          <div className="min-w-0">
            <p className="eyebrow">
              Debrief · {d.problem.id} · {d.session.mode} mode
            </p>
            <h1 className="truncate text-lg leading-snug font-semibold">
              {problemTitle(d.problem.origin_repo, files)}
            </h1>
          </div>
        </div>
        <Button className="group min-h-12" disabled={next.isPending} onClick={() => next.mutate()}>
          {next.isPending ? "Picking…" : "Next problem"}
          <ArrowRight className="size-[18px] transition-transform duration-200 group-hover:translate-x-1" />
        </Button>
      </header>

      <div className="mx-auto flex max-w-[1500px] flex-col gap-5 px-6 py-7">
        {next.isError && <Notice tone="coral">{errorText(next.error)}</Notice>}
        {regrade.isError && <Notice tone="coral">{errorText(regrade.error)}</Notice>}
        {needsJudge && (
          <div className="fade flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber/35 bg-amber/10 px-4 py-2.5 text-amber">
            <p className="text-[13px]">
              {d.judge_model
                ? "The judge gave no valid answer for some items, so they are ungraded. Nothing was guessed."
                : "No judge model is configured, so scores are ungraded. Line matching and your stats are still exact."}
            </p>
            <Button
              compact
              tone="amber"
              variant="outline"
              disabled={regrade.isPending}
              onClick={() => regrade.mutate()}
            >
              <Refresh className={`size-4 ${regrade.isPending ? "animate-spin" : ""}`} />
              {regrade.isPending ? "Grading…" : "Grade again"}
            </Button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Tile
            index={0}
            label="Key bugs found"
            value={`${matched.length} of ${t.bugs}`}
            tone={allFound ? "green" : matched.length > 0 ? "amber" : "coral"}
            note={
              t.missed > 0
                ? `${t.missed} missed`
                : t.ungraded > 0
                  ? `${t.ungraded} not scored yet`
                  : "none missed"
            }
          />
          <Tile
            index={1}
            label="Found without the assistant"
            value={`${unassisted} of ${matched.length}`}
            tone="cyan"
            note={
              matched.length === 0
                ? "nothing found this time"
                : unassisted === matched.length
                  ? "no query covered those lines"
                  : "a query covered the rest"
            }
          />
          <Tile
            index={2}
            label="Wrong assistant claims"
            value={`${t.wrong_claims} of ${t.questions_used}`}
            tone="amber"
            note={`you relied on ${t.relied_on_wrong} of them`}
          />
          <Tile
            index={3}
            label="Not in the answer key"
            value={t.extra}
            tone="ink"
            note={t.extra > 0 ? "findings that matched no key bug" : "every finding matched"}
          />
          <Tile
            index={4}
            label="Time used"
            value={clock(t.seconds_used)}
            tone={d.session.overtime ? "coral" : "ink"}
            note={
              (d.session.overtime ? "overtime · " : "") +
              (t.q_budget != null
                ? `${t.questions_used} of ${t.q_budget} questions spent`
                : `${plural(t.questions_used, "question")} asked`)
            }
          />
        </div>

        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,1.25fr)]">
          <Card
            index={5}
            title="Answer key against your report"
            note="Matched by file and line overlap, then scored by the judge on mechanism and fix."
          >
            <ul>
              {d.bugs.map((b) => (
                <BugRow key={b.id} bug={b} />
              ))}
              {d.extras.map((f) => (
                <ExtraRow key={f.id} f={f} />
              ))}
            </ul>
          </Card>
          <Card
            index={6}
            title="What the assistant told you"
            note="Each answer checked against the answer key."
          >
            {d.audits.length === 0 ? (
              <p className="border-t border-white/[0.06] pt-4 text-mute">
                No answered questions in this session
                {t.refusals > 0 ? ` (${t.refusals} refused)` : ""}.
              </p>
            ) : (
              <ul>
                {d.audits.map((a) => (
                  <Told key={a.query_id} a={a} />
                ))}
              </ul>
            )}
          </Card>
        </div>

        {d.patches.length > 0 && (
          <Card
            index={7}
            title="Your fix"
            note="What you changed, as a diff from the code you were given."
          >
            <div className="flex flex-col gap-4">
              {d.bugs.map(
                (b) =>
                  b.fix?.submitted && (
                    <p key={b.id} className="text-[13px] leading-relaxed text-mute">
                      {b.fix.on_target
                        ? "Your change touches the lines of the bug."
                        : "Your change is in the bug's file but not on the bug's lines."}{" "}
                      {b.fix.syntax_error && (
                        <span className="text-coral">Syntax error: {b.fix.syntax_error}. </span>
                      )}
                      {b.fix.judge_notes}
                    </p>
                  ),
              )}
              {d.patches.map((p) => (
                <DiffView key={p.file} diff={p.diff} />
              ))}
            </div>
          </Card>
        )}

        <Card
          index={7}
          title="The fix"
          note="The upstream git diff that fixed this bug. Old line numbers on the left, new on the right."
        >
          <div className="flex flex-col gap-4">
            {d.bugs.map((b) => (
              <div key={b.id}>
                <DiffView diff={b.fix_diff} />
                {b.killing_test && (
                  <p className="mt-2 font-mono text-[12px] text-mute">
                    Test that fails before the fix: {b.killing_test}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>

        <div className="grid items-start gap-5 xl:grid-cols-2">
          <Card index={8} title="Judge notes">
            <div className="flex flex-col gap-4 leading-relaxed">
              {notes.map((n, i) => (
                <p key={i}>{n}</p>
              ))}
              {notes.length === 0 && (
                <p className="text-mute">
                  {matched.length === 0
                    ? "Nothing you flagged matched the key, so there was nothing for the judge to score."
                    : "The judge left no notes for this session."}
                </p>
              )}
              <div className="rounded-xl border border-white/[0.05] bg-white/[0.03] px-4 py-3.5">
                <p className="flex items-center justify-between gap-2 text-[13px] text-mute">
                  Design notes
                  {d.design.score != null && <Chip mono>{d.design.score} of 3</Chip>}
                </p>
                <p className="mt-1.5 whitespace-pre-wrap">
                  {d.design.notes.trim() || "You wrote none."}
                </p>
                {d.design.reference.length > 0 && (
                  <ul className="mt-2 list-disc pl-5 text-mute">
                    {d.design.reference.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
                <p className="mt-1.5 text-[12.5px] text-mute">{d.design.rationale}</p>
              </div>
            </div>
          </Card>
          <Changes d={d} index={9} />
        </div>

        <p className="fade font-mono text-[12px] text-mute/80">
          {SOURCE_LABEL[d.problem.source]} · {d.problem.upstream_id} · {d.problem.origin_repo} @{" "}
          {d.problem.commit.slice(0, 10)} · {d.problem.licence} · judge:{" "}
          {d.judge_model ?? "not configured"}
        </p>
      </div>
    </div>
  );
}

function Grading() {
  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-5 px-6 py-8">
      <Loading label="Grading your report… this page updates by itself." />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
      <Skeleton className="h-56" />
    </div>
  );
}

export default function Debrief({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const debrief = useQuery({
    queryKey: ["debrief", id],
    queryFn: () => api.debrief(id),
    // Grading runs in the background after submit: poll until it is done.
    refetchInterval: (q) =>
      q.state.error instanceof ApiError && q.state.error.code === "grading_pending" ? 2000 : false,
  });
  const regrade = useMutation({
    mutationFn: () => api.regrade(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["debrief", id] }),
  });

  if (debrief.data) return <Report d={debrief.data} id={id} />;
  if (debrief.error instanceof ApiError) {
    const code = debrief.error.code;
    if (code === "grading_pending") return <Grading />;
    if (code === "not_submitted") {
      return (
        <div className="mx-auto flex max-w-xl flex-col items-start gap-3 p-8">
          <Notice tone="amber">
            This session is still running. The debrief opens after you submit.
          </Notice>
          <Link
            to={`/session/${id}`}
            className="inline-flex min-h-11 items-center text-cyan underline"
          >
            Back to the session
          </Link>
        </div>
      );
    }
    if (code === "grading_failed") {
      return (
        <div className="mx-auto flex max-w-xl flex-col items-start gap-3 p-8">
          <Notice tone="coral">Grading failed: {debrief.error.message}</Notice>
          <Button disabled={regrade.isPending} onClick={() => regrade.mutate()}>
            {regrade.isPending ? "Grading…" : "Grade again"}
          </Button>
        </div>
      );
    }
  }
  if (debrief.isError) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <Notice tone="coral">{errorText(debrief.error)}</Notice>
      </div>
    );
  }
  return <Grading />;
}
