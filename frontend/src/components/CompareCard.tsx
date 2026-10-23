import { motion } from "framer-motion";
import { copy } from "../copy.fa";
import { faDigits, formatPrice } from "../format";
import type { Compare, CompareSide } from "../types";

/**
 * P3: the «X یا Y کدوم بهتره؟» card.
 *
 * One table per side (real numbers from the catalog: price range + median,
 * #models, #shops, #near ≤5 km), an explicit conditional verdict labeled
 * «تصمیم با تو», and — when a replica-style listing surfaced — an honesty
 * warning plus an in-store checklist.  Both sides stay tappable and jump
 * into the normal product flow of that side's best model.
 */

function SideRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="py-1">
      <span className="block text-[10.5px] text-brand-muted">{label}</span>
      <span className="block break-all text-[12px] font-bold">{value}</span>
    </div>
  );
}

function SideTable({ side, onPick }: { side: CompareSide; onPick: (productId: string) => void }) {
  const best = side.best;
  const body = (
    <>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="truncate text-[13.5px] font-bold">«{side.label}»</span>
        {side.replica ? (
          <span className="shrink-0 rounded-full bg-brand-amber/15 px-2 py-0.5 text-[10px] font-bold text-brand-amber">
            {copy.compare.replicaNote}
          </span>
        ) : null}
      </div>
      <SideRow
        label={copy.compare.range}
        value={
          side.min > 0
            ? `${formatPrice(side.min)} تا ${formatPrice(side.max)}`
            : "—"
        }
      />
      <SideRow
        label={copy.compare.median}
        value={side.median > 0 ? formatPrice(side.median) : "—"}
      />
      <SideRow label={copy.compare.models} value={faDigits(side.n_models)} />
      <SideRow label={copy.compare.shops} value={faDigits(side.n_shops)} />
      <SideRow label={copy.compare.near} value={faDigits(side.n_near)} />
      {best?.title ? (
        <p className="mt-1.5 line-clamp-2 text-[11px] leading-5 text-brand-gray">
          🏆 {best.title}
        </p>
      ) : null}
    </>
  );

  if (best?.product_id) {
    return (
      <button
        onClick={() => onPick(best.product_id)}
        className="w-full rounded-2xl border border-brand-border bg-brand-bg p-3 text-right transition-colors hover:border-brand-red/60"
      >
        {body}
      </button>
    );
  }
  return <div className="rounded-2xl border border-brand-border bg-brand-bg p-3">{body}</div>;
}

export function CompareCard({
  compare,
  onPickSide,
}: {
  compare: Compare;
  onPickSide: (productId: string) => void;
}) {
  const sides = compare.sides ?? [];
  const [sideA, sideB] = sides;
  const noData = !sideA?.n_shops && !sideB?.n_shops;

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-3 rounded-card border border-brand-border bg-white p-4 shadow-card"
    >
      <h3 className="text-[14px] font-bold">⚖️ {compare.title}</h3>

      {noData ? (
        <p className="rounded-2xl bg-brand-bg p-3 text-[12.5px] text-brand-muted">
          {copy.compare.notEnough}
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {sideA ? <SideTable side={sideA} onPick={onPickSide} /> : null}
          {sideB ? <SideTable side={sideB} onPick={onPickSide} /> : null}
        </div>
      )}

      {sides.length === 2 ? (
        <p className="text-[11px] text-brand-gray">{copy.compare.tapSide}</p>
      ) : null}

      {compare.verdict ? (
        <div className="rounded-2xl border border-brand-green/40 bg-brand-green/10 p-3">
          <p className="text-[12.5px] leading-6">
            {compare.verdict}
          </p>
          {compare.verdict_label ? (
            <span className="mt-2 inline-block rounded-full bg-brand-green px-2.5 py-0.5 text-[10.5px] font-bold text-white">
              {compare.verdict_label}
            </span>
          ) : null}
        </div>
      ) : null}

      {compare.warning ? (
        <div className="rounded-2xl border border-brand-amber/50 bg-brand-amber/10 p-3">
          <p className="text-[12.5px] font-bold text-brand-amber">⚠️ {compare.warning}</p>
        </div>
      ) : null}

      {compare.checklist?.length ? (
        <div className="rounded-2xl border border-brand-border p-3">
          <h4 className="mb-1.5 text-[12.5px] font-bold text-brand-muted">
            ✅ {copy.compare.checklistTitle}
          </h4>
          <ul className="space-y-1 text-[12.5px] leading-6 text-brand-muted">
            {compare.checklist.map((item) => (
              <li key={item}>• {item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </motion.section>
  );
}
