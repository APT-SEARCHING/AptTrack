# AptTrack Dogfood Paper-Cut Log

**Period**: 2026-04-18 → 2026-05-02 (2 weeks)  
**Purpose**: Capture first-person UX friction daily. Drives Phase 3 re-prioritization at Week 2.  
**Rule**: Log it the moment you feel it. Memory degrades fast.

---

## Summary (update manually each session)

| Severity | Count |
|----------|-------|
| S1 — blocks me | 0 |
| S2 — annoys me | 1 |
| S3 — idea/wish | 0 |
| **Total** | **1** |

| Category | Count |
|----------|-------|
| Alert delivery | 0 |
| UX / navigation | 1 |
| Data quality | 0 |
| Performance | 0 |
| Other | 0 |

**Week 2 re-prioritization decision**: _(fill in after 2026-05-02)_

---

## How to add an entry

Copy the template below, prepend it to the **Entries** section (newest first), and update the summary table.

```
### [YYYY-MM-DD HH:MM] Title
- **Page/context**:
- **What happened**:
- **Severity**: S1 / S2 / S3
- **Category**: Alert delivery / UX / Data quality / Performance / Other
- **Phase**: Phase 3 / Phase 4 / Phase 5 / Later
- **Notes** _(optional)_:
```

---

## Entries

<!-- newest first -->

### [2026-04-20] Email-only alert subscription (no registration required)
- **Page/context**: AlertsPage / subscription creation flow
- **What happened**: Registration friction — users must create an account before they can subscribe to a price alert. Ideally a visitor could just enter their email on a listing page and start receiving alerts.
- **Severity**: S2
- **Category**: UX / navigation
- **Phase**: Phase 4
- **Notes**: Not a one-liner. Requires: (1) add `email` column to `PriceSubscription`, make `user_id` nullable; (2) subscription creation endpoint accepts bare email, no JWT; (3) email verification or rate-limit per email to prevent abuse; (4) `AlertsPage` replaced/supplemented by a magic-link "manage my alerts" flow (same pattern as existing `unsubscribe_token`); (5) price checker reads `email` from row directly. The `unsubscribe_token` mechanism already exists and is the right model to extend.

---

### [2026-04-18 09:15] Example — Alert email has no apartment name in subject line
- **Page/context**: Gmail inbox, alert trigger email
- **What happened**: Subject reads "Price drop alert #7" — no apartment name, no price. I have to open the email to know if it's worth reading.
- **Severity**: S2
- **Category**: Alert delivery
- **Phase**: Phase 4 (email template rewrite is already in Phase 4 scope)
- **Notes**: Ideal subject: "Miro — 1BR A2 dropped to $2,850 (was $3,100)"

---

### [2026-04-18 10:30] Example — AlertsPage shows "Apartment #12" not the name
- **Page/context**: AlertsPage, subscription list
- **What happened**: Every row says "Apartment #12", "Apartment #5". I have no idea which complex is which without clicking through.
- **Severity**: S2
- **Category**: UX / navigation
- **Phase**: Phase 4 (already tracked in active tech debt)
- **Notes**: Quick fix — JOIN on apartments table in the subscriptions endpoint and return title.

---

### [2026-04-18 14:00] Example — No way to see if the daily scrape actually ran
- **Page/context**: Anywhere — no status page
- **What happened**: Prices feel stale but I can't tell if today's scrape ran successfully or silently failed.
- **Severity**: S3
- **Category**: Data quality
- **Phase**: Phase 4 (ScrapeRun observability table is Phase 4)
- **Notes**: Even a "Last updated: 2 hours ago" timestamp on ListingDetailPage would help.
