// Small shared building blocks. Controls are real buttons and labelled inputs with
// 44 px minimum targets and the global focus ring (CLAUDE.md §8, accessibility).
import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import { ApiError } from "../api/client";

export type Tone = "cyan" | "amber" | "coral" | "green" | "mute";

const SOLID: Record<Tone, string> = {
  cyan: "bg-gradient-to-b from-[#74d6f2] to-[#49b9dc] text-bg shadow-[0_10px_26px_-10px_rgb(92_200_232/0.75),inset_0_1px_0_rgb(255_255_255/0.35)]",
  amber:
    "bg-gradient-to-b from-[#f7c56d] to-[#eda636] text-bg shadow-[0_10px_26px_-10px_rgb(242_178_74/0.7),inset_0_1px_0_rgb(255_255_255/0.35)]",
  coral:
    "bg-gradient-to-b from-[#ff9285] to-[#f96a5a] text-bg shadow-[0_10px_26px_-10px_rgb(255_122_107/0.7),inset_0_1px_0_rgb(255_255_255/0.3)]",
  green:
    "bg-gradient-to-b from-[#86dca0] to-[#5cc47c] text-bg shadow-[0_10px_26px_-10px_rgb(111_208_140/0.7),inset_0_1px_0_rgb(255_255_255/0.3)]",
  mute: "bg-raised text-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.06)] hover:bg-line",
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
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl font-semibold transition duration-200 ease-out enabled:hover:-translate-y-px enabled:hover:brightness-110 enabled:active:translate-y-0 enabled:active:brightness-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none ${compact ? "px-3.5 text-[13px]" : "px-5"} ${look} ${className}`}
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
  "min-h-11 w-full rounded-xl border border-line bg-bg/70 px-3.5 text-ink shadow-[inset_0_1px_2px_rgb(0_0_0/0.35)] transition duration-200 placeholder:text-mute/55 hover:border-mute/50 focus:border-cyan focus:bg-bg focus:outline-none focus:ring-2 focus:ring-cyan/25";

export function Notice(props: { tone?: Tone; children: ReactNode; role?: "alert" | "status" }) {
  const tone = props.tone ?? "mute";
  return (
    <div
      role={props.role ?? (tone === "coral" ? "alert" : "status")}
      className={`fade rounded-xl border px-3.5 py-2.5 text-[13px] ${CHIP[tone]}`}
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
      ? "from-[#f7c56d] to-[#eda636] shadow-[0_8px_20px_-8px_rgb(242_178_74/0.8)]"
      : props.tone === "green"
        ? "from-[#8fe0a6] to-[#52bd75] shadow-[0_8px_20px_-8px_rgb(111_208_140/0.8)]"
        : "from-[#74d6f2] to-[#49b9dc] shadow-[0_8px_20px_-8px_rgb(92_200_232/0.8)]";
  return (
    <div
      role="radiogroup"
      aria-label={props.label}
      className="relative grid grid-cols-2 rounded-2xl border border-line bg-bg/80 p-1.5 shadow-[inset_0_1px_3px_rgb(0_0_0/0.5)]"
    >
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute inset-y-1.5 left-1.5 w-[calc(50%-0.375rem)] rounded-xl bg-gradient-to-b transition-transform duration-300 ease-[cubic-bezier(0.2,0.7,0.2,1)] ${thumb}`}
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
            className={`relative z-10 rounded-xl font-semibold whitespace-nowrap transition-colors duration-200 disabled:cursor-not-allowed ${
              props.compact ? "min-h-11 px-3.5 text-[13px]" : "min-h-11 px-4"
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
