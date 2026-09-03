/** Minimal 16px stroke icon set drawn for this console — no icon library.
 *  1.5px strokes, square optical bounds, currentColor. */

interface IconProps {
  className?: string;
  size?: number;
}

function svg(path: React.ReactNode, props: IconProps, viewBox = "0 0 16 16") {
  return (
    <svg
      width={props.size ?? 16}
      height={props.size ?? 16}
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="square"
      aria-hidden="true"
      className={props.className}
    >
      {path}
    </svg>
  );
}

export function ChevronDown(p: IconProps) {
  return svg(<path d="M3.5 6l4.5 4.5L12.5 6" />, p);
}

export function Search(p: IconProps) {
  return svg(
    <>
      <circle cx="7" cy="7" r="4.25" />
      <path d="M10.5 10.5L14 14" />
    </>,
    p,
  );
}

export function SendMark(p: IconProps) {
  return svg(<path d="M8 13V3M3.5 7.5L8 3l4.5 4.5" />, p);
}

export function Plus(p: IconProps) {
  return svg(<path d="M8 3v10M3 8h10" />, p);
}

export function Close(p: IconProps) {
  return svg(<path d="M4 4l8 8M12 4l-8 8" />, p);
}

export function PanelsLeft(p: IconProps) {
  return svg(
    <>
      <rect x="2.5" y="3" width="11" height="10" />
      <path d="M6.5 3v10" />
    </>,
    p,
  );
}

export function PanelsRight(p: IconProps) {
  return svg(
    <>
      <rect x="2.5" y="3" width="11" height="10" />
      <path d="M9.5 3v10" />
    </>,
    p,
  );
}

export function Walkthrough(p: IconProps) {
  return svg(
    <>
      <path d="M3.5 2.5h9v11h-9z" />
      <path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" />
    </>,
    p,
  );
}

export function Sun(p: IconProps) {
  return svg(
    <>
      <circle cx="8" cy="8" r="3.25" />
      <path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1" />
    </>,
    p,
  );
}

export function Moon(p: IconProps) {
  return svg(<path d="M13.2 9.6A5.6 5.6 0 0 1 6.4 2.8a5.6 5.6 0 1 0 6.8 6.8z" />, p);
}

export function Dot(p: IconProps) {
  return (
    <svg width={p.size ?? 8} height={p.size ?? 8} viewBox="0 0 8 8" aria-hidden="true" className={p.className}>
      <circle cx="4" cy="4" r="3" fill="currentColor" />
    </svg>
  );
}
