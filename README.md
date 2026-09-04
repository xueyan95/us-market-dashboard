# 每日美股行情看板 · GitHub Actions 自托管版

完全脱离 WorkBuddy：GitHub Actions 每天自动跑两次（收盘复盘 + 盘前速览），
用 Gemini（AI Studio 免费 key）联网研判，生成单文件 HTML 看板，并推送摘要到飞书。

## 流水线

```
fetch_data.py（行情+财报+情绪）
    → ai_analysis.py（Gemini 联网研判）
        → gen_dashboard.py（生成 index.html）
            → notify_feishu.py（飞书 webhook 推送）
                → deploy job → GitHub Pages（多端直接访问）
```

| 环节 | 数据源 | Key |
|---|---|---|
| 行情 / RSI / 乖离率 | westock-data-clawhub（npm） | 无 |
| 财报日历 | Nasdaq keyless API | 无 |
| 指数 / VIX / 美债 / 黄金 / BTC | yfinance | 无 |
| AI 研判 + 新闻 + FedWatch | Gemini 2.5 Flash（Google Search grounding） | **GEMINI_API_KEY** |
| 飞书推送 | 飞书群自定义机器人 webhook | **FEISHU_WEBHOOK**（可空，缺则静默跳过） |
| 多端访问 | GitHub Pages（自动部署） | 无（仓库需开放 Pages） |

## 部署步骤（一次性）

### 1. 配置 Secrets
仓库 → Settings → Secrets and variables → Actions → New repository secret：

| Secret 名 | 必填 | 值 |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | 你的 AI Studio API key |
| `FEISHU_WEBHOOK` | 可选 | 飞书群机器人 webhook URL（见下） |

### 2. 启用 GitHub Pages（一次性）
仓库 → Settings → Pages → Source → 选择 **「GitHub Actions」** → 保存。

> 说明：私有仓库的 GitHub Pages 仅 GitHub Pro 及以上可用；免费账号需先把仓库设为 Public（代码 + 数据均为公开信息，无敏感凭据）。
> 启用后每次运行会自动发布到 `https://<owner>.github.io/us-market-dashboard/`，手机/电脑/平板直接打开，无需登录。

### 3. 获取飞书 webhook（可选）
1. 打开飞书，进入想接收推送的群 → 群设置 → 群机器人 → 添加「自定义机器人」
2. 复制 webhook 地址（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx`）
3. 填入上面的 `FEISHU_WEBHOOK`

> 说明：WorkBuddy 里的飞书连接器用的是会过期的 OAuth token，无法移植到 GitHub。
> 这里改用群机器人 webhook，一个 URL 永久有效、零维护。

### 4. 触发方式
- **手动**：Actions 页 → 「Daily US Market Dashboard」→ Run workflow
- **自动**：每天 2 次（北京时间 08:00 收盘复盘、21:30 盘前速览）

### 5. 查看看板（任选其一）
- **GitHub Pages**：直接访问 `https://<owner>.github.io/<repo>/`（推荐，无需登录）
- **Artifacts**：每次运行后在 Actions 的 run 详情底部 → Artifacts → 下载 `us-market-dashboard` → 解压得 `index.html`（单文件、零外链、手机/电脑自适应、支持白天/夜间/跟随系统三态主题）

## 修改持仓 / 观察股

编辑 `fetch_data.py` 顶部：
- `HOLDINGS` —— 核心持仓 8 只
- `ALL_SYMS` —— 拉取行情的完整标的池
- `FOCUS` —— 财报日历过滤池

编辑 `gen_dashboard.py` 顶部：
- `LAYERS` —— AI 五层蛋糕分组
- `MATRIX_LAYERS` —— 趋势热力矩阵分组

## 免责声明

以上内容基于公开数据，仅供参考，不构成投资建议。市场有风险，投资需谨慎。
