(() => {
  "use strict";

  const API = {
    missions: "/api/impact-missions",
    intakes: "/api/intakes",
    pledges: "/api/pledges",
  };

  const numberFormatter = new Intl.NumberFormat("en-US");
  const moneyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  async function request(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Accept": "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
    let body;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (!response.ok) {
      const message = body?.message || body?.error?.message || body?.error || `Request failed (${response.status})`;
      throw new Error(typeof message === "string" ? message : "The request could not be completed.");
    }
    return body;
  }

  function showToast(message, isError = false) {
    const toast = document.querySelector("[data-toast]");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("visible");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 5200);
  }

  function setupNavigation() {
    const controls = [
      ...document.querySelectorAll("[data-menu-button]"),
      ...document.querySelectorAll("[data-nav-toggle]"),
    ];
    controls.forEach((button) => {
      const controlledId = button.getAttribute("aria-controls");
      const target = controlledId
        ? document.getElementById(controlledId)
        : document.querySelector("[data-nav-menu], [data-nav], .nav-links, .primary-nav");
      if (!target) return;
      button.addEventListener("click", () => {
        const open = button.getAttribute("aria-expanded") !== "true";
        button.setAttribute("aria-expanded", String(open));
        target.classList.toggle("open", open);
        document.body.classList.toggle("menu-open", open);
      });
      target.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
        button.setAttribute("aria-expanded", "false");
        target.classList.remove("open");
        document.body.classList.remove("menu-open");
      }));
    });
  }

  function missionCard(mission) {
    const quantity = numberFormatter.format(mission.device.quantity);
    const goal = moneyFormatter.format(mission.funding.goal);
    const pledged = moneyFormatter.format(mission.funding.simulatedPledged || 0);
    const remaining = moneyFormatter.format(mission.funding.remaining ?? mission.funding.goal);
    const progress = Math.max(0, Math.min(100, Number(mission.funding.progressPercent || 0)));
    const type = escapeHtml(mission.device.type.replaceAll("-", " "));
    return `
      <article class="mission-card" data-mission-card data-status="funding" data-category="${type}">
        <div class="mission-card-top">
          <span class="status-tag">Sample mission</span>
          <span class="mission-tag">${escapeHtml(mission.location)}</span>
        </div>
        <h3>${escapeHtml(mission.title)}</h3>
        <p class="mission-card-summary">${escapeHtml(mission.summary)}</p>
        <div class="mission-stat-row">
          <div><span>Planned devices</span><b>${quantity} ${type}</b></div>
          <div><span>Activation goal</span><b>${goal}</b></div>
        </div>
        <div class="progress-block">
          <div class="progress-label"><span>${pledged} simulated</span><span>${remaining} remaining</span></div>
          <div class="progress-bar" role="progressbar" aria-label="Simulated pledge progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><i style="width:${progress}%"></i></div>
        </div>
        <a class="mission-card-link" href="/mission?mission=${encodeURIComponent(mission.id)}"><span>Inspect mission</span><span aria-hidden="true">↗</span></a>
      </article>`;
  }

  async function loadLandingMissions() {
    const grids = [...document.querySelectorAll("[data-mission-grid]")]
      .filter((grid) => !grid.querySelector("[data-mission-card]"));
    if (!grids.length) return;
    try {
      const data = await request(API.missions);
      grids.forEach((grid) => {
        const limit = Number.parseInt(grid.dataset.limit || String(data.missions.length), 10);
        grid.innerHTML = data.missions.slice(0, limit).map(missionCard).join("");
      });
    } catch (error) {
      grids.forEach((grid) => {
        grid.innerHTML = `<div class="error-card">Missions could not be loaded. ${escapeHtml(error.message)}</div>`;
      });
    }
  }

  function setupMissionFilters() {
    const container = document.querySelector("[data-mission-filters]");
    if (!container) return;
    const buttons = [...container.querySelectorAll("[data-filter]")];
    const category = container.querySelector("[data-category-filter]") || document.querySelector("[data-category-filter]");
    const cards = [...document.querySelectorAll("[data-mission-card]")];
    const result = document.querySelector("[data-filter-result]");
    const empty = document.querySelector("[data-empty-filter]");
    let status = "all";

    const apply = () => {
      const device = category?.value || "all";
      let visible = 0;
      cards.forEach((card) => {
        const showStatus = status === "all" || card.dataset.status === status;
        const showCategory = device === "all" || card.dataset.category === device;
        const show = showStatus && showCategory;
        card.hidden = !show;
        if (show) visible += 1;
      });
      if (result) result.textContent = `Showing ${visible} illustrative mission${visible === 1 ? "" : "s"}`;
      if (empty) empty.hidden = visible !== 0;
    };

    buttons.forEach((button) => button.addEventListener("click", () => {
      status = button.dataset.filter || "all";
      buttons.forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      apply();
    }));
    category?.addEventListener("change", apply);
  }

  function browserMissionCard(mission) {
    const progress = Math.max(0, Math.min(100, Number(mission.funding.progressPercent || 0)));
    return `
      <article class="browser-mission" data-browser-mission="${escapeHtml(mission.id)}">
        <div class="browser-mission__top"><span>Sample · ${escapeHtml(mission.location)}</span><b>${numberFormatter.format(mission.device.quantity)} ${escapeHtml(mission.device.type)}</b></div>
        <h3>${escapeHtml(mission.title)}</h3>
        <p>${escapeHtml(mission.recipient.type)} · ${escapeHtml(mission.recipient.need)}</p>
        <div class="progress-copy"><strong>${moneyFormatter.format(mission.funding.simulatedPledged || 0)} simulated</strong><span>${moneyFormatter.format(mission.funding.goal)} goal</span></div>
        <div class="progress-bar" role="progressbar" aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100"><i style="width:${progress}%"></i></div>
        <button class="mission-select-button" type="button" data-select-mission="${escapeHtml(mission.id)}">Choose this mission <span aria-hidden="true">→</span></button>
      </article>`;
  }

  async function loadMissionBrowser() {
    const browser = document.querySelector("[data-mission-browser]");
    if (!browser) return;
    try {
      const data = await request(API.missions);
      browser.innerHTML = data.missions.map(browserMissionCard).join("");
      browser.setAttribute("aria-busy", "false");
      browser.querySelectorAll("[data-select-mission]").forEach((button) => {
        button.addEventListener("click", () => {
          const select = document.querySelector("[data-mission-select]");
          if (select) {
            select.value = button.dataset.selectMission;
            document.getElementById("pledge")?.scrollIntoView({ behavior: "smooth", block: "start" });
            window.setTimeout(() => select.focus(), 450);
          }
        });
      });
    } catch (error) {
      browser.setAttribute("aria-busy", "false");
      browser.innerHTML = `<div class="error-card">Mission budgets are temporarily unavailable. ${escapeHtml(error.message)}</div>`;
    }
  }

  function formPayload(form) {
    const payload = {};
    const multi = new Set(["specialties", "services"]);
    for (const [name, value] of new FormData(form).entries()) {
      if (multi.has(name)) {
        if (!payload[name]) payload[name] = [];
        payload[name].push(value);
      } else {
        const field = form.elements.namedItem(name);
        payload[name] = field?.type === "number" ? Number(value) : value;
      }
    }
    for (const name of multi) {
      if (form.querySelector(`[name="${name}"]`) && !payload[name]) payload[name] = [];
    }
    return payload;
  }

  function setupIntakeForms() {
    document.querySelectorAll("form[data-intake]").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const status = form.querySelector("[data-form-status]");
        const requiredGroups = [...form.querySelectorAll("[data-required-group]")];
        let groupError = false;
        requiredGroups.forEach((group) => {
          const checked = group.querySelector("input[type='checkbox']:checked");
          group.classList.toggle("has-error", !checked);
          if (!checked) groupError = true;
        });
        if (!form.reportValidity() || groupError) {
          if (status) {
            status.className = "form-status error";
            status.textContent = groupError ? "Select at least one option in each capability group." : "Complete the required fields above.";
          }
          return;
        }
        const submit = form.querySelector("button[type='submit']");
        if (submit) submit.disabled = true;
        if (status) {
          status.className = "form-status";
          status.textContent = "Saving your pilot inquiry…";
        }
        try {
          const data = await request(API.intakes, {
            method: "POST",
            body: JSON.stringify({ kind: form.dataset.kind, payload: formPayload(form) }),
          });
          form.reset();
          requiredGroups.forEach((group) => group.classList.remove("has-error"));
          if (status) {
            status.className = "form-status success";
            status.textContent = `Inquiry ${data.intake.id.slice(0, 8)} saved locally as unverified. No partnership or transfer has been created.`;
          }
          showToast("Pilot inquiry saved. It is still unverified and private.");
        } catch (error) {
          if (status) {
            status.className = "form-status error";
            status.textContent = error.message;
          }
          showToast(error.message, true);
        } finally {
          if (submit) submit.disabled = false;
        }
      });
    });
  }

  function setupFundPledge() {
    const form = document.querySelector("form[data-pledge]");
    if (!form) return;
    const amount = form.elements.namedItem("amount");
    const name = form.elements.namedItem("displayName");
    const anonymous = form.elements.namedItem("anonymous");
    const status = form.querySelector("[data-form-status]");

    form.querySelectorAll("[data-pledge-amount]").forEach((button) => button.addEventListener("click", () => {
      amount.value = button.dataset.pledgeAmount;
      amount.focus();
    }));
    anonymous?.addEventListener("change", () => {
      name.required = !anonymous.checked;
      name.disabled = anonymous.checked;
      name.placeholder = anonymous.checked ? "Hidden for this simulated pledge" : "How your name would appear";
      if (anonymous.checked) name.value = "";
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const submit = form.querySelector("button[type='submit']");
      if (submit) submit.disabled = true;
      if (status) {
        status.className = "form-status";
        status.textContent = "Recording simulation…";
      }
      try {
        const data = await request(API.pledges, {
          method: "POST",
          body: JSON.stringify({
            missionId: form.elements.namedItem("missionId").value,
            amount: Number(amount.value),
            displayName: name.value.trim(),
            anonymous: Boolean(anonymous.checked),
          }),
        });
        if (status) {
          status.className = "form-status success";
          status.textContent = `${moneyFormatter.format(data.pledge.amount)} demo pledge recorded. No payment was processed.`;
        }
        showToast("Simulation recorded—no card charged, no money moved.");
        await loadMissionBrowser();
      } catch (error) {
        if (status) {
          status.className = "form-status error";
          status.textContent = error.message;
        }
        showToast(error.message, true);
      } finally {
        if (submit) submit.disabled = false;
      }
    });
  }

  function setupMissionPreview() {
    const form = document.querySelector("form[data-pledge-form]");
    if (!form) return;
    const amount = form.querySelector("[data-pledge-amount]");
    const result = form.querySelector("[data-pledge-result]");
    form.querySelectorAll("[data-pledge-preset]").forEach((button) => button.addEventListener("click", () => {
      amount.value = button.dataset.pledgePreset;
      form.querySelectorAll("[data-pledge-preset]").forEach((item) => item.classList.toggle("selected", item === button));
    }));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const dollars = Math.max(1, Number(amount.value || 0));
      const devices = Math.max(1, Math.floor(dollars / 120));
      result.className = "form-result success";
      result.textContent = `${moneyFormatter.format(dollars)} could cover about ${devices} average device activation${devices === 1 ? "" : "s"} in this example. Preview only—nothing was charged or recorded.`;
    });
  }

  setupNavigation();
  setupMissionFilters();
  setupIntakeForms();
  setupFundPledge();
  setupMissionPreview();
  loadLandingMissions();
  loadMissionBrowser();
})();
