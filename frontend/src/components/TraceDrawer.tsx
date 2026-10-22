import { copy } from "../copy.fa";
import { faDigits } from "../format";
import type { TraceEntry } from "../types";
import { Sheet } from "./ui";

export function TraceDrawer({
  open,
  onClose,
  trace,
}: {
  open: boolean;
  onClose: () => void;
  trace: TraceEntry[];
}) {
  return (
    <Sheet open={open} onClose={onClose} title={copy.trace.title}>
      {trace.length ? (
        <ul className="space-y-2">
          {trace.map((entry, index) => (
            <li
              key={`${entry.node}-${index}`}
              className="rounded-2xl border border-brand-border bg-brand-bg p-3"
            >
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-white px-2 py-0.5 text-[11.5px] font-bold">
                  {entry.node}
                </span>
                <span className="text-[11px] text-brand-gray">
                  {faDigits(entry.ms)} میلی‌ثانیه
                </span>
              </div>
              <p className="mt-1.5 text-[12.5px] leading-6 text-brand-muted">{entry.summary}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[13px] text-brand-muted">هنوز چیزی برای نمایش نیست.</p>
      )}
    </Sheet>
  );
}
