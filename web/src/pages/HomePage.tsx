import { Link } from "react-router-dom";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { HeroSection } from "@/components/HeroSection";
import { FeatureCards } from "@/components/FeatureCards";
import { HowItWorks } from "@/components/HowItWorks";
import { getAssistantUrl } from "@/lib/assistantUrl";
import { continueAsGuest } from "@/lib/guestMode";

function TrustSection() {
  return (
    <section id="trust" className="border-t border-white/50 bg-white/30 py-20 backdrop-blur-sm">
      <div className="mx-auto max-w-6xl px-4 md:px-6">
        <div className="grid gap-10 lg:grid-cols-2 lg:items-center">
          <div>
            <h2 className="font-display text-3xl font-semibold text-ink md:text-4xl text-balance">
              Built for trust, designed for appetite
            </h2>
            <p className="mt-3 text-taupe">
              Placeholder metrics for launch storytelling—swap with real data when you ship.
            </p>
            <div className="mt-10 grid grid-cols-3 gap-6">
              {[
                { k: "4.9", l: "Calm UX rating" },
                { k: "12+", l: "Cuisine signals" },
                { k: "24/7", l: "Always on" },
              ].map((s) => (
                <div key={s.l} className="text-center lg:text-left">
                  <p className="font-display text-2xl font-semibold text-ink md:text-3xl">{s.k}</p>
                  <p className="mt-1 text-xs text-taupe">{s.l}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-4">
            {[
              {
                q: "I skip twenty browser tabs now. I say what I want, and the thread stays focused.",
                a: "Jordan L.",
              },
              {
                q: "Guest mode let our team try the agent at a hackathon with zero friction.",
                a: "Sam K.",
              },
            ].map((t) => (
              <blockquote
                key={t.a}
                className="glass-panel rounded-3xl p-6 shadow-soft"
              >
                <p className="text-sm leading-relaxed text-ink/90">“{t.q}”</p>
                <footer className="mt-3 text-xs font-semibold text-taupe">{t.a}</footer>
              </blockquote>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  const assistant = getAssistantUrl();
  return (
    <section className="pb-24 pt-4">
      <div className="mx-auto max-w-6xl px-4 md:px-6">
        <div className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-sage-600 via-sage-700 to-ink p-10 text-center shadow-soft md:p-14">
          <div className="pointer-events-none absolute inset-0 bg-[url('https://images.unsplash.com/photo-1559339352-11d035aa65de?auto=format&fit=crop&w=1600&q=60')] bg-cover bg-center opacity-15 mix-blend-overlay" />
          <div className="relative">
            <h2 className="font-display text-3xl font-semibold text-white md:text-4xl text-balance">
              Step into the DineSmartAI agent
            </h2>
            <p className="mx-auto mt-3 max-w-lg text-sm text-white/85">
              Create an account for a saved profile, or continue as guest for an instant demo.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link
                to="/sign-up"
                className="inline-flex rounded-full bg-white px-8 py-3.5 text-sm font-semibold text-sage-800 shadow-soft transition hover:bg-blush-50"
              >
                Get started
              </Link>
              <button
                type="button"
                onClick={() => continueAsGuest()}
                className="inline-flex rounded-full border border-white/45 bg-white/10 px-8 py-3.5 text-sm font-semibold text-white backdrop-blur transition hover:bg-white/20"
              >
                Continue as guest
              </button>
              <a
                href={assistant}
                className="inline-flex items-center rounded-full px-6 py-3.5 text-sm font-semibold text-white/90 underline-offset-4 hover:underline"
              >
                Already set up? Open assistant
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function HomePage() {
  return (
    <div className="min-h-dvh bg-sage-100 bg-hero-mesh">
      <Navbar />
      <main>
        <HeroSection />
        <FeatureCards />
        <HowItWorks />
        <TrustSection />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
