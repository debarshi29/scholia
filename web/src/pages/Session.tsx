// Session: file tree, read-only code viewer, assistant panel and the report form.
// The timer is display only: the server owns the clock and decides overtime at submit.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type SessionView } from "../api/client";
import AssistantPanel, { type Selection } from "../components/AssistantPanel";
import CodeViewer, { type LineRange } from "../components/CodeViewer";
import ReportForm, { findingProblem } from "../components/ReportForm";
import { Badge, Button, errorText, Loading, Notice } from "../components/ui";
import { baseName, clock, lineRange } from "../lib/format";
import { navigate } from "../router";
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
      className={`flex items-baseline gap-2 font-mono ${over ? "text-coral" : "text-amber"}`}
    >
      <span className="text-xl font-medium tabular-nums">{clock(left)}</span>
      {over && <span className="text-[12px] uppercase">Overtime</span>}
    </div>
  );
}

function FileTree(props: {
  files: string[];
  active: string;
  flags: Record<string, number>;
  onOpen: (path: string) => void;
}) {
  return (
    <nav aria-label="Files" className="min-h-0 overflow-y-auto border-r border-line bg-panel">
      <h2 className="flex min-h-11 items-center border-b border-line px-3 text-[13px] font-semibold tracking-wide text-mute uppercase">
        Files
      </h2>
      <ul className="p-1.5">
        {props.files.map((path) => {
          const dir = path.includes("/") ? path.slice(0, path.lastIndexOf("/") + 1) : "";
          const current = path === props.active;
          const flags = props.flags[path] ?? 0;
          return (
            <li key={path}>
              <button
                type="button"
                aria-current={current ? "true" : undefined}
                onClick={() => props.onOpen(path)}
                title={path}
                className={`flex min-h-11 w-full flex-col justify-center rounded-md px-2 text-left ${
                  current ? "bg-cyan/10 text-ink" : "text-mute hover:bg-raised hover:text-ink"
                }`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-[13px]">{baseName(path)}</span>
                  {flags > 0 && <Badge tone="coral">{flags}</Badge>}
                </span>
                {dir && <span className="truncate font-mono text-[11px] opacity-70">{dir}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
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
      <div className="flex items-center gap-3">
        {props.blocker && <span className="text-[13px] text-amber">{props.blocker}</span>}
        <Button tone="green" disabled={props.blocker !== null} onClick={() => setConfirming(true)}>
          Submit report
        </Button>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2" role="group" aria-label="Confirm submit">
      <span className="text-[13px]">
        Submit {props.count === 0 ? "with no findings" : `${props.count} finding${props.count === 1 ? "" : "s"}`}
        ? You cannot change it afterwards.
      </span>
      <Button tone="green" disabled={props.pending} onClick={props.onSubmit}>
        {props.pending ? "Submitting…" : "Submit now"}
      </Button>
      <Button tone="mute" variant="outline" onClick={() => setConfirming(false)}>
        Keep working
      </Button>
    </div>
  );
}

function Workspace({ session, syncedAt }: { session: SessionView; syncedAt: number }) {
  const id = session.id;
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

  const flagCounts: Record<string, number> = {};
  for (const f of draft.findings) flagCounts[f.file] = (flagCounts[f.file] ?? 0) + 1;
  const flagged = draft.findings
    .filter((f) => f.file === active?.path && f.line_from >= 1 && f.line_to >= f.line_from)
    .map((f) => ({ from: f.line_from, to: Math.min(f.line_to, lineCounts[f.file] ?? f.line_to) }));

  const selection: Selection | null =
    active && range ? { file: active.path, from: range.from, to: range.to } : null;

  const firstProblem = draft.findings
    .map((f, i) => ({ i, problem: findingProblem(f, lineCounts) }))
    .find((x) => x.problem !== null);
  const blocker = firstProblem ? `Finding #${firstProblem.i + 1}: ${firstProblem.problem}` : null;

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
    if (!selection) return;
    setFocusKey(addFinding(id, selection.file, selection.from, selection.to));
  };

  if (!active) return <Notice tone="coral">This problem has no files.</Notice>;

  return (
    <div className="grid h-full grid-rows-[auto_minmax(0,1fr)]">
      <header className="flex min-h-14 flex-wrap items-center justify-between gap-4 border-b border-line bg-panel px-4 py-1.5">
        <div className="flex items-center gap-3">
          <span className="font-mono text-base font-medium">{session.problem_id}</span>
          <Badge tone={session.mode === "constrained" ? "cyan" : "amber"}>
            {session.mode === "constrained" ? "Constrained" : "Realistic"}
          </Badge>
          <Timer session={session} syncedAt={syncedAt} />
        </div>
        <div className="flex flex-col items-end gap-1">
          <SubmitControl
            count={draft.findings.length}
            blocker={blocker}
            pending={submit.isPending}
            onSubmit={() => submit.mutate()}
          />
          {submit.isError && <Notice tone="coral">{errorText(submit.error)}</Notice>}
        </div>
      </header>

      <div className="grid min-h-0 grid-cols-[13rem_minmax(0,1fr)_23rem]">
        <FileTree
          files={session.files.map((f) => f.path)}
          active={active.path}
          flags={flagCounts}
          onOpen={open}
        />

        <div className="grid min-h-0 grid-rows-[auto_minmax(0,3fr)_minmax(0,2fr)]">
          <div className="flex min-h-12 flex-wrap items-center justify-between gap-3 border-b border-line px-3 py-1">
            <span className="truncate font-mono text-[13px] text-mute" title={active.path}>
              {active.path}
              <span className="text-ink">
                {range ? ` · ${lineRange(range.from, range.to)} selected` : ""}
              </span>
            </span>
            <span className="flex gap-2">
              <Button
                compact
                variant="outline"
                tone={session.mode === "constrained" ? "cyan" : "amber"}
                disabled={session.mode === "constrained" && !selection}
                title={selection ? undefined : "Select lines in the code first"}
                onClick={() => questionRef.current?.focus()}
              >
                Ask assistant
              </Button>
              <Button
                compact
                variant="outline"
                tone="coral"
                disabled={!selection}
                title={selection ? undefined : "Select lines in the code first"}
                onClick={flag}
              >
                Flag as bug
              </Button>
            </span>
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
          <ReportForm sessionId={id} lineCounts={lineCounts} focusKey={focusKey} onJump={jump} />
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
