# USER_STORIES.md

# Epic 1 — Campaign Creation

## US-1.1 Create Campaign (P0)

**As a** marketer

**I want to** create a new campaign

**So that** I can generate marketing creatives for a product.

### Acceptance Criteria

- User can click "New Campaign"
- Campaign has a unique ID
- Campaign status is initialized
- Campaign dashboard opens

---

# Epic 2 — Product Import

## US-2.1 Import Product from URL (P0)

**As a** marketer

**I want to** paste my product URL

**So that** AI can understand my product automatically.

### Acceptance Criteria

- Accept Shopify URL
- Accept Amazon URL
- Accept any product page
- Extract title
- Extract description
- Extract product images

---

## US-2.2 Manual Product Input (P0)

**As a** marketer

**I want to** manually enter product information

**So that** I can generate campaigns without a product URL.

### Acceptance Criteria

- Product name
- Description
- Features
- Images
- Target audience (optional)

---

# Epic 3 — Product Understanding

## US-3.1 Analyze Product (P0)

**As a** marketer

**I want** AI to understand my product

**So that** all downstream marketing assets are relevant.

### Acceptance Criteria

Generate

- Product summary
- Key features
- Benefits
- Product category
- Brand tone

---

# Epic 4 — Research

## US-4.1 Generate Customer Insights (P0)

**As a** marketer

**I want** AI to identify customer pain points

**So that** campaigns resonate with the target audience.

### Acceptance Criteria

Generate

- Pain points
- Motivations
- Objections
- Emotional triggers

---

## US-4.2 Generate Target Persona (P0)

**As a** marketer

**I want** AI to create an ideal customer profile

**So that** messaging is personalized.

### Acceptance Criteria

Generate

- Persona name
- Demographics
- Goals
- Frustrations
- Buying motivation

---

# Epic 5 — Campaign Strategy

## US-5.1 Generate Campaign Strategy (P0)

**As a** marketer

**I want** AI to generate a campaign strategy

**So that** all creatives follow a consistent direction.

### Acceptance Criteria

Generate

- Campaign objective
- Positioning
- Marketing angles
- Messaging
- Value proposition

---

# Epic 6 — Hook Generation

## US-6.1 Generate Marketing Hooks (P0)

**As a** marketer

**I want** multiple hooks

**So that** I can test different creative approaches.

### Acceptance Criteria

Generate hooks for

- Curiosity
- Story
- Social proof
- Problem/Solution
- Authority
- FOMO

---

# Epic 7 — Script Generation

## US-7.1 Generate Scripts (P0)

**As a** marketer

**I want** AI to write ad scripts

**So that** I don't have to write them manually.

### Acceptance Criteria

Generate

- Testimonial
- Story
- Founder
- POV
- Product demo

Each script should include:

- Hook
- Body
- CTA

---

# Epic 8 — UGC Generation

## US-8.1 Generate UGC Ads (P0)

**As a** marketer

**I want** AI to generate multiple UGC ads

**So that** I have different creatives for testing.

### Acceptance Criteria

Generate

- 3–5 UGC videos
- Voice
- Avatar
- Captions

---

# Epic 9 — Creative Intelligence Engine

## US-9.1 Evaluate Every Creative (P0)

**As a** marketer

**I want** AI to review every generated ad

**So that** only high-quality creatives are delivered.

### Acceptance Criteria

Every ad receives

- Overall score
- Hook score
- Engagement score
- Brand consistency score
- CTA score
- Improvement suggestions

This evaluation loop is a core part of the product because Genblaze is designed to support agent loops that generate, evaluate, and retry until quality criteria are met. ([Backblaze][2])

---

## US-9.2 Improve Weak Creatives (P0)

**As a** marketer

**I want** weak creatives to be improved automatically

**So that** I receive optimized ads without manual iteration.

### Acceptance Criteria

If score is below threshold

AI should

- Rewrite hook
- Improve script
- Regenerate creative
- Re-evaluate

---

# Epic 10 — Campaign Packaging

## US-10.1 Generate Campaign Package (P0)

**As a** marketer

**I want** all campaign assets bundled together

**So that** I can launch my campaign immediately.

### Acceptance Criteria

Package includes

- Research report
- Campaign strategy
- Hooks
- Scripts
- Videos
- Captions

---

# Epic 11 — Asset Storage

## US-11.1 Store Campaign Assets (P0)

**As a** marketer

**I want** every generated asset stored automatically

**So that** I never lose campaign outputs.

### Acceptance Criteria

Store

- Videos
- Images
- Scripts
- Metadata
- Logs
- Campaign package
- Provenance manifest

This aligns directly with the hackathon's expectation that Backblaze B2 be used meaningfully for generated assets, metadata, and provenance rather than simply as a download location. ([Genblaze Hackathon][1])

---

# MVP Backlog (Implementation Order)

| Priority | User Story                 |
| -------- | -------------------------- |
| P0       | Create Campaign            |
| P0       | Import Product             |
| P0       | Product Understanding      |
| P0       | Customer Research          |
| P0       | Generate Persona           |
| P0       | Generate Campaign Strategy |
| P0       | Generate Hooks             |
| P0       | Generate Scripts           |
| P0       | Generate 3–5 UGC Ads       |
| P0       | Evaluate Creatives         |
| P0       | Improve Weak Creatives     |
| P0       | Generate Campaign Package  |
| P0       | Store Assets & Provenance  |
