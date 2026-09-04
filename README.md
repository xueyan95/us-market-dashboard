# 每日美股行情看板 · GitHub Actions 自托管版

完全脱离 WorkBuddy：GitHub Actions 每天自动跑两次（收盘复盘 + 盘前速览），
用 SiliconFlow（硅基流动，OpenAI 兼容 API）做 AI 研判，生成单文件 HTML 看板，并推送摘要到 Telegram。

## 流水线

```
fetch_data.py（行情+财报+情绪）
    → ai_analysis.py（SiliconFlow 研判 + yfinance 新闻上下文）
        → gen_dashboard.py（生成 index.html）
            → notify_telegram.py（Telegram 推送）
                → deploy job → GitHub Pages（多端直接访问）
```

| 环节 | 数据源 | Key |
|---|---|---|
| 行情 / RSI / 乖离率 | westock-data-clawhub（npm） | 无 |
| 财报日历 | Nasdaq keyless API | 无 |
| 指数 / VIX / 美债 / 黄金 / BTC | yfinance | 无 |
| 近期新闻上下文 | yfinance `Ticker.news` | 无 |
| AI 研判 + FedWatch | SiliconFlow（硅基流动，OpenAI 兼容） | **SILICONFLOW_API_KEY** |
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

### 4. 启用 GitHub Pages（一次性，可选）

仓库 → Settings → Pages → Source → 选择 **「GitHub Actions」** → 保存。

> 说明：私有仓库的 GitHub Pages 仅 GitHub Pro 及以上可用；免费账号需先把仓库设为 Public。
> 启用后每次运行会自动发布到 `https://<owner>.github.io/us-market-dashboard/`，
> 手机/电脑/平板直接打开，无需登录。

### 5. 触发方式

- **手动**：Actions 页 → Daily US Market Dashboard → Run workflow
- **自动**：每天 2 次（北京时间 08:00 收盘复盘、21:30 盘前速览）

### 6. 查看看板（任选其一）

- **GitHub Pages**：直接访问 `https://<owner>.github.io/<repo>/`（推荐，无需登录）
- **Artifacts**：每次运行后在 Actions 的 run 详情底部 → Artifacts → 下载 `us-market-dashboard` → 解压得 `index.html`（单文件、零外链、手机/电脑自适应、支持白天/夜间/跟随系统三态主题）

## Telegram 推送效果预览

```
📊 美股 2026-09-03 收盘复盘（自动化）

【一句话结论】
美股今日普涨，主要受美联储官员偏鸽派言论导致美债收益率回落，
以及 AI 领域重磅利好消息提振。英伟达收购 Hugging Face，OpenAI 发布
GPT-6 Astra，博通上调 AI 业务指引，共同推动科技股和 AI 概念股走强…

【三大指数】
标普 7,748 (+1.06%) · 纳指 26,584 (+1.40%) · 道指 53,686 (+1.18%)

【持仓 8 只】
LAZR 41.09 (-1.3%) · INTC 91.67 (+1.8%) · APP 313.58 (-1.71%) · 
BE 235.55 (+8.41%) · COHR 264.41 (-1.57%) · WOLF 26.84 (+0.71%) · 
NBIS 210.63 (+3.2%) · NOW 145.59 (+6.49%)

【FedWatch】加息 ≈50% / 维持 ≈50% / 降息 <1%
【近期关注】明日（9月4日）将公布美国8月非农就业…
```

## 修改持仓 / 观察股

编辑 `portfolio_config.json`：
- `holdings` —— 当前股票持仓/观察仓代码及 `core`、`watch` 分类
- `option_underlyings` —— 需要跟踪期权 IV 与 P/C ratio 的标的

该文件刻意不保存数量、成本价、账户余额或券商凭据，可安全用于公开仓库。更新一次后，行情抓取、AI 研判、HTML 看板和 Telegram 推送会同时使用新名单。

### Robinhood 仓位快照（公开展示模式）

看板不直接保存或使用 Robinhood 登录信息。它只读取一个运行时快照：`portfolio_snapshot.json`（已被 `.gitignore` 排除）。格式见 `portfolio_snapshot.example.json`。

将快照 JSON 压成单行并 Base64 编码后，保存为仓库 Secret：`PORTFOLIO_SNAPSHOT_B64`。快照只保存数量、平均成本、现金和期权合约定义；不保存股票或期权市场价格。工作流会在每次运行时重新拉取价格，并计算最新市值、组合净值和浮动盈亏。

> 你已选择公开展示这些数据：任何能访问 GitHub Pages 或看板构建产物的人都可能看到它们。该 Secret 是静态快照，不能自行从 Robinhood 更新。自动更新仍需一个受控的本地同步器或私有 API。绝不要将 Robinhood 用户名、密码、MFA、Cookie 或连接器令牌放进 GitHub Secrets。

编辑 `fetch_data.py` 顶部：
- `ALL_SYMS` —— 拉取行情的完整标的池（新持仓需同时确保在此列表）
- `FOCUS` —— 财报日历过滤池

编辑 `gen_dashboard.py` 顶部：
- `LAYERS` —— AI 五层蛋糕分组
- `MATRIX_LAYERS` —— 趋势热力矩阵分组

### 报告时段与数据口径

工作流由 `should_notify.py` 判定 `premarket` 或 `postmarket`，并传给 AI、HTML 与 Telegram：

- **盘前作战卡**：明确标注为最近常规盘收盘数据与新闻上下文；不会把前收误写为盘前实时报价。
- **收盘复盘**：使用最近一个美东常规盘交易日的收盘数据。

## 免责声明

以上内容基于公开数据，仅供参考，不构成投资建议。市场有风险，投资需谨慎。
