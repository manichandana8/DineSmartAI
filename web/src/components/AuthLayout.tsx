import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Logo } from "./Logo";
import { continueAsGuest } from "@/lib/guestMode";

type AuthLayoutProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
  imageSrc: string;
  imageAlt: string;
  footerLink: { to: string; label: string; hint: string };
};

export function AuthLayout({
  title,
  subtitle,
  children,
  imageSrc,
  imageAlt,
  footerLink,
}: AuthLayoutProps) {
  return (
    <div className="min-h-dvh bg-sage-100 bg-hero-mesh">
      <div className="mx-auto grid min-h-dvh max-w-6xl md:grid-cols-2">
        <div className="relative hidden overflow-hidden md:block">
          <img src={imageSrc} alt={imageAlt} className="absolute inset-0 h-full w-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-sage-900/75 via-sage-900/25 to-blush-900/25" />
          <div className="absolute bottom-10 left-10 right-10 text-white">
            <p className="font-display text-3xl font-semibold leading-tight text-balance">
              DineSmartAI
            </p>
            <p className="mt-3 max-w-sm text-sm text-white/85">
              Premium entry, then the full agent—discovery, booking, and orders in one thread.
            </p>
          </div>
        </div>
        <div className="flex flex-col px-4 py-8 md:px-10 md:py-12">
          <div className="mb-6">
            <Logo />
          </div>
          <div className="flex flex-1 flex-col justify-center">
            <div className="glass-panel mx-auto w-full max-w-md rounded-[2rem] p-8 shadow-soft md:p-10">
              <h1 className="font-display text-2xl font-semibold text-ink md:text-3xl">{title}</h1>
              <p className="mt-2 text-sm text-taupe">{subtitle}</p>
              <div className="mt-8">{children}</div>
              <button
                type="button"
                onClick={() => continueAsGuest()}
                className="mt-6 w-full rounded-full border border-dashed border-sage-300 bg-sage-50/50 py-3 text-sm font-semibold text-sage-800 transition hover:border-blush-300 hover:bg-blush-50/40"
              >
                Continue as guest
              </button>
              <p className="mt-2 text-center text-xs text-taupe">
                Opens the AI agent instantly with default demo preferences.
              </p>
              <p className="mt-8 text-center text-sm text-taupe">
                {footerLink.hint}{" "}
                <Link to={footerLink.to} className="font-semibold text-blush-500 hover:underline">
                  {footerLink.label}
                </Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
