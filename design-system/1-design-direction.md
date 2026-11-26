# Design direction

**Mira looks like a precise, calm operations tool wrapped in a loud, unmistakable brand block.** The product UI follows *Swiss Modern* with *data-dense dashboard* rules; the brand layer borrows one controlled move from *neobrutalism* — the solid red block with a hard extruded edge from the logo — and uses it only in marketing, slides and the login screen.

## How the skills were used

| Skill | What it contributed | What we kept / changed |
| --- | --- | --- |
| design-trend-analyzer, design-system-generator | Matched "enterprise, operational, trustworthy, 8-hour daily use" to **Swiss Modern** (grid, whitespace, strict scale) and "brand you remember" to **Neobrutalism** (solid blocks, hard shadows) | Swiss Modern for product, neobrutal block for brand moments only |
| ui-ux-pro-max (`--design-system` for "B2B SaaS contact center dashboard") | Proposed Glassmorphism, trust blue #2563EB + orange CTA, Plus Jakarta Sans; style search returned **Data-Dense Dashboard** and **Bento grid** | **Rejected** glass and the blue/orange palette (generic, fights the red logo, blur hurts legibility on low-end agent PCs). **Kept** its checklist: 4.5:1 text, visible focus, 44 px targets, no emoji icons, reduced motion; data-dense rules for reports; bento grid for wallboards |
| design-system, design-system-creator | Three-tier tokens (primitive → semantic → component), OKLCH primitives, ≤8 spacing steps, documented usage on every token | Applied exactly — see Token architecture |
| design-system-documenter | "Document when to use a token, not just what it is"; do/don't; contrast tables | Every token carries a usage note; component pages have rules and don'ts |
| design-critic | 6-dimension rubric (accessibility, colour, type, layout, modernity, usability) | Scored v1 (below); v2 changes answer each low score |
| apple-design (HIG) | 44 pt touch targets, native call UI, Dynamic Type, safe areas, dark mode, avoid custom glass on non-Apple platforms | Mira Phone rules in Product patterns |
| design-justice | Calm error colours, no alarm states, plain language, shared-device privacy, intermittent connectivity | Terracotta `danger`, no flashing, shared-workstation and offline rules — see Accessibility and agent wellbeing |
| brand | Logo, palette, type, voice, consistency checklists | Logo rules, voice, trilingual copy |
| banner-design, slides | Sizes and layouts for social, ads, web, print; deck structure | Marketing and presentations section |
| design-archivist | Systematic competitor pattern capture | Started below with Ziwo; extend to Genesys, Talkdesk, Maqsam screens when building UI |

## Against Ziwo

What we could verify of Ziwo's presentation: a cloud CCaaS whose site runs in English, Arabic and French and sells on MENA presence, Arabic support, local hosting and integrations ([ziwo.io product page](https://www.ziwo.io/product/call-center-software/)). Its look is the common SaaS pattern: light pages, product screenshots, customer-logo walls, Material-style icons.

| | Ziwo | Mira |
| --- | --- | --- |
| Brand signal | Generic cloud-SaaS | One red block, warm bone neutrals — recognisable in a thumbnail |
| Languages | EN / AR / FR site | EN / AR / FR **product and IVR**, with an Arabic type family designed with the Latin one |
| Agent surface | Its own web app + plug-ins into CRMs | Works **inside ERPNext / Frappe CRM**: the call panel docks beside the customer record |
| Deployment story | Cloud | Cloud **and on your own servers** — the identity must look solid and "owned", not app-store playful |
| Calm under load | Not documented | Explicit rules: no flashing, terracotta errors, one red thing per screen |

## Critique of v1 (design-critic rubric)

| Dimension (weight) | v1 score | Finding | Fixed in v2 by |
| --- | --- | --- | --- |
| Accessibility (20%) | 80 | AA text pairs, but `danger` was a red almost identical to the brand | Terracotta `danger`; full contrast table for both themes |
| Colour harmony (15%) | 78 | Cohesive warm palette; no scales, so designers improvise tints | OKLCH primitive scales (red, green, amber, blue, clay, warm neutral) |
| Typography (15%) | 70 | Inter + IBM Plex Sans Arabic come from different families; no reading sizes | IBM Plex Sans + Plex Sans Arabic + Plex Mono (one family), reading styles added |
| Layout (20%) | 40 | No layouts or grids for any product surface | Product patterns: Desk, Phone, wallboard, Flow, reports |
| Modernity (15%) | 72 | Right tone, but only static colours and type | Component library with live previews, motion and size tokens |
| Usability (15%) | 45 | No components, states or call controls defined | Button, StatusPill, CallPanel, DialPad, KpiTile, TextField |
| **Overall** | **64 / 100 (Fair)** | A good brand start, not yet a design system | — |

v2 should be re-scored with the same rubric once the first real Mira Desk and Mira Phone screens exist; a self-score now would only grade our own intentions.
