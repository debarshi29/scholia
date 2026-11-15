# Security

## Model

Scholia is a **local, single-user tool**. It is designed to run on your own machine and listen on localhost. It has **no authentication**, and **local profiles are not an access-control feature**: anyone who can reach the API can read and change anything. Do not expose the API or the dev server to a network, and do not run it on a shared host.

## What the design protects

| Asset | Protection |
|---|---|
| The answer key | Never returned by any endpoint a live session can call; returned by the debrief only after submit. Covered by a test over every live-session route |
| Your Gemini API key | Read from `.env` (git-ignored) into a secret value; never logged or returned |
| Your sessions and assistant logs | Stored in a local SQLite file; not sent anywhere |
| Third-party code | Sent to Gemini only if the project's licence is on the allowlist (MIT, BSD-2, BSD-3, Apache-2.0, ISC, PSF-2.0) |

## Known limits

- The `X-Profile` header is trusted as sent.
- Model output is parsed strictly, but source code and reports placed inside judge prompts are untrusted text, so a crafted file could attempt prompt injection against the judge. Matching (found or missed) is deterministic and unaffected; only quality scores could be skewed.
- The planted-bug corpus build **executes a cloned repository's doctests** with a timeout. Run it only for repositories you would run tests for. Tier 0 builds do not execute repository code.
- After you submit a fix to a planted-bug (algorithm) problem, grading **runs your edited file's doctests** in a scratch directory with a 20-second timeout. It is your own code on your own machine, but there is no sandbox (no memory, network or filesystem limits), so do not point the API at a network.
- There is no rate limiting or request-size hardening beyond field limits, because there is one local user.

## Supported versions

Only the current `main` branch is supported.

## Reporting a vulnerability

Please report privately. Open a [GitHub security advisory](https://github.com/debarshi29/scholia/security/advisories/new) on this repository, or contact the repository owner directly through their GitHub profile. Include the affected component, steps to reproduce and the impact. Please do not open a public issue for an unpatched vulnerability. You can expect an acknowledgement and a fix or mitigation plan on a best-effort basis.

## Hardening checklist if you adapt this for others

1. Add real authentication and per-user data separation (replace the profile header).
2. Move to a server database and per-user secrets.
3. Put the API behind TLS and a reverse proxy; restrict CORS and origins.
4. Run the planted-bug build and any future code execution in a sandbox.
5. Add rate limits and quotas for model calls.
