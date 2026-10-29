/* The audit log drawn as what it is: a chain. Each block is an entry; the link
 * between two blocks is the earlier entry's hash, carried by the later one.
 * Verifying lights the links in order; a break shows where the chain fails. */

import { IconLock } from "./icons";

interface Linkable {
  seq: number;
  to_state: string;
  actor: string;
  hash: string;
  prev_hash: string;
}

export function ChainStrip({
  entries,
  verified,
  brokenAt,
  label = (s: string) => s.replace(/_/g, " ").toLowerCase(),
  show = 5,
}: {
  entries: Linkable[];
  /** null before anyone has verified; then whether the whole chain held. */
  verified: boolean | null;
  brokenAt?: number | null;
  label?: (state: string) => string;
  show?: number;
}) {
  const tail = [...entries].sort((a, b) => a.seq - b.seq).slice(-show);
  if (!tail.length) return null;
  const state = verified === null ? "" : verified ? "is-verified" : "is-broken";
  return (
    <div className={`chain ${state}`} aria-label="The latest entries of the hash chain">
      {tail.map((e, i) => {
        const broken = verified === false && brokenAt != null && e.seq >= brokenAt;
        const linkOk = i === 0 || tail[i - 1]!.hash === e.prev_hash;
        return (
          <div key={e.seq} className="chain-item">
            {i > 0 && (
              <span
                className={`chain-link ${linkOk ? "" : "is-bad"}`}
                title={`Entry ${e.seq} carries ${e.prev_hash.slice(0, 12)}..., the hash of entry ${tail[i - 1]!.seq}`}
                aria-hidden="true"
              >
                <span className="chain-link-line" />
                <span className="chain-link-hash">{e.prev_hash.slice(0, 6)}</span>
              </span>
            )}
            <div className={`chain-block ${broken ? "is-bad" : ""}`}>
              <span className="chain-seq">
                <IconLock size={12} /> #{e.seq}
              </span>
              <strong className="chain-state">{label(e.to_state)}</strong>
              <span className="chain-actor">{e.actor}</span>
              <code className="chain-hash" title={e.hash}>
                {e.hash.slice(0, 10)}
              </code>
            </div>
          </div>
        );
      })}
    </div>
  );
}
