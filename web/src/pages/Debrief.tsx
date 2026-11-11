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
import { Button, errorText, Loading, Notice } from "../components/ui";
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

type Tone = "cyan" | "amber" | "coral" | "green" | "ink" | "mute";

const TEXT: Record<Tone, string> = {
  cyan: "text-cyan",
  amber: "text-amber",
  coral: "text-coral",
  green: "text-green",
  ink: "text-ink",
  mute: "text-mute",
};
const BAR = { coral: "bg-coral", amber: "bg-amber", green: "bg-green" } as const;

const STATUS: Record<OutcomeStatus, { label: string; tone: Tone }> = {
  found: { label: "Found · full", tone: "green" },
  partial: { label: "Found · partial", tone: "amber" },
  ungraded: { label: "Found · ungraded", tone: "mute" },
  missed: { label: "Missed", tone: "coral" },
  extra: { label: "Extra", tone: "mute" },
};

function Tile(props: { label: string; value: ReactNode; note: ReactNode; tone: Tone }) {
  return (
    <div className="rounded-xl border border-line bg-panel px-6 py-6">
      <p className="text-[13px] text-mute">{props.label}</p>
      <p className={`mt-3 font-mono text-4xl leading-none font-medium ${TEXT[props.tone]}`}>
        {props.value}
      </p>
      <p className="mt-4 text-[13px] text-mute">{props.note}</p>
    </div>
  );
}

function Card(props: { title: string; note?: string; className?: string; children: ReactNode }) {
  return (
    <section className={`rounded-xl border border-line bg-panel px-7 py-7 ${props.className ?? ""}`}>
      <h2 className="text-lg font-semibold">{props.title}</h2>
      {props.note && <p className="mt-1 text-[13px] text-mute">{props.note}</p>}
      <div className="mt-4">{props.children}</div>
    </section>
  );
}

function Pill({ status }: { status: OutcomeStatus }) {
  const s = STATUS[status];
  return (
    <span
      className={`rounded bg-bg px-2.5 py-1.5 text-[13px] leading-none font-semibold whitespace-nowrap ${TEXT[s.tone]}`}
    >
      {s.label}
    </span>
  );
}

function Diff({ text }: { text: string }) {
  return (
    <pre className="mt-2 overflow-x-auto rounded-md border border-line bg-bg p-3 font-mono text-[12px] leading-5">
      {text.split("\n").map((line, i) => {
        const tone =
          line.startsWith("+") && !line.startsWith("+++")
            ? "text-green"
            : line.startsWith("-") && !line.startsWith("---")
              ? "text-coral"
              : line.startsWith("@@")
                ? "text-cyan"
                : "text-mute";
        return (
          <span key={i} className={`block ${tone}`}>
            {line || " "}
          </span>
        );
      })}
    </pre>
  );
}

const SUMMARY = "flex min-h-11 cursor-pointer items-center text-[13px] text-cyan";

function BugRow({ bug }: { bug: DebriefBug }) {
  const f = bug.finding;
  return (
    <li className="grid grid-cols-[9.5rem_minmax(0,1fr)_auto] items-start gap-4 border-t border-line py-5">
      <span className="font-mono text-[13px] text-mute">
        {baseName(bug.file)} {lref(bug.line_from, bug.line_to)}
      </span>
      <div className="min-w-0">
        <p>{bug.mechanism}</p>
        <p className="mt-1 text-[13px] text-mute">
          {CATEGORY_LABEL[bug.category]}
          {bug.assisted ? " · a question covered these lines" : ""}
        </p>
        <details>
          <summary className={SUMMARY}>
            {f ? "Your finding, the judge's scores and the reference fix" : "Reference fix"}
          </summary>
          {f && (
            <div className="rounded-md border border-line border-l-[3px] border-l-coral bg-bg p-3">
              <p className="font-mono text-[12px] text-mute">
                You flagged {baseName(f.file)} {lref(f.line_from, f.line_to)} ·{" "}
                {CATEGORY_LABEL[f.category]}
              </p>
              <p className="mt-1 whitespace-pre-wrap">{f.explanation}</p>
              {f.fix && <p className="mt-1 whitespace-pre-wrap text-mute">Fix: {f.fix}</p>}
              <p className="mt-2 font-mono text-[13px] text-mute">
                judge: mechanism {bug.judge_mechanism ?? "–"}/2 · fix {bug.judge_fix ?? "–"}/2
              </p>
            </div>
          )}
          <Diff text={bug.fix_diff} />
          {bug.killing_test && (
            <p className="mt-2 font-mono text-[12px] text-mute">Failing test: {bug.killing_test}</p>
          )}
        </details>
      </div>
      <Pill status={bug.status} />
    </li>
  );
}

function ExtraRow({ f }: { f: DebriefFinding }) {
  return (
    <li className="grid grid-cols-[9.5rem_minmax(0,1fr)_auto] items-start gap-4 border-t border-line py-5">
      <span className="font-mono text-[13px] text-mute">
        {baseName(f.file)} {lref(f.line_from, f.line_to)}
      </span>
      <div className="min-w-0">
        <p className="whitespace-pre-wrap">Your note: {f.explanation}</p>
        <p className="mt-1 text-[13px] text-mute">
          Not in the answer key. It may still be a fair point; it is not counted as a bug.
        </p>
      </div>
      <Pill status="extra" />
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
    <li className="border-t border-line py-5">
      <p className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-[13px] text-mute">
          Q{a.seq} · {where}
          {a.tokens != null ? ` · ${a.tokens.toLocaleString()} tok` : ""}
        </span>
        <span className={`text-[13px] font-semibold ${TEXT[tone]}`}>
          {a.verdict ? VERDICT_LABEL[a.verdict] : "Not audited"}
        </span>
      </p>
      <p className="mt-3">
        {a.rationale || (a.verdict ? "" : "The judge gave no valid label for this answer.")}
      </p>
      {a.relied_on && (
        <p className="mt-1 text-coral">You relied on it: the bug on these lines got past you.</p>
      )}
      <details>
        <summary className={SUMMARY}>Question and answer</summary>
        <p className="whitespace-pre-wrap text-[13px]">
          <span className="text-mute">You: </span>
          {a.question}
        </p>
        <p className="mt-2 whitespace-pre-wrap text-[13px]">
          <span className="text-mute">Assistant: </span>
          {a.reply}
        </p>
      </details>
    </li>
  );
}

function Changes({ d }: { d: DebriefData }) {
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const weakest = (stats.data ?? [])
    .filter((s) => (s.miss_rate ?? 0) > 0)
    .sort((a, b) => (b.miss_rate ?? 0) - (a.miss_rate ?? 0))
    .slice(0, 2)
    .map((s) => CATEGORY_LABEL[s.category].toLowerCase());
  const rate = (misses: number, attempts: number) => (attempts ? misses / attempts : null);
  return (
    <Card title="What this changes">
      {d.stats_delta.length === 0 ? (
        <p className="text-mute">No change recorded.</p>
      ) : (
        <ul className="flex flex-col gap-3.5">
          {d.stats_delta.map((r) => {
            const before = rate(r.misses_before, r.attempts_before);
            const after = rate(r.misses_after, r.attempts_after) ?? 0;
            return (
              <li key={r.category} className="grid grid-cols-[11rem_1fr_6.5rem] items-center gap-4">
                <span>{CATEGORY_LABEL[r.category]}</span>
                <span className="h-1.5 overflow-hidden rounded-full bg-raised" aria-hidden="true">
                  <span
                    className={`block h-full rounded-full ${BAR[rateTone(after)]}`}
                    style={{ width: `${Math.max(after * 100, after > 0 ? 2 : 0)}%` }}
                  />
                </span>
                <span className="text-right font-mono text-[13px] text-mute">
                  {before === null ? "new" : percent(before).replace("%", "")} → {percent(after)}
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
        className="mt-5 flex min-h-12 items-center justify-center rounded-lg border border-cyan font-semibold text-cyan hover:bg-cyan/10"
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

  return (
    <div className="min-h-full">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line bg-panel px-6 py-3">
        <div className="flex min-w-0 items-center gap-6">
          <Link to="/" className="flex min-h-11 items-center text-mute hover:text-ink">
            ← Library
          </Link>
          <div className="min-w-0">
            <p className="text-[12px] tracking-widest text-mute uppercase">
              Debrief · {d.problem.id} · {d.session.mode} mode
            </p>
            <h1 className="truncate text-lg font-semibold">
              {problemTitle(d.problem.origin_repo, files)}
            </h1>
          </div>
        </div>
        <Button
          className="min-h-12 px-5 text-base font-semibold"
          disabled={next.isPending}
          onClick={() => next.mutate()}
        >
          {next.isPending ? "Picking…" : "Next problem →"}
        </Button>
      </header>

      <div className="mx-auto flex max-w-[1500px] flex-col gap-6 px-6 py-7">
        {next.isError && <Notice tone="coral">{errorText(next.error)}</Notice>}
        {regrade.isError && <Notice tone="coral">{errorText(regrade.error)}</Notice>}
        {needsJudge && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber/40 bg-amber/10 px-4 py-2 text-amber">
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
              {regrade.isPending ? "Grading…" : "Grade again"}
            </Button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Tile
            label="Key bugs found"
            value={`${matched.length} of ${t.bugs}`}
            tone="green"
            note={
              t.missed > 0
                ? `${t.missed} missed`
                : t.ungraded > 0
                  ? `${t.ungraded} not scored yet`
                  : "none missed"
            }
          />
          <Tile
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
            label="Wrong assistant claims"
            value={`${t.wrong_claims} of ${t.questions_used}`}
            tone="amber"
            note={`you relied on ${t.relied_on_wrong} of them`}
          />
          <Tile
            label="Not in the answer key"
            value={t.extra}
            tone="ink"
            note={t.extra > 0 ? "findings that matched no key bug" : "every finding matched"}
          />
          <Tile
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

        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
          <Card
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
          <Card title="What the assistant told you" note="Each answer checked against the answer key.">
            {d.audits.length === 0 ? (
              <p className="border-t border-line pt-5 text-mute">
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

        <div className="grid items-start gap-6 xl:grid-cols-2">
          <Card title="Judge notes">
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
              <div className="border-t border-line pt-4">
                <p className="text-[13px] text-mute">
                  Design notes{d.design.score != null ? ` · ${d.design.score} of 3` : ""}
                </p>
                <p className="mt-1 whitespace-pre-wrap">
                  {d.design.notes.trim() || "You wrote none."}
                </p>
                {d.design.reference.length > 0 && (
                  <ul className="mt-2 list-disc pl-5 text-mute">
                    {d.design.reference.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
                <p className="mt-1 text-[13px] text-mute">{d.design.rationale}</p>
              </div>
            </div>
          </Card>
          <Changes d={d} />
        </div>

        <p className="font-mono text-[12px] text-mute">
          {SOURCE_LABEL[d.problem.source]} · {d.problem.upstream_id} · {d.problem.origin_repo} @{" "}
          {d.problem.commit.slice(0, 10)} · {d.problem.licence} · judge:{" "}
          {d.judge_model ?? "not configured"}
        </p>
      </div>
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
    if (code === "grading_pending") {
      return <Loading label="Grading your report… this page updates by itself." />;
    }
    if (code === "not_submitted") {
      return (
        <div className="flex flex-col items-start gap-3 p-6">
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
        <div className="flex flex-col items-start gap-3 p-6">
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
      <div className="p-6">
        <Notice tone="coral">{errorText(debrief.error)}</Notice>
      </div>
    );
  }
  return <Loading label="Opening the debrief…" />;
}
