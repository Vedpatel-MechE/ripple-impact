(function () {
  "use strict";

  var engine = window.RippleEngine;
  var STORAGE_KEY = "ripple-mission-v1";
  var DRAFTS_KEY = "ripple-mission-v1-drafts";
  var RECOVERY_KEY = "ripple-mission-v1-recovery";
  var SERVER_CURRENT_KEY = "ripple-local-server-current-v1";
  var EDIT_TOKENS_KEY = "ripple-local-server-edit-tokens-v1";
  var names = {
    asset: "Resource",
    skills: "Skilled work",
    funding: "Funding",
    anchor: "Community partner"
  };
  var symbols = { asset: "▣", skills: "✦", funding: "$", anchor: "◎" };
  var roleHints = {
    asset: "List the useful thing you have. It can be equipment, food, space, or a group of people ready to participate.",
    skills: "Set a real scope for paid work: what skill, how many hours, and at what hourly rate.",
    funding: "Add an activation budget. RIPPLE shows which parts of the mission it can cover.",
    anchor: "A local school, nonprofit, library, or clinic states the need and later confirms what reached people."
  };
  var roleTitles = {
    asset: "List what you have",
    skills: "Define paid work",
    funding: "Offer activation money",
    anchor: "Describe the community need"
  };
  var roleActions = {
    asset: "Add resource to mission",
    skills: "Add work scope to mission",
    funding: "Add funding to mission",
    anchor: "Add community partner"
  };
  var templateCopy = {
    devices: {
      mission: "Second life for retired laptops",
      subtitle: "Bring company equipment, paid repair work, and a local school together.",
      assetName: "retired laptops",
      skillLabel: "Device repair technician",
      anchorName: "Neighborhood school",
      needText: "Students need reliable computers at home.",
      location: "Atlanta, GA",
      assetRole: "Assets",
      assetRoleSub: "Company surplus",
      assetQuestion: "What equipment is available?",
      timingQuestion: "Pickup deadline (days)",
      qualityShort: "passes screening",
      qualityHelp: "This is your estimate. Each device still needs inspection and a data-wipe plan.",
      outcome: "Working devices in the hands of people who need them",
      unit: "devices",
      defaultDays: 30,
      proof: ["Record device inventory and ownership", "Agree to a data-wipe and repair scope", "Confirm the school's need", "Document delivery", "Check device use after delivery"],
      work: ["Inspect and securely wipe each device", "Repair eligible units", "Record serial numbers and handoff"]
    },
    food: {
      mission: "Turn food surplus into reliable meals",
      subtitle: "Connect safe surplus food, paid logistics, and a local food partner.",
      assetName: "surplus meal portions each week",
      skillLabel: "Food rescue coordinator",
      anchorName: "Community pantry",
      needText: "Neighbors need dependable weekly meals.",
      location: "Atlanta, GA",
      assetRole: "Food supply",
      assetRoleSub: "Weekly surplus",
      assetQuestion: "What food is available each week?",
      timingQuestion: "Pickup window (days)",
      qualityShort: "passes safety screening",
      qualityHelp: "Only food that passes local safety rules can be used.",
      outcome: "Safe meals reaching people every week",
      unit: "meals / week",
      defaultDays: 7,
      proof: ["Record the surplus source and screening process", "Agree to paid pickup and handling", "Confirm pantry demand and capacity", "Log safe delivery", "Check recurring weekly service"],
      work: ["Check eligible food and pickup timing", "Coordinate safe transport and handoff", "Record delivered meals with the partner"]
    },
    tutoring: {
      mission: "Make paid tutoring reach students",
      subtitle: "Connect students, trained tutors, a local school, and a sustainable budget.",
      assetName: "students signed up",
      skillLabel: "Tutor or learning lead",
      anchorName: "Neighborhood school",
      needText: "Students want weekly academic support.",
      location: "Atlanta, GA",
      assetRole: "Student group",
      assetRoleSub: "Ready to enroll",
      assetQuestion: "Who is signed up for tutoring?",
      timingQuestion: "Pilot length (days)",
      qualityShort: "expected to attend",
      qualityHelp: "This is an attendance assumption. The pilot should measure actual turnout.",
      outcome: "Students receiving consistent learning support",
      unit: "students / week",
      defaultDays: 30,
      proof: ["Record student sign-ups and consent", "Agree to tutor hours and safeguarding", "Confirm school schedule and space", "Log sessions delivered", "Measure attendance and learning separately"],
      work: ["Plan the weekly tutoring sessions", "Deliver paid teaching or coordination hours", "Share attendance records with the school"]
    },
    custom: {
      mission: "A new community mission",
      subtitle: "Connect whatever you have with the people, funds, and partner needed to make it useful.",
      assetName: "useful resources",
      skillLabel: "Local skilled operator",
      anchorName: "Community organization",
      needText: "Describe who needs help and what would change.",
      location: "Your community",
      assetRole: "Resources",
      assetRoleSub: "Anything useful",
      assetQuestion: "What do you have?",
      timingQuestion: "Available for how many days?",
      qualityShort: "estimated usable",
      qualityHelp: "This is your starting estimate. Confirm it with the community partner.",
      outcome: "An outcome defined with the community",
      unit: "resources",
      defaultDays: 30,
      proof: ["Document the resource and its owner", "Agree to a paid work scope", "Confirm the community need", "Log delivery or service", "Measure the outcome with the partner"],
      work: ["Agree on the exact task and deliverables", "Complete the paid work", "Document handoff to the community partner"]
    }
  };
  var priorityWeights = {
    balance: { access: 50, work: 25, durability: 25 },
    access: { access: 75, work: 10, durability: 15 },
    work: { access: 20, work: 65, durability: 15 },
    durability: { access: 20, work: 15, durability: 65 }
  };

  function $(selector) { return document.querySelector(selector); }
  function all(selector) { return Array.prototype.slice.call(document.querySelectorAll(selector)); }
  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
    });
  }
  function amount(value) { return "$" + Math.round(Number(value) || 0).toLocaleString("en-US"); }
  function number(value) { return Math.round(Number(value) || 0).toLocaleString("en-US"); }
  function roundOne(value) { return (Math.round((Number(value) || 0) * 10) / 10).toLocaleString("en-US"); }
  function template() { return templateCopy[state.template]; }
  function metadata() { return engine && engine.templates[state.template]; }

  function blankState(templateId, includeSampleAsset) {
    var id = templateCopy[templateId] ? templateId : "devices";
    var copy = templateCopy[id];
    var base = engine && engine.templates[id] ? engine.templates[id].defaults : {
      quantity: 40, budget: 5000, skilledHours: 32, hourlyRate: 30, needCount: 40, quality: 75
    };
    return {
      template: id,
      role: "asset",
      priority: "balance",
      routeId: null,
      missionName: copy.mission,
      assetName: copy.assetName,
      quantity: base.quantity,
      quality: base.quality,
      pickupDays: copy.defaultDays,
      fundingLabel: "Activation fund",
      budget: base.budget,
      skillLabel: copy.skillLabel,
      skilledHours: base.skilledHours,
      hourlyRate: base.hourlyRate,
      anchorName: copy.anchorName,
      needCount: base.needCount,
      needText: copy.needText,
      location: copy.location,
      parts: { asset: !!includeSampleAsset, skills: false, funding: false, anchor: false },
      proof: { delivered: false, followup: false },
      edited: false,
      fullExample: false
    };
  }

  function loadState() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
      var normalized = normalizeState(saved);
      if (normalized) return normalized;
    } catch (error) { /* File-based browsers can disable storage. */ }
    return blankState("devices", true);
  }

  function normalizeState(saved) {
    if (!saved || typeof saved !== "object" || Array.isArray(saved) || !Object.prototype.hasOwnProperty.call(templateCopy, saved.template)) return null;
    var clean = blankState(saved.template, false);
    var textFields = ["missionName", "assetName", "fundingLabel", "skillLabel", "anchorName", "needText", "location"];
    textFields.forEach(function (key) {
      var limit = key === "needText" ? 240 : 90;
      if (typeof saved[key] === "string" && saved[key].trim()) clean[key] = saved[key].trim().slice(0, limit);
    });
    var numbers = {
      quantity: [1, 100000], quality: [0, 100], pickupDays: [1, 365], budget: [1, 100000000],
      skilledHours: [1, 100000], hourlyRate: [1, 10000], needCount: [1, 100000]
    };
    Object.keys(numbers).forEach(function (key) {
      var value = Number(saved[key]);
      var wholeNumber = key === "quantity" || key === "pickupDays" || key === "needCount" || key === "quality";
      if (saved[key] !== "" && saved[key] != null && Number.isFinite(value) && value >= numbers[key][0] && value <= numbers[key][1] && (!wholeNumber || Number.isInteger(value))) clean[key] = value;
    });
    if (Object.prototype.hasOwnProperty.call(names, saved.role)) clean.role = saved.role;
    if (Object.prototype.hasOwnProperty.call(priorityWeights, saved.priority)) clean.priority = saved.priority;
    if (typeof saved.routeId === "string" && saved.routeId.length <= 80) clean.routeId = saved.routeId;
    ["asset", "skills", "funding", "anchor"].forEach(function (key) { clean.parts[key] = !!(saved.parts && saved.parts[key] === true); });
    ["delivered", "followup"].forEach(function (key) { clean.proof[key] = !!(saved.proof && saved.proof[key] === true); });
    clean.edited = saved.edited === true;
    clean.fullExample = saved.fullExample === true;
    return clean;
  }

  function loadStoredObject(key) {
    try {
      var value = JSON.parse(localStorage.getItem(key));
      return value && typeof value === "object" ? value : null;
    } catch (error) { return null; }
  }

  var state = loadState();
  var drafts = loadStoredObject(DRAFTS_KEY) || {};
  var recovery = normalizeState(loadStoredObject(RECOVERY_KEY));
  var editTokens = loadStoredObject(EDIT_TOKENS_KEY) || {};
  var serverCurrent = loadStoredObject(SERVER_CURRENT_KEY);
  if (!serverCurrent || typeof serverCurrent.id !== "string" || typeof serverCurrent.viewToken !== "string" || !Number.isInteger(serverCurrent.version)) serverCurrent = null;
  var serverBusy = false;
  var serverAvailable = null;
  var model = null;
  var toastTimer;

  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function rememberRecovery() {
    recovery = clone(state);
    try { localStorage.setItem(RECOVERY_KEY, JSON.stringify(recovery)); } catch (error) { /* Session undo still works. */ }
    $("#undo-mission").hidden = false;
  }

  function persistServerCurrent() {
    try {
      if (serverCurrent) localStorage.setItem(SERVER_CURRENT_KEY, JSON.stringify(serverCurrent));
      else localStorage.removeItem(SERVER_CURRENT_KEY);
    } catch (error) { /* The current tab remains usable without local storage. */ }
  }

  function clearServerIdentity(removeLink) {
    serverCurrent = null;
    persistServerCurrent();
    if (removeLink && /^https?:$/.test(location.protocol)) {
      var address = new URL(location.href);
      if (address.searchParams.has("mission") || address.searchParams.has("view")) {
        address.searchParams.delete("mission");
        address.searchParams.delete("view");
        history.replaceState(null, "", address);
      }
    }
    renderServerStatus();
  }

  function renderServerStatus() {
    var status = $("#server-save-status");
    if (!status) return;
    if (!serverCurrent) {
      status.textContent = "This mission is only in this browser. Nothing has been sent to a server.";
    } else if (serverCurrent.dirty) {
      status.textContent = "Version " + serverCurrent.version + " was saved on this local server. Your latest changes are still browser-only.";
    } else {
      status.textContent = "Version " + serverCurrent.version + " is saved on this local server. This is not public sharing.";
    }
  }

  function save(keepServerSync) {
    if (serverCurrent && !keepServerSync) serverCurrent.dirty = true;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      drafts[state.template] = clone(state);
      localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts));
      $("#save-status").textContent = "Changes saved in this browser";
    } catch (error) {
      $("#save-status").textContent = "Changes kept until this page closes";
    }
    $("#undo-mission").hidden = !recovery;
    persistServerCurrent();
    renderServerStatus();
  }

  function showToast(message) {
    var toast = $("#toast");
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("show"); }, 3400);
  }

  function scrollTo(selector) {
    var target = $(selector);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function selectRole(role, moveToForm) {
    if (!names[role]) return;
    state.role = role;
    renderRole();
    renderForm();
    save();
    if (moveToForm) scrollTo("#contribution");
  }

  function changeTemplate(id) {
    if (!templateCopy[id] || id === state.template) return;
    rememberRecovery();
    clearServerIdentity(true);
    state = drafts[id] && drafts[id].template === id ? clone(drafts[id]) : blankState(id, id !== "custom");
    state = normalizeState(state) || blankState(id, id !== "custom");
    if (id === "custom" && !drafts[id]) state.edited = true;
    save();
    renderAll();
    showToast(id === "custom" ? "Custom mission board ready. Start with any resource." : "Your " + id + " mission is ready.");
  }

  function setCompleteExample() {
    rememberRecovery();
    clearServerIdentity(true);
    state = blankState("devices", true);
    state.parts = { asset: true, skills: true, funding: true, anchor: true };
    state.fullExample = true;
    save();
    renderAll();
    showToast("Complete example loaded. Change any card to test it.");
    scrollTo("#studio");
  }

  function newMission() {
    rememberRecovery();
    clearServerIdentity(true);
    state = blankState(state.template, false);
    state.edited = true;
    save();
    renderAll();
    showToast("Blank mission ready. Choose what you bring first.");
    scrollTo("#studio");
  }

  function restorePrevious() {
    if (!recovery || !templateCopy[recovery.template]) return;
    var current = clone(state);
    state = normalizeState(recovery) || blankState("devices", false);
    recovery = current;
    try { localStorage.setItem(RECOVERY_KEY, JSON.stringify(recovery)); } catch (error) { /* Session undo still works. */ }
    clearServerIdentity(true);
    save();
    renderAll();
    showToast("Previous draft restored.");
  }

  function renderTemplatePicker() {
    all(".template-card").forEach(function (button) {
      var selected = button.dataset.template === state.template;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
  }

  function renderRole() {
    all(".role-card").forEach(function (button) {
      var selected = button.dataset.role === state.role;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    var assetRole = $('.role-card[data-role="asset"]');
    assetRole.querySelector("strong").textContent = template().assetRole;
    assetRole.querySelector("small").textContent = template().assetRoleSub;
    $("#role-hint").textContent = roleHints[state.role];
  }

  function field(name, label, type, extra) {
    extra = extra || {};
    var value = state[name] == null ? "" : state[name];
    var id = "field-" + name;
    var attrs = ' id="' + id + '" name="' + name + '"';
    if (extra.min != null) attrs += ' min="' + extra.min + '"';
    if (extra.max != null) attrs += ' max="' + extra.max + '"';
    if (extra.step != null) attrs += ' step="' + extra.step + '"';
    if (extra.required) attrs += " required";
    var control;
    if (type === "textarea") {
      control = "<textarea" + attrs + ' rows="3" maxlength="240">' + escapeHtml(value) + "</textarea>";
    } else if (type === "range") {
      control = '<div class="range-wrap"><input type="range"' + attrs + ' value="' + escapeHtml(value) + '"><output for="' + id + '">' + number(value) + "%</output></div>";
    } else {
      control = '<input type="' + type + '"' + attrs + ' value="' + escapeHtml(value) + '"' + (type === "text" ? ' maxlength="90"' : "") + ">";
    }
    return '<div class="field"><label for="' + id + '">' + escapeHtml(label) + "</label>" + control +
      (extra.help ? '<p class="field-help">' + escapeHtml(extra.help) + "</p>" : "") + "</div>";
  }

  function renderForm() {
    var meta = metadata();
    var role = state.role;
    var fields = "";
    $("#contribution-title").textContent = roleTitles[role];
    $("#contribution-status").textContent = state.parts[role] ? "Added to mission · editable" : "Ready to add";
    $("#contribution-submit").innerHTML = escapeHtml(roleActions[role]) + ' <span aria-hidden="true">→</span>';

    if (role === "asset") {
      if (state.template === "custom") fields += field("missionName", "Name this mission", "text", { required: true });
      fields += field("assetName", template().assetQuestion, "text", { required: true });
      fields += '<div class="field-row">' +
        field("quantity", meta ? meta.quantityLabel : "How many are available?", "number", { min: 1, max: 100000, required: true }) +
        field("pickupDays", template().timingQuestion, "number", { min: 1, max: 365, required: true }) + "</div>";
      fields += field("quality", meta ? meta.qualityLabel : "Estimated usable share (%)", "range", { min: 0, max: 100, step: 1, help: template().qualityHelp });
    } else if (role === "skills") {
      fields += field("skillLabel", "What skill can do the work?", "text", { required: true });
      fields += '<div class="field-row">' +
        field("skilledHours", meta ? meta.skilledHoursLabel : "Available paid hours", "number", { min: 1, max: 100000, required: true }) +
        field("hourlyRate", meta ? meta.hourlyRateLabel : "Hourly rate ($)", "number", { min: 1, max: 10000, required: true }) + "</div>";
      fields += '<p class="form-context">This creates a proposed work scope. No one is hired or paid through this prototype.</p>';
    } else if (role === "funding") {
      fields += field("fundingLabel", "Who is offering it?", "text", { required: true });
      fields += field("budget", meta ? meta.budgetLabel : "Available budget ($)", "number", { min: 1, max: 100000000, required: true });
      fields += '<p class="form-context">This records a draft funding offer. It does not transfer money.</p>';
    } else {
      fields += field("anchorName", "Who knows the need locally?", "text", { required: true });
      fields += '<div class="field-row">' +
        field("needCount", meta ? meta.needCountLabel : "How many people need help?", "number", { min: 1, max: 100000, required: true }) +
        field("location", "Where is the community?", "text", { required: true }) + "</div>";
      fields += field("needText", "What change is needed?", "textarea", { required: true });
    }
    $("#contribution-fields").innerHTML = fields;
  }

  function missionInput() {
    return {
      quantity: state.parts.asset ? state.quantity : 0,
      budget: state.parts.funding ? state.budget : 0,
      skilledHours: state.parts.skills ? state.skilledHours : 0,
      hourlyRate: state.hourlyRate,
      // Without a community partner this is still sample demand.
      needCount: state.needCount,
      quality: state.quality
    };
  }

  function updateModel() {
    model = null;
    if (state.template === "custom" || !engine || !state.parts.asset) return;
    try { model = engine.simulate(state.template, missionInput(), priorityWeights[state.priority]); }
    catch (error) { console.error("RIPPLE model could not run:", error); }
    if (model && model.routes.length && !model.routes.some(function (route) { return route.id === state.routeId; })) {
      state.routeId = model.routes[0].id;
    }
  }

  function selectedRoute() {
    return model && model.routes.find(function (route) { return route.id === state.routeId; });
  }

  function renderMission() {
    var count = Object.keys(state.parts).filter(function (key) { return state.parts[key]; }).length;
    var copy = template();
    $("#mission-domain").textContent = (state.template === "custom" ? "CUSTOM" : state.template.toUpperCase()) + " MISSION";
    $("#mission-title").textContent = state.missionName || copy.mission;
    $("#mission-subtitle").textContent = copy.subtitle;
    $("#mission-count").textContent = count + " / 4";
    $("#progress-fill").style.width = count * 25 + "%";
    $("#mission-location").textContent = state.parts.anchor ? state.location + " · Partner entered" : state.location + " · Example location";
    $("#mission-data-tag").textContent = state.template === "custom" ? "User entered draft" : state.edited ? "User entered + demo estimates" : "Illustrative inputs";
    $("#sample-status").textContent = state.edited ? "Your local draft mission" : "Illustrative sample mission";
  }

  function pieceDescription(role) {
    if (!state.parts[role]) {
      return {
        asset: "Add the resource that starts the mission.",
        skills: "Define the paid work and hours.",
        funding: "Add money for labor and logistics.",
        anchor: "Confirm who needs help locally."
      }[role];
    }
    if (role === "asset") return number(state.quantity) + " " + state.assetName + " · " + number(state.quality) + "% " + template().qualityShort;
    if (role === "skills") return state.skillLabel + " · " + roundOne(state.skilledHours) + " h at " + amount(state.hourlyRate) + "/h";
    if (role === "funding") return amount(state.budget) + " · " + state.fundingLabel;
    return state.anchorName + " · " + number(state.needCount) + " stated need";
  }

  function renderAssembly() {
    all("[data-hero-role]").forEach(function (button) {
      button.classList.toggle("connected", !!state.parts[button.dataset.heroRole]);
    });
    var nodes = ["asset", "skills", "funding", "anchor"].map(function (role) {
      var present = state.parts[role];
      return '<button type="button" class="graph-node ' + (present ? "present" : "missing-node") + '" data-focus-role="' + role + '">' +
        '<span class="graph-sigil" aria-hidden="true">' + symbols[role] + "</span>" +
        '<span class="graph-copy"><span class="graph-role">' + names[role] + "</span><strong>" +
        escapeHtml(present ? (role === "asset" ? state.assetName : role === "skills" ? state.skillLabel : role === "funding" ? state.fundingLabel : state.anchorName) : "Add " + names[role].toLowerCase()) +
        '</strong><small>' + escapeHtml(pieceDescription(role)) + '</small></span><span class="graph-status">' + (present ? "Added" : "Missing") + "</span></button>";
    }).join("");
    $("#assembly-graph").innerHTML = '<div class="graph-nodes">' + nodes + '</div><div class="graph-connector" aria-hidden="true"><span></span><span></span><span></span><span></span></div>';
    var count = Object.keys(state.parts).filter(function (key) { return state.parts[key]; }).length;
    $("#assembly-outcome").innerHTML = '<span class="outcome-orbit" aria-hidden="true">✳</span><div><span class="graph-role">COMMUNITY OUTCOME</span><strong>' +
      escapeHtml(template().outcome) + '</strong><small>' + (count === 4 ? "All four draft pieces are present. Now test the plan and verify the claims." : "Connect the missing pieces to make this mission ready to validate.") +
      '</small></div><span class="outcome-count">' + count + "/4 linked</span>";
    $("#assembly-outcome").classList.toggle("complete", count === 4);
  }

  function missingPieces() {
    var gaps = [];
    var route = selectedRoute();
    if (!state.parts.asset) gaps.push({ role: "asset", title: "A resource to start with", detail: "List the thing, time, or group that could be put to work." });
    if (!state.parts.anchor) gaps.push({ role: "anchor", title: "A local partner to define the need", detail: "The community partner should say who needs help and confirm delivery." });
    if (!state.parts.skills) gaps.push({ role: "skills", title: "A skilled person with a paid scope", detail: "Agree to the work, available hours, and a fair proposed rate." });
    if (!state.parts.funding) gaps.push({ role: "funding", title: "Activation money", detail: "Cover labor, materials, transport, or program coordination." });
    if (state.parts.funding && route && route.budgetGap > 0) {
      gaps.push({ role: "funding", title: amount(route.budgetGap) + " more for the full route", detail: "Illustrative cost to serve all eligible supply, assuming enough skilled hours. This is not a funding request or verified quote." });
    }
    if (state.parts.skills && route && metadata()) {
      var routeMeta = metadata().routes.find(function (item) { return item.id === route.id; });
      if (routeMeta) {
        var potential = Math.min(state.needCount, state.quantity * state.quality / 100 * routeMeta.yield);
        var neededHours = Math.ceil(potential * routeMeta.hoursPerUnit);
        var shortfall = Math.max(0, neededHours - state.skilledHours);
        if (shortfall > 2) gaps.push({
          role: "skills",
          title: "About " + number(shortfall) + " more skilled hours could help",
          detail: "The selected route can run now, but available work hours limit how much eligible supply it can serve."
        });
      }
    }
    return gaps;
  }

  function renderMissing() {
    var gaps = missingPieces();
    $("#gap-count").textContent = gaps.length ? gaps.length + (gaps.length === 1 ? " open gap" : " open gaps") : "Draft pieces ready";
    $("#missing-list").innerHTML = gaps.length ? gaps.map(function (gap) {
      return '<button type="button" class="gap-item" data-focus-role="' + gap.role + '"><span class="gap-symbol">+</span><span><strong>' +
        escapeHtml(gap.title) + '</strong><small>' + escapeHtml(gap.detail) + '</small></span><span class="gap-arrow">↗</span></button>';
    }).join("") : '<div class="all-connected"><span>✳</span><strong>The draft chain is assembled.</strong><p>The next job is checking availability, consent, costs, and partner evidence in the real world.</p></div>';
    var next = gaps[0];
    if (next) {
      $("#next-action-copy").textContent = next.title + ".";
      $("#next-action-button").innerHTML = "Add " + escapeHtml(names[next.role]) + ' <span aria-hidden="true">→</span>';
      $("#next-action-button").dataset.focusRole = next.role;
      $("#next-action-button").dataset.scrollTo = "";
    } else {
      $("#next-action-copy").textContent = "Turn this draft into a checkable plan.";
      $("#next-action-button").innerHTML = 'Review proof trail <span aria-hidden="true">→</span>';
      $("#next-action-button").dataset.focusRole = "";
      $("#next-action-button").dataset.scrollTo = "#proof";
    }
  }

  function recommendRoute() {
    if (!model || !model.routes.length) return null;
    return model.routes.slice().sort(function (a, b) { return b.score - a.score; })[0];
  }

  function minimumStartCost(routeId) {
    var meta = metadata();
    var route = meta && meta.routes.find(function (item) { return item.id === routeId; });
    if (!route) return 0;
    var periodFactor = state.template === "devices" ? 1 : 4.33;
    return Math.ceil(route.fixedCost + periodFactor * (route.hoursPerUnit * state.hourlyRate + route.materialsPerUnit));
  }

  function chartMarkup(route, meta) {
    var values = route.series || [0, 0, 0, 0, 0];
    var highest = Math.max(1, Math.max.apply(null, values) * 1.12);
    var coordinates = values.map(function (value, index) {
      return [42 + index * 125, 145 - (value / highest) * 122];
    });
    var points = coordinates.map(function (point) { return point[0].toFixed(1) + "," + point[1].toFixed(1); }).join(" ");
    var circles = coordinates.map(function (point) {
      return '<circle cx="' + point[0] + '" cy="' + point[1] + '" r="4" fill="' + route.color + '"/>';
    }).join("");
    var labels = ["Now", "6 mo", "12 mo", "18 mo", "24 mo"].map(function (label, index) {
      return '<text x="' + (42 + index * 125) + '" y="183" text-anchor="middle">' + label + "</text>";
    }).join("");
    return '<div class="chart-title"><strong>' + escapeHtml(meta.seriesLabel) + '</strong><span>Median of simulated trials</span></div>' +
      '<svg class="result-chart" viewBox="0 0 590 195" role="img" aria-label="' + escapeHtml(meta.seriesLabel) + ' at five modeled checkpoints">' +
      '<line x1="42" y1="145" x2="542" y2="145" class="chart-axis"/><line x1="42" y1="83" x2="542" y2="83" class="chart-grid"/>' +
      '<polyline points="' + points + '" fill="none" stroke="' + route.color + '" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>' +
      circles + labels + '<text x="8" y="25">' + number(highest) + '</text><text x="15" y="149">0</text></svg>' +
      '<p class="chart-caption">' + escapeHtml(meta.horizonNote) + "</p>";
  }

  function renderPlans() {
    var meta = metadata();
    var priorityRow = $(".priority-row");
    priorityRow.classList.toggle("hidden", state.template === "custom" || !model);
    all(".priority").forEach(function (button) {
      var chosen = button.dataset.priority === state.priority;
      button.classList.toggle("active", chosen);
      button.setAttribute("aria-pressed", String(chosen));
    });
    if (state.template === "custom") {
      $("#plans-title").textContent = "Define what success would mean.";
      $("#plans .surface-intro").textContent = "This mission has no domain model yet. Assemble the people and resources, then define a result a local partner can check.";
      $("#model-badge").textContent = "Planning board only";
      $("#route-cards").innerHTML = '<div class="model-empty"><span>✳</span><h4>Your idea can start here.</h4><p>RIPPLE can assemble any mission. A numerical comparison needs a model built for that specific kind of work, with real local evidence. Your resource map, missing pieces, work scope, and brief still work now.</p></div>';
      $("#plan-detail").innerHTML = "";
      return;
    }
    if (!model) {
      $("#plans-title").textContent = "What could this mission do?";
      $("#plans .surface-intro").textContent = "Add the first resource to unlock example plans for this mission type.";
      $("#model-badge").textContent = "Add a resource first";
      $("#route-cards").innerHTML = '<div class="model-empty"><span>◇</span><h4>Add the first resource to see possible plans.</h4><p>Click Assets or the missing resource card above. The plans will recalculate when you add the other pieces.</p></div>';
      $("#plan-detail").innerHTML = "";
      return;
    }
    $("#plans-title").textContent = "Which plan should we try?";
    $("#plans .surface-intro").textContent = "These are example estimates. Change the mission and the plans recalculate.";
    $("#model-badge").textContent = "1,000 example runs per plan";
    var best = recommendRoute();
    var blocked = model.routes.every(function (route) { return route.output.mid === 0; });
    var missingInputs = [];
    if (!state.parts.skills) missingInputs.push("a skilled operator");
    if (!state.parts.funding) missingInputs.push("an activation budget");
    var blockedHint = missingInputs.length ? "Add " + missingInputs.join(" and ") + " above to unlock a plan." : "Review the usable share, available hours, budget, and community need above.";
    var blocker = blocked ? '<div class="model-warning"><span>!</span><p><strong>Nothing can move yet.</strong> ' + escapeHtml(blockedHint) + '</p></div>' : "";
    var demandNotice = !state.parts.anchor ? '<div class="model-warning"><span>?</span><p><strong>Demand is a sample assumption.</strong> Add a community partner to enter a real stated need. These runs are examples, not predictions or a recommendation.</p></div>' : "";
    $("#route-cards").innerHTML = blocker + demandNotice + model.routes.map(function (route) {
      var selected = route.id === state.routeId;
      var costCaption = route.output.mid === 0 ? amount(minimumStartCost(route.id)) + " min. to start" : amount(route.cost) + " modeled spend";
      var allPiecesEntered = ["asset", "skills", "funding", "anchor"].every(function (role) { return state.parts[role]; });
      var marker = allPiecesEntered && route.output.mid > 0 && best && best.id === route.id ? "TOP DRAFT SCORE" : "ROUTE PREVIEW";
      return '<button class="route-card ' + (selected ? "selected" : "") + '" type="button" data-route="' + escapeHtml(route.id) + '" aria-pressed="' + selected + '" style="--route-color:' + route.color + '">' +
        '<span class="route-top"><span class="route-marker">' + marker + '</span><span class="route-check">' + (selected ? "✓" : "↗") + "</span></span>" +
        "<strong>" + escapeHtml(route.name) + "</strong><small>" + escapeHtml(route.description) + "</small>" +
        '<span class="route-stat"><b>' + number(route.output.mid) + "</b><span>" + escapeHtml(model.unit) + "</span></span>" +
        '<span class="route-footer"><span>' + costCaption + "</span><span>" + roundOne(route.paidHours.mid) + " paid h</span></span></button>";
    }).join("");
    var chosenRoute = selectedRoute() || model.routes[0];
    var laborPerPeriod = Math.round(chosenRoute.paidHours.mid * state.hourlyRate * (state.template === "devices" ? 1 : 4.33));
    var workTitle = state.parts.skills ? state.skillLabel : "Proposed " + template().skillLabel.toLowerCase();
    var risks = chosenRoute.risks.slice(0, 3).map(function (risk) { return "<li>" + escapeHtml(risk) + "</li>"; }).join("");
    var assumptions = chosenRoute.assumptions.map(function (assumption) { return "<li>" + escapeHtml(assumption) + "</li>"; }).join("");
    var metricLabel = state.template === "devices" ? "for this batch" : "each week";
    var costPeriod = state.template === "devices" ? "one-time" : "per month";
    $("#plan-detail").innerHTML =
      '<div class="detail-heading"><div><span class="step-kicker">SELECTED PLAN · ILLUSTRATIVE MODEL</span><h4>' + escapeHtml(chosenRoute.name) + '</h4><p>' + escapeHtml(chosenRoute.description) + '</p></div><span class="estimate-tag">Example estimate</span></div>' +
      '<div class="detail-metrics"><div><span>PEOPLE OR UNITS REACHED</span><strong>' + number(chosenRoute.output.mid) + '</strong><small>' + escapeHtml(meta.outputLabel) + '</small><em>' + number(chosenRoute.output.low) + '–' + number(chosenRoute.output.high) + ' in 80% of runs</em></div><div><span>STILL ACTIVE AT 24 MONTHS</span><strong>' + number(chosenRoute.durable.mid) + '</strong><small>' + escapeHtml(meta.durableLabel) + '</small><em>' + number(chosenRoute.durable.low) + '–' + number(chosenRoute.durable.high) + ' in 80% of runs</em></div><div><span>PAID WORK SCOPED</span><strong>' + roundOne(chosenRoute.paidHours.mid) + ' h</strong><small>' + escapeHtml(meta.paidHoursLabel) + '</small><em>' + roundOne(chosenRoute.paidHours.low) + '–' + roundOne(chosenRoute.paidHours.high) + ' h in 80% of runs</em></div></div>' +
      '<div class="detail-lower"><div class="chart-panel">' + chartMarkup(chosenRoute, meta) + '</div><div class="plan-sidebar">' +
      '<div class="cost-card"><span>THE MONEY PIECE</span><strong>' + amount(chosenRoute.cost) + ' <small>' + costPeriod + '</small></strong><p>Modeled spend at the current budget and work capacity. A typed budget is not reserved money.</p><div class="cost-line"><span>Budget entered</span><b>' + amount(state.parts.funding ? state.budget : 0) + '</b></div><div class="cost-line"><span>Approx. minimum to start</span><b>' + amount(minimumStartCost(chosenRoute.id)) + '</b></div><div class="cost-line"><span>Full-route budget gap*</span><b>' + amount(chosenRoute.budgetGap) + '</b></div><div class="cost-line"><span>Paid work at stated rate</span><b>about ' + amount(laborPerPeriod) + ' ' + costPeriod + '</b></div><small class="cost-footnote">*Serving eligible supply assumes enough skilled hours and stated nearby demand.</small></div>' +
      '<div class="work-card"><span>THE SKILLED PERSON</span><strong>' + escapeHtml(workTitle) + '</strong><p>' + roundOne(chosenRoute.paidHours.mid) + ' paid hours ' + metricLabel + ' at ' + amount(state.hourlyRate) + '/hour in the draft model.</p><ul>' + template().work.map(function (step) { return "<li>" + escapeHtml(step) + "</li>"; }).join("") + '</ul></div></div></div>' +
      '<div class="model-explain"><div><strong>What could break this?</strong><ul>' + risks + '</ul></div><div class="trial-note">' + chosenRoute.successRate + '% of example runs met the draft month-24 target. The target and model assumptions are listed below.</div><details><summary>Show every model assumption</summary><ul>' + assumptions + '</ul><p>The simulation uses illustrative coefficients for a hackathon demo. These need local evidence before a real decision.</p></details></div>';
  }

  function renderProof() {
    var stages = [
      { text: template().proof[0], status: state.parts.asset ? "Resource entered; ownership not verified" : "Need resource", kind: state.parts.asset ? "draft" : "open" },
      { text: template().proof[1], status: state.parts.skills ? "Work scope entered; worker not confirmed" : "Need skilled operator", kind: state.parts.skills ? "draft" : "open" },
      { text: template().proof[2], status: state.parts.anchor ? "Need entered; partner not verified" : "Need community partner", kind: state.parts.anchor ? "draft" : "open" },
      { text: "Document the funding source and confirm availability", status: state.parts.funding ? (selectedRoute() && selectedRoute().budgetGap > 0 ? "Budget entered; modeled gap remains" : "Budget entered; funds not verified") : "Need funding", kind: state.parts.funding ? "draft" : "open" },
      { text: template().proof[3], status: state.proof.delivered ? "Self-reported; evidence not verified" : "Not recorded", kind: state.proof.delivered ? "reported" : "open", key: "delivered" },
      { text: template().proof[4], status: state.proof.followup ? "Self-reported; evidence not verified" : "Not recorded", kind: state.proof.followup ? "reported" : "open", key: "followup" }
    ];
    $("#proof-list").innerHTML = stages.map(function (stage, index) {
      return '<div class="proof-item ' + stage.kind + '"><span class="proof-index">' + String(index + 1).padStart(2, "0") +
        '</span><div><strong>' + escapeHtml(stage.text) + '</strong><small>' + stage.status + '</small></div>' +
        (stage.key ? '<button type="button" class="proof-toggle" data-proof="' + stage.key + '">' + (stage.kind === "reported" ? "Remove report" : "Mark self-reported") + "</button>" : '<span class="proof-indicator">' + (stage.kind === "draft" ? "DRAFT" : "OPEN") + "</span>") + "</div>";
    }).join("");
  }

  function renderAll() {
    renderTemplatePicker();
    renderRole();
    renderForm();
    renderResults();
  }

  function renderResults() {
    updateModel();
    renderMission();
    renderAssembly();
    renderMissing();
    renderPlans();
    renderProof();
  }

  function saveContribution(event) {
    event.preventDefault();
    var form = $("#contribution-form");
    if (!form.reportValidity()) return;
    all("#contribution-form [name]").forEach(function (input) {
      var value = input.type === "number" || input.type === "range" ? Number(input.value) : input.value.trim();
      state[input.name] = value;
    });
    state.parts[state.role] = true;
    state.edited = true;
    state.fullExample = false;
    save();
    renderAll();
    showToast(names[state.role] + " added. The mission map has changed.");
    scrollTo(".assembly");
  }

  function buildBrief() {
    var route = selectedRoute();
    var gaps = missingPieces();
    var lines = [
      "RIPPLE MISSION BRIEF",
      "====================",
      "",
      state.missionName,
      template().subtitle,
      "Location: " + state.location,
      "Status: " + Object.keys(state.parts).filter(function (key) { return state.parts[key]; }).length + " of 4 draft pieces entered",
      "",
      "THE PIECES",
      "Resource: " + (state.parts.asset ? pieceDescription("asset") : "Missing"),
      "Skilled work: " + (state.parts.skills ? pieceDescription("skills") : "Missing"),
      "Funding: " + (state.parts.funding ? pieceDescription("funding") : "Missing"),
      "Community partner: " + (state.parts.anchor ? pieceDescription("anchor") + " — " + state.needText : "Missing"),
      "",
      "WHAT IS STILL MISSING",
      gaps.length ? gaps.map(function (gap) { return "- " + gap.title + ": " + gap.detail; }).join("\n") : "- No draft pieces missing. Verify availability and evidence.",
      "",
      "SELECTED PLAN",
      route ? route.name + " — " + route.description : "No numerical model selected for this draft.",
      route ? "Example reach: " + route.output.mid + " " + model.unit + "; paid work: " + roundOne(route.paidHours.mid) + " hours; modeled spend: " + amount(route.cost) + "." : "",
      route ? "Example risks: " + route.risks.slice(0, 3).join(" | ") : "",
      "",
      "PROOF TO COLLECT",
      template().proof.map(function (item, index) { return String(index + 1) + ". " + item; }).join("\n"),
      "",
      "MODEL STATUS",
      "This is a browser-based hackathon prototype. Its numerical coefficients are illustrative and have not been validated with local partners. Draft entries are not identity verification, a payment, or a commitment."
    ];
    return lines.filter(function (line) { return line !== null && line !== undefined; }).join("\n");
  }

  function downloadBrief() {
    var content = buildBrief();
    var blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    var address = URL.createObjectURL(blob);
    var anchor = document.createElement("a");
    anchor.href = address;
    anchor.download = "ripple-mission-brief.txt";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(function () { URL.revokeObjectURL(address); }, 30000);
    showToast("Mission brief downloaded.");
  }

  function openBrief() {
    $("#brief-text").value = buildBrief();
    $("#brief-dialog").showModal();
  }

  function localServerAvailable() { return location.protocol === "http:" && /^(127\.0\.0\.1|localhost)$/.test(location.hostname); }

  function localReopenLink() {
    if (!serverCurrent || !localServerAvailable()) return "";
    var address = new URL(location.pathname, location.origin);
    address.searchParams.set("mission", serverCurrent.id);
    address.searchParams.set("view", serverCurrent.viewToken);
    address.hash = "studio";
    return address.toString();
  }

  function formatSavedAt(value) {
    var date = new Date(value);
    return Number.isFinite(date.getTime()) ? date.toLocaleString() : "time unavailable";
  }

  function renderServerDialog() {
    var hasLink = !!(serverCurrent && localReopenLink());
    $("#server-result").hidden = !hasLink;
    $("#save-server-copy").hidden = !serverCurrent;
    $("#confirm-server-save").disabled = serverBusy || serverAvailable !== true;
    $("#save-server-copy").disabled = serverBusy || serverAvailable !== true;
    if (!hasLink) {
      $("#confirm-server-save").innerHTML = 'Save draft to server <span aria-hidden="true">→</span>';
      return;
    }
    var canEdit = typeof editTokens[serverCurrent.id] === "string" && !!editTokens[serverCurrent.id];
    $("#confirm-server-save").innerHTML = canEdit ? 'Save new version <span aria-hidden="true">→</span>' : 'Save as a new copy <span aria-hidden="true">→</span>';
    $("#save-server-copy").hidden = !canEdit;
    $("#server-result-title").textContent = "Saved on this local server";
    $("#server-result-detail").textContent = "Version " + serverCurrent.version + " · " + formatSavedAt(serverCurrent.updatedAt) + (serverCurrent.dirty ? " · New browser changes are not on the server yet." : " · No local edits since that save.");
    $("#server-reopen-link").value = localReopenLink();
  }

  function setServerError(message) {
    var element = $("#server-error");
    element.hidden = !message;
    element.textContent = message || "";
  }

  async function apiRequest(path, options) {
    if (!localServerAvailable()) throw Object.assign(new Error("local server unavailable"), { status: 0 });
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); }, 12000);
    var response;
    try {
      response = await fetch(path, Object.assign({ cache: "no-store", credentials: "same-origin", signal: controller.signal }, options || {}));
    } catch (error) {
      throw Object.assign(new Error("local server unavailable"), { status: 0 });
    } finally {
      clearTimeout(timeout);
    }
    var data = null;
    try { data = await response.json(); } catch (error) { /* A generic file server may return HTML. */ }
    if (!response.ok) throw Object.assign(new Error("server rejected request"), { status: response.status });
    if (!data || typeof data !== "object") throw Object.assign(new Error("server response invalid"), { status: -1 });
    return data;
  }

  async function checkLocalServer() {
    var runtime = $("#server-runtime");
    if (!localServerAvailable()) {
      serverAvailable = false;
      runtime.classList.add("unavailable");
      runtime.textContent = location.protocol === "file:" ?
        "This page is open as a file. To use server saving, run python3 server.py in the project folder and open the local address it prints. Browser-only editing and brief downloads still work here." :
        "This is not the RIPPLE server on this computer. Run python3 server.py in the project folder and open the local address it prints. Nothing will be sent from this page.";
      renderServerDialog();
      return false;
    }
    runtime.classList.remove("unavailable");
    runtime.textContent = "Checking for the RIPPLE local server…";
    serverAvailable = null;
    renderServerDialog();
    try {
      var health = await apiRequest("/api/health");
      if (health.ok !== true || health.mode !== "local") throw new Error("not a RIPPLE local server");
      serverAvailable = true;
      runtime.textContent = "RIPPLE local server is ready. Your mission stays browser-only until you press Save below.";
      renderServerDialog();
      return true;
    } catch (error) {
      serverAvailable = false;
      runtime.classList.add("unavailable");
      runtime.textContent = "The RIPPLE backend is not running at this address. In the project folder, run python3 server.py, then open the local address it prints. Nothing was uploaded.";
      renderServerDialog();
      return false;
    }
  }

  async function showServerDialog() {
    setServerError("");
    renderServerDialog();
    $("#server-dialog").showModal();
    if (await checkLocalServer() && serverCurrent) loadServerRevisions();
  }

  function validForServer() {
    var form = $("#contribution-form");
    if (!form.checkValidity()) {
      return false;
    }
    var values = [state.quantity, state.pickupDays, state.budget, state.skilledHours, state.hourlyRate, state.needCount];
    return values.every(function (value) { return Number.isFinite(value) && value > 0; }) &&
      [state.quantity, state.pickupDays, state.needCount, state.quality].every(Number.isInteger) &&
      Number.isFinite(state.quality) && state.quality >= 0 && state.quality <= 100;
  }

  async function saveServerMission(forceCopy) {
    setServerError("");
    if (serverBusy) return;
    if (!validForServer()) {
      setServerError("Finish any empty or invalid fields before saving. Your last valid browser draft is still safe.");
      return;
    }
    if (serverAvailable !== true && !(await checkLocalServer())) return;
    var snapshot = clone(state);
    var current = serverCurrent;
    var editToken = current && editTokens[current.id];
    var update = !!(current && !forceCopy && typeof editToken === "string" && editToken);
    var path = update ? "/api/missions/" + encodeURIComponent(current.id) : "/api/missions";
    var options = update ? {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Edit-Token": editToken },
      body: JSON.stringify({ state: snapshot, version: current.version })
    } : {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: snapshot })
    };
    serverBusy = true;
    $("#server-runtime").textContent = update ? "Saving a new local version…" : "Creating a local saved draft…";
    renderServerDialog();
    try {
      var result = await apiRequest(path, options);
      if (typeof result.id !== "string" || !Number.isInteger(result.version) || (update ? !current.viewToken : typeof result.viewToken !== "string" || typeof result.editToken !== "string")) throw Object.assign(new Error("server response invalid"), { status: -1 });
      if (!update) {
        editTokens[result.id] = result.editToken;
        try { localStorage.setItem(EDIT_TOKENS_KEY, JSON.stringify(editTokens)); } catch (error) { /* Editing remains possible until this page closes. */ }
      }
      serverCurrent = {
        id: result.id,
        viewToken: update ? current.viewToken : result.viewToken,
        version: result.version,
        updatedAt: result.updatedAt,
        dirty: JSON.stringify(state) !== JSON.stringify(snapshot)
      };
      if (location.search.includes("mission=") || location.search.includes("view=")) history.replaceState(null, "", localReopenLink());
      persistServerCurrent();
      renderServerStatus();
      $("#server-runtime").classList.remove("unavailable");
      $("#server-runtime").textContent = "Saved. The reopen link below works only while this local server and its data are available.";
      $("#server-revisions").innerHTML = "<li>Loading version history…</li>";
      showToast("Mission saved as local version " + result.version + ".");
      loadServerRevisions();
    } catch (error) {
      if (error.status === 422) setServerError("The server found an empty or invalid mission field. Finish the form and try again. Nothing was overwritten.");
      else if (error.status === 409) setServerError("This mission has a newer server version. Nothing was overwritten. Reopen the latest saved link, or choose Save as a new copy.");
      else if (error.status === 401 || error.status === 403) setServerError("This browser no longer has permission to edit that saved draft. Save as a new copy instead.");
      else if (error.status === 0) setServerError("The local server could not be reached. Your mission is still safe in this browser. Run python3 server.py and try again.");
      else setServerError("This draft was not saved to the server. Your browser copy is unchanged; please try again.");
      $("#server-runtime").textContent = "No new server version was saved.";
    } finally {
      serverBusy = false;
      renderServerDialog();
    }
  }

  async function loadServerRevisions() {
    if (!serverCurrent || serverAvailable !== true) return;
    var id = serverCurrent.id;
    try {
      var result = await apiRequest("/api/missions/" + encodeURIComponent(id) + "/revisions?viewToken=" + encodeURIComponent(serverCurrent.viewToken));
      if (!serverCurrent || serverCurrent.id !== id) return;
      var list = $("#server-revisions");
      list.replaceChildren();
      if (!Array.isArray(result.revisions) || !result.revisions.length) {
        var empty = document.createElement("li");
        empty.textContent = "No version history available yet.";
        list.appendChild(empty);
        return;
      }
      result.revisions.slice(0, 10).forEach(function (revision) {
        var item = document.createElement("li");
        item.textContent = "Version " + revision.version + " · " + formatSavedAt(revision.updatedAt);
        list.appendChild(item);
      });
    } catch (error) {
      $("#server-revisions").innerHTML = "<li>Version history is unavailable right now.</li>";
    }
  }

  async function loadRemoteFromLink() {
    if (!localServerAvailable()) return;
    var params = new URLSearchParams(location.search);
    if (!params.has("mission") && !params.has("view")) return;
    var id = params.get("mission");
    var viewToken = params.get("view");
    var previousServerCurrent = serverCurrent;
    clearServerIdentity(false);
    if (!id || !viewToken) {
      serverCurrent = previousServerCurrent;
      persistServerCurrent();
      renderServerStatus();
      showToast("That local reopen link is incomplete. Your browser draft is unchanged.");
      return;
    }
    try {
      var result = await apiRequest("/api/missions/" + encodeURIComponent(id) + "?viewToken=" + encodeURIComponent(viewToken));
      var imported = normalizeState(result.state);
      if (!imported || result.id !== id || !Number.isInteger(result.version)) throw new Error("invalid mission data");
      rememberRecovery();
      state = imported;
      serverCurrent = { id: result.id, viewToken: viewToken, version: result.version, updatedAt: result.updatedAt, dirty: false };
      renderAll();
      save(true);
      showToast("Saved mission opened. The previous browser draft can be restored above.");
    } catch (error) {
      serverCurrent = previousServerCurrent;
      persistServerCurrent();
      renderServerStatus();
      showToast("Could not open that saved mission. Your browser draft is unchanged.");
      $("#server-save-status").textContent = "That reopen link could not be opened. Your previous browser draft and local save association are unchanged.";
    }
  }

  function copyReopenLink() {
    var input = $("#server-reopen-link");
    if (!input.value) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(input.value).then(function () { showToast("Local reopen link copied."); }).catch(function () {
        input.select();
        showToast("Select and copy the local reopen link.");
      });
    } else {
      input.select();
      showToast("Select and copy the local reopen link.");
    }
  }

  function onClick(event) {
    var heroRoleButton = event.target.closest("[data-hero-role]");
    if (heroRoleButton) { selectRole(heroRoleButton.dataset.heroRole, true); return; }
    var templateButton = event.target.closest("[data-template]");
    if (templateButton) { changeTemplate(templateButton.dataset.template); return; }
    var roleButton = event.target.closest(".role-card");
    if (roleButton) { selectRole(roleButton.dataset.role, false); return; }
    var focusButton = event.target.closest("[data-focus-role]");
    if (focusButton) { selectRole(focusButton.dataset.focusRole, true); return; }
    var priorityButton = event.target.closest("[data-priority]");
    if (priorityButton) {
      state.priority = priorityButton.dataset.priority;
      updateModel();
      renderPlans();
      save();
      return;
    }
    var routeButton = event.target.closest("[data-route]");
    if (routeButton) {
      state.routeId = routeButton.dataset.route;
      renderMissing();
      renderPlans();
      save();
      return;
    }
    var proofButton = event.target.closest("[data-proof]");
    if (proofButton) {
      state.proof[proofButton.dataset.proof] = !state.proof[proofButton.dataset.proof];
      state.edited = true;
      save();
      renderProof();
      renderMission();
      return;
    }
    var close = event.target.closest("[data-close-dialog]");
    if (close) { close.closest("dialog").close(); }
  }

  document.addEventListener("click", onClick);
  $("#contribution-form").addEventListener("submit", saveContribution);
  $("#contribution-form").addEventListener("input", function (event) {
    if (event.target.name && event.target.name in state) {
      if (!event.target.checkValidity()) {
        $("#save-status").textContent = "Finish this field; the last valid browser draft is kept";
        return;
      }
      state[event.target.name] = event.target.type === "number" || event.target.type === "range" ? Number(event.target.value) : event.target.value;
      state.edited = true;
      if (event.target.type === "range") {
        var output = event.target.parentElement.querySelector("output");
        if (output) output.textContent = number(event.target.value) + "%";
      }
      if (state.parts[state.role]) renderResults();
      save();
    }
  });
  $("#hero-start").addEventListener("click", function () { scrollTo("#studio"); });
  $("#nav-start").addEventListener("click", function () { scrollTo("#studio"); });
  $("#hero-example").addEventListener("click", setCompleteExample);
  $("#load-example").addEventListener("click", setCompleteExample);
  $("#new-mission").addEventListener("click", newMission);
  $("#undo-mission").addEventListener("click", restorePrevious);
  $("#open-guide").addEventListener("click", function () { $("#guide-dialog").showModal(); });
  $("#next-action-button").addEventListener("click", function () {
    if (this.dataset.focusRole) selectRole(this.dataset.focusRole, true);
    else scrollTo(this.dataset.scrollTo || "#proof");
  });
  $("#preview-brief").addEventListener("click", openBrief);
  $("#download-brief").addEventListener("click", downloadBrief);
  $("#download-from-modal").addEventListener("click", downloadBrief);
  $("#open-server-save").addEventListener("click", showServerDialog);
  $("#confirm-server-save").addEventListener("click", function () { saveServerMission(false); });
  $("#save-server-copy").addEventListener("click", function () { saveServerMission(true); });
  $("#copy-server-link").addEventListener("click", copyReopenLink);
  $("#copy-brief").addEventListener("click", function () {
    var content = $("#brief-text").value;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(content).then(function () { showToast("Brief copied."); }).catch(function () {
        $("#brief-text").select();
        showToast("Select and copy the brief text.");
      });
    } else {
      $("#brief-text").select();
      showToast("Select and copy the brief text.");
    }
  });
  all("dialog").forEach(function (dialog) {
    dialog.addEventListener("click", function (event) { if (event.target === dialog) dialog.close(); });
  });

  renderAll();
  save(true);
  loadRemoteFromLink();
})();
