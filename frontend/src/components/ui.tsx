import { motion } from "framer-motion";
import { useEffect, type ReactNode } from "react";

export function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center"
      role="dialog"
      aria-modal="true"
    >
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />
      <motion.div
        initial={{ y: "100%" }}
        animate={{ y: 0 }}
        transition={{ type: "spring", damping: 26, stiffness: 260 }}
        className="relative w-full max-w-[420px] rounded-t-3xl bg-white p-5 shadow-sheet"
      >
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-brand-border" />
        {title ? (
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-[17px] font-bold">{title}</h3>
            <button
              onClick={onClose}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-bg text-brand-muted"
              aria-label="بستن"
            >
              ✕
            </button>
          </div>
        ) : null}
        <div className="max-h-[70vh] overflow-y-auto">{children}</div>
        {footer ? <div className="mt-4">{footer}</div> : null}
      </motion.div>
    </div>
  );
}

export function Chip({
  children,
  onClick,
  active = false,
  tone = "default",
  size = "md",
}: {
  children: ReactNode;
  onClick?: () => void;
  active?: boolean;
  tone?: "default" | "primary" | "success" | "warning" | "muted";
  size?: "sm" | "md";
}) {
  const tones: Record<string, string> = {
    default: active
      ? "bg-brand-red text-white border-brand-red"
      : "bg-white text-brand-text border-brand-border",
    primary: "bg-brand-red text-white border-brand-red",
    success: "bg-brand-green text-white border-brand-green",
    warning: "bg-brand-amber text-brand-text border-brand-amber",
    muted: "bg-brand-bg text-brand-muted border-brand-border",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border ${tones[tone]} ${
        size === "sm" ? "px-2.5 py-1 text-[11px]" : "px-3.5 py-2 text-[13px]"
      } min-h-[36px] font-medium`}
    >
      {children}
    </button>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-brand-border/70 ${className}`} />;
}
