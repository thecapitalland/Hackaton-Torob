import { useState } from "react";
import { copy } from "../copy.fa";
import {
  ceilingLine,
  copyText,
  fairnessLabel,
  medianLine,
  savingLine,
  targetLine,
} from "../lib/haggle";
import type { Fairness, Haggle } from "../types";

const TONES: Record<string, string> = {
  danger: "bg-brand-red/10 text-brand-red",
  muted: "bg-brand-gray/15 text-brand-muted",
  success: "bg-brand-green/10 text-brand-green",
  neutral: "bg-brand-bg text-brand-gray",
};

export function FairnessBadge({
  label,
  className = "",
}: {
  label?: Fairness | string | null;
  className?: string;
}) {
  if (!label) return null;
  const item = fairnessLabel(label);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10.5px] font-bold ${TONES[item.tone]} ${className}`}
    >
      {item.text}
    </span>
  );
}

export function HagglePanel({
  haggle,
  compact = false,
}: {
  haggle: Haggle;
  compact?: boolean;
}) {
  const [copied, setCopied] = useState<"idle" | "ok" | "failed">("idle");
  const lines = haggle.lines ?? [];
  const single = haggle.label === "single" || haggle.n_shops < 2;

  const onCopy = async () => {
    const ok = await copyText(lines.join("\n"));
    setCopied(ok ? "ok" : "failed");
    window.setTimeout(() => setCopied("idle"), 2200);
  };

  return (
    <div
      className={`mt-2 rounded-2xl border border-brand-border bg-brand-bg ${
        compact ? "p-2.5" : "p-3"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11.5px] font-bold text-brand-muted">
          🧠 {copy.haggle.agent}
        </span>
        <FairnessBadge label={haggle.label} />
      </div>
      {!single ? (
        <p className="mt-1 text-[11px] text-brand-gray">{medianLine(haggle)}</p>
      ) : null}

      {!single ? (
        <>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="rounded-full bg-brand-green/10 px-2 py-0.5 text-[11px] font-bold text-brand-green">
              🎯 {targetLine(haggle)}
            </span>
            <span className="rounded-full bg-brand-amber/15 px-2 py-0.5 text-[11px] font-bold text-brand-amber">
              🚧 {ceilingLine(haggle)}
            </span>
            {haggle.saving_pct > 0 ? (
              <span className="rounded-full bg-brand-bg px-2 py-0.5 text-[11px] text-brand-muted">
                {savingLine(haggle)}
              </span>
            ) : null}
          </div>

          <ul className="mt-2 space-y-1 text-[12px] leading-6 text-brand-text">
            {lines.map((line) => (
              <li key={line}>• {line}</li>
            ))}
          </ul>

          <div className="mt-2 flex items-center justify-start gap-2">
            <button
              type="button"
              onClick={onCopy}
              className="rounded-full border border-brand-border bg-white px-2.5 py-1 text-[11px] font-medium text-brand-muted"
            >
              {copied === "ok"
                ? `✓ ${copy.haggle.copied}`
                : copied === "failed"
                  ? copy.haggle.copyFailed
                  : `📋 ${copy.haggle.copy}`}
            </button>
          </div>
        </>
      ) : (
        <p className="mt-1 text-[11.5px] text-brand-muted">{copy.haggle.singleNote}</p>
      )}
    </div>
  );
}
