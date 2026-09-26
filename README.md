# RIPPLE

RIPPLE is a small social-good mission exchange. A person can enter just one real piece—a community need, useful resource, paid skill, or funding offer. The backend checks which pieces fit, shows what is missing, and waits for each role to accept before it calls a plan agreed.

## Run the full-stack demo

From this folder, run:

```bash
python3 server.py
```

Then open `http://127.0.0.1:4174/`. Python's standard library is sufficient: no package installation, account, or API key is required. The new live board and backend bind to this computer only. Signal and consent records are saved in a local SQLite database. The older interactive planner is still available at `http://127.0.0.1:4174/planner`.

You can still double-click [index.html](./index.html) to use the browser-only version. The builder, simulations, and text export work there, but server saving and reopening links require the command above.

## Use the live board

1. Choose what you actually have: a community need, useful resource, skilled paid work, or funding offer.
2. Fill in the short form and add it. Listings are explicitly marked **unverified**.
3. The backend matches by mission area and location. It checks like-for-like quantity and whether the funding offer covers the worker's quoted labor.
4. The board shows missing roles and any resource or labor-budget gap. Any of the four roles can be the first signal.
5. When all four pieces fit, someone who owns one of the selected listings clicks **Start confirmation**. The server checks that listing's owner key before reserving the four offers.
6. Each listing owner opens **Your invitations** in the same browser where they created their listing, reviews the complete plan, and accepts or declines for their own role. Four decisions are recorded separately. A decline reopens the offers; unanswered invitations expire after seven days.
7. Use **Withdraw** on your own open listing. The app preserves a record that it was withdrawn.

The owner key is saved in that browser and controls withdrawal and invitation responses for its listing. It proves control of the listing record, not the person's or organization's real identity. There is no account recovery or external invitation delivery yet.

## Keep the planning prototype

The older interactive planner remains at `/planner` (or [index.html](./index.html)). It includes device reuse, food rescue, tutoring, an open-ended planning board, illustrative route comparisons, and a self-reported proof checklist. Its numbers are hackathon assumptions, not validated impact forecasts.

## What is actually implemented

- A new default mission-exchange board with four standalone signal forms and an open signal pool
- Persistent SQLite signal records, strict field validation, and a matching API
- Match checks for mission area, location, unit/quantity coverage, and labor-funding coverage; leads can start from any role
- Owner-only withdrawal and confirmation using owner keys stored hashed in the database; a selected listing owner must start confirmation
- A local **Your invitations** inbox that shows each owner only the invitations for listings created in their browser; the organizer no longer receives all four response links
- Role-specific plan review before accepting or declining; the public assembly board shows only the mission title, location, and decision status
- One final response per role, recorded in an append-only activity table; all four must accept for the assembly to be marked agreed
- Declines reopen reserved signals; unanswered assemblies expire after seven days
- Clear unverified labels and no payment movement or invented outcome claims
- Legacy interactive mission planner at `/planner`

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

## What the local pilot does—and does not do

The new board saves signals and invitation decisions to SQLite on the **same computer running the server**. Other people cannot reach it over the internet. The local inbox uses an owner key saved in the browser that created each listing; another browser cannot act for that listing unless its key is deliberately transferred. This does not verify real-world identity, resource ownership, funding, or delivery. The legacy planner can still explicitly save a snapshot and keep its edit token in the creator's browser. Do not enter sensitive personal data or transfer money through this prototype.

## A two-minute hackathon demo

1. Add a community need for 20 laptops in a city.
2. Add a company's 24 unused laptops, a technician offering 10 hours at $30/hour, and a $300 funding offer.
3. Show the backend move the chain to **Ready to confirm** only after quantity and quoted labor match.
4. As an owner of one selected listing, start confirmation. Open **Your invitations** and review each role's invitation. For a fictional local demo created in one browser, that browser holds all four owner keys; this simulates the workflow, not four independently identified people.
5. Show that the offers are still marked unverified and say plainly that this build records fit and consent—it does not verify owners, move money, or claim delivery.

`python3 -m unittest -v test_server.py` passes 15 local HTTP integration tests, including owner-only assembly creation, role-scoped invitation access, expiry, and database migration.

## What is needed before public launch

This is a working local full-stack pilot, not a public service. Before real participants can use it remotely, RIPPLE still needs hosted HTTPS, user accounts and key recovery, identity and organization checks, external invitation delivery, moderation, evidence review, privacy/retention rules, and legal/payment operations for paid work. None of those are represented as live here.
