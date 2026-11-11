// Session board: top bar (problem, timer, mode, submit), files and session rules on the
// left, the code in the centre with the report draft under it, the assistant on the right.
// The timer is display only: the server owns the clock and decides overtime at submit.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type SessionView } from "../api/client";
import AssistantPanel, { type Selection } from "../components/AssistantPanel";
import CodeViewer, { type LineRange } from "../components/CodeViewer";
import ReportForm, { findingProblem } from "../components/ReportForm";
import { Button, errorText, Loading, Notice, Segmented } from "../components/ui";
import { baseName, clock, lref, plural, problemTitle } from "../lib/format";
import { Link, navigate } from "../router";
import { useDraft, useDraftStore, type DraftFinding } from "../store/draft";

function Timer({ session, syncedAt }: { session: SessionView; syncedAt: number }) {
  const [now, setNow] = useState(syncedAt);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const left = session.seconds_left - Math.max(0, (now - syncedAt) / 1000);
  const over = left <= 0;
  return (
    <div
      role="timer"
      aria-label={over ? "Time is up" : `Time left: ${clock(left)}`}
      className="flex items-baseline gap-3"
    >
      <span
        className={`font-mono text-[2rem] leading-none font-medium tabular-nums ${over ? "text-coral" : "text-amber"}`}
      >
        {clock(left)}
      </span>
      <span className={`text-[13px] ${over ? "text-coral" : "text-mute"}`}>
        {over ? "overtime" : `left of ${clock(session.session_seconds)}`}
      </span>
    </div>
  );
}

function SubmitControl(props: {
  count: number;
  blocker: string | null;
  pending: boolean;
  onSubmit: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming) {
    return (
      <Button
        className="min-h-12 px-5 text-base font-semibold"
        disabled={props.blocker !== null}
        title={props.blocker ?? undefined}
        onClick={() => setConfirming(true)}
      >
        Submit report →
      </Button>
    );
  }
  return (
    <div className="flex items-center gap-2" role="group" aria-label="Confirm submit">
      <Button
        className="min-h-12 px-5 text-base font-semibold"
        disabled={props.pending}
        onClick={props.onSubmit}
      >
        {props.pending
          ? "Submitting…"
          : `Submit ${props.count === 0 ? "with no findings" : plural(props.count, "finding")}`}
      </Button>
      <Button tone="mute" variant="outline" className="min-h-12" onClick={() => setConfirming(false)}>
        Keep working
      </Button>
    </div>
  );
}

function Workspace({ session, syncedAt }: { session: SessionView; syncedAt: number }) {
  const id = session.id;
  const constrained = session.mode === "constrained";
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: Infinity });
  const draft = useDraft(id);
  const addFinding = useDraftStore((s) => s.addFinding);
  const clearDraft = useDraftStore((s) => s.clear);

  const [activePath, setActivePath] = useState(session.files[0]?.path ?? "");
  const [range, setRange] = useState<LineRange | null>(null);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [reveal, setReveal] = useState<{ line: number; nonce: number } | null>(null);
  const questionRef = useRef<HTMLTextAreaElement | null>(null);

  const active = session.files.find((f) => f.path === activePath) ?? session.files[0];
  const lineCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const f of session.files) {
      const lines = f.content.split("\n");
      counts[f.path] = lines[lines.length - 1] === "" ? lines.length - 1 : lines.length;
    }
    return counts;
  }, [session.files]);
  const totalLines = Object.values(lineCounts).reduce((a, b) => a + b, 0);

  const flagged = draft.findings
    .filter((f) => f.file === active?.path)
    .map((f) => ({ from: f.line_from, to: f.line_to }));
  const selection: Selection | null =
    active && range ? { file: active.path, from: range.from, to: range.to } : null;

  const firstProblem = draft.findings
    .map((f) => ({ f, problem: findingProblem(f) }))
    .find((x) => x.problem !== null);
  const blocker = firstProblem
    ? `${baseName(firstProblem.f.file)} ${lref(firstProblem.f.line_from, firstProblem.f.line_to)}: ${firstProblem.problem}`
    : null;

  const submit = useMutation({
    mutationFn: () =>
      api.submit(id, {
        findings: draft.findings.map((f) => ({
          file: f.file,
          line_from: f.line_from,
          line_to: f.line_to,
          category: f.category,
          explanation: f.explanation.trim(),
          fix: f.fix.trim(),
        })),
        design_notes: draft.designNotes,
      }),
    onSuccess: async () => {
      clearDraft(id);
      await queryClient.invalidateQueries();
      navigate(`/debrief/${id}`, { replace: true });
    },
  });

  const open = (path: string) => {
    setActivePath(path);
    setRange(null);
  };
  const jump = (f: DraftFinding) => {
    setActivePath(f.file);
    setReveal({ line: f.line_from, nonce: Date.now() });
  };
  const flag = () => {
    if (selection) setFocusKey(addFinding(id, selection.file, selection.from, selection.to));
  };

  if (!active) return <Notice tone="coral">This problem has no files.</Notice>;

  return (
    <div className="grid h-full grid-rows-[auto_minmax(0,1fr)]">
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-line bg-panel px-6 py-3">
        <div className="flex min-w-0 items-center gap-6">
          <Link to="/" className="flex min-h-11 items-center text-mute hover:text-ink">
            ← Library
          </Link>
          <div className="min-w-0">
            <p className="text-[12px] tracking-widest text-mute uppercase">
              Problem {session.problem_id} · Python · Unfamiliar codebase
            </p>
            <h1 className="truncate text-lg font-semibold">
              {problemTitle(
                session.origin_repo,
                session.files.map((f) => f.path),
              )}
            </h1>
            <p className="text-[13px] text-mute">
              {plural(session.files.length, "file")} · {totalLines} lines
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-5">
          <Timer session={session} syncedAt={syncedAt} />
          <Segmented
            label="Assistant mode for this session"
            value={session.mode}
            tone={constrained ? "cyan" : "amber"}
            options={[
              { value: "constrained", label: "Constrained · local" },
              { value: "realistic", label: "Realistic · Gemini" },
            ]}
          />
          <SubmitControl
            count={draft.findings.length}
            blocker={blocker}
            pending={submit.isPending}
            onSubmit={() => submit.mutate()}
          />
        </div>
        {(blocker || submit.isError) && (
          <p className="w-full text-right text-[13px] text-amber" role="status">
            {submit.isError ? errorText(submit.error) : `Before you submit: ${blocker}.`}
          </p>
        )}
      </header>

      <div className="grid min-h-0 grid-cols-[15rem_minmax(0,1fr)_25rem]">
        <nav aria-label="Files" className="min-h-0 overflow-y-auto border-r border-line bg-panel p-3.5">
          <h2 className="px-3 pt-3 pb-2 text-[12px] tracking-widest text-mute uppercase">Files</h2>
          <ul className="flex flex-col gap-1.5">
            {session.files.map((f) => {
              const current = f.path === active.path;
              return (
                <li key={f.path}>
                  <button
                    type="button"
                    aria-current={current ? "true" : undefined}
                    onClick={() => open(f.path)}
                    title={f.path}
                    className={`flex min-h-12 w-full items-center justify-between gap-3 rounded-lg px-3 text-left font-mono text-[13px] ${
                      current ? "bg-raised text-ink" : "text-mute hover:bg-raised/60 hover:text-ink"
                    }`}
                  >
                    <span className="truncate">{baseName(f.path)}</span>
                    <span className="text-mute">{lineCounts[f.path]}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          <section className="mt-4 rounded-lg bg-raised px-3.5 py-4 text-[13px] leading-relaxed text-mute">
            <h2 className="mb-2 text-[12px] tracking-widest uppercase">Session rules</h2>
            {constrained ? (
              <>
                <p>
                  The assistant sees only the lines you select. Window:{" "}
                  {session.ctx_cap.toLocaleString()} tokens.
                </p>
                <p className="mt-2">{session.q_budget} questions per session.</p>
              </>
            ) : (
              <>
                <p>The assistant sees the whole file you are in.</p>
                <p className="mt-2">No question limit.</p>
              </>
            )}
            <p className="mt-2">No test runner. Read, reason, report.</p>
          </section>
        </nav>

        <div className="grid min-h-0 grid-rows-[auto_minmax(0,3fr)_minmax(0,2fr)]">
          <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-line bg-panel px-6 py-2">
            <p className="flex items-baseline gap-4" title={active.path}>
              <span className="font-mono">{baseName(active.path)}</span>
              <span className="text-[13px] text-mute">{lineCounts[active.path]} lines</span>
            </p>
            {selection ? (
              <p className="flex items-center gap-3">
                <span className="font-mono text-[13px]">
                  {lref(selection.from, selection.to)} selected
                </span>
                <Button compact variant="outline" onClick={() => questionRef.current?.focus()}>
                  Ask assistant
                </Button>
                <Button compact variant="outline" tone="coral" onClick={flag}>
                  Flag as bug
                </Button>
              </p>
            ) : (
              <p className="text-[13px] text-mute">
                Click a line number, then another, to select a range.{" "}
                {constrained
                  ? "The assistant sees only what you send it."
                  : "Then ask about it or flag it as a bug."}
              </p>
            )}
          </div>
          <div className="min-h-0">
            <CodeViewer
              modelPath={`${id}/${active.path}`}
              content={active.content}
              flagged={flagged}
              onSelect={setRange}
              reveal={reveal}
            />
          </div>
          <ReportForm sessionId={id} focusKey={focusKey} onJump={jump} />
        </div>

        <AssistantPanel
          session={session}
          selection={selection}
          maxQuestionChars={settings.data?.max_question_chars ?? 1000}
          inputRef={questionRef}
        />
      </div>
    </div>
  );
}

export default function Session({ id }: { id: string }) {
  const session = useQuery({
    queryKey: ["session", id],
    queryFn: () => api.session(id),
    refetchInterval: 60_000, // resync the displayed timer with the server clock
  });
  const submitted = Boolean(session.data?.submitted_at);
  useEffect(() => {
    if (submitted) navigate(`/debrief/${id}`, { replace: true });
  }, [submitted, id]);

  if (session.isError) {
    return (
      <div className="p-6">
        <Notice tone="coral">{errorText(session.error)}</Notice>
      </div>
    );
  }
  if (!session.data || submitted) return <Loading label="Opening the session…" />;
  return <Workspace key={id} session={session.data} syncedAt={session.dataUpdatedAt} />;
}
