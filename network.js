(function () {
  "use strict";

  var roleNames = {
    resource: "Resource", worker: "Skilled work", funding: "Funding", community: "Community need"
  };
  var tokenStoreKey = "ripple.signal-owner-tokens.v1";
  var selectedRole = "community";
  var latest = { signals: [], opportunities: [], assemblies: [], invitations: [] };
  var inviteContext = null;
  var refreshTimer = null;

  function $(selector) { return document.querySelector(selector); }
  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
    });
  }
  function getStore(key) {
    try {
      var value = JSON.parse(localStorage.getItem(key) || "{}");
      return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch (_) { return {}; }
  }
  function setStore(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* Local-only convenience; API remains authoritative. */ }
  }
  function money(value) {
    return "$" + Math.round(Number(value) || 0).toLocaleString("en-US");
  }
  function singular(role) { return roleNames[role] || role; }
  function notify(message) {
    var toast = $("#toast");
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(notify.timer);
    notify.timer = window.setTimeout(function () { toast.classList.remove("show"); }, 2600);
  }
  async function api(path, options) {
    options = options || {};
    var headers = Object.assign({}, options.headers || {});
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    var response = await fetch(path, Object.assign({}, options, { cache: "no-store", headers: headers }));
    var result;
    try { result = await response.json(); } catch (_) { result = {}; }
    if (!response.ok) {
      var error = new Error(result.message || "The request could not be completed.");
      error.status = response.status;
      error.payload = result;
      throw error;
    }
    return result;
  }

  function setRole(role) {
    selectedRole = roleNames[role] ? role : "community";
    $("#role").value = selectedRole;
    document.querySelectorAll(".role-option").forEach(function (button) {
      var active = button.dataset.role === selectedRole;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    var labels = {
      community: { heading: "What does the community need?", title: "What is needed?", details: "Describe the gap in plain words." },
      resource: { heading: "What useful thing can you offer?", title: "What resource can you provide?", details: "Include condition, timing, or limits that matter." },
      worker: { heading: "What skilled work can you offer?", title: "What work can you do?", details: "Describe the task, experience, and when you are available." },
      funding: { heading: "What can you fund?", title: "What would your offer support?", details: "Explain any limits or conditions on the offer." }
    }[selectedRole];
    $("#signal-title").textContent = labels.heading;
    var titleInput = document.querySelector('[name="title"]');
    titleInput.placeholder = labels.title;
    document.querySelector('[name="details"]').placeholder = labels.details;
    var fields = "";
    if (selectedRole === "resource" || selectedRole === "community") {
      fields = '<div class="metric-fields"><label>' + (selectedRole === "resource" ? "Quantity available" : "Quantity needed") + '<input name="quantity" type="number" min="1" max="100000" step="1" placeholder="e.g. 20" required></label><label>Unit<input name="unit" maxlength="40" placeholder="e.g. laptops, meal kits" required></label></div>';
    } else if (selectedRole === "worker") {
      fields = '<div class="metric-fields"><label>Hours offered<input name="hours" type="number" min="1" max="100000" step="1" placeholder="e.g. 12" required></label><label>Hourly rate (USD)<input name="hourlyRate" type="number" min="1" max="10000" step="1" placeholder="e.g. 30" required></label></div><p class="field-caption">Paid work is part of the plan—not assumed to be free.</p>';
    } else {
      fields = '<label>Funding amount offered (USD)<input name="amount" type="number" min="1" max="100000000" step="1" placeholder="e.g. 1500" required></label><p class="field-caption">This is an offer only. RIPPLE does not collect or transfer it.</p>';
    }
    $("#role-fields").innerHTML = fields;
    $("#form-message").textContent = "";
    $("#form-message").classList.remove("error");
  }

  function signalValue(signal) {
    if (signal.role === "resource" || signal.role === "community") {
      return Number(signal.quantity).toLocaleString("en-US") + " " + signal.unit;
    }
    if (signal.role === "worker") {
      return Number(signal.hours).toLocaleString("en-US") + " hrs · " + money(signal.hourlyRate) + "/hr";
    }
    return money(signal.amount) + " offered";
  }

  function renderCounts(signals) {
    var counts = { community: 0, resource: 0, worker: 0, funding: 0 };
    signals.forEach(function (signal) { counts[signal.role] = (counts[signal.role] || 0) + 1; });
    $("#role-counts").innerHTML = ["community", "resource", "worker", "funding"].map(function (role) {
      return '<span class="count-chip"><b>' + counts[role] + '</b>' + escapeHtml(singular(role)) + '</span>';
    }).join("");
  }

  function renderSignals(signals) {
    var feed = $("#signal-list");
    $("#feed-count").textContent = signals.length + (signals.length === 1 ? " open signal" : " open signals");
    if (!signals.length) {
      feed.innerHTML = '<p class="quiet-empty">Open offers and needs will appear here. Withdrawn and reserved offers are not listed.</p>';
      return;
    }
    var tokens = getStore(tokenStoreKey);
    feed.innerHTML = signals.map(function (signal) {
      var withdraw = tokens[signal.id]
        ? '<button class="withdraw-button" type="button" data-withdraw="' + escapeHtml(signal.id) + '" title="Withdraw your own signal">Withdraw</button>'
        : "";
      return '<article class="signal-card"><div class="signal-card-main"><span class="signal-card-title">' + escapeHtml(signal.title) + '</span><span class="signal-card-meta"><span class="signal-tag">' + escapeHtml(singular(signal.role)) + '</span>' + escapeHtml(signal.source) + ' · ' + escapeHtml(signal.location) + '<br>' + escapeHtml(signal.category) + ' · ' + escapeHtml(signalValue(signal)) + ' · Unverified</span></div>' + withdraw + '</article>';
    }).join("");
    feed.querySelectorAll("[data-withdraw]").forEach(function (button) {
      button.addEventListener("click", function () { withdrawSignal(button.dataset.withdraw); });
    });
  }

  function chainCell(role, signal, opportunity) {
    var label = singular(role);
    if (!signal) {
      return '<div class="chain-cell"><span class="chain-label">' + escapeHtml(label) + '</span><span class="chain-value">Not matched yet</span><span class="chain-sub">This piece is still needed</span></div>';
    }
    var sub = signal.source + " · " + signalValue(signal);
    var extra = "";
    if (role === "resource" && opportunity.supplyGap > 0) {
      extra = '<span class="chain-sub gap">Short ' + Number(opportunity.supplyGap).toLocaleString("en-US") + ' ' + escapeHtml(signal.unit) + '</span>';
    } else if (role === "resource") {
      extra = '<span class="chain-sub good">Enough for stated need</span>';
    }
    if (role === "funding" && opportunity.fundingGap > 0) {
      extra = '<span class="chain-sub gap">' + money(opportunity.fundingGap) + ' funding gap</span>';
    } else if (role === "funding" && opportunity.estimatedLaborCost) {
      extra = '<span class="chain-sub good">Covers quoted labor</span>';
    }
    return '<div class="chain-cell has-signal"><span class="chain-label">' + escapeHtml(label) + '</span><span class="chain-value">' + escapeHtml(signal.title) + '</span><span class="chain-sub">' + escapeHtml(sub) + '</span>' + extra + '</div>';
  }

  function renderOpportunities(opportunities) {
    var container = $("#opportunities");
    if (!opportunities.length) {
      container.innerHTML = latest.assemblies.length
        ? '<div class="empty-state"><span class="empty-symbol">⌁</span><h4>Open offers have moved into confirmation.</h4><p>Check your invitations and the mission status below. New offers will appear here.</p></div>'
        : '<div class="empty-state"><span class="empty-symbol">⌁</span><h4>The first signal starts the chain.</h4><p>Add a real community need or offer. RIPPLE will show what is still missing.</p></div>';
      return;
    }
    var ownerTokens = getStore(tokenStoreKey);
    container.innerHTML = opportunities.map(function (opportunity) {
      var need = opportunity.need;
      var anchoredBy = opportunity.anchorRole || "community";
      var isLead = anchoredBy !== "community";
      var title = isLead ? singular(anchoredBy) + " lead · " + need.title : need.title;
      var status = opportunity.ready ? '<span class="state-pill ready">Ready to confirm</span>' : '<span class="state-pill">' + (isLead ? "Need a community partner" : "Still needs pieces") + '</span>';
      var gaps = [];
      if (opportunity.missing.length) gaps.push("Needs " + opportunity.missing.map(singular).join(", "));
      if (opportunity.supplyGap) gaps.push("Short " + Number(opportunity.supplyGap).toLocaleString("en-US") + " " + ((opportunity.signals.resource && opportunity.signals.resource.unit) || need.unit));
      if (opportunity.fundingGap) gaps.push(money(opportunity.fundingGap) + " labor funding gap");
      var ownedSignal = ["community", "resource", "worker", "funding"].map(function (role) { return opportunity.signals[role]; }).find(function (signal) { return signal && ownerTokens[signal.id]; });
      var canStart = opportunity.ready && ownedSignal;
      var buttonText = canStart ? "Start confirmation →" : opportunity.ready ? "Listing owner starts" : "Close gaps first";
      return '<article class="opportunity"><div class="opportunity-top"><div><h4 class="opportunity-title">' + escapeHtml(title) + '</h4><div class="opportunity-meta">' + escapeHtml(need.source) + ' · ' + escapeHtml(need.location) + ' · ' + escapeHtml(need.category) + '</div></div>' + status + '</div><div class="chain">' + ["community", "resource", "worker", "funding"].map(function (role) { return chainCell(role, opportunity.signals[role], opportunity); }).join("") + '</div>' + (gaps.length ? '<div class="gap-list">' + gaps.map(function (gap) { return '<span class="gap-chip">' + escapeHtml(gap) + '</span>'; }).join("") + '</div>' : '') + '<div class="opportunity-foot"><span>' + (opportunity.ready ? "Ready for four private confirmations" : isLead ? "Lead listed · waiting for a community need" : "Offers remain separate until the gaps close") + '</span><button class="invite-button" type="button" data-assemble="' + escapeHtml(need.id) + '" data-starter="' + (ownedSignal ? escapeHtml(ownedSignal.id) : "") + '" ' + (canStart ? "" : "disabled") + '>' + buttonText + '</button></div></article>';
    }).join("");
    container.querySelectorAll("[data-assemble]").forEach(function (button) {
      button.addEventListener("click", function () { assemble(button.dataset.assemble, button.dataset.starter, button); });
    });
  }

  function renderAssemblies(assemblies) {
    var container = $("#assemblies");
    if (!assemblies.length) {
      container.innerHTML = '<p class="quiet-empty">Nothing is assembled yet. Every participant must confirm separately.</p>';
      return;
    }
    container.innerHTML = assemblies.map(function (assembly) {
      var stateText = assembly.status === "confirmed" ? "All four listings accepted the plan" : assembly.status === "declined" ? "One listing declined · offers reopened" : assembly.status === "expired" ? "Invitation expired · offers reopened" : "Waiting for separate confirmations · expires " + new Date(assembly.expiresAt).toLocaleDateString();
      var stateClass = assembly.status === "confirmed" ? "ready" : "";
      var decisions = assembly.confirmations.map(function (confirmation) {
        var decision = confirmation.decision;
        var text = decision === "accepted" ? "Accepted" : decision === "declined" ? "Declined" : "Waiting";
        return '<span class="decision ' + escapeHtml(decision) + '">' + escapeHtml(singular(confirmation.role)) + '<br>' + text + '</span>';
      }).join("");
      return '<article class="assembly-card"><div class="assembly-card-head"><strong>' + escapeHtml(assembly.mission.title) + '</strong><span class="state-pill ' + stateClass + '">' + escapeHtml(assembly.status) + '</span></div><small>' + escapeHtml(assembly.mission.location) + ' · ' + escapeHtml(stateText) + '</small><div class="decision-row">' + decisions + '</div></article>';
    }).join("");
  }

  function renderInbox(invitations) {
    var container = $("#my-invitations");
    if (!invitations.length) {
      container.innerHTML = '<p class="quiet-empty">Invitations for listings created in this browser will appear here.</p>';
      return;
    }
    container.innerHTML = invitations.map(function (invitation) {
      var pending = invitation.status === "inviting" && invitation.decision === "pending";
      var state = pending ? "Your response is needed" : invitation.decision === "accepted" ? "You accepted" : invitation.decision === "declined" ? "You declined" : invitation.status === "expired" ? "Expired" : "No response needed";
      return '<article class="assembly-card inbox-card"><div class="assembly-card-head"><strong>' + escapeHtml(invitation.title) + '</strong><span class="state-pill ' + (pending ? "ready" : "") + '">' + escapeHtml(singular(invitation.role)) + '</span></div><small>' + escapeHtml(invitation.location) + ' · ' + escapeHtml(state) + '</small>' + (pending ? '<button class="invite-button inbox-action" type="button" data-inbox-assembly="' + escapeHtml(invitation.assemblyId) + '" data-inbox-role="' + escapeHtml(invitation.role) + '" data-inbox-signal="' + escapeHtml(invitation.signalId) + '">Review the plan →</button>' : "") + '</article>';
    }).join("");
    container.querySelectorAll("[data-inbox-assembly]").forEach(function (button) {
      button.addEventListener("click", function () { openInvitation(button.dataset.inboxAssembly, button.dataset.inboxRole, button.dataset.inboxSignal); });
    });
  }

  async function loadOwnerInbox() {
    var ownerTokens = getStore(tokenStoreKey);
    var ids = Object.keys(ownerTokens);
    var results = await Promise.all(ids.map(async function (signalId) {
      try {
        var result = await api("/api/signals/" + encodeURIComponent(signalId) + "/invitations", { headers: { "X-Owner-Token": ownerTokens[signalId] } });
        return (result.invitations || []).map(function (invitation) { return Object.assign({ signalId: signalId }, invitation); });
      } catch (error) {
        console.warn("Could not load an owned listing's invitations", error);
        return [];
      }
    }));
    return results.flat();
  }

  async function refresh() {
    var health = await api("/api/health");
    if (!health.ok) throw new Error("Backend health check failed.");
    var results = await Promise.all([api("/api/signals"), api("/api/opportunities"), api("/api/assemblies"), loadOwnerInbox()]);
    latest.signals = results[0].signals;
    latest.opportunities = results[1].opportunities;
    latest.assemblies = results[2].assemblies;
    latest.invitations = results[3];
    $("#system-status").textContent = "Backend + database running";
    renderCounts(latest.signals);
    renderSignals(latest.signals);
    renderOpportunities(latest.opportunities);
    renderAssemblies(latest.assemblies);
    renderInbox(latest.invitations);
  }

  async function submitSignal(event) {
    event.preventDefault();
    var form = event.currentTarget;
    var message = $("#form-message");
    if (!form.reportValidity()) return;
    var values = new FormData(form);
    var payload = {
      role: selectedRole,
      source: values.get("source").trim(),
      title: values.get("title").trim(),
      category: values.get("category"),
      location: values.get("location").trim(),
      details: values.get("details").trim(),
      quantity: Number(values.get("quantity") || 0),
      unit: String(values.get("unit") || "").trim(),
      hours: Number(values.get("hours") || 0),
      hourlyRate: Number(values.get("hourlyRate") || 0),
      amount: Number(values.get("amount") || 0)
    };
    var button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = "Adding securely…";
    message.textContent = "";
    message.classList.remove("error");
    try {
      var created = await api("/api/signals", { method: "POST", body: JSON.stringify({ signal: payload }) });
      var tokens = getStore(tokenStoreKey);
      tokens[created.signal.id] = created.ownerToken;
      setStore(tokenStoreKey, tokens);
      form.reset();
      setRole(selectedRole);
      message.textContent = "Added. This signal is saved locally and marked unverified.";
      await refresh();
    } catch (error) {
      message.textContent = error.message;
      message.classList.add("error");
    } finally {
      button.disabled = false;
      button.innerHTML = 'Add this piece <span aria-hidden="true">→</span>';
    }
  }

  async function withdrawSignal(id) {
    if (!window.confirm("Withdraw this signal? It will no longer appear in matching.")) return;
    var tokens = getStore(tokenStoreKey);
    try {
      await api("/api/signals/" + encodeURIComponent(id), { method: "DELETE", headers: { "X-Owner-Token": tokens[id] } });
      delete tokens[id];
      setStore(tokenStoreKey, tokens);
      await refresh();
      notify("Signal withdrawn. The record is retained for integrity.");
    } catch (error) { notify(error.message); }
  }

  async function assemble(communitySignalId, starterSignalId, button) {
    button.disabled = true;
    button.textContent = "Starting confirmation…";
    try {
      var ownerToken = getStore(tokenStoreKey)[starterSignalId];
      if (!ownerToken) throw new Error("Only an owner of a selected listing can start confirmation.");
      await api("/api/assemblies", { method: "POST", headers: { "X-Owner-Token": ownerToken }, body: JSON.stringify({ communitySignalId: communitySignalId, starterSignalId: starterSignalId }) });
      await refresh();
      $("#inbox-title").scrollIntoView({ behavior: "smooth", block: "center" });
      notify("Confirmation started. Each listing owner sees only their own invitation.");
    } catch (error) {
      notify(error.message);
      await refresh();
    } finally {
      button.disabled = false;
      button.textContent = "Start confirmation →";
    }
  }

  async function openInvitation(assemblyId, role, signalId) {
    var ownerToken = getStore(tokenStoreKey)[signalId];
    if (!ownerToken) { notify("The listing's owner key is not available in this browser."); return; }
    inviteContext = { id: assemblyId, role: role, signalId: signalId, ownerToken: ownerToken };
    var dialog = $("#invite-dialog");
    var content = $("#invite-content");
    content.innerHTML = '<span class="invite-content-kicker">YOUR RIPPLE INBOX</span><h2>Checking invitation…</h2>';
    dialog.showModal();
    try {
      var invitation = await api("/api/invitations/" + encodeURIComponent(inviteContext.id) + "/" + inviteContext.role, { headers: { "X-Owner-Token": inviteContext.ownerToken } });
      if (invitation.decision !== "pending" || invitation.status !== "inviting") {
        var stateMessage = invitation.status === "expired" ? "The invitation expired. The offers are open again." : invitation.status === "declined" ? "This mission was closed after a participant declined." : "This role’s response has already been recorded.";
        content.innerHTML = '<span class="invite-content-kicker">' + escapeHtml(singular(invitation.role)) + ' · ' + escapeHtml(invitation.status.toUpperCase()) + '</span><h2>No response needed.</h2><p>' + escapeHtml(stateMessage) + '</p>';
        inviteContext = null;
        return;
      }
      var participantLines = Object.keys(invitation.mission.participants).map(function (role) {
        var participant = invitation.mission.participants[role];
        return '<div class="invite-participant"><b>' + escapeHtml(singular(role)) + ' · ' + escapeHtml(participant.source) + '</b><span>' + escapeHtml(participant.title) + ' · ' + escapeHtml(signalValue(participant)) + '</span><small>' + escapeHtml(participant.details) + '</small></div>';
      }).join("");
      content.innerHTML = '<span class="invite-content-kicker">PRIVATE INVITATION · YOUR CHOICE</span><h2>' + escapeHtml(invitation.mission.title) + '</h2><p>You are being asked to take part as the <b>' + escapeHtml(singular(invitation.role)) + '</b>. Review the whole plan before responding.</p><div class="invite-summary">' + escapeHtml(invitation.mission.location) + ' · ' + escapeHtml(invitation.mission.category) + '<div class="invite-participants-list">' + participantLines + '</div><b>Quoted paid labor: ' + money(invitation.mission.estimatedLaborCost) + '</b><br><br>' + escapeHtml(invitation.mission.note) + '</div><p>Offers are unverified; confirm them directly. Your listing owner key controls this response, but it does not verify your real-world identity.</p><div class="invite-actions"><button class="button secondary" type="button" data-decision="declined">Decline</button><button class="button primary" type="button" data-decision="accepted">I agree to this plan</button></div>';
      content.querySelectorAll("[data-decision]").forEach(function (button) {
        button.addEventListener("click", function () { decideInvitation(button.dataset.decision, button); });
      });
    } catch (error) {
      content.innerHTML = '<span class="invite-content-kicker">INVITATION UNAVAILABLE</span><h2>We could not open this invitation.</h2><p>' + escapeHtml(error.message) + '</p>';
      inviteContext = null;
    }
  }

  async function decideInvitation(decision, button) {
    if (!inviteContext) return;
    if (decision === "declined" && !window.confirm("Decline this invitation? No money or goods move in this pilot.")) return;
    button.disabled = true;
    try {
      var result = await api("/api/invitations/" + encodeURIComponent(inviteContext.id) + "/" + inviteContext.role, {
        method: "POST", headers: { "X-Owner-Token": inviteContext.ownerToken }, body: JSON.stringify({ decision: decision })
      });
      $("#invite-content").innerHTML = '<span class="invite-content-kicker">RESPONSE RECORDED</span><h2>' + (decision === "accepted" ? "You agreed to join the plan." : "You declined this invitation.") + '</h2><p>RIPPLE recorded your choice. The group still needs every role to accept before the plan is marked agreed.</p>';
      inviteContext = null;
      refresh().catch(function () {});
    } catch (error) {
      notify(error.message);
      button.disabled = false;
    }
  }

  function start() {
    document.querySelectorAll(".role-option").forEach(function (button) {
      button.addEventListener("click", function () { setRole(button.dataset.role); });
    });
    $("#signal-form").addEventListener("submit", submitSignal);
    $("#invite-dialog").addEventListener("click", function (event) {
      if (event.target === event.currentTarget) event.currentTarget.close();
    });
    setRole("community");
    refresh().catch(function (error) {
      $("#system-status").textContent = "Backend unavailable";
      $("#system-status").parentElement.style.color = "var(--red)";
      $("#opportunities").innerHTML = '<div class="empty-state"><span class="empty-symbol">!</span><h4>RIPPLE server is not running.</h4><p>Start it from the project folder with <code>python3 server.py</code>, then reload this page.</p></div>';
      console.error(error);
    });
    refreshTimer = window.setInterval(function () { refresh().catch(function () {}); }, 12000);
    window.addEventListener("focus", function () { refresh().catch(function () {}); });
    if (window.location.hash.indexOf("#invite/") === 0) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      notify("Old invitation links are disabled. Open the listing owner's inbox here.");
    }
  }

  document.addEventListener("DOMContentLoaded", start);
}());
