(() => {
  "use strict";

  const tabs = [...document.querySelectorAll("[data-auth-tab]")];
  const forms = [...document.querySelectorAll("[data-auth-form]")];

  const safeNext = () => {
    const value = new URLSearchParams(window.location.search).get("next") || "";
    return value.startsWith("/") && !value.startsWith("//") ? value : "";
  };

  const destination = (user) => safeNext() || (user.role === "admin" ? "/admin" : "/home");

  async function jsonRequest(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { "Accept": "application/json", "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.message || "We could not complete that request.");
    return body;
  }

  function selectTab(name) {
    tabs.forEach((tab) => {
      const selected = tab.dataset.authTab === name;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    forms.forEach((form) => { form.hidden = form.dataset.authForm !== name; });
    document.getElementById("auth-title").textContent = name === "login" ? "Welcome to RIPPLE." : "Create your RIPPLE account.";
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => selectTab(tab.dataset.authTab)));

  forms.forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const status = form.querySelector("[data-auth-status]");
    const submit = form.querySelector("button[type='submit']");
    const values = Object.fromEntries(new FormData(form));
    status.className = "auth-status";
    status.textContent = form.dataset.authForm === "login" ? "Checking your account…" : "Creating your secure account…";
    submit.disabled = true;
    try {
      const data = await jsonRequest(`/api/auth/${form.dataset.authForm}`, { method: "POST", body: JSON.stringify(values) });
      status.className = "auth-status success";
      status.textContent = "Access confirmed. Opening RIPPLE…";
      window.location.assign(destination(data.user));
    } catch (error) {
      status.className = "auth-status error";
      status.textContent = error.message;
      submit.disabled = false;
    }
  }));

  fetch("/api/auth/session", { headers: { "Accept": "application/json" } })
    .then((response) => response.json())
    .then((session) => { if (session.authenticated) window.location.replace(destination(session.user)); })
    .catch(() => {});
})();
