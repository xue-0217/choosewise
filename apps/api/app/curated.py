"""Read validated draft samples for inspection. Drafts never become priced recommendations."""
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal

from .db import now
from .schemas import Needs


class PublicSample(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str
    mode: Literal['real_candidate']
    review_status: Literal['pending']
    recommendation_eligible: Literal[False]
    name: str
    variant_name: str
    sku: str
    category: Literal['keyboard', 'mouse']
    source_url: str
    retrieved_at: str
    dimensions_mm: dict[str, Decimal] = Field(default_factory=dict)
    weight_g: Decimal | None = Field(default=None, gt=0)
    connections_supported: list[Literal['bluetooth', 'receiver']] | None = None
    price_minor: int | None = Field(default=None, strict=True, gt=0)
    quiet: None = None
    currency: Literal['CNY']


NOTICE = '以下是真实官网采集样本，尚待资料审核和价格核对，暂不参与预算推荐。'


def read_samples(folder: Path) -> dict:
    response = {'mode': 'real_candidate', 'status': 'pending_review', 'items': [], 'notice': NOTICE}
    if not folder.exists():
        return response
    runs = sorted((path for path in folder.iterdir() if path.is_dir() and not path.is_symlink()), reverse=True)
    if not runs:
        return response
    # Do not silently fall back to old data when the newest batch is broken.
    path = runs[0] / 'candidates.json'
    try:
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            raise ValueError('Unexpected candidate file')
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema_version') != 'real-candidate-v0.1' or data.get('status') != 'pending_review' or not isinstance(data.get('products'), list) or len(data['products']) > 20:
            raise ValueError('Unexpected batch schema')
        ids = set()
        items = []
        for raw in data['products']:
            sample = PublicSample.model_validate(raw)
            source = urlsplit(sample.source_url)
            if source.scheme != 'https' or source.netloc != 'www.logitech.com' or not source.path.startswith('/zh-cn/shop/p/') or sample.id in ids:
                raise ValueError('Unexpected source or duplicate version')
            ids.add(sample.id)
            item = sample.model_dump(mode='json')
            labels = {'bluetooth': '蓝牙', 'receiver': '兼容 Bolt 接收器（需另购）'}
            item['connection_labels'] = [labels[value] for value in (sample.connections_supported or [])]
            items.append(item)
        response['items'] = items
    except (OSError, ValueError, TypeError, ValidationError):
        response['status'] = 'unavailable'
        response['notice'] = '真实资料暂时无法读取，请稍后重试。'
    return response


def incomplete_real_result(folder: Path, needs: Needs) -> dict:
    samples = read_samples(folder)
    return {'status': 'insufficient_evidence', 'schemes': [], 'needs': needs.model_dump(), 'mode': 'real',
            'generated_at': now().isoformat(), 'catalog_size': len(samples['items']),
            'message': '真实样本尚未完成资料审核和价格核对，暂不能判断哪些方案符合你的预算。不会用演示商品替代真实商品。' if samples['status'] != 'unavailable' else samples['notice'],
            'price_notice': '没有有效报价的商品保留价格未知，不按 0 元或虚拟价格推荐。', 'rule_version': 'v0.2'}
