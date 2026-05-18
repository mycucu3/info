# AI Coding News Radar

这个仓库可以部署到 GitHub，每天自动抓取 AI coding 热点与科技新闻，并发送到你的邮箱。

## 部署步骤

1. 在 GitHub 新建一个仓库，把这些文件推上去。
2. 打开仓库的 `Settings -> Secrets and variables -> Actions -> New repository secret`。
3. 添加这些 secrets：

| Secret | 示例 |
| --- | --- |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USERNAME` | 你的发件邮箱账号 |
| `SMTP_PASSWORD` | 邮箱 SMTP 授权码或 app password |
| `EMAIL_FROM` | 发件邮箱 |
| `EMAIL_TO` | 收件邮箱 |

4. 进入 `Actions -> Daily AI Coding News -> Run workflow` 手动测试一次。
5. 测试通过后，它会每天北京时间 07:30 自动发送。

## 常见邮箱配置

Gmail 推荐使用 App Password：
- `SMTP_HOST=smtp.gmail.com`
- `SMTP_PORT=465`

QQ 邮箱、163 邮箱、企业邮箱也可以用，只要开启 SMTP 并使用授权码。

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
