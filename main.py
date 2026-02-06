import asyncio
import logging
import os
import random
import re
from datetime import datetime

from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

PERSONA = (
    "Я — Элайди, маг Вселенной. Я читаю узоры звёзд и раскрываю нити судьбы, "
    "бережно и с уважением к твоей свободе выбора."
)
DISCLAIMER = (
    "Это не медицинская и не юридическая консультация. "
    "Расклад — метафора для саморефлексии."
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

    return (
        "🪐 *Паспорт карты Элайди*\n"
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


def _extract_place(text: str) -> str | None:
    cleaned = DATE_RE.sub("", text)
    cleaned = TIME_RE.sub("", cleaned)
    cleaned = cleaned.replace("не знаю", "").replace("примерно", "")
    cleaned = cleaned.strip(" ,.-")
    return cleaned or None


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
    return (
        "Сформируй короткий «паспорт карты» в стиле Элайди. "
        "Выдай 5–7 буллетов: сильные стороны, слепые зоны, ресурс, вызов роста, "
        "тема периода, рекомендация и осторожность. "
        "Добавь короткий вывод в 1-2 предложения. "
        "Дай CTA: «Хочешь глубже? Выбери расклад», перечисли пакеты. "
        "Тон мистический, но структурный, без воды. "
        "Укажи режим точности и дисклеймер."
        f"\n\nДанные:\nДата рождения: {date_value}\n"
        f"Время: {time_value}\nМесто: {place_value}\nРежим: {time_mode}\n"
    )


def _build_confirmation(data: dict) -> str:
    date_value = data["date"].strftime("%d.%m.%Y") if data["date"] else "не указана"
    time_value = data["time"] or "не указано"
    place_value = data["place"] or "не указан"
    time_mode = _format_time_mode(data["time_mode"])
    return (
        "Шаг 4/5 — проверь данные:\n"
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Шаг 1/5 — приветствие.\n"
        "Приветствую, искатель. "
        f"{PERSONA}\n\n"
        "Я соберу данные и покажу твой астропрофиль за 60–90 секунд.\n"
        "Нужны: дата рождения, время и город.\n\n"
        "Режимы времени:\n"
        "✅ «знаю точное время»\n"
        "⚠️ «примерно» (±30–60 минут)\n"
        "🟡 «не знаю» (упрощённая интерпретация)\n\n"
        "Шаг 2/5 — отправь данные одним сообщением:\n"
        "например: 12.07.1991 14:25 Москва\n\n"
        f"{DISCLAIMER}"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Шаг 1/5 — данные рождения.\n"
        "Напиши дату, время и город.\n"
        "Если время неизвестно, напиши «не знаю» или «примерно».\n"
        "Пример: 12.07.1991 14:25 Москва\n"
        "После подтверждения я дам паспорт карты и предложу расклады."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    lower_text = text.lower().strip()
    pending = context.user_data.get("pending_data")

    if pending and lower_text in {"да", "верно", "ок", "окей", "yes"}:
        context.user_data.pop("pending_data", None)
        reading = await _generate_reading(pending, text)
        await update.message.reply_text(reading, parse_mode="Markdown")
        return

    if pending and lower_text in {"исправить", "нет", "неверно"}:
        context.user_data.pop("pending_data", None)
        await update.message.reply_text(
            "Шаг 2/5 — отправь данные заново: дата, время, город.\n"
            "Пример: 12.07.1991 14:25 Москва\n"
            "Если время неизвестно, напиши «не знаю» или «примерно»."
        )
        return

    data = _extract_birth_data(text)
    if not data["date"]:
        await update.message.reply_text(
            "Шаг 2/5 — нужна дата рождения.\n"
            "Напиши в формате: 12.07.1991 14:25 Москва"
        )
        return

    if not data["place"]:
        await update.message.reply_text(
            "Шаг 3/5 — нужен город и страна рождения.\n"
            "Напиши, например: Москва, Россия."
        )
        return

    if data["time_mode"] == "unknown":
        await update.message.reply_text(
            "Шаг 3/5 — выбери режим времени:\n"
            "✅ «знаю точное время» (например: 14:25)\n"
            "⚠️ «примерно» (±30–60 минут)\n"
            "🟡 «не знаю»"
        )
        return

    context.user_data["pending_data"] = data
    await update.message.reply_text(_build_confirmation(data), parse_mode="Markdown")


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
