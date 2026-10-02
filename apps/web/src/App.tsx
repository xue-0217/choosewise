import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRight, ArrowsLeftRight, BookOpen, Check, CheckCircle, Clock, Info, Keyboard, Mouse, Plus, SlidersHorizontal, Sparkle, X } from '@phosphor-icons/react'
import { KeyboardArt, MouseArt } from './components/DeviceArt'
import { RealCatalog } from './components/RealCatalog'
import { api, connections, money, targets, uses } from './lib/api'
import type { Analysis, Evidence, Knowledge, Needs, Product, Result, Run, Scheme, Session, SessionState, Target, Use, RealCatalog as RealCatalogData } from './lib/api'

const INITIAL: Needs = { catalog_mode: 'real', target: 'keyboard_mouse_bundle', budget_minor: 50000, currency: 'CNY', primary_use: 'coding', connection: 'any', quiet: 'any', numpad: 'any', text: '' }
let sessionBootstrap: Promise<Session> | null = null
function initializeSession() {
  sessionBootstrap ??= api<Session>('/sessions', 'POST').catch(error => { sessionBootstrap = null; throw error })
  return sessionBootstrap
}
const samples = [
  { label: '宿舍写代码', text: '宿舍使用，主要写代码，偶尔玩游戏，希望安静一点。', use: 'coding' as Use, budget: '500', target: 'keyboard_mouse_bundle' as Target },
  { label: '办公室做表格', text: '经常输入数字，需要数字区，希望安静一点。', use: 'office' as Use, budget: '400', target: 'keyboard' as Target },
  { label: '轻装去上课', text: '想带去上课，要蓝牙连接，体积小一点。', use: 'portable' as Use, budget: '200', target: 'mouse' as Target },
]

function ProductVisual({ product }: { product: Product }) {
  return <div className={`product-visual tone-${product.color}`}>{product.category === 'keyboard' ? <KeyboardArt tone={product.color} compact /> : <MouseArt tone={product.color} />}<span>外观示意</span></div>
}

function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [initialized, setInitialized] = useState(false)
  const [selectedTarget, setSelectedTarget] = useState<Target | null>(null)
  const [budget, setBudget] = useState('500')
  const [draft, setDraft] = useState<Needs>(INITIAL)
  const [advanced, setAdvanced] = useState(false)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [revisionId, setRevisionId] = useState<string | null>(null)
  const [storedResult, setResult] = useState<Result | null>(null)
  const result = storedResult?.mode === draft.catalog_mode ? storedResult : null
  const [realCatalog, setRealCatalog] = useState<RealCatalogData | null>(null)
  const [catalogError, setCatalogError] = useState('')
  const [busy, setBusy] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [stage, setStage] = useState('')
  const [error, setError] = useState('')
  const [activeScheme, setActiveScheme] = useState(0)
  const [compare, setCompare] = useState(false)
  const [evidence, setEvidence] = useState<Evidence[] | null>(null)
  const [knowledge, setKnowledge] = useState<Knowledge[] | null>(null)
  const [drawer, setDrawer] = useState<'evidence' | 'knowledge' | null>(null)
  const resultRef = useRef<HTMLElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const operation = useRef(0)
  const mounted = useRef(true)
  const currentRun = useRef<string | null>(null)
  const drawerRef = useRef<HTMLElement>(null)
  const drawerOpener = useRef<HTMLElement | null>(null)

  const applyNeeds = useCallback((needs: Needs) => {
    setDraft(needs); setSelectedTarget(needs.target); setBudget(String(needs.budget_minor / 100))
  }, [])

  const poll = useCallback(async (sessionId: string, run: Run, sequence: number) => {
    let current = run
    currentRun.current = current.id
    setActiveRunId(current.id)
    const deadline = Date.now() + 100000
    while (current.status === 'queued' || current.status === 'running') {
      if (!mounted.current || sequence !== operation.current) return null
      setStage(current.stage)
      if (Date.now() > deadline) throw new Error('等待时间较长，请刷新读取本次执行状态。')
      await new Promise(resolve => setTimeout(resolve, 350))
      current = await api<Run>(`/sessions/${sessionId}/runs/${current.id}`)
    }
    if (!mounted.current || sequence !== operation.current) return null
    if (current.status === 'failed') throw new Error(current.error?.message || '本次执行没有完成，请重试。')
    if (current.status === 'cancelled') return null
    return current
  }, [])

  useEffect(() => {
    mounted.current = true
    let live = true
    const initialize = async () => {
      try {
        const visitor = await initializeSession()
        if (!live) return
        setSession(visitor)
        const state = await api<SessionState>(`/sessions/${visitor.id}`)
        if (!live) return
        if (state.requirement) { setRevisionId(state.requirement.id); if (state.requirement.needs.catalog_mode === 'real') applyNeeds(state.requirement.needs) }
        if (state.result) { setResult(state.result); if (!state.requirement && state.result.mode === 'real') applyNeeds(state.result.needs) }
        setInitialized(true)
        if (state.active_run) {
          setBusy(true)
          const seq = ++operation.current
          const done = await poll(visitor.id, state.active_run, seq)
          if (!live || !done) return
          if (done.kind === 'analysis' && done.output?.needs.catalog_mode === 'real') setAnalysis(done.output)
          else if (done.result_id) setResult(await api<Result>(`/sessions/${visitor.id}/results/${done.result_id}`))
          setBusy(false)
        }
      } catch (caught) { if (live) { setError(caught instanceof Error ? caught.message : '无法连接服务。'); setBusy(false) } }
    }
    void initialize()
    return () => { live = false; mounted.current = false }
  }, [applyNeeds, poll])

  useEffect(() => {
    if (!drawer) return
    const previousFocus = drawerOpener.current
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDrawer(null)
      if (event.key === 'Tab') {
        const elements = drawerRef.current?.querySelectorAll<HTMLElement>('button, a[href], input, select, textarea, [tabindex="0"]')
        if (!elements?.length) return
        const first = elements[0], last = elements[elements.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', close)
    const old = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', close); document.body.style.overflow = old; previousFocus?.focus() }
  }, [drawer])

  async function analyze(event?: React.FormEvent) {
    event?.preventDefault()
    setError('')
    if (!session) { setError('后端尚未连接，请刷新页面或检查服务是否启动。'); return }
    if (!selectedTarget) { setError('先选择你想买键盘、鼠标，还是一套键鼠。'); return }
    const amount = Number(budget)
    if (!Number.isFinite(amount) || amount <= 0 || amount > 1000000 || !/^\d+(\.\d{1,2})?$/.test(budget)) { setError('请输入有效预算，最多保留两位小数。'); return }
    const needs: Needs = { ...draft, target: selectedTarget, budget_minor: Math.round(amount * 100) }
    const seq = ++operation.current
    currentRun.current = null; setActiveRunId(null)
    setBusy(true); setAnalysis(null); setStage('整理你的选购需求')
    try {
      const run = await api<Run>(`/sessions/${session.id}/analyses`, 'POST', { structured_input: needs, text: needs.text, base_requirement_revision_id: revisionId }, crypto.randomUUID())
      const done = await poll(session.id, run, seq)
      if (done && seq === operation.current) { setAnalysis(done.output); setActiveScheme(0); resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
    } catch (caught) { if (seq === operation.current) setError(caught instanceof Error ? caught.message : '需求整理失败。') }
    finally { if (seq === operation.current) setBusy(false) }
  }

  async function recommend() {
    if (!session || !analysis || busy) return
    const seq = ++operation.current
    currentRun.current = null; setActiveRunId(null)
    setBusy(true); setError(''); setStage('筛选符合预算的商品')
    try {
      const revision = await api<{ id: string }>(`/sessions/${session.id}/requirements`, 'POST', { needs: analysis.needs, base_requirement_revision_id: revisionId })
      setRevisionId(revision.id); applyNeeds(analysis.needs)
      const run = await api<Run>(`/sessions/${session.id}/recommendations`, 'POST', { requirement_revision_id: revision.id }, crypto.randomUUID())
      const done = await poll(session.id, run, seq)
      if (done?.result_id && seq === operation.current) {
        const next = await api<Result>(`/sessions/${session.id}/results/${done.result_id}`)
        if (seq !== operation.current) return
        setResult(next); setAnalysis(null); setCompare(false); setActiveScheme(0)
        resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    } catch (caught) { if (seq === operation.current) setError(caught instanceof Error ? caught.message : '推荐没有完成。') }
    finally { if (seq === operation.current) setBusy(false) }
  }

  async function cancel() {
    if (!session || !currentRun.current) return
    try { await api(`/sessions/${session.id}/runs/${currentRun.current}/cancel`, 'POST'); operation.current++; setBusy(false); setStage(''); setAnalysis(null) }
    catch (caught) { setError(caught instanceof Error ? caught.message : '取消失败。') }
  }

  async function openEvidence(scheme: Scheme) {
    setError('')
    try { const records = await Promise.all(scheme.evidence_ids.map(id => api<Evidence>(`/evidence/${encodeURIComponent(id)}`))); setEvidence(records); drawerOpener.current = document.activeElement as HTMLElement; setDrawer('evidence') }
    catch (caught) { setError(caught instanceof Error ? caught.message : '暂时无法读取资料。') }
  }

  async function openKnowledge() {
    try { const records = await api<{ items: Knowledge[] }>('/knowledge'); setKnowledge(records.items); drawerOpener.current = document.activeElement as HTMLElement; setDrawer('knowledge') }
    catch (caught) { setError(caught instanceof Error ? caught.message : '暂时无法读取知识资料。') }
  }

  function selectCatalog(choice: Needs['catalog_mode']) {
    if (storedResult?.mode === choice) applyNeeds({ ...storedResult.needs, catalog_mode: choice })
    else setDraft({ ...draft, catalog_mode: choice })
    setAnalysis(null); setActiveScheme(0); setCompare(false); setError('')
  }

  const scheme = result?.schemes[activeScheme]
  const mode = draft.catalog_mode

  const loadRealCatalog = useCallback(async () => {
    setCatalogError('')
    try { setRealCatalog(await api<RealCatalogData>('/catalog/real-samples')) }
    catch { setCatalogError('真实资料读取失败，请稍后重试。') }
  }, [])

  useEffect(() => { void loadRealCatalog() }, [loadRealCatalog])

  return <div className="app-shell">
    <header className="site-header">
      <a className="brand" href="#" onClick={event => { event.preventDefault(); formRef.current?.scrollIntoView({ behavior: 'smooth' }) }} aria-label="择物首页"><span className="brand-mark">z<span>·</span></span><span>择物<span className="brand-en">CHOOSEWISE</span></span></a>
      <nav aria-label="主导航"><button className="nav-active" onClick={() => formRef.current?.scrollIntoView({ behavior: 'smooth' })}>开始选购</button><button onClick={() => resultRef.current?.scrollIntoView({ behavior: 'smooth' })}>推荐方案</button><button onClick={() => void openKnowledge()}>选购知识<BookOpen size={14} /></button></nav>
      <span className="header-note">好选择，从真实需求开始。</span>
    </header>

    <main className="page-container">
      <div className="demo-notice"><Info size={15} weight="fill" /><span>{mode === 'demo' ? '演示模式 · 型号、参数和价格均为模拟数据，仅供体验选购流程' : '真实资料 · 官网采集样本已接入，价格与参数待核对，暂不能生成预算内方案'}</span></div>
      <div className="catalog-mode" role="group" aria-label="资料模式">
        <button disabled={busy || !initialized} aria-pressed={mode === 'real'} onClick={() => selectCatalog('real')}>真实资料</button>
        <button disabled={busy || !initialized} aria-pressed={mode === 'demo'} onClick={() => selectCatalog('demo')}>演示体验</button>
        <span>{mode === 'real' ? '查看真实型号与官网来源' : '使用虚构型号测试选购流程'}</span>
      </div>
      <section className="intro-section">
        <div><p className="eyebrow">键盘与鼠标 · 选购助手</p><h1>让下一件装备，<br />更合你的心意<span>。</span></h1><p className="intro-description">告诉我预算和用途，一起找到值得考虑的选择。</p></div>
        <div className="intro-side"><span className="intro-symbol"><Keyboard size={25} weight="light" /><Plus size={15} /><Mouse size={25} weight="light" /></span><p>先想清楚怎么用，<br />再决定买哪一个。</p></div>
      </section>

      <div className="workspace">
        <form className="needs-panel" ref={formRef} onSubmit={event => void analyze(event)}>
          <div className="section-heading"><span className="step-number">01</span><h2>说说你的需求</h2><span className="small-caption">无需登录</span></div>
          <fieldset disabled={busy}>
            <legend className="field-label">这次想选什么？</legend>
            <div className="target-options">{(Object.keys(targets) as Target[]).map(target => <button key={target} type="button" className={`target-option ${selectedTarget === target ? 'selected' : ''}`} aria-pressed={selectedTarget === target} onClick={() => { setSelectedTarget(target); setAnalysis(null) }}>{target === 'mouse' ? <Mouse size={20} /> : <Keyboard size={20} />}<span>{targets[target]}</span>{selectedTarget === target && <Check size={13} weight="bold" />}</button>)}</div>
            <label className="field-label budget-label" htmlFor="budget">你的{selectedTarget === 'keyboard_mouse_bundle' ? '总' : ''}预算<span>人民币</span></label>
            <div className="budget-input"><span>¥</span><input id="budget" type="text" inputMode="decimal" value={budget} onChange={event => { setBudget(event.target.value); setAnalysis(null) }} aria-describedby="budget-help" /><span className="budget-unit">以内</span></div>
            <p id="budget-help" className="field-help">{selectedTarget === 'keyboard_mouse_bundle' ? '键盘和鼠标合计的商品参考价。' : '按商品参考价筛选，未计入未知运费。'}</p>
            <div className="budget-shortcuts">{[200, 350, 500, 800].map(value => <button type="button" key={value} onClick={() => { setBudget(String(value)); setAnalysis(null) }} className={Number(budget) === value ? 'selected' : ''}>¥{value}</button>)}</div>
            <label className="field-label" htmlFor="primary-use">主要用来做什么？</label>
            <select id="primary-use" value={draft.primary_use} onChange={event => { setDraft({ ...draft, primary_use: event.target.value as Use }); setAnalysis(null) }}>{Object.entries(uses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
            <label className="field-label" htmlFor="description">还有什么在意的？<span>选填</span></label>
            <textarea id="description" rows={3} placeholder="例如：宿舍用，希望安静一点；电脑接口少，想要蓝牙……" value={draft.text} onChange={event => { setDraft({ ...draft, text: event.target.value }); setAnalysis(null) }} maxLength={2000} />
            <button type="button" className="advanced-toggle" onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}><SlidersHorizontal size={16} /><span>明确连接、声音和布局要求</span><span>{advanced ? '收起' : '展开'}</span></button>
            {advanced && <div className="advanced-fields"><label>连接方式<select value={draft.connection} onChange={event => { setDraft({ ...draft, connection: event.target.value as Needs['connection'] }); setAnalysis(null) }}>{Object.entries(connections).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>声音要求<select value={draft.quiet} onChange={event => { setDraft({ ...draft, quiet: event.target.value as Needs['quiet'] }); setAnalysis(null) }}><option value="any">没有特别要求</option><option value="prefer">尽量安静</option><option value="required">必须有轻声资料</option></select></label>{selectedTarget !== 'mouse' && <label>独立数字区<select value={draft.numpad} onChange={event => { setDraft({ ...draft, numpad: event.target.value as Needs['numpad'] }); setAnalysis(null) }}><option value="any">都可以</option><option value="required">必须有数字区</option><option value="excluded">不要数字区</option></select></label>}</div>}
          </fieldset>
          {error && <div className="inline-error" role="alert">{error}</div>}
          <button className="primary-button" type="submit" disabled={busy || !session || !initialized}><Sparkle size={18} />{busy ? stage || '正在整理需求' : mode === 'real' ? '检查真实推荐资料' : result ? '按新需求重新挑选' : '帮我挑选'}{!busy && <ArrowRight size={19} />}</button>
          {busy && <button className="cancel-button" type="button" disabled={!activeRunId} onClick={() => void cancel()}>取消本次处理</button>}
          <p className="form-footer">每次生成前，都由你确认需求。</p>
        </form>

        <section className="result-panel" ref={resultRef} aria-live="polite">
          {busy ? <div className="loading-surface"><div className="section-heading"><span className="step-number">02</span><h2>{stage || '正在为你整理'}</h2></div><div className="loading-device"><KeyboardArt tone="sage" /></div><div className="skeleton-line" /><div className="skeleton-line short" /><div className="skeleton-row"><div /><div /></div><p>完成后会核对商品组合与预算。</p></div>
            : analysis ? <div className="confirmation-surface"><span className="confirmation-icon"><CheckCircle size={34} weight="light" /></span><p className="eyebrow">生成方案前，再确认一下</p><h2>这是我理解的需求</h2><div className="confirmation-summary"><p><span>选购目标</span><strong>{targets[analysis.needs.target]}</strong></p><p><span>预算上限</span><strong>¥{money(analysis.needs.budget_minor)}</strong></p><p><span>主要用途</span><strong>{uses[analysis.needs.primary_use]}</strong></p><p><span>连接方式</span><strong>{connections[analysis.needs.connection]}</strong></p><p><span>声音偏好</span><strong>{analysis.needs.quiet === 'required' ? '必须有轻声资料' : analysis.needs.quiet === 'prefer' ? '尽量安静' : '没有特别要求'}</strong></p>{analysis.needs.numpad !== 'any' && <p><span>数字区</span><strong>{analysis.needs.numpad === 'required' ? '必须有' : '不要数字区'}</strong></p>}</div>{analysis.questions.length > 0 ? <div className="questions"><h3>有一点需要你确认</h3>{analysis.questions.map((question, i) => <p key={i}>{question.message}</p>)}<button className="secondary-button" onClick={() => { setAnalysis(null); formRef.current?.scrollIntoView({ behavior: 'smooth' }) }}>回到左侧修改</button></div> : <><p className="confirmation-tip">没有填写的偏好会保留为“不确定”，不会擅自替你决定。</p><button className="primary-button" onClick={() => void recommend()}>{mode === 'real' ? '确认需求，检查资料' : '确认需求，查看方案'}<ArrowRight size={18} /></button><button className="text-button" onClick={() => { setAnalysis(null); formRef.current?.scrollIntoView({ behavior: 'smooth' }) }}>我还想改一下</button></>}</div>
              : result ? <div className="results-surface"><div className="section-heading result-heading"><div><p className="eyebrow">按你的需求挑选</p><h2>{result.schemes.length ? `${result.schemes.length} 套值得考虑的方案` : result.status === 'insufficient_evidence' ? '真实推荐资料还需补齐' : '暂时没有合适的组合'}</h2></div><span className="result-budget">¥{money(result.needs.budget_minor)}{mode === 'real' ? ' 预算' : ' 内'}</span></div><div className="requirement-tags"><span>{targets[result.needs.target]}</span><span>{uses[result.needs.primary_use]}</span>{result.needs.quiet !== 'any' && <span>{result.needs.quiet === 'required' ? '轻声为必须条件' : '希望安静'}</span>}{result.needs.connection !== 'any' && <span>{connections[result.needs.connection]}</span>}</div>{!result.schemes.length ? <><div className="empty-results"><SlidersHorizontal size={36} weight="light" /><h3>{mode === 'real' ? '价格与资料核对完成后，才能推荐。' : '保留你的要求，也保留选择的空间。'}</h3><p>{result.message}</p><button className="secondary-button" onClick={() => formRef.current?.scrollIntoView({ behavior: 'smooth' })}>{mode === 'real' ? '修改选购需求' : '调整预算或要求'}</button></div>{mode === 'real' && <RealCatalog catalog={realCatalog} target={selectedTarget} error={catalogError} retry={() => void loadRealCatalog()} />}</> : <><div className="scheme-tabs" role="tablist" aria-label="推荐方案">{result.schemes.map((item, index) => <button role="tab" aria-selected={activeScheme === index} key={item.id} onClick={() => setActiveScheme(index)}><span>方案 {String(index + 1).padStart(2, '0')}</span><strong>¥{money(item.total_minor)}</strong>{activeScheme === index && <Check size={15} />}</button>)}</div>{scheme && <><div className="featured-scheme"><div className="scheme-topline"><span className="recommend-badge"><CheckCircle size={15} />{scheme.label}</span><span>演示方案</span></div><div className={`products-grid count-${scheme.items.length}`}>{scheme.items.map(product => <article className="product" key={product.id}><ProductVisual product={product} /><div className="product-kind">{product.category === 'keyboard' ? '键盘' : '鼠标'}<span>¥{money(product.price_minor)}</span></div><h3>{product.name}</h3><p className="product-version">{product.version}</p><div className="product-specs"><span>{product.connection_labels.join(' / ')}</span><span>{product.weight_g}g</span></div></article>)}</div><div className="scheme-price"><span>合计演示参考价</span><strong><small>¥</small>{money(scheme.total_minor)}</strong><span className="budget-left">比预算少 ¥{money(scheme.remaining_minor)}</span></div></div><div className="reason-sections"><div><h3><CheckCircle size={17} />为什么考虑这套</h3>{scheme.reasons.map((reason, index) => <p key={index}><Check size={13} />{reason.text}</p>)}</div><div className="tradeoff-section"><h3><Info size={17} />你需要接受的取舍</h3>{scheme.tradeoffs.map((note, index) => <p key={index}>{note}</p>)}</div></div><div className="result-actions"><button className="secondary-button" onClick={() => { setCompare(!compare); if (!compare) setTimeout(() => document.getElementById('comparison')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50) }}><ArrowsLeftRight size={17} />{compare ? '收起对比' : '对比全部方案'}</button><button className="text-button" onClick={() => void openEvidence(scheme)}>查看推荐依据<ArrowRight size={14} /></button></div></>}</>}{compare && result.schemes.length > 0 && <Comparison schemes={result.schemes} /> }<div className="price-footnote"><Clock size={14} /><span>{result.price_notice}<br />生成于 {new Date(result.generated_at).toLocaleString('zh-CN')} · {mode === 'real' ? `当前已采集 ${result.catalog_size} 个真实版本，尚待核对` : `本次从 ${result.catalog_size} 个演示版本中筛选`}</span></div></div>
                : mode === 'real' ? <RealCatalog catalog={realCatalog} target={selectedTarget} error={catalogError} retry={() => void loadRealCatalog()} /> : <div className="guide-surface"><div className="guide-header"><span className="quiet-label">为需求而选</span><span className="guide-number">K / M</span></div><div className="hero-devices"><KeyboardArt tone="cream" /><MouseArt tone="sage" /><span className="art-caption">设备结构示意</span></div><div className="guide-copy"><h2>不必看懂所有参数，<br />先说清楚你的日常。</h2><p>写代码、做表格、打游戏，或轻装出门。<br />选择不同，合适的装备也会不同。</p></div><div className="guide-checks"><span><Check size={15} />预算内的选择</span><span><Check size={15} />说清优点与取舍</span><span><Check size={15} />推荐依据可查看</span></div></div>}
        </section>
      </div>

      <section className="sample-section"><div><p className="eyebrow">还没想好怎么描述？</p><h2>从一个日常场景开始</h2></div><div className="sample-options">{samples.map(sample => <button key={sample.label} disabled={busy} onClick={() => { applyNeeds({ ...INITIAL, target: sample.target, primary_use: sample.use, text: sample.text, budget_minor: Number(sample.budget) * 100 }); setAnalysis(null); setError(''); formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}><span>{sample.label}</span><p>{sample.text}</p><span className="sample-budget">预算 ¥{sample.budget}<ArrowRight size={17} /></span></button>)}</div></section>
    </main>
    <footer className="site-footer"><span>择物 <span>CHOOSEWISE</span></span><p>选择适合自己的，留一点预算给生活。</p><button onClick={() => void openKnowledge()}>关于选购依据<BookOpen size={14} /></button></footer>

    {drawer && <div className="drawer-overlay" onClick={() => setDrawer(null)}><section className="drawer" ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby="drawer-title" onClick={event => event.stopPropagation()}><div className="drawer-header"><div><p className="eyebrow">{drawer === 'knowledge' ? '选购时可以参考' : '可追溯的资料'}</p><h2 id="drawer-title">{drawer === 'knowledge' ? '选购知识' : '推荐依据'}</h2></div><button aria-label="关闭面板" onClick={() => setDrawer(null)} autoFocus><X size={23} /></button></div>{drawer === 'knowledge' ? knowledge?.map(item => <article className="knowledge-item" key={item.id}><BookOpen size={21} /><h3>{item.title}</h3>{item.content.split('\n\n').map((paragraph, index) => <p key={index}>{paragraph}</p>)}</article>) : evidence?.map(item => <article className="knowledge-item" key={item.id}><Info size={21} /><h3>{item.title}</h3><p>{item.content}</p><dl><div><dt>演示价格</dt><dd>¥{money(item.data.price_minor)}</dd></div><div><dt>版本</dt><dd>{item.data.version}</dd></div><div><dt>连接</dt><dd>{item.data.connection_labels.join(' / ')}</dd></div></dl>{item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">打开资料来源</a>}</article>)}</section></div>}
  </div>
}

function Comparison({ schemes }: { schemes: Scheme[] }) {
  const rows = [
    { label: '参考总价', values: schemes.map(s => '¥' + money(s.total_minor)) },
    { label: '键盘', values: schemes.map(s => s.items.find(p => p.category === 'keyboard')?.name || '本次不选键盘') },
    { label: '鼠标', values: schemes.map(s => s.items.find(p => p.category === 'mouse')?.name || '本次不选鼠标') },
    { label: '连接方式', values: schemes.map(s => s.items.map(p => `${p.category === 'keyboard' ? '键盘' : '鼠标'}：${p.connection_labels.join(' / ')}`).join('；')) },
    { label: '声音资料', values: schemes.map(s => s.items.map(p => `${p.category === 'keyboard' ? '键盘' : '鼠标'}：${p.quiet === null ? '暂无资料' : p.quiet ? '轻声（模拟）' : '非轻声（模拟）'}`).join('；')) },
    { label: '独立数字区', values: schemes.map(s => { const p = s.items.find(item => item.category === 'keyboard'); return p ? p.numpad === null ? '暂无资料' : p.numpad ? '有' : '没有' : '不适用' }) },
    { label: '主要取舍', values: schemes.map(s => s.tradeoffs.join(' ')) },
  ]
  return <div className="comparison" id="comparison"><h3><ArrowsLeftRight size={18} />把差异放在一起看</h3><div className="comparison-scroll"><table><caption className="sr-only">推荐方案参数对比</caption><thead><tr><th>关注点</th>{schemes.map((s, index) => <th key={s.id}>方案 {String(index + 1).padStart(2, '0')}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.label}><th scope="row">{row.label}</th>{row.values.map((value, index) => <td key={index}>{value}</td>)}</tr>)}</tbody></table></div></div>
}

export default App
