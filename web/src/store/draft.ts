// The report being written during a session. It lives in the browser (and localStorage,
// so a reload does not lose it) until submit; the server only sees it then.
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { BugCategory } from "../api/client";

export interface DraftFinding {
  key: string;
  file: string;
  line_from: number;
  line_to: number;
  category: BugCategory;
  explanation: string;
  fix: string;
}

export interface Draft {
  findings: DraftFinding[];
  designNotes: string;
}

const EMPTY: Draft = { findings: [], designNotes: "" };

interface DraftState {
  drafts: Record<string, Draft>;
  addFinding: (sessionId: string, file: string, from: number, to: number) => string;
  updateFinding: (sessionId: string, key: string, patch: Partial<DraftFinding>) => void;
  removeFinding: (sessionId: string, key: string) => void;
  setDesignNotes: (sessionId: string, notes: string) => void;
  clear: (sessionId: string) => void;
}

function edit(state: DraftState, sessionId: string, change: (d: Draft) => Draft) {
  return { drafts: { ...state.drafts, [sessionId]: change(state.drafts[sessionId] ?? EMPTY) } };
}

export const useDraftStore = create<DraftState>()(
  persist(
    (set) => ({
      drafts: {},
      addFinding: (sessionId, file, from, to) => {
        const key = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
        const finding: DraftFinding = {
          key,
          file,
          line_from: from,
          line_to: to,
          category: "logic",
          explanation: "",
          fix: "",
        };
        set((s) => edit(s, sessionId, (d) => ({ ...d, findings: [...d.findings, finding] })));
        return key;
      },
      updateFinding: (sessionId, key, patch) =>
        set((s) =>
          edit(s, sessionId, (d) => ({
            ...d,
            findings: d.findings.map((f) => (f.key === key ? { ...f, ...patch } : f)),
          })),
        ),
      removeFinding: (sessionId, key) =>
        set((s) =>
          edit(s, sessionId, (d) => ({ ...d, findings: d.findings.filter((f) => f.key !== key) })),
        ),
      setDesignNotes: (sessionId, notes) =>
        set((s) => edit(s, sessionId, (d) => ({ ...d, designNotes: notes }))),
      clear: (sessionId) =>
        set((s) => {
          const drafts = { ...s.drafts };
          delete drafts[sessionId];
          return { drafts };
        }),
    }),
    { name: "scholia-drafts", version: 1 },
  ),
);

export function useDraft(sessionId: string): Draft {
  return useDraftStore((s) => s.drafts[sessionId]) ?? EMPTY;
}
