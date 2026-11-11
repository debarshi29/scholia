// Debrief: stat tiles, the answer key against your findings, the assistant claim audit,
// judge notes and the change in category stats. The server returns none of this until
// the session is submitted and graded.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import {
  api,
  ApiError,
  type Debrief as DebriefData,
  type DebriefAudit,
  type DebriefBug,
  type DebriefFinding,
  type OutcomeStatus,
  type StatDelta,
} from "../api/client";
import CodeViewer from "../components/CodeViewer";
import { Badge, Button, errorText, Loading, Notice, Panel } from "../components/ui";
import {
  baseName,
  CATEGORY_LABEL,
  clock,
  lineRange,
  percent,
  SOURCE_LABEL,
  STATUS_LABEL,
  VERDICT_LABEL,
} from "../lib/format";
import { Link } from "../router";

type Tone = "cyan" | "amber" | "coral" | "green" | "mute";

const STATUS_TONE: Record<OutcomeStatus, Tone> = {
  found: "green",
  partial: "amber",
  missed: "coral",
  extra: "mute",
  ungraded: "mute",
};

const TEXT: Record<Tone, string> = {
  cyan: "text-cyan",
  amber: "text-amber",
  coral: "text-coral",
  green: "text-green",
  mute: "text-ink",
};

function Tile(props: { label: string; value: ReactNode; note?: ReactNode; tone?: Tone }) {
  return (
    <div className="rounded-lg border border-line bg-panel px-4 py-3">
      <p className="text-[12px] text-mute uppercase">{props.label}</p>
      <p className={`mt-1 font-mono text-2xl font-medium ${TEXT[props.tone ?? "mute"]}`}>
        {props.value}
      </p>
      {props.note && <p className="mt-0.5 text-[12px] text-mute">{props.note}</p>}
    </div>
  );
}

function Tiles({ d }: { d: DebriefData }) {
  const t = d.totals;
  const design = d.design.score;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
      <Tile
        label="Found"
        value={`${t.found}/${t.bugs}`}
        tone={t.found === t.bugs ? "green" : "mute"}
        note={t.assisted > 0 ? `${t.assisted} with the assistant` : "without the assistant"}
      />
      <Tile label="Partial" value={t.partial} tone={t.partial > 0 ? "amber" : "mute"} />
      <Tile label="Missed" value={t.missed} tone={t.missed > 0 ? "coral" : "mute"} />
      <Tile label="Extra findings" value={t.extra} note="matched no key bug" />
      <Tile
        label="Time"
        value={clock(t.seconds_used)}
        tone={d.session.overtime ? "coral" : "amber"}
        note={d.session.overtime ? "overtime" : `of ${clock(t.session_seconds)}`}
      />
      <Tile
        label="Wrong claims"
        value={t.wrong_claims}
        tone={t.relied_on_wrong > 0 ? "coral" : "mute"}
        note={`${t.relied_on_wrong} relied on · ${t.questions_used} answered`}
      />
      <Tile
        label="Design notes"
        value={design == null ? "–" : `${design}/3`}
        note={design == null ? "not scored" : undefined}
      />
    </div>
  );
}

function Diff({ text }: { text: string }) {
  return (
    <pre className="overflow-x-auto rounded-md border border-line bg-bg p-3 font-mono text-[12px] leading-5">
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

function Score({ label, value, max }: { label: string; value: number | null | undefined; max: number }) {
  return (
    <span className="font-mono text-[13px]">
      <span className="text-mute">{label} </span>
      {value == null ? "–" : value}/{max}
    </span>
  );
}

function YourFinding({ f }: { f: DebriefFinding }) {
  return (
    <div className="rounded-md border border-line border-l-[3px] border-l-coral bg-bg p-3">
      <p className="mb-1 flex flex-wrap items-center gap-2 text-[12px] text-mute">
        <span className="uppercase">Your finding</span>
        <span className="font-mono">
          {baseName(f.file)} · {lineRange(f.line_from, f.line_to)}
        </span>
        <Badge>{CATEGORY_LABEL[f.category]}</Badge>
      </p>
      <p className="whitespace-pre-wrap">{f.explanation}</p>
      {f.fix && <p className="mt-1 whitespace-pre-wrap text-mute">Fix: {f.fix}</p>}
    </div>
  );
}

function BugCard(props: { bug: DebriefBug; onShow: () => void }) {
  const b = props.bug;
  return (
    <li className="flex flex-col gap-3 rounded-lg border border-line bg-raised/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={STATUS_TONE[b.status]}>{STATUS_LABEL[b.status]}</Badge>
        {b.assisted && <Badge tone="cyan">Assisted</Badge>}
        <Badge>{CATEGORY_LABEL[b.category]}</Badge>
        <button
          type="button"
          onClick={props.onShow}
          className="min-h-11 rounded-md px-2 font-mono text-[13px] text-green hover:bg-raised"
        >
          {b.file} · {lineRange(b.line_from, b.line_to)}
        </button>
      </div>
      <div>
        <p className="text-[12px] text-mute uppercase">What goes wrong</p>
        <p>{b.mechanism}</p>
      </div>
      {b.finding ? (
        <YourFinding f={b.finding} />
      ) : (
        <p className="text-coral">You did not flag these lines.</p>
      )}
      {b.finding && (
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap gap-4">
            <span className="text-[12px] text-mute uppercase">Judge</span>
            <Score label="mechanism" value={b.judge_mechanism} max={2} />
            <Score label="fix" value={b.judge_fix} max={2} />
          </div>
          {b.status === "ungraded" ? (
            <p className="text-[13px] text-mute">
              The lines match, but the judge returned no valid score. Use “Grade again”.
            </p>
          ) : (
            b.judge_notes && <p className="text-[13px] text-mute">{b.judge_notes}</p>
          )}
        </div>
      )}
      <details>
        <summary className="flex min-h-11 cursor-pointer items-center text-[13px] text-cyan">
          Reference fix{b.killing_test ? " and failing test" : ""}
        </summary>
        <Diff text={b.fix_diff} />
        {b.killing_test && (
          <p className="mt-2 font-mono text-[12px] text-mute">Failing test: {b.killing_test}</p>
        )}
      </details>
    </li>
  );
}

function Audit({ a }: { a: DebriefAudit }) {
  const tone: Tone = a.verdict === "wrong" ? "coral" : a.verdict === "correct" ? "green" : "mute";
  const where = a.file
    ? a.line_from && a.line_to
      ? `${baseName(a.file)} · ${lineRange(a.line_from, a.line_to)}`
      : baseName(a.file)
    : "whole problem";
  return (
    <li className="flex flex-col gap-2 rounded-md border border-line bg-bg p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tone}>{a.verdict ? VERDICT_LABEL[a.verdict] : "Not audited"}</Badge>
        {a.relied_on && <Badge tone="coral">You relied on it</Badge>}
        <span className="font-mono text-[12px] text-mute">
          #{a.seq} · {where} · {a.model}
        </span>
      </div>
      <p className="whitespace-pre-wrap">
        <span className="text-mute">You asked: </span>
        {a.question}
      </p>
      <details>
        <summary className="flex min-h-11 cursor-pointer items-center text-[13px] text-cyan">
          Assistant reply
        </summary>
        <p className="whitespace-pre-wrap text-[13px]">{a.reply}</p>
      </details>
      {a.rationale && <p className="text-[13px] text-mute">{a.rationale}</p>}
    </li>
  );
}

function Stats({ rows }: { rows: StatDelta[] }) {
  const rate = (misses: number, attempts: number) => (attempts ? misses / attempts : null);
  return (
    <table className="w-full text-[13px]">
      <thead>
        <tr className="text-left text-[12px] text-mute uppercase">
          <th className="py-1 font-normal">Category</th>
          <th className="py-1 font-normal">Miss rate</th>
          <th className="py-1 text-right font-normal">Missed / attempts</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const before = rate(r.misses_before, r.attempts_before);
          const after = rate(r.misses_after, r.attempts_after);
          const worse = after !== null && (before === null ? after > 0 : after > before);
          return (
            <tr key={r.category} className="border-t border-line">
              <td className="py-2">{CATEGORY_LABEL[r.category]}</td>
              <td className="py-2 font-mono">
                {percent(before)} → <span className={worse ? "text-coral" : "text-green"}>{percent(after)}</span>
              </td>
              <td className="py-2 text-right font-mono text-mute">
                {r.misses_before}/{r.attempts_before} → {r.misses_after}/{r.attempts_after}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Report({ d, id }: { d: DebriefData; id: string }) {
  const queryClient = useQueryClient();
  const session = useQuery({ queryKey: ["session", id], queryFn: () => api.session(id) });
  const firstBug = d.bugs[0];
  const [view, setView] = useState<{ file: string; line: number; nonce: number } | null>(
    firstBug ? { file: firstBug.file, line: firstBug.line_from, nonce: 0 } : null,
  );
  const regrade = useMutation({
    mutationFn: () => api.regrade(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["debrief", id] }),
  });

  const file = session.data?.files.find((f) => f.path === view?.file) ?? session.data?.files[0];
  const yours = [...d.bugs.flatMap((b) => (b.finding ? [b.finding] : [])), ...d.extras];
  const needsJudge = d.totals.ungraded > 0 || d.audits.some((a) => a.verdict == null);

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">
            Debrief · <span className="font-mono">{d.problem.id}</span>
          </h1>
          <Badge tone={d.session.mode === "constrained" ? "cyan" : "amber"}>
            {d.session.mode === "constrained" ? "Constrained" : "Realistic"}
          </Badge>
          {d.session.overtime && <Badge tone="coral">Overtime</Badge>}
        </div>
        <div className="flex items-center gap-2">
          <Button
            tone="mute"
            variant="outline"
            disabled={regrade.isPending}
            onClick={() => regrade.mutate()}
            title="Run the judge again. Matching and your stats do not change."
          >
            {regrade.isPending ? "Grading…" : "Grade again"}
          </Button>
          <Link
            to="/"
            className="inline-flex min-h-11 items-center rounded-md bg-cyan px-4 font-medium text-bg hover:brightness-110"
          >
            Back to the library
          </Link>
        </div>
      </header>

      {regrade.isError && <Notice tone="coral">{errorText(regrade.error)}</Notice>}
      {needsJudge && (
        <Notice tone="amber">
          {d.judge_model
            ? "The judge gave no valid answer for some items, so they are ungraded. Nothing was guessed. You can grade again."
            : "No judge model is configured, so scores are ungraded. Line matching and your stats are still exact."}
        </Notice>
      )}

      <Tiles d={d} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Panel title="Answer key against your findings">
            <ul className="flex flex-col gap-3">
              {d.bugs.map((b) => (
                <BugCard
                  key={b.id}
                  bug={b}
                  onShow={() => setView({ file: b.file, line: b.line_from, nonce: Date.now() })}
                />
              ))}
            </ul>
            {d.extras.length > 0 && (
              <div className="mt-4 flex flex-col gap-2">
                <p className="text-[12px] text-mute uppercase">
                  Extra findings · matched no key bug
                </p>
                {d.extras.map((f) => (
                  <YourFinding key={f.id} f={f} />
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Design notes">
            <div className="flex flex-col gap-3">
              <div>
                <p className="text-[12px] text-mute uppercase">Yours</p>
                <p className="whitespace-pre-wrap">{d.design.notes.trim() || "None written."}</p>
              </div>
              {d.design.reference.length > 0 && (
                <div>
                  <p className="text-[12px] text-mute uppercase">Reference</p>
                  <ul className="list-disc pl-5">
                    {d.design.reference.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-[13px] text-mute">{d.design.rationale}</p>
            </div>
          </Panel>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Panel
            title={file ? file.path : "Code"}
            aside={
              <span className="flex gap-2 py-2">
                <Badge tone="green">Key</Badge>
                <Badge tone="coral">Yours</Badge>
              </span>
            }
            bodyClassName="h-[26rem]"
          >
            {file && view ? (
              <CodeViewer
                modelPath={`debrief/${id}/${file.path}`}
                content={file.content}
                keyLines={d.bugs
                  .filter((b) => b.file === file.path)
                  .map((b) => ({ from: b.line_from, to: b.line_to }))}
                flagged={yours
                  .filter((f) => f.file === file.path)
                  .map((f) => ({ from: f.line_from, to: f.line_to }))}
                reveal={view}
              />
            ) : (
              <Loading label="Loading the code…" />
            )}
          </Panel>

          <Panel title={`Assistant claim audit · ${d.audits.length}`}>
            {d.audits.length === 0 ? (
              <p className="text-mute">
                No answered questions in this session
                {d.totals.refusals > 0 ? ` (${d.totals.refusals} refused)` : ""}.
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {d.audits.map((a) => (
                  <Audit key={a.query_id} a={a} />
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Category stats after this session">
            {d.stats_delta.length === 0 ? (
              <p className="text-mute">No change recorded.</p>
            ) : (
              <Stats rows={d.stats_delta} />
            )}
          </Panel>

          <Panel title="Where this problem came from">
            <dl className="grid grid-cols-[7rem_1fr] gap-y-1 text-[13px]">
              <dt className="text-mute">Source</dt>
              <dd>{SOURCE_LABEL[d.problem.source]}</dd>
              <dt className="text-mute">Upstream id</dt>
              <dd className="font-mono">{d.problem.upstream_id}</dd>
              <dt className="text-mute">Repository</dt>
              <dd className="font-mono">{d.problem.origin_repo}</dd>
              <dt className="text-mute">Buggy commit</dt>
              <dd className="truncate font-mono" title={d.problem.commit}>
                {d.problem.commit.slice(0, 12)}
              </dd>
              <dt className="text-mute">Licence</dt>
              <dd>{d.problem.licence}</dd>
              <dt className="text-mute">Judge</dt>
              <dd className="font-mono">{d.judge_model ?? "not configured"}</dd>
            </dl>
          </Panel>
        </div>
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
          <Notice tone="amber">This session is still running. The debrief opens after you submit.</Notice>
          <Link to={`/session/${id}`} className="inline-flex min-h-11 items-center text-cyan underline">
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
