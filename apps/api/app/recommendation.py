import itertools
import re
from datetime import timedelta, timezone

from .db import Product, now
from .schemas import Needs


USE_LABELS = {'coding': '写代码', 'office': '日常办公', 'gaming': '游戏', 'portable': '随身携带'}
CONNECTION_LABELS = {'wired': '有线', 'bluetooth': '蓝牙', 'receiver': '接收器'}


def analyze_demo(input_needs: Needs, text: str) -> dict:
    values = input_needs.model_dump()
    values['text'] = text
    questions = []
    amount = re.search(r'(?:预算|降到|改为|改到|不超过)\s*(\d+(?:\.\d{1,2})?)\s*(?:元|块)?', text)
    if amount:
        import decimal
        mentioned = int(decimal.Decimal(amount.group(1)) * 100)
        if mentioned != values['budget_minor']:
            questions.append({'field': 'budget_minor', 'message': f'文字中的预算为 {mentioned / 100:g} 元，与输入框不同，请修改预算后再确认。'})
    if re.search(r'必须蓝牙|只要蓝牙|要蓝牙|蓝牙连接', text):
        values['connection'] = 'bluetooth'
    elif re.search(r'必须无线|只要无线|不要有线|要无线', text):
        values['connection'] = 'wireless'
    elif re.search(r'只要有线|必须有线|有线连接', text):
        values['connection'] = 'wired'
    if re.search(r'必须安静|必须静音|一定要安静', text):
        values['quiet'] = 'required'
    elif any(word in text for word in ['安静', '静音', '不吵', '轻声']):
        values['quiet'] = 'prefer' if values['quiet'] == 'any' else values['quiet']
    if re.search(r'不要数字区|不需要数字区|不带数字区', text):
        values['numpad'] = 'excluded'
    elif re.search(r'必须数字区|需要数字区|要数字小键盘|带数字区', text):
        values['numpad'] = 'required'
    if re.search(r'只要有线|必须有线', text) and re.search(r'必须无线|只要无线|必须蓝牙|只要蓝牙', text):
        questions.append({'field': 'connection', 'message': '“只要有线”与无线要求冲突，请在连接方式中选择最终要求。'})
    return {'needs': Needs.model_validate(values).model_dump(), 'questions': questions, 'mode': 'demo', 'summary': '已按演示规则整理需求，请确认后生成推荐。'}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def eligible(product: Product, needs: Needs, max_age_days: int, demo: bool) -> bool:
    data = product.data
    if product.mode != ('demo' if demo else 'real'):
        return False
    if not demo and product.reviewed != 'verified':
        return False
    if type(data.get('price_minor')) is not int or data['price_minor'] <= 0:
        return False
    if utc(product.price_observed_at) < now() - timedelta(days=max_age_days):
        return False
    if data.get('price_condition', 'public') != 'public' or data.get('availability') == 'unavailable':
        return False
    modes = data.get('connections', [])
    if needs.connection == 'wireless' and not ({'bluetooth', 'receiver'} & set(modes)):
        return False
    if needs.connection in ('bluetooth', 'wired') and needs.connection not in modes:
        return False
    if needs.quiet == 'required' and data.get('quiet') is not True:
        return False
    if product.category == 'keyboard':
        if needs.numpad == 'required' and data.get('numpad') is not True:
            return False
        if needs.numpad == 'excluded' and data.get('numpad') is not False:
            return False
    if not demo and not data.get('evidence_ids'):
        return False
    return True


def score(product: Product, needs: Needs) -> int:
    data = product.data
    points = 0
    if needs.quiet != 'any' and data.get('quiet') is True:
        points += 6
    if needs.primary_use == 'gaming' and data.get('gaming') is True:
        points += 7
    if needs.primary_use == 'portable' and data.get('portable') is True:
        points += 7
    if needs.primary_use == 'office' and product.category == 'keyboard' and data.get('numpad') is True:
        points += 4
    if needs.primary_use == 'coding' and product.category == 'keyboard' and data.get('layout') in ['75% 配列', '87 键']:
        points += 4
    if needs.primary_use in ['coding', 'office'] and data.get('quiet') is True:
        points += 2
    return points


def public_product(product: Product) -> dict:
    data = dict(product.data)
    data.update(id=product.id, name=product.name, category=product.category, version=product.version,
                price_observed_at=utc(product.price_observed_at).isoformat(), mode=product.mode)
    data['connection_labels'] = [CONNECTION_LABELS.get(item, item) for item in data.get('connections', [])]
    return data


def build_recommendation(products: list[Product], needs: Needs, max_age_days: int, demo: bool) -> dict:
    filtered = [p for p in products if eligible(p, needs, max_age_days, demo)]
    if needs.target == 'keyboard_mouse_bundle':
        groups = list(itertools.product([p for p in filtered if p.category == 'keyboard'], [p for p in filtered if p.category == 'mouse']))
    else:
        groups = [(p,) for p in filtered if p.category == needs.target]
    groups = [g for g in groups if sum(p.data['price_minor'] for p in g) <= needs.budget_minor]
    groups.sort(key=lambda group: (-sum(score(p, needs) for p in group), sum(p.data['price_minor'] for p in group), tuple(p.id for p in group)))
    distinct = []
    for group in groups:
        if distinct and needs.target == 'keyboard_mouse_bundle' and all(group[0].id == prev[0].id for prev in distinct):
            continue
        distinct.append(group)
        if len(distinct) == 3:
            break
    if len(distinct) < 3:
        for group in groups:
            if tuple(p.id for p in group) not in [tuple(p.id for p in prev) for prev in distinct]:
                distinct.append(group)
            if len(distinct) == 3:
                break
    schemes = []
    for index, group in enumerate(distinct):
        total = sum(p.data['price_minor'] for p in group)
        evidence = [f'demo:{p.id}' for p in group] if demo else [e for p in group for e in p.data['evidence_ids']]
        reasons = [{'text': f'商品合计 {total / 100:g} 元，在 {needs.budget_minor / 100:g} 元预算内。', 'evidence_ids': evidence}]
        if needs.connection != 'any':
            reasons.append({'text': '所选版本满足已确认的连接要求。', 'evidence_ids': evidence})
        if needs.quiet != 'any' and all(p.data.get('quiet') is True for p in group):
            reasons.append({'text': '所选版本均具有轻声标记；当前标记为模拟资料。' if demo else '依据所提供资料，所选版本满足对应轻声要求。', 'evidence_ids': evidence})
        if demo:
            relevant = [p for p in group if (
                needs.primary_use == 'portable' and p.data.get('portable') is True
                or needs.primary_use == 'gaming' and p.data.get('gaming') is True
                or needs.primary_use == 'office' and p.category == 'keyboard' and p.data.get('numpad') is True
                or needs.primary_use == 'coding' and p.category == 'keyboard' and p.data.get('layout') in ['75% 配列', '87 键']
            )]
            if relevant:
                explanation = {'coding': '键盘采用紧凑布局，保留常用功能键，是写代码场景的一个考虑方向。', 'office': '键盘保留独立数字区，适合经常录入数字的办公场景。', 'gaming': '当前演示资料中有游戏用途标记，因此在游戏场景中优先排序。', 'portable': '当前演示资料中有便携标记，因此在携带场景中优先排序。'}[needs.primary_use]
                reasons.append({'text': explanation + '这些参数与用途标记均为模拟资料。', 'evidence_ids': [f'demo:{p.id}' for p in relevant]})
        tradeoffs = [p.data['note'] for p in group]
        schemes.append({'id': 'scheme-' + '-'.join(p.id for p in group), 'label': ['优先考虑', '另一种选择', '更多选择'][index],
                        'items': [public_product(p) for p in group], 'total_minor': total,
                        'remaining_minor': needs.budget_minor - total, 'reasons': reasons, 'tradeoffs': tradeoffs, 'evidence_ids': evidence})
    return {'status': 'matched' if schemes else 'no_match', 'schemes': schemes, 'needs': needs.model_dump(),
            'mode': 'demo' if demo else 'real', 'generated_at': now().isoformat(),
            'message': '' if schemes else '当前资料库没有同时满足预算和明确要求的方案。可以调整预算或要求；原条件不会自动放宽。',
            'price_notice': '演示型号与价格仅用于体验流程，不代表真实商品或市场售价。' if demo else '价格为记录时的公开参考价，未计入未知运费与未核对优惠。',
            'catalog_size': len(products), 'rule_version': 'v0.1'}
