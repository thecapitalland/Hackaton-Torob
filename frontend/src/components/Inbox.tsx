import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { copy } from "../copy.fa";
import { faDigits, formatPrice } from "../format";
import { bestConfirmedName } from "../lib/followups";
import type { Followup } from "../types";

function ParsedChip({ followup }: { followup: Followup }) {
  const parsed = followup.parsed;
  if (!parsed) return null;
  if (followup.status === "no_response" || parsed.availability === "unclear") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-brand-gray/15 px-2.5 py-1 text-[11.5px] font-medium text-brand-muted">
        {copy.inbox.noAnswer}
      </span>
    );
  }
  if (parsed.availability === "unavailable") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-brand-red/10 px-2.5 py-1 text-[11.5px] font-bold text-brand-red">
        {copy.inbox.unavailable}
      </span>
    );
  }
  const priceChanged = parsed.price_changed;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11.5px] font-bold ${
        priceChanged ? "bg-brand-amber/15 text-brand-amber" : "bg-brand-green/10 text-brand-green"
      }`}
    >
      {priceChanged ? copy.inbox.priceChanged : copy.inbox.available}
      {parsed.price_toman ? ` · ${formatPrice(parsed.price_toman)} تومان` : ""}
      {parsed.hours_text ? ` · ${parsed.hours_text}` : ""}
    </span>
  );
}

function CallCard({ followup }: { followup: Followup }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 rounded-2xl border border-dashed border-brand-border bg-brand-bg p-3">
      <button
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between text-[12.5px] font-bold text-brand-muted"
      >
        📞 تماس خودکار؟ {open ? "▲" : "▼"}
      </button>
      {open ? (
        <div className="mt-2">
          <div className="mb-2 flex h-8 items-end gap-1">
            {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((index) => (
              <span
                key={index}
                className="w-1.5 origin-bottom animate-wave rounded-full bg-brand-green"
                style={{ height: `${12 + (index % 4) * 6}px`, animationDelay: `${index * 90}ms` }}
              />
            ))}
          </div>
          <p className="text-[12px] leading-6 text-brand-muted">
            {followup.call_transcript ?? "تماس شبیه‌سازی‌شده"}
          </p>
          <span className="mt-1 inline-block rounded-full bg-brand-yellow px-2 py-0.5 text-[10.5px] text-brand-muted">
            {copy.permission.simulatedLabel}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function Thread({ followup }: { followup: Followup }) {
  const [showReply, setShowReply] = useState(false);

  useEffect(() => {
    if (followup.status === "no_response") {
      setShowReply(true);
      return;
    }
    const timer = window.setTimeout(() => setShowReply(true), Math.min(followup.delay_ms ?? 2500, 6000));
    return () => window.clearTimeout(timer);
  }, [followup.delay_ms, followup.status]);

  return (
    <div className="rounded-card border border-brand-border bg-white p-3 shadow-card">
      <div className="flex items-center justify-between">
        <h4 className="text-[13.5px] font-bold">🏪 {followup.name}</h4>
        <span className="rounded-full bg-brand-yellow px-2 py-0.5 text-[10.5px] text-brand-muted">
          {copy.permission.simulatedLabel}
        </span>
      </div>

      <div className="mt-2 flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand-green px-3 py-2 text-[12.5px] leading-6 text-white">
          {followup.message}
          <div className="mt-1 text-[10px] text-white/80">
            {copy.inbox.sent} · {copy.inbox.read}
          </div>
        </div>
      </div>

      <div className="mt-2 flex justify-start">
        {showReply ? (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="max-w-[85%] rounded-2xl rounded-bl-sm bg-brand-bg px-3 py-2 text-[12.5px] leading-6 text-brand-text"
          >
            {followup.raw_reply ?? "—"}
          </motion.div>
        ) : (
          <div className="rounded-2xl rounded-bl-sm bg-brand-bg px-3 py-2 text-[12px] text-brand-gray">
            <span className="mr-1 inline-flex gap-1 align-middle">
              {[0, 1, 2].map((index) => (
                <span
                  key={index}
                  className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-gray"
                  style={{ animationDelay: `${index * 140}ms` }}
                />
              ))}
            </span>
            {copy.inbox.typing}
          </div>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <ParsedChip followup={followup} />
        {followup.status === "no_response" ? <CallCard followup={followup} /> : null}
      </div>
    </div>
  );
}

export function Inbox({
  followups,
  onPlanTrip,
}: {
  followups: Followup[];
  onPlanTrip: () => void;
}) {
  const confirmed = followups.filter(
    (followup) => followup.parsed?.availability === "available",
  ).length;
  const bestName = bestConfirmedName(followups);

  if (!followups.length) return null;

  return (
    <section className="space-y-3">
      {confirmed ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border border-brand-green/40 bg-brand-green/10 p-3"
        >
          <p className="text-[13px] font-bold text-brand-green">
            {faDigits(confirmed)} فروشگاه تأیید کرد. پیشنهادم: {bestName ?? "—"} 🏆
          </p>
          <button
            onClick={onPlanTrip}
            className="mt-2 w-full rounded-xl bg-brand-green py-2.5 text-[13px] font-bold text-white"
          >
            {copy.inbox.planTrip}
          </button>
        </motion.div>
      ) : null}

      <AnimatePresence>
        {followups.map((followup) => (
          <Thread key={followup.shop_id} followup={followup} />
        ))}
      </AnimatePresence>
    </section>
  );
}
