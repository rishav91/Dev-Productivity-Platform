import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Analysis Runs — Dev Platform" };

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PAGE_SIZE = 10;

interface RunSummary {
  run_id: string;
  pr_id: string;
  ticket_id: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  blocker_type: string | null;
  severity: number | null;
  insight_status: string | null;
}

async function getRuns(page: number): Promise<RunSummary[]> {
  const res = await fetch(
    `${API_BASE}/runs?page=${page}&page_size=${PAGE_SIZE}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error(`Failed to fetch runs: ${res.status}`);
  return res.json();
}

export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const { page: pageParam } = await searchParams;
  const page = Math.max(1, parseInt(pageParam ?? "1", 10));

  let runs: RunSummary[] = [];
  let error: string | null = null;

  try {
    runs = await getRuns(page);
  } catch (e) {
    error = String(e);
  }

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100 px-4 py-10">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Analysis Runs</h1>
          <p className="text-xs text-gray-500 mt-1">
            Pick a run to view its insight
          </p>
        </div>

        {error ? (
          <div className="text-red-400 font-mono text-sm bg-gray-900 border border-gray-800 rounded-xl p-5">
            {error}
          </div>
        ) : runs.length === 0 ? (
          <div className="text-gray-500 text-sm bg-gray-900 border border-gray-800 rounded-xl p-5">
            No runs found.
          </div>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => (
              <Link
                key={run.run_id}
                href={`/result/${run.run_id}`}
                className="block bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-600 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs text-gray-500">
                        {run.run_id.slice(0, 8)}
                      </span>
                      <span className="text-gray-600 text-xs">·</span>
                      <span className="text-sm text-gray-300">{run.pr_id}</span>
                      <span className="text-gray-600 text-xs">·</span>
                      <span className="text-sm text-gray-400">{run.ticket_id}</span>
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                      {run.blocker_type && run.blocker_type !== "none" && (
                        <span className="text-xs font-mono text-purple-300 bg-purple-950 px-1.5 py-0.5 rounded">
                          {run.blocker_type}
                        </span>
                      )}
                      {run.severity != null && (
                        <SeverityPips level={run.severity} />
                      )}
                      <span className="text-xs text-gray-600">
                        {new Date(run.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                  <div className="shrink-0">
                    <InsightBadge status={run.insight_status} runStatus={run.status} />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}

        {/* Pagination */}
        <div className="flex items-center justify-between pt-2">
          {page > 1 ? (
            <Link
              href={`/?page=${page - 1}`}
              className="text-xs text-blue-500 hover:text-blue-400 font-mono"
            >
              ← Previous
            </Link>
          ) : (
            <span />
          )}
          <span className="text-xs text-gray-600 font-mono">Page {page}</span>
          {runs.length === PAGE_SIZE ? (
            <Link
              href={`/?page=${page + 1}`}
              className="text-xs text-blue-500 hover:text-blue-400 font-mono"
            >
              Next →
            </Link>
          ) : (
            <span />
          )}
        </div>
      </div>
    </main>
  );
}

function InsightBadge({
  status,
  runStatus,
}: {
  status: string | null;
  runStatus: string;
}) {
  if (runStatus === "failed") {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full border bg-gray-800 text-gray-500 border-gray-700">
        failed
      </span>
    );
  }
  if (runStatus !== "complete" || status == null) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full border bg-gray-800 text-gray-400 border-gray-700">
        {runStatus}
      </span>
    );
  }
  const styles: Record<string, string> = {
    insight: "bg-red-950 text-red-300 border-red-800",
    no_issue: "bg-green-950 text-green-300 border-green-800",
    insufficient_evidence: "bg-gray-800 text-gray-400 border-gray-700",
  };
  const labels: Record<string, string> = {
    insight: "Blocker",
    no_issue: "No issue",
    insufficient_evidence: "Inconclusive",
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full border ${styles[status] ?? "bg-gray-800 text-gray-400 border-gray-700"}`}
    >
      {labels[status] ?? status}
    </span>
  );
}

function SeverityPips({ level }: { level: number }) {
  const colors = ["", "bg-green-500", "bg-yellow-400", "bg-orange-400", "bg-red-500", "bg-red-700"];
  return (
    <span className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className={`inline-block h-1.5 w-3 rounded-sm ${i <= level ? colors[level] : "bg-gray-700"}`}
        />
      ))}
      <span className="text-xs text-gray-500 ml-1">{level}/5</span>
    </span>
  );
}
