// Small shared building blocks. Controls are real buttons and labelled inputs with
// 44 px minimum targets and the global focus ring (CLAUDE.md §8, accessibility).
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { ApiError } from "../api/client";

type Tone = "cyan" | "amber" | "coral" | "green" | "mute";

const SOLID: Record<Tone, string> = {
  cyan: "bg-cyan text-bg hover:brightness-110",
  amber: "bg-amber text-bg hover:brightness-110",
  coral: "bg-coral text-bg hover:brightness-110",
  green: "bg-green text-bg hover:brightness-110",
  mute: "bg-raised text-ink hover:bg-line",
};

const OUTLINE: Record<Tone, string> = {
  cyan: "border-cyan/60 text-cyan hover:bg-cyan/10",
  amber: "border-amber/60 text-amber hover:bg-amber/10",
  coral: "border-coral/60 text-coral hover:bg-coral/10",
  green: "border-green/60 text-green hover:bg-green/10",
  mute: "border-line text-ink hover:bg-raised",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: Tone;
  variant?: "solid" | "outline";
  compact?: boolean;
}

export function Button({
  tone = "cyan",
  variant = "solid",
  compact = false,
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  const look = variant === "solid" ? SOLID[tone] : `border ${OUTLINE[tone]}`;
  return (
    <button
      type={type}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-md font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${compact ? "px-3 text-[13px]" : "px-4"} ${look} ${className}`}
      {...rest}
    />
  );
}

const BADGE: Record<Tone, string> = {
  cyan: "border-cyan/40 bg-cyan/10 text-cyan",
  amber: "border-amber/40 bg-amber/10 text-amber",
  coral: "border-coral/40 bg-coral/10 text-coral",
  green: "border-green/40 bg-green/10 text-green",
  mute: "border-line bg-raised text-mute",
};

export function Badge(props: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={props.title}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[12px] font-medium leading-none whitespace-nowrap ${BADGE[props.tone ?? "mute"]}`}
    >
      {props.children}
    </span>
  );
}

export function Panel(props: {
  title?: ReactNode;
  aside?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <section className={`rounded-lg border border-line bg-panel ${props.className ?? ""}`}>
      {props.title !== undefined && (
        <header className="flex min-h-11 items-center justify-between gap-3 border-b border-line px-4">
          <h2 className="text-[13px] font-semibold tracking-wide text-mute uppercase">
            {props.title}
          </h2>
          {props.aside}
        </header>
      )}
      <div className={props.bodyClassName ?? "p-4"}>{props.children}</div>
    </section>
  );
}

export const INPUT =
  "min-h-11 w-full rounded-md border border-line bg-bg px-3 text-ink placeholder:text-mute/60 focus-visible:border-cyan";

export function Notice(props: { tone?: Tone; children: ReactNode; role?: "alert" | "status" }) {
  const tone = props.tone ?? "mute";
  return (
    <div
      role={props.role ?? (tone === "coral" ? "alert" : "status")}
      className={`rounded-md border px-3 py-2 text-[13px] ${BADGE[tone]}`}
    >
      {props.children}
    </div>
  );
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function Loading(props: { label?: string }) {
  return (
    <p role="status" className="p-6 text-mute">
      {props.label ?? "Loading…"}
    </p>
  );
}

/** The two-option pill switch from the boards. One option is always selected. */
export function Segmented<T extends string>(props: {
  label: string;
  value: T;
  options: { value: T; label: string; disabled?: boolean; title?: string }[];
  onChange?: (value: T) => void;
  tone?: "cyan" | "amber";
}) {
  const active = props.tone === "amber" ? "bg-amber text-bg" : "bg-cyan text-bg";
  return (
    <div
      role="radiogroup"
      aria-label={props.label}
      className="flex gap-1 rounded-xl border border-line bg-bg p-1.5"
    >
      {props.options.map((o) => {
        const checked = o.value === props.value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={checked}
            title={o.title}
            disabled={o.disabled || (!props.onChange && !checked)}
            onClick={() => props.onChange?.(o.value)}
            className={`min-h-11 flex-1 rounded-lg px-4 font-semibold whitespace-nowrap transition disabled:cursor-not-allowed ${
              checked ? active : "text-mute enabled:hover:text-ink disabled:opacity-60"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
