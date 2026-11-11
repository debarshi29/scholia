// Assistant panel from the Session board: model line, context-window bar, question pips,
// the thread and the composer. Every question goes to the server's proxy, which enforces
// all limits; this panel only displays them.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type RefObject } from "react";
import { api, type SessionView, type ThreadItem } from "../api/client";
import { baseName, lref, REFUSAL_TEXT } from "../lib/format";
import { Button, errorText, INPUT, Notice } from "./ui";

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
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-mute">Context window</span>
        <span className={`font-mono text-[13px] ${over ? "text-coral" : "text-mute"}`}>
          {tokens === null ? "0" : tokens.toLocaleString()} / {cap.toLocaleString()} tok
        </span>
      </div>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised"
        role="meter"
        aria-label="Context window used by the selection and question"
        aria-valuemin={0}
        aria-valuemax={cap}
        aria-valuenow={tokens ?? 0}
      >
        <div
          className={`h-full rounded-full ${over ? "bg-coral" : "bg-cyan"}`}
          style={{ width: `${tokens === null ? 0 : Math.min(1, tokens / cap) * 100}%` }}
        />
      </div>
      {over && (
        <p className="mt-1.5 text-[13px] text-coral">
          Over the window. Select fewer lines or shorten the question.
        </p>
      )}
    </div>
  );
}

function Pips({ used, budget }: { used: number; budget: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-mute">Questions</span>
        <span
          className={`font-mono text-[13px] ${used >= budget ? "text-coral" : "text-mute"}`}
        >
          {used} of {budget} used
        </span>
      </div>
      {budget > 0 && budget <= 40 && (
        <div className="mt-2 flex gap-1.5" aria-hidden="true">
          {Array.from({ length: budget }, (_, i) => (
            <span
              key={i}
              className={`h-1.5 flex-1 rounded-full ${i < used ? "bg-cyan" : "bg-raised"}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function where(item: { file?: string | null; line_from?: number | null; line_to?: number | null }) {
  if (!item.file) return "";
  const name = baseName(item.file);
  return item.line_from && item.line_to ? `${name} ${lref(item.line_from, item.line_to)}` : name;
}

function Exchange({ item }: { item: ThreadItem }) {
  return (
    <li className="flex flex-col gap-5">
      <div className="rounded-xl bg-raised px-4 py-3.5">
        <p className="text-[12px] tracking-widest text-mute uppercase">You</p>
        <p className="mt-1.5 whitespace-pre-wrap">
          {item.question}{" "}
          <span className="font-mono text-[13px] whitespace-nowrap text-mute">{where(item)}</span>
        </p>
      </div>
      {item.refused ? (
        <Notice tone="coral" role="status">
          <span className="font-medium">Not answered.</span>{" "}
          {item.reason ? REFUSAL_TEXT[item.reason] : "The question was refused."}
          <span className="block text-[12px] opacity-80">This did not use a question.</span>
        </Notice>
      ) : (
        <div className="px-4">
          <p className="text-[12px] tracking-widest text-cyan uppercase">Assistant</p>
          <p className="mt-1.5 leading-relaxed whitespace-pre-wrap">{item.reply}</p>
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
    <aside aria-label="Assistant" className="flex min-h-0 flex-col border-l border-line bg-panel">
      <div className="flex flex-col gap-4 border-b border-line px-6 py-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold">Assistant</h2>
            <p className="mt-0.5 font-mono text-[13px] text-mute">
              {session.model} · {constrained ? "Ollama · localhost" : "Gemini API"}
            </p>
          </div>
          <span
            className={`rounded bg-raised px-2 py-1 font-mono text-[12px] leading-none tracking-wider ${
              constrained ? "text-cyan" : "text-amber"
            }`}
          >
            {constrained ? "LOCAL" : "CLOUD"}
          </span>
        </div>
        {constrained ? (
          <>
            <ContextBar session={session} selection={selection} question={question} />
            <Pips used={session.questions_used} budget={session.q_budget} />
          </>
        ) : (
          <p className="text-[13px] text-amber">
            Sees the whole file you are in, or every file when nothing is selected.{" "}
            {session.questions_used} asked so far.
          </p>
        )}
      </div>

      <ol className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-6 py-5" aria-live="polite">
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
        {ask.isPending && <li className="px-4 text-[13px] text-mute">Waiting for the model…</li>}
        <div ref={threadEnd} />
      </ol>

      <form
        className="flex flex-col gap-2.5 px-6 pt-2 pb-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (canAsk) ask.mutate();
        }}
      >
        {selection && (
          <p className="font-mono text-[13px] text-mute">
            Sending {where({ file: selection.file, line_from: selection.from, line_to: selection.to })}
          </p>
        )}
        <div className="flex items-end gap-2.5">
          <label className="min-w-0 flex-1">
            <span className="sr-only">Question</span>
            <textarea
              ref={inputRef}
              rows={1}
              className={`${INPUT} block max-h-40 min-h-12 resize-none py-3 [field-sizing:content]`}
              value={question}
              aria-invalid={tooLong}
              placeholder={constrained ? "Ask about the selected lines" : "Ask about this code"}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (canAsk) ask.mutate();
                }
              }}
            />
          </label>
          <Button
            type="submit"
            tone={constrained ? "cyan" : "amber"}
            className="min-h-12 font-semibold"
            disabled={!canAsk}
          >
            {ask.isPending ? "…" : "Send"}
          </Button>
        </div>
        {tooLong && (
          <p className="text-[13px] text-coral">
            Questions can be at most {maxQuestionChars} characters.
          </p>
        )}
        {ask.isError && <Notice tone="coral">{errorText(ask.error)}</Notice>}
        <p className="text-[13px] text-mute">
          {constrained
            ? `Every question uses one of ${session.q_budget}. Narrow selections cost fewer tokens.`
            : "No question limit in Realistic mode."}
        </p>
      </form>
    </aside>
  );
}
