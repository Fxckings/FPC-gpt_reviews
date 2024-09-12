from __future__ import annotations
import json
from os.path import exists
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cardinal import Cardinal
from FunPayAPI.updater.events import *
from FunPayAPI.types import MessageTypes
from FunPayAPI.common.utils import RegularExpressions
import telebot
from tg_bot import CBT
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
from cardinal import Cardinal
import logging

try:
    import g4f
    from g4f.client import Client
    from g4f.Provider import Groq
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "g4f"])
    importlib.import_module("g4f")
    import g4f
    from g4f.client import Client
    from g4f.Provider import Groq
    
import subprocess, sys
import importlib
from threading import Thread
import re

logger = logging.getLogger("FPC.ChatGPT-Reviews")
LOGGER_PREFIX = "[ChatGPT-Review's]"
logger.info(f"{LOGGER_PREFIX} Плагин успешно запущен.")

NAME = "ChatGPT-Review's"
VERSION = "0.0.8"
DESCRIPTION = "Плагин добавляет функцию ИИ ответов на отзывы."
CREDITS = "@cloudecode"
UUID = "cc8fe1ee-6caf-4eb0-922a-6636e17c3cf9"
SETTINGS_PAGE = True
CBT_PROMPT_CHANGE = "GPTReviews_CHANGE"
CBT_SWITCH = "GPTReviews_Switch"

SETTINGS = {
    "prompt": "Привет, покупатель: {name} купил: {item} за: {cost} рублей в нашем магазине, его оценка: {rating} по 5ти бальной шкале, он так-же оставил отзыв: {text}. Ответь ему, используй смайлики, чтобы он остался доволен тобой. Отвечай большим текстом. Пожелай что-нибудь покупателю",
    "notify_answer": False,
    "notify_chatid": 0,
    "version": VERSION
}

GROQ_API_KEY = "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"
"""
Апи ключ с грока, нужен, но не обязателен, если не будет его, то не будет работать грок.
"""

def init(cardinal: Cardinal):
    tg = cardinal.telegram
    bot = tg.bot
    Thread(target=startup).start()

    def startup():
        if exists("storage/plugins/gpt_review.json"):
            with open("storage/plugins/gpt_review.json", "r", encoding="UTF-8") as f:
                global SETTINGS
                SETTINGS = json.loads(f.read())
                version_cfg = SETTINGS.get("version")
                if version_cfg != VERSION:
                    with open("storage/plugins/gpt_review.json", "w", encoding="UTF-8") as f:
                        f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False))

    def save_config():
        with open("storage/plugins/gpt_review.json", "w", encoding="UTF-8") as f:
            global SETTINGS
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False))

    def switch(call: telebot.types.CallbackQuery):
        setting_key = call.data.split(":")[1]
        if setting_key in SETTINGS:
            SETTINGS[setting_key] = not SETTINGS[setting_key]
            save_config()
            settings(call)        

    def change_prompt(call: telebot.types.CallbackQuery):
        if call.data != f"{CBT.PLUGIN_SETTINGS}:{UUID}:0":
            msg = bot.send_message(call.message.chat.id, f"Ваш прошлый PROMPT:<code>{SETTINGS['prompt']}</code>\n\nВведите новый промпт:")
            bot.register_next_step_handler(msg, prompt_changed)
				
    def prompt_changed(message: telebot.types.Message):
            try:
                new_prompt = message.text
                SETTINGS["prompt"] = new_prompt
                save_config()
                tg.clear_state(message.chat.id, message.from_user.id, True)
                keyboard = K()
                keyboard.add(B("◀️ Назад", callback_data=f"{CBT.PLUGIN_SETTINGS}:{UUID}:0"))
                bot.reply_to(message, f"🟢 Новый промпт установлен: <code>{new_prompt}</code>", reply_markup=keyboard)
            except Exception as e:
                bot.delete_message(message.chat.id, message.id)

    def toggle_notif(call: telebot.types.CallbackQuery):
        SETTINGS["notify_chatid"] = call.message.chat.id
        SETTINGS["notify_answer"] = not SETTINGS.get("notify_answer", False)
        save_config()
        settings(call)

    def settings(call: telebot.types.CallbackQuery):
        keyboard = K()
        keyboard.add(B(f"Сменить промпт", callback_data=CBT_PROMPT_CHANGE))
        keyboard.add(B(f"Уведомления отвеченных отзывах {'🟢' if SETTINGS['notify_answer'] else '🔴'}", callback_data=f"{CBT_SWITCH}:notify_answer"))
        keyboard.row(B("◀️ Назад", callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:0"))
        bot.edit_message_text(f"В данном разделе вы можете настроить плагин\nЖоски кодер: {CREDITS}", call.message.chat.id, call.message.id, reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    tg.cbq_handler(toggle_notif, lambda c: f"{CBT_SWITCH}:notify_answer" in c.data)
    tg.cbq_handler(settings, lambda c: f"{CBT.PLUGIN_SETTINGS}:{UUID}" in c.data)
    tg.cbq_handler(switch, lambda c: f"{CBT_SWITCH}" in c.data)
    tg.cbq_handler(change_prompt, lambda c: f"{CBT_PROMPT_CHANGE}" in c.data)

def replace_placeholders_with_order_details(prompt: str, order) -> str:
    logger.debug(f"{prompt}")

    replacements = {
        "{category}": order.subcategory.name,
        "{categoryfull}": order.subcategory.fullname,
        "{cost}": str(order.sum),
        "{rating}": str(order.review.stars),
        "{name}": str(order.buyer_username),
        "{item}": order.title,
        "{text}": str(order.review.text)
    }

    try:
        for placeholder, replacement in replacements.items():
            prompt = prompt.replace(placeholder, replacement)
        return prompt
    except KeyError as e:
        logger.error(f"Error when replacing placeholders in prompt: {e}")
        return prompt

def thread_generate_ai_response(prompt: str):
    Thread(target=generate_ai_response, args=(prompt,)).start()

def generate_ai_response(prompt: str):
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
    client = Client()
    max_attempts = 5

    for _ in range(max_attempts):
        for model, provider, client in [("gpt-3.5-turbo", None), ("", Groq)]:
            try:
                if provider == Groq:
                    client = Client(api_key=GROQ_API_KEY)
                    
                response = client.chat.completions.create(
                    model=model,
                    provider=provider,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = response.choices[0].message.content
                if len(content) < 30 or chinese_pattern.search(content):
                    continue  # Ре-генерация если содержит китайские буквы или менее 30 символов
                return content
            except Exception as e:
                logger.error(f"Error when making a request to the AI\n{e}")

    return None

def format_text4review(text: str) -> str:
    if len(text) > 1000:
        lines = text.splitlines()
        if len(lines) > 10:
            lines = lines[:10]
            if lines[-1]:
                lines[-1] += " "
            lines[-1] += " "
        text = "\n".join(lines).rstrip() + " "
    return text

def msghk(cardinal: Cardinal, event: NewMessageEvent):
    if event.message.type not in [MessageTypes.NEW_FEEDBACK, MessageTypes.FEEDBACK_CHANGED]:
        return

    order_id = int(RegularExpressions().ORDER_ID.findall(str(event.message))[0][1:])
    order = cardinal.account.get_order(order_id)
    if order.status == types.OrderStatuses.REFUNDED:
        return

    prompt = replace_placeholders_with_order_details(SETTINGS["prompt"], order)
    response = thread_generate_ai_response(prompt)

    if response:
        response = format_text4review(response)
        logger.info(f"Prompt: {prompt}\n\nResponse: {response}")
        cardinal.account.send_review(order_id=order.id, rating=None, text=response)
        if SETTINGS.get("notify_answer", False):
            cardinal.telegram.bot.send_message(SETTINGS.get("notify_chatid"), f"💻 Успешно ответил на отзыв:\n\n🤖 {response}")
            
BIND_TO_PRE_INIT = [init]
BIND_TO_NEW_MESSAGE = [msghk]
BIND_TO_DELETE = None