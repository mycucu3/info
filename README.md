# AI Coding News Radar

这个仓库可以每天自动抓取 AI coding 热点与科技新闻，并通过钉钉、企业微信或邮箱发送给你。

## 推荐方案

如果你的邮箱是企业内部认证、SSO 登录、没有 SMTP 授权码，优先用钉钉或企业微信机器人 Webhook。

个人微信没有稳定的官方 GitHub Actions 推送接口；可以用 Server 酱、PushPlus 等第三方服务转发到微信，但长期稳定性和隐私都取决于第三方平台。企业微信机器人是更可靠的方案。

## 钉钉推送

钉钉消息可以用群机器人实现，适合日常高频查看。

1. 在钉钉群里添加「自定义机器人」。
2. 安全设置建议选择「加签」或「自定义关键词」。如果选关键词，建议设置关键词：`AI Coding`。
3. 复制机器人 Webhook URL。
4. 到 GitHub 仓库：`Settings -> Secrets and variables -> Actions -> New repository secret`。
5. 新增：

| Secret | 值 |
| --- | --- |
| `DINGTALK_WEBHOOK_URL` | 钉钉机器人 Webhook URL |
| `DINGTALK_SECRET` | 可选。钉钉机器人加签 secret |

不要使用 IP 白名单，因为 GitHub Actions 的出口 IP 不固定。

## 企业微信推送

1. 在企业微信群里添加「群机器人」。
2. 复制机器人 Webhook URL。
3. 到 GitHub 仓库：`Settings -> Secrets and variables -> Actions -> New repository secret`。
4. 新增：

| Secret | 值 |
| --- | --- |
| `WECHAT_WEBHOOK_URL` | 企业微信机器人 Webhook URL |

配置后进入 `Actions -> Daily AI Coding News -> Run workflow` 手动测试一次。测试通过后，会每天北京时间 07:30 自动发到企业微信群。

## 邮箱推送

如果企业允许 SMTP relay、SMTP 授权码或邮件 API，可以继续使用邮箱推送。添加这些 secrets：

| Secret | 示例 |
| --- | --- |
| `SMTP_HOST` | `smtp.gmail.com` 或企业 SMTP 地址 |
| `SMTP_PORT` | `465` |
| `SMTP_USERNAME` | 发件邮箱账号 |
| `SMTP_PASSWORD` | SMTP 授权码、App Password 或企业邮件专用密码 |
| `EMAIL_FROM` | 发件邮箱 |
| `EMAIL_TO` | 收件邮箱 |

如果公司只允许网页登录或 SSO，而不提供 SMTP/API，那 GitHub Actions 无法安全地模拟登录网页邮箱。需要找 IT 开 SMTP relay、邮件 API、应用专用密码，或改用企业微信 Webhook。

## 同时发多个通道

同时配置 `DINGTALK_WEBHOOK_URL`、`WECHAT_WEBHOOK_URL` 和完整 SMTP secrets 时，脚本会向所有已配置通道发送。

## 本地测试

```bash
python scripts/daily_ai_coding_news.py --dry-run
```

## 调整发送时间

编辑 `.github/workflows/daily-ai-coding-news.yml` 里的 cron。GitHub Actions 使用 UTC 时间：

```yaml
- cron: "30 23 * * *"
```

这表示北京时间每天 07:30。
