/* RIPPLE scenario engine.
 * All coefficients below are illustrative product assumptions. They are not
 * estimates calibrated to field data or predictions of a real project's impact.
 */
(function (scope) {
  "use strict";

  var RUNS = 1000;
  var CHECKPOINTS = [0, 6, 12, 18, 24];
  var WEEKS_PER_MONTH = 4.33;

  var templates = {
    devices: {
      id: "devices",
      title: "Give retired devices a second life",
      subtitle: "A company offers surplus laptops. A local technician can prepare them for people who need access.",
      unit: "devices",
      outputLabel: "Devices placed now",
      durableLabel: "Devices still in use at month 24",
      seriesLabel: "Devices in use",
      paidHoursLabel: "Paid technician hours",
      costLabel: "One-time project cost",
      quantityLabel: "Surplus devices available",
      budgetLabel: "One-time budget ($)",
      skilledHoursLabel: "Technician hours available",
      hourlyRateLabel: "Technician rate ($/hour)",
      needCountLabel: "People needing devices",
      qualityLabel: "Share that passes safety screening (%)",
      horizonNote: "One-time device batch; chart shows devices still working at months 0, 6, 12, 18, and 24.",
      defaults: { quantity: 40, budget: 5000, skilledHours: 120, hourlyRate: 25, needCount: 45, quality: 75 },
      routes: [
        {
          id: "direct", name: "Fast handoff", color: "#6be0f5",
          description: "Screen, wipe, and distribute devices that work immediately.",
          yield: 0.72, hoursPerUnit: 1.1, materialsPerUnit: 10, fixedCost: 0,
          base24Survival: 0.57, variation: 0.09, shockChance: 0.08, shockSeverity: 0.12,
          risks: ["Devices that need repair are left out.", "Without follow-up support, a broken laptop may stop helping its recipient."],
          assumption: "72% of screened devices work after a simple wipe and check; 1.1 paid hours and $10 in supplies per placement."
        },
        {
          id: "repair", name: "Repair and place", color: "#a999ff",
          description: "Pay a technician to fix recoverable devices before placement.",
          yield: 0.91, hoursPerUnit: 2.7, materialsPerUnit: 25, fixedCost: 200,
          base24Survival: 0.77, variation: 0.075, shockChance: 0.05, shockSeverity: 0.10,
          risks: ["Repair parts and diagnosis can cost more than expected.", "A technician may become the bottleneck if more devices arrive."],
          assumption: "91% of screened devices are usable after repair; 2.7 paid hours and $25 in parts per placement, plus $200 setup."
        },
        {
          id: "crew", name: "Local repair crew", color: "#86edba",
          description: "Hire a local lead to prepare devices and establish a follow-up repair desk.",
          yield: 0.89, hoursPerUnit: 3.05, materialsPerUnit: 23, fixedCost: 520,
          base24Survival: 0.88, variation: 0.055, shockChance: 0.035, shockSeverity: 0.08,
          risks: ["The crew needs a host and continued access to parts.", "Setup consumes budget before any device is placed."],
          assumption: "89% of screened devices can be placed; 3.05 paid hours and $23 in parts per device, plus $520 for shared tools and coordination."
        }
      ]
    },
    food: {
      id: "food",
      title: "Turn steady food surplus into meals",
      subtitle: "A food business commits a weekly surplus; local operators turn safe food into predictable access.",
      unit: "meals per week",
      outputLabel: "Safe meals delivered each week now",
      durableLabel: "Weekly meals still delivered at month 24",
      seriesLabel: "Safe meals delivered per week",
      paidHoursLabel: "Paid operator hours per week",
      costLabel: "Monthly operating cost",
      quantityLabel: "Surplus meal portions offered each week",
      budgetLabel: "Monthly operating budget ($)",
      skilledHoursLabel: "Paid operator hours available per week",
      hourlyRateLabel: "Operator rate ($/hour)",
      needCountLabel: "Weekly meals needed nearby",
      qualityLabel: "Share that passes food-safety screening (%)",
      horizonNote: "Assumes the same supply and funding recur weekly. Chart shows safe meals delivered per week at months 0, 6, 12, 18, and 24.",
      defaults: { quantity: 180, budget: 3200, skilledHours: 45, hourlyRate: 22, needCount: 210, quality: 78 },
      routes: [
        {
          id: "pickup", name: "Same-day pickup", color: "#6be0f5",
          description: "Move screened food quickly through existing community pickup points.",
          yield: 0.74, hoursPerUnit: 0.16, materialsPerUnit: 0.32, fixedCost: 0,
          base24Survival: 0.48, variation: 0.10, shockChance: 0.11, shockSeverity: 0.16,
          risks: ["Short pickup windows can cause safe food to go unused.", "Continuity depends on the donor maintaining a weekly supply."],
          assumption: "74% of safe surplus reaches recipients; 0.16 paid hours and $0.32 in supplies per meal."
        },
        {
          id: "coldchain", name: "Cold-chain rescue", color: "#a999ff",
          description: "Pay a coordinator and support refrigerated routing to preserve more safe food.",
          yield: 0.91, hoursPerUnit: 0.22, materialsPerUnit: 0.65, fixedCost: 280,
          base24Survival: 0.76, variation: 0.075, shockChance: 0.065, shockSeverity: 0.12,
          risks: ["Refrigeration and transport availability can break the route.", "Food-safety screening remains essential even with cold storage."],
          assumption: "91% of safe surplus is delivered; 0.22 paid hours and $0.65 in supplies per meal, plus $280 monthly routing overhead."
        },
        {
          id: "kitchen", name: "Community meal crew", color: "#86edba",
          description: "Hire local cooks to turn eligible surplus into ready-to-eat meals.",
          yield: 0.86, hoursPerUnit: 0.30, materialsPerUnit: 1.15, fixedCost: 420,
          base24Survival: 0.84, variation: 0.06, shockChance: 0.045, shockSeverity: 0.09,
          risks: ["Kitchen access and scheduling must be secured locally.", "Food that fails screening is never assumed safe to serve."],
          assumption: "86% of safe surplus becomes served meals; 0.30 paid hours and $1.15 in ingredients and supplies per meal, plus $420 monthly kitchen overhead."
        }
      ]
    },
    tutoring: {
      id: "tutoring",
      title: "Connect paid tutors with students",
      subtitle: "A school has students requesting support and a budget for skilled teaching time.",
      unit: "students per week",
      outputLabel: "Students supported each week now",
      durableLabel: "Students still receiving support at month 24",
      seriesLabel: "Students supported per week",
      paidHoursLabel: "Paid tutor hours per week",
      costLabel: "Monthly operating cost",
      quantityLabel: "Students signed up for support",
      budgetLabel: "Monthly tutoring budget ($)",
      skilledHoursLabel: "Paid tutor hours available per week",
      hourlyRateLabel: "Tutor rate ($/hour)",
      needCountLabel: "Students needing support nearby",
      qualityLabel: "Expected consistent attendance (%)",
      horizonNote: "Assumes monthly funding and tutor hours continue. Chart shows students receiving weekly support at months 0, 6, 12, 18, and 24; it does not measure learning gains.",
      defaults: { quantity: 60, budget: 2800, skilledHours: 36, hourlyRate: 24, needCount: 75, quality: 80 },
      routes: [
        {
          id: "dropin", name: "Open tutoring hours", color: "#6be0f5",
          description: "Offer one-to-one help to students who show up each week.",
          yield: 0.76, hoursPerUnit: 0.95, materialsPerUnit: 1.5, fixedCost: 0,
          base24Survival: 0.42, variation: 0.10, shockChance: 0.10, shockSeverity: 0.15,
          risks: ["Students with the largest barriers may not attend drop-in sessions.", "Low attendance can waste available tutor time."],
          assumption: "76% of consistently attending students can be served; 0.95 paid tutor hours and $1.50 in materials per student each week."
        },
        {
          id: "cohort", name: "Small learning cohorts", color: "#a999ff",
          description: "Group students with similar needs and keep the same tutor with each cohort.",
          yield: 0.90, hoursPerUnit: 0.52, materialsPerUnit: 3.0, fixedCost: 180,
          base24Survival: 0.69, variation: 0.075, shockChance: 0.06, shockSeverity: 0.12,
          risks: ["Students may need different subjects or schedules.", "Group support may not be enough for students needing individual help."],
          assumption: "90% of consistently attending students fit a cohort; 0.52 paid tutor hours and $3 in materials per student each week, plus $180 monthly coordination."
        },
        {
          id: "peer", name: "Paid peer-tutor crew", color: "#86edba",
          description: "Train and pay local peer tutors, with a skilled lead supervising sessions.",
          yield: 0.86, hoursPerUnit: 0.67, materialsPerUnit: 3.5, fixedCost: 310,
          base24Survival: 0.82, variation: 0.06, shockChance: 0.04, shockSeverity: 0.09,
          risks: ["A lead must monitor tutoring quality and safeguarding.", "Peer tutors need regular training and scheduling support."],
          assumption: "86% of consistently attending students can be served; 0.67 paid team hours and $3.50 in materials per student each week, plus $310 monthly supervision."
        }
      ]
    }
  };

  function number(value, fallback, max) {
    var parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.min(max, Math.max(0, parsed));
  }

  function cleanInput(template, input) {
    input = input || {};
    var defaults = template.defaults;
    return {
      quantity: number(input.quantity, defaults.quantity, 100000),
      budget: number(input.budget, defaults.budget, 100000000),
      skilledHours: number(input.skilledHours, defaults.skilledHours, 100000),
      hourlyRate: number(input.hourlyRate, defaults.hourlyRate, 10000),
      needCount: number(input.needCount, defaults.needCount, 100000),
      quality: number(input.quality, defaults.quality, 100)
    };
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function hash(text) {
    var value = 2166136261;
    for (var index = 0; index < text.length; index += 1) {
      value ^= text.charCodeAt(index);
      value = Math.imul(value, 16777619);
    }
    return value >>> 0;
  }

  function generator(seed) {
    var state = seed >>> 0;
    return function () {
      state += 0x6D2B79F5;
      var value = state;
      value = Math.imul(value ^ (value >>> 15), value | 1);
      value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
      return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };
  }

  function normal(random) {
    var a = Math.max(random(), 0.0000001);
    return Math.sqrt(-2 * Math.log(a)) * Math.cos(2 * Math.PI * random());
  }

  function percentile(values, portion) {
    var sorted = values.slice().sort(function (a, b) { return a - b; });
    if (!sorted.length) return 0;
    var point = (sorted.length - 1) * portion;
    var below = Math.floor(point);
    var above = Math.ceil(point);
    return sorted[below] + (sorted[above] - sorted[below]) * (point - below);
  }

  function band(trials, key, digits) {
    var values = trials.map(function (trial) { return trial[key]; });
    var power = Math.pow(10, digits || 0);
    function rounded(portion) { return Math.round(percentile(values, portion) * power) / power; }
    return { low: rounded(0.10), mid: rounded(0.50), high: rounded(0.90) };
  }

  function routeTrial(template, route, input, random) {
    var safeSupply = input.quantity * (input.quality / 100);
    var supplyNoise = clamp(1 + normal(random) * 0.07, 0.78, 1.18);
    var yieldNoise = clamp(1 + normal(random) * 0.045, 0.85, 1.12);
    var potential = Math.max(0, Math.floor(Math.min(input.needCount, safeSupply * route.yield * supplyNoise * yieldNoise)));
    var hoursPerUnit = route.hoursPerUnit * clamp(1 + normal(random) * 0.08, 0.78, 1.25);
    var materialsPerUnit = route.materialsPerUnit * clamp(1 + normal(random) * 0.10, 0.72, 1.30);
    var recurring = template.id !== "devices";
    var costMultiplier = recurring ? WEEKS_PER_MONTH : 1;
    var costPerUnit = costMultiplier * (hoursPerUnit * input.hourlyRate + materialsPerUnit);
    var laborLimit = Math.floor(input.skilledHours / Math.max(0.0001, hoursPerUnit));
    var fundingLimit = costPerUnit > 0
      ? Math.floor(Math.max(0, input.budget - route.fixedCost) / costPerUnit)
      : potential;
    var output = Math.max(0, Math.min(potential, laborLimit, fundingLimit));
    var paidHours = output * hoursPerUnit;
    var cost = output > 0 ? route.fixedCost + output * costPerUnit : 0;
    var fullReachCost = potential > 0 ? route.fixedCost + potential * costPerUnit : 0;
    var budgetGap = Math.max(0, fullReachCost - input.budget);
    var series = [output];
    var active = output;
    var sixMonthSurvival = Math.pow(route.base24Survival, 0.25);

    for (var period = 1; period < CHECKPOINTS.length; period += 1) {
      var survival = clamp(sixMonthSurvival + normal(random) * route.variation, 0.45, 0.998);
      if (random() < route.shockChance) survival *= (1 - route.shockSeverity);
      active = Math.max(0, Math.round(active * survival));
      series.push(active);
    }

    return {
      output: output,
      durable: active,
      paidHours: paidHours,
      cost: cost,
      budgetGap: budgetGap,
      series: series,
      laborShortfall: potential > laborLimit
    };
  }

  function routeRisks(template, route, input, trials, gap) {
    var risks = route.risks.slice();
    if (input.quality < 45) risks.push("The screening estimate is low; verify usable supply before committing resources.");
    if (input.needCount < input.quantity * input.quality / 100 * route.yield) risks.push("More safe supply may be available than the stated nearby demand.");
    if (gap.mid > 0) risks.push("Current budget is below the modeled cost of serving all eligible supply.");
    if (trials.filter(function (trial) { return trial.laborShortfall; }).length > RUNS / 2) {
      risks.push("Available skilled hours limit how much of the eligible supply can be served.");
    }
    if (template.id === "food") risks.push("Only food that passes local safety requirements can enter a real program.");
    if (template.id === "tutoring") risks.push("Student attendance and actual learning gains require field measurement.");
    return risks.slice(0, 5);
  }

  function routeAssumptions(template, route, input) {
    var assumptions = [
      "Illustrative scenario model; coefficients have not been validated with local partners.",
      route.assumption,
      "Quality is applied before route yield; items or participants outside that share are excluded.",
      "Success means month-24 activity reaches at least 40% of the stated nearby need."
    ];
    if (template.id === "devices") {
      assumptions.push("Budget and paid technician hours cover this one batch; active devices may decrease through failure and loss of use.");
    } else {
      assumptions.push("Weekly supply, paid hours, and monthly funding repeat for 24 months; the model varies continuity at each six-month checkpoint.");
    }
    if (input.hourlyRate === 0) assumptions.push("The hourly rate is $0, so paid hours are scoped but labor cost is omitted.");
    return assumptions;
  }

  function normalizedPriorities(priorities) {
    priorities = priorities || {};
    var access = number(priorities.access, 60, 100);
    var work = number(priorities.work, 20, 100);
    var durability = number(priorities.durability, 20, 100);
    var total = access + work + durability;
    if (total === 0) return { access: 0.6, work: 0.2, durability: 0.2 };
    return { access: access / total, work: work / total, durability: durability / total };
  }

  function simulate(templateId, input, priorities) {
    var template = templates[templateId];
    if (!template) throw new Error("Unknown RIPPLE template: " + templateId);
    var values = cleanInput(template, input);
    var weights = normalizedPriorities(priorities);
    var goal = Math.ceil(values.needCount * 0.40);
    var possible = Math.max(1, Math.min(values.quantity, values.needCount));
    var results = template.routes.map(function (route) {
      var random = generator(hash(JSON.stringify({ templateId: templateId, input: values, route: route.id })));
      var trials = [];
      for (var index = 0; index < RUNS; index += 1) {
        trials.push(routeTrial(template, route, values, random));
      }
      var output = band(trials, "output", 0);
      var durable = band(trials, "durable", 0);
      var paidHours = band(trials, "paidHours", 1);
      var cost = Math.round(percentile(trials.map(function (trial) { return trial.cost; }), 0.50));
      var budgetGap = band(trials, "budgetGap", 0).mid;
      var successRate = goal === 0 ? 0 : Math.round(100 * trials.filter(function (trial) {
        return trial.durable >= goal;
      }).length / RUNS);
      var series = CHECKPOINTS.map(function (_, checkpoint) {
        return Math.round(percentile(trials.map(function (trial) { return trial.series[checkpoint]; }), 0.50));
      });
      var score = 100 * (
        weights.access * output.mid / possible +
        weights.work * paidHours.mid / Math.max(1, values.skilledHours) +
        weights.durability * durable.mid / possible
      );
      if (budgetGap > 0) score -= 8 * Math.min(1, budgetGap / Math.max(1, values.budget));
      return {
        id: route.id,
        name: route.name,
        description: route.description,
        color: route.color,
        output: output,
        durable: durable,
        paidHours: paidHours,
        successRate: successRate,
        cost: cost,
        budgetGap: budgetGap,
        series: series,
        score: Math.round(clamp(score, 0, 100)),
        risks: routeRisks(template, route, values, trials, { mid: budgetGap }),
        assumptions: routeAssumptions(template, route, values)
      };
    });
    return { unit: template.unit, routes: results };
  }

  scope.RippleEngine = { simulate: simulate, templates: templates };
})(typeof window !== "undefined" ? window : globalThis);
