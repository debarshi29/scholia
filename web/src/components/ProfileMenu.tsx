// The profile switcher in the top bar: who is practising, a list to switch, and a link to
// manage profiles. Switching clears the query cache, because every number on screen
// (stats, history, defaults) belongs to the profile.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type Profile } from "../api/client";
import { navigate } from "../router";
import { useProfileStore } from "../store/profile";
import { Check, Chevron, User } from "./icons";

export function initial(name: string): string {
  return (name.trim()[0] ?? "?").toUpperCase();
}

export default function ProfileMenu() {
  const id = useProfileStore((s) => s.id);
  const setProfile = useProfileStore((s) => s.setProfile);
  const queryClient = useQueryClient();
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const list: Profile[] = profiles.data ?? [];
  const current = list.find((p) => p.id === id);
  const name = current?.name ?? "Profile";

  const choose = (p: Profile) => {
    setOpen(false);
    if (p.id === id) return;
    setProfile(p.id);
    queryClient.clear();
    navigate("/");
  };

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-9 items-center gap-2 rounded-md border border-line px-2.5 text-[13px] transition hover:border-mute/60 hover:bg-raised"
      >
        <span className="flex size-5 items-center justify-center rounded bg-cyan/15 font-mono text-[11px] font-semibold text-cyan">
          {current ? initial(name) : <User className="size-3.5" />}
        </span>
        <span className="max-w-32 truncate">{name}</span>
        <Chevron className={`size-3.5 text-mute transition-transform ${open ? "" : "rotate-180"}`} />
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Profiles"
          className="fade surface absolute right-0 z-30 mt-1.5 w-60 p-1.5"
        >
          <p className="eyebrow px-2 pt-1 pb-1.5">Practising as</p>
          <ul>
            {list.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  role="menuitemradio"
                  aria-checked={p.id === id}
                  onClick={() => choose(p)}
                  className="flex min-h-9 w-full items-center gap-2.5 rounded-md px-2 text-left text-[13px] transition hover:bg-ink/[0.05]"
                >
                  <span className="flex size-5 shrink-0 items-center justify-center rounded bg-ink/[0.07] font-mono text-[11px] text-mute">
                    {initial(p.name)}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{p.name}</span>
                  <span className="font-mono text-[11.5px] text-mute">{p.sessions}</span>
                  {p.id === id && <Check className="size-3.5 text-cyan" />}
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-1 border-t border-line pt-1">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                navigate("/profiles");
              }}
              className="flex min-h-9 w-full items-center rounded-md px-2 text-left text-[13px] text-mute transition hover:bg-ink/[0.05] hover:text-ink"
            >
              Manage profiles…
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
