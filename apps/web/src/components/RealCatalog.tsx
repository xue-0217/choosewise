import { ArrowSquareOut, Keyboard, Mouse, Info } from '@phosphor-icons/react'
import { money } from '../lib/api'
import type { RealCatalog as Catalog, Target } from '../lib/api'

export function RealCatalog({ catalog, target, error, retry }: { catalog: Catalog | null; target: Target | null; error: string; retry: () => void }) {
  const items = catalog?.items.filter(item => !target || target === 'keyboard_mouse_bundle' || item.category === target) || []
  return <div className="real-catalog">
    <div className="real-catalog-heading"><div><p className="eyebrow">采集结果已接入</p><h2>真实商品资料</h2></div><span className="real-review-badge">待核对</span></div>
    <p className="real-catalog-notice"><Info size={17} /><span>{error || catalog?.notice || '正在读取官网采集资料…'}</span></p>
    {error || catalog?.status === 'unavailable' ? <button className="secondary-button" onClick={retry}>重新读取资料</button> : catalog && items.length === 0 ? <p className="real-empty">这个品类暂时没有已采集的样本。</p> : items.map(item => <article className="real-product" key={item.id}>
      <div className="real-product-title">{item.category === 'keyboard' ? <Keyboard size={23} /> : <Mouse size={23} />}<div><span>{item.category === 'keyboard' ? '键盘' : '鼠标'} · 官网资料</span><h3>{item.name}</h3></div></div>
      <p className="real-variant">{item.variant_name}<br />版本编号：{item.sku}</p>
      <dl className="real-specs"><div><dt>重量声明</dt><dd>{item.weight_g ? `${item.weight_g}g（口径待核对）` : '待补充'}</dd></div><div><dt>连接声明</dt><dd>{item.connection_labels.join(' / ') || '待补充'}</dd></div><div><dt>参考价格</dt><dd>{item.price_minor === null ? '价格待补充' : `¥${money(item.price_minor)}（待核对）`}</dd></div><div><dt>声音表现</dt><dd>待核对</dd></div></dl>
      <div className="real-source"><span>采集于 {new Date(item.retrieved_at).toLocaleDateString('zh-CN')}</span><a href={item.source_url} target="_blank" rel="noreferrer">查看官网来源<ArrowSquareOut size={14} /></a></div>
    </article>)}
  </div>
}
