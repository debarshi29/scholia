// A unified git diff rendered the way a code host shows it: file header with +/- counts,
// hunk headers, old and new line numbers, tinted added and removed lines.
interface Row {
  kind: "hunk" | "add" | "del" | "ctx";
  oldNo: number | null;
  newNo: number | null;
  text: string;
}

interface FileDiff {
  path: string;
  rows: Row[];
  added: number;
  removed: number;
}

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/;

export function parseDiff(diff: string): FileDiff[] {
  const files: FileDiff[] = [];
  let current: FileDiff | null = null;
  let oldNo = 0;
  let newNo = 0;
  for (const line of diff.replace(/\n$/, "").split("\n")) {
    const git = /^diff --git a\/(\S+) b\//.exec(line);
    if (git) {
      current = { path: git[1] ?? "", rows: [], added: 0, removed: 0 };
      files.push(current);
      continue;
    }
    if (line.startsWith("--- ") || line.startsWith("+++ ")) {
      if (!current) {
        current = { path: line.slice(4).replace(/^[ab]\//, ""), rows: [], added: 0, removed: 0 };
        files.push(current);
      }
      continue;
    }
    if (!current || /^(index |new file|deleted file|similarity|rename |old mode|new mode)/.test(line)) {
      continue;
    }
    const hunk = HUNK.exec(line);
    if (hunk) {
      oldNo = Number(hunk[1]);
      newNo = Number(hunk[2]);
      current.rows.push({ kind: "hunk", oldNo: null, newNo: null, text: line });
    } else if (line.startsWith("+")) {
      current.rows.push({ kind: "add", oldNo: null, newNo: newNo++, text: line.slice(1) });
      current.added++;
    } else if (line.startsWith("-")) {
      current.rows.push({ kind: "del", oldNo: oldNo++, newNo: null, text: line.slice(1) });
      current.removed++;
    } else if (!line.startsWith("\\")) {
      current.rows.push({ kind: "ctx", oldNo: oldNo++, newNo: newNo++, text: line.slice(1) });
    }
  }
  return files.filter((f) => f.rows.length > 0);
}

const ROW: Record<Row["kind"], string> = {
  hunk: "bg-cyan/[0.07] text-cyan/90",
  add: "bg-green/[0.11]",
  del: "bg-coral/[0.11]",
  ctx: "",
};
const SIGN: Record<Row["kind"], string> = { hunk: "", add: "+", del: "−", ctx: "" };
const SIGN_TONE: Record<Row["kind"], string> = {
  hunk: "",
  add: "text-green",
  del: "text-coral",
  ctx: "",
};

export default function DiffView({ diff }: { diff: string }) {
  const files = parseDiff(diff);
  if (files.length === 0) {
    return (
      <pre className="overflow-x-auto rounded-md border border-line bg-bg p-3 font-mono text-[12px] text-mute">
        {diff}
      </pre>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {files.map((file) => (
        <figure key={file.path} className="overflow-hidden rounded-md border border-line bg-bg">
          <figcaption className="flex items-center justify-between gap-3 border-b border-line bg-ink/[0.03] px-3.5 py-2">
            <span className="truncate font-mono text-[12.5px]">{file.path}</span>
            <span className="flex shrink-0 items-center gap-2.5 font-mono text-[12px]">
              <span className="text-green">+{file.added}</span>
              <span className="text-coral">−{file.removed}</span>
            </span>
          </figcaption>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-[12.5px] leading-[1.55]">
              <tbody>
                {file.rows.map((row, i) => (
                  <tr key={i} className={ROW[row.kind]}>
                    <td className="w-12 border-r border-line px-2 text-right text-mute/60 select-none">
                      {row.oldNo ?? ""}
                    </td>
                    <td className="w-12 border-r border-line px-2 text-right text-mute/60 select-none">
                      {row.newNo ?? ""}
                    </td>
                    <td className={`w-6 text-center select-none ${SIGN_TONE[row.kind]}`}>
                      {SIGN[row.kind]}
                    </td>
                    <td className="py-px pr-4 whitespace-pre">{row.text || " "}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </figure>
      ))}
    </div>
  );
}
