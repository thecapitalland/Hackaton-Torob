import { useState } from "react";
import { copy } from "../copy.fa";
import { faDigits, formatPriceShort } from "../format";
import type { Market } from "../types";

function hoursSummary(market: Market): { text: string; friday: string } {
  const hours = (market.hours_external ?? {}) as Record<string, string>;
  const friday = hours.fri ?? "";
  const typical =
    hours.typical ?? hours.sat_thu ?? hours.alaeddin ?? hours.charsou ?? hours.sat_wed ?? "";
  return { text: typical, friday };
}

export function MarketCard({
  market,
  onRoute,
  onFilterMarket,
}: {
  market: Market;
  onRoute?: (market: Market) => void;
  onFilterMarket?: (market: Market) => void;
}) {
  const [open, setOpen] = useState(true);
  const { text, friday } = hoursSummary(market);
  const routeUrl = `https://neshan.org/maps/@${market.center?.[0]},${market.center?.[1]},16z`;

  return (
    <section className="rounded-card border border-brand-border bg-white p-4 shadow-card">
      <button onClick={() => setOpen((value) => !value)} className="w-full text-right">
        <h3 className="text-[15px] font-bold text-brand-purple">
          {copy.market.title}: {market.name_fa}
        </h3>
        <p className="mt-0.5 text-[12px] text-brand-gray">
          {open ? "بستن ▲" : "جزئیات ▼"}
        </p>
      </button>

      {open ? (
        <div className="mt-3 space-y-2 text-[13px] leading-6">
          {market.data_backed === false ? (
            <p className="rounded-xl bg-brand-yellow p-2.5 text-[12.5px]">
              {copy.market.notCovered}{" "}
              <span className="font-bold">{market.alt?.name_fa ?? "—"}</span>
            </p>
          ) : (
            <>
              <p className="font-bold text-brand-text">{copy.market.why}</p>
              <ul className="space-y-1 text-brand-muted">
                {market.shops_in_market ? (
                  <li>
                    • {faDigits(market.shops_in_market)} {copy.market.shopsInCity}{" "}
                    {faDigits(market.shops_citywide ?? 0)} {copy.market.shopsCity}
                  </li>
                ) : null}
                {market.price_median_market ? (
                  <li>
                    • {copy.market.median}: {formatPriceShort(market.price_median_market)} تومان (
                    {copy.market.cityAll}: {formatPriceShort(market.price_median_city)})
                  </li>
                ) : null}
                <li>• {copy.market.note}</li>
              </ul>
            </>
          )}

          {text ? (
            <p className="text-brand-muted">
              {copy.market.hours} {text}
              {friday ? ` — ${copy.market.friday}: ${friday}` : ""}
            </p>
          ) : null}

          <span className="inline-block rounded-full bg-brand-yellow px-2 py-1 text-[11px] text-brand-muted">
            {copy.market.externalTag}
          </span>

          <div className="flex gap-2 pt-1">
            <a
              href={routeUrl}
              target="_blank"
              rel="noreferrer"
              className="flex-1 rounded-xl border border-brand-border py-2 text-center text-[12.5px] font-medium"
            >
              {copy.market.route}
            </a>
            {onFilterMarket ? (
              <button
                onClick={() => onFilterMarket(market)}
                className="flex-1 rounded-xl bg-brand-purple py-2 text-center text-[12.5px] font-bold text-white"
              >
                {copy.market.onlyThisMarket}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
