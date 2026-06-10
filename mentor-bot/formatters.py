import html
import re


def md_to_html(text: str) -> str:
    """Convert the AI's standard Markdown into the subset of HTML that Telegram
    renders. Claude replies use **bold**, *italic*, `code`, ``` blocks,
    # headings, [links](url) and - bullets — none of which Telegram shows
    without a parse_mode. We translate to <b>/<i>/<code>/<pre>/<a> and bullets,
    escaping everything else so user/AI text can't break the markup."""
    if not text:
        return text

    placeholders: list[str] = []

    def _stash(rendered: str) -> str:
        placeholders.append(rendered)
        return f"\x00{len(placeholders) - 1}\x00"

    # Fenced code blocks ```…``` → <pre> (escape inner, stash so nothing else
    # touches the contents).
    def _fence(m: re.Match) -> str:
        body = html.escape(m.group(1))
        return _stash(f"<pre>{body}</pre>")

    text = re.sub(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", _fence, text, flags=re.DOTALL)

    # Inline code `…` → <code>.
    def _code(m: re.Match) -> str:
        return _stash(f"<code>{html.escape(m.group(1))}</code>")

    text = re.sub(r"`([^`\n]+)`", _code, text)

    # Links [text](url) → <a>. Stash so the text/url aren't re-processed.
    def _link(m: re.Match) -> str:
        label = html.escape(m.group(1))
        url = html.escape(m.group(2), quote=True)
        return _stash(f'<a href="{url}">{label}</a>')

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", _link, text)

    # Escape the remaining text before injecting our own tags.
    text = html.escape(text)

    # Headings (#, ##, ###) → bold lines (Telegram has no headings). Strip any
    # inner **/__ first so we don't emit nested <b><b> that Telegram rejects.
    def _heading(m: re.Match) -> str:
        inner = m.group(1).replace("**", "").replace("__", "")
        return f"<b>{inner}</b>"

    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$", _heading, text)

    # Bold: **text** / __text__ (run before italic so ** isn't eaten by *).
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)

    # Italic: *text* / _text_ (single markers, not part of a word like a_b).
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<i>\1</i>", text)

    # Bullet markers (- or *) at line start → • for readability.
    text = re.sub(r"(?m)^(\s*)[-*]\s+", r"\1• ", text)

    # Restore stashed inline/code/link fragments.
    for i, rendered in enumerate(placeholders):
        text = text.replace(f"\x00{i}\x00", rendered)

    return text


def income_bar(current: float, goal: float, width: int = 20) -> str:
    pct = min(current / goal, 1.0) if goal else 0
    pct = max(pct, 0.0)
    filled = int(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct * 100:.1f}% (${current:,.0f} / ${goal:,.0f})"


def income_breakdown(ctx: dict) -> str:
    return (
        f"Оборот: ${ctx['month_income']:,.0f} | "
        f"Витрати: ${ctx['month_oneoff_expenses']:,.0f} | "
        f"Підписки: ${ctx['subscriptions_total']:,.0f}"
    )


def split_message(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        split_at = text.rfind("\n\n", 0, max_len)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()
    return parts


def format_pipeline(pipeline: dict) -> str:
    statuses = [
        ("new", "🆕 Нові"),
        ("negotiation", "💬 Переговори"),
        ("proposal", "📄 Пропозиція"),
        ("closed", "✅ Закриті"),
        ("rejected", "❌ Відмови"),
    ]
    lines = []
    for key, label in statuses:
        d = pipeline.get(key, {"n": 0, "value": 0})
        if d["n"] > 0 or key in ("new", "negotiation", "proposal"):
            lines.append(f"{label}: {d['n']} лід(ів)  ≈${d['value']:,.0f}")
    return "\n".join(lines)


def format_lead(lead: dict) -> str:
    status_icons = {
        "new": "🆕", "negotiation": "💬", "proposal": "📄",
        "closed": "✅", "rejected": "❌",
    }
    icon = status_icons.get(lead["status"], "•")
    value = f"${lead['estimated_value']:,.0f}" if lead.get("estimated_value") else "—"
    lines = [f"{icon} <b>{lead['name']}</b>  {value}"]
    if lead.get("company"):
        lines.append(f"   🏢 {lead['company']}")
    if lead.get("project_type"):
        lines.append(f"   🛠 {lead['project_type']}")
    if lead.get("next_action"):
        lines.append(f"   ➡️ {lead['next_action']}")
        if lead.get("next_action_date"):
            lines.append(f"   📅 до {lead['next_action_date']}")
    return "\n".join(lines)


def format_leads_list(leads: list[dict]) -> str:
    if not leads:
        return "Активних лідів немає."
    return "\n\n".join(format_lead(l) for l in leads)


def format_income_history(rows: list[dict], expenses_by_month: dict | None = None) -> str:
    if not rows:
        return "Записів про доходи ще немає."
    expenses_by_month = expenses_by_month or {}
    lines = ["📊 <b>Дохід по місяцях:</b>\n"]
    for r in rows:
        exp = expenses_by_month.get(r["month"], 0)
        net = r["total"] - exp
        line = f"  {r['month']}:  оборот ${r['total']:,.0f}"
        if exp:
            line += f"  −${exp:,.0f}  =  <b>${net:,.0f}</b>"
        line += f"  ({r['n_payments']} оплат)"
        lines.append(line)
    lines.append("\n<i>Витрати по місяцях не включають поточні підписки.</i>")
    return "\n".join(lines)


def format_checkin_history(logs: list[dict]) -> str:
    if not logs:
        return "Записів check-in ще немає."
    lines = []
    for log in logs:
        icon = "🌅" if log["log_type"] == "morning" else "🌆"
        mood = f"  настрій {log['mood_score']}/5" if log.get("mood_score") else ""
        lines.append(f"{icon} <b>{log['log_date']}</b>{mood}")
        if log.get("raw_input"):
            preview = log["raw_input"][:80] + ("…" if len(log["raw_input"]) > 80 else "")
            lines.append(f"   {preview}")
    return "\n".join(lines)
