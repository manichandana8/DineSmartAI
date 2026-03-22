const steps = [
  {
    n: "1",
    title: "Tell DineSmartAI what you want",
    body: "Cuisine, neighborhood, dietary needs, vibe—say it naturally.",
  },
  {
    n: "2",
    title: "Get intelligent recommendations",
    body: "Curated picks that respect your constraints, not generic search noise.",
  },
  {
    n: "3",
    title: "Let the agent reserve or order",
    body: "Choose how to follow through, with explicit confirmations along the way.",
  },
  {
    n: "4",
    title: "Enjoy your meal",
    body: "Show up—or track pickup—knowing the plan matches what you asked for.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="py-20">
      <div className="mx-auto max-w-6xl px-4 md:px-6">
        <h2 className="text-center font-display text-3xl font-semibold text-ink md:text-4xl">
          How it works
        </h2>
        <p className="mx-auto mt-3 max-w-lg text-center text-sm text-taupe">
          Four calm steps from idea to table—powered by the DineSmartAI agent.
        </p>
        <ol className="mx-auto mt-14 grid max-w-3xl gap-8">
          {steps.map((s) => (
            <li key={s.n} className="flex gap-5">
              <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-blush-200 to-blush-300 font-display text-lg font-bold text-white shadow-sm">
                {s.n}
              </span>
              <div className="pt-1">
                <h3 className="font-display text-xl font-semibold text-ink">{s.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-taupe">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
