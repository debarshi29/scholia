import type {
  BugCategory,
  ClaimVerdict,
  OutcomeStatus,
  RefusalReason,
  Source,
} from "../api/client";

export const CATEGORIES: BugCategory[] = [
  "logic",
  "boundary",
  "null_empty",
  "shared_mutable_state",
  "concurrency",
  "resource_leak",
  "error_handling",
  "complexity",
];

export const CATEGORY_LABEL: Record<BugCategory, string> = {
  logic: "Logic",
  boundary: "Boundary",
  null_empty: "Null / empty",
  shared_mutable_state: "Shared mutable state",
  concurrency: "Concurrency",
  resource_leak: "Resource leak",
  error_handling: "Error handling",
  complexity: "Complexity",
};

export const SOURCE_LABEL: Record<Source, string> = {
  swebench: "SWE-bench Lite",
  bugsinpy: "BugsInPy",
};

export const STATUS_LABEL: Record<OutcomeStatus, string> = {
  found: "Found",
  partial: "Partial",
  missed: "Missed",
  extra: "Extra",
  ungraded: "Ungraded",
};

export const VERDICT_LABEL: Record<ClaimVerdict, string> = {
  correct: "Correct",
  wrong: "Wrong",
  unverifiable: "Unverifiable",
};

/** Why the proxy refused a question, in plain words. */
export const REFUSAL_TEXT: Record<RefusalReason, string> = {
  no_selection: "Select the lines you want to ask about first.",
  invalid_selection: "That selection is not valid for this file.",
  question_too_long: "The question is too long.",
  over_ctx_cap: "The selection and question are over the context cap. Select fewer lines.",
  budget_exhausted: "The question budget is used up.",
  licence_not_allowed: "This problem's licence does not allow sending it to the cloud model.",
  backend_error: "The model could not be reached. This did not cost a question.",
};

/** `mm:ss`, or `h:mm:ss` from one hour up. */
export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s % 60)}` : `${pad(m)}:${pad(s % 60)}`;
}

export function lineRange(from: number, to: number): string {
  return from === to ? `line ${from}` : `lines ${from}–${to}`;
}

export function percent(rate: number | null | undefined): string {
  return rate == null ? "–" : `${Math.round(rate * 100)}%`;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function baseName(path: string): string {
  return path.split("/").pop() ?? path;
}
