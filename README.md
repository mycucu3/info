# AI Coding News Radar

这个仓库每天自动抓取 AI coding 热点与科技新闻，并推送到你日常能看到的地方。

日报会输出为一份更适合截图展示的 Markdown 简报，包括：

- 顶部日期、信号数和平均热度
- 今日趋势判断
- 精选热点卡片
- 热度分、来源、日期和原文链接
- 后续追踪方向

## 个人微信推送

个人微信没有官方 Webhook。最简单的做法是使用 PushPlus，把 GitHub Actions 的消息转发到你的微信。

步骤：

1. 打开 [PushPlus](https://www.pushplus.plus/)。
2. 用微信扫码登录并关注它的公众号。
3. 在 PushPlus 后台复制你的 token。
4. 打开 GitHub 仓库：`Settings -> Secrets and variables -> Actions -> New repository secret`。
5. 新增：

| Secret           | 值                  |
| ---------------- | ------------------- |
| `PUSHPLUS_TOKEN` | 你的 PushPlus token |

配置后进入 `Actions -> Daily AI Coding News -> Run workflow` 手动测试一次。测试通过后，会每天北京时间 10:48 自动推送到微信。

## 钉钉推送

钉钉消息需要群机器人，适合你有一个自用小群或工作群的情况。

1. 在钉钉群里添加「自定义机器人」。
2. 安全设置建议选择「加签」或「自定义关键词」。如果选关键词，建议设置关键词：`AI Coding`。
3. 复制机器人 Webhook URL。
4. 在 GitHub Actions Secrets 新增：

| Secret                 | 值                          |
| ---------------------- | --------------------------- |
| `DINGTALK_WEBHOOK_URL` | 钉钉机器人 Webhook URL      |
| `DINGTALK_SECRET`      | 可选。钉钉机器人加签 secret |

不要使用 IP 白名单，因为 GitHub Actions 的出口 IP 不固定。

## 企业微信推送

1. 在企业微信群里添加「群机器人」。
2. 复制机器人 Webhook URL。
3. 在 GitHub Actions Secrets 新增：

| Secret               | 值                         |
| -------------------- | -------------------------- |
| `WECHAT_WEBHOOK_URL` | 企业微信机器人 Webhook URL |

## 邮箱推送

如果邮箱支持 SMTP relay、SMTP 授权码或 app password，可以添加：

| Secret          | 示例                                         |
| --------------- | -------------------------------------------- |
| `SMTP_HOST`     | `smtp.gmail.com` 或企业 SMTP 地址            |
| `SMTP_PORT`     | `465`                                        |
| `SMTP_USERNAME` | 发件邮箱账号                                 |
| `SMTP_PASSWORD` | SMTP 授权码、App Password 或企业邮件专用密码 |
| `EMAIL_FROM`    | 发件邮箱                                     |
| `EMAIL_TO`      | 收件邮箱                                     |

如果公司邮箱只允许 SSO 网页登录，而不提供 SMTP/API，GitHub Actions 无法安全地模拟网页登录。

## 多通道发送

同时配置多个通道时，脚本会向所有已配置通道发送。例如同时配置 `PUSHPLUS_TOKEN` 和 `DINGTALK_WEBHOOK_URL`，就会同时推送到微信和钉钉。

## 本地测试

```bash
python scripts/daily_ai_coding_news.py --dry-run
```

## 发送时间

`.github/workflows/daily-ai-coding-news.yml` 默认配置：

```yaml
- cron: "48 2 * * *"
```

GitHub Actions 使用 UTC 时间，这表示北京时间每天 10:48。避开整点可以降低 GitHub 定时任务延迟或被丢弃的概率。
