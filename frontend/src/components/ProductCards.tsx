import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { copy } from "../copy.fa";
import { faDigits, formatPriceShort } from "../format";
import type { MoreItem, ProductCard } from "../types";
import { Chip } from "./ui";

const RIBBONS: Record<string, { label: string; className: string }> = {
  best: { label: copy.cards.best, className: "bg-brand-red" },
  budget: { label: copy.cards.budget, className: "bg-brand-green" },
  premium: { label: copy.cards.premium, className: "bg-brand-purple" },
};

export function ProductCards({
  cards,
  more,
  onSelect,
  onSelectMore,
}: {
  cards: ProductCard[];
  more: MoreItem[];
  onSelect: (productId: string) => void;
  onSelectMore: (productId: string) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showMore, setShowMore] = useState(false);
  const [compare, setCompare] = useState(false);

  if (!cards.length) return null;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-[16px] font-bold">{copy.cards.title}</h2>
        {cards.length > 1 ? (
          <button
            onClick={() => setCompare((value) => !value)}
            className="rounded-full border border-brand-border bg-white px-3 py-1.5 text-[12px] text-brand-muted"
          >
            {compare ? copy.cards.hideCompare : copy.cards.compare}
          </button>
        ) : null}
      </div>

      <div className="no-scrollbar -mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2">
        {cards.map((card) => {
          const ribbon = RIBBONS[card.kind] ?? RIBBONS.best;
          const isOpen = expanded === card.product_id;
          return (
            <motion.article
              key={card.product_id}
              layout
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              className="w-[268px] shrink-0 snap-center overflow-hidden rounded-card border border-brand-border bg-white shadow-card"
            >
              <div className={`${ribbon.className} px-3 py-1.5 text-[12px] font-bold text-white`}>
                {ribbon.label}
              </div>
              <div className="flex gap-3 p-3">
                <div className="h-20 w-20 shrink-0 overflow-hidden rounded-xl bg-brand-bg">
                  {card.image ? (
                    <img
                      src={card.image}
                      alt={card.title}
                      loading="lazy"
                      className="h-full w-full object-contain"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-[22px]">📦</div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="mb-0.5 truncate text-[12px] text-brand-gray">{card.brand}</p>
                  <h3 className="line-clamp-2 text-[14px] font-bold leading-6">{card.title}</h3>
                </div>
              </div>

              <div className="flex items-center gap-3 px-3 text-[13px]">
                <span className="font-bold text-brand-red">
                  {copy.cards.from} {formatPriceShort(card.min_price)} تومان
                </span>
                <span className="text-brand-muted">
                  {copy.cards.inShops} {faDigits(card.n_shops)} {copy.cards.shops}
                </span>
              </div>

              <div className="mt-2 flex flex-wrap gap-1.5 px-3">
                {card.highlights.map((highlight) => (
                  <span
                    key={highlight}
                    className="rounded-full bg-brand-bg px-2 py-1 text-[11px] text-brand-muted"
                  >
                    {highlight}
                  </span>
                ))}
              </div>

              {card.warnings?.length ? (
                <div className="mx-3 mt-2 rounded-xl border border-brand-amber/60 bg-brand-yellow p-2 text-[11.5px] leading-5">
                  {card.warnings.map((warning) => (
                    <p key={warning}>⚠️ {warning}</p>
                  ))}
                </div>
              ) : null}

              <div className="px-3 pt-2">
                <button
                  onClick={() => setExpanded(isOpen ? null : card.product_id)}
                  className="text-[12.5px] font-medium text-brand-muted"
                >
                  {copy.cards.why} {isOpen ? "▲" : "▼"}
                </button>
                <AnimatePresence initial={false}>
                  {isOpen ? (
                    <motion.p
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden text-[12.5px] leading-6 text-brand-muted"
                    >
                      <span className="block pt-1">{card.why}</span>
                    </motion.p>
                  ) : null}
                </AnimatePresence>
              </div>

              <div className="p-3">
                <button
                  onClick={() => onSelect(card.product_id)}
                  className="w-full rounded-xl bg-brand-red py-2.5 text-[13.5px] font-bold text-white"
                >
                  {copy.cards.showShops}
                </button>
              </div>
            </motion.article>
          );
        })}
      </div>

      {compare && cards.length > 1 ? (
        <CompareTable cards={cards} />
      ) : null}

      {more.length ? (
        <div className="px-1">
          <button
            onClick={() => setShowMore((value) => !value)}
            className="text-[13px] font-bold text-brand-muted"
          >
            {copy.cards.more} {showMore ? "▲" : "▼"}
          </button>
          <AnimatePresence initial={false}>
            {showMore ? (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <ul className="mt-2 space-y-2">
                  {more.map((item) => (
                    <li key={item.product_id}>
                      <button
                        onClick={() => onSelectMore(item.product_id)}
                        className="flex w-full items-center gap-3 rounded-card border border-brand-border bg-white p-2.5 text-right shadow-card"
                      >
                        <div className="h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-brand-bg">
                          {item.image ? (
                            <img src={item.image} alt="" className="h-full w-full object-contain" />
                          ) : null}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="line-clamp-1 text-[13px] font-medium">{item.title}</p>
                          <p className="text-[11.5px] text-brand-muted">
                            {copy.cards.from} {formatPriceShort(item.min_price)} ·{" "}
                            {faDigits(item.n_shops)} {copy.cards.shops}
                          </p>
                        </div>
                        <span className="text-brand-gray">‹</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      ) : null}
    </section>
  );
}

function CompareTable({ cards }: { cards: ProductCard[] }) {
  return (
    <div className="overflow-x-auto rounded-card border border-brand-border bg-white p-3 shadow-card">
      <table className="w-full text-right text-[12px]">
        <thead>
          <tr className="text-brand-muted">
            <th className="p-1 font-medium">ویژگی</th>
            {cards.map((card) => (
              <th key={card.product_id} className="p-1 font-medium">
                <span className="line-clamp-2">{card.title}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="align-top">
          <tr className="border-t border-brand-border">
            <td className="p-1 text-brand-muted">قیمت</td>
            {cards.map((card) => (
              <td key={card.product_id} className="p-1 font-bold text-brand-red">
                {formatPriceShort(card.min_price)}
              </td>
            ))}
          </tr>
          <tr className="border-t border-brand-border">
            <td className="p-1 text-brand-muted">تعداد فروشگاه</td>
            {cards.map((card) => (
              <td key={card.product_id} className="p-1">
                {faDigits(card.n_shops)}
              </td>
            ))}
          </tr>
          <tr className="border-t border-brand-border">
            <td className="p-1 text-brand-muted">ویژگی‌ها</td>
            {cards.map((card) => (
              <td key={card.product_id} className="p-1 text-brand-muted">
                {card.highlights.slice(0, 3).map((item) => (
                  <p key={item}>• {item}</p>
                ))}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export { Chip };
