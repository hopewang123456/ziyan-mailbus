/** 子言·佳琦 双子星标准版 — 规范见 twin-star-logo-spec / docs HUD */

type Props = {
  size?: number;
  className?: string;
  title?: string;
};

export function TwinStarsLogo({ size = 40, className = "", title = "子言·佳琦 双子星" }: Props) {
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      {/* 子言星 · cyan */}
      <circle cx="35" cy="35" r="14" fill="none" stroke="#00d4ff" strokeWidth="2.5" opacity="0.95" />
      <circle cx="35" cy="35" r="4" fill="#00d4ff" opacity="0.9" />
      <circle cx="35" cy="35" r="20" fill="none" stroke="#00d4ff" strokeWidth="0.5" opacity="0.25">
        <animate attributeName="r" values="20;28;20" dur="2.5s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.25;0;0.25" dur="2.5s" repeatCount="indefinite" />
      </circle>
      <circle cx="35" cy="35" r="28" fill="none" stroke="#00d4ff" strokeWidth="0.3" opacity="0.12">
        <animate attributeName="r" values="28;36;28" dur="3.5s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.15;0;0.15" dur="3.5s" repeatCount="indefinite" />
      </circle>
      {/* 佳琦星 · purple */}
      <circle cx="65" cy="65" r="11" fill="none" stroke="#8b5cf6" strokeWidth="2" opacity="0.95" />
      <circle cx="65" cy="65" r="3" fill="#8b5cf6" opacity="0.9" />
      <circle cx="65" cy="65" r="15" fill="none" stroke="#8b5cf6" strokeWidth="0.5" opacity="0.2">
        <animate attributeName="r" values="15;22;15" dur="2.5s" begin="1.25s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.2;0;0.2" dur="2.5s" begin="1.25s" repeatCount="indefinite" />
      </circle>
      {/* 轨道 */}
      <ellipse
        cx="50"
        cy="50"
        rx="32"
        ry="10"
        fill="none"
        stroke="rgba(0,212,255,0.12)"
        strokeWidth="0.5"
        transform="rotate(-15 50 50)"
      />
      <ellipse
        cx="50"
        cy="50"
        rx="26"
        ry="8"
        fill="none"
        stroke="rgba(139,92,246,0.1)"
        strokeWidth="0.5"
        transform="rotate(10 50 50)"
      />
      {/* 信号连接 */}
      <path
        d="M42 42 Q52 35 56 56"
        fill="none"
        stroke="#00d4ff"
        strokeWidth="0.8"
        strokeDasharray="3 3"
        opacity="0.4"
      >
        <animate attributeName="stroke-dashoffset" values="0;-18" dur="2s" repeatCount="indefinite" />
      </path>
      <path
        d="M50 50 Q58 45 60 60"
        fill="none"
        stroke="#8b5cf6"
        strokeWidth="0.6"
        strokeDasharray="2 2"
        opacity="0.28"
      >
        <animate attributeName="stroke-dashoffset" values="0;-12" dur="2.4s" begin="0.4s" repeatCount="indefinite" />
      </path>
      {/* 小行星 · agents */}
      <circle cx="75" cy="12" r="1.5" fill="rgba(255,255,255,0.25)" />
      <circle cx="12" cy="75" r="1.5" fill="rgba(255,255,255,0.2)" />
      <circle cx="88" cy="40" r="1" fill="rgba(255,255,255,0.15)" />
      <circle cx="18" cy="22" r="1" fill="rgba(255,255,255,0.12)" />
      <circle cx="80" cy="78" r="1.2" fill="rgba(255,255,255,0.18)" />
    </svg>
  );
}
