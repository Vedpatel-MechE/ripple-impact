# RIPPLE — project handoff

Updated: September 26, 2026

Workspace: `/Users/ved/Documents/ChatGPT/Ripple- Hackgt`

Repository: `https://github.com/Vedpatel-MechE/ripple-impact`

## The product now

RIPPLE turns donated corporate technology into accepted, usable devices for public schools and charities. It coordinates a company, a recipient, one or more paid repair partners, and public charitable funding around a mission with an itemized activation budget and evidence trail.

The equipment is donated. Donors do not invest, receive ownership, or earn a return. Donations fund only activation work such as secure erasure, diagnosis, parts, repair labor, packing, delivery, and responsible recycling. Impact is counted only after recipient acceptance.

The public promise is:

> Retired by companies. Ready for classrooms.

## What is implemented

- A new public landing page with sourced access/e-waste context, a clear activation workflow, sample mission progress, four role routes, and the proof model.
- Separate multi-page portals for companies, schools/charities, repair partners, and public donors.
- A filterable mission browser, detailed mission budget/custody/evidence page, and dedicated transparency architecture.
- Persistent validated company, recipient, and repairer pilot intakes.
- Three fictional mission records returned by the backend.
- Persistent simulated pledges that update sample mission progress while always returning `paymentProcessed: false`.
- Append-only intake and pledge event records.
- Responsive navigation and layouts, keyboard focus states, reduced-motion support, status feedback, and clear prototype disclosures.
- The previous general mission planner and signal/consent system remain under `/planner` and their existing API routes.
- A local-and-hosted authentication gateway with participant registration, password hashing, HttpOnly sessions, role checks, CSRF protection, and logout.
- An administrator-only inquiry operations dashboard with queue metrics, search/filtering, complete submission detail, internal notes, workflow statuses, and append-only review history.
- Every new role inquiry and simulated pledge is associated with its authenticated participant account.
- A signed-in Smart Cart that converts a group's plain-language goal, budget, size, and priority into three explainable, budget-safe activation packages.
- A public shareable Circle that lets friends contribute separately, attach optional motivations, and see live group progress and a changing social story.
- A two-step Visa-style sandbox checkout whose demo card fields stay browser-side; the backend never receives card numbers, expiry dates, security codes, or billing names.
- Persistent Circle, contribution, and append-only Circle event records with transactional overfunding protection.

## Important routes

| Route | Purpose |
| --- | --- |
| `/` | Participant registration and sign-in gateway |
| `/home` | Signed-in platform story, workflow, roles, missions, and proof |
| `/admin` | Administrator-only inquiry operations console |
| `/company` | Declare a potential donated batch |
| `/recipient` | Submit an aggregate school/charity device need |
| `/repair` | Submit repair capacity and services |
| `/fund` | Browse sample missions and record a simulated pledge |
| `/missions` | Filter six illustrative mission-stage scenarios |
| `/mission?mission=south-atlanta-laptop-lab` | Inspect mission economics, custody, and evidence |
| `/smart-cart` | Build a group package and publish a shareable Circle |
| `/circle?id=<id>` | Open a Circle, see live progress, share it, and complete sandbox checkout |
| `/transparency` | Verification, ledger, custody, privacy, standards, and limitations |
| `/planner` | Legacy general-purpose planning prototype |

## How to run and verify

```bash
python3 server.py
```

Open `http://127.0.0.1:4174/`.

```bash
python3 -m unittest -v
python3 -m py_compile server.py
node --check site.js
node --check smart-cart.js
node --check circle.js
git diff --check
```

All 20 local HTTP tests pass. They include participant registration, CSRF enforcement, inquiry ownership, admin role enforcement, status updates, append-only history, logout invalidation, Smart Cart recommendations, Circle publication, public progress, sandbox contribution, overfunding protection, and proof that card data is never persisted.

Local administrator development access is `admin@ripple.local` / `RippleAdmin!2026`, but it is no longer printed or autofilled in the browser. Vercel creates no default administrator; hosted access requires private `RIPPLE_ADMIN_EMAIL` and `RIPPLE_ADMIN_PASSWORD` environment values.

## Code map

- `network.html`: landing page
- `company.html`, `recipient.html`, `repair.html`, `fund.html`: role portals
- `missions.html`, `mission.html`, `transparency.html`: discovery, detail, and trust pages
- `smart-cart.html`, `smart-cart.js`: group planner, recommendation comparison, and Circle creation
- `circle.html`, `circle.js`: shareable Circle, contributor story, social-share actions, and sandbox checkout
- `site.css`: shared design system and responsive behavior
- `site.js`: shared interaction/controller layer
- `login.html`, `auth.js`: authentication gateway
- `admin.html`, `admin.js`: administrator dashboard
- `server.py`: shared static/local routing, validation, authentication, APIs, and dual-database application logic
- `ripple_database.py`: SQLite/Postgres compatibility adapter
- `schema_postgres.sql`: hosted schema, invariants, and append-only triggers
- `api/index.py`: Vercel Python Function entry point
- `vercel.json`, `scripts/build_vercel.py`: hosted routes, security headers, and static-asset build
- `test_server.py`: 20 integration tests
- `index.html`, `styles.css`, `engine.js`, `app.js`: legacy planner
- `network.css`, `network.js`: legacy signal exchange assets retained for compatibility

## Trust boundary

The current app is a functional local product demonstration and is prepared for hosted Preview deployment—not a live social-good network.

- Missions and organizations are fictional samples.
- Intake submissions are unverified inquiries and are not public commitments.
- No ownership, organization authority, need, device condition, repair capability, or delivery is verified.
- No real payment, asset transfer, pickup, repair contract, tax receipt, or impact claim occurs.
- The Visa-style checkout is a sandbox simulation, not a live Visa API or payment gateway. Card-form values are wiped after a successful simulation and are never sent to RIPPLE.
- Smart Cart currently uses an explainable local rules engine over fictional mission budgets. A production GenAI model and live catalog/partner data are not connected yet.
- Student-level personal data should never be collected in this workflow.

For a real pilot, a qualified charity/fiscal sponsor should receive and administer funds, approve expenses, manage reallocation/refunds, reconcile the ledger, and issue any eligible acknowledgment. RIPPLE should provide the activation and proof software.

## Strongest hackathon framing

The problem is not simply “companies throw away laptops.” A donated device is not yet a usable learning device. The activation gap—authorization, matching, secure erasure, diagnosis, parts, paid labor, QA, delivery, failure routing, and recipient acceptance—is fragmented, expensive, and hard to trust.

RIPPLE's three core product ideas are:

1. **Mission Composer + Tranche Engine** — turn a large batch into feasible work packages matched to recipient requirements and repair capacity.
2. **Batch Passport + Chain of Custody** — preserve who claimed, checked, released, received, repaired, rejected, and accepted each batch.
3. **Restricted Giving Ledger + Impact Receipt** — show the approved activation budget and keep pledge, payment, work, delivery, and accepted impact as separate states.

For the Aramco Americas social-good track, RIPPLE connects education access, electronic-waste reduction, paid local technical work, and transparent philanthropy. The current prototype demonstrates the system honestly; it does not invent partners or impact.

## Best next implementation phase

Do not add more glossy pages first. Run a manual pilot-design exercise with one real organization in each role, then add:

1. reviewed organization accounts and permissions;
2. private batch manifests and secure document storage;
3. two-party custody handoffs and exception records;
4. item-level sanitization/QA evidence;
5. a real charitable steward and compliant payment integration;
6. tranche recommendation logic trained on real capacity and failure data.

Keep the product narrow: laptops, tablets, desktops, and monitors first. Other commodities can be a later vertical only after its own safety, grading, repair, logistics, and acceptance rules are defined.
