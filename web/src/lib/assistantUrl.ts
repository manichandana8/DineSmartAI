/** DineSmartAI AI chat UI (FastAPI serves `/assistant` when marketing build is deployed). */
export function getAssistantUrl(): string {
  const v = import.meta.env.VITE_ASSISTANT_URL as string | undefined;
  if (v && v.trim()) return v.trim().replace(/\/$/, "");
  return "/assistant";
}
