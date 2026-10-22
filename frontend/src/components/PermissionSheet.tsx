import { useState } from "react";
import { motion } from "framer-motion";
import { copy } from "../copy.fa";
import { faDigits, formatPrice } from "../format";
import type { PendingApproval } from "../types";
import { Sheet } from "./ui";

const CHANNELS = [
  { key: "simulated_sms", label: copy.permission.channelSms },
  { key: "simulated_whatsapp", label: copy.permission.channelWhatsapp },
  { key: "open_my_whatsapp", label: copy.permission.channelOpen },
];

export function PermissionSheet({
  pending,
  onApprove,
  onReject,
}: {
  pending: PendingApproval | null;
  onApprove: (value: {
    approved: boolean;
    shop_ids: string[];
    message: string;
    messages: Record<string, string>;
    channel: string;
  }) => void;
  onReject: () => void;
}) {
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [channel, setChannel] = useState("simulated_sms");

  if (!pending) return null;
  const textOf = (shopId: string, fallback: string | undefined) =>
    messages[shopId] ?? fallback ?? pending.message ?? "";

  return (
    <Sheet
      open
      onClose={onReject}
      title={copy.permission.title}
      footer={
        <div className="flex gap-2">
          <button
            onClick={() => {
              const perShop: Record<string, string> = {};
              for (const target of pending.targets) {
                perShop[target.shop_id] = textOf(target.shop_id, target.message);
              }
              onApprove({
                approved: true,
                shop_ids: pending.targets.map((target) => target.shop_id),
                message: perShop[pending.targets[0]?.shop_id ?? ""] ?? "",
                messages: perShop,
                channel,
              });
            }}
            className="flex-1 rounded-2xl bg-brand-green py-3 text-[14px] font-bold text-white"
          >
            {copy.permission.send}
          </button>
          <button
            onClick={onReject}
            className="flex-1 rounded-2xl border border-brand-border py-3 text-[14px] font-bold text-brand-muted"
          >
            {copy.permission.decline}
          </button>
        </div>
      }
    >
      <div className="space-y-3">
        <div>
          <h4 className="mb-1.5 text-[12.5px] font-bold text-brand-muted">
            {copy.permission.recipients}
          </h4>
          <ul className="flex flex-wrap gap-1.5">
            {pending.targets.map((target) => (
              <li
                key={target.shop_id}
                className="rounded-full border border-brand-border bg-brand-bg px-2.5 py-1 text-[12px]"
              >
                🏪 {target.name}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h4 className="mb-1.5 text-[12.5px] font-bold text-brand-muted">
            {copy.permission.message}
          </h4>
          {/* B1: each shop gets its own message with its own target price */}
          <div className="space-y-2">
            {pending.targets.map((target) => (
              <div
                key={target.shop_id}
                className="rounded-2xl border border-brand-border bg-brand-bg p-2.5"
              >
                <p className="mb-1 text-[11.5px] font-bold text-brand-muted">
                  🏪 {target.name}
                  {target.target_price ? (
                    <span className="ms-1 font-medium">
                      · هدف چانه: {formatPrice(target.target_price)}
                    </span>
                  ) : null}
                </p>
                <textarea
                  value={textOf(target.shop_id, target.message)}
                  onChange={(event) =>
                    setMessages((prev) => ({
                      ...prev,
                      [target.shop_id]: event.target.value,
                    }))
                  }
                  rows={3}
                  className="w-full resize-none rounded-xl border border-brand-border bg-white p-2.5 text-[12.5px] leading-5 outline-none focus:border-brand-red"
                />
              </div>
            ))}
          </div>
        </div>

        <div>
          <h4 className="mb-1.5 text-[12.5px] font-bold text-brand-muted">روش ارسال</h4>
          <div className="flex flex-wrap gap-1.5">
            {CHANNELS.map((item) => (
              <button
                key={item.key}
                onClick={() => setChannel(item.key)}
                className={`rounded-full border px-3 py-1.5 text-[12px] ${
                  channel === item.key
                    ? "border-brand-red bg-brand-red text-white"
                    : "border-brand-border bg-white text-brand-muted"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="rounded-xl bg-brand-yellow p-2.5 text-[11.5px] leading-5 text-brand-muted"
        >
          {pending.privacy_note ?? copy.permission.privacy}
        </motion.p>
      </div>
    </Sheet>
  );
}

export function ChannelBadge({ channel }: { channel: string }) {
  const label =
    CHANNELS.find((item) => item.key === channel)?.label ?? copy.permission.channelSms;
  return (
    <span className="rounded-full bg-brand-bg px-2 py-0.5 text-[11px] text-brand-muted">
      {label}
    </span>
  );
}

export function countShops(count: number): string {
  return `${faDigits(count)} فروشگاه`;
}
