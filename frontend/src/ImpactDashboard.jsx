import { useEffect, useMemo, useRef, useState } from "react";

const repository = {
  name: "usecase5-demo/customer-platform",
  defaultBranch: "main",
  branches: ["main", "feature/customer-contract-v2", "feature/order-api-update"],
  files: [
    { path: "README.md", service: "", schema: "", symbol: "README", content: "# Customer Platform\n\nService documentation and local setup." },
    { path: "order-api/Controllers/OrderController.cs", service: "order-api", schema: "", symbol: "GET /api/orders", content: '[HttpGet("/api/orders")]\npublic IActionResult GetOrders() => Ok(service.GetOrders());' },
    { path: "customer-api/migrations/customer_contract.sql", service: "customer-api", schema: "customer_contract", symbol: "customer_contract", content: "CREATE TABLE customer_contract (\n  customer_id INT,\n  account_number VARCHAR(32),\n  status VARCHAR(20)\n);" },
    { path: "customer-api/Models/CustomerDto.cs", service: "customer-api", schema: "", symbol: "CustomerDto", content: "public class CustomerDto {\n  public int CustomerId { get; set; }\n  public string Status { get; set; }\n}" }
  ]
};

const changePresets = {
  "README.md": { title: "Update onboarding documentation", description: "Clarify local setup instructions.", content: "# Customer Platform\n\nUpdated onboarding and local setup instructions.", breaking: false },
  "order-api/Controllers/OrderController.cs": { title: "Change orders API response contract", description: "Update the public orders endpoint contract for the new response model.", content: '[HttpGet("/api/orders")]\npublic ActionResult<OrderSummary[]> GetOrders() => Ok(service.GetOrderSummaries());', breaking: true },
  "customer-api/migrations/customer_contract.sql": { title: "Remove legacy account number from customer contract", description: "Apply the proposed shared schema change.", content: "CREATE TABLE customer_contract (\n  customer_id INT,\n  status VARCHAR(20)\n);", breaking: true },
  "customer-api/Models/CustomerDto.cs": { title: "Add customer tier to response model", description: "Expose customer tier to downstream callers.", content: "public class CustomerDto {\n  public int CustomerId { get; set; }\n  public string Status { get; set; }\n  public string Tier { get; set; }\n}", breaking: false }
};

const stages = ["PR Trigger", "Diff Analysis", "Dependencies", "Consumers", "Schemas", "Test Mapping", "Severity", "PR Actions"];
const emptyResult = { severity: "Not analyzed", severity_reasons: [], affected_services: [], api_consumers: [], schema_impacts: [], affected_tests: [], owning_contacts: [], notification_status: "not_required", gate_status: "not_required", comment_markdown: "Create and analyze a pull request to generate the reviewer comment.", elapsed_seconds: 0 };

function humanize(v) { return String(v ?? "Not available").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase()); }
function Badge({ value }) { const n = String(value || "").toLowerCase(); const tone = n.includes("critical") || n.includes("pending") ? "danger" : n.includes("high") ? "warn" : n.includes("low") || n.includes("sent") || n.includes("approved") ? "good" : "neutral"; return <span className={`badge ${tone}`}>{humanize(value)}</span>; }
function SeverityBadge({ value }) { return <span className={`severity-badge severity-${String(value || "unknown").toLowerCase()}`}>{humanize(value)}</span>; }
async function request(path, options = {}) { const r = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options }); if (!r.ok) throw new Error(`${r.status} ${await r.text()}`); return r.json(); }

function parsePatch(patch = "") {
  const rows = [];
  let oldLine = 0;
  let newLine = 0;
  for (const line of patch.split("\n")) {
    const hunk = line.match(/^@@ -(?<old>\d+)(?:,\d+)? \+(?<next>\d+)(?:,\d+)? @@/);
    if (hunk) {
      oldLine = Number(hunk.groups.old);
      newLine = Number(hunk.groups.next);
      rows.push({ type: "hunk", text: line });
      continue;
    }
    if (line.startsWith("+")) {
      rows.push({ type: "addition", oldLine: "", newLine: newLine++, text: line.slice(1) });
    } else if (line.startsWith("-")) {
      rows.push({ type: "deletion", oldLine: oldLine++, newLine: "", text: line.slice(1) });
    } else if (line.startsWith("\\")) {
      rows.push({ type: "meta", oldLine: "", newLine: "", text: line });
    } else {
      rows.push({ type: "context", oldLine: oldLine++, newLine: newLine++, text: line.startsWith(" ") ? line.slice(1) : line });
    }
  }
  return rows;
}

function highlightCode(text) {
  const tokens = text.split(/(\/\/.*|#. *|\b(?:class|const|def|function|import|from|if|else|return|new|public|private|async|await|true|false|null|None)\b|\b\d+(?:\.\d+)?\b|["'`][^"'`]*["'`])/g);
  return tokens.map((token, index) => {
    if (/^(\/\/|#\.).*/.test(token)) return <span className="diff-comment" key={index}>{token}</span>;
    if (/^\b(?:class|const|def|function|import|from|if|else|return|new|public|private|async|await|true|false|null|None)\b$/.test(token)) return <span className="diff-keyword" key={index}>{token}</span>;
    if (/^\d/.test(token)) return <span className="diff-number" key={index}>{token}</span>;
    if (/^["'`]/.test(token)) return <span className="diff-string" key={index}>{token}</span>;
    return <span key={index}>{token}</span>;
  });
}

function DiffViewer({ file }) {
  const rows = parsePatch(file?.patch || "");
  return <div className="diff-viewer">
    <div className="diff-toolbar"><strong>{file?.path}</strong><span>{rows.filter(row => row.type === "addition").length} additions · {rows.filter(row => row.type === "deletion").length} deletions</span></div>
    {rows.length ? <div className="diff-table">{rows.map((row, index) => row.type === "hunk" ? <div className="diff-row diff-hunk" key={index}><span className="diff-gutter" /><span className="diff-gutter" /><code>{row.text}</code></div> : <div className={`diff-row diff-${row.type}`} key={index}><span className="diff-gutter">{row.oldLine}</span><span className="diff-gutter">{row.newLine}</span><code><b className="diff-marker">{row.type === "addition" ? "+" : row.type === "deletion" ? "-" : " "}</b>{highlightCode(row.text)}</code></div>)}</div> : <div className="diff-empty">GitHub did not return a patch for this file. The file may be binary or the patch may be truncated.</div>}
  </div>;
}

function HostedIntegration({ provider, setProvider, status }) {
  const details = status?.[provider];
  const [repositoryName, setRepositoryName] = useState("");
  const [prNumber, setPrNumber] = useState("");
  const [manualResult, setManualResult] = useState(null);
  const [manualError, setManualError] = useState("");
  const [pullRequests, setPullRequests] = useState([]);
  const [loadingPullRequests, setLoadingPullRequests] = useState(false);
  const [workspace, setWorkspace] = useState(null);
  const [selectedFilePath, setSelectedFilePath] = useState("");
  const [editedContent, setEditedContent] = useState("");
  const [editingFile, setEditingFile] = useState(false);
  const [commitMessage, setCommitMessage] = useState("Update file from impact analysis assistant");
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [updatingFile, setUpdatingFile] = useState(false);
  const [reviewingPR, setReviewingPR] = useState(false);
  const [mergingPR, setMergingPR] = useState(false);
  const [reviewState, setReviewState] = useState("");
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [analysisHistory, setAnalysisHistory] = useState([]);
  const analysisKeyRef = useRef("");
  const analysisPromiseRef = useRef(null);
  const manualReady = provider === "github" && details?.manual_analysis_configured;
  const hostedAnalysis = manualResult?.workflow;
  const hostedServices = hostedAnalysis?.affected_services || [];
  const hostedConsumers = hostedAnalysis?.api_consumers || [];
  const hostedSchemas = hostedAnalysis?.schema_impacts || [];
  const hostedTests = hostedAnalysis?.affected_tests || [];

  async function analyzeHostedPR(number, force = false) {
    const repositoryValue = repositoryName.trim();
    const key = `${repositoryValue}#${number}`;
    if (!manualReady || !repositoryValue || !Number(number) || (!force && analysisKeyRef.current === key)) return;
    if (analysisPromiseRef.current) return analysisPromiseRef.current;
    const startedAt = performance.now();
    setManualError("");
    setAnalysisRunning(true);
    const promise = request(details.manual_analysis_path, {
      method: "POST",
      body: JSON.stringify({ repository: repositoryValue, pr_number: Number(number) })
    }).then(data => {
      const runtime = Number(((performance.now() - startedAt) / 1000).toFixed(2));
      const next = { ...data, runtime_seconds: runtime };
      setManualResult(next);
      setAnalysisHistory(history => [...history, { key, runtime_seconds: runtime }]);
      analysisKeyRef.current = key;
      setReviewState("");
      return next;
    }).catch(error => {
      setManualError(`Analysis failed: ${error.message}`);
      throw error;
    }).finally(() => {
      analysisPromiseRef.current = null;
      setAnalysisRunning(false);
    });
    analysisPromiseRef.current = promise;
    return promise;
  }

  async function loadPullRequests() {
    setManualError("");
    setLoadingPullRequests(true);
    try {
      const data = await request(`/integration/github/pull-requests?repository=${encodeURIComponent(repositoryName.trim())}`);
      setPullRequests(data.pull_requests || []);
      if (!data.pull_requests?.length) setManualError("No open pull requests found for this repository.");
    } catch (error) {
      setManualError(error.message);
    } finally {
      setLoadingPullRequests(false);
    }
  }

  async function loadWorkspace(number) {
    setManualError("");
    setWorkspaceLoading(true);
    try {
      const data = await request(`/integration/github/pull-request?repository=${encodeURIComponent(repositoryName.trim())}&pr_number=${number}`);
      setWorkspace(data);
      const firstFile = data.files?.find(file => file.change_type !== "deleted") || data.files?.[0];
      setSelectedFilePath(firstFile?.path || "");
      setEditedContent(firstFile?.content || "");
      setEditingFile(false);
      if (Number(number)) analyzeHostedPR(number, true).catch(() => undefined);
    } catch (error) {
      setManualError(error.message);
    } finally {
      setWorkspaceLoading(false);
    }
  }

  function refreshSelectedPR() {
    if (prNumber && !workspaceLoading) loadWorkspace(Number(prNumber));
  }

  function selectHostedFile(file) {
    setSelectedFilePath(file.path);
    setEditedContent(file.content || "");
    setEditingFile(false);
  }

  async function updateHostedFile() {
    setManualError("");
    setUpdatingFile(true);
    try {
      await request("/integration/github/pull-request/update", {
        method: "POST",
        body: JSON.stringify({ repository: repositoryName.trim(), pr_number: Number(prNumber), path: selectedFilePath, content: editedContent, message: commitMessage.trim() || "Update file from impact analysis assistant" })
      });
      await loadWorkspace(Number(prNumber));
      setManualError("File committed to the GitHub pull-request branch.");
    } catch (error) {
      setManualError(error.message);
    } finally {
      setUpdatingFile(false);
    }
  }

  async function reviewHostedPR(event) {
    setManualError("");
    setReviewingPR(true);
    try {
      const data = await request("/integration/github/pull-request/review", {
        method: "POST",
        body: JSON.stringify({ repository: repositoryName.trim(), pr_number: Number(prNumber), event, body: event === "APPROVE" ? "Impact analysis reviewed and approved." : "Impact analysis found issues that require changes." })
      });
      setReviewState(data.event === "APPROVE" ? "Approved on GitHub" : "Changes requested on GitHub");
    } catch (error) {
      setManualError(error.message);
    } finally {
      setReviewingPR(false);
    }
  }

  async function mergeHostedPR() {
    setManualError("");
    setMergingPR(true);
    try {
      const data = await request("/integration/github/pull-request/merge", { method: "POST", body: JSON.stringify({ repository: repositoryName.trim(), pr_number: Number(prNumber) }) });
      setReviewState(data.message || "Merged and dependency graph refreshed");
    } catch (error) {
      setManualError(`Merge failed: ${error.message}`);
    } finally {
      setMergingPR(false);
    }
  }

  return <section className="hosted-layout">
    <article className="panel hosted-main">
      <div className="panel-title"><div><small>Hosted repository</small><h2>{provider === "github" ? "GitHub" : "Azure DevOps"} pull requests</h2></div><Badge value={details?.configured ? "Webhook connected" : manualReady ? "Token connected" : "Configuration required"} /></div>
      <div className="provider-toggle"><button className={provider === "github" ? "active" : ""} onClick={() => setProvider("github")}>GitHub</button><button className={provider === "azure_devops" ? "active" : ""} onClick={() => setProvider("azure_devops")}>Azure DevOps</button></div>
      <div className="hosted-repo"><span className="repo-glyph">{provider === "github" ? "GH" : "AZ"}</span><div><strong>{provider === "github" ? "Organization / repository" : "Organization / project / repository"}</strong><p>{manualReady ? "Run analysis directly from your local backend using the GitHub token." : "Configure provider credentials on the backend to begin."}</p></div></div>
      {provider === "github" && <>
        <div className="manual-form">
          <label>Repository<input placeholder="owner/repository" value={repositoryName} onChange={event => setRepositoryName(event.target.value)} /></label>
          <button className="secondary" disabled={!manualReady || !repositoryName.trim() || loadingPullRequests} onClick={loadPullRequests}>{loadingPullRequests ? "Loading..." : "Load open PRs"}</button>
          <label>PR number<select disabled={analysisRunning} value={prNumber} onChange={event => { setPrNumber(event.target.value); if (event.target.value) loadWorkspace(Number(event.target.value)); }}><option value="">Select a PR</option>{pullRequests.map(pr => <option key={pr.number} value={pr.number} title={`PR #${pr.number} | ${pr.title} | ${pr.author || "Unknown author"} | Open`}>#{pr.number} - {pr.title}</option>)}</select></label>
        </div>
        {workspaceLoading && <div className="empty">Loading PR files...</div>}
        {workspace && !workspaceLoading && <div className="hosted-workspace">
          <div className="hosted-pr-meta"><div><small title={`PR #${workspace.pr_number} | ${workspace.title} | ${workspace.author || "Unknown author"} | Open`}>Pull request #{workspace.pr_number}</small><h3>{workspace.title}</h3><p>{workspace.source_branch} → {workspace.target_branch} · opened by {workspace.author}</p></div><div className="review-actions"><button className="refresh-button" disabled={workspaceLoading || analysisRunning} onClick={refreshSelectedPR}>{workspaceLoading ? "Refreshing..." : "Refresh PR"}</button><button className="request-button" disabled={reviewingPR || analysisRunning} onClick={() => reviewHostedPR("REQUEST_CHANGES")}>{reviewingPR ? "Sending..." : "Reject / request changes"}</button><button className={`approve-button ${hostedAnalysis?.severity === "Critical" ? "blocked" : ""}`} disabled={reviewingPR || analysisRunning || hostedAnalysis?.severity === "Critical"} title={hostedAnalysis?.severity === "Critical" ? "Critical severity pull requests require additional review and cannot be approved." : "Approve pull request"} onClick={() => reviewHostedPR("APPROVE")}>{reviewingPR ? "Sending..." : hostedAnalysis?.severity === "Critical" ? "Approval blocked" : "Approve"}</button></div></div>
          <div className="hosted-editor"><nav className="hosted-files" aria-label="Changed files">{workspace.files.map(file => <button key={file.path} className={selectedFilePath === file.path ? "selected" : ""} onClick={() => selectHostedFile(file)}><span>{file.path}</span><small>{file.change_type}</small></button>)}</nav><div className="hosted-file-card"><div className="hosted-file-header"><div><strong>{selectedFilePath}</strong><span>{workspace.files.find(file => file.path === selectedFilePath)?.change_type || "modified"}</span></div><button className="secondary" disabled={workspace.files.find(file => file.path === selectedFilePath)?.change_type === "deleted"} onClick={() => setEditingFile(value => !value)}>{editingFile ? "Close editor" : "Edit file"}</button></div><DiffViewer file={workspace.files.find(file => file.path === selectedFilePath)} />{editingFile && <div className="hosted-edit-area"><label>File content<textarea value={editedContent} onChange={event => setEditedContent(event.target.value)} /></label><label>Commit message<input value={commitMessage} onChange={event => setCommitMessage(event.target.value)} /></label><button className="primary" disabled={updatingFile || !selectedFilePath} onClick={updateHostedFile}>{updatingFile ? "Committing..." : "Commit change to PR"}</button></div>}</div></div>
        </div>}
        {manualError && <div className="error">{manualError}</div>}
        {manualResult && <div className="manual-result"><strong>{analysisRunning ? "Analyzing PR Impact..." : "Analysis completed"}</strong><span>{manualResult.analysis_input?.repository} PR #{manualResult.analysis_input?.pr_number}</span><span>{manualResult.analysis_input?.source_branch} → {manualResult.analysis_input?.target_branch}</span><span>Analysis Runtime: {manualResult.runtime_seconds ?? manualResult.elapsed_seconds ?? "-"} seconds</span><span>{manualResult.comment?.posted ? "Comment posted to GitHub" : "Comment not posted"}</span>{reviewState && <span>{reviewState}</span>}</div>}
      </>}
      <div className="endpoint"><small>{details?.configured ? "Webhook endpoint" : "Manual analysis endpoint"}</small><code>{details?.configured ? details?.webhook_path : details?.manual_analysis_path}</code></div>
      <div className="hosted-note">Credentials stay on the backend. A webhook is optional for local manual analysis.</div>
    </article>
    {/* Event activity will return when webhook event streaming is available. */}
    <article className="panel hosted-checklist"><div className="panel-title"><h3>Integration checklist</h3><span>{manualReady ? "Ready for manual analysis" : "Needs setup"}</span></div>{["Provider token configured", "Webhook signature validation", "Duplicate delivery protection", "Diff and component analysis"].map((item, index) => <div className="check-row" key={item}><span className={index === 0 && !manualReady ? "pending" : "complete"}>{index === 0 && !manualReady ? "!" : "✓"}</span><b>{item}</b><small>{index === 0 && !manualReady ? "Add GITHUB_TOKEN" : index === 1 && !details?.configured ? "Optional for local use" : "Enabled"}</small></div>)}</article>
    {analysisRunning && <div className="analysis-loading" role="status"><span className="spinner" />Analyzing PR Impact...</div>}
    {hostedAnalysis && <section className="hosted-analysis">
      <div className="panel-title"><div><small>Real GitHub pull request</small><h2>Impact analysis</h2></div><Badge value={hostedAnalysis.severity} /></div>
      {hostedAnalysis.severity === "Critical" && <div className="critical-banner" role="alert"><strong>Critical Review Required</strong><span>Approval is blocked until additional review is complete.</span><div><b>Owning Team:</b> {(hostedAnalysis.owning_contacts || []).join(", ") || "Unassigned"}</div><div><b>Team Lead:</b> {(hostedAnalysis.owning_contacts || []).map(owner => `@${String(owner).replaceAll(" ", ".")}`).join(", ") || "Unassigned"}</div></div>}
      <section className="metrics"><article><small>Severity</small><SeverityBadge value={hostedAnalysis.severity} /><p>{hostedAnalysis.severity_reasons?.[0] || "No reason returned"}</p></article><article><small>Total PRs</small><strong>{pullRequests.length || 1}</strong><p>Loaded repository PRs</p></article><article><small>Critical PRs</small><strong>{hostedAnalysis.severity === "Critical" ? 1 : 0}</strong><p>Additional review required</p></article><article><small>Impacted services</small><strong>{hostedServices.length}</strong><p>Downstream blast radius</p></article><article><small>Affected teams</small><strong>{hostedAnalysis.owning_contacts?.length || 0}</strong><p>Owners identified</p></article><article><small>Graph coverage</small><strong>{hostedAnalysis.graph_coverage?.coverage_pct ?? "-"}%</strong><p>Dependency graph</p></article><article><small>Analysis Runtime</small><strong>{manualResult?.runtime_seconds ?? hostedAnalysis.elapsed_seconds ?? "-"}s</strong><p>{analysisHistory.length} execution(s)</p></article><article><small>Average Runtime</small><strong>{analysisHistory.length ? (analysisHistory.reduce((sum, item) => sum + item.runtime_seconds, 0) / analysisHistory.length).toFixed(2) : "-"}s</strong><p>Analysis history</p></article></section>
      {hostedAnalysis.warnings?.length > 0 && <section className="warnings" aria-label="Dependency graph warnings"><div className="panel-title"><h3>Warnings</h3><span>{hostedAnalysis.warnings.length}</span></div>{hostedAnalysis.warnings.map((warning, index) => <div className="warning-row" key={`${warning.code}-${index}`}><Badge value={warning.code} /><span>{warning.detail}</span></div>)}</section>}
      <section className="impact-grid"><article className="panel span2"><div className="panel-title"><h3>Downstream services and owners</h3><span>{hostedServices.length} found</span></div>{hostedServices.length ? <div className="cards">{hostedServices.map(service => <div className={service.criticality === "core_financial" ? "service critical" : "service"} key={service.name}><div><strong>{service.name}</strong><p>Owner: {service.owner}</p></div><Badge value={service.criticality} /></div>)}</div> : <div className="empty">No downstream services found.</div>}</article><article className="panel"><div className="panel-title"><h3>API consumers</h3><span>{hostedConsumers.length}</span></div>{hostedConsumers.length ? hostedConsumers.map(consumer => <div className="row" key={consumer.consumer}><div><b>{consumer.consumer}</b><p>{consumer.provider}</p></div><Badge value={consumer.type} /></div>) : <div className="empty">No API consumers.</div>}</article><article className="panel"><div className="panel-title"><h3>Schema impact</h3><span>{hostedSchemas.length}</span></div>{hostedSchemas.length ? hostedSchemas.map(schema => <div className="schema" key={schema.schema}><b>{schema.schema}</b><p>Readers: {schema.readers?.join(", ") || "None"}</p><p>Writers: {schema.writers?.join(", ") || "None"}</p><p>Pipelines: {schema.pipelines?.join(", ") || "None"}</p></div>) : <div className="empty">No schema impact.</div>}</article><article className="panel span2"><div className="panel-title"><h3>Affected tests</h3><span>{hostedTests.length}</span></div>{hostedTests.length ? <div className="test-cards">{hostedTests.map(test => <div key={test.name}><span>✓</span><b>{test.name}</b><small>{humanize(test.type)}</small></div>)}</div> : <div className="empty">No mapped tests.</div>}</article><article className="panel span3"><div className="panel-title"><h3>Generated PR comment</h3><span>Reviewer-facing output</span></div><pre className="comment">{hostedAnalysis.comment_markdown}</pre></article></section>
    </section>}
  </section>;
}

export default function ImpactDashboard() {
  const [health, setHealth] = useState("checking");
  const [branch, setBranch] = useState(repository.branches[1]);
  const [selectedPath, setSelectedPath] = useState(repository.files[2].path);
  const selected = repository.files.find(f => f.path === selectedPath);
  const preset = changePresets[selectedPath];
  const [title, setTitle] = useState(preset.title);
  const [description, setDescription] = useState(preset.description);
  const [newContent, setNewContent] = useState(preset.content);
  const [breaking, setBreaking] = useState(preset.breaking);
  const [pullRequest, setPullRequest] = useState(null);
  const [result, setResult] = useState(emptyResult);
  const [running, setRunning] = useState(false);
  const [activeStage, setActiveStage] = useState(0);
  const [tab, setTab] = useState("repository");
  const [error, setError] = useState("");
  const [graphVersion, setGraphVersion] = useState("poc-v1");
  const [mode, setMode] = useState("local");
  const [provider, setProvider] = useState("github");
  const [integrationStatus, setIntegrationStatus] = useState(null);

  useEffect(() => { request("/health").then(() => setHealth("online")).catch(() => setHealth("offline")); request("/integration/status").then(setIntegrationStatus).catch(() => setIntegrationStatus(null)); }, []);
  function selectFile(path) { const f = repository.files.find(x => x.path === path); const p = changePresets[path]; setSelectedPath(path); setTitle(p.title); setDescription(p.description); setNewContent(p.content); setBreaking(p.breaking); setPullRequest(null); setResult(emptyResult); setTab("repository"); }
  function createPullRequest() { setError(""); if (!title.trim() || newContent === selected.content) { setError("Enter a PR title and change the selected file before creating the pull request."); return; } setPullRequest({ number: 418, title, description, source: branch, target: repository.defaultBranch, commit: `demo-${Date.now().toString().slice(-6)}`, file: { ...selected, newContent, breaking } }); setTab("pull-request"); }
  async function analyze() { if (!pullRequest) return; setRunning(true); setError(""); setActiveStage(0); const timer = setInterval(() => setActiveStage(v => Math.min(v + 1, stages.length)), 180); try { const f = pullRequest.file; const data = await request("/analyze", { method: "POST", body: JSON.stringify({ event_id: `pr-${pullRequest.number}`, event_type: "pull_request", repository: repository.name, pr_number: pullRequest.number, commit_sha: pullRequest.commit, changed_files: [{ path: f.path, service: f.service || undefined, schema: f.schema || undefined, symbol: f.symbol, patch: `OLD:\n${f.content}\nNEW:\n${f.newContent}`, breaking: f.breaking }] }) }); setResult(data); setActiveStage(stages.length); setTab("impact"); } catch (e) { setError(`Analysis failed: ${e.message}`); setHealth("offline"); } finally { clearInterval(timer); setRunning(false); } }
  async function merge() { if (!pullRequest) return; setRunning(true); try { const data = await request("/webhooks/merge", { method: "POST", body: JSON.stringify({ event_id: `merge-${pullRequest.number}`, event_type: "merge", repository: repository.name, pr_number: pullRequest.number, commit_sha: pullRequest.commit, changed_files: [] }) }); setGraphVersion(data.graph_version || pullRequest.commit); } catch (e) { setError(`Merge simulation failed: ${e.message}`); } finally { setRunning(false); } }

  const services = result.affected_services || [], consumers = result.api_consumers || [], schemas = result.schema_impacts || [], tests = result.affected_tests || [];
  const diff = useMemo(() => ({ old: selected.content, new: newContent }), [selected, newContent]);
  return <div className="shell">
    <header><div className="brand"><span>IA</span><div><h1>AI Impact Analysis Assistant</h1><p>UC-05 · Repository-driven pull-request demonstration</p></div></div><div className="status"><i className={health} />{health === "online" ? "Agent online" : "Agent offline"}<b>Graph {graphVersion}</b></div></header>
    <main>
      <section className="hero"><div><small>{mode === "local" ? "Local demonstration" : "Hosted repository integration"}</small><h2>{mode === "local" ? repository.name : (provider === "github" ? "GitHub pull-request analysis" : "Azure DevOps pull-request analysis")}</h2><p>{mode === "local" ? "Sample service ecosystem with API, model, schema, and documentation files." : "Receive provider webhooks, retrieve the real PR diff, and classify changed components."}</p></div><div className="repo-mark">{mode === "local" ? "REPO" : provider === "github" ? "GH" : "AZ"}</div></section>
      <div className="mode-switch"><button className={mode === "local" ? "active" : ""} onClick={() => setMode("local")}>Local demo</button><button className={mode === "hosted" ? "active" : ""} onClick={() => setMode("hosted")}>Hosted repository</button></div>
      {mode === "hosted" && <HostedIntegration provider={provider} setProvider={setProvider} status={integrationStatus} />}
      {mode === "local" && <nav className="steps"><button className={tab === "repository" ? "active" : ""} onClick={() => setTab("repository")}>1. Edit repository</button><button className={tab === "pull-request" ? "active" : ""} disabled={!pullRequest} onClick={() => setTab("pull-request")}>2. Pull request</button><button className={tab === "impact" ? "active" : ""} disabled={result === emptyResult} onClick={() => setTab("impact")}>3. Impact analysis</button></nav>}
      {error && <div className="error">{error}</div>}

      {mode === "local" && <>
        {tab === "repository" && <section className="workspace">
          <aside className="files"><div className="panel-title"><h3>Repository files</h3><span>{branch}</span></div>{repository.files.map(f => <button key={f.path} className={selectedPath === f.path ? "selected" : ""} onClick={() => selectFile(f.path)}><span>▤</span>{f.path}</button>)}</aside>
          <article className="editor"><div className="panel-title"><h3>Create a change</h3><span>{selected.path}</span></div>
            <label>Feature branch<select value={branch} onChange={e => setBranch(e.target.value)}>{repository.branches.filter(b => b !== "main").map(b => <option key={b}>{b}</option>)}</select></label>
            <div className="diff-grid"><div><label>Current content</label><textarea value={diff.old} readOnly /></div><div><label>Proposed content</label><textarea value={newContent} onChange={e => setNewContent(e.target.value)} /></div></div>
            <div className="form-grid"><label>PR title<input value={title} onChange={e => setTitle(e.target.value)} /></label><label>Change classification<select value={breaking ? "breaking" : "non-breaking"} onChange={e => setBreaking(e.target.value === "breaking")}><option value="non-breaking">Non-breaking</option><option value="breaking">Breaking</option></select></label></div>
            <label>PR description<textarea className="description" value={description} onChange={e => setDescription(e.target.value)} /></label>
            <div className="actions"><button className="primary" onClick={createPullRequest}>Create pull request</button></div>
          </article>
        </section>}

        {tab === "pull-request" && pullRequest && <section className="pr-layout">
          <article className="panel pr-card"><div className="pr-head"><div><small>Pull request #{pullRequest.number}</small><h2>{pullRequest.title}</h2><p>{pullRequest.description}</p></div><Badge value="Open" /></div><div className="branch-line"><span>{pullRequest.source}</span><b>→</b><span>{pullRequest.target}</span></div><div className="change-summary"><div><strong>1</strong><span>Changed file</span></div><div><strong>{pullRequest.file.breaking ? "Yes" : "No"}</strong><span>Breaking change</span></div><div><strong>{pullRequest.commit}</strong><span>Commit</span></div></div><div className="file-change"><h3>{pullRequest.file.path}</h3><div className="mini-diff"><pre className="removed">{pullRequest.file.content}</pre><pre className="added">{pullRequest.file.newContent}</pre></div></div><div className="actions"><button className="secondary" onClick={() => setTab("repository")}>Edit change</button><button className="primary" onClick={analyze} disabled={running || health !== "online"}>{running ? "Analyzing…" : "Run impact analysis"}</button></div></article>
          <aside className="panel"><h3>Agent execution</h3><div className="pipeline">{stages.map((s, i) => <div key={s} className={i < activeStage ? "done" : i === activeStage && running ? "running" : ""}><span>{i < activeStage ? "✓" : i + 1}</span><b>{s}</b></div>)}</div></aside>
        </section>}

        {tab === "impact" && <><>{result.severity === "Critical" && <div className="critical-banner" role="alert"><strong>Critical Review Required</strong><span>Approval is blocked until additional review is complete.</span><div><b>Owning Team:</b> {(result.owning_contacts || []).join(", ") || "Unassigned"}</div><div><b>Team Lead:</b> {(result.owning_contacts || []).map(owner => `@${String(owner).replaceAll(" ", ".")}`).join(", ") || "Unassigned"}</div></div>}</><section className="metrics"><article><small>Severity</small><SeverityBadge value={result.severity} /><p>{result.severity_reasons?.[0] || "No reason returned"}</p></article><article><small>Total PRs</small><strong>1</strong><p>Local pull request</p></article><article><small>Critical PRs</small><strong>{result.severity === "Critical" ? 1 : 0}</strong><p>Additional review required</p></article><article><small>Impacted services</small><strong>{services.length}</strong><p>Downstream blast radius</p></article><article><small>Affected teams</small><strong>{result.owning_contacts?.length || 0}</strong><p>Owners identified</p></article><article><small>Graph coverage</small><strong>{result.graph_coverage?.coverage_pct ?? "-"}%</strong><p>Dependency graph</p></article><article><small>Analysis Runtime</small><strong>{result.elapsed_seconds || "-"}s</strong><p>End-to-end graph execution</p></article><article><small>Affected tests</small><strong>{tests.length}</strong><p>Recommended suites</p></article></section>{result.warnings?.length > 0 && <section className="warnings"><div className="panel-title"><h3>Warnings</h3><span>{result.warnings.length}</span></div>{result.warnings.map((warning, index) => <div className="warning-row" key={`${warning.code}-${index}`}><Badge value={warning.code} /><span>{warning.detail}</span></div>)}</section>}
            <section className="impact-grid"><article className="panel span2"><div className="panel-title"><h3>Downstream services and owners</h3><span>{services.length} found</span></div>{services.length ? <div className="cards">{services.map(s => <div className={s.criticality === "core_financial" ? "service critical" : "service"} key={s.name}><div><strong>{s.name}</strong><p>Owner: {s.owner}</p></div><Badge value={s.criticality} /></div>)}</div> : <div className="empty">No downstream services found.</div>}</article><article className="panel"><div className="panel-title"><h3>API consumers</h3><span>{consumers.length}</span></div>{consumers.length ? consumers.map(c => <div className="row" key={c.consumer}><div><b>{c.consumer}</b><p>{c.provider}</p></div><Badge value={c.type} /></div>) : <div className="empty">No API consumers.</div>}</article><article className="panel"><div className="panel-title"><h3>Schema impact</h3><span>{schemas.length}</span></div>{schemas.length ? schemas.map(s => <div className="schema" key={s.schema}><b>{s.schema}</b><p>Readers: {s.readers?.join(", ") || "None"}</p><p>Writers: {s.writers?.join(", ") || "None"}</p><p>Pipelines: {s.pipelines?.join(", ") || "None"}</p></div>) : <div className="empty">No schema impact.</div>}</article><article className="panel span2"><div className="panel-title"><h3>Affected tests</h3><span>{tests.length}</span></div>{tests.length ? <div className="test-cards">{tests.map(t => <div key={t.name}><span>✓</span><b>{t.name}</b><small>{humanize(t.type)}</small></div>)}</div> : <div className="empty">No mapped tests.</div>}</article><article className="panel span3"><div className="panel-title"><h3>Generated PR comment</h3><span>Reviewer-facing output</span></div><pre className="comment">{result.comment_markdown}</pre><div className="actions"><button className="secondary" onClick={() => setTab("pull-request")}>Back to PR</button><button className="primary" onClick={merge} disabled={running}>Simulate approval and merge</button></div></article></section></>}
      </>}
    </main>
  </div>;
}
