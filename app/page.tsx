"use client";

import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/nextjs";
import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-[radial-gradient(ellipse_at_top,_#f0fdf8_0%,_#fafaf9_42%,_#e7e5e4_100%)]">
      <div className="container mx-auto px-4 py-12">
        <nav className="mb-16 flex items-center justify-between">
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-stone-900">
            IdeaGen
          </h1>
          <div>
            <SignedOut>
              <SignInButton mode="modal">
                <button
                  type="button"
                  className="rounded-lg bg-teal-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-teal-900"
                >
                  Sign In
                </button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <div className="flex items-center gap-4">
                <Link
                  href="/product"
                  className="rounded-lg bg-teal-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-teal-900"
                >
                  Open app
                </Link>
                <UserButton showName={true} />
              </div>
            </SignedIn>
          </div>
        </nav>

        <section className="mx-auto max-w-3xl pb-16 pt-10 text-center">
          <p className="mb-4 text-xs font-semibold uppercase tracking-[0.22em] text-teal-800">
            AI agent economy
          </p>
          <h2 className="mb-6 font-serif text-5xl font-semibold leading-tight tracking-tight text-stone-900 md:text-6xl">
            Generate your next
            <br />
            business idea
          </h2>
          <p className="mx-auto mb-10 max-w-2xl text-lg text-stone-600">
            Sign in, add optional context, and stream a structured business idea
            for the AI agent economy. Generate and score share one request pool,
            1 free, 5 with Premium.
          </p>

          <SignedOut>
            <SignInButton mode="modal">
              <button
                type="button"
                className="rounded-xl bg-stone-900 px-8 py-4 text-lg font-semibold text-white transition hover:bg-stone-700"
              >
                Start free — 1 request included
              </button>
            </SignInButton>
          </SignedOut>
          <SignedIn>
            <Link href="/product">
              <button
                type="button"
                className="rounded-xl bg-stone-900 px-8 py-4 text-lg font-semibold text-white transition hover:bg-stone-700"
              >
                Go to generator
              </button>
            </Link>
          </SignedIn>
        </section>

        <section className="mx-auto grid max-w-4xl gap-6 md:grid-cols-2">
          <div className="rounded-2xl border border-stone-200 bg-white/90 p-8 shadow-sm">
            <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-teal-800">
              Free
            </p>
            <p className="mb-4 font-serif text-4xl font-semibold text-stone-900">
              $0
            </p>
            <ul className="mb-6 space-y-2 text-left text-stone-600">
              <li>✓ Sign-in required</li>
              <li>✓ 1 lifetime AI request</li>
              <li>✓ Optional context + industry chips</li>
              <li>✓ History and export (score uses your request)</li>
            </ul>
            <SignedOut>
              <SignInButton mode="modal">
                <button
                  type="button"
                  className="w-full rounded-xl border border-stone-300 py-3 font-semibold text-stone-800 transition hover:bg-stone-50"
                >
                  Try free
                </button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <Link
                href="/product"
                className="block w-full rounded-xl border border-stone-300 py-3 text-center font-semibold text-stone-800 transition hover:bg-stone-50"
              >
                Open free tier
              </Link>
            </SignedIn>
          </div>

          <div className="rounded-2xl border border-teal-900/20 bg-stone-900 p-8 text-white shadow-lg">
            <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-teal-300">
              Premium
            </p>
            <p className="mb-4 font-serif text-4xl font-semibold">
              $10
              <span className="text-lg font-normal text-stone-300">/month</span>
            </p>
            <ul className="mb-6 space-y-2 text-left text-stone-200">
              <li>✓ 5 lifetime AI requests</li>
              <li>✓ Generate and score share the pool</li>
              <li>✓ Same structured AI output</li>
              <li>✓ Managed via Clerk Billing</li>
            </ul>
            <SignedOut>
              <SignInButton mode="modal">
                <button
                  type="button"
                  className="w-full rounded-xl bg-teal-500 py-3 font-semibold text-stone-950 transition hover:bg-teal-400"
                >
                  Sign in to upgrade
                </button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <Link
                href="/product#upgrade"
                className="block w-full rounded-xl bg-teal-500 py-3 text-center font-semibold text-stone-950 transition hover:bg-teal-400"
              >
                Upgrade in app
              </Link>
            </SignedIn>
          </div>
        </section>
      </div>
    </main>
  );
}
