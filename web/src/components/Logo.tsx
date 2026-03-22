import { Link } from "react-router-dom";

type LogoProps = {
  className?: string;
  subtitle?: boolean;
};

export function Logo({ className = "", subtitle = true }: LogoProps) {
  return (
    <Link to="/" className={`group flex items-center gap-3 ${className}`}>
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sage-400 via-sage-500 to-blush-300 text-lg shadow-soft transition duration-300 group-hover:scale-[1.03] group-hover:shadow-glow"
        aria-hidden
      >
        <span className="drop-shadow-sm">🍽</span>
      </div>
      <div className="min-w-0 text-left leading-tight">
        <p className="font-display text-lg font-semibold tracking-tight text-ink md:text-xl">
          DineSmartAI
        </p>
        {subtitle ? (
          <p className="text-xs font-medium text-taupe">AI dining concierge</p>
        ) : null}
      </div>
    </Link>
  );
}
