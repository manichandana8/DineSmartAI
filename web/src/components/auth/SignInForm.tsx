import { enterAssistantSignedIn } from "@/lib/guestMode";

export function SignInForm() {
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        enterAssistantSignedIn();
      }}
    >
      <div>
        <label htmlFor="email" className="block text-xs font-semibold uppercase tracking-wide text-taupe">
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          className="mt-1.5 w-full rounded-2xl border border-sage-200/80 bg-white/70 px-4 py-3 text-sm text-ink shadow-sm outline-none ring-blush-300/40 transition placeholder:text-sage-400 focus:border-blush-300 focus:ring-2"
        />
      </div>
      <div>
        <label htmlFor="password" className="block text-xs font-semibold uppercase tracking-wide text-taupe">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          className="mt-1.5 w-full rounded-2xl border border-sage-200/80 bg-white/70 px-4 py-3 text-sm text-ink shadow-sm outline-none ring-blush-300/40 transition placeholder:text-sage-400 focus:border-blush-300 focus:ring-2"
        />
      </div>
      <div className="flex items-center justify-between gap-3 pt-1">
        <label className="flex cursor-pointer items-center gap-2 text-sm text-taupe">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-sage-300 text-blush-400 focus:ring-blush-300"
          />
          Remember me
        </label>
        <button type="button" className="text-sm font-semibold text-blush-500 hover:underline">
          Forgot password?
        </button>
      </div>
      <button
        type="submit"
        className="mt-2 w-full rounded-full bg-ink py-3.5 text-sm font-semibold text-white shadow-soft transition hover:bg-sage-900"
      >
        Sign in
      </button>
      <button
        type="button"
        onClick={() => enterAssistantSignedIn()}
        className="flex w-full items-center justify-center gap-2 rounded-full border border-sage-200 bg-white/80 py-3 text-sm font-semibold text-ink shadow-sm transition hover:bg-white"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden>
          <path
            fill="currentColor"
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
          />
          <path
            fill="currentColor"
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
          />
          <path
            fill="currentColor"
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
          />
          <path
            fill="currentColor"
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
          />
        </svg>
        Continue with Google
      </button>
    </form>
  );
}
