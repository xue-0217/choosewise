from datetime import timedelta

from app.db import Product, now
from app.recommendation import analyze_demo, build_recommendation, eligible
from app.schemas import Needs


def needs(**changes):
    return Needs(target='keyboard_mouse_bundle', budget_minor=30000, primary_use='coding', **changes)


def product(id, category, price, **changes):
    return Product(id=id, category=category, name=id, version='test', mode='demo', reviewed='demo',
                   price_observed_at=now(), data=dict(price_minor=price, connections=['wired'], quiet=None,
                   numpad=False, note='测试资料', **changes))


def test_integer_bundle_budget_boundary():
    products = [product('k', 'keyboard', 20000), product('m', 'mouse', 10001)]
    assert build_recommendation(products, needs(), 7, True)['status'] == 'no_match'
    products[1].data['price_minor'] = 10000
    scheme = build_recommendation(products, needs(), 7, True)['schemes'][0]
    assert scheme['total_minor'] == 30000 and scheme['remaining_minor'] == 0


def test_unknown_sound_not_accepted_as_quiet():
    item = product('k', 'keyboard', 20000)
    assert not eligible(item, needs(quiet='required'), 7, True)
    item.data['quiet'] = True
    assert eligible(item, needs(quiet='required'), 7, True)


def test_stale_conditional_and_real_data_excluded():
    item = product('k', 'keyboard', 20000)
    item.price_observed_at = now() - timedelta(days=8)
    assert not eligible(item, needs(), 7, True)
    item.price_observed_at = now()
    item.data['price_condition'] = 'member'
    assert not eligible(item, needs(), 7, True)
    item.data['price_condition'] = 'public'
    item.mode = 'real'
    assert not eligible(item, needs(), 7, True)


def test_budget_and_connection_conflict_requires_clarification():
    output = analyze_demo(needs(), '预算200元，必须有线，必须无线')
    assert output['needs']['budget_minor'] == 30000
    assert {q['field'] for q in output['questions']} == {'budget_minor', 'connection'}
    assert analyze_demo(needs(), '必须有线')['needs']['connection'] == 'wired'


def test_boolean_price_is_invalid():
    assert not eligible(product('k', 'keyboard', True), needs(), 7, True)
