import json
from decimal import Decimal

import httpx
import pytest

from scripts.crawl_catalog import collect, extract_page, literal_block, price_for_variant


URL = 'https://www.logitech.com/zh-cn/shop/p/test-mouse.910-test'


def page(sku='910-test', offers=None, extra_schema=None, embedded=True):
    product = {'@type': 'Product', 'brand': 'Logitech', 'name': '测试鼠标', 'category': 'mice',
               'offers': {'@type': 'AggregateOffer', 'lowPrice': 0, 'highPrice': 0, 'priceCurrency': 'CNY'},
               'model': [{'sku': sku, 'name': '测试鼠标 - 玫瑰粉', 'offers': offers or {}}]}
    graph = {'@graph': [product] + (extra_schema or [])}
    html = '<title>测试</title><script type="application/ld+json">' + json.dumps(graph) + '</script>'
    if embedded:
        html += '<script>data={specsAndRequirements:{productDimensions:{specs:{spec:[{facet:"重量",value:"73.8 克",__proto__:null},{facet:"宽",value:"60 毫米",__proto__:null}]}}},inRiverTechSpecs:{connectivity:[{facet:"连接类型",values:[{value:"蓝牙低功耗技术",variants:[],universal:true}]}]}};</script>'
    return html


def test_extracts_decimal_weight_and_keeps_unverified_fields_unknown():
    draft = extract_page(page(), URL, '2026-10-02T00:00:00+00:00', 'a' * 64)
    assert draft.sku == '910-test' and draft.weight_g == Decimal('73.8')
    assert draft.dimensions_mm == {'width': Decimal('60')}
    assert draft.connections_supported == ['bluetooth']
    assert draft.price_minor is None and draft.price_status == 'invalid_placeholder'
    assert draft.quiet is None and draft.numpad is None and draft.receiver_in_box is None
    assert not draft.recommendation_eligible and draft.review_status == 'pending'
    assert all(item['source_url'] == URL and item['review_status'] == 'pending' for item in draft.claims)


def test_unknown_specs_stay_unknown():
    draft = extract_page(page(embedded=False), URL, 'time', 'hash')
    assert draft.weight_g is None and draft.connections_supported is None
    assert draft.dimensions_mm == {} and 'WEIGHT_NOT_EXTRACTED' in draft.issues


def test_selected_variant_must_match_source_sku():
    with pytest.raises(ValueError, match='REQUESTED_VARIANT_NOT_FOUND'):
        extract_page(page(sku='different'), URL, 'time', 'hash')


@pytest.mark.parametrize('value', [0, -5, 'NaN', 'Infinity', '10.123', 'bad'])
def test_invalid_prices_are_never_budget_prices(value):
    product = {'offers': {}}
    variant = {'offers': {'@type': 'Offer', 'price': value, 'priceCurrency': 'CNY'}}
    assert price_for_variant(product, variant)[0] is None


def test_family_price_not_assigned_to_color_variant_and_usd_not_converted():
    assert price_for_variant({'offers': {'@type': 'AggregateOffer', 'lowPrice': 99, 'priceCurrency': 'CNY'}}, {})[0] is None
    assert price_for_variant({}, {'offers': {'@type': 'Offer', 'price': '24.99', 'priceCurrency': 'USD'}})[0] is None
    assert price_for_variant({}, {'offers': {'@type': 'Offer', 'price': '99.90', 'priceCurrency': 'CNY'}})[0] == 9990


def test_balanced_scan_respects_strings_and_does_not_execute_code():
    assert literal_block('marker:{text:"} [",nested:{ok:true}}; alert(1)', 'marker:') == '{text:"} [",nested:{ok:true}}'
    assert literal_block('marker:{broken:true', 'marker:') is None
    assert literal_block('marker:{} marker:{}', 'marker:') is None


def test_collect_handles_duplicate_and_404():
    requested = []
    bad = 'https://www.logitech.com/zh-cn/shop/p/missing'

    def handle(request):
        requested.append(str(request.url))
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nDisallow: /api/\n')
        if str(request.url) == bad:
            return httpx.Response(404)
        return httpx.Response(200, text=page(), headers={'Content-Type': 'text/html'})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        records, report = collect([{'url': URL}, {'url': URL}, {'url': bad}], client, pause=0)
    assert len(records) == 1 and requested.count(URL) == 1
    assert report['attempts'][1]['status'] == 'skipped_duplicate'
    assert report['attempts'][2] == {'url': bad, 'status': 'http_error', 'http_status': 404}


def test_robots_blocks_page_and_redirect_cannot_leave_allowlist():
    requested = []

    def handle(request):
        requested.append(str(request.url))
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nDisallow: /zh-cn/shop/p/blocked\n')
        return httpx.Response(302, headers={'Location': 'https://other.example/secret'})

    blocked = 'https://www.logitech.com/zh-cn/shop/p/blocked.910-test'
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        records, report = collect([{'url': blocked}, {'url': URL}], client, pause=0)
    assert records == [] and blocked not in requested
    assert all(item['error'] == 'SOURCE_NOT_ALLOWED' for item in report['attempts'])
    assert not any('other.example' in item for item in requested)


def test_robots_failure_never_fetches_product():
    requested = []

    def handle(request):
        requested.append(str(request.url))
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            collect([{'url': URL}], client, pause=0)
    assert requested == ['https://www.logitech.com/robots.txt']
