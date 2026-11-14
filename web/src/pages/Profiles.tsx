// Manage local profiles: switch, create, rename, set session defaults, reset the weak-spot
// stats, delete. Profiles keep progress apart on this machine; there is no login.
import ThemeToggle from "../components/ThemeToggle";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { api, type AssistantMode, type Profile } from "../api/client";
import { ArrowLeft, Plus, Trash } from "../components/icons";
import { initial } from "../components/ProfileMenu";
import { Button, Chip, errorText, INPUT, Loading, Notice, stagger } from "../components/ui";
import { percent, plural, shortDate } from "../lib/format";
import { Link, navigate } from "../router";
import { DEFAULT_PROFILE, useProfileStore } from "../store/profile";

type ModeChoice = AssistantMode | "";

function toNumber(raw: string): number | null {
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}

function Field(props: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12.5px] font-medium">{props.label}</span>
      {props.children}
      {props.hint && <span className="text-[12px] text-mute">{props.hint}</span>}
    </label>
  );
}

function Editor({ profile, onDone }: { profile: Profile; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(profile.name);
  const [mode, setMode] = useState<ModeChoice>(profile.default_mode ?? "");
  const [ctx, setCtx] = useState(profile.default_ctx_cap?.toString() ?? "");
  const [budget, setBudget] = useState(profile.default_q_budget?.toString() ?? "");
  const save = useMutation({
    mutationFn: () =>
      api.updateProfile(profile.id, {
        name: name.trim(),
        default_mode: mode === "" ? null : mode,
        default_ctx_cap: toNumber(ctx),
        default_q_budget: toNumber(budget),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      onDone();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="fade grid gap-3 border-t border-line pt-4 sm:grid-cols-2">
      <Field label="Name">
        <input
          className={INPUT}
          value={name}
          maxLength={40}
          required
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field label="Default assistant" hint="Used when you start a session from the Library.">
        <select
          className={`${INPUT} cursor-pointer`}
          value={mode}
          onChange={(e) => setMode(e.target.value as ModeChoice)}
        >
          <option value="">Server default (Constrained)</option>
          <option value="constrained">Constrained · local</option>
          <option value="realistic">Realistic · Gemini</option>
        </select>
      </Field>
      <Field label="Context window (tokens)" hint="Empty uses the server default.">
        <input
          className={INPUT}
          inputMode="numeric"
          value={ctx}
          placeholder="server default"
          onChange={(e) => setCtx(e.target.value.replace(/\D/g, ""))}
        />
      </Field>
      <Field label="Questions per session" hint="Empty uses the server default. 0 means none.">
        <input
          className={INPUT}
          inputMode="numeric"
          value={budget}
          placeholder="server default"
          onChange={(e) => setBudget(e.target.value.replace(/\D/g, ""))}
        />
      </Field>
      <div className="flex items-center gap-2 sm:col-span-2">
        <Button type="submit" compact disabled={save.isPending || name.trim() === ""}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        <Button compact variant="outline" tone="mute" onClick={onDone}>
          Cancel
        </Button>
        {save.isError && <span className="text-[12.5px] text-coral">{errorText(save.error)}</span>}
      </div>
    </form>
  );
}

function Row({ profile, index }: { profile: Profile; index: number }) {
  const queryClient = useQueryClient();
  const current = useProfileStore((s) => s.id);
  const setProfile = useProfileStore((s) => s.setProfile);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<"reset" | "delete" | null>(null);
  const isCurrent = current === profile.id;

  const use = () => {
    setProfile(profile.id);
    queryClient.clear();
    navigate("/");
  };
  const reset = useMutation({
    mutationFn: () => api.resetProfileStats(profile.id),
    onSuccess: async () => {
      setConfirm(null);
      await queryClient.invalidateQueries();
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteProfile(profile.id),
    onSuccess: async () => {
      if (isCurrent) setProfile(DEFAULT_PROFILE);
      queryClient.clear();
      await queryClient.invalidateQueries();
    },
  });
  const rate = profile.attempts > 0 ? profile.misses / profile.attempts : null;

  return (
    <li className="surface rise flex flex-col gap-3 px-4 py-3.5" style={stagger(index)}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-md bg-cyan/15 font-mono font-semibold text-cyan">
          {initial(profile.name)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 font-semibold">
            <span className="truncate">{profile.name}</span>
            {isCurrent && <Chip tone="cyan">in use</Chip>}
            {profile.is_default && <Chip>default</Chip>}
          </p>
          <p className="text-[12.5px] text-mute">
            {plural(profile.sessions, "session")} · {profile.graded} graded ·{" "}
            {plural(profile.attempts, "bug")} attempted
            {rate !== null && ` · ${percent(rate)} missed`} · since {shortDate(profile.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {!isCurrent && (
            <Button compact onClick={use}>
              Use this profile
            </Button>
          )}
          <Button compact variant="outline" tone="mute" onClick={() => setEditing((v) => !v)}>
            {editing ? "Close" : "Edit"}
          </Button>
          <Button
            compact
            variant="outline"
            tone="amber"
            disabled={profile.attempts === 0}
            onClick={() => setConfirm(confirm === "reset" ? null : "reset")}
          >
            Reset stats
          </Button>
          {!profile.is_default && (
            <Button
              compact
              variant="outline"
              tone="coral"
              aria-label={`Delete ${profile.name}`}
              onClick={() => setConfirm(confirm === "delete" ? null : "delete")}
            >
              <Trash className="size-3.5" />
              Delete
            </Button>
          )}
        </div>
      </div>
      {confirm === "reset" && (
        <div className="fade flex flex-wrap items-center gap-3 rounded-md border border-amber/30 bg-amber/10 px-3 py-2.5 text-[13px]">
          <span className="flex-1">
            Forget this profile&apos;s weak-spot counts? Its sessions and debriefs are kept.
          </span>
          <Button compact tone="amber" disabled={reset.isPending} onClick={() => reset.mutate()}>
            {reset.isPending ? "Resetting…" : "Reset stats"}
          </Button>
        </div>
      )}
      {confirm === "delete" && (
        <div className="fade flex flex-wrap items-center gap-3 rounded-md border border-coral/30 bg-coral/10 px-3 py-2.5 text-[13px]">
          <span className="flex-1">
            Delete &ldquo;{profile.name}&rdquo; with {plural(profile.sessions, "session")}, assistant
            logs and reports? This cannot be undone.
          </span>
          <Button compact tone="coral" disabled={remove.isPending} onClick={() => remove.mutate()}>
            {remove.isPending ? "Deleting…" : "Delete for good"}
          </Button>
        </div>
      )}
      {(reset.isError || remove.isError) && (
        <Notice tone="coral">{errorText(reset.error ?? remove.error)}</Notice>
      )}
      {editing && <Editor profile={profile} onDone={() => setEditing(false)} />}
    </li>
  );
}

function NewProfile() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api.createProfile({ name: name.trim() }),
    onSuccess: async () => {
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
  });
  return (
    <form
      className="surface flex flex-wrap items-end gap-3 px-4 py-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <div className="min-w-48 flex-1">
        <Field label="New profile">
          <input
            className={INPUT}
            value={name}
            maxLength={40}
            placeholder="A name, e.g. Interview prep"
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
      </div>
      <Button type="submit" disabled={create.isPending || name.trim() === ""}>
        <Plus className="size-4" />
        Add profile
      </Button>
      {create.isError && (
        <p className="w-full text-[12.5px] text-coral">{errorText(create.error)}</p>
      )}
    </form>
  );
}

export default function Profiles() {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  return (
    <>
      <header className="topbar sticky top-0 z-20 flex min-h-12 items-center gap-3 px-5">
        <Link
          to="/"
          className="flex min-h-9 items-center gap-1.5 rounded-md px-2.5 text-mute transition hover:bg-ink/5 hover:text-ink"
        >
          <ArrowLeft className="size-4" />
          Library
        </Link>
        <h1 className="text-[15px] font-semibold">Profiles</h1>
        <span className="ml-auto">
          <ThemeToggle />
        </span>
      </header>
      <div className="mx-auto flex max-w-3xl flex-col gap-4 px-5 py-6">
        <p className="text-[13px] text-mute">
          Each profile keeps its own sessions, weak-spot stats and defaults on this machine. There
          is no login: anyone using this browser can switch profiles.
        </p>
        {profiles.isError && <Notice tone="coral">{errorText(profiles.error)}</Notice>}
        {!profiles.data && !profiles.isError && <Loading label="Loading profiles…" />}
        <ul className="flex flex-col gap-3">
          {profiles.data?.map((p, i) => <Row key={p.id} profile={p} index={i} />)}
        </ul>
        <NewProfile />
      </div>
    </>
  );
}
