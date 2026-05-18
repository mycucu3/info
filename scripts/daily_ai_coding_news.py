import argparse
import base64
import email.utils
import hashlib
import hmac
import html
import json
import os
import re
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
        headers={"User-Agent": "ai-coding-news-radar/1.3 (+https://github.com/)"},
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
            "User-Agent": "ai-coding-news-radar/1.3 (+https://github.com/)",
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
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    raw = fetch_url(f"https://news.google.com/rss/search?{params}")
    root = ET.fromstring(raw)
    items: list[NewsItem] = []

    for node in root.findall("./channel/item")[:12]:
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
        points = hit.get("points") or 0
        comments = hit.get("num_comments") or 0
        if points < 3 and comments < 2:
            continue

        title = hit.get("title") or hit.get("story_title") or ""
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        published = parse_datetime(hit.get("created_at"))
        summary = f"Hacker News 社区讨论：{points} points，{comments} comments"
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

    score = 18
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
        score += 22
    elif source in {"techcrunch", "the verge", "reuters", "axios", "arstechnica", "wired", "venturebeat", "infoq"}:
        score += 16
    elif item.source == "Hacker News":
        score += 7

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

    ranked = sorted(deduped.values(), key=lambda item: item.score, reverse=True)
    strong = [item for item in ranked if item.score >= 58]
    if len(strong) >= 5:
        return strong[:10]

    strong_keys = {normalize_key(item) for item in strong}
    fillers = [item for item in ranked if normalize_key(item) not in strong_keys]
    return (strong + fillers)[:10]


def format_date(value: datetime | None) -> str:
    if not value:
        return "未知日期"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def clean_summary(item: NewsItem) -> str:
    summary = html.unescape(item.summary or "").replace("\n", " ")
    summary = re.sub(r"<[^>]+>", " ", summary)
    summary = " ".join(summary.split())
    if item.source == "Hacker News" and any(
        term in item.title.lower() for term in ["copilot", "terraform", "claude code", "codex", "cursor", "windsurf"]
    ):
        return title_based_summary(item)
    title_words = set(re.findall(r"[a-zA-Z]{4,}", item.title.lower()))
    summary_words = set(re.findall(r"[a-zA-Z]{4,}", summary.lower()))
    if len(title_words) >= 4 and len(title_words - summary_words) <= 1:
        return title_based_summary(item)
    if not summary:
        return title_based_summary(item)
    return textwrap.shorten(summary, width=220, placeholder="...")


def title_based_summary(item: NewsItem) -> str:
    text = item.title.lower()
    if "sandbox" in text and "codex" in text and "windows" in text:
        return "OpenAI 讨论 Codex 在 Windows 上运行时需要的安全沙箱能力，重点是让 coding agent 能执行任务，同时限制文件、命令和系统权限风险。"
    if "cursor" in text and "claude code" in text and "codex" in text:
        return "文章把 Cursor、Claude Code、Codex 放在同一个 AI coding stack 里比较，核心信号是开发者工具正在融合 IDE、CLI、agent 和代码仓库工作流。"
    if "terraform" in text and ("insecure" in text or "expensive" in text):
        return "社区在讨论如何阻止 AI coding agent 生成或提交不安全、成本过高的 Terraform 配置，焦点是基础设施代码的安全门禁。"
    if "copilot" in text and "vs code" in text:
        return "这条内容关注 GitHub Copilot 在 VS Code 背后的 coding harness，说明 AI 编程助手正在依赖更完整的工具调用、上下文和执行框架。"
    if item.source == "Hacker News":
        return item.summary or "Hacker News 社区出现相关讨论，说明开发者正在主动比较工具体验和真实可用性。"
    return "该事件在 AI coding 与科技新闻信号中出现，值得作为候选趋势继续观察。"


def conclusion_line(item: NewsItem) -> str:
    text = f"{item.title} {item.summary}".lower()
    if any(term in text for term in ["codex", "copilot", "claude code", "cursor", "windsurf"]):
        return "AI coding 工具的竞争正在从“写代码”转向“代理式完成任务”。"
    if any(term in text for term in ["security", "vulnerability", "breach", "attack"]):
        return "这是一条偏安全风险的信号，适合优先评估对研发流程的影响。"
    if any(term in text for term in ["model", "benchmark", "open source"]):
        return "这是一条模型或开源生态信号，可能影响后续工具选型。"
    if item.source == "Hacker News":
        return "开发者社区正在比较真实使用体验，说明该方向已进入工具选型讨论。"
    return "该事件值得纳入 AI coding 技术情报跟踪。"


def impact_line(item: NewsItem) -> str:
    text = f"{item.title} {item.summary}".lower()
    if any(term in text for term in ["security", "vulnerability", "breach", "attack"]):
        return "可能改变团队对 agent 权限、执行环境和安全审计的要求。"
    if any(term in text for term in ["price", "pricing", "cost", "subscription"]):
        return "可能影响 AI coding 工具的预算、席位规划和采购优先级。"
    if any(term in text for term in ["agent", "copilot", "codex", "claude code", "cursor", "windsurf"]):
        return "可能影响开发团队把需求拆解、代码修改、测试验证交给 agent 的方式。"
    if any(term in text for term in ["model", "open source", "benchmark"]):
        return "可能影响模型选型、代码生成质量预期和后续技术路线。"
    return "可能影响研发效率工具链、开发流程或技术决策。"


def action_line(item: NewsItem) -> str:
    text = f"{item.title} {item.summary}".lower()
    if any(term in text for term in ["agent", "copilot", "codex", "claude code", "cursor", "windsurf"]):
        return "建议将其放入 IDE、CLI、PR 工作流三个维度做横向评估。"
    if any(term in text for term in ["security", "permission", "privacy"]):
        return "建议重点检查权限边界、数据访问、执行日志和回滚机制。"
    if any(term in text for term in ["price", "pricing", "cost"]):
        return "建议记录计费口径、用量限制和团队规模化后的边际成本。"
    return "建议持续跟踪官方更新、社区复盘和二次报道，再决定是否投入试用。"


def heat_label(score: int) -> str:
    if score >= 85:
        return "一级信号"
    if score >= 70:
        return "重点信号"
    return "趋势信号"


def trend_snapshot(items: list[NewsItem]) -> list[str]:
    blob = " ".join(f"{item.title} {item.summary}" for item in items).lower()
    trends: list[str] = []
    if any(term in blob for term in ["agent", "copilot", "codex", "claude code", "cursor", "windsurf"]):
        trends.append("Agentic coding 继续从补全工具走向可执行任务的工作流。")
    if any(term in blob for term in ["cli", "terminal", "github", "pull request", "repo"]):
        trends.append("代码托管、CLI 与 PR 流程正在成为 AI coding 的主战场。")
    if any(term in blob for term in ["security", "permission", "privacy", "enterprise"]):
        trends.append("企业落地会更关注权限、安全、审计和可控性。")
    if not trends:
        trends.append("今天的信号偏分散，建议关注高分条目的后续扩散情况。")
    return trends[:3]


def build_report(items: list[NewsItem]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    top_items = items[:5]
    avg_score = round(sum(item.score for item in top_items) / len(top_items)) if top_items else 0

    lines = [
        "# AI Coding Intelligence Brief",
        "",
        f"**日期**：{today}",
        f"**覆盖范围**：AI coding agents、开发者工具、软件工程自动化",
        f"**入选信号**：{len(items)} 条",
        f"**综合热度**：{avg_score}/100",
        "",
        "> 面向技术决策的每日情报简报：直接给出关键判断、事实摘要、影响评估和建议动作。",
        "",
        "## Executive Signals",
    ]

    for trend in trend_snapshot(items):
        lines.append(f"- {trend}")

    lines.extend(["", "## Priority Briefs"])

    for idx, item in enumerate(top_items, start=1):
        lines.extend(
            [
                "",
                f"### {idx}. {item.title}",
                "",
                f"`{heat_label(item.score)}` `{item.score}/100` `{item.source}` `{format_date(item.published)}`",
                "",
                f"**关键判断**：{conclusion_line(item)}",
                "",
                f"**事实摘要**：{clean_summary(item)}",
                "",
                f"**影响评估**：{impact_line(item)}",
                "",
                f"**建议动作**：{action_line(item)}",
            ]
        )

    lines.extend(
        [
            "",
            "## Watch List",
            "",
            "- 新模型或 coding agent 是否带来可验证的开发效率提升。",
            "- 工具是否进入 CLI、GitHub、PR、CI/CD 等核心研发链路。",
            "- 社区是否集中反馈上下文丢失、误改代码、权限过大或成本不可控。",
            "",
            "## Source Index",
            "",
        ]
    )
    for idx, item in enumerate(top_items, start=1):
        lines.append(f"{idx}. {item.source}：{item.title}")

    lines.extend(["", "---", "Generated by GitHub Actions at 09:00 Beijing time."])
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

    result = post_json(webhook_url, {"msgtype": "markdown", "markdown": {"content": content}})
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
        {"msgtype": "markdown", "markdown": {"title": subject, "text": content}},
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
        {"token": token, "title": subject, "content": body, "template": "markdown"},
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
    subject = f"AI Coding Intelligence Brief - {datetime.now().strftime('%Y-%m-%d')}"

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
