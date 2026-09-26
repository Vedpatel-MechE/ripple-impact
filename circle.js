(() => {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  const circleId = params.get("id") || "";
  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const preciseMoney = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  const checkout = document.querySelector("[data-checkout]");
  const form = document.querySelector("[data-circle-contribution]");
  let circle = null;

  const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { "Accept": "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) } });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.message || "The Circle could not be updated.");
    return body;
  }

  function renderFriends() {
    const container = document.querySelector("[data-circle-friends]");
    document.querySelector("[data-friend-count]").textContent = `${circle.contributorCount} joined`;
    container.innerHTML = circle.contributors.length ? circle.contributors.slice().reverse().map((friend) => `
      <article><span>${escapeHtml(friend.displayName.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase() || "AF")}</span><div><strong>${escapeHtml(friend.displayName)}</strong><small>${friend.message ? `“${escapeHtml(friend.message)}”` : "Joined the Circle"}</small></div><b>${money.format(friend.amount)}</b></article>`).join("")
      : '<div class="circle-empty-friends"><span>＋</span><p>Be the first friend to move this Circle forward.</p></div>';
  }

  function render() {
    document.title = `${circle.groupName} | RIPPLE Circle`;
    document.querySelector("[data-circle-status]").textContent = circle.status === "funded" ? "Circle completed" : "Open Circle";
    document.querySelector("[data-circle-location]").textContent = circle.mission.location;
    document.querySelector("[data-circle-headline]").textContent = circle.socialHeadline;
    document.querySelector("[data-circle-statement]").textContent = circle.creatorStatement || `${circle.creatorName} created ${circle.groupName} so friends can complete one transparent technology mission together.`;
    document.querySelector("[data-circle-raised]").textContent = money.format(circle.raised);
    document.querySelector("[data-circle-goal]").textContent = money.format(circle.goal);
    document.querySelector("[data-circle-remaining]").textContent = money.format(circle.remaining);
    document.querySelector("[data-circle-count]").textContent = circle.contributorCount;
    document.querySelector("[data-circle-percent]").textContent = `${Math.round(circle.progressPercent)}%`;
    document.querySelector("[data-circle-progress]").style.width = `${circle.progressPercent}%`;
    document.querySelector("[data-circle-ring]").style.setProperty("--progress", `${circle.progressPercent * 3.6}deg`);
    document.querySelector("[data-package-title]").textContent = circle.package.title;
    document.querySelector("[data-package-devices]").textContent = circle.package.targetDevices;
    document.querySelector("[data-package-explanation]").textContent = circle.package.explanation;
    document.querySelector("[data-package-lines]").innerHTML = circle.package.breakdown.map((line) => `<li><span>${escapeHtml(line.label)}</span><b>${money.format(line.amount)}</b></li>`).join("");
    document.querySelector("[data-package-total]").textContent = money.format(circle.goal);
    document.querySelector("[data-package-assumptions]").textContent = circle.package.assumptions;
    document.querySelector("[data-circle-story]").textContent = circle.groupStory;
    document.querySelector("[data-mission-title]").textContent = circle.mission.title;
    document.querySelector("[data-mission-summary]").textContent = circle.mission.summary;
    document.querySelector("[data-mission-recipient]").textContent = `${circle.mission.recipient.type} · ${circle.mission.recipient.need}`;
    document.querySelector("[data-mission-location]").textContent = circle.mission.location;
    document.querySelector("[data-mission-device]").textContent = `${circle.mission.device.quantity} ${circle.mission.device.type}`;
    document.querySelector("[data-mission-link]").href = `/mission?mission=${encodeURIComponent(circle.mission.id)}`;
    form.elements.amount.max = circle.remaining;
    form.elements.amount.value = Math.min(50, circle.remaining);
    document.querySelector("[data-open-checkout]").disabled = circle.status !== "open";
    document.querySelector("[data-open-checkout]").innerHTML = circle.status === "open" ? 'Join this Circle <span aria-hidden="true">→</span>' : "Circle target completed ✓";
    renderFriends();
    const shareText = `${circle.socialHeadline} Join the Circle:`;
    const encodedUrl = encodeURIComponent(window.location.href);
    document.querySelector("[data-circle-whatsapp]").href = `https://wa.me/?text=${encodeURIComponent(`${shareText} ${window.location.href}`)}`;
    document.querySelector("[data-circle-facebook]").href = `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`;
  }

  function openCheckout() {
    if (!circle || circle.status !== "open") return;
    document.querySelector("[data-checkout-backdrop]").hidden = false;
    checkout.classList.add("open");
    checkout.setAttribute("aria-hidden", "false");
    document.body.classList.add("checkout-open");
    form.hidden = false;
    document.querySelector("[data-checkout-success]").hidden = true;
    document.querySelector("[data-checkout-step='details']").hidden = false;
    document.querySelector("[data-checkout-step='payment']").hidden = true;
    form.elements.amount.focus();
  }

  function closeCheckout() {
    checkout.classList.remove("open");
    checkout.setAttribute("aria-hidden", "true");
    document.querySelector("[data-checkout-backdrop]").hidden = true;
    document.body.classList.remove("checkout-open");
  }

  document.querySelector("[data-open-checkout]").addEventListener("click", openCheckout);
  document.querySelector("[data-close-checkout]").addEventListener("click", closeCheckout);
  document.querySelector("[data-checkout-backdrop]").addEventListener("click", closeCheckout);
  document.querySelector("[data-finish-checkout]").addEventListener("click", closeCheckout);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeCheckout(); });
  document.querySelectorAll("[data-circle-amount]").forEach((button) => button.addEventListener("click", () => {
    const value = button.dataset.circleAmount === "split" ? Math.ceil(circle.remaining / Math.max(1, circle.package.groupSize)) : Number(button.dataset.circleAmount);
    form.elements.amount.value = Math.min(value, circle.remaining);
  }));
  form.elements.anonymous.addEventListener("change", () => {
    form.elements.displayName.disabled = form.elements.anonymous.checked;
    form.elements.displayName.required = !form.elements.anonymous.checked;
    if (form.elements.anonymous.checked) form.elements.displayName.value = "";
  });
  document.querySelector("[data-payment-next]").addEventListener("click", () => {
    const amount = Number(form.elements.amount.value);
    if (!amount || amount < 1 || amount > circle.remaining || (!form.elements.anonymous.checked && !form.elements.displayName.value.trim())) {
      document.querySelector("[data-checkout-status]").textContent = `Enter a name and an amount from $1 to ${preciseMoney.format(circle.remaining)}.`;
      return;
    }
    document.querySelector("[data-checkout-status]").textContent = "";
    document.querySelector("[data-checkout-total]").textContent = preciseMoney.format(amount);
    document.querySelector("[data-checkout-step='details']").hidden = true;
    document.querySelector("[data-checkout-step='payment']").hidden = false;
    form.elements.cardNumber.focus();
  });
  document.querySelector("[data-payment-back]").addEventListener("click", () => {
    document.querySelector("[data-checkout-step='payment']").hidden = true;
    document.querySelector("[data-checkout-step='details']").hidden = false;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const number = form.elements.cardNumber.value.replace(/\s+/g, "");
    const status = document.querySelector("[data-checkout-status]");
    if (!form.reportValidity()) return;
    if (number !== "4111111111111111" || !/^\d{2}\/\d{2}$/.test(form.elements.expiry.value) || !/^\d{3}$/.test(form.elements.cvc.value)) {
      status.className = "checkout-status error";
      status.textContent = "Use the demo Visa number 4111 1111 1111 1111, a demo MM/YY, and a three-digit demo code.";
      return;
    }
    const button = form.querySelector("button[type='submit']");
    button.disabled = true;
    status.className = "checkout-status";
    status.textContent = "Authorizing in the local sandbox…";
    try {
      const data = await request(`/api/smart-carts/${encodeURIComponent(circle.id)}/checkout`, { method: "POST", body: JSON.stringify({
        displayName: form.elements.displayName.value.trim(), amount: Number(form.elements.amount.value),
        anonymous: form.elements.anonymous.checked, message: form.elements.message.value.trim(), sandboxConfirmation: true,
      }) });
      circle = data.circle;
      form.elements.cardNumber.value = ""; form.elements.expiry.value = ""; form.elements.cvc.value = ""; form.elements.billingName.value = "";
      form.hidden = true;
      document.querySelector("[data-checkout-success]").hidden = false;
      document.querySelector("[data-receipt-amount]").textContent = preciseMoney.format(data.contribution.amount);
      document.querySelector("[data-receipt-reference]").textContent = data.contribution.gatewayReference;
      render();
    } catch (error) {
      status.className = "checkout-status error";
      status.textContent = error.message;
    } finally { button.disabled = false; }
  });

  async function shareCircle() {
    const text = circle.socialHeadline;
    if (navigator.share) await navigator.share({ title: circle.groupName, text, url: window.location.href }).catch(() => {});
    else { await navigator.clipboard.writeText(`${text} ${window.location.href}`); document.querySelector("[data-circle-share]").textContent = "Share text copied"; }
  }
  document.querySelector("[data-circle-share]").addEventListener("click", shareCircle);
  document.querySelector("[data-circle-copy]").addEventListener("click", async () => { await navigator.clipboard.writeText(window.location.href); document.querySelector("[data-circle-copy]").textContent = "Copied"; });

  request(`/api/smart-carts/${encodeURIComponent(circleId)}`).then((data) => {
    circle = data.circle;
    render();
    document.querySelector("[data-circle-loading]").hidden = true;
    document.querySelector("[data-circle-content]").hidden = false;
    document.querySelector("[data-circle-root]").setAttribute("aria-busy", "false");
  }).catch((error) => {
    document.querySelector("[data-circle-loading]").hidden = true;
    document.querySelector("[data-circle-error]").hidden = false;
    document.querySelector("[data-circle-error-message]").textContent = error.message;
    document.querySelector("[data-circle-root]").setAttribute("aria-busy", "false");
  });
})();
