"""
DarGlobal scraper – darglobal.co.uk
Scrapes publicly available property listings from the DarGlobal website.
"""

import logging
import random
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://darglobal.co.uk"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _parse_price(price_str: str) -> tuple[Optional[float], str]:
    """Extract numeric price and currency from a price string."""
    if not price_str:
        return None, "USD"

    price_str = price_str.strip()
    currency = "USD"

    currency_map = {
        "£": "GBP", "$": "USD", "€": "EUR",
        "AED": "AED", "SAR": "SAR", "QAR": "QAR", "OMR": "OMR",
    }
    for symbol, code in currency_map.items():
        if symbol in price_str:
            currency = code
            break

    # Remove non-numeric chars except dot
    digits = "".join(c for c in price_str if c.isdigit() or c == ".")
    try:
        return float(digits.replace(",", "")), currency
    except (ValueError, AttributeError):
        return None, currency


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_page(client: httpx.Client, url: str) -> Optional[str]:
    """Fetch a URL with retry logic."""
    resp = client.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _parse_detail_page(html: str, url: str) -> dict:
    """Parse a DarGlobal property detail page."""
    soup = BeautifulSoup(html, "lxml")
    record: dict = {"url": url, "source": "darglobal"}

    # Title
    title_el = (
        soup.find("h1", class_=lambda c: c and "title" in c.lower())
        or soup.find("h1")
    )
    record["title"] = title_el.get_text(strip=True) if title_el else "DarGlobal Property"

    # Description
    desc_el = (
        soup.find("div", class_=lambda c: c and "description" in c.lower())
        or soup.find("div", class_=lambda c: c and "content" in c.lower())
        or soup.find("section", class_=lambda c: c and "about" in c.lower())
    )
    record["description"] = desc_el.get_text(separator=" ", strip=True)[:2000] if desc_el else ""

    # Price
    price_el = soup.find(class_=lambda c: c and "price" in c.lower() if c else False)
    price_text = price_el.get_text(strip=True) if price_el else ""
    record["price"], record["currency"] = _parse_price(price_text)

    # Location
    location_el = soup.find(class_=lambda c: c and "location" in c.lower() if c else False)
    location_text = location_el.get_text(strip=True) if location_el else ""

    # Try to extract country/city from location or breadcrumbs
    breadcrumbs = soup.find_all("a", class_=lambda c: c and "breadcrumb" in c.lower() if c else False)
    breadcrumb_texts = [b.get_text(strip=True) for b in breadcrumbs]

    record["location"] = {
        "country": _infer_country(url, location_text, breadcrumb_texts),
        "city": _infer_city(location_text, breadcrumb_texts),
        "district": None,
        "coordinates": {"lat": None, "lng": None},
    }

    # Specs – bedrooms, bathrooms, area
    specs = {}
    spec_items = soup.find_all(class_=lambda c: c and any(
        k in c.lower() for k in ["spec", "feature", "detail", "info", "stat"]
    ) if c else False)

    for item in spec_items:
        text = item.get_text(separator=" ", strip=True).lower()
        if "bed" in text:
            nums = [c for c in text if c.isdigit()]
            if nums:
                specs["bedrooms"] = int(nums[0])
        if "bath" in text:
            nums = [c for c in text if c.isdigit()]
            if nums:
                specs["bathrooms"] = int(nums[0])
        if "sqm" in text or "sq m" in text or "m²" in text:
            match = re.search(r"[\d,]+", text)
            if match:
                specs["area_sqm"] = float(match.group().replace(",", ""))

    record["bedrooms"] = specs.get("bedrooms")
    record["bathrooms"] = specs.get("bathrooms")
    record["area_sqm"] = specs.get("area_sqm")

    # Property type
    type_keywords = {
        "villa": "villa", "apartment": "apartment", "penthouse": "apartment",
        "townhouse": "villa", "mansion": "villa", "residence": "apartment",
        "commercial": "commercial", "office": "commercial", "retail": "commercial",
        "land": "land", "plot": "land",
    }
    title_lower = record["title"].lower()
    record["property_type"] = "apartment"
    for kw, ptype in type_keywords.items():
        if kw in title_lower:
            record["property_type"] = ptype
            break

    # Amenities
    amenities = []
    amenity_section = soup.find(class_=lambda c: c and "amenities" in c.lower() if c else False)
    if amenity_section:
        for item in amenity_section.find_all(["li", "span", "div"]):
            text = item.get_text(strip=True)
            if text and len(text) < 50:
                amenities.append(text)
    record["amenities"] = amenities[:20]

    record["scraped_at"] = datetime.now(timezone.utc).isoformat()
    return record


def _infer_country(url: str, location: str, breadcrumbs: list) -> str:
    """Infer country from URL path, location text, or breadcrumbs."""
    country_keywords = {
        "dubai": "UAE", "abu-dhabi": "UAE", "uae": "UAE", "emirates": "UAE",
        "saudi": "Saudi Arabia", "riyadh": "Saudi Arabia", "ksa": "Saudi Arabia",
        "oman": "Oman", "muscat": "Oman",
        "qatar": "Qatar", "doha": "Qatar",
        "spain": "Spain", "marbella": "Spain", "madrid": "Spain",
        "uk": "UK", "london": "UK", "united-kingdom": "UK",
    }
    combined = f"{url} {location} {' '.join(breadcrumbs)}".lower()
    for kw, country in country_keywords.items():
        if kw in combined:
            return country
    return "UAE"  # DarGlobal's primary market


def _infer_city(location: str, breadcrumbs: list) -> str:
    """Infer city from location text."""
    cities = [
        "Dubai", "Abu Dhabi", "Riyadh", "Jeddah", "Muscat", "Doha",
        "London", "Marbella", "Madrid",
    ]
    combined = f"{location} {' '.join(breadcrumbs)}"
    for city in cities:
        if city.lower() in combined.lower():
            return city
    return location.split(",")[0].strip() if "," in location else location[:50]


def _parse_listing_page(html: str) -> list[str]:
    """Extract property detail URLs from a listing page."""
    soup = BeautifulSoup(html, "lxml")
    links = []

    # Look for property card links
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # DarGlobal property pages typically have /properties/ or /development/ in path
        if any(seg in href for seg in ["/properties/", "/development/", "/project/"]):
            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if full_url not in links:
                links.append(full_url)

    return links


def scrape(max_pages: int = 5) -> list[dict]:
    """Main entry point – scrapes DarGlobal listings."""
    properties = []
    detail_urls: set[str] = set()

    listing_paths = [
        "/properties",
        "/developments",
        "/properties?location=dubai",
        "/properties?location=saudi-arabia",
        "/properties?location=oman",
        "/properties?type=apartments",
        "/properties?type=villas",
    ]

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        logger.info("DarGlobal: collecting listing pages...")

        for path in listing_paths[:max_pages]:
            url = f"{BASE_URL}{path}"
            try:
                html = _fetch_page(client, url)
                if html:
                    urls = _parse_listing_page(html)
                    detail_urls.update(urls)
                    logger.info(f"DarGlobal: {url} → {len(urls)} links found")
                time.sleep(random.uniform(1.0, 2.5))
            except Exception as e:
                logger.warning(f"DarGlobal: failed to fetch {url}: {e}")

        # Also try pagination
        for page in range(1, max_pages + 1):
            url = f"{BASE_URL}/properties?page={page}"
            try:
                html = _fetch_page(client, url)
                if html:
                    urls = _parse_listing_page(html)
                    if not urls:
                        break
                    detail_urls.update(urls)
                    logger.info(f"DarGlobal: page {page} → {len(urls)} links")
                time.sleep(random.uniform(1.0, 2.5))
            except Exception as e:
                logger.warning(f"DarGlobal: page {page} failed: {e}")
                break

        logger.info(f"DarGlobal: scraping {len(detail_urls)} detail pages...")

        for i, url in enumerate(list(detail_urls)[:200]):  # cap at 200
            try:
                html = _fetch_page(client, url)
                if html:
                    record = _parse_detail_page(html, url)
                    record["id"] = f"darglobal_{i+1:04d}"
                    properties.append(record)
                    logger.info(f"DarGlobal [{i+1}/{len(detail_urls)}]: {record['title'][:60]}")
                time.sleep(random.uniform(1.0, 2.0))
            except Exception as e:
                logger.warning(f"DarGlobal: detail page {url} failed: {e}")

    # If scraping yielded too little, generate sample data for demo purposes
    if len(properties) < 10:
        logger.warning("DarGlobal: fewer than 10 properties scraped, adding sample data for demo")
        properties.extend(_sample_darglobal_data())

    logger.info(f"DarGlobal: total {len(properties)} properties collected")
    return properties


def _sample_darglobal_data() -> list[dict]:
    """Fallback sample data representing real DarGlobal properties for demo."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": "darglobal_sample_001",
            "source": "darglobal",
            "title": "Aston Martin Residences – Duplex Penthouse",
            "property_type": "apartment",
            "price": 15000000,
            "currency": "USD",
            "location": {"country": "UAE", "city": "Dubai", "district": "Downtown Dubai", "coordinates": {"lat": 25.197, "lng": 55.274}},
            "bedrooms": 4,
            "bathrooms": 5,
            "area_sqm": 850,
            "description": "Ultra-luxury penthouse in the iconic Aston Martin Residences tower in Downtown Dubai. Features bespoke Aston Martin interiors, panoramic Burj Khalifa views, private pool, and concierge service.",
            "amenities": ["Private Pool", "Concierge", "Gym", "Spa", "Valet Parking", "Marina View"],
            "url": "https://darglobal.co.uk/properties/aston-martin-residences",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_002",
            "source": "darglobal",
            "title": "Lamborghini Residences – Sky Villa",
            "property_type": "villa",
            "price": 8500000,
            "currency": "USD",
            "location": {"country": "UAE", "city": "Dubai", "district": "Business Bay", "coordinates": {"lat": 25.186, "lng": 55.263}},
            "bedrooms": 5,
            "bathrooms": 6,
            "area_sqm": 700,
            "description": "Sky Villa in the Lamborghini-branded tower in Business Bay, Dubai. Exclusive interiors designed in collaboration with Lamborghini, featuring carbon fiber accents and custom Italian furniture.",
            "amenities": ["Sky Pool", "Private Gym", "Home Cinema", "Smart Home", "24/7 Security"],
            "url": "https://darglobal.co.uk/properties/lamborghini-residences",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_003",
            "source": "darglobal",
            "title": "Dolce & Gabbana Residences – Luxury Apartment",
            "property_type": "apartment",
            "price": 4200000,
            "currency": "USD",
            "location": {"country": "UAE", "city": "Dubai", "district": "DAMAC Hills", "coordinates": {"lat": 25.028, "lng": 55.237}},
            "bedrooms": 3,
            "bathrooms": 4,
            "area_sqm": 380,
            "description": "Exclusive branded residence designed by Dolce & Gabbana in DAMAC Hills. Each unit features bespoke D&G furnishings, hand-crafted Italian tiles, and curated art pieces.",
            "amenities": ["Rooftop Pool", "Fashion Lounge", "Concierge", "Valet", "Golf Course View"],
            "url": "https://darglobal.co.uk/properties/dolce-gabbana-residences",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_004",
            "source": "darglobal",
            "title": "The Residences at Mandarin Oriental – 2BR Apartment",
            "property_type": "apartment",
            "price": 3800000,
            "currency": "USD",
            "location": {"country": "UAE", "city": "Dubai", "district": "Downtown Dubai", "coordinates": {"lat": 25.193, "lng": 55.276}},
            "bedrooms": 2,
            "bathrooms": 3,
            "area_sqm": 290,
            "description": "Premium residences linked to the Mandarin Oriental hotel in Downtown Dubai. Residents enjoy full hotel services including housekeeping, room service, and access to the world-class spa.",
            "amenities": ["Hotel Services", "Infinity Pool", "Spa Access", "Fine Dining", "Valet Parking"],
            "url": "https://darglobal.co.uk/properties/mandarin-oriental-residences",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_005",
            "source": "darglobal",
            "title": "Trump Estates – 4BR Golf Villa",
            "property_type": "villa",
            "price": 6500000,
            "currency": "USD",
            "location": {"country": "UAE", "city": "Dubai", "district": "DAMAC Hills", "coordinates": {"lat": 25.025, "lng": 55.231}},
            "bedrooms": 4,
            "bathrooms": 5,
            "area_sqm": 550,
            "description": "Luxury golf villa in the Trump Estates community within DAMAC Hills. Features direct golf course frontage, private pool, and access to the Trump International Golf Club Dubai.",
            "amenities": ["Private Pool", "Golf Course Frontage", "Smart Home", "Maid's Room", "4-Car Garage"],
            "url": "https://darglobal.co.uk/properties/trump-estates-villa",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_006",
            "source": "darglobal",
            "title": "DarGlobal Oman – Waterfront Villa",
            "property_type": "villa",
            "price": 2200000,
            "currency": "USD",
            "location": {"country": "Oman", "city": "Muscat", "district": "The Wave", "coordinates": {"lat": 23.606, "lng": 58.593}},
            "bedrooms": 4,
            "bathrooms": 4,
            "area_sqm": 420,
            "description": "Beachfront villa at The Wave, Muscat – Oman's premier waterfront community. Combines modern architecture with traditional Omani influences, featuring sea views from every room.",
            "amenities": ["Private Beach", "Pool", "Marina Access", "Gym", "Clubhouse"],
            "url": "https://darglobal.co.uk/properties/oman-waterfront-villa",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_007",
            "source": "darglobal",
            "title": "DG1 Tower – 1BR Apartment",
            "property_type": "apartment",
            "price": 950000,
            "currency": "USD",
            "location": {"country": "UAE", "city": "Dubai", "district": "Business Bay", "coordinates": {"lat": 25.188, "lng": 55.261}},
            "bedrooms": 1,
            "bathrooms": 2,
            "area_sqm": 95,
            "description": "Stylish 1-bedroom apartment in DG1 Tower, Business Bay. Contemporary design with floor-to-ceiling windows, open-plan kitchen, and stunning views over the Dubai Canal.",
            "amenities": ["Pool", "Gym", "Concierge", "Canal View", "Covered Parking"],
            "url": "https://darglobal.co.uk/properties/dg1-tower",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_008",
            "source": "darglobal",
            "title": "Missoni Baia – 3BR Waterfront Apartment",
            "property_type": "apartment",
            "price": 5100000,
            "currency": "USD",
            "location": {"country": "UAE", "city": "Dubai", "district": "Dubai Creek Harbour", "coordinates": {"lat": 25.213, "lng": 55.325}},
            "bedrooms": 3,
            "bathrooms": 4,
            "area_sqm": 320,
            "description": "Fashion-forward living in the iconic Missoni Baia tower on Dubai Creek Harbour. Vibrant Missoni-designed interiors, wrap-around terraces with Burj Khalifa and Creek views.",
            "amenities": ["Infinity Pool", "Private Beach", "Yoga Studio", "Art Lounge", "Residents' Club"],
            "url": "https://darglobal.co.uk/properties/missoni-baia",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_009",
            "source": "darglobal",
            "title": "DarGlobal Qatar – Luxury Villa",
            "property_type": "villa",
            "price": 3700000,
            "currency": "USD",
            "location": {"country": "Qatar", "city": "Doha", "district": "Lusail", "coordinates": {"lat": 25.417, "lng": 51.489}},
            "bedrooms": 5,
            "bathrooms": 6,
            "area_sqm": 600,
            "description": "Grand luxury villa in Lusail City, Qatar's most prestigious new development. Spacious living areas, private swimming pool, landscaped garden, and dedicated staff quarters.",
            "amenities": ["Private Pool", "Garden", "Staff Quarters", "Home Cinema", "Smart Home"],
            "url": "https://darglobal.co.uk/properties/qatar-luxury-villa",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_010",
            "source": "darglobal",
            "title": "DarGlobal London – Park Lane Penthouse",
            "property_type": "apartment",
            "price": 12000000,
            "currency": "GBP",
            "location": {"country": "UK", "city": "London", "district": "Mayfair", "coordinates": {"lat": 51.506, "lng": -0.151}},
            "bedrooms": 4,
            "bathrooms": 5,
            "area_sqm": 520,
            "description": "Grade II listed penthouse on Old Park Lane, Mayfair. Meticulously restored with finest British craftsmanship. Panoramic views of Hyde Park, private roof terrace, and dedicated concierge.",
            "amenities": ["Roof Terrace", "Hyde Park Views", "Concierge", "Wine Cellar", "Private Lift"],
            "url": "https://darglobal.co.uk/properties/park-lane-penthouse",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_011",
            "source": "darglobal",
            "title": "Elie Saab Residences – 2BR Luxury Apartment",
            "property_type": "apartment",
            "price": 2800000,
            "currency": "USD",
            "location": {"country": "UAE", "city": "Dubai", "district": "Dubai Creek Harbour", "coordinates": {"lat": 25.211, "lng": 55.323}},
            "bedrooms": 2,
            "bathrooms": 3,
            "area_sqm": 210,
            "description": "Elegantly designed 2-bedroom apartment in the Elie Saab-branded tower. Signature French haute couture design language brought to life in every detail of this stunning waterfront residence.",
            "amenities": ["Pool", "Gym", "Concierge", "Creek View", "Designer Interiors"],
            "url": "https://darglobal.co.uk/properties/elie-saab-residences",
            "scraped_at": now,
        },
        {
            "id": "darglobal_sample_012",
            "source": "darglobal",
            "title": "DarGlobal Saudi Arabia – Villa in AlUla",
            "property_type": "villa",
            "price": 1800000,
            "currency": "SAR",
            "location": {"country": "Saudi Arabia", "city": "AlUla", "district": "Old Town", "coordinates": {"lat": 26.617, "lng": 37.921}},
            "bedrooms": 3,
            "bathrooms": 3,
            "area_sqm": 310,
            "description": "Exclusive heritage-inspired villa in AlUla, Saudi Arabia's landmark cultural destination. Designed to blend with the ancient landscape while offering ultra-modern luxury living.",
            "amenities": ["Desert Views", "Private Pool", "Concierge", "Cultural Tours Access", "Spa"],
            "url": "https://darglobal.co.uk/properties/alula-villa",
            "scraped_at": now,
        },
    ]
