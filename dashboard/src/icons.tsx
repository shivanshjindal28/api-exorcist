/* The console's icons: 24-unit stroke drawings in the style of the Lucide set,
 * written out here so the dashboard keeps React as its only runtime
 * dependency. Every icon is decorative (aria-hidden); the text beside it
 * carries the meaning. */

import type { ReactNode } from "react";

type IconProps = { size?: number; className?: string };

function icon(paths: ReactNode) {
  return function Icon({ size = 18, className }: IconProps) {
    return (
      <svg
        className={className ? `icon ${className}` : "icon"}
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        {paths}
      </svg>
    );
  };
}

export const IconOverview = icon(
  <>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </>,
);

export const IconProjects = icon(
  <>
    <path d="M4 20h16a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-7.9a1 1 0 0 1-.8-.4L9.6 4.4A1 1 0 0 0 8.8 4H4a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1Z" />
    <path d="m10 13 2 2 4-4" />
  </>,
);

export const IconBank = icon(
  <>
    <path d="M3 21h18" />
    <path d="M5 21V10" />
    <path d="M10 21V10" />
    <path d="M14 21V10" />
    <path d="M19 21V10" />
    <path d="m2 10 10-6 10 6" />
  </>,
);

export const IconPlus = icon(
  <>
    <path d="M12 5v14" />
    <path d="M5 12h14" />
  </>,
);

export const IconScan = icon(
  <>
    <path d="M3 7V5a2 2 0 0 1 2-2h2" />
    <path d="M17 3h2a2 2 0 0 1 2 2v2" />
    <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
    <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
    <circle cx="11.5" cy="11.5" r="3.5" />
    <path d="m16 16-2-2" />
  </>,
);

export const IconSun = icon(
  <>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </>,
);

export const IconMoon = icon(<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />);

export const IconLogOut = icon(
  <>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <path d="m16 17 5-5-5-5" />
    <path d="M21 12H9" />
  </>,
);

export const IconChevronDown = icon(<path d="m6 9 6 6 6-6" />);

export const IconCollapse = icon(
  <>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M9 3v18" />
    <path d="m16 15-3-3 3-3" />
  </>,
);

export const IconExpand = icon(
  <>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M9 3v18" />
    <path d="m14 9 3 3-3 3" />
  </>,
);

export const IconCheck = icon(<path d="M20 6 9 17l-5-5" />);

export const IconCheckCircle = icon(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="m8.5 12 2.5 2.5 4.5-5" />
  </>,
);

export const IconAlert = icon(
  <>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    <path d="M12 9v4" />
    <path d="M12 17h.01" />
  </>,
);

export const IconInfo = icon(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 16v-4" />
    <path d="M12 8h.01" />
  </>,
);

export const IconX = icon(
  <>
    <path d="M18 6 6 18" />
    <path d="m6 6 12 12" />
  </>,
);

export const IconShield = icon(
  <>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
    <path d="m9 12 2 2 4-4" />
  </>,
);

export const IconGhost = icon(
  <>
    <path d="M9 10h.01" />
    <path d="M15 10h.01" />
    <path d="M12 2a8 8 0 0 0-8 8v12l3-3 2.5 2.5L12 19l2.5 2.5L17 19l3 3V10a8 8 0 0 0-8-8Z" />
  </>,
);

export const IconEndpoint = icon(
  <>
    <path d="m8 3-5 9 5 9" />
    <path d="m16 3 5 9-5 9" />
    <path d="M12 8v8" />
  </>,
);

export const IconActivity = icon(<path d="M22 12h-4l-3 9L9 3l-3 9H2" />);

export const IconGraph = icon(
  <>
    <circle cx="5" cy="6" r="2.5" />
    <circle cx="19" cy="6" r="2.5" />
    <circle cx="12" cy="18" r="2.5" />
    <path d="M7.5 6h9" />
    <path d="m6.3 8.2 4.4 7.6" />
    <path d="m17.7 8.2-4.4 7.6" />
  </>,
);

export const IconAudit = icon(
  <>
    <path d="M9 12h6" />
    <path d="M9 16h6" />
    <path d="M14 3v4a1 1 0 0 0 1 1h4" />
    <path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2Z" />
  </>,
);

export const IconChart = icon(
  <>
    <path d="M3 3v18h18" />
    <path d="M7 16v-4" />
    <path d="M12 16V8" />
    <path d="M17 16v-7" />
  </>,
);

export const IconLock = icon(
  <>
    <rect x="4" y="11" width="16" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </>,
);

export const IconExternal = icon(
  <>
    <path d="M15 3h6v6" />
    <path d="M10 14 21 3" />
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
  </>,
);

export const IconGlobe = icon(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a14 14 0 0 1 0 18" />
    <path d="M12 3a14 14 0 0 0 0 18" />
  </>,
);

export const IconWorkflow = icon(
  <>
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
    <path d="M6.5 10v3a2 2 0 0 0 2 2H14" />
  </>,
);

export const IconGateway = icon(
  <>
    <rect x="3" y="4" width="18" height="6" rx="1.5" />
    <rect x="3" y="14" width="18" height="6" rx="1.5" />
    <path d="M7 7h.01" />
    <path d="M7 17h.01" />
  </>,
);

export const IconMinus = icon(<path d="M5 12h14" />);

export const IconSort = icon(
  <>
    <path d="m8 9 4-4 4 4" />
    <path d="m16 15-4 4-4-4" />
  </>,
);
