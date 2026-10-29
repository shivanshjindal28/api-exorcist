import { useCallback, useEffect, useRef, useState } from "react";
import { IconGhost, IconGraph, IconShield } from "../icons";
import { motionOK } from "../motion";

// Shown once per browser tab, unless the viewer turns it off. Both are
// per-viewer conveniences, so browser storage is enough; it is read
// defensively because storage can be unavailable.
const SEEN_KEY = "apix.splash.seen";
const OFF_KEY = "apix.splash.off";

function read(store: () => Storage, key: string): string | null {
  try {
    return store().getItem(key);
  } catch {
    return null;
  }
}

function write(store: () => Storage, key: string, value: string | null): void {
  try {
    if (value === null) store().removeItem(key);
    else store().setItem(key, value);
  } catch {
    // Not remembered; the splash simply shows again next time.
  }
}

export function shouldShowSplash(): boolean {
  return read(() => localStorage, OFF_KEY) !== "1" && read(() => sessionStorage, SEEN_KEY) !== "1";
}

/** The launch screen: what this is, before the console. */
export function Splash({ onClose }: { onClose: () => void }) {
  const [leaving, setLeaving] = useState(false);
  const [off, setOff] = useState(false);
  const enter = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    write(() => sessionStorage, SEEN_KEY, "1");
    write(() => localStorage, OFF_KEY, off ? "1" : null);
    if (!motionOK()) {
      onClose();
      return;
    }
    setLeaving(true);
    window.setTimeout(onClose, 380);
  }, [off, onClose]);

  useEffect(() => {
    enter.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [close]);

  return (
    <div
      className={`splash ${leaving ? "is-leaving" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="splash-title"
      aria-describedby="splash-pitch"
    >
      <div className="splash-aurora" aria-hidden="true" />
      <div className="splash-grid" aria-hidden="true" />
      <div className="splash-body">
        <div className="splash-mark" aria-hidden="true">
          <span className="splash-ring r1" />
          <span className="splash-ring r2" />
          <span className="splash-ring r3" />
          <span className="splash-glow" />
          <img src="/logo.png" alt="" width={220} height={220} />
        </div>
        <p className="splash-kicker">API inventory and safe retirement</p>
        <h1 id="splash-title" className="splash-title">
          API Exorcist
        </h1>
        <p id="splash-pitch" className="splash-pitch">
          Finds the zombie, shadow and orphaned APIs a bank has forgotten, proves which are
          dead, and retires them without an outage.
        </p>
        <ul className="splash-points">
          <li>
            <IconGhost size={20} />
            <span>
              <strong>Six sources, correlated</strong>
              Absence from the gateway or the spec is evidence.
            </span>
          </li>
          <li>
            <IconGraph size={20} />
            <span>
              <strong>Every verdict explained</strong>
              Signed reasons, and what could not be checked.
            </span>
          </li>
          <li>
            <IconShield size={20} />
            <span>
              <strong>Safe Kill</strong>
              Shadow, named approval, canary, rollback, audit.
            </span>
          </li>
        </ul>
        <div className="splash-actions">
          <button ref={enter} className="splash-enter" onClick={close}>
            Enter the console <span aria-hidden="true">&rarr;</span>
          </button>
          <label className="splash-off">
            <input type="checkbox" checked={off} onChange={(e) => setOff(e.target.checked)} />
            Don&apos;t show on launch
          </label>
        </div>
        <p className="splash-foot">
          v{__APP_VERSION__} · B.Tech CSE (Cyber Security) capstone · MPSTME, NMIMS
        </p>
      </div>
    </div>
  );
}
