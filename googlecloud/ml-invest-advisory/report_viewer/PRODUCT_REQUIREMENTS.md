---
title: "Portfolio Report Viewer: Product Requirements Specification"
subtitle: "Version 0.1 (draft for review), 2026-11-14"
---

| | |
|---|---|
| **Product** | Portfolio Report Viewer (beta), the web front end of the ML Invest Advisory report pipeline |
| **Document status** | Draft for review |
| **Owner** | Hil Liao |
| **Code** | `googlecloud/ml-invest-advisory/report_viewer/` (viewer), `portfolio_reports/ollama_report_pipeline/` (reports) |
| **Scope** | F1, client sign-in and news-based portfolio reports (existing, beta). F2, export a report as a prompt to an AI assistant (new) |

# 1. Summary

The Portfolio Report Viewer lets clients of the managed investment portfolios sign in with their Google account and
read AI-generated reports about how the latest market news affects their own holdings. Reports are refreshed
continuously during US market hours. They combine real-time quotes for each portfolio with news and research,
with **Fundstrat as the primary market intelligence source** and CNBC, WSJ and global financial headlines as
supporting sources.

This document covers two things:

- **F1 (existing, beta):** sign-in and the report viewer as it is built today. It also covers one gap to close
  before clients use it: limiting each client to their own portfolios.
- **F2 (new):** an **Ask AI** button that exports the open report as a ready-made prompt for **Google Gemini** or
  **Meta AI**, so a client can ask follow-up questions in an AI assistant of their choice.

# 2. Background and problem

Each trading day, the report pipeline produces about 24 HTML reports: for every portfolio, one daily report plus one
"news" report per news source. Before the viewer, clients had to open each report's Cloud Storage URL
separately, with no overview of what was available or how fresh it was.

Clients also tend to have follow-up questions after reading a report, such as "What happens to my portfolio if NVDA
falls another 5%?" or "Explain the Fundstrat view on yields in plain language." The reports are static, so today
there is no way to explore them further.

# 3. Users

| Persona | Description | Main needs |
|---|---|---|
| **Portfolio client** | Owner of one or more managed portfolios (e.g. `vicky` and `vicky-tw-portfolio`). Reads reports on a laptop or phone, not necessarily technical. | Sign in easily. See only their own portfolios. Find today's most relevant report quickly. Ask follow-up questions. |
| **Portfolio manager / operator** | Runs the report pipeline and the viewer, and manages who can see what. | Control access per client. Know the reports are current. Keep client data from leaking. |

# 4. Goals and non-goals

**Goals**

1. A client reaches today's reports for their portfolios within one sign-in and one click.
2. A client can never see another client's portfolio.
3. A client can take any report into Gemini or Meta AI for Q&A in under 10 seconds, knowing exactly what data
   they are sharing.

**Non-goals for this release**

- A built-in chat inside the viewer, or calling the Gemini or Meta APIs from the server.
- Storing or syncing a client's AI conversations.
- Editing portfolios or placing trades.
- Changing how the reports are generated (prompts, model, schedule).

# 5. F1: Client sign-in and news-based portfolio reports (existing, beta)

## 5.1 Report content

The report pipeline (`run-market-hours.sh`) runs Monday to Friday, 08:00 to 18:00 America/New_York, excluding NYSE
holidays. That window starts about 1.5 hours before the market opens. On each pass it:

1. Fetches real-time quotes for every holding in each portfolio, including Taiwan-listed stocks converted to USD.
2. Combines the holdings with the latest news and research, and has a locally hosted LLM (Ollama,
   `gemma4:12b-it-qat` by default) write the reports.
3. Converts them to HTML and uploads them to `gs://hil-financial-services-smart-invest/reports/<portfolio>/`, one
   folder per portfolio.

**Report types** (one set per portfolio):

| Report | Content | Main input |
|---|---|---|
| **Daily report** | Portfolio performance snapshot, AI daily briefing, holding-by-holding commentary | Real-time quotes + the **Fundstrat Daily Technical Strategy** article of the day |
| **News**, one per news source | Breaking-news impact: key news, direct holdings impact, macro and sector channels, resilience vs. vulnerability, tactical action items | Real-time quotes + that source's news summary |

**News and research sources**

| Source | Role | Content used |
|---|---|---|
| **Fundstrat** (fundstratdirect.com) | **Primary market intelligence source** | **Flash Insights** posts. **Daily Technical Strategy**, the newest article each day, which also drives the daily report. **First Word macro analysis**, Tom Lee's macro strategy articles. |
| **CNBC** | Supporting: market news | Front-page headlines and stories |
| **WSJ** | Supporting: market and business news | Front-page headlines and stories |
| **Global headlines** | Supporting: broad market context | Combined headlines and teasers from Bloomberg, Financial Times, Yahoo Finance, MarketWatch, Investing.com and Barron's |

Every report ends with an **Input Prompt for LLM** section. It shows the exact holdings data and news text the
model was given, so a reader can check any statement against its source.

## 5.2 Viewer features (as built)

| ID | Feature | Description |
|---|---|---|
| F1.1 | Google sign-in | Clients sign in with their Google account (OAuth 2.0 authorization code flow with PKCE). The viewer requests only `openid`, `email` and read-only Cloud Storage access. |
| F1.2 | Access enforced by Cloud Storage | The server reads reports with the **signed-in client's own token** and holds no credentials of its own. Not signed in: **401** and a sign-in prompt. Signed in without access: **403**, naming the account. |
| F1.3 | Portfolio tabs | One tab per portfolio, with a report count. |
| F1.4 | Report tabs | Per portfolio: the daily report first, then the news reports by source (CNBC, Fundstrat, Fundstrat daily technical, Fundstrat macro analysis, Global headlines, WSJ). |
| F1.5 | Info bar | Upload time ("Updated 9 h ago", highlighted when older than 24 h), size, file name, **Reload**, and **Open in Cloud Storage ↗**. |
| F1.6 | Refresh list | Re-lists the reports to pick up new uploads; cached reports that were re-uploaded are reloaded. |
| F1.7 | Deep links | The URL keeps the selected report, so it can be bookmarked, and it survives the sign-in round trip. |
| F1.8 | Light and dark theme | Viewer and reports follow the device setting; printing stays black on white. |
| F1.9 | Keyboard and screen readers | WAI-ARIA tabs; ←/→/Home/End switch tabs. |
| F1.10 | Safe report display | Reports load in a sandboxed frame with a strict Content-Security-Policy: no scripts, no outbound requests. |
| F1.11 | Sign-out | Ends the session and revokes the Google token. Sessions otherwise end after about 1 hour. |
| F1.12 | Deployment | Python standard library only. Runs directly or as a container (`Dockerfile`, port 8081 for local testing). The OAuth client secret is mounted at run time, never stored in the image. |

## 5.3 Gap: clients must see only their own portfolios (required before client launch)

**Current behavior:** access is checked for the whole bucket. Any account with read access to
`gs://hil-financial-services-smart-invest/reports/` sees **every** portfolio's reports. That's acceptable while
only the operator uses the viewer, but not for clients.

**Requirement F1-R1:** a signed-in client sees, lists and can open only the reports of the portfolios assigned to
them. Requests for any other portfolio's report return **403**, even when the client types the URL directly.

**Acceptance criteria**

- Client A, assigned `vicky` and `vicky-tw-portfolio`, sees only those two portfolio tabs.
- Client A requesting `/reports/yang/daily-report-yang-llm-generated.html` gets 403. The response doesn't reveal
  whether that report exists.
- The operator can add or remove a client's access to a portfolio without redeploying the viewer.
- Access changes take effect within 5 minutes.

**Proposed approach (for design review)**

1. **Primary control in Cloud Storage.** The pipeline already uploads each portfolio's reports to its own folder,
   `reports/<portfolio>/…`. Each client's Google account gets read access to only their folders, using Cloud
   Storage managed folders with per-folder IAM. Because the viewer already uses the client's own token, Cloud
   Storage then enforces the rule with no change to the viewer's access logic.
2. **Defense in depth in the viewer.** An operator-maintained mapping from account email to portfolios also filters
   the report list and the report routes on the server.

**Done:** the pipeline uploads to per-portfolio folders, and the viewer lists the sub-folders and takes the
portfolio from the folder name.

**Still needed:**

- the managed folders and their IAM bindings
- listing each assigned folder separately. The viewer lists all of `reports/` in one request today. That request
  will probably fail with 403 for an account that can read only some folders (not verified).
- the server-side mapping from account to portfolios (item 2)

## 5.4 Known limitations of the beta

- **Google sign-in needs an approved address.** Google only allows plain `http://` sign-in on `localhost`, so any
  other address needs HTTPS and a domain, e.g. a reverse proxy, Tailscale, or Cloud Run with Identity-Aware Proxy.
- **Sessions are short.** They live in server memory and last about 1 hour. A server restart signs everyone out.
- **Dark mode needs fresh reports.** It applies only to reports generated after the style change of 2026-11-14.

# 6. F2: Export a report as a prompt to Google Gemini or Meta AI (new)

## 6.1 User stories

- As a **client**, I want to send the report I'm reading to Gemini or Meta AI with one click, so I can ask
  follow-up questions about my portfolio in plain language.
- As a **client**, I want to see exactly what data I'm about to share, and choose whether to include my raw
  holdings, before anything leaves the viewer.
- As the **operator**, I want the AI assistant to be told how to use the report, e.g. to cite it, say when
  something isn't in it, and avoid presenting answers as personal financial advice, so clients get grounded answers.

## 6.2 User experience

1. The info bar gets an **Ask AI ▾** button next to **Reload**, with these choices:
   - **Ask Gemini** (opens gemini.google.com)
   - **Ask Meta AI** (opens meta.ai)
   - **Copy prompt**
   - **Download prompt (.md)**
2. Choosing an option opens a **share dialog** that:
   - names the destination and states that the report's content will be shared with that service under the
     client's own account there
   - lists what is included: report text, portfolio name, report time, and optionally the source data
   - offers a checkbox, **Include source data (holdings and values, news text)**, off by default (see open
     question 2)
   - shows the prompt size in characters and approximate tokens
   - offers **Copy & open** and **Cancel**
3. On **Copy & open**, the viewer:
   - copies the prompt to the clipboard
   - opens the assistant in a new tab
   - shows a toast: "Prompt copied. Paste it into Gemini (Ctrl+V / ⌘V) and press Enter."
4. **Copy prompt** and **Download prompt** do the same without opening any site, for clients who use other
   assistants or the mobile apps.
5. If the clipboard is unavailable, the dialog shows the prompt in a read-only text box with **Select all**, and
   the client copies it by hand.

**Why copy-and-paste rather than a pre-filled link:**

- To the author's knowledge, neither assistant documents a supported way to pre-fill a prompt through a link. This
  needs confirming; see open question 4.
- A typical report prompt (15,000 to 40,000 characters) is far longer than links reliably support.
- The clipboard approach works the same for both assistants and for any future one.

## 6.3 Prompt content

The prompt is plain text in Markdown, assembled from these parts in order:

1. **Instructions to the assistant**:
   - "You are helping the owner of this investment portfolio understand the report below."
   - "Base your answers on the report; quote or name the section you use."
   - "Say clearly when a question can't be answered from the report."
   - "Separate facts from the report from your own general knowledge."
   - "This is information, not personal financial advice."
   - "Wait for my first question."
2. **Report metadata**: portfolio, report type and news source, generation time with time zone, upload time.
3. **Report body**: the report's text converted from HTML to Markdown, keeping headings, lists and tables.
4. **Source data** (only if the client ticks the box): the report's **Input Prompt for LLM** section, with the
   holdings data and news text.
5. **Closing line**: "Ask me what you'd like to know about this report."

**Requirements**

| ID | Requirement |
|---|---|
| F2.1 | The prompt is built on the server by a new route, `GET /api/reports/<portfolio>/<file>/prompt?include_source=0\|1`. The route applies exactly the same sign-in and access checks as `/reports/<portfolio>/<file>`, including F1-R1. |
| F2.2 | Without `include_source=1`, the prompt contains no holdings data, share counts or dollar values except what the report body itself states. |
| F2.3 | The prompt never contains anything outside the report: no session data, tokens, email address, file paths, or other portfolios. |
| F2.4 | The instructions block is a template file the operator can edit without changing code. |
| F2.5 | Prompts over a configurable limit (default 100,000 characters) show a warning with the size, and the client can still copy them. |
| F2.6 | The viewer makes no network calls to Google Gemini or Meta. It only opens their public sites in a new tab (`noopener`, `noreferrer`). No API keys are involved. |
| F2.7 | The server logs export events (time, account, report file, destination, source data included yes or no) but never the prompt content. |
| F2.8 | The share dialog is keyboard-operable and screen-reader friendly, and works at phone width. |
| F2.9 | The feature can be switched off, or limited to certain destinations, with configuration, e.g. `AI_EXPORT_DESTINATIONS=gemini,meta,copy`. |

## 6.4 Acceptance criteria

- Signed in as a client with access, choosing **Ask Gemini** on any report:
  - copies a prompt starting with the instructions block and containing the full report text
  - opens gemini.google.com in a new tab
  - pasting the prompt there produces an assistant reply that acknowledges the report and waits for a question
- With **Include source data** unticked, the prompt contains no ticker share counts and no lines from the
  **Input Prompt for LLM** section.
- Requesting the prompt route for a portfolio the client can't access returns 403 (F1-R1). Requesting it without a
  session returns 401.
- **Ask Meta AI** behaves the same with meta.ai.
- **Download prompt** saves `<report name>-prompt.md` with the same content.
- With clipboard access blocked, the manual-copy fallback appears.
- Unit tests cover prompt assembly, the include and exclude rule, and the access checks of the new route.

## 6.5 Privacy and risk

| Risk | Mitigation |
|---|---|
| Portfolio data leaves Google Cloud for a third-party AI service. Its retention and model-training terms depend on the client's account type, e.g. consumer vs. Workspace. | The client starts every export explicitly. The dialog names the destination and the data. Source data is off by default. The operator can disable destinations (F2.9). Exports are logged without content (F2.7). |
| The AI assistant gives inaccurate or overconfident answers. | The instructions block requires grounding in the report and a clear "not in the report" answer. The UI shows a short disclaimer next to the button. |
| Clients read assistant answers as personal investment advice. | The instructions and the UI disclaimer say the answers are informational. **Open question 3:** the wording should be reviewed by qualified counsel or compliance before launch. |
| The reports contain summaries of subscription research (Fundstrat), and exporting them to third-party AI services may raise content-licensing questions. | **Open question 5:** review the content subscription terms before launch. Source data (the raw news text) is off by default. |

# 7. Non-functional requirements

| Area | Requirement |
|---|---|
| Security | The existing controls stay in place: no server-side credentials, strict CSP, `HttpOnly`/`SameSite` session cookies, `Secure` cookies over HTTPS. Client deployments must use HTTPS. The OAuth client secret comes from a secret store or a mounted file, never from the image or git. |
| Privacy | Collect only the minimum (`openid`, `email`, read-only Cloud Storage). Logs contain no report content or prompts. |
| Performance | Report list in under 2 s and a report in under 1 s (p95) once signed in. Prompt ready to copy in under 1 s. |
| Availability | Best effort during the pipeline window (Mon to Fri, 08:00 to 18:00 ET); no formal SLA during beta. |
| Compatibility | Current Chrome, Edge, Safari and Firefox on desktop and mobile. The clipboard needs a secure context (HTTPS or `localhost`). |
| Accessibility | WCAG 2.1 AA for the viewer and the share dialog. |
| Maintainability | Python standard library only. Unit tests run with `python3 -m unittest`. |

# 8. Success metrics

- **Adoption:** share of clients who sign in at least 3 trading days a week.
- **Freshness:** share of report views where the report is less than 2 hours old during market hours.
- **F2 usage:** exports per active client per week, split by destination and by source data on or off.
- **Quality:** client feedback on assistant answers (e.g. a periodic thumbs-up or thumbs-down survey).
- **Security:** zero cross-client access incidents. Every 403 is logged and reviewed during beta.

# 9. Release plan

| Milestone | Content | Exit criteria |
|---|---|---|
| M1: per-client access (F1-R1) | Managed-folder IAM on the existing per-portfolio folders, per-folder listing, server-side mapping, tests | Acceptance criteria in 5.3 pass. Each client sees only their own tabs. |
| M2: HTTPS deployment | Public HTTPS address (e.g. Cloud Run + IAP, or an OCI VM with a TLS proxy) and secret from a secret store | Clients sign in from their own devices. |
| M3: Ask AI (F2), internal | Prompt route, share dialog, Gemini and Meta AI destinations, copy and download, logging, tests | Acceptance criteria in 6.4 pass with operator accounts. |
| M4: client launch | Disclaimer wording reviewed (open question 3), content terms checked (open question 5), client onboarding | Open questions 2, 3 and 5 resolved. |

# 10. Open questions

1. **Portfolio assignment source:** who maintains the account-to-portfolio mapping, and where? Options are IAM on
   managed folders alone, or IAM plus a config file in the bucket.
2. **Source data default:** should **Include source data** be on by default for better answers, or off to minimize
   what is shared? This draft proposes off.
3. **Disclaimer wording:** the wording in the reports, the viewer and the AI instructions block, and any
   obligations that come with giving clients AI-generated portfolio commentary, should be reviewed by qualified
   counsel or compliance. This document makes no determination on them.
4. **Pre-filled links:** do Gemini or Meta AI now offer a supported link format that pre-fills a prompt? If so,
   short prompts could skip the paste step. Not verified for this draft.
5. **Research content terms:** do the Fundstrat subscription terms, and those of other sources, allow summaries
   to be shared with clients and exported to third-party AI services?
6. **Destination naming:** this draft says "Meta AI" (meta.ai) for Meta's assistant. Confirm the current product
   name and URL, including whether "Muse" refers to the assistant or the model behind it.
7. **Session length:** is the current 1-hour session acceptable for clients, or should longer sessions with
   refresh tokens be added (more convenient, but more sensitive tokens to store)?

# Appendix A: Current viewer routes

| Route | Access | Purpose |
|---|---|---|
| `GET /` | Public (no report data) | Tab UI |
| `GET /api/reports` | Signed in | Reports grouped into tabs, plus the signed-in account |
| `GET /reports/<portfolio>/<file>` | Signed in | One report's HTML |
| `GET /auth/login`, `GET /auth/callback` | Public | Google sign-in |
| `POST /auth/logout` | Signed in | Sign out and revoke the token |
| `GET /api/reports/<portfolio>/<file>/prompt` | Signed in (**new, F2.1**) | AI export prompt |

# Appendix B: Report file naming

Each portfolio has its own folder, and every file name ends with the portfolio name:

- `reports/<portfolio>/daily-report-<portfolio>-llm-generated.html`
- `reports/<portfolio>/news-<source>-<portfolio>-llm-generated.html`

For example:

- `reports/yang/daily-report-yang-llm-generated.html`
- `reports/vicky-tw-portfolio/news-fundstrat-daily-technical-vicky-tw-portfolio-llm-generated.html`

Use cases: `daily-report`, `news`. Sources (`fetch-news.sh --site` keys): `fundstrat-flash-insights`,
`fundstrat-daily-technical`, `fundstrat-macro-analysis`, `cnbc`, `wsj`, `aggregate`. The viewer takes the portfolio
from the folder name. Files directly under `reports/`, from the old flat layout, aren't listed.
