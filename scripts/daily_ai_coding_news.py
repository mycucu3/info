import argparse
import base64
import email.utils
import hashlib
import hmac
import html
import json
import os
import smtplib
import ssl
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "ai-coding-news-agent.config.json")


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    published: datetime | None
    summary: str = ""
    score: int = 0


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_url(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ai-coding-news-radar/1.1 (+https://github.com/)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def post_json(url: str, payload: dict, timeout: int = 20) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "ai-coding-news-radar/1.1 (+https://github.com/)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None


def google_news_rss(query: str) -> list[NewsItem]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )
    raw = fetch_url(f"https://news.google.com/rss/search?{params}")
    root = ET.fromstring(raw)
    items: list[NewsItem] = []

    for node in root.findall("./channel/item")[:15]:
        title = html.unescape(node.findtext("title", default="")).strip()
        link = node.findtext("link", default="").strip()
        published = parse_datetime(node.findtext("pubDate"))
        source_node = node.find("source")
        source = source_node.text.strip() if source_node is not None and source_node.text else "Google News"
        summary = html.unescape(node.findtext("description", default="")).strip()
        if title and link:
            items.append(NewsItem(title=title, link=link, source=source, published=published, summary=summary))
    return items


def hacker_news_search(query: str) -> list[NewsItem]:
    params = urllib.parse.urlencode({"query": query, "tags": "story", "hitsPerPage": 10})
    data = json.loads(fetch_url(f"https://hn.algolia.com/api/v1/search_by_date?{params}").decode("utf-8"))
    items: list[NewsItem] = []

    for hit in data.get("hits", []):
        title = hit.get("title") or hit.get("story_title") or ""
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        published = parse_datetime(hit.get("created_at"))
        points = hit.get("points") or 0
        comments = hit.get("num_comments") or 0
        summary = f"Hacker News signal: {points} points, {comments} comments"
        if title and link:
            items.append(NewsItem(title=title, link=link, source="Hacker News", published=published, summary=summary))
    return items


def normalize_key(item: NewsItem) -> str:
    title = item.title.lower()
    for token in [" - ", " | ", " — "]:
        title = title.split(token)[0]
    return "".join(ch for ch in title if ch.isalnum() or ch.isspace()).strip()


def score_item(item: NewsItem, config: dict) -> int:
    text = f"{item.title} {item.summary} {item.source}".lower()
    tracked_entities = [name.lower() for name in config.get("tracked_entities", [])]
    important_terms = [
        "agent",
        "coding",
        "developer",
        "copilot",
        "codex",
        "claude code",
        "cursor",
        "windsurf",
        "security",
        "model",
        "open source",
        "github",
        "ai",
    ]

    score = 20
    score += sum(8 for name in tracked_entities if name in text)
    score += sum(4 for term in important_terms if term in text)

    if item.published:
        age_hours = (datetime.now(timezone.utc) - item.published).total_seconds() / 3600
        if age_hours <= 24:
            score += 25
        elif age_hours <= 72:
            score += 16
        elif age_hours <= 168:
            score += 8

    source = item.source.lower()
    if source in {"openai", "github blog", "anthropic", "microsoft", "google developers"}:
        score += 20
    elif source in {"techcrunch", "the verge", "reuters", "axios", "arstechnica", "wired"}:
        score += 14
    elif item.source == "Hacker News":
        score += 10

    return min(score, 100)


def collect_news(config: dict) -> list[NewsItem]:
    candidates: list[NewsItem] = []

    for query in config.get("queries", []):
        try:
            candidates.extend(google_news_rss(query))
        except Exception as exc:
            print(f"Google News query failed: {query}: {exc}")

    for query in ["AI coding agents", "OpenAI Codex", "GitHub Copilot coding agent", "Claude Code"]:
        try:
            candidates.extend(hacker_news_search(query))
        except Exception as exc:
            print(f"Hacker News query failed: {query}: {exc}")

    deduped: dict[str, NewsItem] = {}
    for item in candidates:
        item.score = score_item(item, config)
        key = normalize_key(item)
        if key not in deduped or item.score > deduped[key].score:
            deduped[key] = item

    return sorted(deduped.values(), key=lambda item: item.score, reverse=True)[:12]


def format_date(value: datetime | None) -> str:
    if not value:
        return "unknown date"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def clean_summary(item: NewsItem) -> str:
    summary = html.unescape(item.summary or "").replace("\n", " ")
    summary = " ".join(summary.split())
    if not summary:
        return "该事件在多个 AI coding/科技新闻查询中出现。"
    return textwrap.shorten(summary, width=180, placeholder="...")


def build_report(items: list[NewsItem]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# AI Coding 与科技新闻雷达",
        f"日期：{today}",
        "",
        "## 今日最值得看",
    ]

    for idx, item in enumerate(items[:6], start=1):
        lines.extend(
            [
                f"{idx}. {item.title}",
                f"   - 发生了什么：{clean_summary(item)}",
                "   - 为什么重要：可能影响 AI coding 工具选择、开发者工作流、团队自动化或技术决策。",
                f"   - 热度分：{item.score}/100",
                f"   - 来源：{item.source}，{format_date(item.published)}",
                f"   - 链接：{item.link}",
                "",
            ]
        )

    lines.extend(
        [
            "## AI Coding 趋势",
            "- Coding agent 正在从编辑器内补全，走向异步任务、CLI、移动端监督和企业权限治理。",
            "- 对团队来说，接下来更值得关注的是可靠性、上下文管理、成本控制、代码安全和审计能力。",
            "",
            "## 值得继续追踪",
            "- 新模型是否改变代码生成质量和价格。",
            "- GitHub、OpenAI、Anthropic、Cursor、Windsurf 等产品是否推出新的 agent 工作流。",
            "- 社区是否集中反馈权限、安全、误改代码、长任务失败等问题。",
        ]
    )
    return "\n".join(lines)


def has_email_config() -> bool:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"]
    return all(os.environ.get(name) for name in required)


def send_email(subject: str, body: str) -> None:
    if not has_email_config():
        raise RuntimeError("Email is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM, EMAIL_TO.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["EMAIL_FROM"]
    msg["To"] = os.environ["EMAIL_TO"]
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"]), context=context) as server:
        server.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        server.send_message(msg)


def has_wechat_config() -> bool:
    return bool(os.environ.get("WECHAT_WEBHOOK_URL"))


def send_wechat(subject: str, body: str) -> None:
    webhook_url = os.environ.get("WECHAT_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("WeChat is not configured. Set WECHAT_WEBHOOK_URL.")

    content = f"**{subject}**\n\n{body}"
    if len(content) > 3900:
        content = content[:3850] + "\n\n...内容过长，已截断。"

    result = post_json(
        webhook_url,
        {
            "msgtype": "markdown",
            "markdown": {"content": content},
        },
    )
    if result.get("errcode", 0) != 0:
        raise RuntimeError(f"WeChat webhook failed: {result}")


def has_dingtalk_config() -> bool:
    return bool(os.environ.get("DINGTALK_WEBHOOK_URL"))


def dingtalk_webhook_url() -> str:
    webhook_url = os.environ.get("DINGTALK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("DingTalk is not configured. Set DINGTALK_WEBHOOK_URL.")

    secret = os.environ.get("DINGTALK_SECRET")
    if not secret:
        return webhook_url

    timestamp = str(round(datetime.now().timestamp() * 1000))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest).decode("utf-8"))
    separator = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{separator}timestamp={timestamp}&sign={sign}"


def send_dingtalk(subject: str, body: str) -> None:
    content = f"### {subject}\n\n{body}"
    if len(content) > 18000:
        content = content[:17900] + "\n\n...内容过长，已截断。"

    result = post_json(
        dingtalk_webhook_url(),
        {
            "msgtype": "markdown",
            "markdown": {
                "title": subject,
                "text": content,
            },
        },
    )
    if result.get("errcode", 0) != 0:
        raise RuntimeError(f"DingTalk webhook failed: {result}")


def has_pushplus_config() -> bool:
    return bool(os.environ.get("PUSHPLUS_TOKEN"))


def send_pushplus(subject: str, body: str) -> None:
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        raise RuntimeError("PushPlus is not configured. Set PUSHPLUS_TOKEN.")

    result = post_json(
        "https://www.pushplus.plus/send",
        {
            "token": token,
            "title": subject,
            "content": body,
            "template": "markdown",
        },
    )
    if result.get("code") != 200:
        raise RuntimeError(f"PushPlus failed: {result}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print the report instead of sending.")
    args = parser.parse_args()

    config = load_config()
    items = collect_news(config)
    report = build_report(items)
    subject = f"AI Coding 与科技新闻雷达 - {datetime.now().strftime('%Y-%m-%d')}"

    if args.dry_run:
        print(report)
        return

    sent_to: list[str] = []
    if has_wechat_config():
        send_wechat(subject, report)
        sent_to.append("WeChat")
    if has_dingtalk_config():
        send_dingtalk(subject, report)
        sent_to.append("DingTalk")
    if has_pushplus_config():
        send_pushplus(subject, report)
        sent_to.append("PushPlus")
    if has_email_config():
        send_email(subject, report)
        sent_to.append("email")

    if not sent_to:
        raise RuntimeError("No delivery channel configured. Set PUSHPLUS_TOKEN, DINGTALK_WEBHOOK_URL, WECHAT_WEBHOOK_URL, or full SMTP email secrets.")

    print(f"Sent report with {len(items)} items to {', '.join(sent_to)}.")


if __name__ == "__main__":
    main()
