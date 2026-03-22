/**
 * Guest / demo entry: skip account, use default preferences, show demo banner in the chat UI.
 */
import { getAssistantUrl } from "./assistantUrl";

export const GUEST_STORAGE_KEY = "dinesmartai_guest";
export const DEMO_PREFS_KEY = "dinesmartai_demo_prefs";

/** Defaults for optional future profile merge (mock). */
export const DEFAULT_GUEST_PREFS = {
  mode: "guest" as const,
  cuisine: ["Mediterranean", "Japanese", "Italian"],
  dietary: "no_restrictions",
  spice: "medium",
  budget: 2,
  diningModes: ["dine_in", "takeout"],
  ambience: ["casual", "date_night"],
  location: "San Francisco, CA",
};

export function setGuestDemoSession(): void {
  try {
    localStorage.setItem(GUEST_STORAGE_KEY, "1");
    localStorage.setItem(DEMO_PREFS_KEY, JSON.stringify(DEFAULT_GUEST_PREFS));
  } catch {
    /* private mode */
  }
}

export function clearGuestDemoSession(): void {
  try {
    localStorage.removeItem(GUEST_STORAGE_KEY);
    localStorage.removeItem(DEMO_PREFS_KEY);
  } catch {
    /* ignore */
  }
}

/** Frictionless entry into the AI agent with demo treatment. */
export function continueAsGuest(): void {
  setGuestDemoSession();
  const base = getAssistantUrl();
  const url = base.includes("?") ? `${base}&demo=1` : `${base}?demo=1`;
  window.location.assign(url);
}

/** After sign-in / sign-up (mock): full experience without demo banner. */
export function enterAssistantSignedIn(): void {
  clearGuestDemoSession();
  window.location.assign(getAssistantUrl());
}
