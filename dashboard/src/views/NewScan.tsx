import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { ApiError } from "../api";
import { ErrorBox, canApprove, useLoad, useSession } from "../common";
import { megabytes, pathOf, selectFiles } from "../folder";
import type { Selection } from "../folder";
import type { InputOption } from "../types";
import { DemoButton } from "./scan/ScanView";

/** Where to go once a scan has started: its live progress page. */
function openScan(id: string) {
  window.location.hash = `#results/${id}/overview`;
}

export function NewScan() {
  const { api, principal } = useSession();
  const caps = useLoad(() => api.capabilities());
  const mayScan = canApprove(principal);

  return (
    <div className="stack">
      <p className="lead">
        Find the APIs in a project, and what is wrong with them: undocumented, unowned,
        untouched for a year, still in the code after being removed from the
        documentation. Choose what to scan.
      </p>
      {!mayScan && (
        <div className="notice" role="note">
          You are signed in as a viewer: you can read every scan, but starting one needs
          an approver.
        </div>
      )}
      {caps.error && <ErrorBox message={caps.error} />}
      <div className="options">
        <FolderOption option={caps.data?.folder} disabled={!mayScan} />
        <GithubOption option={caps.data?.github} disabled={!mayScan} />
        <WebsiteOption option={caps.data?.website} />
      </div>
      <section className="card demo-card" aria-labelledby="opt-demo">
        <div>
          <h2 id="opt-demo">Not sure what to expect? Run the demo</h2>
          <p className="muted small">
            A simulated bank with all six evidence sources, traffic included, so every view
            is complete: zombie classification, the removal gate, Safe Kill with approval
            and rollback, the audit log and the accuracy benchmark. It opens like any scan.
          </p>
        </div>
        <DemoButton />
      </section>
    </div>
  );
}

function Warning({ option }: { option: InputOption | undefined }) {
  if (!option?.warning) return null;
  return (
    <p className="option-warning" role="note">
      {option.warning}
    </p>
  );
}

// ---------------------------------------------------------------------------
function FolderOption({ option, disabled }: { option?: InputOption; disabled: boolean }) {
  const { api } = useSession();
  const [selection, setSelection] = useState<Selection | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  function pick(e: ChangeEvent<HTMLInputElement>) {
    setError(null);
    const list = Array.from(e.target.files ?? []);
    setSelection(list.length ? selectFiles(list.map((f) => ({ file: f, path: pathOf(f) }))) : null);
  }

  async function upload() {
    if (!selection || !selection.upload.length) return;
    setError(null);
    setProgress(0);
    try {
      const job = await api.uploadFolder(selection.upload, setProgress);
      openScan(job.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setProgress(null);
    }
  }

  const skipped = selection
    ? selection.skipped.dependencies + selection.skipped.binary + selection.skipped.tooLarge
    : 0;

  return (
    <section className="card option" aria-labelledby="opt-folder">
      <h2 id="opt-folder">
        <span className="option-num">1</span> Upload a project folder
      </h2>
      <p className="muted small">
        Pick the project's top folder. Its files are copied to API Exorcist on this
        machine, read, and deleted when the scan ends. Nothing in them is run.
      </p>
      <Warning option={option} />
      {/* The native control says "Choose Files" even when it picks a folder,
          so it is hidden visually (still focusable) behind a truthful label. */}
      <label className={`file-pick${disabled || progress !== null ? " is-disabled" : ""}`}>
        <input
          className="visually-hidden"
          type="file"
          multiple
          disabled={disabled || progress !== null}
          onChange={pick}
          aria-label="Choose a project folder"
          {...{ webkitdirectory: "", directory: "" }}
        />
        <span aria-hidden="true">{selection ? "Choose a different folder" : "Choose folder"}</span>
      </label>
      {selection && (
        <div className="small" aria-live="polite">
          <p>
            <strong>{selection.root || "Folder"}</strong>: {selection.upload.length} file(s),{" "}
            {megabytes(selection.bytes)} to upload.
          </p>
          {skipped > 0 && (
            <p className="muted">
              Left out, because the scanner never reads them:{" "}
              {[
                selection.skipped.dependencies &&
                  `${selection.skipped.dependencies} in dependency or build folders`,
                selection.skipped.binary && `${selection.skipped.binary} images or binaries`,
                selection.skipped.tooLarge && `${selection.skipped.tooLarge} over 2 MB`,
              ]
                .filter(Boolean)
                .join(", ")}
              .
            </p>
          )}
          {selection.upload.length === 0 && (
            <p className="warn-text">Nothing left to scan in this folder.</p>
          )}
        </div>
      )}
      {progress !== null && (
        <div className="upload-progress" role="progressbar" aria-valuenow={Math.round(progress * 100)}
          aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress">
          <span style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      )}
      {error && <ErrorBox message={error} />}
      <button
        disabled={disabled || !selection || !selection.upload.length || progress !== null}
        onClick={upload}
      >
        {progress === null ? "Scan this folder" : `Uploading ${Math.round(progress * 100)}%`}
      </button>
    </section>
  );
}

// ---------------------------------------------------------------------------
function GithubOption({ option, disabled }: { option?: InputOption; disabled: boolean }) {
  const { api } = useSession();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unavailable = option && !option.available;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const job = await api.scanGithub(url.trim());
      openScan(job.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <form className="card option" aria-labelledby="opt-github" onSubmit={submit}>
      <h2 id="opt-github">
        <span className="option-num">2</span> Scan a GitHub repository
      </h2>
      <p className="muted small">
        A public repository's link. It is downloaded with its commit history, which shows
        how long each endpoint's code has gone unchanged.
      </p>
      {unavailable && <p className="option-warning">{option.reason}</p>}
      <Warning option={option} />
      <label htmlFor="github-url">Repository link</label>
      <input
        id="github-url"
        type="url"
        inputMode="url"
        spellCheck={false}
        placeholder="https://github.com/owner/repository"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        disabled={disabled || unavailable || busy}
      />
      {error && <ErrorBox message={error} />}
      <button type="submit" disabled={disabled || unavailable || busy || !url.trim()}>
        {busy ? "Starting..." : "Scan repository"}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
function WebsiteOption({ option }: { option?: InputOption }) {
  return (
    <section className="card option option-off" aria-labelledby="opt-website">
      <h2 id="opt-website">
        <span className="option-num">3</span> Scan a live website
      </h2>
      <p className="muted small">A website's address, such as https://example.com.</p>
      <label htmlFor="website-url">Website address</label>
      <input id="website-url" type="url" placeholder="https://example.com" disabled />
      <p className="option-warning" role="note">
        {option?.reason ??
          "Scanning a live website is not available in this version."}
      </p>
      <button disabled>Not available</button>
    </section>
  );
}
