# Scraper Bug Log

Open issues found during dogfood. Fix together in a batch.

---

## BUG-01: universal_dom picks up deposit as rent price

**Status**: open  
**Affected**: Camden Village (id=244) — `$1,000` shown instead of `$2,055/mo`  
**Root cause**: `_PRICE_RE = re.compile(r"\$\s*([\d,]{3,6})")` in `universal_dom.py` matches
the first `$` it finds. Camden Village HTML layout is:
```
Deposit: $1000   $2,055 per month
```
The deposit `$1000` appears before the rent, so it wins.  
**Fix**: Before running `_PRICE_RE`, strip `Deposit[:\s]+\$[\d,]+` from the card text.
Alternatively, prefer prices followed by `/mo` or `per month` over bare amounts.  
**File**: `backend/app/services/scraper_agent/platforms/universal_dom.py` — `_extract_unit_from_card()`

---

<!-- Add new bugs below this line -->
