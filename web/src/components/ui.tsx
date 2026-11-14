// Small shared building blocks. Controls are real buttons and labelled inputs with
// 44 px minimum targets and the global focus ring (CLAUDE.md §8, accessibility).
import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import { ApiError } from "../api/client";

export type Tone = "cyan" | "amber" | "coral" | "green" | "mute";

const SOLID: Record<Tone, string> = {
  cyan: "bg-cyan text-bg hover:bg-[#7fd6ef]",
  amber: "bg-amber text-bg hover:bg-[#f5c36a]",
  coral: "bg-coral text-bg hover:bg-[#ff9285]",
  green: "bg-green text-bg hover:bg-[#8adca2]",
  mute: "bg-raised text-ink hover:bg-line",
};

const OUTLINE: Record<Tone, string> = {
  cyan: "border-cyan/50 text-cyan hover:border-cyan hover:bg-cyan/10",
  amber: "border-amber/50 text-amber hover:border-amber hover:bg-amber/10",
  coral: "border-coral/50 text-coral hover:border-coral hover:bg-coral/10",
  green: "border-green/50 text-green hover:border-green hover:bg-green/10",
  mute: "border-line text-ink hover:border-mute/60 hover:bg-raised",
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
      className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-md font-medium transition duration-150 ease-out enabled:active:brightness-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none ${compact ? "min-h-8 px-3 text-[12.5px]" : "px-4 text-[13.5px]"} ${look} ${className}`}
      {...rest}
    />
  );
}

const CHIP: Record<Tone, string> = {
  cyan: "border-cyan/30 bg-cyan/10 text-cyan",
  amber: "border-amber/30 bg-amber/10 text-amber",
  coral: "border-coral/30 bg-coral/10 text-coral",
  green: "border-green/30 bg-green/10 text-green",
  mute: "border-line bg-white/[0.04] text-mute",
};
const DOT: Record<Tone, string> = {
  cyan: "bg-cyan",
  amber: "bg-amber",
  coral: "bg-coral",
  green: "bg-green",
  mute: "bg-mute/70",
};

/** A small status pill, optionally with a coloured dot. */
export function Chip(props: { tone?: Tone; dot?: boolean; mono?: boolean; children: ReactNode }) {
  const tone = props.tone ?? "mute";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] leading-none font-medium whitespace-nowrap ${
        props.mono ? "font-mono tracking-wide uppercase" : ""
      } ${CHIP[tone]}`}
    >
      {props.dot && <span className={`size-1.5 rounded-full ${DOT[tone]}`} />}
      {props.children}
    </span>
  );
}

export const INPUT =
  "min-h-9 w-full rounded-md border border-line bg-bg/70 px-3.5 text-ink transition duration-200 placeholder:text-mute/55 hover:border-mute/50 focus:border-cyan focus:bg-bg focus:outline-none focus:ring-2 focus:ring-cyan/25";

export function Notice(props: { tone?: Tone; children: ReactNode; role?: "alert" | "status" }) {
  const tone = props.tone ?? "mute";
  return (
    <div
      role={props.role ?? (tone === "coral" ? "alert" : "status")}
      className={`fade rounded-md border px-3.5 py-2.5 text-[13px] ${CHIP[tone]}`}
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
    <div role="status" className="flex items-center gap-3 p-8 text-mute">
      <span className="typing" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      {props.label ?? "Loading…"}
    </div>
  );
}

/** A shimmering placeholder block shown while data loads. */
export function Skeleton(props: { className?: string }) {
  return <div aria-hidden="true" className={`skeleton ${props.className ?? "h-6"}`} />;
}

/** `style` for a staggered `.rise` entrance. */
export function stagger(i: number): CSSProperties {
  return { "--i": Math.min(i, 14) } as CSSProperties;
}

const BAR_FILL: Record<Exclude<Tone, "mute">, string> = {
  cyan: "bar-cyan",
  amber: "bar-amber",
  coral: "bar-coral",
  green: "bar-green",
};

/** A meter bar with an animated, glowing fill. */
export function Bar(props: { value: number; tone: Exclude<Tone, "mute">; label?: string; thin?: boolean }) {
  const pct = Math.max(0, Math.min(1, props.value)) * 100;
  return (
    <span
      className={`bar-track block ${props.thin ? "h-1.5" : "h-2"}`}
      role={props.label ? "img" : undefined}
      aria-label={props.label}
      aria-hidden={props.label ? undefined : true}
    >
      <span
        className={`bar-fill ${BAR_FILL[props.tone]}`}
        style={{ width: `${pct > 0 ? Math.max(pct, 2.5) : 0}%` }}
      />
    </span>
  );
}

/** The pill switch from the boards, with a thumb that slides between two options. */
export function Segmented<T extends string>(props: {
  label: string;
  value: T;
  options: [Option<T>, Option<T>];
  onChange?: (value: T) => void;
  tone?: "cyan" | "amber" | "green";
  compact?: boolean;
}) {
  const index = props.options.findIndex((o) => o.value === props.value);
  const thumb =
    props.tone === "amber"
      ? "bg-amber"
      : props.tone === "green"
        ? "bg-green"
        : "bg-cyan";
  return (
    <div
      role="radiogroup"
      aria-label={props.label}
      className="relative grid grid-cols-2 rounded-lg border border-line bg-bg/80 p-0.5"
    >
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute inset-y-0.5 left-0.5 w-[calc(50%-0.25rem)] rounded-md transition-transform duration-300 ease-[cubic-bezier(0.2,0.7,0.2,1)] ${thumb}`}
        style={{ transform: `translateX(${index === 1 ? "100%" : "0"})` }}
      />
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
            className={`relative z-10 rounded-md font-medium whitespace-nowrap transition-colors duration-200 disabled:cursor-not-allowed ${
              props.compact ? "min-h-8 px-3 text-[12.5px]" : "min-h-9 px-4 text-[13px]"
            } ${checked ? "text-bg" : "text-mute enabled:hover:text-ink disabled:opacity-55"}`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

interface Option<T> {
  value: T;
  label: string;
  disabled?: boolean;
  title?: string;
}
