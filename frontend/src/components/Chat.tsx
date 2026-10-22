import { motion } from "framer-motion";
import { copy } from "../copy.fa";
import { faDigits } from "../format";
import type { Slots } from "../types";

export function SlotPills({ slots }: { slots: Slots }) {
  const pills: string[] = [];
  if (slots.category) pills.push(`🎧 ${slots.category}`);
  if (slots.budget_max) pills.push(`💰 تا ${faDigits(slots.budget_max.toLocaleString("en-US")).replace(/,/g, "٬")}`);
  if (slots.budget_min) pills.push(`💰 از ${faDigits(slots.budget_min.toLocaleString("en-US")).replace(/,/g, "٬")}`);
  if (slots.location?.label) pills.push(`📍 ${slots.location.label}`);
  if (slots.installment) pills.push("💳 قسطی");
  if (slots.payment_in_person) pills.push("💵 حضوری");
  if (slots.today) pills.push("⏰ امروز");

  if (!pills.length) return null;

  return (
    <div className="no-scrollbar flex gap-2 overflow-x-auto px-4 pb-2 pt-1">
      {pills.map((pill) => (
        <motion.span
          key={pill}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="shrink-0 rounded-full border border-brand-border bg-white px-3 py-1.5 text-[12px] text-brand-muted"
        >
          {pill}
        </motion.span>
      ))}
      <span className="shrink-0 rounded-full border border-dashed border-brand-border px-3 py-1.5 text-[12px] text-brand-gray">
        برای ویرایش بگو
      </span>
    </div>
  );
}

export function TypingIndicator({ steps }: { steps?: string[] }) {
  const list = steps ?? copy.home.steps;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl rounded-tr-sm border border-brand-border bg-white p-3 shadow-card"
    >
      <div className="mb-2 flex items-center gap-2 text-[13px] text-brand-muted">
        <span className="flex gap-1">
          {[0, 1, 2].map((index) => (
            <span
              key={index}
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-red"
              style={{ animationDelay: `${index * 140}ms` }}
            />
          ))}
        </span>
        {copy.home.typing}
      </div>
      <div className="flex flex-wrap items-center gap-1 text-[11px] text-brand-gray">
        {list.map((step, index) => (
          <span key={step} className="flex items-center gap-1">
            {index > 0 ? <span>←</span> : null}
            <span className="rounded-full bg-brand-bg px-2 py-0.5">{step}</span>
          </span>
        ))}
      </div>
    </motion.div>
  );
}
