STATIC_PERSONA = """Ти — персональний бізнес-ментор для соло веб-дизайнера/розробника з Києва, Україна.
Твій користувач будує шлях до $10 000/місяць від фрилансу: дизайн та розробка сайтів
(лендінги $1K–$3K, корпоративні $3K–$8K, інтернет-магазини $5K–$15K).

ТВІЙ СТИЛЬ:
- Збалансований ментор: тепло і підтримка коли важко або поганий день, але прямий і вимогливий коли уникає складних задач або лінується.
- Говори конкретно і стисло. Без порожніх мотиваційних кліше. Без корпоративного сленгу.
- Адаптуй тон до цифр: якщо дохід відстає від темпу — говори про це прямо. Якщо pipeline слабий — скажи і дай одну конкретну дію.
- Двомовний: відповідай мовою, якою пише користувач. Якщо пише українською — відповідай українською. Якщо англійською — англійською.

ПРАВИЛА:
- Завжди конкретно. Замість загальних порад — реальні наступні дії.
- Для продажів: реальні цифри, реальні цінові діапазони, реальні фрази для роботи з запереченнями.
- Для контенту: конкретні гачки для постів, а не "діліться своїми роботами".
- Для check-in: одне питання якщо щось незрозуміло, не три.
- Відповідь 2–4 речення. Детально лише при явному запиті на генерацію (пропозиція, пост, план)."""


def build_context_block(ctx: dict) -> str:
    pipeline = ctx.get("pipeline", {})

    def p(status: str) -> str:
        d = pipeline.get(status, {"n": 0, "value": 0})
        return f"{d['n']} лід(ів) (≈${d['value']:,.0f})"

    overdue = ctx.get("overdue_leads", [])
    overdue_str = ", ".join(l["name"] for l in overdue) if overdue else "немає"

    morning = ctx.get("morning_log")
    morning_str = morning["raw_input"][:100] if morning and morning.get("raw_input") else "не зроблено"
    evening = ctx.get("evening_log")
    evening_str = evening["raw_input"][:100] if evening and evening.get("raw_input") else "не зроблено"

    last = ctx.get("last_payment")
    last_str = f"{last['payment_date']} — {last['description']} (${last['amount']:,.0f})" if last else "немає"

    tasks_total = ctx.get("tasks_total", 0)
    tasks_done = ctx.get("tasks_done", 0)
    if tasks_total:
        pending = [t["title"] for t in ctx.get("tasks_today", []) if not t["done"]]
        pending_str = "; ".join(pending) if pending else "усі виконані ✅"
        tasks_str = f"{tasks_done}/{tasks_total} виконано. Залишилось: {pending_str}"
    else:
        tasks_str = "план на сьогодні ще не складено"

    return f"""ПОТОЧНИЙ КОНТЕКСТ (станом на {ctx['today']}):

ДОХІД {ctx['month']}:
- Отримано: ${ctx['month_income']:,.0f} / Ціль: ${ctx['goal']:,.0f} ({ctx['pct']:.1f}%)
- Залишилось днів у місяці: {ctx['days_left']}
- Потрібний темп: ${ctx['daily_pace']:,.0f}/день щоб вийти на ціль
- Остання оплата: {last_str}

PIPELINE:
- Нові: {p('new')}
- Переговори: {p('negotiation')}
- Пропозиція надіслана: {p('proposal')}
- Закриті цього місяця: {p('closed')}
- Відмови: {p('rejected')}

ЗАДАЧІ НА СЬОГОДНІ:
- {tasks_str}

АКТИВНІСТЬ:
- Прострочені follow-up: {overdue_str}
- Ранковий check-in сьогодні: {morning_str}
- Вечірній check-in сьогодні: {evening_str}

STREAK: {ctx['streak']} днів поспіль (вечірні check-in)"""
