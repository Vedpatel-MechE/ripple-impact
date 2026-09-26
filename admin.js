(() => {
  "use strict";

  const state = { session: null, inquiries: [], activeId: null };
  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const labels = {
    company: "Company", recipient: "School / charity", repairer: "Repair partner",
    submitted: "Submitted", reviewing: "Reviewing", "needs-information": "Needs information",
    approved: "Approved", declined: "Declined",
  };
  const ignoredFields = new Set(["organizationName", "contactName", "email", "location", "notes"]);

  async function request(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Accept": "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(state.session?.csrfToken && options.method && options.method !== "GET" ? { "X-CSRF-Token": state.session.csrfToken } : {}),
        ...(options.headers || {}),
      },
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.replace("/?next=/admin"); throw new Error("Session expired"); }
    if (!response.ok) throw new Error(body.message || "The request could not be completed.");
    return body;
  }

  function formatDate(value, detailed = false) {
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return "Unknown";
    return new Intl.DateTimeFormat("en-US", detailed
      ? { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }
      : { month: "short", day: "numeric", year: "numeric" }).format(date);
  }

  function currentFilters() {
    return {
      search: $("[data-admin-search]").value.trim().toLowerCase(),
      kind: $("[data-admin-kind]").value,
      status: $("[data-admin-status-filter]").value,
    };
  }

  function visibleInquiries() {
    const filters = currentFilters();
    return state.inquiries.filter((item) => {
      const haystack = `${item.organizationName} ${item.contactName} ${item.email} ${item.location} ${item.summary}`.toLowerCase();
      return (!filters.search || haystack.includes(filters.search))
        && (filters.kind === "all" || item.kind === filters.kind)
        && (filters.status === "all" || item.status === filters.status);
    });
  }

  function renderTable() {
    const items = visibleInquiries();
    $("[data-admin-result]").textContent = `${items.length} of ${state.inquiries.length} inquir${items.length === 1 ? "y" : "ies"}`;
    $("[data-inquiry-list]").innerHTML = items.length ? items.map((item) => `
      <tr>
        <td><strong>${escapeHtml(item.organizationName)}</strong><small>${escapeHtml(item.location)}</small></td>
        <td><span class="kind-mark kind-${escapeHtml(item.kind)}">${escapeHtml(labels[item.kind])}</span></td>
        <td><span>${escapeHtml(item.summary)}</span><small>${escapeHtml(item.contactName)} · ${escapeHtml(item.email)}</small></td>
        <td><span class="workflow-status status-${escapeHtml(item.status)}"><i></i>${escapeHtml(labels[item.status])}</span></td>
        <td><span>${escapeHtml(formatDate(item.createdAt))}</span></td>
        <td><button type="button" class="open-review" data-open-review="${escapeHtml(item.id)}" aria-label="Review ${escapeHtml(item.organizationName)}">→</button></td>
      </tr>`).join("") : '<tr><td colspan="6" class="admin-empty">No inquiries match these filters.</td></tr>';
    document.querySelectorAll("[data-open-review]").forEach((button) => button.addEventListener("click", () => openReview(button.dataset.openReview)));
  }

  function renderDashboard(data) {
    state.inquiries = data.inquiries;
    const counts = {
      total: data.counts.total,
      submitted: data.counts.byStatus.submitted || 0,
      reviewing: data.counts.byStatus.reviewing || 0,
      participants: data.counts.participants,
    };
    Object.entries(counts).forEach(([key, value]) => { $(`[data-admin-count="${key}"]`).textContent = value; });
    renderTable();
  }

  function humanize(key) {
    return key.replace(/([A-Z])/g, " $1").replace(/^./, (letter) => letter.toUpperCase());
  }

  function displayValue(value) {
    if (Array.isArray(value)) return value.map((item) => labels[item] || humanize(item)).join(", ");
    return String(value ?? "—").replaceAll("-", " ");
  }

  function openReview(id) {
    const item = state.inquiries.find((inquiry) => inquiry.id === id);
    if (!item) return;
    state.activeId = id;
    $("[data-review-kind]").textContent = `${labels[item.kind]} inquiry · ${item.id.slice(0, 8)}`;
    $("[data-review-title]").textContent = item.organizationName;
    $("[data-review-summary]").innerHTML = `
      <div><span>Primary contact</span><strong>${escapeHtml(item.contactName)}</strong><small>${escapeHtml(item.email)}</small></div>
      <div><span>Submitted by</span><strong>${escapeHtml(item.submittedBy.displayName)}</strong><small>${escapeHtml(item.submittedBy.email)}</small></div>
      <div><span>Received</span><strong>${escapeHtml(formatDate(item.createdAt, true))}</strong><small>${escapeHtml(item.location)}</small></div>`;
    $("[data-review-details]").innerHTML = Object.entries(item.payload)
      .filter(([key]) => !ignoredFields.has(key))
      .map(([key, value]) => `<div><dt>${escapeHtml(humanize(key))}</dt><dd>${escapeHtml(displayValue(value))}</dd></div>`).join("")
      + `<div><dt>Submitter notes</dt><dd>${escapeHtml(item.payload.notes || "None provided")}</dd></div>`;
    $("[data-review-events]").innerHTML = item.events.slice().reverse().map((event) => {
      const eventLabel = event.event === "submitted_unverified" ? "Submitted as unverified" : humanize(event.event.replace("status:", "Status: "));
      return `<li><i></i><div><strong>${escapeHtml(eventLabel)}</strong><small>${escapeHtml(formatDate(event.createdAt, true))}</small></div></li>`;
    }).join("");
    $("[data-admin-status]").value = item.status;
    $("[data-admin-notes]").value = item.reviewNotes || "";
    $("[data-review-status]").textContent = "";
    $("[data-review-panel]").classList.add("open");
    $("[data-review-panel]").setAttribute("aria-hidden", "false");
    $("[data-review-backdrop]").hidden = false;
    document.body.classList.add("review-open");
    $("[data-review-close]").focus();
  }

  function closeReview() {
    $("[data-review-panel]").classList.remove("open");
    $("[data-review-panel]").setAttribute("aria-hidden", "true");
    $("[data-review-backdrop]").hidden = true;
    document.body.classList.remove("review-open");
    state.activeId = null;
  }

  async function loadDashboard() {
    const data = await request("/api/admin/dashboard");
    renderDashboard(data);
  }

  $("[data-review-form]").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.activeId) return;
    const button = event.currentTarget.querySelector("button[type='submit']");
    const status = $("[data-review-status]");
    button.disabled = true;
    status.className = "review-form-status";
    status.textContent = "Saving review…";
    try {
      await request(`/api/admin/intakes/${encodeURIComponent(state.activeId)}`, {
        method: "PATCH",
        body: JSON.stringify({ status: $("[data-admin-status]").value, reviewNotes: $("[data-admin-notes]").value }),
      });
      status.className = "review-form-status success";
      status.textContent = "Review saved to the audit trail.";
      await loadDashboard();
      window.setTimeout(closeReview, 650);
    } catch (error) {
      status.className = "review-form-status error";
      status.textContent = error.message;
    } finally { button.disabled = false; }
  });

  ["[data-admin-search]", "[data-admin-kind]", "[data-admin-status-filter]"].forEach((selector) => {
    $(selector).addEventListener(selector.includes("search") ? "input" : "change", renderTable);
  });
  $("[data-review-close]").addEventListener("click", closeReview);
  $("[data-review-backdrop]").addEventListener("click", closeReview);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && state.activeId) closeReview(); });
  $("[data-admin-logout]").addEventListener("click", async () => {
    await request("/api/auth/logout", { method: "POST", body: "{}" });
    window.location.assign("/");
  });

  request("/api/auth/session").then((session) => {
    if (!session.authenticated || session.user.role !== "admin") { window.location.replace("/home"); return; }
    state.session = session;
    $("[data-admin-name]").textContent = session.user.displayName;
    $("[data-admin-email]").textContent = session.user.email;
    $("[data-admin-avatar]").textContent = session.user.displayName.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
    return loadDashboard();
  }).catch((error) => {
    $("[data-inquiry-list]").innerHTML = `<tr><td colspan="6" class="admin-empty">${escapeHtml(error.message)}</td></tr>`;
  });
})();
