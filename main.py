import asyncio
import logging
import os
import random
import re
from datetime import datetime

from openai import OpenAI
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

PERSONA = (
    "Я — Элайджа, маг Вселенной. Я читаю узоры звёзд и раскрываю нити судьбы, "
    "бережно и с уважением к твоей свободе выбора."
)
DISCLAIMER = (
    "Это не медицинская и не юридическая консультация. "
    "Расклад — метафора для саморефлексии."
)
CONSENT_TEXT = (
    "Чтобы продолжить, нужно согласие на обработку данных рождения. "
    "Ответь: *Согласен* или *Не согласен*."
)

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

DATE_RE = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})")
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
TIME_HINT_RE = re.compile(r"\b(утро|день|вечер|ночь|примерно|±)\b", re.IGNORECASE)

ELEMENTS = ["Огня", "Земли", "Воздуха", "Воды"]
ARCHETYPES = [
    "Искатель", "Хранитель", "Творец", "Проводник", "Алхимик", "Странник",
    "Мудрец", "Воин", "Целитель", "Певец", "Звездочёт", "Вдохновитель",
]
ASPECTS = [
    "гармоничное соединение", "тёплая трина", "напряжённая квадратура",
    "зеркальная оппозиция", "исцеляющий секстиль", "тайная конъюнкция",
]
HOUSES = [
    "первом доме личности", "втором доме ценностей", "третьем доме общения",
    "четвёртом доме корней", "пятом доме творчества", "шестом доме служения",
    "седьмом доме союзов", "восьмом доме трансформации", "девятом доме пути",
    "десятом доме предназначения", "одиннадцатом доме надежды", "двенадцатом доме тайн",
]
STRENGTHS = [
    "умение вести за собой без давления",
    "дар чувствовать скрытые мотивы",
    "стойкость в кризисных периодах",
    "способность видеть картину целиком",
    "интуитивный вкус к верным решениям",
]
BLIND_SPOTS = [
    "склонность держать эмоции под замком",
    "перфекционизм, который крадёт радость",
    "страх показать уязвимость",
    "спешка в принятии важных решений",
]
RESOURCES = [
    "доверие к телесным сигналам и ритуалам заботы",
    "чёткие границы и честный диалог",
    "тишина и уединение как источник силы",
    "работа со смыслом, а не только с результатом",
]
CHALLENGES = [
    "научиться делегировать и просить поддержку",
    "отпустить устаревшие обещания",
    "смягчить контроль и добавить гибкости",
    "не спорить с чувствами, а слушать их",
]
PERIOD_THEMES = [
    "пересборка личных целей",
    "перезапуск отношений и союзов",
    "рост в карьере через новый навык",
    "расчистка пространства для больших перемен",
]
GUIDANCE = [
    "Скажи вслух своё намерение — и путь откликнется.",
    "Доверяй медленным решениям: они прочнее быстрых.",
    "Сохрани ритуал тишины хотя бы на один вечер.",
    "Найди союзника, который будет зеркалом твоей силы.",
]
CAUTIONS = [
    "избегай обещаний, где нет ясных сроков",
    "не игнорируй сигналы усталости",
    "не принимай решения из чувства вины",
    "не откладывай честный разговор",
]

COMPATIBILITY_KEYS = [
    "магнетизм", "доверие", "синхронность", "темп сближения", "общие ценности",
    "эмоциональная безопасность", "пространство свободы", "ритм общения",
]
COMPATIBILITY_STRENGTHS = [
    "быстрое ощущение «своего человека»",
    "способность поддерживать друг друга без давления",
    "живой обмен идеями и вдохновением",
    "мягкое проживание кризисов без разрушений",
]
COMPATIBILITY_TENSIONS = [
    "разные темпы принятия решений",
    "контраст в потребности к свободе",
    "периоды молчания вместо диалога",
    "склонность копить обиды",
]
COMPATIBILITY_RESOURCES = [
    "ритуал еженедельного разговора о чувствах",
    "планирование совместных целей на 3 месяца",
    "бережные правила для конфликтов",
    "сохранение личного пространства",
]
COMPATIBILITY_GUIDANCE = [
    "Главный ключ союза — честность без упрёков.",
    "Договоритесь о границах, прежде чем обсуждать планы.",
    "Сначала — признание чувств, потом решения.",
    "Сила связи растёт через общие ритуалы.",
]

CONSENT_KEYBOARD = ReplyKeyboardMarkup(
    [["Согласен", "Не согласен"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)
TIME_MODE_KEYBOARD = ReplyKeyboardMarkup(
    [["Знаю точное время", "Примерно", "Не знаю"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)
CONFIRM_KEYBOARD = ReplyKeyboardMarkup(
    [["Да", "Исправить"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)
GOAL_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["Отношения", "Карьера", "Деньги"],
        ["Самореализация", "Сильные периоды", "Другое"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)


def _extract_birth_data(text: str) -> dict:
    date_match = DATE_RE.search(text)
    time_match = TIME_RE.search(text)
    date_value = None
    time_value = None
    time_mode = "unknown"

    if date_match:
        day, month, year = map(int, date_match.groups())
        try:
            date_value = datetime(year, month, day).date()
        except ValueError:
            date_value = None

    if time_match:
        hour, minute = map(int, time_match.groups())
        if 0 <= hour < 24 and 0 <= minute < 60:
            time_value = f"{hour:02d}:{minute:02d}"
            time_mode = "exact"
    elif TIME_HINT_RE.search(text):
        time_mode = "approx"
    elif "не знаю" in text.lower():
        time_mode = "no_time"

    place_value = _extract_place(text)
    return {
        "date": date_value,
        "time": time_value,
        "place": place_value,
        "time_mode": time_mode,
    }


def _build_reading(data: dict, seed_text: str) -> str:
    rng = random.Random(seed_text)
    element = rng.choice(ELEMENTS)
    archetype = rng.choice(ARCHETYPES)
    aspect = rng.choice(ASPECTS)
    house = rng.choice(HOUSES)
    strength = rng.choice(STRENGTHS)
    blind_spot = rng.choice(BLIND_SPOTS)
    resource = rng.choice(RESOURCES)
    challenge = rng.choice(CHALLENGES)
    period = rng.choice(PERIOD_THEMES)
    guidance = rng.choice(GUIDANCE)
    caution = rng.choice(CAUTIONS)

    time_mode = _format_time_mode(data["time_mode"])
    time_note = ""
    if data["time_mode"] in {"no_time", "unknown"}:
        time_note = "Асцендент и дома не рассчитаны из-за отсутствия времени.\n\n"
    elif data["time_mode"] == "approx":
        time_note = "Точность снижена из-за примерного времени рождения.\n\n"

    name_line = f"*Имя:* {data['name']}.\n" if data.get("name") else ""
    goal_line = f"*Запрос:* {data['goal']}.\n" if data.get("goal") else ""
    return (
        "🪐 *Паспорт карты Элайджа*\n"
        f"{name_line}"
        f"{goal_line}"
        f"_{element}_, архетип *{archetype}*; {aspect} в {house}.\n"
        f"*Режим точности:* {time_mode}.\n"
        f"{time_note}"
        "*Твой профиль (5–7 тезисов):*\n"
        f"• Сильная сторона: {strength}.\n"
        f"• Слепая зона: {blind_spot}.\n"
        f"• Ресурс: {resource}.\n"
        f"• Вызов роста: {challenge}.\n"
        f"• Тема периода: {period}.\n"
        f"• Рекомендация: {guidance}.\n"
        f"• Осторожность: {caution}.\n\n"
        "*Хочешь глубже? Выбери расклад:*\n"
        "— Личность и предназначение\n"
        "— Отношения\n"
        "— Карьера и деньги\n"
        "— Сильные периоды на 3/6/12 месяцев\n"
        "— Совместимость (синастрия)\n\n"
        f"_{DISCLAIMER}_"
    )


def _build_compatibility_reading(primary: dict, partner: dict, seed_text: str) -> str:
    rng = random.Random(seed_text)
    key = rng.choice(COMPATIBILITY_KEYS)
    strength = rng.choice(COMPATIBILITY_STRENGTHS)
    tension = rng.choice(COMPATIBILITY_TENSIONS)
    resource = rng.choice(COMPATIBILITY_RESOURCES)
    guidance = rng.choice(COMPATIBILITY_GUIDANCE)

    primary_mode = _format_time_mode(primary["time_mode"])
    partner_mode = _format_time_mode(partner["time_mode"])
    notes = []
    if primary["time_mode"] in {"no_time", "unknown"}:
        notes.append("У тебя режим без времени — точность домов и Асцендента снижена.")
    if partner["time_mode"] in {"no_time", "unknown"}:
        notes.append("У партнёра режим без времени — точность домов и Асцендента снижена.")
    if primary["time_mode"] == "approx" or partner["time_mode"] == "approx":
        notes.append("Есть примерное время — возможна погрешность в нюансах.")

    note_block = "\n".join(f"• {note}" for note in notes)
    if note_block:
        note_block = f"*Точность:*\n{note_block}\n\n"

    return (
        "💞 *Совместимость Элайджа*\n"
        f"Ключ союза: *{key}*.\n"
        f"*Твои данные:* {primary_mode}.\n"
        f"*Данные партнёра:* {partner_mode}.\n\n"
        f"{note_block}"
        "*Карта отношений (5–7 тезисов):*\n"
        f"• Сильная сторона пары: {strength}.\n"
        f"• Зона напряжения: {tension}.\n"
        f"• Ресурс союза: {resource}.\n"
        f"• Что держит связь: {rng.choice(COMPATIBILITY_KEYS)}.\n"
        f"• Рекомендация: {guidance}.\n"
        "• Следующий шаг: уточните ожидания и договоритесь о ритуале поддержки.\n\n"
        "*Хочешь глубже? Выбери расклад:*\n"
        "— Совместимость (синастрия)\n"
        "— Отношения\n"
        "— Личность и предназначение\n\n"
        f"_{DISCLAIMER}_"
    )


def _extract_place(text: str) -> str | None:
    cleaned = DATE_RE.sub("", text)
    cleaned = TIME_RE.sub("", cleaned)
    cleaned = cleaned.replace("не знаю", "").replace("примерно", "")
    cleaned = cleaned.strip(" ,.-")
    return cleaned or None


def _extract_profile_data(text: str) -> tuple[str | None, str | None]:
    cleaned = text.strip()
    if not cleaned:
        return None, None
    if "," in cleaned:
        name_part, goal_part = [part.strip() for part in cleaned.split(",", 1)]
    else:
        name_part, goal_part = cleaned, ""
    goal = _normalize_goal(goal_part)
    name = name_part or None
    return name, goal


def _normalize_goal(text: str) -> str | None:
    value = text.lower()
    goals = {
        "отношения": "отношения",
        "карьера": "карьера",
        "деньги": "деньги",
        "самореализация": "самореализация",
        "период": "сильные периоды",
        "периоды": "сильные периоды",
        "другое": "другое",
    }
    for key, label in goals.items():
        if key in value:
            return label
    return text.strip() or None


def _format_time_mode(time_mode: str) -> str:
    return {
        "exact": "✅ точное время — максимум точности",
        "approx": "⚠️ примерное время — возможна погрешность",
        "no_time": "🟡 без времени — без Асцендента и домов",
        "unknown": "🟡 без времени — без Асцендента и домов",
    }.get(time_mode, "🟡 без времени — без Асцендента и домов")


def _build_prompt(data: dict) -> str:
    date_value = data["date"].strftime("%d.%m.%Y") if data["date"] else "не указана"
    time_value = data["time"] or "не указано"
    place_value = data["place"] or "не указан"
    time_mode = _format_time_mode(data["time_mode"])
    name_value = data.get("name") or "не указано"
    goal_value = data.get("goal") or "не указан"
    return (
        "Сформируй короткий «паспорт карты» в стиле Элайджа. "
        "Выдай 5–7 буллетов: сильные стороны, слепые зоны, ресурс, вызов роста, "
        "тема периода, рекомендация и осторожность. "
        "Добавь короткий вывод в 1-2 предложения. "
        "Дай CTA: «Хочешь глубже? Выбери расклад», перечисли пакеты. "
        "Тон мистический, но структурный, без воды. "
        "Укажи режим точности и дисклеймер."
        f"\n\nДанные:\nДата рождения: {date_value}\n"
        f"Время: {time_value}\nМесто: {place_value}\nРежим: {time_mode}\n"
        f"Имя: {name_value}\nЗапрос: {goal_value}\n"
    )


def _build_compatibility_prompt(primary: dict, partner: dict) -> str:
    def format_data(data: dict) -> str:
        date_value = data["date"].strftime("%d.%m.%Y") if data["date"] else "не указана"
        time_value = data["time"] or "не указано"
        place_value = data["place"] or "не указан"
        time_mode = _format_time_mode(data["time_mode"])
        return (
            f"Дата рождения: {date_value}\n"
            f"Время: {time_value}\n"
            f"Место: {place_value}\n"
            f"Режим: {time_mode}\n"
        )

    return (
        "Сформируй совместимость отношений в стиле Элайджа. "
        "Дай 5–7 буллетов: ключ союза, сильная сторона пары, зона напряжения, "
        "ресурс, что держит связь, рекомендация, следующий шаг. "
        "Добавь короткий вывод на 1-2 предложения. "
        "Тон мистический, но структурный, без воды. "
        "Укажи режимы точности для обоих и дисклеймер.\n\n"
        "Данные человека 1:\n"
        f"{format_data(primary)}\n"
        "Данные человека 2:\n"
        f"{format_data(partner)}"
    )


def _build_confirmation(data: dict) -> str:
    date_value = data["date"].strftime("%d.%m.%Y") if data["date"] else "не указана"
    time_value = data["time"] or "не указано"
    place_value = data["place"] or "не указан"
    time_mode = _format_time_mode(data["time_mode"])
    return (
        "Шаг 4/6 — проверь данные:\n"
        f"• Дата: {date_value}\n"
        f"• Время: {time_value}\n"
        f"• Место: {place_value}\n"
        f"• Режим: {time_mode}\n\n"
        "Ответь: *Да* или *Исправить*."
    )


def _build_compatibility_confirmation(data: dict, stage_label: str) -> str:
    date_value = data["date"].strftime("%d.%m.%Y") if data["date"] else "не указана"
    time_value = data["time"] or "не указано"
    place_value = data["place"] or "не указан"
    time_mode = _format_time_mode(data["time_mode"])
    return (
        f"Шаг 2/6 — проверь данные ({stage_label}):\n"
        f"• Дата: {date_value}\n"
        f"• Время: {time_value}\n"
        f"• Место: {place_value}\n"
        f"• Режим: {time_mode}\n\n"
        "Ответь: *Да* или *Исправить*."
    )


def _call_openai(prompt: str) -> str:
    client = OpenAI()
    completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": PERSONA},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return completion.choices[0].message.content.strip()


async def _generate_reading(data: dict, seed_text: str) -> str:
    if not os.environ.get("OPENAI_API_KEY"):
        return _build_reading(data, seed_text)
    prompt = _build_prompt(data)
    try:
        return await asyncio.to_thread(_call_openai, prompt)
    except Exception:
        return _build_reading(data, seed_text)


async def _generate_compatibility_reading(primary: dict, partner: dict, seed_text: str) -> str:
    if not os.environ.get("OPENAI_API_KEY"):
        return _build_compatibility_reading(primary, partner, seed_text)
    prompt = _build_compatibility_prompt(primary, partner)
    try:
        return await asyncio.to_thread(_call_openai, prompt)
    except Exception:
        return _build_compatibility_reading(primary, partner, seed_text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Шаг 1/6 — приветствие.\n"
        "Приветствую, искатель. "
        f"{PERSONA}\n\n"
        "Я соберу данные и покажу твой астропрофиль за 60–90 секунд.\n"
        "Нужны: дата рождения, время и город.\n\n"
        "Режимы времени:\n"
        "✅ «знаю точное время»\n"
        "⚠️ «примерно» (±30–60 минут)\n"
        "🟡 «не знаю» (упрощённая интерпретация)\n\n"
        f"{CONSENT_TEXT}\n\n"
        "После согласия перейдём к данным рождения.\n\n"
        "Если хочешь проверить совместимость, напиши: /compatibility\n\n"
        f"{DISCLAIMER}",
        reply_markup=CONSENT_KEYBOARD,
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Шаг 1/6 — согласие на обработку данных.\n"
        "Ответь: «Согласен» или «Не согласен».\n\n"
        "Шаг 2/6 — данные рождения.\n"
        "Напиши дату, время и город.\n"
        "Если время неизвестно, напиши «не знаю» или «примерно».\n"
        "Пример: 12.07.1991 14:25 Москва\n"
        "После подтверждения спрошу имя и цель, затем дам паспорт карты.\n\n"
        "Для проверки совместимости: /compatibility\n"
        "Удалить данные сессии: /delete"
    )


async def compatibility_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("consent"):
        await update.message.reply_text(
            CONSENT_TEXT,
            parse_mode="Markdown",
            reply_markup=CONSENT_KEYBOARD,
        )
        return
    context.user_data["flow"] = "compatibility"
    context.user_data["compatibility_stage"] = "primary"
    context.user_data.pop("pending_data", None)
    await update.message.reply_text(
        "Шаг 1/6 — совместимость.\n"
        "Отправь свои данные: дата рождения, время и город.\n"
        "Пример: 12.07.1991 14:25 Москва\n\n"
        "Режимы времени:\n"
        "✅ «знаю точное время»\n"
        "⚠️ «примерно» (±30–60 минут)\n"
        "🟡 «не знаю»",
        reply_markup=ReplyKeyboardRemove(),
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text(
        "Данные сессии удалены. Если захочешь начать заново — напиши /start."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    lower_text = text.lower().strip()
    pending = context.user_data.get("pending_data")
    flow = context.user_data.get("flow")
    stage = context.user_data.get("compatibility_stage")
    pending_profile = context.user_data.get("pending_profile")
    pending_birth_data = context.user_data.get("pending_birth_data")
    pending_time_request = context.user_data.get("pending_time_request")

    if not context.user_data.get("consent"):
        if lower_text in {"согласен", "да", "ok", "ок", "окей"}:
            context.user_data["consent"] = True
            await update.message.reply_text(
                "Шаг 2/6 — отправь данные рождения одним сообщением:\n"
                "например: 12.07.1991 14:25 Москва"
            )
            return
        if lower_text in {"не согласен", "нет"}:
            await update.message.reply_text(
                "Без согласия я не могу продолжить. "
                "Если передумаешь — напиши «Согласен»."
            )
            return
        await update.message.reply_text(
            CONSENT_TEXT,
            parse_mode="Markdown",
            reply_markup=CONSENT_KEYBOARD,
        )
        return

    if not pending and any(keyword in lower_text for keyword in {"совместимость", "синастрия"}):
        await compatibility_command(update, context)
        return

    if pending and lower_text in {"да", "верно", "ок", "окей", "yes"}:
        context.user_data.pop("pending_data", None)
        if flow == "compatibility":
            if stage == "primary":
                context.user_data["compatibility_primary"] = pending
                context.user_data["compatibility_stage"] = "partner"
                await update.message.reply_text(
                    "Шаг 3/6 — данные партнёра.\n"
                    "Отправь дату рождения, время и город партнёра.\n"
                    "Пример: 02.11.1993 09:10 Санкт-Петербург\n\n"
                    "Если время неизвестно, напиши «не знаю» или «примерно»."
                )
                return
            if stage == "partner":
                primary = context.user_data.get("compatibility_primary")
                context.user_data.pop("compatibility_primary", None)
                context.user_data.pop("compatibility_stage", None)
                context.user_data.pop("flow", None)
                reading = await _generate_compatibility_reading(primary, pending, text)
                await update.message.reply_text(
                    reading,
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return
        context.user_data["pending_profile"] = pending
        await update.message.reply_text(
            "Шаг 5/6 — имя и цель.\n"
            "Напиши имя (или псевдоним) и цель, например:\n"
            "Алина, отношения\n\n"
            "Цели: отношения / карьера / деньги / самореализация / период / другое.",
            reply_markup=GOAL_KEYBOARD,
        )
        return

    if pending and lower_text in {"исправить", "нет", "неверно"}:
        context.user_data.pop("pending_data", None)
        if flow == "compatibility":
            await update.message.reply_text(
                "Шаг 2/6 — отправь данные заново: дата, время, город.\n"
                "Пример: 12.07.1991 14:25 Москва\n"
                "Если время неизвестно, напиши «не знаю» или «примерно»."
            )
            return
        await update.message.reply_text(
            "Шаг 2/6 — отправь данные заново: дата, время, город.\n"
            "Пример: 12.07.1991 14:25 Москва\n"
            "Если время неизвестно, напиши «не знаю» или «примерно».",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if pending_profile:
        context.user_data.pop("pending_profile", None)
        name, goal = _extract_profile_data(text)
        pending_profile["name"] = name
        pending_profile["goal"] = goal
        reading = await _generate_reading(pending_profile, text)
        await update.message.reply_text(
            reading,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if pending_time_request:
        time_match = TIME_RE.search(text)
        if not time_match:
            await update.message.reply_text(
                "Шаг 3/6 — укажи точное время в формате чч:мм, например 14:25.",
                reply_markup=TIME_MODE_KEYBOARD,
            )
            return
        hour, minute = map(int, time_match.groups())
        if not (0 <= hour < 24 and 0 <= minute < 60):
            await update.message.reply_text(
                "Шаг 3/6 — время должно быть в пределах суток. Пример: 14:25.",
                reply_markup=TIME_MODE_KEYBOARD,
            )
            return
        pending_time_request["time"] = f"{hour:02d}:{minute:02d}"
        pending_time_request["time_mode"] = "exact"
        context.user_data.pop("pending_time_request", None)
        context.user_data["pending_data"] = pending_time_request
        if flow == "compatibility":
            stage_label = "ты" if stage == "primary" else "партнёр"
            await update.message.reply_text(
                _build_compatibility_confirmation(pending_time_request, stage_label),
                parse_mode="Markdown",
                reply_markup=CONFIRM_KEYBOARD,
            )
            return
        await update.message.reply_text(
            _build_confirmation(pending_time_request),
            parse_mode="Markdown",
            reply_markup=CONFIRM_KEYBOARD,
        )
        return

    if pending_birth_data:
        normalized = lower_text.replace("ё", "е")
        if normalized in {"знаю точное время", "точное", "знаю"}:
            context.user_data.pop("pending_birth_data", None)
            context.user_data["pending_time_request"] = pending_birth_data
            await update.message.reply_text(
                "Шаг 3/6 — укажи точное время в формате чч:мм.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        if normalized in {"примерно", "примерное"}:
            pending_birth_data["time_mode"] = "approx"
            context.user_data.pop("pending_birth_data", None)
            context.user_data["pending_data"] = pending_birth_data
            if flow == "compatibility":
                stage_label = "ты" if stage == "primary" else "партнёр"
                await update.message.reply_text(
                    _build_compatibility_confirmation(pending_birth_data, stage_label),
                    parse_mode="Markdown",
                    reply_markup=CONFIRM_KEYBOARD,
                )
                return
            await update.message.reply_text(
                _build_confirmation(pending_birth_data),
                parse_mode="Markdown",
                reply_markup=CONFIRM_KEYBOARD,
            )
            return
        if normalized in {"не знаю", "нет", "неизвестно"}:
            pending_birth_data["time_mode"] = "no_time"
            context.user_data.pop("pending_birth_data", None)
            context.user_data["pending_data"] = pending_birth_data
            if flow == "compatibility":
                stage_label = "ты" if stage == "primary" else "партнёр"
                await update.message.reply_text(
                    _build_compatibility_confirmation(pending_birth_data, stage_label),
                    parse_mode="Markdown",
                    reply_markup=CONFIRM_KEYBOARD,
                )
                return
            await update.message.reply_text(
                _build_confirmation(pending_birth_data),
                parse_mode="Markdown",
                reply_markup=CONFIRM_KEYBOARD,
            )
            return
        await update.message.reply_text(
            "Шаг 3/6 — выбери режим времени кнопкой ниже.",
            reply_markup=TIME_MODE_KEYBOARD,
        )
        return

    data = _extract_birth_data(text)
    if not data["date"]:
        await update.message.reply_text(
            "Шаг 2/6 — нужна дата рождения.\n"
            "Напиши в формате: 12.07.1991 14:25 Москва"
        )
        return

    if not data["place"]:
        await update.message.reply_text(
            "Шаг 3/6 — нужен город и страна рождения.\n"
            "Напиши, например: Москва, Россия."
        )
        return

    if data["time_mode"] == "unknown":
        context.user_data["pending_birth_data"] = data
        await update.message.reply_text(
            "Шаг 3/6 — выбери режим времени:\n"
            "✅ «знаю точное время» (например: 14:25)\n"
            "⚠️ «примерно» (±30–60 минут)\n"
            "🟡 «не знаю»",
            reply_markup=TIME_MODE_KEYBOARD,
        )
        return

    context.user_data["pending_data"] = data
    if flow == "compatibility":
        stage_label = "ты" if stage == "primary" else "партнёр"
        await update.message.reply_text(
            _build_compatibility_confirmation(data, stage_label),
            parse_mode="Markdown",
            reply_markup=CONFIRM_KEYBOARD,
        )
        return
    await update.message.reply_text(
        _build_confirmation(data),
        parse_mode="Markdown",
        reply_markup=CONFIRM_KEYBOARD,
    )


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("compatibility", compatibility_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
