# 每日美股行情看板 · GitHub Actions 自托管版

完全脱离 WorkBuddy：GitHub Actions 每天自动跑两次（收盘复盘 + 盘前速览），
用 SiliconFlow（硅基流动，OpenAI 兼容 API）做 AI 研判，生成单文件 HTML 看板，并推送摘要到 Telegram。

## 流水线

```
should_notify.py（交易日/时段判断）
    → fetch_news.py + fetch_data.py（新闻、行情、财报、公开观察池）
    → validate_data.py（关键数据完整性）
    → ai_analysis.py（只允许有 URL 证据的新闻卡片）
        → gen_dashboard.py（生成 index.html）
            → notify_telegram.py（Telegram 推送）
                → deploy job → GitHub Pages（多端直接访问）
```

| 环节 | 数据源 | Key |
|---|---|---|
| 行情 / RSI / 乖离率 | westock-data-clawhub（npm） | 无 |
| 财报日历 | Nasdaq keyless API | 无 |
| 美股/A股指数 / VIX / 美债 / 黄金期货 / BTC | yfinance | 无 |
| 近期新闻上下文 | 多源 RSS，yfinance 仅作兜底 | 无 |
| AI 研判 + 利率环境摘要 | SiliconFlow（硅基流动，OpenAI 兼容） | **SILICONFLOW_API_KEY** |
| SPY Forward P/E | State Street 公布的 Price/Earnings Ratio FY1 | 无 |
| SOXX Forward P/E（估算） | iShares 每日持仓 + BusinessQuant FY1 共识 EPS | **BUSINESSQUANT_API_KEY**（免费层） |
| Telegram 推送 | Telegram Bot API | **TELEGRAM_BOT_TOKEN** + **TELEGRAM_CHAT_ID**（可空，缺则静默跳过） |
| 多端访问 | GitHub Pages（自动部署） | 仓库需 public |

## 部署步骤（一次性）

### 1. 创建 Telegram 机器人

1. Telegram 搜索 **`@BotFather`**，开聊
2. 发送 `/newbot`，按提示设置：
   - `name`：随便取（如「每日美股看板」）
   - `username`：必须以 `bot` 结尾（如 `us_dash_bot`），全网唯一
3. BotFather 回复里复制 **token**（形如 `7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxx`）

### 2. 拿到你的 chat_id

1. Telegram 搜索你刚创建的 bot（用 username 搜），点 **Start** 发任意一条消息（如 `/start`）
2. 浏览器访问（把 `<TOKEN>` 替换成上一步的 token）：
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. 返回 JSON 里找 `"chat":{"id": 123456789, ...}` —— 这个 **数字** 就是 `chat_id`
   - 个人对话就是你的 user id
   - 群组是负数（要先 `@你的bot` 加入群，再发一条消息才会出现）

### 3. 配置 GitHub Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret：

| Secret 名 | 必填 | 值 |
|---|---|---|
| `SILICONFLOW_API_KEY` | ✅ | 你的硅基流动 API key（[控制台](https://cloud.siliconflow.cn/account/ak)） |
| `TELEGRAM_BOT_TOKEN` | 推荐 | 第 1 步拿到的 token |
| `TELEGRAM_CHAT_ID` | 推荐 | 第 2 步拿到的数字 chat_id |

配完后可手动测试：Actions 页 → Daily US Market Dashboard → Run workflow。

### ETF Forward P/E 的免费口径

看板会每天记录公开的 ETF 估值与常规盘收盘价，并以双轴趋势图展示：左轴为 Forward P/E、右轴为 ETF 价格；鼠标悬停可查看当日数值。

- **SPY**：使用 State Street 免费公布的 `Price/Earnings Ratio FY1`。
- **SOXX**：下载 iShares 免费每日持仓，用各成分股持仓市值除以 BusinessQuant 的 FY1 共识盈利之和计算，等价于市值加权的调和平均 P/E；不会把成分股 P/E 做算术平均。
- **质量门槛**：只有获得 FY1 共识 EPS 的成分股覆盖 SOXX 至少 90% 权重时，才写入和绘制 SOXX Forward P/E。低于阈值会显示缺口与覆盖率，绝不以 trailing P/E 替代。
- `valuation_history.json` 只包含公开 ETF 估值、收盘价、来源和覆盖率；Actions 以机器人提交将其保存在仓库，供长期趋势图使用，不包含账户、持仓、成本或密钥。

### 4. 启用 GitHub Pages（一次性，可选）

仓库 → Settings → Pages → Source → 选择 **「GitHub Actions」** → 保存。

> 说明：私有仓库的 GitHub Pages 仅 GitHub Pro 及以上可用；免费账号需先把仓库设为 Public。
> 启用后每次运行会自动发布到 `https://<owner>.github.io/us-market-dashboard/`，
> 手机/电脑/平板直接打开，无需登录。

### 5. 触发方式

- **手动**：Actions 页 → Daily US Market Dashboard → Run workflow
- **自动**：每天 2 次（北京时间 08:00 收盘复盘、21:00 夏令时/22:00 冬令时盘前速览；盘前统一为美东 09:00）

### 6. 查看看板（任选其一）

- **GitHub Pages**：直接访问 `https://<owner>.github.io/<repo>/`（推荐，无需登录）
- **Artifacts**：每次运行后在 Actions 的 run 详情底部 → Artifacts → 下载 `us-market-dashboard` → 解压得 `index.html`（单文件、零外链、手机/电脑自适应、支持白天/夜间/跟随系统三态主题）

## 公开页与私有操作台

GitHub Pages 是**公开市场页**：它只发布市场数据、公开观察池和明确标记为公开的研究。它不读取或展示账户、订单、持仓、成本、P&L、私有 thesis 或交易复盘。

账户复盘在本机私有操作台完成。受控同步器在临时 mode-600 文件中校验只读券商快照后，调用：

```
python3 sync_portfolio_snapshot.py --snapshot-file <temporary-file> \
  --private-dashboard-file <local-private-dashboard>/data/current_snapshot.json
```

随后运行本机私有操作台的 renderer。该流程不会把快照写入 Git、GitHub Secrets、Actions 输入或 Pages。绝不要将 Robinhood 用户名、密码、MFA、Cookie 或连接器令牌写入任何文件或 Secret。

`portfolio_config.json` 仅用于公开市场观察池的分类；它不是账户记录，也不代表当前持仓或交易意图。

## 数据边界与历史

- A 股当前只覆盖上证、深证、沪深300和创业板指数行情；没有可靠中文新闻源时，AI 不得补写 A 股事件。
- 每次 Actions 运行保留 90 天 artifact，内含公开 HTML、市场数据、AI 输出和公开研究映射；不含账户数据。
- `notes/` 提供交易前记录和周度复盘模板；本机私有操作台负责呈现账户复盘与日志缺口。
- Telegram 推送只描述公开市场报告；不含账户、订单或持仓资料。

编辑 `gen_dashboard.py` 顶部：
- `LAYERS` —— AI 五层蛋糕分组
- `MATRIX_LAYERS` —— 趋势热力矩阵分组

### 报告时段与数据口径

工作流由 `should_notify.py` 判定 `premarket` 或 `postmarket`，并传给 AI、HTML 与 Telegram：

- **盘前作战卡**：抓取公开观察池、核心指数/板块 ETF 和 AI 主线核心池的 5 分钟延长时段报价，计算相对昨日 16:00 ET 常规盘收盘的变化；新闻只使用昨日收盘后新增且发布时间可验证的内容。没有盘前成交时明确显示缺失，不用昨收冒充实时价格。
- **收盘复盘**：使用最近一个美东常规盘交易日的收盘数据，聚焦市场宽度、板块表现、公开研究的待验证证据与下一交易日事项。

## 免责声明

以上内容基于公开数据，仅供参考，不构成投资建议。市场有风险，投资需谨慎。
