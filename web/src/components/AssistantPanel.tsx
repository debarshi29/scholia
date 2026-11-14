// Assistant panel from the Session board: model line, context-window bar, question pips,
// the thread and the composer. Every question goes to the server's proxy, which enforces
// all limits; this panel only displays them.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type RefObject } from "react";
import { api, type SessionView, type ThreadItem } from "../api/client";
import { baseName, lref, REFUSAL_TEXT } from "../lib/format";
import { Chat, Cloud, Cpu, Send } from "./icons";
import { Bar, Button, Chip, errorText, INPUT, Notice } from "./ui";

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
    placeholderData: (previous) => previous,
  });
  const cap = session.ctx_cap;
  const tokens = selection ? (measure.data?.tokens ?? null) : null;
  const over = tokens !== null && tokens > cap;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] text-mute">Context window</span>
        <span className={`font-mono text-[12.5px] ${over ? "text-coral" : "text-mute"}`}>
          <span className={over ? "" : "text-ink"}>
            {tokens === null ? "0" : tokens.toLocaleString()}
          </span>{" "}
          / {cap.toLocaleString()} tok
        </span>
      </div>
      <div
        className="mt-2"
        role="meter"
        aria-label="Context window used by the selection and question"
        aria-valuemin={0}
        aria-valuemax={cap}
        aria-valuenow={tokens ?? 0}
      >
        <Bar value={tokens === null ? 0 : tokens / cap} tone={over ? "coral" : "cyan"} thin />
      </div>
      {over && (
        <p className="fade mt-1.5 text-[12.5px] text-coral">
          Over the window. Select fewer lines or shorten the question.
        </p>
      )}
    </div>
  );
}

function Pips({ used, budget }: { used: number; budget: number }) {
  const left = Math.max(0, budget - used);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] text-mute">Questions</span>
        <span className={`font-mono text-[12.5px] ${left === 0 ? "text-coral" : "text-mute"}`}>
          <span className={left === 0 ? "" : "text-ink"}>{used}</span> of {budget} used
        </span>
      </div>
      {budget > 0 && budget <= 40 && (
        <div className="mt-2 flex gap-1" aria-hidden="true">
          {Array.from({ length: budget }, (_, i) => (
            <span
              key={i}
              className={`h-1.5 flex-1 rounded-full transition-colors duration-500 ${
                i < used ? "bg-cyan" : "bg-ink/[0.08]"
              }`}
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

function Exchange({ item, amber }: { item: ThreadItem; amber: boolean }) {
  const place = where(item);
  return (
    <li className="rise flex flex-col gap-3">
      <div className="ml-6 rounded-lg rounded-tr-md border border-line bg-ink/[0.05] px-4 py-3">
        <p className="flex items-center justify-between gap-2">
          <span className="eyebrow">You</span>
          {place && <span className="font-mono text-[12px] text-mute">{place}</span>}
        </p>
        <p className="mt-1.5 whitespace-pre-wrap">{item.question}</p>
      </div>
      {item.refused ? (
        <Notice tone="coral" role="status">
          <span className="font-semibold">Not answered.</span>{" "}
          {item.reason ? REFUSAL_TEXT[item.reason] : "The question was refused."}
          <span className="mt-0.5 block text-[12px] opacity-80">This did not use a question.</span>
        </Notice>
      ) : (
        <div
          className={`mr-2 border-l-2 pl-4 ${amber ? "border-amber/50" : "border-cyan/50"}`}
        >
          <p className={`eyebrow ${amber ? "!text-amber" : "!text-cyan"}`}>Assistant</p>
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
    threadEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [session.thread.length, ask.isPending]);

  const tooLong = question.length > maxQuestionChars;
  const canAsk = question.trim().length > 0 && !tooLong && !ask.isPending;
  const sending = selection
    ? where({ file: selection.file, line_from: selection.from, line_to: selection.to })
    : null;

  return (
    <aside
      aria-label="Assistant"
      className="flex min-h-0 flex-col border-l border-line bg-panel/70 backdrop-blur"
    >
      <div className="flex flex-col gap-3.5 border-b border-line px-5 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span
              className={`flex size-9 shrink-0 items-center justify-center rounded-md ${
                constrained ? "bg-cyan/15 text-cyan" : "bg-amber/15 text-amber"
              }`}
            >
              {constrained ? <Cpu className="size-[18px]" /> : <Cloud className="size-[18px]" />}
            </span>
            <div className="min-w-0">
              <h2 className="leading-tight font-semibold">Assistant</h2>
              <p className="truncate font-mono text-[12px] text-mute">
                {session.model} · {constrained ? "Ollama" : "Gemini API"}
              </p>
            </div>
          </div>
          <Chip tone={constrained ? "cyan" : "amber"} mono>
            {constrained ? "Local" : "Cloud"}
          </Chip>
        </div>
        {constrained ? (
          <>
            <ContextBar session={session} selection={selection} question={question} />
            <Pips used={session.questions_used} budget={session.q_budget} />
          </>
        ) : (
          <p className="text-[13px] text-amber/90">
            Sees the whole file you are in, or every file when nothing is selected.{" "}
            {session.questions_used} asked so far.
          </p>
        )}
      </div>

      <ol className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 py-5" aria-live="polite">
        {session.thread.length === 0 && !ask.isPending && (
          <li className="fade my-auto flex flex-col items-center gap-3 px-4 text-center text-[13px] text-mute">
            <span className="flex size-11 items-center justify-center rounded-lg bg-ink/[0.05]">
              <Chat className="size-5" />
            </span>
            {constrained
              ? "The assistant sees only the lines you select, and it can be wrong. Check what it tells you against the code."
              : "The assistant can be wrong. Check what it tells you against the code."}
          </li>
        )}
        {session.thread.map((item) => (
          <Exchange key={item.query_id} item={item} amber={!constrained} />
        ))}
        {ask.isPending && (
          <li className="fade flex items-center gap-3 pl-4 text-[13px] text-mute">
            <span className="typing" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            Waiting for the model
          </li>
        )}
        <div ref={threadEnd} />
      </ol>

      <form
        className="flex flex-col gap-2 border-t border-line bg-bg/40 px-5 pt-3.5 pb-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (canAsk) ask.mutate();
        }}
      >
        <p className="flex items-center gap-2 text-[12.5px] text-mute">
          <span
            className={`size-1.5 rounded-full ${sending ? "bg-cyan" : "bg-mute/50"}`}
          />
          {sending ? (
            <>
              Sending <span className="font-mono text-ink">{sending}</span>
            </>
          ) : constrained ? (
            "Nothing selected yet"
          ) : (
            "Nothing selected: the whole problem is sent"
          )}
        </p>
        <div className="flex items-end gap-2">
          <label className="min-w-0 flex-1">
            <span className="sr-only">Question</span>
            <textarea
              ref={inputRef}
              rows={1}
              className={`${INPUT} block max-h-40 min-h-9 resize-none py-3 [field-sizing:content]`}
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
            className="min-h-9 px-4"
            disabled={!canAsk}
            aria-label="Send question"
          >
            Send
            <Send className="size-4" />
          </Button>
        </div>
        {tooLong && (
          <p className="text-[12.5px] text-coral">
            Questions can be at most {maxQuestionChars} characters.
          </p>
        )}
        {ask.isError && <Notice tone="coral">{errorText(ask.error)}</Notice>}
        <p className="text-[12.5px] text-mute">
          {constrained
            ? `Every question uses one of ${session.q_budget}. Narrow selections cost fewer tokens.`
            : "No question limit in Realistic mode."}
        </p>
      </form>
    </aside>
  );
}
