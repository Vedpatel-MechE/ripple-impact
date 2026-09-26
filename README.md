# RIPPLE

RIPPLE helps people assemble a social good mission from four pieces: a useful resource, skilled work, funding, and a community partner who knows the need. It shows what is missing, compares possible plans, and produces a brief a real team can discuss.

## Run the full-stack demo

From this folder, run:

```bash
python3 server.py
```

Then open `http://127.0.0.1:4174/`. Python's standard library is sufficient: no package installation, account, or API key is required. The backend binds to this computer only. It saves explicitly shared mission snapshots and revisions in a local SQLite database.

You can still double-click [index.html](./index.html) to use the browser-only version. The builder, simulations, and text export work there, but server saving and reopening links require the command above.

## How to use it in one minute

1. Press **Try a complete example** to see a fully assembled mission.
2. Choose **Assets**, **Skills**, **Funding**, or **Community need**. Edit the short card and press **Add**. The impact chain changes.
3. Click a missing piece to fill it. The gap list and next action update.
4. Under **Which plan should we try?**, switch your priority and compare cost, reach, paid work, durability, risks, and model assumptions.
5. Open the **Proof trail** and export the mission brief for a teammate. In the full-stack demo, press **Save mission to server** to create a local reopen link and revision record.

For your own idea, choose **Something else entirely**. It lets you assemble the people and resources and export the plan. It does not invent a numerical forecast for a domain that has no model yet.

## What is actually implemented

- Four role specific contribution forms: assets, skilled paid work, funding, and community need
- Live mission map and missing piece detection
- Three distinct simulation templates: device reuse, food rescue, and tutoring
- 1,000 seeded trials per plan, with outcome ranges and a five point timeline
- Priority based plan comparison, proposed paid work scope, costs, risks, and visible assumptions
- Proof checklist with self reported status
- Local browser draft saving, one-step recovery, a guided tour, brief preview, copy, and text download
- A localhost Python/SQLite API for explicit mission saving, reopening, and version history; edit capability uses a high-entropy token held in the creator's browser
- Custom planning board for other social good ideas
- Responsive visual design and reduced motion support

## How the models work

The scenario engine in [engine.js](./engine.js) varies screening yield, paid hours, cost, and continuity across 1,000 reproducible trials. The device model covers one batch. The food and tutoring models assume weekly supply and hours and a monthly budget. Each has its own costs and routes. [app.js](./app.js) turns the results into the mission builder; [styles.css](./styles.css) provides the visual design.

All numerical coefficients are illustrative hackathon assumptions. They are not calibrated to a real organization. The app labels sample entries, estimates, and self-reported proof accordingly.

## What server saving does—and does not do

Saving to the server is an explicit action; merely filling out the builder keeps the draft in your browser. The reopen link works on the **same computer running the local server**. This is not a public hosting or sharing service. Someone with the view link can read that snapshot; the edit token is retained only in the creator's browser. The server records revisions but does not verify the truth of submitted claims. Do not enter real private data or transfer money through this prototype.

## A two minute hackathon demo

1. “A company is retiring laptops. A school knows students need them. A local technician wants paid work. Why do these pieces never meet?”
2. Open the incomplete mission and show RIPPLE identifying the missing school, operator, and budget.
3. Add each role, then show the chain become complete.
4. Compare **Fast handoff**, **Repair and place**, and **Local repair crew**. Change the skilled hours or budget and show the results move.
5. Switch to **Food rescue** to demonstrate that the platform handles a different problem with a separate model.
6. Export the mission brief and point to the proof trail: “The plan tells us what to check before we claim impact.”

## What is needed before public launch

The current site is a working local full-stack prototype. A public service would also need real partner onboarding, identity and asset verification, secure user accounts and hosting, evidence review, domain models calibrated with field data, and legal/payment operations for paid work. None of those are represented as live here.
