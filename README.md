# RIPPLE

RIPPLE is a full-stack prototype for turning retired corporate technology into accepted, usable devices for public schools and charities. It runs locally with SQLite and is prepared for Vercel with a managed Postgres database.

The platform coordinates four parties around one transparent mission:

1. A company offers equipment at no charge.
2. A school or charity defines what recipients can actually use.
3. Repair partners scope and perform paid activation work.
4. Public donors fund the activation gap: secure erasure, diagnosis, parts, labor, packing, delivery, and responsible recycling.

RIPPLE keeps “offered,” “repairable,” “delivered,” and “accepted” separate. A mission counts impact only after the receiving organization accepts the devices.

## Run locally

Local development uses Python's standard library, SQLite, and browser-native HTML/CSS/JavaScript. No package install or API key is required. Create a participant account from the opening screen. Local administrator credentials are documented below but are intentionally never printed in the browser UI.

```bash
python3 server.py
```

Open [http://127.0.0.1:4174/](http://127.0.0.1:4174/).

The SQLite database is created as `ripple.sqlite3`. To use a different port or database:

```bash
python3 server.py --port 4176 --db /tmp/ripple-demo.sqlite3
```

## Product surfaces

| Route | Audience and job |
| --- | --- |
| `/` | Authentication gateway for participant registration and sign-in |
| `/home` | Signed-in platform landing page: problem, workflow, roles, and proof model |
| `/admin` | Administrator-only inquiry dashboard, filters, review notes, statuses, and history |
| `/company` | Company batch declaration and private pilot intake |
| `/recipient` | School/charity device-need intake without student-level personal data |
| `/repair` | Repairer capability, service, capacity, and turnaround intake |
| `/fund` | Sample mission browser and simulation-only pledge flow |
| `/missions` | Filterable mission-discovery experience |
| `/mission?mission=<slug>` | Mission budget, readiness, custody, evidence, and contribution preview |
| `/smart-cart` | Signed-in group planner that compares activation packages and creates a shareable Circle |
| `/circle?id=<id>` | Public, shareable group-funding page with live sandbox progress and contribution checkout |
| `/transparency` | Verification, giving-ledger, custody, privacy, and prototype-boundary model |
| `/planner` | The earlier general-purpose social-good planning prototype |

## Core product features

### Mission Composer and Tranche Engine

A large equipment batch can be divided into workable repair tranches and aligned with recipient requirements. The current build demonstrates this workflow with three fictional missions; automatic optimization is a future phase.

### Batch Passport and Chain of Custody

The experience models claim-specific evidence across declaration, release, sanitization, repair, QA, delivery, and recipient acceptance. One vague “verified” badge is deliberately avoided.

### Restricted Giving Ledger and Impact Receipt

The donor experience exposes a mission's activation budget and separates pledge, allocation, paid work, QA, and recipient acceptance. Prototype pledges are persisted as simulations only.

### Smart Cart and shared Circles

A signed-in organizer describes the group's goal, budget, size, and priority. RIPPLE calculates three explainable mission packages from the selected sample mission's visible activation costs, keeps every option within budget, and lets the organizer publish one shareable Circle. Friends can then contribute separately, add an optional motivation, and watch the group's total and shared story update.

The current recommendation engine is a deterministic local planning simulation, not a hosted generative-AI model. The checkout is a Visa-style sandbox interaction, not a Visa integration: demo card fields remain in the browser and the server records only the chosen amount, display preference, optional message, and a fake sandbox reference. No money moves.

## Backend APIs

The server has strict JSON schemas, body limits, same-origin protections, persistent SQLite/Postgres records, database-backed throttling for public-sensitive actions, and append-only event tables.

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Create a local participant account and secure session |
| `POST` | `/api/auth/login` | Authenticate a participant or administrator |
| `POST` | `/api/auth/logout` | Invalidate the current session |
| `GET` | `/api/auth/session` | Return the current user and CSRF token |
| `GET` | `/api/my/intakes` | Return the signed-in participant's inquiry states |
| `GET` | `/api/admin/dashboard` | Administrator-only inquiry queue and counts |
| `PATCH` | `/api/admin/intakes/<id>` | Administrator status/review update with audit event |
| `GET` | `/api/platform` | Sample mission summaries and local prototype counters |
| `GET` | `/api/impact-missions` | Three honestly labeled fictional mission summaries |
| `GET` | `/api/impact-missions/<slug>` | One fictional mission with budget, repair, and progress data |
| `POST` | `/api/intakes` | Validated company, recipient, or repairer inquiry |
| `POST` | `/api/pledges` | Simulation-only pledge; always returns `paymentProcessed: false` |
| `POST` | `/api/smart-cart/recommendations` | Authenticated, CSRF-protected generation of three budget-safe package options |
| `POST` | `/api/smart-carts` | Publish the selected package as a shareable Circle |
| `GET` | `/api/smart-carts/<id>` | Public Circle progress, package, mission, contributors, and shared story |
| `GET` | `/api/my/smart-carts` | Return Circles created by the signed-in organizer |
| `POST` | `/api/smart-carts/<id>/checkout` | Record an explicitly confirmed sandbox contribution; never accepts card data |

The legacy planner, signal matching, owner-token, invitation, and consent APIs remain available for backwards compatibility.

## Architecture

- `server.py`: shared validation, routing, authentication, mission, Circle, and legacy APIs
- `ripple_database.py`: small compatibility layer for local SQLite and hosted Postgres
- `schema_postgres.sql`: idempotent hosted schema and append-only database triggers
- `api/index.py`: Vercel Python Function entry point
- `vercel.json`, `scripts/build_vercel.py`: Vercel routes, security headers, and public-asset allowlist
- `site.css`: shared intentional design system and responsive layouts
- `site.js`: authenticated navigation, mission loading/filtering, role intakes, donor simulation, and feedback
- `login.html`, `auth.js`: sign-in and participant registration gateway
- `admin.html`, `admin.js`: protected inquiry operations console
- `network.html`: signed-in platform landing page
- `company.html`, `recipient.html`, `repair.html`, `fund.html`: role-specific portals
- `missions.html`, `mission.html`, `transparency.html`: mission and trust surfaces
- `smart-cart.html`, `smart-cart.js`: authenticated group-goal planner and Circle publisher
- `circle.html`, `circle.js`: public Circle, social sharing, and browser-only sandbox checkout
- `test_server.py`: local HTTP integration and security-boundary tests
- `index.html`, `styles.css`, `engine.js`, `app.js`: legacy general mission planner at `/planner`

The frontend is framework-free on purpose: each page is server-rendered static HTML with shared CSS and small progressive JavaScript modules. This keeps the hackathon build easy to run while leaving clear seams for a component framework, hosted API, identity provider, and payment processor later.

## Verify

```bash
python3 -m unittest -v
python3 -m py_compile server.py
node --check site.js
node --check smart-cart.js
node --check circle.js
git diff --check
```

There are 20 HTTP integration tests covering authentication, CSRF and role boundaries, the full administrator inquiry workflow, role-intake and simulated-pledge APIs, the complete Smart Cart/Circle/sandbox checkout flow, plus legacy persistence, matching, owner authorization, invitation privacy, expiry, origin checks, and database migration.

## Deploy to Vercel

The repository is deployment-ready, but Vercel still needs a durable database and private environment values:

1. Import `Vedpatel-MechE/ripple-impact` in Vercel.
2. In the project, open **Storage** and connect a managed Postgres provider such as Neon. Ensure its pooled connection is available as `DATABASE_URL` in Preview and Production.
3. Add `RIPPLE_ADMIN_EMAIL`, `RIPPLE_ADMIN_PASSWORD`, and `RIPPLE_ALLOWED_ORIGINS` in **Settings → Environment Variables**. Use `.env.example` as the field reference; never commit real values.
4. Deploy a Preview. The build copies only HTML, CSS, and browser JavaScript into `dist/`; Python source, tests, SQLite files, documentation, and secrets are not browser assets.
5. Open `/api/health`. A ready hosted deployment returns `{"ok":true,"mode":"hosted","database":"ready","matching":"ready"}`.
6. Test registration, login/logout, admin authorization, inquiries, Smart Cart publication, a public Circle in an incognito window, and sandbox checkout before promoting the deployment to Production.
7. When adding a custom domain, append its exact HTTPS origin to `RIPPLE_ALLOWED_ORIGINS` and redeploy.

The Python Function initializes the idempotent schema under a Postgres advisory lock. Hosted sessions use `Secure`, `HttpOnly`, `SameSite=Strict`, `__Host-` cookies. The current Circle checkout remains a simulation and must not be presented as real payment processing.

## Local administrator

The local server creates this development-only account, but the login page does not publish or autofill it:

```text
Email: admin@ripple.local
Password: RippleAdmin!2026
```

Hosted Vercel deployments do not create this default. They use only private environment values. Override both values locally whenever other people can access the machine:

```bash
RIPPLE_ADMIN_EMAIL=admin@example.org RIPPLE_ADMIN_PASSWORD='replace-with-a-long-password1' python3 server.py
```

Passwords are stored as PBKDF2-HMAC-SHA256 hashes with per-user random salts. Session identifiers are random and stored only as hashes. Cookies expire after 12 hours, hosted cookies are `Secure`, and all authenticated writes require a per-session CSRF token. This remains prototype identity infrastructure; production launch still requires operational monitoring, recovery controls, and a security review.

## Prototype boundaries

This is not a live charity, marketplace, payment processor, repair certification, or verified impact system.

- All displayed missions and organizations are fictional samples.
- Intake submissions are private, local, and unverified.
- Simulated pledges do not request, charge, collect, hold, or transfer money.
- Circle checkout references are fictional sandbox records. There is no Visa gateway, authorization, settlement, refund, chargeback, or PCI-compliant payment environment.
- Smart Cart recommendations use local transparent rules against sample data. No production generative-AI model, live inventory, price, or partner feed is connected.
- No tax acknowledgment is issued.
- No ownership, asset condition, organization authority, need, repair skill, delivery, or educational outcome is verified.
- Do not enter serial numbers, passwords, confidential asset manifests, student records, or other sensitive data.

A real pilot should have a qualified charity or fiscal sponsor own the donation account, approvals, restricted-fund policy, reconciliation, and acknowledgments. RIPPLE should begin as the coordination and evidence technology—not as an unlicensed holder of charitable funds.

## Sensible production phases

1. Run one manually coordinated city-level pilot with a company, recipient, repairer, and qualified charitable steward.
2. Add reviewed organization accounts, role permissions, private files, email invitations, and audit logging.
3. Add device manifest import, NIST-aligned sanitization evidence, CPSC recall screening, and two-party custody events.
4. Integrate a charitable payment provider or fiscal sponsor; never build homegrown escrow.
5. Add tranche optimization and mission recommendations only after real operational data exists.

Useful external references for a future implementation include NCES school data, IRS Tax Exempt Organization Search, NIST SP 800-88 Rev. 2, CPSC recall data, and EPA-certified electronics recycler directories. Registry presence supports only the specific claim checked; it does not prove current need, authority, delivery, or impact.
