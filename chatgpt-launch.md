# ChatGPT manual dashboard launch

Use this runbook only when the user explicitly asks to refresh the GitHub-hosted dashboard.

1. Read the brokerage accounts with read-only tools. Identify the dedicated Agentic account from the broker's agentic-access signal. Treat every other account as manual and read-only.
2. Report current manual and Agentic holdings to the user in ChatGPT only. Do not write either account's positions, quantities, costs, P&L, account identifiers, or private thesis into this repository, a GitHub workflow input, an artifact, or the deployed Pages site.
3. Explain that the dashboard's GitHub workflow remains responsible for public market data, news, AI analysis, HTML generation, notification, and Pages deployment. Its manual portfolio display uses the separately configured GitHub snapshot mechanism.
4. From this directory, run `./trigger_dashboard.sh --slot premarket` or `./trigger_dashboard.sh --slot postmarket`. Use `--no-notify` only when the user requested no Telegram notification.
5. Confirm that the GitHub Actions run was requested. Poll its result when the user asks; report its run URL/status and never expose GitHub credentials.

The manual portfolio is never an Agentic trading signal. Never create, change, cancel, or submit an order during this runbook.
