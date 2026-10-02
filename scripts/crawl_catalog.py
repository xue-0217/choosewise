"""Small, bounded public-page collector. Drafts only; no database writes or JS execution."""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://www.logitech.com'
AGENT = 'ChoosewiseResearch'
USER_AGENT = AGENT + '/0.1 (+local product data sampling)'
MAX_BYTES = 2_000_000
JSON_STRING = r'"(?:\\.|[^"\\])*"'


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class Draft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    mode: Literal['real_candidate'] = 'real_candidate'
    review_status: Literal['pending'] = 'pending'
    recommendation_eligible: Literal[False] = False
    brand: str
    name: str
    variant_name: str
    sku: str
    category: Literal['keyboard', 'mouse']
    source_url: str
    retrieved_at: str
    source_locale: Literal['zh-cn'] = 'zh-cn'
    page_sha256: str
    dimensions_mm: dict[str, Decimal] = Field(default_factory=dict)
    weight_g: Decimal | None = Field(default=None, gt=0)
    connections_supported: list[Literal['bluetooth', 'receiver']] | None = None
    receiver_in_box: bool | None = None
    numpad: bool | None = None
    quiet: None = None
    price_minor: int | None = Field(default=None, strict=True, gt=0)
    currency: Literal['CNY'] = 'CNY'
    price_status: Literal['missing', 'invalid_placeholder', 'variant_price_observed']
    observed_price: dict
    claims: list[dict]
    issues: list[str]


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_json = False
        self.in_title = False
        self.buffers = []
        self.current = []
        self.title = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'script' and attributes.get('type', '').lower() == 'application/ld+json':
            self.in_json = True
            self.current = []
        if tag == 'title':
            self.in_title = True

    def handle_data(self, data):
        if self.in_json:
            self.current.append(data)
        if self.in_title:
            self.title.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.in_json:
            self.buffers.append(''.join(self.current))
            self.in_json = False
        if tag == 'title':
            self.in_title = False


def nodes(value):
    """Traverse schema graphs, not unrelated nested ProductModel entries."""
    if isinstance(value, list):
        for item in value:
            yield from nodes(item)
    elif isinstance(value, dict):
        yield value
        if '@graph' in value:
            yield from nodes(value['@graph'])


def literal_block(html: str, marker: str) -> str | None:
    """Bounded brace scanning of public embedded data. Never evaluate JavaScript."""
    matches = list(re.finditer(re.escape(marker), html))
    if len(matches) != 1:
        return None
    start = matches[0].end()
    if start >= len(html) or html[start] not in '{[':
        return None
    stack, quote, escaped = [], None, False
    for position in range(start, min(len(html), start + 100_000)):
        char = html[position]
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
        elif char in '\"\'':
            quote = char
        elif char in '{[':
            stack.append(char)
        elif char in '}]':
            if not stack or (stack.pop(), char) not in [('{', '}'), ('[', ']')]:
                return None
            if not stack:
                return html[start:position + 1]
    return None


def price_for_variant(product: dict, variant: dict):
    # AggregateOffer is family-level. Its 0 values do not imply a free product.
    aggregate = product.get('offers', {})
    raw = {key: aggregate.get(key) for key in ['@type', 'priceCurrency', 'lowPrice', 'highPrice', 'price', 'availability']} if isinstance(aggregate, dict) else {}
    if any(raw.get(key) == 0 for key in ['lowPrice', 'highPrice', 'price']):
        return None, 'invalid_placeholder', raw
    offer = variant.get('offers', {})
    if not isinstance(offer, dict) or offer.get('@type') != 'Offer' or offer.get('priceCurrency') != 'CNY':
        return None, 'missing', raw
    try:
        value = Decimal(str(offer['price']))
        if not value.is_finite() or value <= 0 or value * 100 != (value * 100).to_integral_value():
            return None, 'invalid_placeholder', raw
        if offer.get('availability') not in [None, 'https://schema.org/InStock']:
            return None, 'missing', raw
        raw = {key: offer.get(key) for key in ['@type', 'priceCurrency', 'price', 'availability', 'url']}
        return int(value * 100), 'variant_price_observed', raw
    except (KeyError, InvalidOperation, ValueError):
        return None, 'invalid_placeholder', raw


def extract_page(html: str, url: str, fetched_at: str, digest: str) -> Draft:
    parser = PageParser()
    parser.feed(html)
    graph = []
    for raw in parser.buffers:
        try:
            graph.extend(nodes(json.loads(raw)))
        except (ValueError, RecursionError):
            continue
    products = [node for node in graph if node.get('@type') == 'Product']
    if len(products) != 1:
        raise ValueError('PRODUCT_SCHEMA_MISSING_OR_AMBIGUOUS')
    product = products[0]
    category = {'keyboards': 'keyboard', 'mice': 'mouse'}.get(product.get('category'))
    if not category:
        raise ValueError('UNSUPPORTED_CATEGORY')
    requested_sku = urlsplit(url).path.rsplit('.', 1)[-1]
    variants = [model for model in product.get('model', []) if model.get('sku') == requested_sku]
    if len(variants) != 1:
        raise ValueError('REQUESTED_VARIANT_NOT_FOUND')
    variant = variants[0]
    claims = []

    def claim(field, value, locator, excerpt, scope='product_family'):
        claims.append(dict(field=field, value=value, source_url=url, locator=locator,
                           excerpt=excerpt[:100], evidence_type='manufacturer_spec', scope=scope, review_status='pending'))

    dimensions, weight = {}, None
    specs = literal_block(html, 'specsAndRequirements:')
    dimensions_block = literal_block(specs, 'productDimensions:') if specs else None
    if dimensions_block:
        pairs = re.findall(r'\{facet:(' + JSON_STRING + r'),value:(' + JSON_STRING + r')', dimensions_block)
        for raw_name, raw_value in pairs:
            facet, value = json.loads(raw_name), json.loads(raw_value)
            match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(毫米|克)', value)
            if not match or Decimal(match[1]) <= 0:
                continue
            if facet in ['高', '宽', '深'] and match[2] == '毫米':
                field = {'高': 'height', '宽': 'width', '深': 'depth'}[facet]
                dimensions[field] = Decimal(match[1])
                claim('dimensions_mm.' + field, match[1], 'specsAndRequirements.productDimensions', f'{facet}: {value}')
            elif facet == '重量' and match[2] == '克':
                weight = Decimal(match[1])
                claim('weight_g', match[1], 'specsAndRequirements.productDimensions', f'{facet}: {value}')
    connections = None
    technical = literal_block(html, 'inRiverTechSpecs:')
    connectivity = literal_block(technical, 'connectivity:') if technical else None
    if connectivity:
        pattern = r'facet:(' + JSON_STRING + r'),values:\[\{value:(' + JSON_STRING + r'),variants:\[\],universal:true'
        for raw_name, raw_value in re.findall(pattern, connectivity):
            facet, value = json.loads(raw_name), json.loads(raw_value)
            if facet == '连接类型' and value == '蓝牙低功耗技术':
                connections = (connections or []) + ['bluetooth']
                claim('connections_supported', 'bluetooth', 'inRiverTechSpecs.connectivity', f'{facet}: {value}')
            if facet == '连接类型支持' and re.fullmatch(r'兼容 Logi Bolt USB 接收器（需另购）', value):
                connections = (connections or []) + ['receiver']
                claim('connections_supported', 'receiver', 'inRiverTechSpecs.connectivity', value)
    receiver_in_box, numpad = None, None
    for node in graph:
        if node.get('@type') != 'FAQPage':
            continue
        for question in node.get('mainEntity', []):
            name = question.get('name', '')
            answer = question.get('acceptedAnswer', {}).get('text', '')
            if name == '是否附带 USB 无线接收器？' and answer.startswith('不附带'):
                receiver_in_box = False
                claim('receiver_in_box', False, 'FAQPage:receiver', answer[:50], 'page_selected_variant')
            if name == '是否内置数字小键盘？' and answer.startswith('没有'):
                numpad = False
                claim('numpad', False, 'FAQPage:numpad', answer[:50], 'product_family')
    price, price_status, observed = price_for_variant(product, variant)
    issues = ['HUMAN_REVIEW_REQUIRED', 'QUIET_NOT_VERIFIED', 'WEIGHT_BATTERY_SCOPE_REQUIRES_REVIEW']
    if price is None:
        issues.append('NO_USABLE_VARIANT_PRICE')
    if weight is None:
        issues.append('WEIGHT_NOT_EXTRACTED')
    if connections is None:
        issues.append('CONNECTION_NOT_EXTRACTED')
    brand = product.get('brand', 'Logitech')
    if isinstance(brand, dict):
        brand = brand.get('name', 'Logitech')
    return Draft(id='logitech-cn-' + requested_sku, brand=brand, name=product['name'], variant_name=variant['name'],
                 sku=requested_sku, category=category, source_url=url, retrieved_at=fetched_at, page_sha256=digest,
                 dimensions_mm=dimensions, weight_g=weight, connections_supported=connections,
                 receiver_in_box=receiver_in_box, numpad=numpad, price_minor=price,
                 price_status=price_status, observed_price=observed, claims=claims, issues=issues)


def allowed_url(url):
    parsed = urlsplit(url)
    return parsed.scheme == 'https' and parsed.netloc == 'www.logitech.com' and parsed.path.startswith('/zh-cn/shop/p/') and not parsed.query and not parsed.fragment


def fetch_page(client, url, robots, pause):
    for _ in range(4):
        if not allowed_url(url) or not robots.can_fetch(AGENT, url):
            raise ValueError('SOURCE_NOT_ALLOWED')
        time.sleep(pause)
        with client.stream('GET', url) as response:
            if response.status_code in [301, 302, 303, 307, 308]:
                url = urljoin(url, response.headers.get('location', ''))
                continue
            response.raise_for_status()
            if 'text/html' not in response.headers.get('content-type', ''):
                raise ValueError('NOT_HTML')
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('PAGE_TOO_LARGE')
                chunks.append(chunk)
            body = b''.join(chunks)
            # This adapter accepts UTF-8; changed encoding fails closed.
            return body.decode('utf-8-sig'), url, hashlib.sha256(body).hexdigest()
    raise ValueError('TOO_MANY_REDIRECTS')


def collect(sources, client, pause=1.5):
    started_at = timestamp()
    robots_response = client.get(ORIGIN + '/robots.txt')
    robots_response.raise_for_status()
    robots = RobotFileParser(ORIGIN + '/robots.txt')
    robots.parse(robots_response.text.splitlines())
    pause = max(pause, float(robots.crawl_delay(AGENT) or 0))
    records, attempts = [], []
    seen = set()
    for source in sources:
        url = source['url']
        if url in seen:
            attempts.append(dict(url=url, status='skipped_duplicate'))
            continue
        seen.add(url)
        try:
            html, final_url, digest = fetch_page(client, url, robots, pause)
            if urlsplit(url).path.rsplit('.', 1)[-1] != urlsplit(final_url).path.rsplit('.', 1)[-1]:
                raise ValueError('VARIANT_REDIRECT_CHANGED')
            draft = extract_page(html, final_url, timestamp(), digest)
            if any(record.id == draft.id for record in records):
                attempts.append(dict(url=url, status='skipped_duplicate_variant'))
                continue
            records.append(draft)
            attempts.append(dict(url=url, final_url=final_url, http_status=200, status='collected', sku=draft.sku))
        except httpx.HTTPStatusError as error:
            attempts.append(dict(url=url, status='http_error', http_status=error.response.status_code))
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            # Never store request headers or arbitrary remote error bodies.
            known = {'SOURCE_NOT_ALLOWED', 'PRODUCT_SCHEMA_MISSING_OR_AMBIGUOUS', 'UNSUPPORTED_CATEGORY', 'REQUESTED_VARIANT_NOT_FOUND', 'VARIANT_REDIRECT_CHANGED', 'NOT_HTML', 'PAGE_TOO_LARGE', 'TOO_MANY_REDIRECTS'}
            code = str(error) if str(error) in known else type(error).__name__
            attempts.append(dict(url=url, status='rejected', error=code))
    report = dict(started_at=started_at, finished_at=timestamp(), adapter_version='logitech-cn-v0.1',
                  robots_url=ORIGIN + '/robots.txt', robots_sha256=hashlib.sha256(robots_response.content).hexdigest(),
                  pause_seconds=pause, attempted=len(attempts), collected=len(records),
                  usable_prices=sum(record.price_minor is not None for record in records), attempts=attempts,
                  database_modified=False, recommendation_mode_changed=False)
    return records, report


def main():
    parser = argparse.ArgumentParser(description='低频采集罗技中国官网公开商品页面，结果仅进入待审核区。')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'scripts/crawl_sources.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/curated/crawl-runs')
    args = parser.parse_args()
    sources = json.loads(args.manifest.read_text(encoding='utf-8'))['sources']
    if not 1 <= len(sources) <= 20:
        parser.error('每批只接受 1～20 个公开页面')
    with httpx.Client(timeout=30, headers={'User-Agent': USER_AGENT}, follow_redirects=False) as client:
        records, report = collect(sources, client)
    folder = args.output / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True, exist_ok=False)
    candidates = dict(schema_version='real-candidate-v0.1', status='pending_review', products=[record.model_dump(mode='json') for record in records])
    (folder / 'candidates.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'collected': report['collected'], 'attempted': report['attempted'], 'usable_prices': report['usable_prices'], 'output': str(folder)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
