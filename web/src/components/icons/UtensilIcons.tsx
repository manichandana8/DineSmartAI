/** Minimal fork + butter knife for brand use (stroke-based, not cartoonish). */

type IconProps = { className?: string };

export function IconFork({ className = "h-7 w-[11px]" }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 14 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M7 2v8M4 2v6M7 2h-3M10 2v6M7 2h3"
        stroke="currentColor"
        strokeWidth="1.65"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M7 10v28" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" />
    </svg>
  );
}

export function IconButterKnife({ className = "h-7 w-[11px]" }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 14 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M4 2c4 0 7 2.5 7 7v4c0 2.5-2 4.5-4.5 4.5H4V2Z"
        stroke="currentColor"
        strokeWidth="1.65"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M4 17.5v20.5" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" />
    </svg>
  );
}
