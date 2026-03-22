const features = [
  {
    title: "AI restaurant discovery",
    body: "Describe cravings in plain language; we narrow the universe before you ever see a list.",
    icon: "✦",
  },
  {
    title: "Personalized recommendations",
    body: "Your diet, spice, budget, and ambience preferences shape every suggestion.",
    icon: "◇",
  },
  {
    title: "Dish-level intelligence",
    body: "Go beyond cuisine tags—think ingredients, preparations, and what actually lands on the plate.",
    icon: "◎",
  },
  {
    title: "Reservation automation",
    body: "When you’re ready, the agent can drive structured booking flows with clear confirmation.",
    icon: "◆",
  },
  {
    title: "Order assistance",
    body: "Takeout and delivery intents stay in-thread with helpful next steps.",
    icon: "→",
  },
  {
    title: "Phone-call booking",
    body: "Optional voice-agent path for venues where a call is still the fastest route.",
    icon: "☎",
  },
];

export function FeatureCards() {
  return (
    <section id="features" className="border-y border-white/50 bg-white/40 py-20 backdrop-blur-sm">
      <div className="mx-auto max-w-6xl px-4 md:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-display text-3xl font-semibold text-ink md:text-4xl text-balance">
            One assistant, every dining moment
          </h2>
        </div>
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <article
              key={f.title}
              className="glass-panel group rounded-3xl p-7 shadow-soft transition duration-300 hover:-translate-y-1 hover:shadow-lg"
            >
              <span className="text-2xl text-blush-400 transition group-hover:scale-110">{f.icon}</span>
              <h3 className="mt-4 font-display text-lg font-semibold text-ink">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-taupe">{f.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
