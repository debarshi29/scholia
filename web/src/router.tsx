// A three-page app does not need a routing library: this is the History API in 40 lines.
import { useSyncExternalStore, type MouseEvent, type ReactNode } from "react";

export type Route =
  | { page: "library" }
  | { page: "profiles" }
  | { page: "session"; id: string }
  | { page: "debrief"; id: string }
  | { page: "not-found" };

export function parseRoute(pathname: string): Route {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length === 0) return { page: "library" };
  if (parts.length === 1 && parts[0] === "profiles") return { page: "profiles" };
  const [head, id] = parts;
  if (parts.length === 2 && id && (head === "session" || head === "debrief")) {
    return { page: head, id: decodeURIComponent(id) };
  }
  return { page: "not-found" };
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

export function navigate(path: string, options: { replace?: boolean } = {}): void {
  if (options.replace) window.history.replaceState(null, "", path);
  else window.history.pushState(null, "", path);
  listeners.forEach((l) => l());
}

export function usePath(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname);
}

export function Link(props: { to: string; className?: string; children: ReactNode }) {
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    navigate(props.to);
  };
  return (
    <a href={props.to} onClick={onClick} className={props.className}>
      {props.children}
    </a>
  );
}
