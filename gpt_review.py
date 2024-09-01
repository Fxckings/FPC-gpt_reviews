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
from g4f.client import Client
from g4f.Provider import Groq

groqapi= "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"
client = Client(api_key=groqapi)

logger = logging.getLogger("FPC.ChatGPT-Review's")
LOGGER_PREFIX = "[ChatGPT-Review's]"
in_progress = False
logger.info(f"{LOGGER_PREFIX} Плагин успешно запущен.")

NAME = "ChatGPT-Review's"
VERSION = "0.0.7"
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

def init(cardinal: Cardinal):
    tg = cardinal.telegram
    bot = tg.bot

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
        keyboard.add(B(f"Сменить ПРОМПТ", callback_data=CBT_PROMPT_CHANGE))
        keyboard.add(B(f"Уведомления отвеченных отзывах {'🟢' if SETTINGS['notify_answer'] else '🔴'}", callback_data=f"{CBT_SWITCH}:notify_answer"))
        keyboard.row(B("◀️ Назад", callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:0"))
        bot.edit_message_text("В данном разделе вы можете настроить плагин", call.message.chat.id, call.message.id, reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    tg.cbq_handler(toggle_notif, lambda c: f"{CBT_SWITCH}:notify_answer" in c.data)
    tg.cbq_handler(settings, lambda c: f"{CBT.PLUGIN_SETTINGS}:{UUID}" in c.data)
    tg.cbq_handler(switch, lambda c: f"{CBT_SWITCH}" in c.data)
    tg.cbq_handler(change_prompt, lambda c: f"{CBT_PROMPT_CHANGE}" in c.data)

def replace_placeholders_with_order_details(prompt: str, order) -> str:
    logger.debug(f"gpt-review: {prompt}")

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
        logger.error(f"gpt-review: Error when replacing placeholders in prompt: {e}")
        return prompt


def generate_ai_response(prompt: str):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"gpt-review: Error when making a request to the AI\n{e}\nRetrying in 0 seconds...")
        try:
            response = client.chat.completions.create(
                model="",
	            messages=[{"role": "user", "content": prompt}],
                provider=Groq
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"gpt-review: Error when making a request to the AI\n{e}")

def format_text4review(text_: str):
    if len(text_) > 1000:
        lines = text_.splitlines()
        if len(lines) > 10:
            lines = lines[:10]
            if lines[-1]:
                lines[-1] += " "
            lines[-1] += " "
        text_ = "\n".join(lines).rstrip() + " "
    return text_

def message_hook(cardinal: Cardinal, event: NewMessageEvent):
    if event.message.type not in [MessageTypes.NEW_FEEDBACK, MessageTypes.FEEDBACK_CHANGED]:
        return

    order_id = RegularExpressions().ORDER_ID.findall(str(event.message))[0][1:]
    order = cardinal.account.get_order(order_id)
    if order.status == types.OrderStatuses.REFUNDED:
        return

    prompt = replace_placeholders_with_order_details(SETTINGS["prompt"], order)
    ai_response = generate_ai_response(prompt)

    if ai_response:
        ai_response = format_text4review(ai_response)
        logger.info(f"Prompt: {prompt}\n\nResponse: {ai_response}")
        cardinal.account.send_review(order_id=order.id, rating=None, text=ai_response)
        if SETTINGS.get("notify_answer", False):
            chat_id = SETTINGS.get("notify_chatid")
            cardinal.telegram.bot.send_message(chat_id, f"💻 Успешно ответил на отзыв:\n\n🤖 {ai_response}")
            
BIND_TO_PRE_INIT = [init]
BIND_TO_NEW_MESSAGE = [message_hook]
BIND_TO_DELETE = None