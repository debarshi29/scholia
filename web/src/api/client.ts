// Typed client for the FastAPI app. The types come from `pnpm gen:api`.
// The browser never talks to Ollama or Gemini: every model call goes through /api.
import { DEFAULT_PROFILE, useProfileStore } from "../store/profile";
import type { components } from "./schema";

type S = components["schemas"];

export type ProblemCard = S["ProblemCard"];
export type CategoryStat = S["CategoryStat"];
export type LibrarySettings = S["LibrarySettings"];
export type SessionCreate = S["SessionCreate"];
export type SessionSummary = S["SessionSummary"];
export type SessionView = S["SessionView"];
export type SourceFile = S["SourceFile"];
export type ThreadItem = S["ThreadItem"];
export type AskRequest = S["AskRequest"];
export type AskResult = S["AskResult"];
export type MeasureRequest = S["MeasureRequest"];
export type MeasureResult = S["MeasureResult"];
export type Finding = S["Finding"];
export type Report = S["Report"];
export type SubmitResult = S["SubmitResult"];
export type Debrief = S["Debrief"];
export type DebriefBug = S["DebriefBug"];
export type DebriefFinding = S["DebriefFinding"];
export type DebriefAudit = S["DebriefAudit"];
export type StatDelta = S["StatDelta"];
export type BugCategory = S["BugCategory"];
export type AssistantMode = S["AssistantMode"];
export type RefusalReason = S["RefusalReason"];
export type OutcomeStatus = S["OutcomeStatus"];
export type ClaimVerdict = S["ClaimVerdict"];
export type Source = S["Source"];
export type Profile = S["ProfileView"];
export type ProfileCreate = S["ProfileCreate"];
export type ProfileUpdate = S["ProfileUpdate"];

/** An error in the API's envelope: `{"error": {"code", "message"}}`. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      method,
      headers: {
        "X-Profile": useProfileStore.getState().id,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the Scholia server. Is it running?");
  }
  const text = await resp.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!resp.ok) {
    const err = (data as { error?: { code?: string; message?: string } } | null)?.error;
    if (err?.code === "profile_not_found" && useProfileStore.getState().id !== DEFAULT_PROFILE) {
      // The profile was deleted (maybe in another tab): fall back to the default one.
      useProfileStore.getState().setProfile(DEFAULT_PROFILE);
      window.location.assign("/");
    }
    throw new ApiError(
      resp.status,
      err?.code ?? "http_error",
      err?.message ?? `The server returned ${resp.status}.`,
    );
  }
  return data as T;
}

const session = (id: string) => `/api/sessions/${encodeURIComponent(id)}`;

export const api = {
  problems: () => request<ProblemCard[]>("GET", "/api/problems"),
  stats: () => request<CategoryStat[]>("GET", "/api/stats"),
  settings: () => request<LibrarySettings>("GET", "/api/settings"),
  sessions: () => request<SessionSummary[]>("GET", "/api/sessions"),
  createSession: (body: SessionCreate) => request<SessionView>("POST", "/api/sessions", body),
  session: (id: string) => request<SessionView>("GET", session(id)),
  ask: (id: string, body: AskRequest) => request<AskResult>("POST", `${session(id)}/ask`, body),
  measure: (id: string, body: MeasureRequest) =>
    request<MeasureResult>("POST", `${session(id)}/measure`, body),
  submit: (id: string, body: Report) =>
    request<SubmitResult>("POST", `${session(id)}/submit`, body),
  debrief: (id: string) => request<Debrief>("GET", `${session(id)}/debrief`),
  profiles: () => request<Profile[]>("GET", "/api/profiles"),
  createProfile: (body: ProfileCreate) => request<Profile>("POST", "/api/profiles", body),
  updateProfile: (id: string, body: ProfileUpdate) =>
    request<Profile>("PATCH", `/api/profiles/${encodeURIComponent(id)}`, body),
  resetProfileStats: (id: string) =>
    request<Profile>("POST", `/api/profiles/${encodeURIComponent(id)}/reset-stats`),
  deleteProfile: (id: string) =>
    request<null>("DELETE", `/api/profiles/${encodeURIComponent(id)}`),
  markValidity: (id: string, findingId: number, valid: boolean) =>
    request<DebriefFinding>("POST", `${session(id)}/findings/${findingId}/validity`, { valid }),
  regrade: (id: string) => request<{ status: string }>("POST", `${session(id)}/regrade`),
};
