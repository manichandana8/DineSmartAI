import { Link } from "react-router-dom";
import { continueAsGuest } from "@/lib/guestMode";

const imgHero =
  "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1200&q=80";

export function HeroSection() {
  return (
    <section className="relative mx-auto max-w-6xl px-4 pb-20 pt-10 md:px-6 md:pb-28 md:pt-14">
      <div className="grid items-center gap-14 lg:grid-cols-2 lg:gap-10">
        <div className="order-2 lg:order-1">
          <p className="mb-4 inline-flex animate-soft-pulse rounded-full border border-white/60 bg-white/50 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-sage-700 shadow-sm backdrop-blur">
            DineSmartAI · AI agent
          </p>
          <h1 className="font-display text-4xl font-semibold leading-[1.08] tracking-tight text-ink md:text-5xl lg:text-[3.35rem] text-balance">
            Your AI dining concierge
          </h1>
          <p className="mt-5 max-w-lg text-lg leading-relaxed text-taupe">
            Discover restaurants that fit your mood, diet, and budget—then let the agent help with
            reservations, orders, and phone booking. One calm conversation from craving to table.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              to="/sign-up"
              className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-blush-300 to-blush-400 px-8 py-3.5 text-sm font-semibold text-white shadow-soft transition hover:brightness-105 hover:shadow-glow"
            >
              Get started
            </Link>
            <button
              type="button"
              onClick={() => continueAsGuest()}
              className="inline-flex items-center justify-center rounded-full border border-sage-300/80 bg-white/60 px-8 py-3.5 text-sm font-semibold text-ink shadow-sm backdrop-blur transition hover:bg-white/90"
            >
              Continue as guest
            </button>
          </div>
          <p className="mt-4 text-xs text-taupe">
            Guest mode uses default preferences—no account required. Upgrade anytime.
          </p>
        </div>

        <div className="order-1 lg:order-2">
          <div className="relative mx-auto max-w-md lg:max-w-none">
            <div className="pointer-events-none absolute -right-4 -top-8 h-40 w-40 rounded-full bg-blush-200/50 blur-3xl animate-soft-pulse" />
            <div className="pointer-events-none absolute -bottom-10 -left-6 h-48 w-48 rounded-full bg-sage-300/45 blur-3xl" />

            <div className="relative">
              <div className="glass-panel absolute -left-4 top-[12%] z-10 hidden max-w-[200px] animate-float rounded-2xl p-4 shadow-soft md:block">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-blush-500">
                  Tonight
                </p>
                <p className="mt-1 font-display text-sm font-semibold text-ink">Quiet table for two</p>
              </div>
              <div className="glass-panel absolute -right-2 bottom-[18%] z-10 hidden max-w-[180px] animate-float-delayed rounded-2xl p-4 shadow-soft md:block">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-sage-600">
                  Agent
                </p>
                <p className="mt-1 font-display text-sm font-semibold text-ink">Reserve & order</p>
                <p className="mt-1 text-xs text-taupe">With your OK</p>
              </div>

              <div className="glass-panel relative overflow-hidden rounded-[2rem] p-2 shadow-soft ring-1 ring-white/60">
                <img
                  src={imgHero}
                  alt=""
                  width={900}
                  height={1100}
                  className="aspect-[4/5] w-full rounded-[1.65rem] object-cover"
                  loading="eager"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
