# ================= Amazon PA-API 5 Server (Clean, No-Cache) =================
import http.server, socketserver, json, os, time, hashlib
import re
from urllib.parse import urlparse, parse_qs, unquote
import requests
from datetime import datetime, timezone

# ================= Env Loader (prefer apikeys/env variants, then .env) ======
# --- make stdout/stderr utf-8 safe on Windows ---
import sys
for _stream in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
# -----------------------------------------------

FOLDER = os.path.dirname(__file__)
os.chdir(FOLDER)

PAAPI_SRC = "env-not-loaded"
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    for p in [
        os.path.join(FOLDER, "apikeys"),
        os.path.join(FOLDER, "apikey.env"),
        os.path.join(FOLDER, "apikeys.env"),
        os.path.join(FOLDER, ".env"),
        os.path.join(os.path.dirname(FOLDER), ".env"),
    ]:
        if os.path.exists(p):
            load_dotenv(p, override=True)
            PAAPI_SRC = os.path.basename(p)
            break
except Exception:
    pass
# ============================================================================

# ================= Config / Env (accept AMZ_* aliases) ======================
PORT = 5050

def _env(name, default=""):
    return os.getenv(name, default)

# Prefer PAAPI_*, fall back to AMZ_* aliases if present
PAAPI_PARTNER_TAG = _env("PAAPI_PARTNER_TAG") or _env("AMZ_TAG_PROMO") or _env("AMZ_TAG_FLIP") or ""
PAAPI_ACCESS_KEY  = _env("PAAPI_ACCESS_KEY") or _env("AMZ_ACCESS_KEY") or ""
PAAPI_SECRET_KEY  = _env("PAAPI_SECRET_KEY") or _env("AMZ_SECRET_KEY") or ""
PAAPI_HOST        = _env("PAAPI_HOST", "webservices.amazon.com")
PAAPI_REGION      = _env("PAAPI_REGION", "us-east-1")
PAAPI_MARKETPLACE = _env("PAAPI_MARKETPLACE") or _env("AMZ_MARKETPLACE", "www.amazon.com")
PAAPI_TIMEOUT_MS  = int(_env("PAAPI_TIMEOUT_MS", "10000"))
PAAPI_MAX_RETRIES = int(_env("PAAPI_MAX_RETRIES", "3"))

PAAPI_ENDPOINT = f"https://{PAAPI_HOST}/paapi5"
HTTP_TIMEOUT = PAAPI_TIMEOUT_MS / 1000.0

print(
    f"[paapi] loaded from: {PAAPI_SRC}  "
    f"tag={bool(PAAPI_PARTNER_TAG)} key={bool(PAAPI_ACCESS_KEY)} secret={bool(PAAPI_SECRET_KEY)}"
)
# ============================================================================


# ================= SigV4 Signing ===========================================
import hmac as _hmac

def _sign(key: bytes, msg: str) -> bytes:
    return _hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _hmac.new(k_date, region_name.encode("utf-8"), hashlib.sha256).digest()
    k_service = _hmac.new(k_region, service_name.encode("utf-8"), hashlib.sha256).digest()
    k_signing = _hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
    return k_signing

def sigv4_headers(host: str, region: str, service: str, target: str, payload_bytes: bytes) -> dict:
    """
    Build canonical SigV4 headers for PA-API v5.
    target: "GetItems" | "SearchItems"

    IMPORTANT:
    - Sign EXACTLY these headers (lowercase): content-encoding;host;x-amz-date;x-amz-target
    - Still send Content-Type, Accept, etc., but DO NOT include them in the signed headers.
    - Include Content-Encoding: amz-1.0 (PA-API quirk; matches Scratchpad).
    """
    amz_target = f"com.amazon.paapi5.v1.ProductAdvertisingAPIv1.{target}"

    # Timestamps
    t = datetime.now(timezone.utc)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    # Canonical request pieces
    canonical_uri = f"/paapi5/{target.lower()}"
    canonical_querystring = ""
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()

    # Signed headers (match Scratchpad)
    signed_headers_kv = {
        "content-encoding": "amz-1.0",
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-target": amz_target,
    }
    signed_headers_list = sorted(signed_headers_kv.keys())
    canonical_headers = "".join(f"{k}:{signed_headers_kv[k]}\n" for k in signed_headers_list)
    signed_headers = ";".join(signed_headers_list)

    canonical_request = "\n".join([
        "POST",
        canonical_uri,
        canonical_querystring,
        canonical_headers,
        signed_headers,
        payload_hash
    ])

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        algorithm,
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    ])

    signing_key = _get_signature_key(PAAPI_SECRET_KEY, date_stamp, region, service)
    signature = _hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {
        # Signed headers
        "Content-Encoding": "amz-1.0",
        "Host": host,
        "X-Amz-Date": amz_date,
        "X-Amz-Target": amz_target,

        # Auth
        "Authorization": (
            f"{algorithm} Credential={PAAPI_ACCESS_KEY}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),

        # Unsigned-but-required
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json, text/javascript",
        "X-Amz-User-Agent": "paapi-tool/1.0 (Language=Python)",
    }
    return headers
# ============================================================================


# ================= Mapping Helpers ==========================================
def _money_display(amount_obj):
    if not amount_obj:
        return None
    return amount_obj.get("DisplayAmount") or None

def _first(lst):
    return lst[0] if isinstance(lst, list) and lst else None

def map_get_items_to_card(item: dict) -> dict:
    title = (item.get("ItemInfo", {}).get("Title", {}) or {}).get("DisplayValue")

    offers = item.get("Offers", {}) or {}
    listing = _first(offers.get("Listings"))
    summaries = offers.get("Summaries") or []

    # Price + SavingsBasis under listing["Price"]
    price_info = (listing or {}).get("Price") or {}
    buybox_price = _money_display(price_info)
    saving_basis = _money_display(price_info.get("SavingsBasis"))
    list_price = saving_basis or (_money_display(_first(summaries).get("LowestPrice")) if summaries else None)

    savepct = 0
    try:
        if list_price and buybox_price:
            ln = float(str(list_price).replace("$", "").replace(",", ""))
            pn = float(str(buybox_price).replace("$", "").replace(",", ""))
            if ln > pn and ln > 0:
                savepct = round((ln - pn) / ln * 100)
    except Exception:
        savepct = 0

    # Images omitted to avoid PA-API ValidationException issues on certain accounts/locales

    delivery = (listing or {}).get("DeliveryInfo", {}) or {}
    prime = delivery.get("IsPrimeEligible")
    afn = delivery.get("IsAmazonFulfilled")

    avail = (listing or {}).get("Availability", {}) or {}
    avail_msg = avail.get("Message")

    tokens = []
    if prime: tokens.append("Prime")
    if afn: tokens.append("Amazon Fulfilled")
    if avail_msg: tokens.append(avail_msg)
    availability = " • ".join(tokens) if tokens else None

    deal_label = "Buy Box Winner" if (listing or {}).get("IsBuyBoxWinner") else None
    detail_url = item.get("DetailPageURL")

    return {
        "asin": item.get("ASIN"),
        "title": title or "Unknown",
        "buybox_price": buybox_price or None,
        "list_price": list_price or None,
        "savepct": savepct,
        # image omitted
        "coupon": None,
        "availability": availability,
        "deal_label": deal_label,
        "affiliate": detail_url
    }

def map_get_items_to_structured(item: dict) -> dict:
    """
    Produce a richer, organized structure from a PA-API GetItems item.
    All fields are optional-safe and default to None or empty lists.
    """
    def gv(obj, *path, default=None):
        cur = obj or {}
        for k in path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return cur if cur is not None else default

    def money(m):
        if not isinstance(m, dict):
            return None
        return {
            "display": m.get("DisplayAmount"),
            "amount": gv(m, "Amount"),
            "currency": gv(m, "Currency")
        }

    asin = item.get("ASIN")
    detail_url = item.get("DetailPageURL")

    item_info = item.get("ItemInfo", {}) or {}
    byline = item_info.get("ByLineInfo", {}) or {}
    manuf  = item_info.get("ManufactureInfo", {}) or {}
    prod   = item_info.get("ProductInfo", {}) or {}
    tech   = item_info.get("TechnicalInfo", {}) or {}
    feats  = item_info.get("Features", {}) or {}

    offers = item.get("Offers", {}) or {}
    listing = _first(offers.get("Listings")) or {}
    summaries = offers.get("Summaries") or []

    price_info = listing.get("Price") or {}
    lowest = _first(summaries)

    images = item.get("Images", {}) or {}
    primary = images.get("Primary") or {}

    availability = listing.get("Availability", {}) or {}
    delivery = listing.get("DeliveryInfo", {}) or {}

    structured = {
        "asin": asin,
        "title": gv(item_info, "Title", "DisplayValue"),
        "detailPageURL": detail_url,
        "brand": gv(byline, "Brand", "DisplayValue"),
        "manufacturer": gv(manuf, "Manufacturer", "DisplayValue"),
        "modelNumber": gv(manuf, "Model", "DisplayValue") or gv(prod, "Model", "DisplayValue"),
        "partNumber": gv(manuf, "ItemPartNumber", "DisplayValue"),
        "features": feats.get("DisplayValues") or [],
        "classifications": {
            "binding": gv(item_info.get("Classifications", {}), "Binding", "DisplayValue"),
            "productGroup": gv(item_info.get("Classifications", {}), "ProductGroup", "DisplayValue"),
        },
        "images": {
            "primary": {
                "small": gv(primary, "Small", "URL"),
                "medium": gv(primary, "Medium", "URL"),
                "large": gv(primary, "Large", "URL"),
            }
        },
        "offers": {
            "buybox": money(price_info),
            "savingsBasis": money(price_info.get("SavingsBasis")),
            "lowest": money(gv(lowest or {}, "LowestPrice")) if lowest else None,
            "highest": money(gv(lowest or {}, "HighestPrice")) if lowest else None,
            "offerCount": gv(lowest or {}, "OfferCount"),
            "isBuyBoxWinner": bool(listing.get("IsBuyBoxWinner")),
        },
        "delivery": {
            "isPrimeEligible": bool(delivery.get("IsPrimeEligible")),
            "isAmazonFulfilled": bool(delivery.get("IsAmazonFulfilled")),
        },
        "availability": {
            "message": availability.get("Message"),
        },
        "externalIds": item_info.get("ExternalIds") or {},
    }
    return structured

def map_get_items_to_text(item: dict) -> str:
    """Human-friendly multi-line summary."""
    card = map_get_items_to_card(item)
    lines = [
        f"Product Title: {card.get('title') or 'Unknown'}",
        f"Reg Price: {card.get('list_price') or 'N/A'}",
        f"Discounted Price: {card.get('buybox_price') or 'N/A'}",
        f"You Save: {card.get('savepct') or 0}%",
        f"ASIN: {card.get('asin') or 'N/A'}",
        f"Availability: {card.get('availability') or 'N/A'}",
        f"Deal: {card.get('deal_label') or 'None'}",
        f"Link: {card.get('affiliate') or 'N/A'}",
    ]
    return "\n".join(lines)

def map_search_to_list(items, refinements=None, page=1, total_pages=None):
    results = []
    for it in items or []:
        asin = it.get("ASIN")
        title = (it.get("ItemInfo", {}).get("Title", {}) or {}).get("DisplayValue")
        listing = _first((it.get("Offers", {}) or {}).get("Listings"))
        price = _money_display((listing or {}).get("Price"))
        url = it.get("DetailPageURL")
        results.append({"title": title or "Unknown", "asin": asin, "price": price, "url": url})

    has_next = False
    try:
        if total_pages is not None and page is not None:
            has_next = page < int(total_pages)
    except Exception:
        has_next = False

    norm_refinements = {"brands": [], "priceBuckets": [], "browseNodes": []}
    if refinements:
        brands = refinements.get("Brands", {}).get("RefinementOptions") or []
        norm_refinements["brands"] = [b.get("Label") for b in brands if b.get("Label")]
        price_buckets = refinements.get("Price", {}).get("RefinementOptions") or []
        norm_refinements["priceBuckets"] = [p.get("DisplayValue") for p in price_buckets if p.get("DisplayValue")]
        nodes = refinements.get("BrowseNode", {}).get("RefinementOptions") or []
        norm_refinements["browseNodes"] = [{"id": n.get("Value"), "label": n.get("Label")}
                                           for n in nodes if n.get("Value") and n.get("Label")]

    return {"results": results, "refinements": norm_refinements, "page": page or 1, "hasNextPage": has_next}
# ============================================================================


# ================= Endpoint Implementations ================================
def _map_error_to_status(raw_err: dict):
    code_str = (raw_err.get("code") or "UNKNOWN").upper()
    http_status = 400
    if code_str.startswith("HTTP_"):
        try:
            http_status = int(code_str.split("_", 1)[1])
        except Exception:
            http_status = 400
    elif code_str in ("THROTTLING", "TOO_MANY_REQUESTS"):
        http_status = 429
    elif code_str in ("ACCESS_DENIED", "UNAUTHORIZED", "INVALID_SIGNATURE"):
        http_status = 403
    elif code_str in ("INTERNAL_ERROR", "SERVICE_UNAVAILABLE"):
        http_status = 503
    return http_status, code_str

# ------- SAFE RESOURCE SETS (US): trimmed to avoid ValidationException on some accounts
def _full_resources_getitems():
    # Keep to a conservative, widely-accepted subset.
    return [
        # Images (Primary only; Variants can trigger ValidationException on some locales)
        "Images.Primary.Small",
        "Images.Primary.Medium",
        "Images.Primary.Large",

        # Item info (core only)
        "ItemInfo.Title",
        "ItemInfo.ByLineInfo",
        "ItemInfo.Features",
        "ItemInfo.ProductInfo",

        # Offers (summary + listing for price and availability)
        "Offers.Listings.Price",                  # includes SavingsBasis inside
        "Offers.Listings.IsBuyBoxWinner",
        "Offers.Listings.Availability.Message",
        "Offers.Listings.DeliveryInfo.IsAmazonFulfilled",
        "Offers.Listings.DeliveryInfo.IsPrimeEligible",
        "Offers.Summaries.LowestPrice",
        "Offers.Summaries.HighestPrice",
        "Offers.Summaries.OfferCount",

        # Useful for families but safe
        "ParentASIN",
    ]

def _full_resources_searchitems():
    return [
        # Images (no HighRes)
        "Images.Primary.Small", "Images.Primary.Medium", "Images.Primary.Large",

        # Item info (titles & basic product details)
        "ItemInfo.Title", "ItemInfo.ByLineInfo", "ItemInfo.Classifications",
        "ItemInfo.ExternalIds", "ItemInfo.ProductInfo",

        # Offers summary sufficient for list display
        "Offers.Listings.Price",
        "Offers.Summaries.LowestPrice", "Offers.Summaries.HighestPrice",

        # For filters
        "SearchRefinements",
        "ParentASIN",
    ]

def handle_get_items(asin: str, fmt: str = "card"):
    asin = (asin or "").strip().upper()
    if len(asin) != 10:
        return 400, {"error": {"code": "ASIN_INVALID", "message": "Provide a valid 10-char ASIN"}}

    body = {
        "ItemIds": [asin],
        "PartnerTag": PAAPI_PARTNER_TAG,
        "PartnerType": "Associates",
        "Marketplace": PAAPI_MARKETPLACE,
        "Resources": _full_resources_getitems(),
    }

    raw = paapi_post("GetItems", body)
    if "error" in raw:
        status, code_str = _map_error_to_status(raw["error"])
        msg = raw["error"].get("message") or "Unknown error"
        return status, {"error": {"code": code_str, "message": msg}}

    items = (raw.get("ItemsResult") or {}).get("Items") or []
    if not items:
        errs = raw.get("Errors") or []
        if errs:
            e = errs[0]
            return 404, {"error": {"code": e.get("Code", "ASIN_NOT_FOUND"), "message": e.get("Message", "Item not found")}}
        return 404, {"error": {"code": "ASIN_NOT_FOUND", "message": "Item not found or not eligible in marketplace"}}

    item = items[0]
    fmt_norm = (fmt or "card").strip().lower()
    if fmt_norm == "structured":
        return 200, map_get_items_to_structured(item)
    if fmt_norm == "text":
        return 200, {"text": map_get_items_to_text(item)}
    return 200, map_get_items_to_card(item)

def handle_search_items(payload: dict):
    keywords     = (payload.get("keywords") or "").strip()
    search_index = (payload.get("searchIndex") or "All").strip()
    brand        = (payload.get("brand") or "").strip()
    min_price    = payload.get("minPrice")
    max_price    = payload.get("maxPrice")
    browse_node  = (payload.get("browseNodeId") or "").strip()
    external_id  = bool(payload.get("externalId"))
    page         = int(payload.get("page") or 1)

    if not keywords:
        return 400, {"error": {"code": "BAD_REQUEST", "message": "Missing keywords"}}

    resources = _full_resources_searchitems()
    if external_id and "ItemInfo.ExternalIds" not in resources:
        resources.append("ItemInfo.ExternalIds")

    req = {
        "PartnerTag": PAAPI_PARTNER_TAG,
        "PartnerType": "Associates",
        "Marketplace": PAAPI_MARKETPLACE,
        "Keywords": keywords,
        "SearchIndex": search_index,
        "ItemCount": 10,
        "ItemPage": page,
        "Resources": resources
    }

    if brand:
        req["Brands"] = [brand]
    if isinstance(min_price, int):
        req["MinPrice"] = min_price
    if isinstance(max_price, int):
        req["MaxPrice"] = max_price
    if browse_node:
        req["BrowseNodeId"] = browse_node

    raw = paapi_post("SearchItems", req)
    if "error" in raw:
        status, code_str = _map_error_to_status(raw["error"])
        msg = raw["error"].get("message") or "Unknown error"
        return status, {"error": {"code": code_str, "message": msg}}

    search_result = raw.get("SearchResult") or {}
    items = search_result.get("Items") or []
    refinements = search_result.get("SearchRefinements")

    if external_id:
        norm_key = keywords.replace("-", "").replace(" ", "").lower()
        def match_external(it):
            ext = ((it.get("ItemInfo") or {}).get("ExternalIds") or {})
            fields = []
            for key in ("EANs", "UPCs", "ISBNs"):
                vals = (ext.get(key) or {}).get("DisplayValues") or []
                fields.extend([str(v) for v in vals])
            for v in fields:
                if v and v.replace("-", "").replace(" ", "").lower() == norm_key:
                    return True
            return False
        items = [it for it in items if match_external(it)]

    mapped = map_search_to_list(items, refinements=refinements, page=page, total_pages=None)
    return 200, mapped
# ============================================================================


# ================= HTTP Handler =============================================
class Handler(http.server.SimpleHTTPRequestHandler):
    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/").lower()
        if path == "/health":
            ok = all([PAAPI_PARTNER_TAG, PAAPI_ACCESS_KEY, PAAPI_SECRET_KEY])
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "status": "ok" if ok else "warn",
                "host": PAAPI_HOST,
                "region": PAAPI_REGION,
                "marketplace": PAAPI_MARKETPLACE,
                "have_tag": bool(PAAPI_PARTNER_TAG),
                "have_key": bool(PAAPI_ACCESS_KEY),
                "have_secret": bool(PAAPI_SECRET_KEY),
                "env_src": PAAPI_SRC
            }).encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(b'{"error":"Not found"}')

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/").lower()
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {}

        if path == "/paapi/get-items":
            asin = (data.get("asin") or "").strip().upper()
            fmt  = (data.get("format") or "card").strip()
            code, payload = handle_get_items(asin, fmt)
            self._set_headers(code)
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/paapi/search-items":
            code, payload = handle_search_items(data or {})
            self._set_headers(code)
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        # New: resolve Amazon links (amzn.to and normal) to ASIN → GetItems
        if path in ("/price", "/paapi/price"):
            link = (data.get("link") or data.get("url") or data.get("href") or "").strip()
            fmt  = (data.get("format") or "card").strip()
            code, payload = handle_price_link(link, fmt)
            self._set_headers(code)
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        self._set_headers(404)
        self.wfile.write(b'{"error":"Not found"}')
# ============================================================================


# ================= PATCH: Canonical Signing Fix for Windows =================
def paapi_post(target: str, body_dict: dict) -> dict:
    """
    POST to PA-API with retries/backoff; returns dict or {'error':{code,message}}.
    - Enforces LF-only JSON and canonical UTF-8 encoding.
    - Signs EXACT header set to match the Scratchpad (content-encoding;host;x-amz-date;x-amz-target).
    """
    if not (PAAPI_PARTNER_TAG and PAAPI_ACCESS_KEY and PAAPI_SECRET_KEY):
        return {"error": {"code": "CONFIG_ERROR", "message": "Missing PAAPI env credentials"}}

    url = f"{PAAPI_ENDPOINT}/{target.lower()}"
    json_body = json.dumps(body_dict, separators=(",", ":"), ensure_ascii=False)
    payload = json_body.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")

    headers = sigv4_headers(PAAPI_HOST, PAAPI_REGION, "ProductAdvertisingAPI", target, payload)

    tries = 0
    max_tries = max(PAAPI_MAX_RETRIES, 3)

    while True:
        tries += 1
        try:
            r = requests.post(url, data=payload, headers=headers, timeout=HTTP_TIMEOUT)
            print("[paapi]", r.status_code, "| reqid", r.headers.get("x-amzn-RequestId"), "|", target)

            if r.status_code in (429,) or 500 <= r.status_code < 600:
                if tries < max_tries:
                    time.sleep((0.5 * tries))
                    continue

            if r.status_code != 200:
                try:
                    errtxt = r.text[:400]
                except Exception:
                    errtxt = "HTTP Error"
                return {"error": {"code": f"HTTP_{r.status_code}", "message": errtxt}}

            try:
                return r.json()
            except Exception:
                return {"error": {"code": "BAD_JSON", "message": r.text[:400]}}

        except requests.RequestException as e:
            if tries < max_tries:
                time.sleep(0.5 * tries)
                continue
            return {"error": {"code": "NETWORK_ERROR", "message": str(e)[:200]}}
# ================= END PATCH =================================================


# ================= Helpers: Link → ASIN =====================================
_ASIN_RE_PATH = re.compile(r"/(?:dp|gp/product|gp/aw/d|gp/offer-listing|exec/obidos/ASIN|o/ASIN|ASIN|product)/([A-Z0-9]{10})(?:[/?#]|$)", re.IGNORECASE)
_ASIN_RE_QUERY = re.compile(r"[?&](?:ASIN|asin)=([A-Z0-9]{10})(?:[&#]|$)")
_ASIN_RE_ANY = re.compile(r"(^|[^A-Z0-9])([A-Z0-9]{10})([^A-Z0-9]|$)", re.IGNORECASE)

def _extract_asin_from_url(url: str):
    if not url:
        return None
    try:
        u = urlparse(url)
    except Exception:
        return None

    path = unquote(u.path or "")
    query = u.query or ""

    m = _ASIN_RE_PATH.search(path)
    if m:
        return m.group(1).upper()

    m = _ASIN_RE_QUERY.search("?" + query)
    if m:
        return m.group(1).upper()

    # As a last resort, scan entire URL for a 10-char token
    m = _ASIN_RE_ANY.search(url)
    if m:
        return m.group(2).upper()
    return None

def _resolve_final_url(url: str) -> str:
    if not url:
        return ""
    try:
        # Some shorteners require GET to follow redirects reliably
        r = requests.get(url, allow_redirects=True, timeout=HTTP_TIMEOUT, headers={
            "User-Agent": "Mozilla/5.0 (compatible; paapi-tool/1.0)"
        })
        return r.url or url
    except Exception:
        return url

def handle_price_link(link: str, fmt: str = "card"):
    link = (link or "").strip()
    if not link:
        return 400, {"error": {"code": "BAD_REQUEST", "message": "Missing link"}}

    # If user pasted a bare ASIN, accept it directly
    if re.fullmatch(r"[A-Za-z0-9]{10}", link):
        asin = link.upper()
        return handle_get_items(asin, fmt)

    # Try direct extraction first
    asin = _extract_asin_from_url(link)
    if not asin:
        # Follow redirects (amzn.to, bit.ly, etc.)
        final = _resolve_final_url(link)
        asin = _extract_asin_from_url(final)
    if not asin:
        return 400, {"error": {"code": "ASIN_NOT_FOUND", "message": "Could not extract ASIN from link"}}

    return handle_get_items(asin, fmt)
# ============================================================================


# ================= Entry Point ==============================================
if __name__ == "__main__":
    # quick manual test
    from pprint import pprint
    body = {
        "ItemIds": ["B0C6HT9RYM"],
        "PartnerTag": PAAPI_PARTNER_TAG,
        "PartnerType": "Associates",
        "Marketplace": PAAPI_MARKETPLACE,
        "Resources": _full_resources_getitems()
    }
    print("Testing direct PAAPI call...")
    res = paapi_post("GetItems", body)
    pprint(res)
    print("Test complete\n")
    # Start server
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"PA-API Tool running on http://127.0.0.1:{PORT}")
        print("Endpoints: POST /paapi/get-items, POST /paapi/search-items, GET /health")
        httpd.serve_forever()
# ================= End File =================================================
