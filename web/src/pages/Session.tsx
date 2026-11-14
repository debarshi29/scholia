// Session board: top bar (problem, timer, mode, submit), files and session rules on the
// left, the code in the centre with the report draft under it, the assistant on the right.
// The timer is display only: the server owns the clock and decides overtime at submit.
import ThemeToggle from "../components/ThemeToggle";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type SessionView } from "../api/client";
import AssistantPanel, { type Selection } from "../components/AssistantPanel";
import CodeViewer, { type LineRange } from "../components/CodeViewer";
import { ArrowLeft, ArrowRight, Chat, Eye, FileCode, Flag, Target } from "../components/icons";
import ReportForm, { findingProblem } from "../components/ReportForm";
import { Button, errorText, Loading, Notice, Segmented } from "../components/ui";
import { baseName, clock, lref, plural, problemTitle } from "../lib/format";
import { Link, navigate } from "../router";
import { useDraft, useDraftStore, type DraftFinding } from "../store/draft";

/** Seconds left, ticking locally from the last server sync. Display only. */
function useSecondsLeft(session: SessionView, syncedAt: number): number {
  const [now, setNow] = useState(syncedAt);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return session.seconds_left - Math.max(0, (now - syncedAt) / 1000);
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
        className="group min-h-9"
        disabled={props.blocker !== null}
        title={props.blocker ?? undefined}
        onClick={() => setConfirming(true)}
      >
        Submit report
        <ArrowRight className="size-[18px] transition-transform duration-200 group-hover:translate-x-1" />
      </Button>
    );
  }
  return (
    <div className="fade flex items-center gap-2" role="group" aria-label="Confirm submit">
      <Button tone="green" className="min-h-9" disabled={props.pending} onClick={props.onSubmit}>
        {props.pending
          ? "Submitting…"
          : `Submit ${props.count === 0 ? "with no findings" : plural(props.count, "finding")}`}
      </Button>
      <Button tone="mute" variant="outline" className="min-h-9" onClick={() => setConfirming(false)}>
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
  const setEdit = useDraftStore((s) => s.setEdit);
  const edits = draft.edits ?? {};

  const [activePath, setActivePath] = useState(session.files[0]?.path ?? "");
  const [range, setRange] = useState<LineRange | null>(null);
  const [fixMode, setFixMode] = useState(Object.keys(draft.edits ?? {}).length > 0);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [reveal, setReveal] = useState<{ line: number; nonce: number } | null>(null);
  const [reportOpen, setReportOpen] = useState(draft.findings.length > 0);
  const questionRef = useRef<HTMLTextAreaElement | null>(null);

  const left = useSecondsLeft(session, syncedAt);
  const over = left <= 0;
  const low = !over && left <= 300;
  const elapsedShare = Math.min(1, Math.max(0, 1 - left / session.session_seconds));

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

  const flagsByFile: Record<string, number> = {};
  for (const f of draft.findings) flagsByFile[f.file] = (flagsByFile[f.file] ?? 0) + 1;
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
        patches: Object.entries(edits).map(([file, content]) => ({ file, content })),
      }),
    onSuccess: async () => {
      clearDraft(id);
      await queryClient.invalidateQueries();
      navigate(`/debrief/${id}`, { replace: true });
    },
  });

  const onEdit = (content: string) => {
    if (!active) return;
    // Back to the original text is no edit at all.
    setEdit(id, active.path, content === active.content ? null : content);
  };
  const open = (path: string) => {
    setActivePath(path);
    setRange(null);
  };
  const jump = (f: DraftFinding) => {
    setActivePath(f.file);
    setReveal({ line: f.line_from, nonce: Date.now() });
  };
  const flag = () => {
    if (!selection) return;
    setFocusKey(addFinding(id, selection.file, selection.from, selection.to));
    setReportOpen(true);
  };

  if (!active) return <Notice tone="coral">This problem has no files.</Notice>;
  const rule = "flex items-start gap-2.5";

  return (
    <div className="grid h-full grid-rows-[auto_minmax(0,1fr)]">
      <header className="topbar relative flex flex-wrap items-center justify-between gap-x-5 gap-y-2 px-4 py-1.5">
        <div className="flex min-w-0 items-center gap-4">
          <Link
            to="/"
            className="flex min-h-9 items-center gap-1.5 rounded-md px-2.5 text-mute transition hover:bg-ink/5 hover:text-ink"
          >
            <ArrowLeft className="size-4" />
            Library
          </Link>
          <div className="min-w-0">
            <p className="eyebrow">Problem {session.problem_id} · Python · Unfamiliar codebase</p>
            <h1 className="flex items-baseline gap-3 truncate text-lg leading-snug font-semibold">
              {problemTitle(
                session.origin_repo,
                session.files.map((f) => f.path),
              )}
              <span className="text-[12.5px] font-normal text-mute">
                {plural(session.files.length, "file")} · {totalLines} lines
              </span>
            </h1>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <div
            role="timer"
            aria-label={over ? "Time is up" : `Time left: ${clock(left)}`}
            className="flex items-baseline gap-2.5"
          >
            <span
              className={`font-mono text-[1.4rem] leading-none font-medium tabular-nums transition-colors duration-500 ${
                over || low ? "text-coral" : "text-amber"
              } ${over ? "" : ""}`}
            >
              {clock(left)}
            </span>
            <span className={`text-[12.5px] ${over ? "text-coral" : "text-mute"}`}>
              {over ? "overtime" : `left of ${clock(session.session_seconds)}`}
            </span>
          </div>
          <Segmented
            label="Assistant mode for this session"
            value={session.mode}
            tone={constrained ? "cyan" : "amber"}
            compact
            options={[
              { value: "constrained", label: "Constrained · local" },
              { value: "realistic", label: "Realistic · Gemini" },
            ]}
          />
          <ThemeToggle />
          <SubmitControl
            count={draft.findings.length}
            blocker={blocker}
            pending={submit.isPending}
            onSubmit={() => submit.mutate()}
          />
        </div>
        {(blocker || submit.isError) && (
          <p className="fade w-full text-right text-[12.5px] text-amber" role="status">
            {submit.isError ? errorText(submit.error) : `Before you submit: ${blocker}.`}
          </p>
        )}
        {/* Elapsed time as a line along the bottom edge of the bar. */}
        <span className="absolute inset-x-0 -bottom-px h-0.5 bg-ink/[0.04]" aria-hidden="true">
          <span
            className={`block h-full transition-[width] duration-1000 ease-linear ${
              over || low
                ? "bg-coral"
                : "bg-amber"
            }`}
            style={{ width: `${elapsedShare * 100}%` }}
          />
        </span>
      </header>

      <div className="grid min-h-0 grid-cols-[13.5rem_minmax(0,1fr)_23.5rem]">
        <nav
          aria-label="Files"
          className="flex min-h-0 flex-col gap-4 overflow-y-auto border-r border-line bg-panel/70 p-3"
        >
          <div>
            <h2 className="eyebrow px-2 pt-2 pb-2">Files</h2>
            <ul className="flex flex-col gap-1">
              {session.files.map((f) => {
                const current = f.path === active.path;
                const flags = flagsByFile[f.path] ?? 0;
                return (
                  <li key={f.path}>
                    <button
                      type="button"
                      aria-current={current ? "true" : undefined}
                      onClick={() => open(f.path)}
                      title={f.path}
                      className={`relative flex min-h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-left font-mono text-[12.5px] transition ${
                        current
                          ? "bg-ink/[0.07] text-ink"
                          : "text-mute hover:bg-ink/[0.04] hover:text-ink"
                      }`}
                    >
                      {current && (
                        <span className="absolute top-2.5 bottom-2.5 left-0 w-0.5 rounded-full bg-cyan" />
                      )}
                      <FileCode className={`size-4 shrink-0 ${current ? "text-cyan" : ""}`} />
                      <span className="min-w-0 flex-1 truncate">{baseName(f.path)}</span>
                      {flags > 0 && (
                        <span className="rounded-full bg-coral/15 px-1.5 py-0.5 text-[11px] leading-none text-coral">
                          {flags}
                        </span>
                      )}
                      {edits[f.path] !== undefined && (
                        <span
                          title="Edited: part of your fix"
                          className="size-2 rounded-full bg-green"
                        />
                      )}
                      <span className="text-[11.5px] text-mute/80">{lineCounts[f.path]}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
          <section className="rounded-lg border border-line px-3 py-3 text-[12px] leading-relaxed text-mute">
            <h2 className="eyebrow mb-2.5">Session rules</h2>
            <ul className="flex flex-col gap-2.5">
              <li className={rule}>
                <Eye className="mt-0.5 size-4 shrink-0 text-cyan" />
                {constrained
                  ? `The assistant sees only the lines you select. Window: ${session.ctx_cap.toLocaleString()} tokens.`
                  : "The assistant sees the whole file you are in."}
              </li>
              <li className={rule}>
                <Target className="mt-0.5 size-4 shrink-0 text-amber" />
                {constrained ? `${session.q_budget} questions per session.` : "No question limit."}
              </li>
              <li className={rule}>
                <Flag className="mt-0.5 size-4 shrink-0 text-coral" />
                No test runner. Read, reason, report, and optionally fix.
              </li>
            </ul>
          </section>
        </nav>

        <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto]">
          <div className="flex min-h-10 items-center justify-between gap-3 border-b border-line bg-panel/60 px-4 py-1">
            <p className="flex min-w-0 items-baseline gap-3" title={active.path}>
              <span className="truncate font-mono text-[13px]">{active.path}</span>
              <span className="shrink-0 text-[12.5px] text-mute">
                {lineCounts[active.path]} lines
              </span>
            </p>
            <div className="flex items-center gap-3">
              <Segmented
                label="Editor mode"
                value={fixMode ? "fix" : "read"}
                tone="green"
                compact
                onChange={(v) => setFixMode(v === "fix")}
                options={[
                  { value: "read", label: "Read" },
                  { value: "fix", label: "Fix" },
                ]}
              />
              {fixMode && edits[active.path] !== undefined && (
                <Button compact variant="outline" tone="mute" onClick={() => setEdit(id, active.path, null)}>
                  Reset file
                </Button>
              )}
            </div>
            {selection ? (
              <p key="actions" className="fade flex items-center gap-2">
                <span className="mr-1 rounded-full bg-cyan/10 px-2.5 py-1 font-mono text-[12.5px] text-cyan">
                  {lref(selection.from, selection.to)}
                </span>
                <Button
                  compact
                  variant="outline"
                  tone={constrained ? "cyan" : "amber"}
                  onClick={() => questionRef.current?.focus()}
                >
                  <Chat className="size-4" />
                  Ask assistant
                </Button>
                <Button compact variant="outline" tone="coral" onClick={flag}>
                  <Flag className="size-4" />
                  Flag as bug
                </Button>
              </p>
            ) : (
              <p key="hint" className="fade text-[12.5px] text-mute">
                Click two line numbers to select a range.
              </p>
            )}
          </div>
          <div className="min-h-0">
            <CodeViewer
              key={`${active.path}:${fixMode}`}
              modelPath={`${id}/${active.path}`}
              content={edits[active.path] ?? active.content}
              onEdit={fixMode ? onEdit : undefined}
              flagged={flagged}
              onSelect={setRange}
              reveal={reveal}
            />
          </div>
          <ReportForm
            sessionId={id}
            open={reportOpen}
            onToggle={() => setReportOpen((v) => !v)}
            focusKey={focusKey}
            onJump={jump}
          />
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
      <div className="mx-auto max-w-xl p-8">
        <Notice tone="coral">{errorText(session.error)}</Notice>
      </div>
    );
  }
  if (!session.data || submitted) return <Loading label="Opening the session…" />;
  return <Workspace key={id} session={session.data} syncedAt={session.dataUpdatedAt} />;
}
