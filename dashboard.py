# ════════════════════════════════════════════════════════════════════
# DASHBOARD — Flask web app for tracking job applications
# ════════════════════════════════════════════════════════════════════
import os
import hashlib
from flask import Flask, jsonify, request, render_template_string
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# Initialise Firebase (only once)
if not firebase_admin._apps:
    cred = credentials.Certificate({
        "type":          "service_account",
        "project_id":    os.environ["FIREBASE_PROJECT_ID"],
        "client_email":  os.environ["FIREBASE_CLIENT_EMAIL"],
        "private_key":   os.environ["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
        "token_uri":     "https://oauth2.googleapis.com/token",
    })
    firebase_admin.initialize_app(cred)

db = firestore.client()
SEEN_COLLECTION = "seen_jobs"

# ── HTML template ─────────────────────────────────────────────────
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Raghav's Job Tracker</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif;
           background: #f5f5f5; color: #1a1a1a; }

    header { background: #1a1a1a; color: #fff; padding: 24px 32px; }
    header h1 { font-size: 22px; font-weight: 700; }
    header p  { color: #888; font-size: 13px; margin-top: 4px; }

    .filters { display: flex; gap: 8px; padding: 16px 32px;
               background: #fff; border-bottom: 1px solid #eee;
               flex-wrap: wrap; }
    .filter-btn { padding: 6px 16px; border-radius: 20px; border: 1px solid #ddd;
                  background: #fff; cursor: pointer; font-size: 13px;
                  color: #555; transition: all .15s; }
    .filter-btn.active { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }

    .stats { display: flex; gap: 12px; padding: 16px 32px; flex-wrap: wrap; }
    .stat  { background: #fff; border: 1px solid #eee; border-radius: 10px;
             padding: 12px 20px; min-width: 100px; }
    .stat-num   { font-size: 24px; font-weight: 700; }
    .stat-label { font-size: 12px; color: #888; margin-top: 2px; }

    .jobs { padding: 16px 32px; display: flex; flex-direction: column; gap: 12px; }

    .job-card { background: #fff; border: 1px solid #eee; border-radius: 12px;
                padding: 20px; }
    .job-card.applied     { border-left: 4px solid #16a34a; }
    .job-card.rejected    { border-left: 4px solid #dc2626; opacity: .7; }
    .job-card.interviewing { border-left: 4px solid #0077b5; }
    .job-card.new         { border-left: 4px solid #888; }

    .job-top { display: flex; justify-content: space-between;
               align-items: flex-start; flex-wrap: wrap; gap: 8px; }
    .job-title   { font-size: 16px; font-weight: 700; }
    .job-meta    { font-size: 13px; color: #666; margin-top: 4px; }
    .job-date    { font-size: 12px; color: #aaa; }

    .status-badge { font-size: 11px; font-weight: 600; padding: 4px 12px;
                    border-radius: 12px; white-space: nowrap; }
    .badge-new          { background: #f3f4f6; color: #555; }
    .badge-applied      { background: #dcfce7; color: #166534; }
    .badge-rejected     { background: #fee2e2; color: #991b1b; }
    .badge-interviewing { background: #dbeafe; color: #1e40af; }

    .actions { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
    .action-btn { padding: 7px 16px; border-radius: 8px; border: 1px solid #ddd;
                  background: #fff; cursor: pointer; font-size: 12px;
                  font-weight: 600; transition: all .15s; }
    .action-btn:hover { opacity: .85; }
    .btn-applied      { background: #dcfce7; color: #166534; border-color: #16a34a; }
    .btn-interviewing { background: #dbeafe; color: #1e40af; border-color: #3b82f6; }
    .btn-rejected     { background: #fee2e2; color: #991b1b; border-color: #dc2626; }
    .btn-reset        { background: #f3f4f6; color: #555; }
    .apply-link { font-size: 12px; color: #534AB7; text-decoration: none;
                  padding: 7px 16px; border: 1px solid #534AB7;
                  border-radius: 8px; font-weight: 600; }
    .apply-link:hover { background: #f0edff; }

    .empty { text-align: center; padding: 60px; color: #aaa; font-size: 15px; }
    .city-tag { font-size: 11px; padding: 2px 8px; border-radius: 8px;
                background: #f0f0f0; color: #555; margin-right: 6px; }
    .source-tag { font-size: 11px; padding: 2px 8px; border-radius: 8px;
                  background: #eef2ff; color: #4338ca; }
  </style>
</head>
<body>

<header>
  <h1>Raghav's Job Tracker</h1>
  <p>Track your applications across Australia</p>
</header>

<div class="stats" id="stats"></div>

<div class="filters">
  <button class="filter-btn active" onclick="filterJobs('all')">All</button>
  <button class="filter-btn" onclick="filterJobs('new')">New</button>
  <button class="filter-btn" onclick="filterJobs('applied')">Applied</button>
  <button class="filter-btn" onclick="filterJobs('interviewing')">Interviewing</button>
  <button class="filter-btn" onclick="filterJobs('rejected')">Rejected</button>
</div>

<div class="jobs" id="jobs-container">
  <div class="empty">Loading jobs...</div>
</div>

<script>
  let allJobs    = [];
  let activeFilter = 'all';

  async function loadJobs() {
    const resp = await fetch('/api/jobs');
    allJobs    = await resp.json();
    renderStats();
    renderJobs();
  }

  function renderStats() {
    const counts = { new: 0, applied: 0, interviewing: 0, rejected: 0 };
    allJobs.forEach(j => { if (counts[j.status] !== undefined) counts[j.status]++; });
    document.getElementById('stats').innerHTML = `
      <div class="stat">
        <div class="stat-num">${allJobs.length}</div>
        <div class="stat-label">Total</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:#555">${counts.new}</div>
        <div class="stat-label">New</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:#16a34a">${counts.applied}</div>
        <div class="stat-label">Applied</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:#1e40af">${counts.interviewing}</div>
        <div class="stat-label">Interviewing</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:#dc2626">${counts.rejected}</div>
        <div class="stat-label">Rejected</div>
      </div>
    `;
  }

  function renderJobs() {
    const filtered = activeFilter === 'all'
      ? allJobs
      : allJobs.filter(j => j.status === activeFilter);

    const container = document.getElementById('jobs-container');
    if (!filtered.length) {
      container.innerHTML = '<div class="empty">No jobs in this category yet.</div>';
      return;
    }

    container.innerHTML = filtered.map(job => `
      <div class="job-card ${job.status}" id="card-${job.id}">
        <div class="job-top">
          <div>
            <div class="job-title">${job.title || 'Analyst Role'}</div>
            <div class="job-meta">
              <span class="city-tag">${job.city || ''}</span>
              <span class="source-tag">${job.source || ''}</span>
              ${job.company || ''} ${job.location ? '· ' + job.location : ''}
            </div>
          </div>
          <div style="text-align:right">
            <span class="status-badge badge-${job.status}">${capitalise(job.status)}</span>
            <div class="job-date">Seen ${job.first_seen || ''}</div>
          </div>
        </div>

        <div class="actions">
          <button class="action-btn btn-applied"
            onclick="updateStatus('${job.id}', 'applied')">Applied</button>
          <button class="action-btn btn-interviewing"
            onclick="updateStatus('${job.id}', 'interviewing')">Interviewing</button>
          <button class="action-btn btn-rejected"
            onclick="updateStatus('${job.id}', 'rejected')">Rejected</button>
          <button class="action-btn btn-reset"
            onclick="updateStatus('${job.id}', 'new')">Reset</button>
          <a class="apply-link" href="${job.url || '#'}" target="_blank">
            View Job
          </a>
        </div>
      </div>
    `).join('');
  }

  async function updateStatus(jobId, status) {
    await fetch(`/api/jobs/${jobId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    const job = allJobs.find(j => j.id === jobId);
    if (job) job.status = status;
    renderStats();
    renderJobs();
  }

  function filterJobs(filter) {
    activeFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderJobs();
  }

  function capitalise(s) {
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
  }

  loadJobs();
</script>
</body>
</html>
"""


# ── API routes ────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/jobs")
def get_jobs():
    """Return all jobs from Firestore as JSON."""
    docs = db.collection(SEEN_COLLECTION).order_by(
        "first_seen", direction=firestore.Query.DESCENDING
    ).stream()

    jobs = []
    for doc in docs:
        data    = doc.to_dict()
        data["id"] = doc.id
        data.setdefault("status", "new")
        jobs.append(data)

    return jsonify(jobs)


@app.route("/api/jobs/<job_id>/status", methods=["POST"])
def update_status(job_id):
    """Update the application status of a job."""
    body   = request.get_json()
    status = body.get("status", "new")

    if status not in ("new", "applied", "interviewing", "rejected"):
        return jsonify({"error": "Invalid status"}), 400

    db.collection(SEEN_COLLECTION).document(job_id).update({
        "status": status
    })
    return jsonify({"ok": True, "status": status})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
