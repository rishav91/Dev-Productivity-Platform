import type { Metadata } from "next";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type SourceType =
  | "github_pr"
  | "jira_ticket"
  | "slack_thread"
  | "repo_history"
  | "webhook_event";

interface EvidenceItem {
  source_type: SourceType;
  source_id: string;
  quote: string;
  rationale: string;
}

interface InsightPayload {
  status: "insight" | "no_issue" | "insufficient_evidence";
  blocker_type:
    | "scope_creep"
    | "review_bottleneck"
    | "dependency_block"
    | "unclear_requirements"
    | "none"
    | null;
  severity: number | null;
  owner: string | null;
  owner_confidence: number | null;
  summary: string;
  recommended_actions: string[];
  evidence: EvidenceItem[];
  missing_sources: string[];
  confidence: number;
  recurrence_count: number;
  baseline_cycle_p85_days: number | null;
}

interface ArtifactSnapshot {
  run_id: string;
  insight: InsightPayload;
  langsmith_trace_url: string | null;
}

async function getSnapshot(runId: string): Promise<ArtifactSnapshot> {
  const res = await fetch(`${API_BASE}/runs/${runId}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load run ${runId}: ${res.status}`);
  }
  return res.json();
}

export async function generateMetadata({
  params,
}: {
  params: { run_id: string };
}): Promise<Metadata> {
  return { title: `Analysis ${params.run_id.slice(0, 8)} — Dev Platform` };
}

export default async function ResultPage({
  params,
}: {
  params: { run_id: string };
}) {
  let snapshot: ArtifactSnapshot;

  try {
    snapshot = await getSnapshot(params.run_id);
  } catch (e) {
    return (
      <main className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center">
        <div className="text-center space-y-2">
          <p className="text-red-400 font-mono text-sm">Failed to load analysis</p>
          <p className="text-gray-500 text-xs">{String(e)}</p>
        </div>
      </main>
    );
  }

  const { insight, run_id, langsmith_trace_url } = snapshot;

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100 px-4 py-10">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs text-gray-500 font-mono mb-1">
              run/{run_id.slice(0, 8)}
            </p>
            <h1 className="text-xl font-semibold text-gray-100">
              Delivery Insight
            </h1>
          </div>
          <StatusBadge status={insight.status} />
        </div>

        {/* Summary card */}
        <Card>
          <p className="text-gray-200 leading-relaxed">{insight.summary}</p>
        </Card>

        {/* Insight details — only when status=insight */}
        {insight.status === "insight" && (
          <Card title="Finding">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <Row
                label="Blocker type"
                value={insight.blocker_type ?? "—"}
                mono
              />
              <Row
                label="Severity"
                value={
                  insight.severity ? (
                    <SeverityBar level={insight.severity} />
                  ) : (
                    "—"
                  )
                }
              />
              <Row
                label="Owner"
                value={
                  insight.owner ? (
                    <span>
                      {insight.owner}
                      {insight.owner_confidence != null && (
                        <span className="ml-2 text-gray-500 text-xs">
                          ({(insight.owner_confidence * 100).toFixed(0)}% conf)
                        </span>
                      )}
                    </span>
                  ) : (
                    <span className="text-gray-500 italic">unassigned</span>
                  )
                }
              />
              <Row
                label="Recurrence"
                value={
                  insight.recurrence_count > 0 ? (
                    <span className="text-amber-400 font-medium">
                      {insight.recurrence_count}× in last 90 days
                    </span>
                  ) : (
                    "First occurrence"
                  )
                }
              />
              <Row
                label="Baseline p85"
                value={
                  insight.baseline_cycle_p85_days != null
                    ? `${insight.baseline_cycle_p85_days.toFixed(1)} days`
                    : "Sparse history"
                }
              />
              <Row
                label="Confidence"
                value={`${(insight.confidence * 100).toFixed(0)}%`}
              />
            </dl>
          </Card>
        )}

        {/* Recommended actions */}
        {insight.recommended_actions.length > 0 && (
          <Card title="Recommended actions">
            <ul className="space-y-2">
              {insight.recommended_actions.map((action, i) => (
                <li key={i} className="flex gap-2 text-sm text-gray-300">
                  <span className="text-blue-400 mt-0.5 shrink-0">→</span>
                  {action}
                </li>
              ))}
            </ul>
          </Card>
        )}

        {/* Evidence */}
        {insight.evidence.length > 0 && (
          <Card title="Evidence">
            <div className="space-y-3">
              {insight.evidence.map((e, i) => (
                <div
                  key={i}
                  className="border border-gray-800 rounded-md p-3 space-y-1"
                >
                  <div className="flex items-center gap-2">
                    <SourceChip sourceType={e.source_type} />
                    <span className="text-xs text-gray-500 font-mono">
                      {e.source_id}
                    </span>
                  </div>
                  <blockquote className="text-sm text-gray-300 italic border-l-2 border-gray-700 pl-3">
                    &ldquo;{e.quote}&rdquo;
                  </blockquote>
                  <p className="text-xs text-gray-500">{e.rationale}</p>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Missing sources */}
        {insight.missing_sources.length > 0 && (
          <div className="flex items-center gap-2 text-xs text-amber-400/70">
            <span>⚠</span>
            <span>
              Missing inputs:{" "}
              {insight.missing_sources.map((s) => (
                <code key={s} className="font-mono mx-1">
                  {s}
                </code>
              ))}
              — findings may be incomplete.
            </span>
          </div>
        )}

        {/* LangSmith trace link */}
        {langsmith_trace_url && (
          <div className="pt-2 border-t border-gray-800">
            <a
              href={langsmith_trace_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-500 hover:text-blue-400 font-mono"
            >
              View LangSmith trace →
            </a>
          </div>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Card({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
      {title && (
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          {title}
        </h2>
      )}
      {children}
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <>
      <dt className="text-gray-500">{label}</dt>
      <dd className={mono ? "font-mono text-gray-200" : "text-gray-200"}>
        {value}
      </dd>
    </>
  );
}

function StatusBadge({
  status,
}: {
  status: InsightPayload["status"];
}) {
  const styles = {
    insight: "bg-red-950 text-red-300 border-red-800",
    no_issue: "bg-green-950 text-green-300 border-green-800",
    insufficient_evidence: "bg-gray-800 text-gray-400 border-gray-700",
  };
  const labels = {
    insight: "Blocker detected",
    no_issue: "No issue",
    insufficient_evidence: "Insufficient evidence",
  };
  return (
    <span
      className={`text-xs font-medium px-2.5 py-1 rounded-full border ${styles[status]}`}
    >
      {labels[status]}
    </span>
  );
}

function SeverityBar({ level }: { level: number }) {
  const colors = [
    "",
    "bg-green-500",
    "bg-yellow-400",
    "bg-orange-400",
    "bg-red-500",
    "bg-red-700",
  ];
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className={`h-2 w-4 rounded-sm ${i <= level ? colors[level] : "bg-gray-700"}`}
          />
        ))}
      </div>
      <span className="text-gray-400 text-xs">{level}/5</span>
    </div>
  );
}

function SourceChip({ sourceType }: { sourceType: SourceType }) {
  const styles: Record<SourceType, string> = {
    github_pr: "bg-purple-950 text-purple-300",
    jira_ticket: "bg-blue-950 text-blue-300",
    slack_thread: "bg-green-950 text-green-300",
    repo_history: "bg-gray-800 text-gray-400",
    webhook_event: "bg-gray-800 text-gray-400",
  };
  const labels: Record<SourceType, string> = {
    github_pr: "GitHub PR",
    jira_ticket: "Jira",
    slack_thread: "Slack",
    repo_history: "Repo",
    webhook_event: "Webhook",
  };
  return (
    <span
      className={`text-xs font-medium px-1.5 py-0.5 rounded ${styles[sourceType]}`}
    >
      {labels[sourceType]}
    </span>
  );
}
