from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 План дня", callback_data="cmd_plan_day"),
            InlineKeyboardButton("✅ Задачі", callback_data="cmd_tasks"),
        ],
        [
            InlineKeyboardButton("🗓 План тижня", callback_data="cmd_plan_week"),
            InlineKeyboardButton("📆 План місяця", callback_data="cmd_plan_month"),
        ],
        [
            InlineKeyboardButton("🗂 Огляд планів", callback_data="cmd_plan_overview"),
            InlineKeyboardButton("📅 Зустрічі", callback_data="cmd_meetings"),
        ],
        [
            InlineKeyboardButton("💰 Дохід", callback_data="cmd_income"),
            InlineKeyboardButton("🔗 Ліди", callback_data="cmd_leads"),
        ],
        [
            InlineKeyboardButton("💸 Витрати", callback_data="cmd_expenses"),
            InlineKeyboardButton("🔁 Підписки", callback_data="cmd_subscriptions"),
        ],
        [
            InlineKeyboardButton("🎯 Ціль місяця", callback_data="cmd_setgoal"),
            InlineKeyboardButton("📡 Канали", callback_data="cmd_channels"),
        ],
        [
            InlineKeyboardButton("📄 Пропозиція", callback_data="cmd_proposal"),
            InlineKeyboardButton("🧮 Ціна", callback_data="cmd_price"),
        ],
        [
            InlineKeyboardButton("✍️ Контент", callback_data="cmd_post_idea"),
            InlineKeyboardButton("📊 Огляд тижня", callback_data="cmd_review_week"),
        ],
        [
            InlineKeyboardButton("🌅 Ранок", callback_data="cmd_morning"),
            InlineKeyboardButton("🌆 Вечір", callback_data="cmd_evening"),
        ],
        [
            InlineKeyboardButton("❓ Запитати ментора", callback_data="cmd_ask"),
        ],
    ])


def mood_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("😞 1", callback_data="mood_1"),
        InlineKeyboardButton("😕 2", callback_data="mood_2"),
        InlineKeyboardButton("😐 3", callback_data="mood_3"),
        InlineKeyboardButton("🙂 4", callback_data="mood_4"),
        InlineKeyboardButton("😄 5", callback_data="mood_5"),
    ]])


def lead_status_keyboard(lead_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Переговори", callback_data=f"lstatus_{lead_id}_negotiation"),
            InlineKeyboardButton("📄 Пропозиція", callback_data=f"lstatus_{lead_id}_proposal"),
        ],
        [
            InlineKeyboardButton("✅ Закрито", callback_data=f"lstatus_{lead_id}_closed"),
            InlineKeyboardButton("❌ Відмова", callback_data=f"lstatus_{lead_id}_rejected"),
        ],
    ])


def proposal_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖼 Лендінг", callback_data="ptype_landing"),
            InlineKeyboardButton("🏢 Корпоративний", callback_data="ptype_corporate"),
        ],
        [
            InlineKeyboardButton("🛒 Інтернет-магазин", callback_data="ptype_ecommerce"),
            InlineKeyboardButton("🔧 Підтримка", callback_data="ptype_support"),
        ],
    ])


def platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("LinkedIn", callback_data="platform_linkedin"),
            InlineKeyboardButton("Behance", callback_data="platform_behance"),
        ],
        [
            InlineKeyboardButton("Telegram", callback_data="platform_telegram"),
            InlineKeyboardButton("Instagram", callback_data="platform_instagram"),
        ],
    ])


def weekly_platforms_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("LinkedIn + Instagram", callback_data="wplat_li_ig"),
            InlineKeyboardButton("LinkedIn + Behance", callback_data="wplat_li_be"),
        ],
        [
            InlineKeyboardButton("Всі (LinkedIn, Instagram, Behance, Telegram)", callback_data="wplat_all"),
        ],
    ])


def save_cancel_keyboard(save_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💾 Зберегти", callback_data=save_cb),
        InlineKeyboardButton("❌ Не зберігати", callback_data="cancel"),
    ]])


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Пропустити", callback_data="skip"),
    ]])


def tasks_keyboard(tasks: list[dict], horizon: str = "day") -> InlineKeyboardMarkup:
    """One button per task that toggles its done state, plus a generate/re-generate row."""
    rows = []
    for t in tasks:
        mark = "✅" if t["done"] else "⬜️"
        title = t["title"]
        if len(title) > 40:
            title = title[:39] + "…"
        rows.append([InlineKeyboardButton(f"{mark} {title}", callback_data=f"task_{t['id']}")])
    label = "♻️ Перегенерувати план" if tasks else "✨ Скласти план"
    rows.append([InlineKeyboardButton(label, callback_data=f"cmd_plan_{horizon}")])
    return InlineKeyboardMarkup(rows)


def plan_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Прийняти план", callback_data="plan_accept"),
            InlineKeyboardButton("🔄 Перегенерувати", callback_data="plan_regen"),
        ],
        [InlineKeyboardButton("✏️ Додати свою задачу", callback_data="plan_add_own")],
    ])


def subscriptions_keyboard(subs: list[dict]) -> InlineKeyboardMarkup:
    """A delete button per active subscription."""
    rows = []
    for s in subs:
        rows.append([InlineKeyboardButton(
            f"🗑 {s['name']} (${s['amount']:,.0f})", callback_data=f"subdel_{s['id']}"
        )])
    return InlineKeyboardMarkup(rows)


def meeting_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Створити", callback_data="mtg_create"),
        InlineKeyboardButton("❌ Скасувати", callback_data="mtg_cancel"),
    ]])


def meetings_keyboard(meetings: list[dict]) -> InlineKeyboardMarkup:
    """A cancel button per upcoming meeting."""
    rows = []
    for m in meetings:
        title = m["title"]
        if len(title) > 30:
            title = title[:29] + "…"
        rows.append([InlineKeyboardButton(f"🗑 {title}", callback_data=f"mtgdel_{m['id']}")])
    return InlineKeyboardMarkup(rows)


def goal_confirm_keyboard(suggested: float | None) -> InlineKeyboardMarkup:
    rows = []
    if suggested:
        rows.append([InlineKeyboardButton(f"✅ Прийняти ${suggested:,.0f}", callback_data=f"goal_accept_{int(suggested)}")])
    rows.append([InlineKeyboardButton("✏️ Ввести свою цифру", callback_data="goal_manual")])
    return InlineKeyboardMarkup(rows)
