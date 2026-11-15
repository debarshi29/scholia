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
  planted: "Algorithms",
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
  backend_error: "The model could not be reached or returned nothing.",
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

/** `L18` or `L30–L36`, the way the boards write line references. */
export function lref(from: number, to: number): string {
  return from === to ? `L${from}` : `L${from}–L${to}`;
}

/** The short project name shown in titles and lists. The algorithms repo is called "Python",
 * which says nothing, so it is shown as "algorithms". */
export function repoLabel(originRepo: string): string {
  if (originRepo.toLowerCase() === "thealgorithms/python") return "algorithms";
  return originRepo.split("/").pop() ?? originRepo;
}

/** A display name for a problem: problems have ids, not titles. `django: deletion`. */
export function problemTitle(originRepo: string, files: string[]): string {
  const repo = repoLabel(originRepo);
  const path = files[0] ?? "";
  const stem = baseName(path).replace(/\.py$/, "");
  // A package's __init__.py is better named by its folder.
  const first = stem === "__init__" ? (path.split("/").slice(-2, -1)[0] ?? stem) : stem;
  return first ? `${repo}: ${first}` : repo;
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** Bar colour for a miss rate: coral from 40%, amber from 20%, green below. */
export function rateTone(rate: number): "coral" | "amber" | "green" {
  return rate >= 0.4 ? "coral" : rate >= 0.2 ? "amber" : "green";
}
