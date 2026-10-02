import asyncio
import hashlib
import json
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from .core.config import PROJECT_ROOT, Settings
from .curated import incomplete_real_result, read_samples
from .db import Base, Product, Requirement, Run, Snapshot, Visitor, create_database, now
from .llm import model_json
from .recommendation import analyze_demo, build_recommendation, public_product, utc
from .schemas import AnalyzeRequest, ConfirmRequest, Explanations, Needs, RecommendRequest


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine, factory = create_database(settings.database_url)
    tasks: set[asyncio.Task] = set()
    semaphore = asyncio.Semaphore(settings.max_concurrent_runs)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.demo_mode:
            raise RuntimeError('Real mode is not enabled in this demo baseline. Implement reviewed sources, claims and import validation before enabling real recommendations.')
        if settings.demo_mode:
            Base.metadata.create_all(engine)
            catalog = json.loads((PROJECT_ROOT / 'data/demo/catalog.json').read_text(encoding='utf-8'))
            with factory.begin() as db:
                for item in catalog['products']:
                    if not db.get(Product, item['id']):
                        db.add(Product(id=item['id'], category=item['category'], name=item['name'], version=item['version'], data=item, mode='demo', reviewed='demo'))
        with factory.begin() as db:
            for interrupted in db.scalars(select(Run).where(Run.status.in_(['queued', 'running']))):
                interrupted.status = 'failed'
                interrupted.stage = '执行已中断'
                interrupted.error = {'code': 'RUN_INTERRUPTED', 'message': '服务重启导致上次执行中断，请主动重试。'}
        app.state.settings = settings
        app.state.engine = engine
        app.state.factory = factory
        try:
            yield
        finally:
            for task in list(tasks):
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            engine.dispose()

    app = FastAPI(title='择物 · 选购助手接口', version='0.1.0', lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def errors(request: Request, error: HTTPException):
        detail = error.detail if isinstance(error.detail, dict) else {'code': 'REQUEST_REJECTED', 'message': str(error.detail)}
        return JSONResponse(status_code=error.status_code, content={'error': detail})

    def session_for(request: Request) -> Visitor:
        token = request.cookies.get('choosewise_session', '')
        with factory() as db:
            visitor = db.scalar(select(Visitor).where(Visitor.token_hash == hashlib.sha256(token.encode()).hexdigest())) if token else None
            if not visitor or utc(visitor.expires_at) <= now():
                raise HTTPException(401, {'code': 'SESSION_EXPIRED', 'message': '当前会话已过期，请重新开始。'})
            return visitor

    def own(visitor: Visitor, session_id: str):
        if visitor.id != session_id:
            raise HTTPException(404, '没有找到当前会话的记录。')

    def serialize_run(run: Run) -> dict:
        return {'id': run.id, 'kind': run.kind, 'status': run.status, 'stage': run.stage, 'output': run.output, 'error': run.error, 'result_id': run.result_id}

    def stage(run_id: str, name: str):
        with factory.begin() as db:
            run = db.get(Run, run_id)
            if not run or run.status == 'cancelled':
                raise asyncio.CancelledError()
            run.status = 'running'
            run.stage = name

    async def execute(run_id: str, kind: str, payload: dict):
        async def work():
            async with semaphore:
                if kind == 'analysis':
                    stage(run_id, '整理你的选购需求')
                    parsed = AnalyzeRequest.model_validate(payload)
                    if settings.demo_mode:
                        output = analyze_demo(parsed.structured_input, parsed.text)
                    else:
                        raw = await model_json(settings, '将需求整理为 JSON，包含 needs 和 questions。needs 字段为 target,budget_minor,currency,primary_use,connection,quiet,numpad,text。枚举与输入相同，预算保持输入值；冲突必须放入 questions，每条包含 field,message。不得静默忽略硬要求。', payload)
                        output = {'needs': Needs.model_validate(raw['needs']).model_dump(), 'questions': raw.get('questions', []), 'mode': 'real', 'summary': '请确认整理后的需求。'}
                        if output['needs']['budget_minor'] != parsed.structured_input.budget_minor:
                            raise ValueError('MODEL_OUTPUT_INVALID')
                    with factory.begin() as db:
                        run = db.get(Run, run_id)
                        if run.status != 'cancelled':
                            run.output = output
                            run.status = 'succeeded'
                            run.stage = '需求已整理'
                else:
                    stage(run_id, '筛选符合预算的商品')
                    with factory() as db:
                        revision = db.get(Requirement, payload['requirement_revision_id'])
                        needs = Needs.model_validate(revision.data)
                        session_id = revision.session_id
                        products = list(db.scalars(select(Product))) if needs.catalog_mode == 'demo' else []
                    result = incomplete_real_result(settings.curated_directory, needs) if needs.catalog_mode == 'real' else build_recommendation(products, needs, settings.price_max_age_days, settings.demo_mode)
                    if not settings.demo_mode and result['schemes']:
                        stage(run_id, '根据资料解释方案')
                        raw = await model_json(settings, '只解释输入 schemes，不修改商品或金额。返回 {"schemes":[{"scheme_id":"原方案id","reasons":[{"text":"解释","evidence_ids":["所提供的证据id"]}],"tradeoffs":["取舍"]}]}。结论必须由对应证据支持；不得保证未知体验。', {'needs': needs.model_dump(), 'schemes': result['schemes']})
                        explanation = Explanations.model_validate(raw)
                        expected = {s['id']: s for s in result['schemes']}
                        if len(explanation.schemes) != len(expected) or {s.scheme_id for s in explanation.schemes} != set(expected):
                            raise ValueError('MODEL_OUTPUT_INVALID')
                        for item in explanation.schemes:
                            allowed = set(expected[item.scheme_id]['evidence_ids'])
                            if any(not set(reason.evidence_ids) <= allowed for reason in item.reasons):
                                raise ValueError('MODEL_OUTPUT_INVALID')
                            expected[item.scheme_id]['reasons'] = [reason.model_dump() for reason in item.reasons]
                            expected[item.scheme_id]['tradeoffs'] = item.tradeoffs
                    stage(run_id, '核对金额与资料版本')
                    with factory.begin() as db:
                        current = {p.id: p for p in db.scalars(select(Product))} if needs.catalog_mode == 'demo' else {}
                        rerun = incomplete_real_result(settings.curated_directory, needs) if needs.catalog_mode == 'real' else build_recommendation(list(current.values()), needs, settings.price_max_age_days, settings.demo_mode)
                        available = {s['id']: s for s in rerun['schemes']}
                        for scheme in result['schemes']:
                            if scheme['id'] not in available or scheme['total_minor'] != available[scheme['id']]['total_minor'] or scheme['items'] != available[scheme['id']]['items']:
                                raise ValueError('DATA_CHANGED')
                            if scheme['total_minor'] > needs.budget_minor:
                                raise ValueError('BUDGET_INVALID')
                        run = db.get(Run, run_id)
                        if run.status == 'cancelled':
                            return
                        snapshot = Snapshot(session_id=session_id, run_id=run_id, requirement_id=revision.id, data=result)
                        db.add(snapshot)
                        db.flush()
                        run.result_id = snapshot.id
                        run.status = 'succeeded'
                        run.stage = '资料检查已完成' if needs.catalog_mode == 'real' else '方案已完成'
        try:
            await asyncio.wait_for(work(), timeout=settings.run_timeout_seconds)
        except asyncio.CancelledError:
            with factory.begin() as db:
                run = db.get(Run, run_id)
                if run and run.status not in ['succeeded', 'cancelled']:
                    run.status = 'failed'
                    run.error = {'code': 'RUN_INTERRUPTED', 'message': '本次执行已中断，请主动重试。'}
            raise
        except Exception as error:
            code = str(error) if str(error) in ['MODEL_OUTPUT_INVALID', 'DATA_CHANGED', 'MODEL_NOT_CONFIGURED'] else 'RUN_FAILED'
            messages = {'DATA_CHANGED': '商品资料已变化，请重新生成。', 'MODEL_NOT_CONFIGURED': '模型服务尚未配置。', 'MODEL_OUTPUT_INVALID': '模型返回内容未通过校验，请重试。'}
            with factory.begin() as db:
                run = db.get(Run, run_id)
                if run and run.status != 'cancelled':
                    run.status = 'failed'
                    run.stage = '暂时无法完成'
                    run.error = {'code': code, 'message': messages.get(code, '本次生成没有完成，原方案仍然保留，请主动重试。')}

    def new_run(visitor: Visitor, kind: str, payload: dict, key: str | None) -> dict:
        if not key or not 8 <= len(key) <= 100:
            raise HTTPException(422, '提交请求需要有效的幂等标识。')
        digest = hashlib.sha256(json.dumps({'kind': kind, 'payload': payload}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with factory() as db:
            prior = db.scalar(select(Run).where(Run.session_id == visitor.id, Run.idempotency_key == key))
            if prior:
                if prior.input_hash != digest:
                    raise HTTPException(409, '相同请求标识对应了不同内容，请重新提交。')
                return serialize_run(prior)
            if db.scalar(select(Run).where(Run.session_id == visitor.id, Run.status.in_(['queued', 'running']))):
                raise HTTPException(409, '当前已有需求正在处理，请稍后再试。')
            if db.scalar(select(func.count()).select_from(Run).where(Run.status.in_(['queued', 'running']))) >= settings.max_concurrent_runs:
                raise HTTPException(429, '当前处理较多，请稍后再试。')
            if not settings.demo_mode and not settings.model_ready:
                raise HTTPException(503, '真实模型服务尚未配置。')
            run = Run(session_id=visitor.id, kind=kind, idempotency_key=key, input_hash=digest)
            db.add(run)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                prior = db.scalar(select(Run).where(Run.session_id == visitor.id, Run.idempotency_key == key))
                if prior and prior.input_hash == digest:
                    return serialize_run(prior)
                raise HTTPException(409, '请求状态冲突，请读取当前结果后再提交。')
            reply = serialize_run(run)
        task = asyncio.create_task(execute(run.id, kind, payload))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return reply

    @app.get('/api/v1/health/live')
    def live():
        return {'status': 'ok', 'mode': 'demo' if settings.demo_mode else 'real'}

    @app.get('/api/v1/health/ready')
    def ready():
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {'status': 'ok', 'mode': 'demo' if settings.demo_mode else 'real', 'model_configured': settings.model_ready}

    @app.post('/api/v1/sessions')
    def create_session(request: Request, response: Response):
        token = request.cookies.get('choosewise_session', '')
        with factory.begin() as db:
            visitor = db.scalar(select(Visitor).where(Visitor.token_hash == hashlib.sha256(token.encode()).hexdigest())) if token else None
            if not visitor or utc(visitor.expires_at) <= now():
                token = secrets.token_urlsafe(32)
                visitor = Visitor(token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=now() + timedelta(hours=settings.session_ttl_hours))
                db.add(visitor)
                db.flush()
            response.set_cookie('choosewise_session', token, httponly=True, samesite='strict', secure=settings.cookie_secure, max_age=settings.session_ttl_hours * 3600)
            return {'id': visitor.id, 'expires_at': utc(visitor.expires_at).isoformat(), 'mode': 'demo' if settings.demo_mode else 'real'}

    @app.get('/api/v1/sessions/{session_id}')
    def session_state(session_id: str, visitor: Visitor = Depends(session_for)):
        own(visitor, session_id)
        with factory() as db:
            revision = db.scalar(select(Requirement).where(Requirement.session_id == session_id).order_by(Requirement.created_at.desc()))
            result = db.scalar(select(Snapshot).where(Snapshot.session_id == session_id).order_by(Snapshot.created_at.desc()))
            active = db.scalar(select(Run).where(Run.session_id == session_id, Run.status.in_(['queued', 'running'])))
            return {'id': session_id, 'requirement': {'id': revision.id, 'needs': revision.data} if revision else None, 'result': dict(result.data, id=result.id) if result else None, 'active_run': serialize_run(active) if active else None}

    @app.post('/api/v1/sessions/{session_id}/analyses', status_code=202)
    async def analyze(session_id: str, body: AnalyzeRequest, idempotency_key: str | None = Header(default=None), visitor: Visitor = Depends(session_for)):
        own(visitor, session_id)
        if body.base_requirement_revision_id:
            with factory() as db:
                base = db.get(Requirement, body.base_requirement_revision_id)
                if not base or base.session_id != visitor.id:
                    raise HTTPException(404, '需求版本不存在。')
        return new_run(visitor, 'analysis', body.model_dump(), idempotency_key)

    @app.post('/api/v1/sessions/{session_id}/requirements', status_code=201)
    def confirm(session_id: str, body: ConfirmRequest, visitor: Visitor = Depends(session_for)):
        own(visitor, session_id)
        with factory.begin() as db:
            latest = db.scalar(select(Requirement).where(Requirement.session_id == session_id).order_by(Requirement.created_at.desc()))
            if (latest.id if latest else None) != body.base_requirement_revision_id:
                raise HTTPException(409, '需求版本已经改变，请刷新后再确认。')
            revision = Requirement(session_id=session_id, base_id=body.base_requirement_revision_id, data=body.needs.model_dump())
            db.add(revision)
            db.flush()
            return {'id': revision.id, 'needs': revision.data}

    @app.post('/api/v1/sessions/{session_id}/recommendations', status_code=202)
    async def recommend(session_id: str, body: RecommendRequest, idempotency_key: str | None = Header(default=None), visitor: Visitor = Depends(session_for)):
        own(visitor, session_id)
        with factory() as db:
            revision = db.get(Requirement, body.requirement_revision_id)
            if not revision or revision.session_id != visitor.id:
                raise HTTPException(404, '需求版本不存在。')
        return new_run(visitor, 'recommendation', body.model_dump(), idempotency_key)

    @app.get('/api/v1/sessions/{session_id}/runs/{run_id}')
    def read_run(session_id: str, run_id: str, visitor: Visitor = Depends(session_for)):
        own(visitor, session_id)
        with factory() as db:
            run = db.get(Run, run_id)
            if not run or run.session_id != visitor.id:
                raise HTTPException(404, '执行记录不存在。')
            return serialize_run(run)

    @app.post('/api/v1/sessions/{session_id}/runs/{run_id}/cancel')
    def cancel(session_id: str, run_id: str, visitor: Visitor = Depends(session_for)):
        own(visitor, session_id)
        with factory.begin() as db:
            run = db.get(Run, run_id)
            if not run or run.session_id != visitor.id:
                raise HTTPException(404, '执行记录不存在。')
            if run.status in ['queued', 'running']:
                run.status = 'cancelled'
                run.stage = '已取消'
            return serialize_run(run)

    @app.get('/api/v1/sessions/{session_id}/results/{result_id}')
    def read_result(session_id: str, result_id: str, visitor: Visitor = Depends(session_for)):
        own(visitor, session_id)
        with factory() as db:
            snapshot = db.get(Snapshot, result_id)
            if not snapshot or snapshot.session_id != visitor.id:
                raise HTTPException(404, '推荐方案不存在。')
            return dict(snapshot.data, id=snapshot.id)

    @app.get('/api/v1/products')
    def products():
        with factory() as db:
            entries = db.scalars(select(Product).where(Product.mode == ('demo' if settings.demo_mode else 'real')))
            return {'mode': 'demo' if settings.demo_mode else 'real', 'items': [public_product(p) for p in entries]}

    @app.get('/api/v1/catalog/real-samples')
    def real_samples():
        return read_samples(settings.curated_directory)

    @app.get('/api/v1/evidence/{evidence_id}')
    def evidence(evidence_id: str):
        if settings.demo_mode and evidence_id.startswith('demo:'):
            with factory() as db:
                product = db.get(Product, evidence_id.removeprefix('demo:'))
                if product and product.mode == 'demo':
                    return {'id': evidence_id, 'title': product.name + ' · 演示资料', 'content': '这是用于验证筛选与价格计算的模拟资料。所有参数、价格与安静标记均不属于真实商品实测。', 'data': public_product(product), 'source_url': None, 'mode': 'demo'}
        raise HTTPException(404, '未找到公开证据。')

    @app.get('/api/v1/knowledge')
    def knowledge():
        documents = []
        for path in sorted((PROJECT_ROOT / 'knowledge').rglob('*.md')):
            content = path.read_text(encoding='utf-8')
            body = content.split('---', 2)[-1].strip()
            title = next((line.split(':', 1)[1].strip() for line in content.splitlines() if line.startswith('title:')), path.stem)
            documents.append({'id': path.stem, 'title': title, 'content': body})
        return {'items': documents}

    return app


app = create_app()
