(() => {
  "use strict";

  const planForm = document.querySelector("[data-smart-plan]");
  const createForm = document.querySelector("[data-smart-create]");
  const results = document.querySelector("[data-smart-results]");
  const success = document.querySelector("[data-smart-success]");
  let session = null;
  let plan = null;
  let options = [];
  let selectedType = "balanced";

  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: {
      "Accept": "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(session?.csrfToken && options.method && options.method !== "GET" ? { "X-CSRF-Token": session.csrfToken } : {}),
    }});
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.assign(`/?next=${encodeURIComponent(window.location.pathname)}`); throw new Error("Sign in to build a Circle."); }
    if (!response.ok) throw new Error(body.message || "RIPPLE could not complete that request.");
    return body;
  }

  function planPayload() {
    const data = new FormData(planForm);
    return {
      missionId: data.get("missionId"), budget: Number(data.get("budget")), groupSize: Number(data.get("groupSize")),
      priority: data.get("priority"), prompt: String(data.get("prompt") || "").trim(),
    };
  }

  function optionCard(option) {
    return `<article class="smart-option ${option.type === selectedType ? "selected" : ""}" data-option="${escapeHtml(option.type)}">
      <div class="smart-option-top"><span>${escapeHtml(option.tag)}</span><input type="radio" name="smartOption" value="${escapeHtml(option.type)}" ${option.type === selectedType ? "checked" : ""} aria-label="Choose ${escapeHtml(option.title)}"></div>
      <h4>${escapeHtml(option.title)}</h4>
      <div class="smart-option-outcome"><strong>${option.targetDevices}</strong><span>planned<br>devices</span></div>
      <div class="smart-option-price"><b>${money.format(option.goal)}</b><span>about ${money.format(option.perPerson)} per friend</span></div>
      <p>${escapeHtml(option.explanation)}</p>
      <ul>${option.breakdown.map((line) => `<li><span>${escapeHtml(line.label)}</span><b>${money.format(line.amount)}</b></li>`).join("")}</ul>
      <button type="button" data-choose-option="${escapeHtml(option.type)}">${option.type === selectedType ? "Selected" : "Choose this package"}</button>
    </article>`;
  }

  function renderOptions() {
    document.querySelector("[data-smart-options]").innerHTML = options.map(optionCard).join("");
    document.querySelectorAll("[data-choose-option], [data-option]").forEach((element) => element.addEventListener("click", (event) => {
      const type = event.currentTarget.dataset.chooseOption || event.currentTarget.dataset.option;
      if (type) { selectedType = type; renderOptions(); }
    }));
  }

  planForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!planForm.reportValidity()) return;
    const button = planForm.querySelector("button[type='submit']");
    const status = document.querySelector("[data-plan-status]");
    button.disabled = true;
    status.className = "form-status";
    status.textContent = "Building three transparent packages…";
    try {
      plan = planPayload();
      const data = await request("/api/smart-cart/recommendations", { method: "POST", body: JSON.stringify(plan) });
      options = data.options;
      selectedType = "balanced";
      document.querySelector("[data-smart-brief]").textContent = data.brief;
      renderOptions();
      results.hidden = false;
      success.hidden = true;
      status.textContent = "";
      results.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      status.className = "form-status error";
      status.textContent = error.message;
    } finally { button.disabled = false; }
  });

  createForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!plan || !options.length || !createForm.reportValidity()) return;
    const button = createForm.querySelector("button[type='submit']");
    const status = document.querySelector("[data-create-status]");
    button.disabled = true;
    status.className = "form-status";
    status.textContent = "Creating the private-to-share Circle link…";
    try {
      const data = await request("/api/smart-carts", { method: "POST", body: JSON.stringify({
        ...plan, packageType: selectedType, groupName: planForm.elements.groupName.value.trim(),
        creatorStatement: createForm.elements.creatorStatement.value.trim(),
      }) });
      const absolute = new URL(data.shareUrl || data.sharePath, window.location.origin).href;
      document.querySelector("[data-share-link]").value = absolute;
      document.querySelector("[data-open-circle]").href = absolute;
      document.querySelector("[data-success-summary]").textContent = `${data.circle.groupName} can now work together toward ${data.circle.package.targetDevices} planned devices and a ${money.format(data.circle.goal)} sandbox target.`;
      results.hidden = true;
      success.hidden = false;
      success.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (error) {
      status.className = "form-status error";
      status.textContent = error.message;
    } finally { button.disabled = false; }
  });

  document.querySelector("[data-copy-link]").addEventListener("click", async () => {
    const input = document.querySelector("[data-share-link]");
    await navigator.clipboard.writeText(input.value);
    document.querySelector("[data-copy-link]").textContent = "Copied";
  });
  document.querySelector("[data-native-share]").addEventListener("click", async () => {
    const url = document.querySelector("[data-share-link]").value;
    const text = document.querySelector("[data-success-summary]").textContent;
    if (navigator.share) await navigator.share({ title: "Join my RIPPLE Circle", text, url }).catch(() => {});
    else { await navigator.clipboard.writeText(`${text} ${url}`); document.querySelector("[data-native-share]").textContent = "Share text copied"; }
  });

  const missionParam = new URLSearchParams(window.location.search).get("mission");
  if (["south-atlanta-laptop-lab", "clayton-tablet-library", "westside-desktop-classroom"].includes(missionParam)) planForm.elements.missionId.value = missionParam;
  request("/api/auth/session").then((data) => { session = data; if (!data.authenticated) window.location.replace("/?next=/smart-cart"); });
})();
