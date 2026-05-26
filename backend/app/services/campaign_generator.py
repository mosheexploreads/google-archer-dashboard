"""
Campaign generator service.

Flow per ASIN:
  1. Check attribution_link_cache table → reuse cached URL
  2. If not cached: call Archer /generate_attribution_link → save to cache
  3. Get product name from Archer /get_single_product (if not supplied by user)
  4. Call Claude to generate ad copy (keywords, headlines, descriptions)
  5. Persist result to CampaignJobItem

500+ ASINs processed concurrently (ThreadPoolExecutor, 5 workers).
Job state is DB-backed so it survives Railway restarts.
"""
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from anthropic import Anthropic

from ..config import get_settings
from ..database import SessionLocal
from ..models import AttributionLinkCache, CampaignJob, CampaignJobItem
from .archer_client import ArcherClient

logger = logging.getLogger(__name__)

_CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
_MAX_WORKERS = 5

# ── Claude prompt (ported verbatim from amazon-ads-automation) ─────────────

_POLICY_RULES = """\
GOOGLE ADS POLICY COMPLIANCE (critical - violations cause disapprovals):

NEVER use these words or phrases:
- Medical/disease claims: "cure", "cures", "treats", "treatment", "heals", "prevents disease", "fights cancer", "eliminates"
- Clinical language: "clinically proven", "medically tested", "doctor recommended", "FDA approved", "pharmaceutical"
- Unrealistic promises: "miracle", "magic", "instant results", "guaranteed results", "100% effective", "works immediately"
- Superlatives without proof: "#1", "best in the world", "most powerful", "strongest ever"
- Urgency manipulation: "act now or else", "last chance forever"
- Prohibited health claims for supplements: do not say a supplement diagnoses, cures, treats, or prevents any disease

ALWAYS use these safe alternatives instead:
- Use "supports" instead of "treats" (e.g. "supports immune health" NOT "treats immune issues")
- Use "promotes" instead of "cures" (e.g. "promotes wellness" NOT "cures illness")
- Use "may help" or "helps maintain" for gentle benefit claims
- Use "daily wellness routine", "everyday support", "as part of a healthy lifestyle"
- Focus on ingredients, quality, formulation, and general wellbeing
- For supplements: describe ingredients and general support, not medical outcomes
- Use "shop", "explore", "discover", "get" instead of aggressive CTAs
- Superlatives are OK when qualified: "one of the top-rated", "highly reviewed on Amazon"
"""

# ── Branded keyword campaign prompt ───────────────────────────────────────────
_BRAND_PROMPT_TEMPLATE = """\
You are a Google Ads expert specializing in Amazon affiliate marketing.

Product: {product_name}
ASIN: {asin}

Generate a complete Google Ads campaign for this product. Focus on BRANDED keywords only (using the brand name from the product).

EXAMPLE FORMAT (follow this style):
Campaign: Resilia Softgels with Black Seed Oil
Keywords: "resilia oregano oil", "resilia immune support", [resilia oil of oregano], [resilia oregano capsules], "resilia 6000mg oregano", [resilia black seed oil], "resilia softgels", [resilia oregano and black seed oil], [resilia 6000mg]
Headlines: Resilia Black Seed & Oregano, Official Resilia Wellness, Resilia 6000mg Softgels, Resilia Oil of Oregano Store, Potent 6000mg Herbal Blend, Immune & Digestive Support, Support Your Immune Defense, Promote Digestive Balance, Natural Seasonal Support, Herbal Gut Health Support, Resilia Oil On Amazon, Resilia Softgels On Amazon, Resilia Wellness On Amazon, Organic Oil of Oregano, Official Resilia on Amazon
Descriptions: Potent 6000mg blend of organic oregano oil and black seed oil for daily immune support., Support your digestive balance and gut health with easy-to-take, non-GMO herbal softgels., Experience premium immune defense with Resilia. No strong taste and no herbal aftertaste., Formulated for microbial balance and seasonal wellness. Trusted herbal support in 60ct.

Provide your response in the following exact format:

CAMPAIGN_NAME: [Product name - keep it simple and branded]

KEYWORDS:
"brand keyword 1"
"brand keyword 2"
[brand keyword 3]
[brand keyword 4]
"brand keyword 5"
[brand keyword 6]
"brand keyword 7"
[brand keyword 8]
[brand keyword 9]
... (generate 9 keywords total - mix of "exact match" with quotes and [phrase match] with brackets)

HEADLINES:
Brand + Product Attribute
Official Brand Name
Brand Product Specs
Brand Product On Amazon Store
Product Benefit 1
Product Benefit 2
Product Benefit 3
Product Benefit 4
Product Benefit 5
Product Feature Highlight
Brand On Amazon
Brand Product On Amazon
Official Brand on Amazon
... (generate 12-15 headlines total)

DESCRIPTIONS:
Detailed benefit description mentioning key specs and product attributes.
Another benefit focusing on quality, certifications, or unique selling points.
Third benefit emphasizing trust, results, or product formulation details.
Fourth benefit if applicable focusing on use case or additional features.

RULES:
- Keywords: 9 total, all branded, mix of "exact match" (quotes) and [phrase match] (brackets)
- Roughly 40% exact match, 60% phrase match
- Headlines: 12-15 total, MAXIMUM 30 characters each (strict limit!)
- Descriptions: 4 total, MAXIMUM 90 characters each (strict limit!)
- Use brand name in most keywords and many headlines
- Include "on Amazon" variations in headlines
- Focus on benefits, specs, and trust factors
- Match the style of the example above

""" + _POLICY_RULES

# ── Amazon category keyword campaign prompt ───────────────────────────────────
_AMAZON_PROMPT_TEMPLATE = """\
You are a Google Ads expert specializing in Amazon affiliate marketing.

Product: {product_name}
ASIN: {asin}

Generate a complete Google Ads campaign targeting shoppers searching for this PRODUCT CATEGORY on Amazon.
DO NOT use any brand-specific keywords. Target generic category searches — every keyword MUST include the word "amazon".

EXAMPLE (for "Resilia Softgels with Black Seed Oil"):
Campaign: Black Seed Oil Supplement
Keywords: "black seed oil amazon", [black seed oil capsules amazon], "oregano oil amazon", [oregano oil capsules amazon], "black seed oil supplement amazon", [buy black seed oil amazon], "oil of oregano amazon", [herbal immune supplement amazon], "black seed supplement amazon"
Headlines: Black Seed Oil on Amazon, Shop Oil of Oregano, Buy Black Seed Capsules, Top Black Seed Amazon, Oregano Oil on Amazon, Herbal Supplement Amazon, Shop Herbal Oils Amazon, Black Seed Oil Store, Oregano Capsules Amazon, Shop on Amazon
Descriptions: Shop top-rated black seed oil supplements with fast delivery on Amazon., Find premium oregano oil capsules and herbal immune support on Amazon., Browse quality herbal supplements at great prices on Amazon today., Discover trusted black seed and oregano oil blends available on Amazon.

Provide your response in the following exact format:

CAMPAIGN_NAME: [Generic category name — NO brand name, keep it short and descriptive]

KEYWORDS:
"category keyword amazon"
[category keyword amazon]
"category variation amazon"
[buy category keyword amazon]
"category on amazon"
[related category amazon]
"shop category amazon"
[category supplement amazon]
"broader category amazon"
(9 keywords total — EVERY keyword MUST contain the word "amazon" — mix of "exact match" (quotes) and [phrase match] (brackets) — NO bare keywords without quotes or brackets)

HEADLINES:
Category on Amazon
Shop Category Amazon
Buy Category on Amazon
Top Category Amazon
... (12-15 headlines total, MAXIMUM 30 characters each - strict!)

DESCRIPTIONS:
Shopping-focused description for finding this category on Amazon (max 90 chars).
Quality/selection description for this product type available on Amazon (max 90 chars).
Trust/value description about shopping this category on Amazon (max 90 chars).
Fourth shopping-intent description for this category on Amazon (max 90 chars).

RULES:
- Keywords: 9 total, EVERY keyword MUST include the word "amazon"
- Mix of "exact match" (quotes) and [phrase match] (brackets) — roughly 40% exact, 60% phrase
- NO bare keywords (no broad match — every keyword must have quotes or brackets)
- NO brand name in keywords, headlines, or descriptions — use generic category terms only
- Headlines: 12-15 total, MAXIMUM 30 characters each (strict!)
- Descriptions: 4 total, MAXIMUM 90 characters each (strict!)
- Focus on Amazon shopping intent: buy, shop, find, discover, browse on Amazon

""" + _POLICY_RULES

# Keep old name as alias for backwards compatibility
_PROMPT_TEMPLATE = _BRAND_PROMPT_TEMPLATE


# ── Public API ────────────────────────────────────────────────────────────────

def start_job(items: List[Dict], campaign_type: str = "brand") -> str:
    """
    Create a CampaignJob + CampaignJobItems in the DB and start background processing.
    campaign_type: "brand" (branded keywords) | "amazon" (category + Amazon keywords)
    Returns the job_id (UUID string).
    """
    job_id = str(uuid.uuid4())
    campaign_type = campaign_type if campaign_type in ("brand", "amazon") else "brand"

    db = SessionLocal()
    try:
        job = CampaignJob(
            id=job_id,
            status="pending",
            campaign_type=campaign_type,
            total=len(items),
            processed=0,
            failed_count=0,
        )
        db.add(job)

        for item in items:
            asin = item.get("asin", "").strip().upper()
            if not asin:
                continue
            db.add(CampaignJobItem(
                job_id=job_id,
                asin=asin,
                product_name=item.get("product_name") or None,
                status="pending",
            ))
        db.commit()
    finally:
        db.close()

    _launch_job_thread(job_id)
    return job_id


def resume_pending_jobs() -> None:
    """
    Called on startup: re-launch any jobs that were running/pending when the
    process last stopped (e.g. Railway restart).
    """
    db = SessionLocal()
    try:
        stale = db.query(CampaignJob).filter(
            CampaignJob.status.in_(["pending", "running"])
        ).all()
        if not stale:
            return
        logger.info("Resuming %d stale campaign job(s)…", len(stale))
        for job in stale:
            job.status = "pending"
        db.commit()
        for job in stale:
            _launch_job_thread(job.id)
    except Exception:
        logger.exception("Failed to resume pending campaign jobs")
    finally:
        db.close()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _launch_job_thread(job_id: str) -> None:
    t = threading.Thread(
        target=_process_job,
        args=(job_id,),
        daemon=True,
        name=f"cjob-{job_id[:8]}",
    )
    t.start()


def _process_job(job_id: str) -> None:
    """Background thread: update status to running, then process all pending items."""
    db = SessionLocal()
    try:
        job = db.query(CampaignJob).filter(CampaignJob.id == job_id).first()
        if not job:
            return
        job.status = "running"
        db.commit()

        campaign_type = job.campaign_type or "brand"
        pending = db.query(CampaignJobItem).filter(
            CampaignJobItem.job_id == job_id,
            CampaignJobItem.status == "pending",
        ).all()
        item_data = [
            {"id": i.id, "asin": i.asin, "product_name": i.product_name,
             "campaign_type": campaign_type}
            for i in pending
        ]
    finally:
        db.close()

    if not item_data:
        _finalize_job(job_id)
        return

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {executor.submit(_process_one, d): d["id"] for d in item_data}
        for future in as_completed(futures):
            item_id = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.exception("Unhandled error for item %d", item_id)
                _mark_item_failed(item_id, str(exc))

    _finalize_job(job_id)


def _process_one(item_data: Dict) -> None:
    """Process a single ASIN: get link → get name → generate ad copy → save."""
    item_id: int = item_data["id"]
    asin: str = item_data["asin"]
    product_name: Optional[str] = item_data.get("product_name")
    campaign_type: str = item_data.get("campaign_type", "brand")

    db = SessionLocal()
    try:
        # 1. Attribution link (cached per asin+campaign_type)
        link = _get_or_create_link(db, asin, campaign_type)
        if not link:
            _set_item_result(db, item_id, status="failed",
                             error="Failed to generate attribution link from Archer API")
            return

        # 2. Product name from Archer if not supplied
        if not product_name:
            product_name = _fetch_product_name(asin)
        if not product_name:
            _set_item_result(db, item_id, status="failed",
                             error="Product name not found in Archer API")
            return

        # 3. Generate ad copy with Claude
        ad_copy = _generate_ad_copy(product_name, asin, campaign_type)

        # 4. Persist
        _set_item_result(
            db, item_id,
            status="done",
            product_name=product_name,
            attribution_link=link,
            ad_copy=json.dumps(ad_copy),
        )
        logger.info(
            "ASIN %s done: %d keywords, %d headlines, %d descriptions",
            asin,
            len(ad_copy.get("keywords", [])),
            len(ad_copy.get("headlines", [])),
            len(ad_copy.get("descriptions", [])),
        )

    except Exception as exc:
        logger.exception("Error processing ASIN %s (item %d)", asin, item_id)
        db.rollback()
        _mark_item_failed(item_id, str(exc)[:500])
    finally:
        db.close()


def _set_item_result(db: Any, item_id: int, **kwargs) -> None:
    """Update a CampaignJobItem with the given fields."""
    item = db.query(CampaignJobItem).filter(CampaignJobItem.id == item_id).first()
    if not item:
        return
    for k, v in kwargs.items():
        setattr(item, k, v)
    db.commit()


def _mark_item_failed(item_id: int, error: str) -> None:
    db = SessionLocal()
    try:
        item = db.query(CampaignJobItem).filter(CampaignJobItem.id == item_id).first()
        if item:
            item.status = "failed"
            item.error = error[:500]
            db.commit()
    except Exception:
        logger.exception("Could not mark item %d as failed", item_id)
    finally:
        db.close()


def _finalize_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(CampaignJob).filter(CampaignJob.id == job_id).first()
        if not job:
            return

        done = db.query(CampaignJobItem).filter(
            CampaignJobItem.job_id == job_id,
            CampaignJobItem.status == "done",
        ).count()
        failed = db.query(CampaignJobItem).filter(
            CampaignJobItem.job_id == job_id,
            CampaignJobItem.status == "failed",
        ).count()

        job.processed = done + failed
        job.failed_count = failed

        if failed == 0:
            job.status = "completed"
        elif done == 0:
            job.status = "failed"
        else:
            job.status = "partial"

        db.commit()
        logger.info(
            "Campaign job %s finished: status=%s, done=%d, failed=%d",
            job_id, job.status, done, failed,
        )
    except Exception:
        logger.exception("Failed to finalize job %s", job_id)
    finally:
        db.close()


# ── Archer / Claude helpers ───────────────────────────────────────────────────

def _get_or_create_link(db: Any, asin: str, campaign_type: str = "brand") -> Optional[str]:
    """
    Return cached attribution link or generate + cache a new one.
    Each (asin, campaign_type) pair gets its own distinct Archer link so revenue
    can be tracked separately per campaign type.
    """
    cached = db.query(AttributionLinkCache).filter(
        AttributionLinkCache.asin == asin,
        AttributionLinkCache.campaign_type == campaign_type,
    ).first()
    if cached:
        logger.debug("Attribution link cache hit for %s / %s", asin, campaign_type)
        return cached.url

    type_label = "Brand" if campaign_type == "brand" else "Amazon"
    link_name = f"Google Ads - {asin} - {type_label}"
    try:
        client = ArcherClient()
        link = client.generate_attribution_link(
            asin=asin,
            link_name=link_name,
            geo="US",
        )
        if link:
            db.merge(AttributionLinkCache(asin=asin, campaign_type=campaign_type, url=link))
            db.commit()
        return link
    except Exception as exc:
        logger.warning("Attribution link generation failed for %s/%s: %s", asin, campaign_type, exc)
        return None


def _fetch_product_name(asin: str) -> Optional[str]:
    """Look up product name via Archer /get_single_product."""
    try:
        client = ArcherClient()
        result = client.check_asin(asin)
        name = result.get("product_name")
        if name:
            logger.debug("Product name for %s: %s", asin, name[:60])
        return name
    except Exception as exc:
        logger.warning("Product name lookup failed for %s: %s", asin, exc)
        return None


def _generate_ad_copy(product_name: str, asin: str, campaign_type: str = "brand") -> Dict:
    """
    Call Claude to generate keywords, headlines, and descriptions.
    campaign_type "brand" → branded keyword prompt
    campaign_type "amazon" → Amazon category keyword prompt (all keywords include "amazon")
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    client = Anthropic(api_key=settings.anthropic_api_key)
    template = _BRAND_PROMPT_TEMPLATE if campaign_type == "brand" else _AMAZON_PROMPT_TEMPLATE
    prompt = template.format(product_name=product_name, asin=asin)

    try:
        message = client.messages.create(
            model=_CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text
        parsed = _parse_response(text)

        # Append type tag + ASIN to campaign name
        base_name = parsed.get("campaign_name") or product_name[:50]
        tag = "[Brand]" if campaign_type == "brand" else "[Amazon]"
        parsed["campaign_name"] = f"{base_name} - {tag} {asin}"
        return parsed

    except Exception as exc:
        logger.exception("Claude API failed for ASIN %s", asin)
        tag = "[Brand]" if campaign_type == "brand" else "[Amazon]"
        return {
            "campaign_name": f"Campaign - {tag} {asin}",
            "keywords": [],
            "headlines": [],
            "descriptions": [],
        }


def _parse_response(text: str) -> Dict:
    """Parse Claude's structured response into a dict."""
    lines = text.strip().split("\n")
    data: Dict = {
        "campaign_name": "",
        "keywords": [],
        "headlines": [],
        "descriptions": [],
    }
    current_section: Optional[str] = None

    def _clean(line: str) -> str:
        line = line.strip()
        line = line.strip("#").strip()
        line = line.strip("*").strip()
        line = line.strip("-").strip()
        return line

    def _is_header(line: str, section: str) -> bool:
        return _clean(line).upper().rstrip(":") == section

    for raw in lines:
        cleaned = _clean(raw.strip())
        if not cleaned:
            continue

        if cleaned.upper().startswith("CAMPAIGN_NAME:"):
            data["campaign_name"] = cleaned.split(":", 1)[1].strip()
            current_section = None
        elif _is_header(cleaned, "KEYWORDS"):
            current_section = "keywords"
        elif _is_header(cleaned, "HEADLINES"):
            current_section = "headlines"
        elif _is_header(cleaned, "DESCRIPTIONS"):
            current_section = "descriptions"
        elif current_section:
            if any(_is_header(cleaned, s) for s in
                   ["KEYWORDS", "HEADLINES", "DESCRIPTIONS", "CAMPAIGN_NAME", "RULES"]):
                continue
            content = cleaned.lstrip("0123456789.-) ").strip()
            if content:
                data[current_section].append(content)

    return data
