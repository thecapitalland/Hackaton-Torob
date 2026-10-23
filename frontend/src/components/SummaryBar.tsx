import { useState } from "react";
import { copy } from "../copy.fa";
import { formatPrice } from "../format";
import type { Slots } from "../types";

export function SummaryBar({
  slots,
  radiusKm,
  onEdit,
}: {
  slots: Slots;
  radiusKm: number | null;
  onEdit: (slot: "product" | "budget" | "location" | "radius", message: string) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const segments = [
    slots.category || (slots.keywords || []).join(" ") || copy.summary.product,
    slots.budget_max ? `تا ${formatPrice(slots.budget_max)}` : slots.budget_min ? `از ${formatPrice(slots.budget_min)}` : copy.summary.budget,
    slots.location?.label || copy.summary.location,
    radiusKm === null ? copy.home.wholeCity : `${radiusKm} ${copy.home.km}`,
  ];

  const slotNames = ["product", "budget", "location", "radius"] as const;
  const beginEdit = (key: string) => {
    setEditing(key);
    setValue("");
  };
  const submit = () => {
    if (!value.trim() || editing === null) return;
    const slot = slotNames[Number(editing)] ?? "product";
    onEdit(slot, value.trim());
    setEditing(null);
    setValue("");
  };

  return (
    <div className="space-y-2 rounded-2xl border border-brand-border bg-white px-3 py-2 shadow-card" aria-label="خلاصهٔ جستجو">
      <div className="no-scrollbar flex gap-2 overflow-x-auto">
        {segments.map((segment, index) => (
          <button
            key={`${index}-${segment}`}
            onClick={() => beginEdit(String(index))}
            className="shrink-0 rounded-full bg-brand-bg px-3 py-1.5 text-[11.5px] text-brand-muted"
          >
            {segment}{index < segments.length - 1 ? " ·" : ""}
          </button>
        ))}
      </div>
      {editing !== null ? (
        <div className="flex gap-2">
          <input
            autoFocus
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") submit(); }}
            placeholder={copy.summary.editHint}
            className="min-w-0 flex-1 rounded-lg border border-brand-border px-2.5 py-2 text-[12px] outline-none focus:border-brand-red"
          />
          <button onClick={submit} className="rounded-lg bg-brand-red px-3 text-[12px] font-bold text-white">{copy.home.cta}</button>
          <button onClick={() => setEditing(null)} className="rounded-lg bg-brand-bg px-2 text-[12px]">✕</button>
        </div>
      ) : null}
    </div>
  );
}
