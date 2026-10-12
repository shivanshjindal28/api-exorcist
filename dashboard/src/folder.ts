// Choosing which files of a picked folder to upload.
//
// A project folder on disk is mostly things the scanner never reads:
// installed dependencies, build output, version-control internals, images.
// Uploading node_modules alone can mean 100,000 files and hundreds of MB, so
// those are left out in the browser, before anything is sent, and the page says
// how many were left out and why.

/** Folders that hold dependencies, build output or tool state, never API code. */
export const SKIPPED_DIRS = new Set([
  "node_modules", ".git", ".hg", ".svn", "venv", ".venv", "env", "__pycache__",
  ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", "build", "out",
  "target", ".next", ".nuxt", ".gradle", ".idea", ".vscode", "coverage",
  "site-packages", "bower_components", ".terraform", ".cache",
]);

const BINARY = /\.(png|jpe?g|gif|webp|ico|bmp|svgz|mp[34]|mov|avi|webm|wav|ogg|zip|gz|tgz|bz2|xz|7z|rar|jar|war|class|exe|dll|so|dylib|bin|pdf|docx?|xlsx?|pptx?|woff2?|ttf|otf|eot|sqlite3?|db|pyc|o|a|lib|iso|dmg)$/i;

/** No source file worth reading is this large; generated bundles often are. */
export const MAX_FILE_BYTES = 2 * 1024 * 1024;

export interface PickedFile {
  file: Blob & { name: string; size: number };
  path: string;
}

export interface Selection {
  upload: PickedFile[];
  bytes: number;
  skipped: { dependencies: number; binary: number; tooLarge: number };
  root: string;
}

/** The path a folder picker gives a file: "project/src/app.py". */
export function pathOf(file: File): string {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
}

export function selectFiles(files: PickedFile[]): Selection {
  const sel: Selection = {
    upload: [],
    bytes: 0,
    skipped: { dependencies: 0, binary: 0, tooLarge: 0 },
    root: "",
  };
  for (const f of files) {
    const parts = f.path.split("/").filter(Boolean);
    if (!sel.root && parts.length > 1) sel.root = parts[0]!;
    if (parts.slice(0, -1).some((p) => SKIPPED_DIRS.has(p))) {
      sel.skipped.dependencies += 1;
    } else if (BINARY.test(f.path)) {
      sel.skipped.binary += 1;
    } else if (f.file.size > MAX_FILE_BYTES) {
      sel.skipped.tooLarge += 1;
    } else {
      sel.upload.push(f);
      sel.bytes += f.file.size;
    }
  }
  return sel;
}

export function megabytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 1024 * 1024 ? 2 : 1)} MB`;
}
