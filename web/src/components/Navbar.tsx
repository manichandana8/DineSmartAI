import { Link, NavLink, useLocation } from "react-router-dom";
import { Logo } from "./Logo";
import { getAssistantUrl } from "@/lib/assistantUrl";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-3 py-2 text-sm font-medium transition ${
    isActive
      ? "bg-white/70 text-ink shadow-sm"
      : "text-taupe hover:bg-white/50 hover:text-ink"
  }`;

export function Navbar() {
  const loc = useLocation();
  const assistant = getAssistantUrl();
  const onHome = loc.pathname === "/";

  return (
    <header className="sticky top-0 z-50 border-b border-white/40 bg-sage-100/75 backdrop-blur-xl">
      <div className="mx-auto max-w-6xl px-4 md:px-6">
        <div className="flex items-center justify-between gap-3 py-3 md:gap-4">
          <Logo />
          <nav
            className="hidden items-center gap-0.5 md:flex lg:gap-1"
            aria-label="Primary"
          >
            <NavLink to="/" end className={navLinkClass}>
              Home
            </NavLink>
            {onHome ? (
              <>
                <a
                  href="#features"
                  className="rounded-full px-3 py-2 text-sm font-medium text-taupe transition hover:bg-white/50 hover:text-ink"
                >
                  Features
                </a>
                <a
                  href="#how-it-works"
                  className="rounded-full px-3 py-2 text-sm font-medium text-taupe transition hover:bg-white/50 hover:text-ink"
                >
                  How it works
                </a>
              </>
            ) : (
              <>
                <Link
                  to="/#features"
                  className="rounded-full px-3 py-2 text-sm font-medium text-taupe transition hover:bg-white/50 hover:text-ink"
                >
                  Features
                </Link>
                <Link
                  to="/#how-it-works"
                  className="rounded-full px-3 py-2 text-sm font-medium text-taupe transition hover:bg-white/50 hover:text-ink"
                >
                  How it works
                </Link>
              </>
            )}
          </nav>
          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            <Link
              to="/sign-in"
              className="rounded-full px-3 py-2 text-sm font-semibold text-taupe transition hover:bg-white/50 hover:text-ink sm:px-4"
            >
              Sign in
            </Link>
            <Link
              to="/sign-up"
              className="rounded-full bg-gradient-to-r from-blush-300 to-blush-400 px-4 py-2 text-sm font-semibold text-white shadow-soft transition hover:brightness-105"
            >
              Get started
            </Link>
            <a
              href={assistant}
              className="hidden rounded-full border border-sage-300/70 bg-white/35 px-3 py-2 text-xs font-semibold text-sage-800 xl:inline-block"
            >
              Assistant
            </a>
          </div>
        </div>
        <nav
          className="flex gap-1 overflow-x-auto border-t border-white/30 py-2 md:hidden [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          aria-label="Sections"
        >
          <NavLink to="/" end className={({ isActive }) => navLinkClass({ isActive }) + " shrink-0 text-xs"}>
            Home
          </NavLink>
          <Link
            to="/#features"
            className="shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold text-taupe"
          >
            Features
          </Link>
          <Link
            to="/#how-it-works"
            className="shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold text-taupe"
          >
            How it works
          </Link>
          <Link
            to="/sign-in"
            className="shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold text-taupe"
          >
            Sign in
          </Link>
          <Link
            to="/sign-up"
            className="shrink-0 rounded-full bg-blush-200/80 px-3 py-1.5 text-xs font-semibold text-ink"
          >
            Get started
          </Link>
        </nav>
      </div>
    </header>
  );
}
