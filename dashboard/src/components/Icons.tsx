// サイドバー・issue一覧で共有するアイコン（Claude Design ProducerDesk.dc.htmlのSVGに対応）。

const BASE = {
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export function WarningIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      strokeWidth="2.3"
      style={{ flex: "none" }}
      aria-hidden="true"
      {...BASE}
    >
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

export function DashboardIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      strokeWidth="2"
      style={{ flex: "none" }}
      aria-hidden="true"
      {...BASE}
    >
      <rect x="2.5" y="3.5" width="16" height="17" rx="2" />
      <path d="M18.5 8h3M18.5 12h3M18.5 16h3" />
      <rect x="6" y="7.5" width="4.5" height="9" rx=".6" strokeWidth="1.7" />
      <rect x="12.5" y="7.5" width="2.5" height="3" rx=".5" strokeWidth="1.7" />
      <rect
        x="12.5"
        y="13"
        width="2.5"
        height="3.5"
        rx=".5"
        strokeWidth="1.7"
      />
    </svg>
  );
}

export function IssuesIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      strokeWidth="2"
      style={{ flex: "none" }}
      aria-hidden="true"
      {...BASE}
    >
      <rect x="3.5" y="3.5" width="17" height="17" rx="1.5" />
      <path d="M11 8h6M11 12h6M11 16h6" />
      <path d="M7.5 8h.01M7.5 12h.01M7.5 16h.01" strokeWidth="2.6" />
    </svg>
  );
}

export function ExternalLinkIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      strokeWidth="2.2"
      style={{ flex: "none" }}
      aria-hidden="true"
      {...BASE}
    >
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <path d="M15 3h6v6M10 14 21 3" />
    </svg>
  );
}
