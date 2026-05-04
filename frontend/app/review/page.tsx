import Link from "next/link";

import { AiEvidenceButton } from "@/components/ai-evidence-button";
import { EvidenceSearchButton } from "@/components/evidence-search-button";
import { Panel } from "@/components/panel";
import { ReviewInbox } from "@/components/review-inbox";
import { getReviewQueue } from "@/lib/api";

export const dynamic = "force-dynamic";

type ReviewPageProps = {
  searchParams?: Promise<{
    status?: string;
    fact_type?: string;
    researcher_id?: string;
    min_confidence?: string;
    source_contains?: string;
  }>;
};

const statusFilters = [
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "all", label: "All evidence" },
];

const factTypes = [
  { key: "", label: "All fact types" },
  { key: "phd_institution", label: "PhD institution" },
  { key: "nationality", label: "Nationality" },
  { key: "home_institution", label: "Home institution" },
  { key: "birth_month", label: "Birth month" },
];

const confidenceFilters = [
  { key: "", label: "Any confidence" },
  { key: "0.7", label: "70%+" },
  { key: "0.85", label: "85%+" },
  { key: "0.95", label: "95%+" },
];

export default async function ReviewPage({ searchParams }: ReviewPageProps) {
  const params = searchParams ? await searchParams : {};
  const activeStatus = params.status || "pending";
  const candidates = await getReviewQueue({
    status: activeStatus,
    fact_type: params.fact_type,
    researcher_id: params.researcher_id,
    min_confidence: params.min_confidence,
    source_contains: params.source_contains,
  });
  const pendingCount = candidates.filter((candidate) => candidate.status === "pending").length;
  const approvedCount = candidates.filter((candidate) => candidate.status === "approved").length;
  const rejectedCount = candidates.filter((candidate) => candidate.status === "rejected").length;

  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-card">
          <span className="eyebrow">Evidence Review</span>
          <h1 className="hero-title">Triage extracted source claims.</h1>
          <p className="hero-copy">
            Filter pending and reviewed fact candidates by status, fact type, confidence, and source before approving evidence into the
            outreach-safe fact ledger.
          </p>
          <div className="kpi-grid">
            <div className="metric">
              <div className="metric-value">{candidates.length}</div>
              <div className="metric-label">Candidates in this view</div>
            </div>
            <div className="metric">
              <div className="metric-value">{pendingCount}</div>
              <div className="metric-label">Pending here</div>
            </div>
            <div className="metric">
              <div className="metric-value">{approvedCount}</div>
              <div className="metric-label">Approved here</div>
            </div>
            <div className="metric">
              <div className="metric-value">{rejectedCount}</div>
              <div className="metric-label">Rejected here</div>
            </div>
          </div>
        </div>
        <Panel title="Review scope" copy="Use quick status shortcuts or apply a more exact filter set.">
          <div className="stack">
            <div className="timeline-strip">
              {statusFilters.map((filter) => (
                <Link
                  className={`timeline-chip ${activeStatus === filter.key ? "selected-chip" : ""}`}
                  href={{ pathname: "/review", query: { status: filter.key } }}
                  key={filter.key}
                >
                  {filter.label}
                </Link>
              ))}
            </div>
            <form className="stack" method="get">
              <div className="form-grid">
                <label>
                  Status
                  <select defaultValue={activeStatus} name="status">
                    {statusFilters.map((filter) => (
                      <option key={filter.key} value={filter.key}>
                        {filter.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Fact type
                  <select defaultValue={params.fact_type || ""} name="fact_type">
                    {factTypes.map((filter) => (
                      <option key={filter.key || "all"} value={filter.key}>
                        {filter.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Confidence
                  <select defaultValue={params.min_confidence || ""} name="min_confidence">
                    {confidenceFilters.map((filter) => (
                      <option key={filter.key || "all"} value={filter.key}>
                        {filter.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Source contains
                  <input defaultValue={params.source_contains || ""} name="source_contains" placeholder="cv, repec, ideas..." />
                </label>
                {params.researcher_id ? <input name="researcher_id" type="hidden" value={params.researcher_id} /> : null}
              </div>
              <div className="template-actions">
                <button type="submit">Apply filters</button>
                <Link className="ghost-button" href="/review">
                  Clear filters
                </Link>
              </div>
            </form>
          </div>
        </Panel>
      </section>

      <Panel
        title="Review Results"
        copy="Pending items can be edited before approval; reviewed items remain visible for audit history."
      >
        {candidates.length ? (
          <ReviewInbox candidates={candidates} />
        ) : params.researcher_id && params.fact_type ? (
          <div className="empty-state compact-empty">
            <h3>No pending evidence exists for this blocker.</h3>
            <p className="muted">
              Roadshow has no extracted candidate to approve for this speaker yet. Search trusted sources first; if no public evidence is found,
              add the approved fact manually on the speaker dossier.
            </p>
            <div className="template-actions">
              <EvidenceSearchButton
                className="button-link"
                helperText="Checks RePEc Genealogy, ORCID, CEPR, institutional profiles, and linked CV pages for reviewable evidence."
                label="Search trusted evidence"
                researcherId={params.researcher_id}
              />
              <AiEvidenceButton className="ghost-button" researcherId={params.researcher_id} />
              <Link className="ghost-button" href={`/researchers/${params.researcher_id}?missing_fact=${params.fact_type}#manual-facts`}>
                Add approved {factTypes.find((factType) => factType.key === params.fact_type)?.label ?? "fact"}
              </Link>
            </div>
          </div>
        ) : (
          <p className="fine-print">No pending fact candidates are waiting for review.</p>
        )}
      </Panel>
    </div>
  );
}
