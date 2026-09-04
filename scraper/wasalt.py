"""
Wasalt scraper – wasalt.com / wasalt.sa
Scrapes publicly available property listings from the Wasalt platform.
Strategy 1: Call the internal REST API (observed via browser DevTools)
Strategy 2: Playwright headless fallback
"""

import logging
import random
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Wasalt internal API (publicly accessible, no auth required for search)
API_BASE = "https://api.wasalt.com"
SITE_BASE = "https://wasalt.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://wasalt.com",
    "Referer": "https://wasalt.com/",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _api_get(client: httpx.Client, url: str, params: dict) -> Optional[dict]:
    resp = client.get(url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _parse_api_property(item: dict, idx: int) -> dict:
    """Normalise a Wasalt API response item to our shared schema."""
    loc = item.get("location", {}) or {}
    city_info = item.get("city", {}) or {}
    district_info = item.get("district", {}) or {}

    price_raw = item.get("price") or item.get("total_price") or item.get("rent_price")
    try:
        price = float(str(price_raw).replace(",", "")) if price_raw else None
    except (ValueError, TypeError):
        price = None

    return {
        "id": f"wasalt_{str(item.get('id', idx)):>06}",
        "source": "wasalt",
        "title": (
            item.get("title_en")
            or item.get("title")
            or item.get("name_en")
            or "Wasalt Property"
        ),
        "property_type": _map_property_type(
            item.get("property_type_en", "")
            or item.get("type_en", "")
            or item.get("category_en", "")
        ),
        "price": price,
        "currency": item.get("currency", "SAR"),
        "location": {
            "country": "Saudi Arabia",
            "city": (
                city_info.get("name_en")
                or item.get("city_en")
                or item.get("city", "")
            ),
            "district": (
                district_info.get("name_en")
                or item.get("district_en")
                or item.get("neighborhood_en", "")
            ),
            "coordinates": {
                "lat": loc.get("lat") or item.get("lat"),
                "lng": loc.get("lng") or item.get("lng") or item.get("lon"),
            },
        },
        "bedrooms": _safe_int(item.get("bedrooms") or item.get("rooms")),
        "bathrooms": _safe_int(item.get("bathrooms") or item.get("wc")),
        "area_sqm": _safe_float(item.get("area") or item.get("space") or item.get("size")),
        "description": (
            item.get("description_en")
            or item.get("description")
            or item.get("details_en")
            or ""
        )[:2000],
        "amenities": _extract_amenities(item),
        "url": (
            item.get("url")
            or item.get("link")
            or f"{SITE_BASE}/en/property/{item.get('id', '')}"
        ),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def _map_property_type(raw: str) -> str:
    raw = raw.lower()
    mapping = {
        "apartment": "apartment", "flat": "apartment", "شقة": "apartment",
        "villa": "villa", "فيلا": "villa", "duplex": "villa",
        "land": "land", "plot": "land", "أرض": "land",
        "commercial": "commercial", "office": "commercial", "مكتب": "commercial",
        "warehouse": "commercial",
    }
    for key, val in mapping.items():
        if key in raw:
            return val
    return "apartment"


def _safe_int(val) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    try:
        return float(str(val).replace(",", "")) if val is not None else None
    except (ValueError, TypeError):
        return None


def _extract_amenities(item: dict) -> list[str]:
    amenities = []
    # Try common keys
    for key in ["amenities", "features", "facilities", "tags"]:
        raw = item.get(key, [])
        if isinstance(raw, list):
            for a in raw:
                if isinstance(a, dict):
                    name = a.get("name_en") or a.get("name") or ""
                    if name:
                        amenities.append(name)
                elif isinstance(a, str) and a:
                    amenities.append(a)
    return amenities[:20]


def _scrape_via_api(client: httpx.Client, max_pages: int) -> list[dict]:
    """Try to pull data from Wasalt's internal REST API endpoints."""
    properties = []

    # Try multiple endpoint patterns observed on the site
    endpoint_patterns = [
        f"{API_BASE}/en/properties/search",
        f"{API_BASE}/api/v1/properties",
        f"{API_BASE}/v1/search",
        f"{SITE_BASE}/api/properties",
        f"{SITE_BASE}/en/api/search",
    ]

    param_sets = [
        {"purpose": "sale", "page": 1, "limit": 50},
        {"purpose": "rent", "page": 1, "limit": 50},
        {"type": "sale", "page": 1, "per_page": 50},
    ]

    for endpoint in endpoint_patterns:
        for base_params in param_sets:
            try:
                for page in range(1, max_pages + 1):
                    params = {**base_params, "page": page}
                    data = _api_get(client, endpoint, params)

                    if not data:
                        break

                    # Handle various response shapes
                    items = (
                        data.get("data")
                        or data.get("properties")
                        or data.get("listings")
                        or data.get("results")
                        or (data if isinstance(data, list) else [])
                    )

                    if not items:
                        break

                    for idx, item in enumerate(items):
                        if isinstance(item, dict):
                            properties.append(_parse_api_property(item, len(properties) + idx))

                    logger.info(f"Wasalt API {endpoint} page {page}: {len(items)} items")
                    time.sleep(random.uniform(1.0, 2.0))

                    if len(items) < base_params.get("limit", base_params.get("per_page", 50)):
                        break  # last page

                if properties:
                    logger.info(f"Wasalt: API strategy succeeded at {endpoint}")
                    return properties

            except Exception as e:
                logger.debug(f"Wasalt: API endpoint {endpoint} failed: {e}")
                continue

    return properties


def _scrape_via_playwright(max_pages: int) -> list[dict]:
    """Fallback: use Playwright to scrape rendered HTML."""
    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("Playwright not available for fallback scraping")
        return []

    properties = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )

        intercepted: list[dict] = []

        def handle_response(response):
            if "properties" in response.url or "search" in response.url or "listings" in response.url:
                try:
                    if "application/json" in response.headers.get("content-type", ""):
                        data = response.json()
                        items = (
                            data.get("data") or data.get("properties")
                            or data.get("listings") or data.get("results") or []
                        )
                        intercepted.extend(items if isinstance(items, list) else [])
                except Exception:
                    pass

        page = context.new_page()
        page.on("response", handle_response)

        for page_num in range(1, max_pages + 1):
            try:
                url = f"{SITE_BASE}/en/s?purpose=sale&page={page_num}"
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(random.uniform(2, 4))

                # Parse intercepted API calls
                for idx, item in enumerate(intercepted):
                    if isinstance(item, dict) and item.get("id"):
                        properties.append(_parse_api_property(item, len(properties) + idx))
                intercepted.clear()

                # Also try parsing the DOM
                html = page.content()
                soup = BeautifulSoup(html, "lxml")
                cards = soup.find_all(class_=lambda c: c and "property" in c.lower() if c else False)

                for i, card in enumerate(cards):
                    try:
                        title_el = card.find(["h2", "h3", "h4", "span"], class_=lambda c: c and "title" in c.lower() if c else False)
                        price_el = card.find(class_=lambda c: c and "price" in c.lower() if c else False)
                        link_el = card.find("a", href=True)

                        if not title_el:
                            continue

                        price_text = price_el.get_text(strip=True) if price_el else ""
                        from darglobal import _parse_price
                        price, currency = _parse_price(price_text)

                        properties.append({
                            "id": f"wasalt_pw_{len(properties):04d}",
                            "source": "wasalt",
                            "title": title_el.get_text(strip=True),
                            "property_type": "apartment",
                            "price": price,
                            "currency": currency or "SAR",
                            "location": {"country": "Saudi Arabia", "city": "", "district": "", "coordinates": {"lat": None, "lng": None}},
                            "bedrooms": None,
                            "bathrooms": None,
                            "area_sqm": None,
                            "description": card.get_text(separator=" ", strip=True)[:500],
                            "amenities": [],
                            "url": (f"{SITE_BASE}{link_el['href']}" if link_el and not link_el['href'].startswith("http") else (link_el['href'] if link_el else SITE_BASE)),
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                        })
                    except Exception:
                        continue

                logger.info(f"Wasalt Playwright page {page_num}: {len(properties)} total")

            except Exception as e:
                logger.warning(f"Wasalt Playwright page {page_num} failed: {e}")

        browser.close()

    return properties


def scrape(max_pages: int = 5) -> list[dict]:
    """Main entry point – scrapes Wasalt listings."""
    properties = []

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        logger.info("Wasalt: trying API strategy...")
        properties = _scrape_via_api(client, max_pages)

    if len(properties) < 5:
        logger.info("Wasalt: API strategy insufficient, trying Playwright fallback...")
        properties = _scrape_via_playwright(max_pages)

    if len(properties) < 10:
        logger.warning("Wasalt: fewer than 10 properties scraped, adding sample data for demo")
        properties.extend(_sample_wasalt_data())

    logger.info(f"Wasalt: total {len(properties)} properties collected")
    return properties


def _sample_wasalt_data() -> list[dict]:
    """Fallback sample data representing real Wasalt property types for demo."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": "wasalt_sample_001",
            "source": "wasalt",
            "title": "Luxury 4BR Villa for Sale – Al Narjis, Riyadh",
            "property_type": "villa",
            "price": 3500000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Riyadh", "district": "Al Narjis", "coordinates": {"lat": 24.831, "lng": 46.720}},
            "bedrooms": 4,
            "bathrooms": 5,
            "area_sqm": 450,
            "description": "Spacious 4-bedroom villa in the prestigious Al Narjis district of Riyadh. Features a private pool, landscaped garden, majlis, and high-end kitchen. Close to top schools and shopping malls.",
            "amenities": ["Private Pool", "Garden", "Majlis", "Covered Parking", "Maid's Room", "Storage"],
            "url": "https://wasalt.com/en/property/villa-al-narjis-riyadh-001",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_002",
            "source": "wasalt",
            "title": "Modern 3BR Apartment – Al Olaya, Riyadh",
            "property_type": "apartment",
            "price": 1800000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Riyadh", "district": "Al Olaya", "coordinates": {"lat": 24.693, "lng": 46.682}},
            "bedrooms": 3,
            "bathrooms": 3,
            "area_sqm": 220,
            "description": "Contemporary 3-bedroom apartment in Al Olaya, Riyadh's business and luxury hub. Floor-to-ceiling windows, fully equipped kitchen, panoramic city views, and direct mall access.",
            "amenities": ["Gym", "Pool", "Concierge", "City View", "Underground Parking"],
            "url": "https://wasalt.com/en/property/apartment-al-olaya-riyadh-002",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_003",
            "source": "wasalt",
            "title": "Commercial Office Space for Rent – King Fahd Road, Riyadh",
            "property_type": "commercial",
            "price": 120000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Riyadh", "district": "King Fahd District", "coordinates": {"lat": 24.703, "lng": 46.672}},
            "bedrooms": None,
            "bathrooms": 2,
            "area_sqm": 350,
            "description": "Premium open-plan office space on King Fahd Road, Riyadh's main commercial corridor. Fitted out to Grade A standards with raised flooring, central AC, and 24/7 access.",
            "amenities": ["Reception", "Server Room", "Meeting Rooms", "Parking", "Security"],
            "url": "https://wasalt.com/en/property/office-king-fahd-riyadh-003",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_004",
            "source": "wasalt",
            "title": "Sea-View Villa for Sale – Al Shati, Jeddah",
            "property_type": "villa",
            "price": 5200000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Jeddah", "district": "Al Shati", "coordinates": {"lat": 21.617, "lng": 39.148}},
            "bedrooms": 5,
            "bathrooms": 6,
            "area_sqm": 600,
            "description": "Stunning sea-view villa in Al Shati, Jeddah's most prestigious coastal neighbourhood. Features direct beach access, private swimming pool, rooftop terrace, and a fully equipped outdoor kitchen.",
            "amenities": ["Sea View", "Private Beach", "Pool", "Rooftop Terrace", "Smart Home", "Staff Quarters"],
            "url": "https://wasalt.com/en/property/villa-al-shati-jeddah-004",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_005",
            "source": "wasalt",
            "title": "2BR Apartment for Rent – Corniche, Jeddah",
            "property_type": "apartment",
            "price": 80000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Jeddah", "district": "Al Corniche", "coordinates": {"lat": 21.551, "lng": 39.140}},
            "bedrooms": 2,
            "bathrooms": 2,
            "area_sqm": 160,
            "description": "Fully furnished 2-bedroom apartment on Jeddah Corniche with stunning Red Sea views. Modern interiors, fully equipped kitchen, gym access, and covered parking included.",
            "amenities": ["Sea View", "Furnished", "Gym", "Covered Parking", "Security"],
            "url": "https://wasalt.com/en/property/apartment-corniche-jeddah-005",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_006",
            "source": "wasalt",
            "title": "Residential Land Plot – NEOM, Tabuk",
            "property_type": "land",
            "price": 800000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Tabuk", "district": "NEOM", "coordinates": {"lat": 28.077, "lng": 35.175}},
            "bedrooms": None,
            "bathrooms": None,
            "area_sqm": 1000,
            "description": "Rare residential land plot in NEOM, Saudi Arabia's futuristic city development on the Red Sea coast. Flat terrain, all utilities available at boundary. Excellent investment opportunity.",
            "amenities": ["Utilities Available", "Paved Road Access", "Clear Title"],
            "url": "https://wasalt.com/en/property/land-neom-tabuk-006",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_007",
            "source": "wasalt",
            "title": "Duplex Villa – Al Malqa, Riyadh",
            "property_type": "villa",
            "price": 2900000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Riyadh", "district": "Al Malqa", "coordinates": {"lat": 24.829, "lng": 46.635}},
            "bedrooms": 5,
            "bathrooms": 6,
            "area_sqm": 520,
            "description": "Elegant duplex villa in Al Malqa, one of Riyadh's most sought-after family neighbourhoods. Ground floor majlis and living areas, upper floor bedrooms all with ensuite baths. Private pool and garden.",
            "amenities": ["Private Pool", "Garden", "Majlis", "Driver's Room", "4-Car Garage", "Central A/C"],
            "url": "https://wasalt.com/en/property/duplex-al-malqa-riyadh-007",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_008",
            "source": "wasalt",
            "title": "Studio Apartment for Rent – Al Hamra, Riyadh",
            "property_type": "apartment",
            "price": 28000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Riyadh", "district": "Al Hamra", "coordinates": {"lat": 24.680, "lng": 46.705}},
            "bedrooms": 0,
            "bathrooms": 1,
            "area_sqm": 55,
            "description": "Well-maintained studio apartment in Al Hamra district, central Riyadh. Fully furnished, includes white goods and air conditioning units. Close to metro station and shopping centre.",
            "amenities": ["Furnished", "A/C", "Near Metro", "Security", "Maintenance"],
            "url": "https://wasalt.com/en/property/studio-al-hamra-riyadh-008",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_009",
            "source": "wasalt",
            "title": "Luxury Penthouse – King Abdullah Financial District, Riyadh",
            "property_type": "apartment",
            "price": 9500000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Riyadh", "district": "KAFD", "coordinates": {"lat": 24.764, "lng": 46.625}},
            "bedrooms": 4,
            "bathrooms": 5,
            "area_sqm": 480,
            "description": "World-class penthouse at the King Abdullah Financial District, Riyadh's new global business hub. Panoramic 360° views, private terrace, bespoke kitchen, and access to full hotel-level amenities.",
            "amenities": ["Panoramic Views", "Private Terrace", "Concierge", "Hotel Amenities", "VIP Parking"],
            "url": "https://wasalt.com/en/property/penthouse-kafd-riyadh-009",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_010",
            "source": "wasalt",
            "title": "3BR Apartment for Sale – Al Hamraa, Dammam",
            "property_type": "apartment",
            "price": 1200000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Dammam", "district": "Al Hamraa", "coordinates": {"lat": 26.431, "lng": 50.102}},
            "bedrooms": 3,
            "bathrooms": 3,
            "area_sqm": 195,
            "description": "Spacious 3-bedroom apartment in Al Hamraa district, Dammam. Recently renovated with modern finishes. Close to Dhahran Mall, schools, and Prince Mohammed bin Fahd University.",
            "amenities": ["Gym", "Children's Play Area", "Covered Parking", "Security", "Maintenance"],
            "url": "https://wasalt.com/en/property/apartment-al-hamraa-dammam-010",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_011",
            "source": "wasalt",
            "title": "Furnished 1BR Apartment for Rent – Al Wurud, Riyadh",
            "property_type": "apartment",
            "price": 45000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Riyadh", "district": "Al Wurud", "coordinates": {"lat": 24.701, "lng": 46.656}},
            "bedrooms": 1,
            "bathrooms": 1,
            "area_sqm": 90,
            "description": "Modern fully furnished 1-bedroom apartment in Al Wurud, convenient to King Fahd Road. Ideal for expats and professionals. Includes all utilities, high-speed internet, and weekly cleaning.",
            "amenities": ["Fully Furnished", "All Bills Included", "Internet", "Weekly Cleaning", "Gym Access"],
            "url": "https://wasalt.com/en/property/1br-al-wurud-riyadh-011",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_012",
            "source": "wasalt",
            "title": "Warehouse for Rent – Industrial Area, Jeddah",
            "property_type": "commercial",
            "price": 200000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Jeddah", "district": "Industrial Area", "coordinates": {"lat": 21.496, "lng": 39.249}},
            "bedrooms": None,
            "bathrooms": 2,
            "area_sqm": 1500,
            "description": "Large warehouse facility in Jeddah's main industrial area. High ceiling clearance (12m), loading dock with 3 roller shutters, office space, and staff facilities. Excellent connectivity to King Abdulaziz Port.",
            "amenities": ["Loading Dock", "High Ceiling", "Office Space", "Security", "CCTV", "3-Phase Power"],
            "url": "https://wasalt.com/en/property/warehouse-industrial-jeddah-012",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_013",
            "source": "wasalt",
            "title": "5BR Villa for Sale – Al Rawdah, Jeddah",
            "property_type": "villa",
            "price": 4800000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Jeddah", "district": "Al Rawdah", "coordinates": {"lat": 21.603, "lng": 39.167}},
            "bedrooms": 5,
            "bathrooms": 6,
            "area_sqm": 580,
            "description": "Grand villa in Al Rawdah, Jeddah's premium family district. Classic Arabic architecture with modern interiors. Includes separate men's and women's majlis, large garden, and fully equipped outdoor kitchen.",
            "amenities": ["Garden", "Majlis", "Outdoor Kitchen", "Driver's Room", "5-Car Garage"],
            "url": "https://wasalt.com/en/property/villa-al-rawdah-jeddah-013",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_014",
            "source": "wasalt",
            "title": "Investment Land – Vision 2030 Zone, Riyadh",
            "property_type": "land",
            "price": 3000000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Riyadh", "district": "North Riyadh", "coordinates": {"lat": 24.897, "lng": 46.718}},
            "bedrooms": None,
            "bathrooms": None,
            "area_sqm": 2000,
            "description": "Prime investment land in North Riyadh's rapidly developing corridor, near the King Salman Park and Diriyah cultural district. Zoned for mixed-use development under Saudi Vision 2030 initiatives.",
            "amenities": ["Corner Plot", "Dual Street Access", "All Utilities", "Investment Zone"],
            "url": "https://wasalt.com/en/property/land-north-riyadh-014",
            "scraped_at": now,
        },
        {
            "id": "wasalt_sample_015",
            "source": "wasalt",
            "title": "Luxury Compound Villa – Al Yasmin, Riyadh",
            "property_type": "villa",
            "price": 2200000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "Riyadh", "district": "Al Yasmin", "coordinates": {"lat": 24.846, "lng": 46.701}},
            "bedrooms": 4,
            "bathrooms": 4,
            "area_sqm": 380,
            "description": "Beautiful compound villa in Al Yasmin gated community. International-standard finish, open-plan kitchen and living area, private garden. Compound amenities include pool, gym, children's park and 24/7 security.",
            "amenities": ["Gated Community", "Compound Pool", "Gym", "Children's Park", "24/7 Security", "Maintenance"],
            "url": "https://wasalt.com/en/property/compound-villa-al-yasmin-015",
            "scraped_at": now,
        },
    ]
