# info-bot

定时收集每日信息并推送到个人微信的「晨报机器人」。基于 **Python + GitHub Actions + WxPusher** 搭建，零服务器成本。

## 功能特性

- 默认每天早上 8:00（北京时间）发送一份分类晨报
- 三大板块：**💱 今日汇率** / **💻 科技要闻** / **🌐 时事政治**
- 支持 RSS / JSON API / 普通 HTML 网页 / 汇率 API 四类信息源
- 基于 URL 哈希自动去重，状态文件 commit 回仓库实现持久化
- 可选 LLM 摘要（DeepSeek / 通义 / OpenAI 兼容接口）
- WxPusher 推送到个人微信，单日 1000 条免费额度

## 快速开始

### 1. 准备 WxPusher

1. 打开 <https://wxpusher.zjiecode.com>，微信扫码登录
2. 进入「应用管理」→「新建应用」，记下 `appToken`（形如 `AT_xxx`）
3. 微信关注「WxPusher」公众号，在「我的」→「我的UID」拿到 UID（形如 `UID_xxx`）

### 2. 本地试跑

```bash
git clone <your-repo-url> info-bot
cd info-bot
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env 填入 WXPUSHER_APP_TOKEN 和 WXPUSHER_UIDS

# 干跑模式（不真实推送，只打印）
DRY_RUN=true python -m src.main

# 真实推送
python -m src.main
```

### 3. 部署到 GitHub Actions

1. 把仓库推到 GitHub
2. 进入 Repo Settings → Secrets and variables → Actions，新增 Secrets：
   - `WXPUSHER_APP_TOKEN`
   - `WXPUSHER_UIDS`
   - `LLM_API_KEY`（可选）
3. 进入 Actions 标签页启用 workflow，可手动触发一次测试
4. 之后默认每 30 分钟自动跑一次

## 自定义信息源

编辑 [sources.yaml](sources.yaml)，每条 source 用 `category` 决定推送时归到哪个板块：

| category | 板块 |
| --- | --- |
| `rate` | 💱 今日汇率 |
| `tech` | 💻 科技要闻 |
| `politics` | 🌐 时事政治 |
| `other` | 📰 其他 |

四种 source `type`：

```yaml
sources:
  # 汇率（欧洲央行参考汇率，工作日更新）
  - name: 澳元兑人民币 (AUD/CNY)
    type: rate
    category: rate
    url: https://api.frankfurter.dev/v1/latest
    base: AUD
    target: CNY

  # 标准 RSS / Atom
  - name: 少数派
    type: rss
    category: tech
    url: https://sspai.com/feed
    max_items: 5

  # JSON API（数组型响应，按 *_field 提取字段）
  - name: V2EX 最热
    type: api
    category: tech
    url: https://www.v2ex.com/api/topics/hot.json
    title_field: title
    url_field: url
    summary_field: content_rendered

  # 静态 HTML 网页（CSS 选择器）
  - name: HackerNews
    type: web
    category: tech
    url: https://news.ycombinator.com/
    item_selector: "tr.athing"
    title_selector: "span.titleline > a"
    link_selector: "span.titleline > a"
    link_attr: href
```

## 目录结构

```
info-bot/
├── .github/workflows/crawler.yml   定时任务
├── sources.yaml                    信息源配置
├── state/seen.json                 去重状态（自动提交）
├── src/
│   ├── main.py                     入口
│   ├── config.py                   配置加载
│   ├── models.py                   数据模型
│   ├── collectors/
│   │   ├── rss.py
│   │   ├── api.py
│   │   └── web.py
│   ├── dedup.py
│   ├── summarizer.py               AI 摘要
│   └── pusher.py                   WxPusher 推送
├── requirements.txt
└── README.md
```

## 上线后的调优指南

| 想调整 | 改这里 |
| --- | --- |
| 推送时间 | `.github/workflows/crawler.yml` 的 cron（默认 `0 0 * * *` = 北京时间 08:00） |
| 想一天两次 | cron 写 `0 0,12 * * *`（北京 08:00 + 20:00） |
| 某个源噪音太大 | 把对应 source 的 `enabled: false`，或调小它的 `max_items` |
| 单次推送条数过多 | `sources.yaml` 的 `settings.max_push_per_run`（默认 35） |
| 觉得每条 summary 太长 | `settings.max_content_length`（默认 200） |
| 想换汇率币种 | 在汇率 source 里改 `base` 和 `target`（ISO 4217 三字母代码） |
| 新增分类板块 | 在 [src/pusher.py](src/pusher.py) 的 `CATEGORY_META` 里加一项 |
| 想开启 AI 摘要 | 1. 在 Secrets 设置 `LLM_API_KEY` 2. `settings.enable_summary: true` |
| 想换 LLM 提供商 | Secrets / Variables 里改 `LLM_BASE_URL` 和 `LLM_MODEL`（OpenAI 兼容协议即可） |
| 摘要模板不满意 | 编辑 [src/summarizer.py](src/summarizer.py) 里的 `PROMPT` |
| 新增信息源 | 在 [sources.yaml](sources.yaml) 追加一条 source 配置 |
| 状态文件越积越大 | 已自动按 first_seen 截断到最近 5000 条，可改 [src/dedup.py](src/dedup.py) 里的 `MAX_ENTRIES` |

## 注意事项

- GitHub Actions 服务器在境外，访问国内某些站点可能受限
- 建议仓库设为 **public** 享受无限 Actions 分钟数
- 爬虫请遵守 robots.txt 和站点 ToS
- WxPusher 免费版每日 1000 条上限，按需控制源数量
