import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path / "test.db"}', demo_mode=True))
    with TestClient(app) as test_client:
        yield test_client


NEEDS = dict(target='keyboard_mouse_bundle', budget_minor=50000, currency='CNY', primary_use='coding',
             connection='bluetooth', quiet='required', numpad='any', text='')


def finish(client, session, run):
    for _ in range(100):
        result = client.get(f'/api/v1/sessions/{session}/runs/{run}').json()
        if result['status'] not in ['queued', 'running']:
            assert result['status'] == 'succeeded', result
            return result
        time.sleep(.02)
    pytest.fail('Operation did not complete')


def test_complete_flow_idempotency_restore_and_isolation(client):
    session = client.post('/api/v1/sessions').json()['id']
    prefix = f'/api/v1/sessions/{session}'
    key = str(uuid4())
    body = dict(structured_input=NEEDS, text='宿舍写代码，希望安静')
    reply = client.post(prefix + '/analyses', json=body, headers={'Idempotency-Key': key})
    assert reply.status_code == 202
    analysis = finish(client, session, reply.json()['id'])
    repeated = client.post(prefix + '/analyses', json=body, headers={'Idempotency-Key': key})
    assert repeated.json()['id'] == analysis['id']
    changed = client.post(prefix + '/analyses', json=dict(body, text='不同需求'), headers={'Idempotency-Key': key})
    assert changed.status_code == 409
    revision = client.post(prefix + '/requirements', json={'needs': analysis['output']['needs']}).json()
    assert client.post(prefix + '/requirements', json={'needs': NEEDS}).status_code == 409
    response = client.post(prefix + '/recommendations', json={'requirement_revision_id': revision['id']}, headers={'Idempotency-Key': str(uuid4())})
    run = finish(client, session, response.json()['id'])
    url = prefix + '/results/' + run['result_id']
    result = client.get(url).json()
    assert 1 <= len(result['schemes']) <= 3
    for scheme in result['schemes']:
        assert sum(item['price_minor'] for item in scheme['items']) == scheme['total_minor'] <= 50000
        assert all(item['quiet'] is True and 'bluetooth' in item['connections'] for item in scheme['items'])
    assert client.get(prefix).json()['result']['id'] == result['id']
    assert client.post('/api/v1/sessions').json()['id'] == session
    client.cookies.clear()
    assert client.get(url).status_code == 401
    other = client.post('/api/v1/sessions').json()['id']
    assert other != session and client.get(url).status_code == 404
    assert client.get(f'/api/v1/sessions/{other}/results/{result["id"]}').status_code == 404


@pytest.mark.parametrize('budget', [0, -1, True, 123.4, '50000'])
def test_invalid_money_rejected(client, budget):
    session = client.post('/api/v1/sessions').json()['id']
    reply = client.post(f'/api/v1/sessions/{session}/requirements', json={'needs': dict(NEEDS, budget_minor=budget)})
    assert reply.status_code == 422


def test_failed_regeneration_keeps_last_successful_snapshot(client, monkeypatch):
    session = client.post('/api/v1/sessions').json()['id']
    prefix = f'/api/v1/sessions/{session}'
    revision = client.post(prefix + '/requirements', json={'needs': NEEDS}).json()['id']
    run = client.post(prefix + '/recommendations', json={'requirement_revision_id': revision}, headers={'Idempotency-Key': str(uuid4())}).json()
    original = finish(client, session, run['id'])['result_id']

    def fail(*args):
        raise ValueError('DATA_CHANGED')

    monkeypatch.setattr('app.main.build_recommendation', fail)
    run = client.post(prefix + '/recommendations', json={'requirement_revision_id': revision}, headers={'Idempotency-Key': str(uuid4())}).json()
    for _ in range(100):
        state = client.get(prefix + '/runs/' + run['id']).json()
        if state['status'] == 'failed':
            break
        time.sleep(.02)
    assert state['status'] == 'failed' and state['error']['code'] == 'DATA_CHANGED'
    assert client.get(prefix).json()['result']['id'] == original


def test_real_mode_cannot_be_enabled_without_completed_evidence_pipeline(tmp_path):
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path / "real.db"}', demo_mode=False))
    with pytest.raises(RuntimeError, match='Real mode is not enabled'):
        with TestClient(app):
            pytest.fail('Unreviewed real mode must not start')
