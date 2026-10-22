import { motion } from "framer-motion";
import { copy } from "../copy.fa";
import { faDigits } from "../format";
import type { Ooc } from "../types";

export function OutOfCatalogCard({
  ooc,
  onPickAlternative,
}: {
  ooc: Ooc;
  onPickAlternative: (productId: string) => void;
}) {
  const market = ooc.market;
  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-3 rounded-card border border-brand-border bg-white p-4 shadow-card"
    >
      <div className="rounded-2xl bg-brand-bg p-3">
        <h3 className="text-[14px] font-bold text-brand-muted">
          🔍 {copy.ooc.header}
        </h3>
        <p className="mt-1 text-[13px] text-brand-muted">
          «{ooc.query}» {copy.ooc.notFound}
        </p>
      </div>

      {ooc.alternatives?.length ? (
        <div>
          <h4 className="mb-2 text-[13.5px] font-bold">{copy.ooc.closest}</h4>
          <ul className="space-y-2">
            {ooc.alternatives.map((item) => (
              <li key={item.product_id}>
                <button
                  onClick={() => onPickAlternative(item.product_id)}
                  className="flex w-full items-center gap-3 rounded-xl border border-brand-border bg-white p-2 text-right"
                >
                  <div className="h-11 w-11 shrink-0 overflow-hidden rounded-lg bg-brand-bg">
                    {item.image ? (
                      <img src={item.image} alt="" className="h-full w-full object-contain" />
                    ) : (
                      <span className="flex h-full w-full items-center justify-center">📦</span>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-1 text-[12.5px] font-medium">{item.persian_title}</p>
                    <p className="text-[11px] text-brand-gray">
                      {item.category_name} · {faDigits(item.offers ?? item.n_shops ?? 0)} فروشگاه
                    </p>
                  </div>
                  <span className="text-brand-gray">‹</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {ooc.tips?.length ? (
        <div className="rounded-2xl border border-brand-amber/50 bg-brand-yellow p-3">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h4 className="text-[13.5px] font-bold">{copy.ooc.tips}</h4>
            <span className="rounded-full bg-brand-amber/20 px-2 py-0.5 text-[10.5px] font-medium text-brand-muted">
              {ooc.tips_label}
            </span>
          </div>
          <ul className="space-y-1 text-[12.5px] leading-6 text-brand-muted">
            {ooc.tips.map((tip) => (
              <li key={tip}>• {tip}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {market ? (
        <div className="rounded-2xl border border-brand-border p-3">
          <h4 className="text-[13.5px] font-bold text-brand-purple">
            {copy.ooc.marketTitle}: {market.name_fa}
          </h4>
          {market.hours_text ? (
            <p className="mt-1 text-[12.5px] text-brand-muted">
              {copy.market.hours} {market.hours_text}
            </p>
          ) : null}
          <span className="mt-2 inline-block rounded-full bg-brand-yellow px-2 py-1 text-[11px] text-brand-muted">
            {copy.ooc.approxTag}
          </span>
          <div className="mt-2 flex gap-2">
            {market.route_url ? (
              <a
                href={market.route_url}
                target="_blank"
                rel="noreferrer"
                className="flex-1 rounded-xl border border-brand-border py-2 text-center text-[12.5px] font-medium"
              >
                {copy.market.route}
              </a>
            ) : null}
            {market.sources?.[0] ? (
              <a
                href={market.sources[0]}
                target="_blank"
                rel="noreferrer"
                className="flex-1 rounded-xl border border-brand-border py-2 text-center text-[12.5px] font-medium"
              >
                {copy.ooc.source}
              </a>
            ) : null}
          </div>
        </div>
      ) : (
        <p className="text-[12.5px] text-brand-muted">{copy.ooc.noMarket}</p>
      )}
    </motion.section>
  );
}
