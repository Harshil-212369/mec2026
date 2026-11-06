---
name: cloudflare-credits
description: Cost guard for H's Cloudflare Startup Program credits (Tier 3, $10,000). Use before creating, deploying, or configuring ANY Cloudflare product (Workers, Pages, R2, D1, KV, Workers AI, AI Gateway, domains), when choosing a Cloudflare product, or when asked whether something is covered by credits.
---

# Cloudflare credits: check coverage before you build

## The account (as of 2026-11-05; re-check the dashboard, numbers change)
| Item | Value |
|---|---|
| Account | H's Cloudflare account, the one with the startup credits (not the domain account) |
| Program | Cloudflare Startup Program, **Tier 3** |
| Credits | $10,000; 0% used on 2026-11-05 |
| Valid | Program start Jun 18, 2026, **expires Jun 18, 2027**. No extensions |
| Where to check | dash.cloudflare.com > Manage account > Billing > Credits |

## Coverage (source: cloudflare.com/startups FAQ, read 2026-11-05)
| Status | Products |
|---|---|
| **Covered by credits** | Workers, Workers for Platforms, Durable Objects, Workflows, Workers KV, D1, Queues, Vectorize, Pages, Images, Stream, Cache Reserve, Argo Smart Routing |
| **Covered with a cap** | **Workers AI: $2,500 cap for Tier 3** (open-source models; partner models billed at standard rates). R2: $10,000 cap (that is the whole balance) |
| **Free on every tier (no credit drawn)** | DNS, CDN, DDoS protection, SSL certificates, WAF (1,000 custom rules), 3 enterprise domains, Business/Pro plans, Load Balancing (2 origins), Rate Limiting (1 rule) |
| **NOT covered: bills H's card** | **AI Gateway** (temporarily excluded), **Registrar** (domain registration/renewal), Workers AI **partner** models, Enterprise add-ons (unless approved), Magic Transit, Spectrum, Dedicated IPs, China Network |
| **Needs a request to Cloudflare first** | Advanced Certificate Manager, SSL for SaaS, Advanced Rate Limiting, extra Load Balancing origins (email); Bot Management, API Shield, Apex Proxying, extra Zero Trust seats (support ticket) |

**Correction to an older note:** an August note said Workers AI credits go up to $50,000. That is the Tier 1 cap. **H is Tier 3: $2,500.**

## Before using any Cloudflare product, state in one line
`<product>: covered | capped at $X | NOT covered. At the limit it <fails | bills the card>.`
If it is **NOT covered**, stop and ask H. Do not proceed on "it's probably cheap".

## Rules when building
- Workers AI: open-source models only. Never partner or commercial models. Never AI Gateway.
- Set a CPU limit on every Worker in the committed `wrangler.toml`:
  ```toml
  [limits]
  cpu_ms = 50
  ```
- Deploy from committed config only, never from dashboard-only settings.
- R2: R2's cap is the entire balance. Keep uploads small, and for video prefer YouTube embeds over R2.
- Never buy or renew a domain from a session.
- For MEC this is Tier 2 work (AGENTS rule 7): only after the offline baseline is tagged and a teammate confirms it; keep an offline path for the demo.

## Connector note
The claude.ai "Cloudflare Developer Platform" connector describes itself as deprecated in favour of the Cloudflare API MCP server (`https://mcp.cloudflare.com/mcp`). It works for Workers/KV/R2/D1 today. If its tools fail, tell H instead of retrying.
