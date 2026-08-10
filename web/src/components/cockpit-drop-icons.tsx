/** 上区吊舱：细吊索 + 精致矢量（透明底） */

import type { ReactNode } from "react";

type IconProps = { className?: string; active?: boolean };

export function DropPendant({
  className = "",
  children,
  wide,
}: {
  className?: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <span className={`cp-pendant ${wide ? "is-wide" : ""} ${className}`}>
      <span className="cp-pendant-cable" aria-hidden />
      <span className="cp-pendant-body">{children}</span>
    </span>
  );
}

export function DropHeadphonesIcon({ className = "", active }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 96 96" fill="none" aria-hidden>
      <defs>
        <linearGradient id="hpm" x1="20" y1="10" x2="76" y2="86">
          <stop stopColor="#e8eef8" />
          <stop offset="0.45" stopColor="#8a9bb0" />
          <stop offset="1" stopColor="#3a465a" />
        </linearGradient>
      </defs>
      <path
        d="M24 44c0-15 10-28 24-28s24 13 24 28"
        stroke="url(#hpm)"
        strokeWidth="4.5"
        strokeLinecap="round"
      />
      <path
        d="M28 44c0-12 8-22 20-22s20 10 20 22"
        stroke="#121820"
        strokeWidth="1.5"
        opacity="0.35"
      />
      <rect x="14" y="40" width="18" height="30" rx="8" fill="#161e2a" stroke="url(#hpm)" strokeWidth="2" />
      <rect x="64" y="40" width="18" height="30" rx="8" fill="#161e2a" stroke="url(#hpm)" strokeWidth="2" />
      <rect x="18" y="46" width="10" height="18" rx="4" fill="#060a10" />
      <rect x="68" y="46" width="10" height="18" rx="4" fill="#060a10" />
      <circle cx="23" cy="44" r="2.5" fill={active ? "#e8a045" : "#00d4ff"} />
      {active && (
        <circle cx="23" cy="44" r="6" stroke="#e8a045" strokeWidth="1" opacity="0.5" />
      )}
    </svg>
  );
}

export function DropIntercomIcon({ className = "", active }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 96 96" fill="none" aria-hidden>
      <defs>
        <linearGradient id="icm" x1="30" y1="8" x2="70" y2="88">
          <stop stopColor="#c5d0e0" />
          <stop offset="1" stopColor="#2a3344" />
        </linearGradient>
      </defs>
      <rect x="36" y="6" width="24" height="6" rx="1.5" fill="#3a465a" />
      <path d="M40 12h16v6H40z" fill="#1a222e" />
      <rect
        x="32"
        y="16"
        width="32"
        height="58"
        rx="10"
        fill="#121820"
        stroke="url(#icm)"
        strokeWidth="2"
      />
      <rect x="38" y="24" width="20" height="16" rx="3" fill="#0a1018" stroke="#3a465a" />
      <circle
        className="ic-led"
        cx="48"
        cy="52"
        r="6"
        fill={active ? "#00d4ff" : "#2a3548"}
        stroke="#8a9bb0"
        strokeWidth="1"
      />
      {active && (
        <circle cx="48" cy="52" r="11" stroke="#00d4ff" strokeWidth="1.2" opacity="0.45" />
      )}
      <path
        d="M40 64h16M40 69h16M40 74h10"
        stroke="#5a6578"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M64 70c10 3 14 12 14 20"
        stroke="#6a7a90"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray="1.5 2.5"
      />
    </svg>
  );
}

export function DropBadgeFrame({ children }: { children?: ReactNode }) {
  return (
    <span className="cp-badge-medal">
      <svg className="cp-badge-medal-ring" viewBox="0 0 100 100" fill="none" aria-hidden>
        <defs>
          <linearGradient id="bdg" x1="10" y1="10" x2="90" y2="90">
            <stop stopColor="#e6eef8" />
            <stop offset="0.5" stopColor="#8a9bb0" />
            <stop offset="1" stopColor="#3a465a" />
          </linearGradient>
        </defs>
        <circle cx="50" cy="50" r="46" stroke="url(#bdg)" strokeWidth="3" />
        <circle cx="50" cy="50" r="40" stroke="#00d4ff" strokeWidth="1" opacity="0.4" />
        <circle
          cx="50"
          cy="50"
          r="40"
          stroke="#8b5cf6"
          strokeWidth="1"
          opacity="0.3"
          strokeDasharray="3 5"
        />
      </svg>
      <span className="cp-badge-medal-core">{children}</span>
    </span>
  );
}
