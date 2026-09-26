# RIPPLE — session handoff

Updated: September 26, 2026

Workspace: `/Users/ved/Documents/ChatGPT/Ripple- Hackgt`

Primary artifact: [network.html](./network.html) · legacy planner: [index.html](./index.html)

## Latest implementation update

The root page is now the **live mission exchange** (`network.html` / `network.js`), backed by new signal, matching, and participant-consent endpoints in `server.py`. The earlier interactive planner remains at `/planner`. This is still a localhost-only pilot; nobody outside the computer running it can use it yet.

The working loop is implemented: any role can post first; the server matches mission area and location, checks same-unit quantity coverage, and checks whether a funding offer covers the quoted labor. It shows incomplete leads and their missing pieces. An owner of any selected listing can start confirmation with that listing's owner key. Each listing owner then sees only their own invitation in **Your invitations** and can review all four offers before accepting or declining for their role. The server records one final decision per role, reopens offers after a decline, and expires unanswered invitations after seven days. Owner keys are stored hashed, owner withdrawals are retained as events, and event rows cannot be edited or deleted through SQL. The public assembly board exposes only the mission title, location, and role decision status.

Trust boundary: entries remain unverified. Control of a listing's browser-stored key permits a response, but does not verify a real person, organization, asset, or funding source. The inbox is local; there is no external invitation delivery, account recovery, or independent identity check. No payments, goods movement, delivery proof, or measured impact are claimed.

Start with `python3 server.py` and open `http://127.0.0.1:4174/`. Add four test records only with clearly fictional names if demonstrating locally. Creating all four in one browser lets that browser simulate all four decisions; it does not demonstrate four independently identified people.

## Read this first

The user is a noncoder building a HackGT social-good project. They want us to do the technical implementation, explain it in plain language, and make it feel unusually ambitious and interactive. Their personal interests are entrepreneurship, philanthropy/social good, and helping people earn money through useful work. They do **not** want a conventional donor marketplace, a LinkedIn clone, a laptop-only charity app, or an idea that sounds impressive but has no reason for people to open it.

The current concept is **RIPPLE, an impact assembly engine**: one person or organization starts with a useful piece—an idle resource, paid skill, funding, or a locally stated need. RIPPLE builds a mission around that piece, exposes the missing links, compares possible ways to act, and creates a checkable brief. Laptops are one demonstration, not the product boundary. Food rescue, tutoring, and a custom planning board show broader scope.

The local full-stack prototype is working and visually polished. Its first screen now demonstrates a multi-contributor matching loop; the legacy planning prototype remains linked from the header. It is **not** a launched marketplace or a verified-impact system. Numerical outcomes in the planner are illustrative model assumptions, not field-tested predictions. No real people, companies, payments, or partner commitments are connected.

## How the idea evolved

1. The first proposal involved detecting fatigue-related reaction-time lapses through a short game. The user rejected it as personally uninteresting and unconvincing on adoption and sponsor fit.
2. The user explicitly named their interests: entrepreneurship, social good/philanthropy, and conversations about earning money. The concept shifted toward connecting underused resources, skilled workers, community need, and activation funding.
3. An earlier version, referred to as **Forge Fund**, used discarded company laptops as a concrete example. The user challenged its trust model, how anyone would discover the opportunity, whether it was just another LinkedIn, whether it was real technology, and whether it was too much like a business for a hackathon.
4. The concept became **RIPPLE**: an interactive mission-building tool where any of four contributors can start, with technical value in gap detection, scenario simulation, clear work scopes, and an evidence trail. The device example remains the easiest demo story.
5. The user then asked for a complete, market-quality-feeling build with a dramatic impact visual, clear interaction, and the important features actually implemented. This resulted in the interactive planner.
6. The user then clarified that they still could not understand how the four sides get onto RIPPLE or how a chain begins. The default page was changed to a persistent signal board: people post one piece, the backend matches and exposes gaps, and a proposed chain gathers role-by-role decisions. The local single-user planner remains at `/planner`.

The strongest fit among the sponsor prompts the user pasted is **Aramco Americas Social Good**: the mission can address education, climate/waste, food access, or local needs. The current build does **not** satisfy Meta's requirement that AI play a meaningful role, nor SpaceXAI's requirement to use Grok technology. Impiricus's HCP-engagement challenge is not a natural fit. This judgment is based on the prompts supplied in the conversation, not a fresh review of current event rules.

## The product in plain language

Imagine a company has equipment it no longer needs. That alone helps nobody. A technician could repair it, but has no project. A school knows students need devices, but cannot prepare them. A funder could cover the work, but does not know the exact gap. One person posts one real need or offer. RIPPLE stores it, compares it with the other open signals, shows what's missing, and—when the pieces fit—asks each role to agree to the same plan.

The same four-sided pattern can start from **any** role:

| Starter | What they enter | What the mission needs next |
| --- | --- | --- |
| Asset holder | What useful thing is available, quantity, timing, estimated usable share | Worker, funding, community partner |
| Skilled person | Type of work, available paid hours, proposed hourly rate | Resource, budget, community partner |
| Funder | Proposed activation budget and source | Resource, paid scope, community partner |
| Community partner | Local need, location, number of people/units affected | Resource, worker, funding |

This is the core differentiation from a one-off AI answer: the prototype maintains structured mission state and recalculates scenario tradeoffs as inputs change. The **future** defensibility would depend on real partner commitments and verifiable evidence; those do not yet exist.

### Problem hypothesis and adoption reality

The problem hypothesis is that useful social-good projects fail before they start because the right resource, operator, money, and local demand are fragmented across different people. That is a plausible framing, **not yet proven with interviews or measured data in this session**. RIPPLE's proposed first-use reason is immediate: “I have one useful piece; show me what else is needed and what a workable pilot could look like.” The prototype demonstrates that planning experience. It does **not yet** solve discovery—RIPPLE has no way to know a company is discarding laptops unless the company enters it, an approved integration supplies it, or an organizer finds it manually.

The initial deployment should therefore be a **small coordinated pilot**, not a claim that strangers will spontaneously fill a four-sided marketplace. Suggested outreach targets—not existing partners—are a campus IT or business asset owner, a local repair or logistics operator, a school/library/nonprofit, and a pilot funder. The anchor is the local organization that can define a real need and later check delivery; the app cannot invent one.

The user previously asked why people would trust the system and how it differs from “just asking AI.” The honest answer is that **trust is currently an unsolved product requirement**. A real RIPPLE would need identity and organization checks, proof of resource ownership, signed work scope, funding availability confirmation, chain-of-custody or service records, community-side confirmation, and a dispute process. A model-generated plan is not any of those things. The app's existing value is making a proposed mission structured, comparable, and explicit about missing proof—not authorizing anyone to send money.

## What is implemented today

- Root-page live board with separate community, resource, skilled-work, and funding entries; any one can start the matching process.
- SQLite persistence for signal records, hashed owner keys, assemblies, and append-only state-change events. A legacy invitation-token column remains for database compatibility but is no longer used for access.
- Server matching by mission area and city/remote scope, like-for-like quantity sufficiency, and labor-budget coverage; a match is explicitly only a planning fit.
- Unmatched offers are surfaced as leads instead of disappearing because no community need has been listed yet.
- Only an owner of one selected listing can start confirmation; the assembly starter receives no links that could answer for other roles.
- A local owner inbox shows each listing owner only that listing's invitations. The role-specific review shows the complete proposed plan and expected paid labor amount before accepting or declining.
- Public assembly summaries contain mission title, location, and role decision states rather than the full participant snapshot.
- All four role decisions are required to mark a proposed chain agreed. One decision is final; declines reopen the contributions; unanswered chains expire after seven days.
- Owners can withdraw their own unreserved signal using the high-entropy owner token stored locally; withdrawal is an event, not a hard delete.
- Local service remains loopback-only. No account system, external invitation delivery, identity verification, payments, or impact verification is represented as completed.

- A responsive, animated landing page with a live-looking impact network. Its four visual role labels are clickable entry points.
- An in-page guided tour and prominent complete-example shortcut.
- Four role-specific forms and four domain choices: devices, food, tutoring, and custom.
- A live mission map that marks each piece as added or missing; clicking a missing piece opens the relevant form.
- A gap engine that identifies missing roles, modeled full-route budget gaps, and skilled-hour shortfalls.
- Three distinct route comparisons per modeled domain. Users can prioritize balanced impact, faster reach, paid local work, or longer-lasting activity.
- A deterministic, browser-side scenario engine running 1,000 illustrative trials per route. It displays median reach, 10th–90th percentile ranges, paid hours, modeled cost, a five-point timeline, risks, and assumptions.
- Separate one-time device economics versus recurring weekly food/tutoring work and monthly budgets.
- A custom mission board for any other idea. It supports assembling roles, gaps, work scope, proof checklist, and export, but **does not invent a numerical forecast** for an unmodeled domain.
- A proof checklist that now labels entered claims as **draft** and completion claims as **self-reported/unverified**. It does not perform identity, ownership, funding, or delivery verification.
- A plain-text mission brief preview, copy action, and download.
- Browser-local saving, one-step draft recovery, and separate draft slots for each domain. No account is required.
- An optional localhost Python/SQLite API for explicit mission snapshots, separate view/edit tokens, and immutable revision history. The server is not internet-facing by default.
- Reduced-motion and responsive styling.

## How to use and demo it

For the live board, run `python3 server.py` in this folder, then open `http://127.0.0.1:4174/`. Add one signal from any role. To show the full matching workflow, enter a need for 20 laptops, a resource offer of 24 laptops, 10 hours of work at $30/hour, and a $300 funding offer. That demo is only illustrative; label those as sample entries. As an owner of any selected listing, click **Start confirmation**. Open **Your invitations** in the browser that created each listing to review and answer for that role. If one browser created all four fictional signals, it can simulate all four decisions; explain that this is a workflow demo. The legacy planner is at `http://127.0.0.1:4174/planner`.

For a first-time user: click **Try a complete example**. The four-piece device mission appears. Click **Skills**, change technician hours or rate, and press **Add work scope to mission**. The map and modeled outcomes update. Click a route to inspect its costs, paid work, risks, and assumptions. Switch to **Rescue useful food** to see that RIPPLE is not a laptop app. Choose **Something else entirely** to build a non-modeled mission. **Restore previous draft** recovers the prior mission after a switch or reset. The **How do I use this?** button opens a short tour.

Suggested 2–3 minute HackGT demonstration:

1. State the problem with the four disconnected people: resource owner, skilled worker, funder, and community partner.
2. Show an incomplete mission and click its missing pieces.
3. Load the complete example, then change paid hours or budget and show route outcomes move.
4. Change the priority to **Pay local workers** or **Last longer** and inspect the different top-scoring route.
5. Switch to food rescue to demonstrate the generalized pattern.
6. Open the proof checklist, export the brief, and optionally save a local server version. Say clearly that this is a **plan to validate**, not proof that impact already occurred.

## Code map

| File | Responsibility |
| --- | --- |
| [index.html](./index.html) | Page structure, accessibility labels, hero visual, builder, dialogs |
| [styles.css](./styles.css) | Responsive design, animation, dark hero, light mission studio |
| [engine.js](./engine.js) | Domain metadata and three illustrative seeded scenario models |
| [app.js](./app.js) | State, forms, role/template switching, gaps, rendering, storage, proof UI, export |
| [server.py](./server.py) | Localhost-only static server and validated SQLite mission API |
| [test_server.py](./test_server.py) | HTTP-level API/security tests |
| [network.html](./network.html), [network.css](./network.css), [network.js](./network.js) | Default live board, visual design, signal form, matching view, and owner invitation inbox |
| [README.md](./README.md) | Short run instructions and product summary |

The app uses no framework or third-party dependency. Ordinary edits are kept in `localStorage`. Pressing **Save mission to local server** explicitly sends a draft to the Python backend, which records versions in SQLite. A view-token link can reopen it on the same local server; the creator's edit token stays in that browser. This is not public sharing, identity verification, or secure production account management.

## Verification already done

- `node --check app.js`, `node --check engine.js`, and `git diff --check` passed after the most recent code changes.
- The site was opened in a browser at `http://127.0.0.1:4174/`. The desktop hero and builder were visually inspected; a narrow mobile viewport was also checked and reset.
- The complete example populated all four mission pieces and produced route outputs.
- Switching to food produced food-specific fields and route outputs; custom mode showed a planning board rather than a fake forecast.
- Changing a role's hours updated results. Switching domains and using **Restore previous draft** recovered the former mission.
- The proof UI was inspected after updating statuses so it no longer displays typed information as verified.
- A direct engine smoke test produced three routes in each template; default-route median outputs were 21/27/26 devices, 104/119/83 meals per week, and 26/38/29 students per week. These are **illustrative software outputs**, not social-impact claims.
- `python3 -m unittest -v test_server.py` passed all 15 HTTP integration tests, covering snapshots, signals, matching, owner-only assembly creation, role-scoped invitation access, withdrawal, expiry, and database migration.

There is no automated end-to-end test suite yet. The current browser preview may have a custom mission selected in its local storage; use **Try a complete example** or **Start blank mission** for a clean demo.

## Honest limitations and risks

1. **No external discovery or adoption loop:** the API can match signals after users enter them, but there are no live company inventories, skilled-worker listings, funders, or partner organizations. Finding the first participants remains a manual organizer task.
2. **Trust is still incomplete:** owner keys control listing actions, but typed inputs are not verified; anyone can enter a fictional organization or budget. A person with access to a browser or copied owner key can act for that listing. The proof trail is a checklist/self-report, not audit-grade proof. No escrow, payment transfer, identity check, organization vetting, delivery confirmation, or dispute process is implemented.
3. **Illustrative simulations:** coefficients were created for a hackathon demonstration, not calibrated with field data. The 1,000 trials demonstrate sensitivity and uncertainty *within the assumed model*, not an evidence-backed success probability for a real program.
4. **Custom missions are not automatically simulated:** a new domain needs its own outcome definition, cost structure, constraints, and local data. The planning board works now; a trustworthy forecast does not.
5. **Local-only persistence:** the new board stores data in SQLite on this computer. There is no cloud sync, public access, account, external invitation delivery, or owner-key recovery. The old planner still uses browser drafts and local snapshots. Browser-stored owner keys must be kept private.
6. **Not production-ready:** a local API now exists, but launching publicly still requires secure hosting, user accounts and permissions, abuse prevention, deeper accessibility testing, legal/compliance review for paid work and donations, privacy policy, operational ownership, and field validation.
7. **Copy/UX needs continued review:** the initial zero-output badge was changed to “ROUTE PREVIEW.” Continue checking that no copy suggests a route is validated or actionable without partners and resources.

Do not describe this prototype as a safe place to move money or as verified impact. Do not invent partners, case studies, measured social outcomes, or a claim of being the first company to build this.

## Sensible next steps

### Next phases

1. **Local matching and consent — implemented.** Four signal types, match/gap checks, owner-scoped inbox and responses, decline/reopen, expiry, and persistent records.
2. **Trust and evidence — partial local guardrails only.** The app distinguishes unverified offers, hashes owner keys, restricts assembly creation and each role's response to a selected listing owner, and records decisions. Next: verify organizations and asset ownership, provide external invitation delivery and key recovery, and define evidence reviewers and dispute handling with real partners.
3. **Remote pilot — not yet deployed.** Add secure accounts, HTTPS hosting, email delivery, moderation/abuse controls, privacy and retention settings, and a real community partner. This needs a hosting and identity-provider choice plus operational approval; the localhost app cannot be safely made public by merely opening a port.
4. **Prove the outcome — not implemented.** Add chain-of-custody or service evidence, community-side delivery confirmation, and follow-up outcomes before claiming impact.

For HackGT, demonstrate the local matching loop clearly, then ask one real community partner to validate whether the fields and proof steps make sense. Keep sample records labeled as samples.

### If continuing toward a real service

Start with a narrow, manually coordinated pilot in one city and one domain. Secure a real resource owner and community partner before building a full marketplace. Learn what documentation each side requires, what makes a paid worker trust a scope, and who will verify custody, service, and outcome. Only then add shared accounts, signed commitments, evidence records, matching/discovery, and payments. A general platform can be the long-term vision; the first proof should be one completed mission.

For any payment flow, use a regulated provider and proper legal review; do not build homegrown escrow or suggest that money held in this prototype is safe. If genuine organization and beneficiary data are gathered, a public version will also need permissions, privacy controls, retention rules, and abuse handling.

## Working style for whoever continues

- Speak to the user in direct, simple language. They repeatedly asked “what is this and how do I use it?”; show the action and outcome first, then explain the technology.
- The user asked us to build, not just propose. Make concrete changes and verify them before handing back advice.
- Keep the skilled person and paid work central. Avoid pitching RIPPLE as only a donor or charity app.
- Keep the universal mission idea visible. Laptops are an example, not the entire product.
- Preserve the difference between illustrative predictions, user-entered claims, self-reports, and independently verified evidence.
- Keep any future local data and user changes in this project intact while continuing the build.
