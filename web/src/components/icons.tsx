// A small stroke icon set, drawn inline so there is no icon dependency.
import type { ReactNode } from "react";

interface Props {
  className?: string;
}

function Svg(props: Props & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={props.className ?? "size-4"}
    >
      {props.children}
    </svg>
  );
}

export const ArrowLeft = (p: Props) => (
  <Svg {...p}>
    <path d="M19 12H5M11 6l-6 6 6 6" />
  </Svg>
);
export const ArrowRight = (p: Props) => (
  <Svg {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Svg>
);
export const FileCode = (p: Props) => (
  <Svg {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5M10 13l-2 2 2 2M14 13l2 2-2 2" />
  </Svg>
);
export const Clock = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Svg>
);
export const Flag = (p: Props) => (
  <Svg {...p}>
    <path d="M5 21V4M5 4h11l-2 4 2 4H5" />
  </Svg>
);
export const Chat = (p: Props) => (
  <Svg {...p}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
  </Svg>
);
export const Send = (p: Props) => (
  <Svg {...p}>
    <path d="M4 12l16-8-6 16-3-7z" />
  </Svg>
);
export const Check = (p: Props) => (
  <Svg {...p}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Svg>
);
export const Target = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="12" r="5" />
    <circle cx="12" cy="12" r="1" />
  </Svg>
);
export const Eye = (p: Props) => (
  <Svg {...p}>
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
);
export const Layers = (p: Props) => (
  <Svg {...p}>
    <path d="M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5" />
  </Svg>
);
export const Chevron = (p: Props) => (
  <Svg {...p}>
    <path d="M6 9l6 6 6-6" />
  </Svg>
);
export const Cpu = (p: Props) => (
  <Svg {...p}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
    <path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" />
  </Svg>
);
export const Cloud = (p: Props) => (
  <Svg {...p}>
    <path d="M7 18a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 18 10.5a3.75 3.75 0 0 1-.5 7.5z" />
  </Svg>
);
export const Refresh = (p: Props) => (
  <Svg {...p}>
    <path d="M20 11a8 8 0 0 0-14.6-3.5M4 4v4h4M4 13a8 8 0 0 0 14.6 3.5M20 20v-4h-4" />
  </Svg>
);
export const Trash = (p: Props) => (
  <Svg {...p}>
    <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
  </Svg>
);

/** The app mark: a magnifier over code lines. */
export function Mark(props: Props) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={props.className ?? "size-7"}>
      <defs>
        <linearGradient id="mark-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7fdcf5" />
          <stop offset="1" stopColor="#3aa9cf" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#mark-g)" />
      <path
        d="M9 11h8M9 16h5M9 21h7"
        stroke="#0e1116"
        strokeWidth="2.4"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="21" cy="18" r="4.2" stroke="#0e1116" strokeWidth="2.4" fill="none" />
      <path d="M24.2 21.2l2.6 2.6" stroke="#0e1116" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export const User = (p: Props) => (
  <Svg {...p}>
    <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20a7.5 7.5 0 0 1 15 0" />
  </Svg>
);
export const Plus = (p: Props) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);
