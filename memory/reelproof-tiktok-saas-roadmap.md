# Design: ReelProof TikTok SaaS Roadmap

Generated: 2026-07-24  
Status: DRAFT  
Mode: Startup validation

## Product position

ReelProof should not become a generic AI video maker. TikTok, CapCut, and
existing tools already cover basic generation, scripting, editing, remixing,
captions, localization, and scheduling. ReelProof's wedge is a **creative
refresh system for TikTok Shop merchants**:

> Turn one SKU and one commercial hypothesis into several TikTok-native
> creative tests, keep them compliant and on-brand, track fatigue, and make the
> next batch from what worked.

The initial buyer is a TikTok Shop merchant or small performance agency that
runs paid TikTok Shop ads and has a recurring need for fresh creative. The
economic user is the person accountable for creative volume, ad fatigue, and
weekly GMV—not an individual creator looking for a fun one-off video.

## Market evidence

1. TikTok's own current guidance calls for 3–5 unique creative assets per ad
   group and regular refreshes when fatigue appears. This is recurring work,
   not a one-time generation problem.
   - https://ads.tiktok.com/business/library/Web_Auction_Best_Practices_Guide.pdf
   - https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en

2. TikTok Shop's current advertising flow is commerce-first: GMV Max is the
   default Shop-ads path, supports up to 50 videos per ad group, and relies on
   product-link creative. That makes creative production tied directly to a
   buyer's revenue workflow.
   - https://ads.tiktok.com/help/article/getting-started-video-shopping-ads
   - https://ads.tiktok.com/help/article/add-product-links-tiktok-videos

3. Generic production is crowded. TikTok Symphony generates/remixes videos,
   scripts, translations, and edits from product information or URLs; CapCut's
   commerce product and tools such as OpusClip already sell editing, captions,
   scheduling, and repurposing. OpusClip's $15–$29 monthly creator pricing is
   a useful warning: generic editing has a low willingness-to-pay ceiling.
   - https://newsroom.tiktok.com/symphony-creative-studio?lang=de-DE
   - https://www.opus.pro/pricing

4. TikTok provides first-party demand signals through Creator Search Insights
   and Creative Center. Search-gap topics, regional trends, top ads, keyword
   insights, and creative patterns should inform the brief; do not scrape or
   pretend to own those signals.
   - https://newsroom.tiktok.com/creator-search-insights?lang=en
   - https://ads.tiktok.com/help/article/creative-center?lang=en

## What ReelProof already has

- Topic/product-image input, 9:16 slideshow and POV outputs
- Captions, music, optional narration, download-ready assets
- Self-healing visual quality loop
- Durable asset provenance and verify view
- Reliable background jobs and replayable progress events

Those are a strong production engine. They are not yet the reason a merchant
will pay every month. The roadmap below converts the engine into a recurring
TikTok commerce workflow.

## Build next: demand-validation feature set

### 1. Creative Test Pack — P0

**Job:** Generate a weekly batch of 3–5 materially different ads for one SKU,
not five cosmetic rewrites of the same video.

Inputs: SKU/product page, offer, target country, target audience, objective,
and optional creator footage/product assets.

Outputs: five labeled hypotheses such as problem→solution, product demo,
objection handling, before/after, and offer/urgency. Every asset carries a
different hook, opening frame, proof type, CTA, caption, and visual plan.

Why it matters: it maps exactly to TikTok's stated need for creative diversity
and refresh cadence. This is the first feature to sell.

### 2. TikTok Opportunity Brief — P0

**Job:** Decide what to make before spending generation credits.

For a country/category, turn permitted first-party inputs—Creator Search
Insights topics/content gaps, Creative Center examples, and a merchant's own
product facts—into a ranked creative brief. Each recommendation must cite its
source, explain the audience intent, and produce an editable hypothesis.

Do not build an unauthorized trend scraper. Start with creator-provided exports,
URLs, or screenshots plus links back to TikTok's tools.

### 3. Product and Offer Truth Layer — P0

**Job:** Keep AI creative tied to the SKU that actually converts.

Create a product record with benefits, ingredients/specifications, price,
promotion, inventory caveats, approved claims, prohibited claims, product-link
instructions, and brand assets. The generator may only make claims present in
this record.

Why it matters: generic generators hallucinate benefits; commerce advertisers
need usable creative, not attractive fiction.

### 4. TikTok Commerce Readiness Check — P0

**Job:** Stop unusable creative before it reaches Ads Manager.

Add checks for 9:16, 720p+, safe zones, first-three-second proposition, legible
captions, product visibility, CTA/offer consistency, product-link instructions,
and approved commercial audio. Business accounts need commercially cleared
music; generated background music must not be presented as automatically
commercially cleared.

Reference: https://ads.tiktok.com/help/article/creative-best-practices
and https://ads.tiktok.com/help/article/how-to-use-the-commercial-music-library?lang=en

### 5. Creative Experiment Ledger — P0

**Job:** Remember what was tested and stop regenerating the same idea.

Persist SKU, hook, hypothesis, creative type, audience, offer, render version,
TikTok upload/ad ID, and outcome. Start with CSV upload from Ads Manager or
manual metrics entry. This should answer: "Which hook/proof/CTA deserves the
next five variants?"

This is the bridge from ReelProof's existing provenance to commercial learning.

## Add only after paid pilots prove the workflow

### 6. Fatigue and Refresh Planner — P1

Detect declining CTR/CVR/ROAS or user-marked fatigue, then create the next
creative pack that changes the weak variable rather than rebuilding everything.
TikTok explicitly recommends refreshes as fatigue appears. Do this only after
the experiment ledger has real outcome data.

### 7. Creator-Footage Remix — P1

Accept raw creator/affiliate footage and make compliant variants: new hook,
product sequence, captions, CTA, localized VO, and B-roll. TikTok's own
guidance favors native, human/creator-led creative; a faceless-only generator
will miss many high-intent Shop buyers.

### 8. TikTok Shop Campaign Package — P1

Export a package per creative: MP4, caption, hashtags, product-link selection
instructions, approved claims, creative ID, and campaign naming. Later, connect
the Shop/catalog and Ads Manager after a buyer proves they use this weekly.

### 9. TikTok Draft Export / Direct Post — P2

Use TikTok's official Content Posting API to send a draft or, with explicit
creator consent, post directly. This is convenience, not the core product;
TikTok requires app audit before unaudited clients can post publicly.

Reference: https://developers.tiktok.com/products/content-posting-api

### 10. Agency Review and Approval — P2

Add a brand/agency approval queue, locked claim library, client comments, and
an immutable export record. Build this only if agencies become the paying user.

## Explicitly do not build now

- A general-purpose timeline editor, caption editor, or cross-network scheduler
- Talking AI avatars or a broad influencer/creator marketplace
- Autonomous trend scraping or a promise to predict virality
- A generic analytics dashboard without a test-hypothesis model
- Provenance as the primary marketing message for creators; retain it as trust,
  compliance, and agency differentiation

## Recommended validation offer

Sell a concierge pilot before turning this into a broad SaaS:

"Every week, give us one TikTok Shop SKU and your offer. We deliver five
creative hypotheses, five TikTok-ready assets, a compliance checklist, and a
next-week recommendation based on your results."

Target five merchants/agencies already spending on TikTok Shop ads. Charge for
the pilot rather than collecting waitlist signups. A useful pass threshold is
three paid pilots that each request a second weekly batch. If users only want
one-off videos, do not build the SaaS roadmap; that demand belongs to the
commodity creator-tool category.

## Approaches considered

### A. Generic TikTok generator

Effort: Small. Risk: High.

Fast to ship, but it directly competes with TikTok Symphony, CapCut, and low
priced AI editors. It does not explain recurring payment.

### B. TikTok Shop Creative Refresh OS — Recommended

Effort: Medium. Risk: Medium.

Uses ReelProof's current engine to create test packs, keep product claims true,
record outcomes, and automate the next creative-refresh decision. It is tied to
an economic user and a recurring cadence.

### C. Agency provenance/compliance suite

Effort: Large. Risk: Medium.

Could become valuable to regulated brands, but it has slower sales cycles and
does not validate the immediate TikTok Shop creative problem quickly.

## Success criteria

- At least 3 of 5 paid pilots renew for a second weekly creative batch.
- Each active pilot uploads or runs at least 3 assets per week.
- At least one pilot uses the experiment ledger to request a specific next
  variant based on result data rather than asking for "more videos."
- Users describe the product as a way to keep ads fresh or test creative, not
  merely as an AI video generator.
