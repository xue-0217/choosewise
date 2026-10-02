export type Target = 'keyboard' | 'mouse' | 'keyboard_mouse_bundle'
export type Use = 'coding' | 'office' | 'gaming' | 'portable'
export interface Needs {
  catalog_mode: 'demo' | 'real'
  target: Target
  budget_minor: number
  currency: 'CNY'
  primary_use: Use
  connection: 'any' | 'wireless' | 'bluetooth' | 'wired'
  quiet: 'any' | 'prefer' | 'required'
  numpad: 'any' | 'required' | 'excluded'
  text: string
}
export interface Product {
  id: string
  category: 'keyboard' | 'mouse'
  name: string
  version: string
  price_minor: number
  weight_g: number
  layout: string
  quiet: boolean | null
  color: string
  numpad: boolean | null
  connection_labels: string[]
  price_observed_at: string
  note: string
}
export interface Scheme {
  id: string
  label: string
  items: Product[]
  total_minor: number
  remaining_minor: number
  reasons: { text: string; evidence_ids: string[] }[]
  tradeoffs: string[]
  evidence_ids: string[]
}
export interface Result {
  id: string
  status: 'matched' | 'no_match' | 'insufficient_evidence'
  schemes: Scheme[]
  needs: Needs
  mode: 'demo' | 'real'
  generated_at: string
  message: string
  price_notice: string
  catalog_size: number
}
export interface Analysis {
  needs: Needs
  questions: { field: string; message: string }[]
  mode: string
  summary: string
}
export interface Run {
  id: string
  kind: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  stage: string
  output: Analysis | null
  error: { code: string; message: string } | null
  result_id: string | null
}
export interface Session {
  id: string
  mode: 'demo' | 'real'
}
export interface SessionState {
  requirement: { id: string; needs: Needs } | null
  result: Result | null
  active_run: Run | null
}
export interface Evidence { id: string; title: string; content: string; source_url: string | null; data: Product }
export interface Knowledge { id: string; title: string; content: string }
export interface RealSample {
  id: string
  name: string
  variant_name: string
  sku: string
  category: 'keyboard' | 'mouse'
  weight_g: string | null
  dimensions_mm: Record<string, string>
  connection_labels: string[]
  source_url: string
  retrieved_at: string
  price_minor: number | null
}
export interface RealCatalog { status: 'pending_review' | 'unavailable'; items: RealSample[]; notice: string }

export const money = (minor: number) => (minor / 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
export const uses: Record<Use, string> = { coding: '写代码', office: '日常办公', gaming: '玩游戏', portable: '随身携带' }
export const targets: Record<Target, string> = { keyboard_mouse_bundle: '键盘 + 鼠标', keyboard: '键盘', mouse: '鼠标' }
export const connections = { any: '都可以', wireless: '必须无线', bluetooth: '必须蓝牙', wired: '必须有线' }

export async function api<T>(path: string, method = 'GET', body?: unknown, key?: string): Promise<T> {
  const response = await fetch('/api/v1' + path, {
    method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(key ? { 'Idempotency-Key': key } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error?.message || (response.status === 422 ? '请检查输入的预算和需求。' : '暂时无法连接服务，请稍后重试。'))
  return data as T
}
