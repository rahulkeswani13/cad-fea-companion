import type { PointerEvent as ReactPointerEvent, ReactNode } from "react";

export function SectionLabel({
  index,
  title,
  right,
}: {
  index: string;
  title: string;
  right?: ReactNode;
}) {
  return (
    <div className="section-label hairline-b pb-2">
      <span className="index">{index}</span>
      <span className="truncate">{title}</span>
      {right != null && <span className="ml-auto normal-case tracking-normal">{right}</span>}
    </div>
  );
}

export function Stamp({
  kind,
  label,
}: {
  kind: "pass" | "caution" | "fail" | "neutral" | "accent";
  label: string;
}) {
  const tone =
    kind === "pass"
      ? "text-pass border-pass/40"
      : kind === "caution"
        ? "text-caution border-caution/40"
        : kind === "fail"
          ? "text-fail border-fail/40"
          : kind === "accent"
            ? "text-accent border-accent/40"
            : "text-ink-dim border-line-strong";
  return (
    <span
      className={`inline-flex shrink-0 items-center border px-1.5 py-px font-mono text-[10px] font-semibold tracking-[0.12em] uppercase rounded-[2px] ${tone}`}
    >
      {label}
    </span>
  );
}

/** Drag handle on a rail's inner edge: drag to resize, double-click to reset.
 *  `rail` names the owning rail (for the testid); `edge` is where it sits. */
export function RailHandle({
  rail,
  edge,
  onDrag,
  onReset,
}: {
  rail: "left" | "right";
  edge: "left" | "right";
  onDrag: (e: ReactPointerEvent) => void;
  onReset: () => void;
}) {
  return (
    <div
      data-testid={`rail-${rail}-handle`}
      onPointerDown={onDrag}
      onDoubleClick={onReset}
      title="Drag to resize — double-click to reset"
      className={`absolute inset-y-0 z-10 w-[5px] cursor-col-resize transition-colors duration-150 hover:bg-accent/40 ${
        edge === "right" ? "right-0" : "left-0"
      }`}
    />
  );
}

export function Btn({
  children,
  onClick,
  disabled,
  variant = "ghost",
  title,
  className = "",
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "ghost" | "solid" | "outline";
  title?: string;
  className?: string;
  type?: "button" | "submit";
}) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-[2px] px-2.5 py-1.5 font-mono text-[11px] tracking-[0.08em] uppercase transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40";
  const skin =
    variant === "solid"
      ? "bg-accent text-[#16130e] hover:bg-[#ff7a42] active:bg-accent-dim font-semibold"
      : variant === "outline"
        ? "border border-line-strong text-ink hover:border-accent hover:text-accent"
        : "text-ink-dim hover:text-ink hover:bg-raised";
  return (
    <button type={type} onClick={onClick} disabled={disabled} title={title} className={`${base} ${skin} ${className}`}>
      {children}
    </button>
  );
}

export function IconBtn({
  children,
  onClick,
  title,
  active,
  className = "",
  testid,
}: {
  children: ReactNode;
  onClick?: () => void;
  title?: string;
  active?: boolean;
  className?: string;
  testid?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      data-testid={testid}
      className={`inline-flex h-7 w-7 items-center justify-center rounded-[2px] transition-colors duration-150 ${
        active ? "bg-raised text-ink" : "text-ink-faint hover:bg-raised hover:text-ink"
      } ${className}`}
    >
      {children}
    </button>
  );
}

/** Cost hint for prompt items: instant / seconds / solve. */
export function CostChip({ cost }: { cost?: string }) {
  if (!cost) return null;
  const kind = cost === "solve" ? "caution" : cost === "seconds" ? "neutral" : "neutral";
  const label = cost === "solve" ? "SOLVE" : cost === "seconds" ? "~SEC" : "INSTANT";
  return <Stamp kind={kind} label={label} />;
}

/** Toggle switch (role=switch) — gates like HITL tool confirmation (ADR-016). */
export function Switch({
  checked,
  onToggle,
  label,
  title,
  testid,
}: {
  checked: boolean;
  onToggle: (next: boolean) => void;
  label: string;
  title?: string;
  testid?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={title ?? label}
      data-testid={testid}
      onClick={() => onToggle(!checked)}
      className="inline-flex h-[20px] w-[36px] shrink-0 items-center rounded-full border border-line-strong bg-raised px-[2px] transition-colors duration-150 hover:border-accent aria-checked:border-accent"
    >
      <span
        className={`h-[12px] w-[12px] rounded-full transition-transform duration-150 ${
          checked ? "translate-x-[18px] bg-accent" : "translate-x-0 bg-ink-faint"
        }`}
      />
    </button>
  );
}
