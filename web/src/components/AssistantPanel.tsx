// The assistant panel: context-window bar, budget pips, the thread and refusal notices.
// Every question goes to the server's proxy, which enforces all limits; this panel only
// displays them.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type RefObject } from "react";
import { api, type SessionView, type ThreadItem } from "../api/client";
import { baseName, lineRange, REFUSAL_TEXT } from "../lib/format";
import { Badge, Button, errorText, INPUT, Notice } from "./ui";

export interface Selection {
  file: string;
  from: number;
  to: number;
}

interface Props {
  session: SessionView;
  selection: Selection | null;
  maxQuestionChars: number;
  inputRef: RefObject<HTMLTextAreaElement | null>;
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function ContextBar(props: { session: SessionView; selection: Selection | null; question: string }) {
  const { session, selection } = props;
  const question = useDebounced(props.question, 400);
  const measure = useQuery({
    queryKey: ["measure", session.id, selection, question],
    queryFn: () =>
      api.measure(session.id, {
        file: selection!.file,
        line_from: selection!.from,
        line_to: selection!.to,
        question,
      }),
    enabled: selection !== null,
    staleTime: 60_000,
  });
  const cap = session.ctx_cap;
  const tokens = selection ? (measure.data?.tokens ?? null) : null;
  const over = tokens !== null && tokens > cap;
  const share = tokens === null ? 0 : Math.min(1, tokens / cap);
  return (
    <div>
      <div className="flex items-baseline justify-between text-[12px]">
        <span className="text-mute uppercase">Context window</span>
        <span className={`font-mono ${over ? "text-coral" : "text-ink"}`}>
          {tokens === null ? "–" : tokens.toLocaleString()} / {cap.toLocaleString()} tokens
        </span>
      </div>
      <div
        className="mt-1 h-2 overflow-hidden rounded-full bg-raised"
        role="meter"
        aria-label="Context window used by the selection and question"
        aria-valuemin={0}
        aria-valuemax={cap}
        aria-valuenow={tokens ?? 0}
      >
        <div
          className={`h-full rounded-full ${over ? "bg-coral" : "bg-cyan"}`}
          style={{ width: `${share * 100}%` }}
        />
      </div>
      <p className={`mt-1 text-[12px] ${over ? "text-coral" : "text-mute"}`}>
        {!selection
          ? "Select lines in the code to ask about them."
          : over
            ? "Over the cap. Select fewer lines or shorten the question."
            : `${baseName(selection.file)}, ${lineRange(selection.from, selection.to)}`}
      </p>
    </div>
  );
}

function BudgetPips({ used, budget }: { used: number; budget: number }) {
  const left = Math.max(0, budget - used);
  return (
    <div>
      <div className="flex items-baseline justify-between text-[12px]">
        <span className="text-mute uppercase">Question budget</span>
        <span className={`font-mono ${left === 0 ? "text-coral" : "text-ink"}`}>
          {left} of {budget} left
        </span>
      </div>
      {budget <= 30 && (
        <div className="mt-1.5 flex flex-wrap gap-1" aria-hidden="true">
          {Array.from({ length: budget }, (_, i) => (
            <span
              key={i}
              className={`h-2 w-4 rounded-sm ${i < used ? "bg-raised" : "bg-cyan"}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Exchange({ item }: { item: ThreadItem }) {
  const where =
    item.file && item.line_from && item.line_to
      ? `${baseName(item.file)} · ${lineRange(item.line_from, item.line_to)}`
      : item.file
        ? baseName(item.file)
        : "no selection";
  return (
    <li className="flex flex-col gap-2">
      <div className="rounded-md border border-line bg-raised px-3 py-2">
        <p className="mb-1 font-mono text-[12px] text-mute">{where}</p>
        <p className="whitespace-pre-wrap">{item.question}</p>
      </div>
      {item.refused ? (
        <Notice tone="coral" role="status">
          <span className="font-medium">Not answered.</span>{" "}
          {item.reason ? REFUSAL_TEXT[item.reason] : "The question was refused."}
          <span className="block text-[12px] opacity-80">This did not use a question.</span>
        </Notice>
      ) : (
        <div className="px-1">
          <p className="mb-1 font-mono text-[12px] text-mute">{item.model}</p>
          <p className="whitespace-pre-wrap">{item.reply}</p>
        </div>
      )}
    </li>
  );
}

export default function AssistantPanel(props: Props) {
  const { session, selection, maxQuestionChars, inputRef } = props;
  const constrained = session.mode === "constrained";
  const [question, setQuestion] = useState("");
  const queryClient = useQueryClient();
  const threadEnd = useRef<HTMLDivElement | null>(null);

  const ask = useMutation({
    mutationFn: () =>
      api.ask(session.id, {
        file: selection?.file ?? null,
        line_from: selection?.from ?? null,
        line_to: selection?.to ?? null,
        question: question.trim(),
      }),
    onSuccess: (result) => {
      if (!result.refused) setQuestion("");
      return queryClient.invalidateQueries({ queryKey: ["session", session.id] });
    },
  });

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ block: "end" });
  }, [session.thread.length, ask.isPending]);

  const tooLong = question.length > maxQuestionChars;
  const canAsk = question.trim().length > 0 && !tooLong && !ask.isPending;

  return (
    <aside
      aria-label="Assistant"
      className="flex min-h-0 flex-col border-l border-line bg-panel"
    >
      <header className="flex min-h-11 items-center justify-between gap-2 border-b border-line px-3">
        <h2 className="text-[13px] font-semibold tracking-wide text-mute uppercase">Assistant</h2>
        <Badge tone={constrained ? "cyan" : "amber"}>
          {constrained ? "Constrained" : "Realistic"}
        </Badge>
      </header>

      <div className="flex flex-col gap-3 border-b border-line p-3">
        {constrained ? (
          <>
            <ContextBar session={session} selection={selection} question={question} />
            <BudgetPips used={session.questions_used} budget={session.q_budget} />
          </>
        ) : (
          <p className="text-[13px] text-amber">
            Sees the whole file you are in (or every file, with nothing selected). No budget.
            <span className="block text-mute">{session.questions_used} asked so far.</span>
          </p>
        )}
      </div>

      <ol className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-3" aria-live="polite">
        {session.thread.length === 0 && !ask.isPending && (
          <li className="text-[13px] text-mute">
            {constrained
              ? "The assistant sees only the lines you select, and it can be wrong. Check what it tells you against the code."
              : "The assistant can be wrong. Check what it tells you against the code."}
          </li>
        )}
        {session.thread.map((item) => (
          <Exchange key={item.query_id} item={item} />
        ))}
        {ask.isPending && <li className="text-[13px] text-mute">Waiting for the model…</li>}
        <div ref={threadEnd} />
      </ol>

      <form
        className="flex flex-col gap-2 border-t border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (canAsk) ask.mutate();
        }}
      >
        <label className="flex flex-col gap-1">
          <span className="flex justify-between text-[12px] text-mute uppercase">
            <span>Question</span>
            <span className={`font-mono normal-case ${tooLong ? "text-coral" : ""}`}>
              {question.length}/{maxQuestionChars}
            </span>
          </span>
          <textarea
            ref={inputRef}
            className={`${INPUT} min-h-20 resize-y py-2`}
            value={question}
            placeholder={
              constrained ? "Ask about the selected lines…" : "Ask about this code…"
            }
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && canAsk) ask.mutate();
            }}
          />
        </label>
        {ask.isError && <Notice tone="coral">{errorText(ask.error)}</Notice>}
        <Button type="submit" tone={constrained ? "cyan" : "amber"} disabled={!canAsk}>
          {ask.isPending ? "Asking…" : "Send question"}
        </Button>
      </form>
    </aside>
  );
}
