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
