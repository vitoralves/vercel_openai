"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import {
  PricingTable,
  UserButton,
  useAuth,
  useUser,
} from "@clerk/nextjs";
import { fetchEventSource } from "@microsoft/fetch-event-source";

type Usage = {
  plan: "free" | "premium";
  used: number;
  limit: number;
  remaining: number;
};

const FREE_LIFETIME_LIMIT = 1;
const PREMIUM_LIFETIME_LIMIT = 5;

type IdeaScores = {
  novelty: number;
  feasibility: number;
  overall: number;
  notes: string;
};

type SavedIdea = {
  id: string;
  title: string;
  context: string;
  content: string;
  created_at: number;
  favorite: boolean;
  scores?: IdeaScores | null;
};

const INDUSTRY_CHIPS = [
  "Healthcare",
  "Fintech",
  "DevTools",
  "Climate",
  "Education",
  "Marketplace",
] as const;

function UsageBanner({
  usage,
  onUpgradeClick,
}: {
  usage: Usage | null;
  onUpgradeClick: () => void;
}) {
  if (!usage) {
    return (
      <div className="rounded-xl border border-stone-200/80 bg-white/70 px-4 py-3 text-sm text-stone-600 backdrop-blur">
        Checking your plan…
      </div>
    );
  }

  const remaining = usage.remaining ?? 0;
  const exhausted = remaining <= 0;
  const isPremium = usage.plan === "premium";

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm ${
        exhausted
          ? "border-amber-300/80 bg-amber-50/90 text-amber-950"
          : isPremium
            ? "border-teal-200/80 bg-teal-50/90 text-teal-950"
            : "border-stone-200/80 bg-white/80 text-stone-800"
      }`}
    >
      <div>
        <span className="font-semibold">
          {isPremium ? "Premium" : "Free"}
        </span>
        {" · "}
        {exhausted
          ? "No requests left"
          : `${remaining} request${remaining === 1 ? "" : "s"} left`}{" "}
        <span className={isPremium ? "text-teal-800/70" : "text-stone-500"}>
          ({usage.used}/{usage.limit} used · generate & score)
        </span>
      </div>
      <div className="flex items-center gap-3">
        {!isPremium && (exhausted || remaining <= 1) && (
          <button
            type="button"
            onClick={onUpgradeClick}
            className="rounded-lg bg-stone-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-stone-700"
          >
            Upgrade to Premium
          </button>
        )}
        <UserButton showName={true} />
      </div>
    </div>
  );
}

function IdeaGenerator() {
  const { getToken, has, isLoaded: authLoaded } = useAuth();
  const { user } = useUser();
  const clerkPremium = Boolean(
    has?.({ plan: "premium_subscription" }) || has?.({ plan: "premium" }),
  );
  const [usage, setUsage] = useState<Usage | null>(null);
  const [context, setContext] = useState("");
  const [activeChip, setActiveChip] = useState<string | null>(null);
  const [idea, setIdea] = useState("");
  const [activeIdeaId, setActiveIdeaId] = useState<string | null>(null);
  const [ideas, setIdeas] = useState<SavedIdea[]>([]);
  const [scores, setScores] = useState<IdeaScores | null>(null);
  const [status, setStatus] = useState<
    "idle" | "loading" | "streaming" | "error" | "limited"
  >("idle");
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [copied, setCopied] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const displayUsage: Usage | null = useMemo(() => {
    if (!usage) {
      if (!clerkPremium) return null;
      return {
        plan: "premium",
        used: 0,
        limit: PREMIUM_LIFETIME_LIMIT,
        remaining: PREMIUM_LIFETIME_LIMIT,
      };
    }
    if (clerkPremium && usage.plan === "free") {
      const used = usage.used ?? 0;
      return {
        plan: "premium",
        used,
        limit: PREMIUM_LIFETIME_LIMIT,
        remaining: Math.max(PREMIUM_LIFETIME_LIMIT - used, 0),
      };
    }
    return usage;
  }, [clerkPremium, usage]);

  const authHeaders = useCallback(async () => {
    const jwt = await getToken();
    if (!jwt) return null;
    return {
      Authorization: `Bearer ${jwt}`,
      "Content-Type": "application/json",
    };
  }, [getToken]);

  const loadUsage = useCallback(async () => {
    const headers = await authHeaders();
    if (!headers) return;
    const res = await fetch("/api/usage", { headers });
    if (!res.ok) return;
    const data = (await res.json()) as Usage;
    setUsage(data);
    if (data.plan === "premium") {
      setShowUpgrade(false);
      if ((data.remaining ?? 0) > 0) {
        setStatus((prev) => (prev === "limited" ? "idle" : prev));
        setError(null);
      } else {
        setStatus("limited");
      }
    } else if ((data.remaining ?? 0) <= 0) {
      setShowUpgrade(true);
      setStatus("limited");
    }
  }, [authHeaders]);

  const loadIdeas = useCallback(async () => {
    const headers = await authHeaders();
    if (!headers) return;
    const res = await fetch("/api/ideas", { headers });
    if (!res.ok) return;
    const data = (await res.json()) as { ideas: SavedIdea[] };
    setIdeas(data.ideas || []);
  }, [authHeaders]);

  useEffect(() => {
    if (!authLoaded) return;
    void loadUsage();
    void loadIdeas();
  }, [loadUsage, loadIdeas, user?.id, authLoaded, clerkPremium]);

  useEffect(() => {
    const refresh = () => {
      void loadUsage();
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [loadUsage]);

  useEffect(() => {
    if (!clerkPremium) return;
    setShowUpgrade(false);
    if ((displayUsage?.remaining ?? 1) > 0) {
      setStatus((prev) => (prev === "limited" ? "idle" : prev));
      setError(null);
    }
  }, [clerkPremium, displayUsage?.remaining]);

  const sortedIdeas = useMemo(() => {
    return [...ideas].sort((a, b) => {
      if (a.favorite !== b.favorite) return a.favorite ? -1 : 1;
      return b.created_at - a.created_at;
    });
  }, [ideas]);

  const applyChip = (chip: string) => {
    setActiveChip(chip);
    const tag = `Industry focus: ${chip}.`;
    setContext((prev) => {
      const without = prev
        .replace(/Industry focus:\s*[^.]*\.?\s*/gi, "")
        .trim();
      return without ? `${tag} ${without}`.slice(0, 500) : tag;
    });
  };

  const saveIdea = async (content: string, ctx: string) => {
    const headers = await authHeaders();
    if (!headers || !content.trim()) return null;
    const res = await fetch("/api/ideas", {
      method: "POST",
      headers,
      body: JSON.stringify({ content, context: ctx || undefined }),
    });
    if (!res.ok) return null;
    const saved = (await res.json()) as SavedIdea;
    setIdeas((prev) => [saved, ...prev.filter((i) => i.id !== saved.id)]);
    setActiveIdeaId(saved.id);
    return saved;
  };

  const generate = async () => {
    if (status === "loading" || status === "streaming") return;

    if ((displayUsage?.remaining ?? 0) <= 0) {
      setStatus("limited");
      if (displayUsage?.plan !== "premium") setShowUpgrade(true);
      setError(
        displayUsage?.plan === "premium"
          ? "Premium request limit reached. Generate and score share the same credits."
          : "Free tier limit reached. Upgrade to Premium for more requests.",
      );
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("loading");
    setError(null);
    setIdea("");
    setScores(null);
    setActiveIdeaId(null);

    const headers = await authHeaders();
    if (!headers) {
      setStatus("error");
      setError("Authentication required. Please sign in again.");
      return;
    }

    const ctx = context.trim();
    let buffer = "";
    try {
      await fetchEventSource("/api/generate", {
        method: "POST",
        headers,
        body: JSON.stringify({ context: ctx || undefined }),
        signal: controller.signal,
        async onopen(response) {
          if (response.ok) {
            setStatus("streaming");
            const plan = response.headers.get("X-Plan");
            const used = response.headers.get("X-Used");
            const limit = response.headers.get("X-Limit");
            const remaining = response.headers.get("X-Remaining");
            if (plan) {
              const nextPlan = plan === "premium" ? "premium" : "free";
              const nextLimit = limit
                ? Number(limit)
                : nextPlan === "premium"
                  ? PREMIUM_LIFETIME_LIMIT
                  : FREE_LIFETIME_LIMIT;
              const nextUsed = used ? Number(used) : 0;
              setUsage({
                plan: nextPlan,
                used: nextUsed,
                limit: nextLimit,
                remaining:
                  remaining === "" || remaining === null
                    ? Math.max(nextLimit - nextUsed, 0)
                    : Number(remaining),
              });
            }
            return;
          }

          let detail: Record<string, unknown> = {};
          try {
            const payload = await response.json();
            detail = (payload.detail as Record<string, unknown>) || payload;
          } catch {
            detail = {};
          }

          if (response.status === 402) {
            const nextPlan =
              detail.plan === "premium" || clerkPremium ? "premium" : "free";
            const nextLimit = Number(
              detail.limit ??
                (nextPlan === "premium"
                  ? PREMIUM_LIFETIME_LIMIT
                  : FREE_LIFETIME_LIMIT),
            );
            setStatus("limited");
            if (nextPlan !== "premium") setShowUpgrade(true);
            setError(
              (detail.message as string) ||
                "Request limit reached. Generate and score share the same credits.",
            );
            setUsage({
              plan: nextPlan,
              used: Number(detail.used ?? nextLimit),
              limit: nextLimit,
              remaining: Number(detail.remaining ?? 0),
            });
            throw new Error("quota");
          }

          if (response.status === 429) {
            setStatus("error");
            setError(
              (detail.message as string) ||
                "Too many requests. Please wait and try again.",
            );
            throw new Error("rate_limited");
          }

          setStatus("error");
          setError(
            (detail.message as string) ||
              `Request failed (${response.status}). Please try again.`,
          );
          throw new Error("request_failed");
        },
        onmessage(ev) {
          buffer += ev.data;
          setIdea(buffer);
        },
        onerror(err) {
          if (controller.signal.aborted) return;
          if (
            err instanceof Error &&
            ["quota", "request_failed", "rate_limited"].includes(err.message)
          ) {
            throw err;
          }
          setStatus("error");
          setError(
            "Stream interrupted. You were not charged if nothing was generated.",
          );
          throw err;
        },
      });

      if (!controller.signal.aborted) {
        if (buffer) {
          setStatus("idle");
          await saveIdea(buffer, ctx);
        } else {
          setStatus("error");
          setError("No idea was generated. Please try again.");
        }
        await loadUsage();
      }
    } catch {
      if (!controller.signal.aborted) {
        await loadUsage();
      }
    }
  };

  const toggleFavorite = async (ideaItem: SavedIdea) => {
    const headers = await authHeaders();
    if (!headers) return;
    const res = await fetch(`/api/ideas/${ideaItem.id}/favorite`, {
      method: "POST",
      headers,
      body: JSON.stringify({ favorite: !ideaItem.favorite }),
    });
    if (!res.ok) return;
    const updated = (await res.json()) as SavedIdea;
    setIdeas((prev) =>
      prev.map((i) => (i.id === updated.id ? updated : i)),
    );
  };

  const scoreCurrent = async () => {
    if (!idea.trim() || scoring) return;
    if ((displayUsage?.remaining ?? 0) <= 0) {
      setStatus("limited");
      if (displayUsage?.plan !== "premium") setShowUpgrade(true);
      setError(
        displayUsage?.plan === "premium"
          ? "Premium request limit reached. Generate and score share the same credits."
          : "Free tier limit reached. Upgrade to Premium for more requests.",
      );
      return;
    }
    const headers = await authHeaders();
    if (!headers) return;
    setScoring(true);
    setError(null);
    try {
      const res = await fetch("/api/ideas/score", {
        method: "POST",
        headers,
        body: JSON.stringify({
          content: idea,
          idea_id: activeIdeaId || undefined,
        }),
      });
      const payload = await res.json();
      if (!res.ok) {
        const detail = payload.detail || payload;
        if (res.status === 402) {
          const nextPlan =
            detail.plan === "premium" || clerkPremium ? "premium" : "free";
          const nextLimit = Number(
            detail.limit ??
              (nextPlan === "premium"
                ? PREMIUM_LIFETIME_LIMIT
                : FREE_LIFETIME_LIMIT),
          );
          setStatus("limited");
          if (nextPlan !== "premium") setShowUpgrade(true);
          setUsage({
            plan: nextPlan,
            used: Number(detail.used ?? nextLimit),
            limit: nextLimit,
            remaining: Number(detail.remaining ?? 0),
          });
        }
        setError(
          detail.message ||
            (typeof detail === "string" ? detail : "Failed to score idea."),
        );
        return;
      }
      const nextScores = payload.scores as IdeaScores;
      setScores(nextScores);
      if (payload.usage) {
        setUsage(payload.usage as Usage);
      } else {
        await loadUsage();
      }
      if (activeIdeaId) {
        setIdeas((prev) =>
          prev.map((i) =>
            i.id === activeIdeaId ? { ...i, scores: nextScores } : i,
          ),
        );
      }
    } finally {
      setScoring(false);
    }
  };

  const copyMarkdown = async () => {
    if (!idea) return;
    await navigator.clipboard.writeText(idea);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const downloadMarkdown = () => {
    if (!idea) return;
    const title =
      ideas.find((i) => i.id === activeIdeaId)?.title || "ideagen-idea";
    const slug = title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 48);
    const blob = new Blob([idea], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug || "ideagen-idea"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const openIdea = (item: SavedIdea) => {
    setIdea(item.content);
    setContext(item.context || "");
    setActiveIdeaId(item.id);
    setScores(item.scores || null);
    setStatus("idle");
    setError(null);
  };

  const exhausted = (displayUsage?.remaining ?? 0) <= 0;
  const busy = status === "loading" || status === "streaming";

  return (
    <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 lg:grid-cols-[260px_1fr]">
      <aside className="space-y-4 lg:sticky lg:top-8 lg:self-start">
        <UsageBanner
          usage={displayUsage}
          onUpgradeClick={() => setShowUpgrade(true)}
        />

        <div className="rounded-2xl border border-stone-200/80 bg-white/80 p-4 shadow-sm backdrop-blur">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-wide text-stone-800">
              History
            </h2>
            <span className="text-xs text-stone-400">{ideas.length}</span>
          </div>
          {sortedIdeas.length === 0 ? (
            <p className="text-sm text-stone-500">
              Generated ideas will appear here.
            </p>
          ) : (
            <ul className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">
              {sortedIdeas.map((item) => (
                <li key={item.id}>
                  <div
                    className={`rounded-xl border px-3 py-2 transition ${
                      activeIdeaId === item.id
                        ? "border-teal-700/40 bg-teal-50/80"
                        : "border-stone-200 bg-white hover:border-stone-300"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => openIdea(item)}
                      className="w-full text-left"
                    >
                      <p className="line-clamp-2 text-sm font-medium text-stone-800">
                        {item.title}
                      </p>
                      <p className="mt-1 text-xs text-stone-400">
                        {new Date(item.created_at * 1000).toLocaleString()}
                      </p>
                    </button>
                    <button
                      type="button"
                      onClick={() => void toggleFavorite(item)}
                      className="mt-2 text-xs font-medium text-teal-800 hover:underline"
                    >
                      {item.favorite ? "★ Favorited" : "☆ Favorite"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <div className="space-y-6">
        <header>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.22em] text-teal-800">
            Workspace
          </p>
          <h1 className="font-serif text-4xl font-semibold tracking-tight text-stone-900 md:text-5xl">
            Business Idea Generator
          </h1>
          <p className="mt-3 max-w-2xl text-stone-600">
            Pick an industry chip, add optional context, then stream a structured
            idea with Problem, ICP, MVP, Moat, Risks, and Go-to-market.
          </p>
        </header>

        <div className="rounded-2xl border border-stone-200/80 bg-white/85 p-6 shadow-sm backdrop-blur">
          <p className="mb-2 text-sm font-medium text-stone-700">Industry</p>
          <div className="mb-4 flex flex-wrap gap-2">
            {INDUSTRY_CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                disabled={busy}
                onClick={() => applyChip(chip)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                  activeChip === chip
                    ? "bg-teal-800 text-white"
                    : "border border-stone-300 bg-stone-50 text-stone-700 hover:border-teal-700/40 hover:bg-teal-50"
                } disabled:opacity-50`}
              >
                {chip}
              </button>
            ))}
          </div>

          <label
            htmlFor="context"
            className="mb-2 block text-sm font-medium text-stone-700"
          >
            Context{" "}
            <span className="font-normal text-stone-400">(optional)</span>
          </label>
          <textarea
            id="context"
            value={context}
            onChange={(e) => setContext(e.target.value.slice(0, 500))}
            rows={4}
            placeholder="e.g. B2B SaaS for clinics in Brazil, bootstrapped, targeting clinic managers…"
            className="w-full resize-y rounded-xl border border-stone-300 bg-white px-4 py-3 text-stone-800 outline-none ring-teal-700/20 placeholder:text-stone-400 focus:ring-2"
            disabled={busy}
          />
          <div className="mt-1 text-right text-xs text-stone-400">
            {context.length}/500
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void generate()}
              disabled={busy || exhausted}
              className="rounded-xl bg-teal-800 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-900 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy
                ? "Generating…"
                : idea
                  ? "Regenerate idea"
                  : "Generate idea"}
            </button>
            {status === "error" && (
              <button
                type="button"
                onClick={() => void generate()}
                disabled={busy || exhausted}
                className="rounded-xl border border-stone-300 px-5 py-2.5 text-sm font-medium text-stone-700 transition hover:bg-stone-50"
              >
                Retry
              </button>
            )}
            {idea && !busy && (
              <button
                type="button"
                onClick={() => {
                  setIdea("");
                  setScores(null);
                  setActiveIdeaId(null);
                  setStatus("idle");
                  setError(null);
                }}
                className="rounded-xl border border-stone-300 px-5 py-2.5 text-sm font-medium text-stone-700 transition hover:bg-stone-50"
              >
                Clear
              </button>
            )}
          </div>

          {error && (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          )}
        </div>

        <div className="rounded-2xl border border-stone-200/80 bg-white/90 p-8 shadow-sm">
          {idea && !busy && (
            <div className="mb-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void copyMarkdown()}
                className="rounded-lg border border-stone-300 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-50"
              >
                {copied ? "Copied" : "Copy Markdown"}
              </button>
              <button
                type="button"
                onClick={downloadMarkdown}
                className="rounded-lg border border-stone-300 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-50"
              >
                Download .md
              </button>
              <button
                type="button"
                onClick={() => void scoreCurrent()}
                disabled={scoring || exhausted}
                className="rounded-lg border border-teal-800/30 bg-teal-50 px-3 py-1.5 text-xs font-semibold text-teal-900 hover:bg-teal-100 disabled:opacity-50"
              >
                {scoring ? "Scoring…" : "Score this idea (1 request)"}
              </button>
            </div>
          )}

          {scores && (
            <div className="mb-6 rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-700">
              <p className="font-semibold text-stone-900">
                Scores · Novelty {scores.novelty}/10 · Feasibility{" "}
                {scores.feasibility}/10 · Overall {scores.overall}/10
              </p>
              {scores.notes && (
                <p className="mt-1 text-stone-600">{scores.notes}</p>
              )}
            </div>
          )}

          {status === "loading" && (
            <div className="space-y-4 py-6">
              <div className="h-8 w-1/2 animate-pulse rounded bg-stone-200" />
              <div className="h-4 w-1/3 animate-pulse rounded bg-stone-100" />
              <div className="space-y-2 pt-2">
                <div className="h-3 w-full animate-pulse rounded bg-stone-100" />
                <div className="h-3 w-11/12 animate-pulse rounded bg-stone-100" />
                <div className="h-3 w-4/5 animate-pulse rounded bg-stone-100" />
              </div>
              <div className="h-4 w-1/4 animate-pulse rounded bg-stone-100 pt-4" />
              <div className="h-3 w-full animate-pulse rounded bg-stone-100" />
              <div className="h-3 w-5/6 animate-pulse rounded bg-stone-100" />
            </div>
          )}

          {status !== "loading" && !idea && (
            <div className="py-14 text-center">
              <p className="font-serif text-xl text-stone-500">
                Your structured idea will stream here.
              </p>
              <p className="mt-2 text-sm text-stone-400">
                Sections: Problem · ICP · MVP · Moat · Risks · Go-to-market
              </p>
            </div>
          )}

          {idea && (
            <div className="markdown-content text-stone-700">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                {idea}
              </ReactMarkdown>
              {status === "streaming" && (
                <span className="ml-1 inline-block h-4 w-2 animate-pulse bg-teal-700 align-middle" />
              )}
            </div>
          )}
        </div>

        {showUpgrade && (
          <div
            id="upgrade"
            className="rounded-2xl border border-stone-200 bg-white/95 p-8 shadow-sm"
          >
            <h2 className="mb-2 text-center font-serif text-3xl text-stone-900">
              Upgrade to Premium
            </h2>
            <p className="mb-8 text-center text-stone-600">
              Premium unlocks 5 lifetime AI requests for $10/month. Generate and
              score share the same pool.
            </p>
            <PricingTable />
          </div>
        )}
      </div>
    </div>
  );
}

export default function Product() {
  return (
    <main className="min-h-screen bg-[radial-gradient(ellipse_at_top,_#f0fdf8_0%,_#fafaf9_42%,_#e7e5e4_100%)]">
      <div className="absolute left-4 top-4 z-10">
        <Link
          href="/"
          className="text-sm font-medium text-stone-600 transition hover:text-stone-900"
        >
          ← IdeaGen
        </Link>
      </div>
      <IdeaGenerator />
    </main>
  );
}
