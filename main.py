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
GUIDANCE = [
    "Прислушайся к телу — оно знает, где твоя истина.",
    "Отпусти старое обещание и дай место новому союзу.",
    "Сохрани ритуал тишины хотя бы на один вечер.",
    "Доверяй медленным решениям: они прочнее быстрых.",
    "Скажи вслух своё намерение — и путь откликнется.",
    "Найди союзника, который будет зеркалом твоей силы.",
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


def _build_reading(seed_text: str) -> str:
    rng = random.Random(seed_text)
    element = rng.choice(ELEMENTS)
    archetype = rng.choice(ARCHETYPES)
    aspect = rng.choice(ASPECTS)
    house = rng.choice(HOUSES)
    guidance = rng.choice(GUIDANCE)

    return (
        "🪐 *Натальный расклад Элайди*\n\n"
        f"В твоей карте звучит стихия *{element}*, открывая образ *{archetype}*.\n"
        f"Я вижу {aspect} в {house}. Это указывает на скрытую силу, которая ведёт тебя.\n\n"
        f"Совет мага: _{guidance}_"
    )


def _extract_place(text: str) -> str | None:
    cleaned = DATE_RE.sub("", text)
    cleaned = TIME_RE.sub("", cleaned)
    cleaned = cleaned.replace("не знаю", "").replace("примерно", "")
    cleaned = cleaned.strip(" ,.-")
    return cleaned or None


def _format_time_mode(time_mode: str) -> str:
    return {
        "exact": "✅ точное время",
        "approx": "⚠️ примерное время",
        "no_time": "🟡 без времени",
        "unknown": "🟡 без времени",
    }.get(time_mode, "🟡 без времени")


def _build_prompt(data: dict) -> str:
    date_value = data["date"].strftime("%d.%m.%Y") if data["date"] else "не указана"
    time_value = data["time"] or "не указано"
    place_value = data["place"] or "не указан"
    time_mode = _format_time_mode(data["time_mode"])
    return (
        "Сформируй короткий «паспорт карты» в стиле Элайди. "
        "Выдай 5–7 буллетов: сильные стороны, слепые зоны, тема месяца/года, "
        "рекомендация и осторожность. "
        "Дай короткий вывод в 1-2 предложения и CTA: «Хочешь глубже? Выбери расклад». "
        "Тон мистический, но структурный. "
        "Укажи режим точности и дисклеймер."
        f"\n\nДанные:\nДата рождения: {date_value}\n"
        f"Время: {time_value}\nМесто: {place_value}\nРежим: {time_mode}\n"
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
        return _build_reading(seed_text)
    prompt = _build_prompt(data)
    try:
        return await asyncio.to_thread(_call_openai, prompt)
    except Exception:
        return _build_reading(seed_text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Приветствую, искатель. "
        f"{PERSONA}\n\n"
        "Напиши дату рождения (дд.мм.гггг), время (чч:мм) и город. "
        "Если время неизвестно, укажи «не знаю» или «примерно».\n\n"
        f"{DISCLAIMER}"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Напиши мне сообщение с датой, временем и городом рождения.\n"
        "Если время неизвестно, напиши «не знаю».\n"
        "Пример: 12.07.1991 14:25 Москва\n"
        "Я отвечу натальным раскладом от имени Элайди."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    data = _extract_birth_data(text)
    if not data["date"]:
        await update.message.reply_text(
            "Чтобы карта была ясной, мне нужна дата рождения. "
            "Напиши в формате: 12.07.1991 14:25 Москва"
        )
        return

    reading = await _generate_reading(data, text)
    await update.message.reply_text(reading, parse_mode="Markdown")


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
