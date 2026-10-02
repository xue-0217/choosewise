import json

import pytest

from app.curated import read_samples
from tests.test_api import NEEDS, finish
from uuid import uuid4


@pytest.fixture
def draft_batch(tmp_path):
    root = tmp_path / 'crawl-runs'
    batch = root / '20261002T150000Z'
    batch.mkdir(parents=True)
    product = dict(id='sample-m240', mode='real_candidate', review_status='pending', recommendation_eligible=False,
                   name='M240 轻音蓝牙鼠标', variant_name='M240 - 玫瑰粉', sku='910-test', category='mouse',
                   source_url='https://www.logitech.com/zh-cn/shop/p/m240.910-test', retrieved_at='2026-10-02T15:00:00Z',
                   dimensions_mm={'width': '60'}, weight_g='73.8', connections_supported=['bluetooth'],
                   quiet=None, price_minor=None, currency='CNY')
    (batch / 'candidates.json').write_text(json.dumps(dict(schema_version='real-candidate-v0.1', status='pending_review', products=[product])), encoding='utf-8')
    return root


def test_real_sample_projection_preserves_unknown_price_and_review(draft_batch):
    samples = read_samples(draft_batch)
    assert len(samples['items']) == 1
    item = samples['items'][0]
    assert item['weight_g'] == '73.8' and item['price_minor'] is None
    assert not item['recommendation_eligible'] and item['review_status'] == 'pending'


def test_invalid_newest_batch_does_not_fall_back_to_old_data(draft_batch):
    newest = draft_batch / '20261003T150000Z'
    newest.mkdir()
    (newest / 'candidates.json').write_text('{bad', encoding='utf-8')
    response = read_samples(draft_batch)
    assert response['status'] == 'unavailable' and response['items'] == []


@pytest.mark.parametrize('update', [{'price_minor': 0}, {'source_url': 'javascript:alert(1)'}, {'review_status': 'verified'}, {'recommendation_eligible': True}])
def test_invalid_or_promoted_draft_not_exposed(draft_batch, update):
    path = next(draft_batch.glob('*/candidates.json'))
    data = json.loads(path.read_text(encoding='utf-8'))
    data['products'][0].update(update)
    path.write_text(json.dumps(data), encoding='utf-8')
    assert read_samples(draft_batch)['status'] == 'unavailable'


def test_real_request_never_uses_demo_catalog(tmp_path, draft_batch, monkeypatch):
    from app.core.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    def forbidden_demo(*args):
        pytest.fail('Real catalog must not fall back to demo recommendations')

    monkeypatch.setattr('app.main.build_recommendation', forbidden_demo)
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path / "real-read.db"}', curated_directory=draft_batch))
    with TestClient(app) as client:
        assert client.get('/api/v1/catalog/real-samples').json()['items'][0]['sku'] == '910-test'
        session = client.post('/api/v1/sessions').json()['id']
        prefix = f'/api/v1/sessions/{session}'
        revision = client.post(prefix + '/requirements', json={'needs': dict(NEEDS, catalog_mode='real')}).json()['id']
        run = client.post(prefix + '/recommendations', json={'requirement_revision_id': revision}, headers={'Idempotency-Key': str(uuid4())}).json()
        completed = finish(client, session, run['id'])
        result = client.get(prefix + '/results/' + completed['result_id']).json()
        assert result['mode'] == 'real' and result['status'] == 'insufficient_evidence'
        assert result['schemes'] == [] and result['catalog_size'] == 1
        assert 'M1' not in json.dumps(result) and 'M2' not in json.dumps(result)
