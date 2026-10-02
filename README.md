# 电商导购

根据预算、用途和偏好，推荐键盘、鼠标及键鼠组合。第一阶段完成推荐体验，商城能力后续加入。

## 文件夹用途

| 文件夹 | 放什么 |
|---|---|
| `docs/` | 产品与技术文档 |
| `apps/web/` | 网站前端：页面、组件、样式与交互 |
| `apps/api/` | 网站后端：接口、推荐逻辑与数据库操作 |
| `data/demo/` | 明确标注的演示商品数据 |
| `data/curated/` | 核对后的真实商品资料 |
| `knowledge/keyboards/` | 键盘选购知识 |
| `knowledge/mice/` | 鼠标选购知识 |
| `scripts/` | 资料导入、更新与维护脚本 |
| `evaluations/` | 推荐评测用例与核验记录 |
| `infra/` | Docker、部署与环境配置 |

## 文档入口

- [产品需求文档](./docs/PRODUCT.md)
- [技术设计文档](./docs/TECHNICAL.md)

已完成可本地运行的演示版，工作名称为「择物」。支持单品或键鼠组合、预算与用途、需求确认、最多三套方案、取舍说明、方案对比、依据和知识查看，以及刷新恢复。没有商城功能。

**网站默认打开「真实资料」，展示已采集的 K380s 与 M240、具体版本及官网来源。** 样本尚待参数审核和价格核对，提交真实需求返回资料不足，不生成预算内方案。切换「演示体验」后才使用 12 个虚构商品版本测试完整推荐流程；未产生付费模型调用。演示插图为结构示意。

## 本地启动

本机已安装前后端依赖。重新下载项目时：前端在 `apps/web` 运行 `npm ci`；后端用 Python 3.13 创建 `.venv`，依次运行 `python -m pip install -r requirements.lock.txt` 与 `python -m pip install --no-deps -e .`。

打开两个 PowerShell 终端，分别运行：

```powershell
cd D:\progects\电商导购\apps\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd D:\progects\电商导购\apps\web
npm run dev
```

网站：<http://127.0.0.1:5173>；接口文档：<http://127.0.0.1:8000/docs>。开发前端通过 Vite 转发 `/api`，不用额外配置跨域。

本地默认使用 SQLite，首次启动自动建五张业务表并导入演示数据，数据库存入 `apps/api/choosewise-demo.db`，不纳入版本管理。相同浏览器会话保留已确认需求与结果，会话有效期默认 24 小时；旧演示结果只能在主动切换「演示体验」后查看。价格资料有效期默认 7 天，过期版本不参与筛选。演示初始化时间只是模拟记录时间。

配置示例位于 `apps/api/.env.example`。`llm.py` 已留出模型适配代码，但供应商、真实资料审核和证据校验尚未完成，当前不支持将 `DEMO_MODE` 改为 `false`。API 采用单进程运行，不要添加多个 worker。

## 检查与构建

后端在 `apps/api` 运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

前端在 `apps/web` 运行（浏览器测试需要上述两个服务启动）：

```powershell
npm run build
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm run test:e2e
```

本机浏览器验收使用已安装的 Chrome。其他机器可用 `npx playwright install chromium`，不设置 `PLAYWRIGHT_CHANNEL` 即使用 Playwright 的 Chromium。测试结果、真实运行截图与限制见 [验收记录](./evaluations/REPORT.md)。

演示数据调整后，在项目根目录运行 `apps/api/.venv/Scripts/python.exe scripts/validate_demo_catalog.py`。此脚本只校验虚构资料，不更新价格或导入真实商品。

## 真实资料采集测试

已测试罗技中国官网的一个键盘版本和一个鼠标版本。采集参数、具体 SKU、来源和采集时间；页面价格为 0 时保留未知。采集器不写业务数据库，不执行页面 JavaScript，先检查 robots.txt，限定公开页面白名单，每次请求至少间隔 1.5 秒，网络失败不自动重复重试。

在项目根目录运行：

```powershell
apps/api/.venv/Scripts/python.exe scripts/crawl_catalog.py
```

结果按批次保存到 `data/curated/crawl-runs/`。网站通过 `/api/v1/catalog/real-samples` 读取最新批次；文件出错不会自动回退到旧批次或演示型号。适配器仅支持 `scripts/crawl_sources.json` 中限定域名与路径的页面，每批最多 20 页；清单包含一个已知 404 链接，用于负向测试。当前样本缺少有效价格和人工审核，不能用于预算推荐。详细结果见 [采集测试记录](./evaluations/CRAWL_REPORT.md)。

## PostgreSQL 与容器方案

`infra/compose.yaml` 包含 Nginx 前端、单进程 API 与 PostgreSQL，迁移在 API 启动前执行。本机 Docker 引擎未启动，当前只验证配置和迁移 SQL，尚未实际构建容器或连接 PostgreSQL。

之后启动 Docker Desktop，在 `infra` 复制 `.env.example` 为 `.env` 并设置本地随机密码，再运行：

```powershell
cd D:\progects\电商导购\infra
docker compose up --build
```

容器访问地址为 <http://127.0.0.1:8080>。这里是本地演示配置；正式部署前仍需完善资料审核、模型评测、限流、持久化执行器与 HTTPS 配置。

## 下一步

先整理真实商品、渠道价格与证据，再完成审核导入和模型接入；验证推荐准确性后再考虑商城。完整演进蓝图保留在技术文档中，当前基线与目标分开标注。
