from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Дохід", callback_data="cmd_income"),
            InlineKeyboardButton("🔗 Ліди", callback_data="cmd_leads"),
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


def save_cancel_keyboard(save_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💾 Зберегти", callback_data=save_cb),
        InlineKeyboardButton("❌ Не зберігати", callback_data="cancel"),
    ]])


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Пропустити", callback_data="skip"),
    ]])
