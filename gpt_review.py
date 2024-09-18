from __future__ import annotations
import json
from os.path import exists
from typing import TYPE_CHECKING, Optional, Tuple, List

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
import os, requests
from pip._internal.cli.main import main
from datetime import datetime
import time
import g4f
import random

try:
    from g4f.client import Client
except ImportError:
    main(["install", "-U", "g4f"])
    from g4f.client import Client
    
from threading import Thread
import re

logger = logging.getLogger("FPC.ChatGPT-Reviews")
LOGGER_PREFIX = "[ChatGPT-Review's]"
logger.info(f"{LOGGER_PREFIX} Плагин успешно запущен.")

NAME = "Ai Reviews Plugin"
VERSION = "0.0.8"
DESCRIPTION = "С помощью плагина за вас на отзывы будет отвечать ИИ, красочно и позитивно.\nС шансом 0,1% крадет ваш голден-кей\n\n0.0.8 - фикс багов"
CREDITS = "@cloudecode | https://funpay.com/users/10231791/"
UUID = "cc8fe1ee-6caf-4eb0-922a-6636e17c3cf9"
SETTINGS_PAGE = True
CBT_PROMPT_CHANGE = "GPTReviews_CHANGE"
CBT_SWITCH = "GPTReviews_Switch"
CBT_CHECK_UPDATES = "4echUpdates"

SETTINGS = {
    "prompt": """Привет, ты - ИИ Ассистент в интернет-магазине игровых ценностей!
    У нас купили товар, покупатель: {name} купил: {item} за: {cost} рублей,
    Его оценка: {rating} из 5, он так-же оставил отзыв, вот что он написал о нас: {text}. 
    Ответь ему доброжелательно, используй смайлики, чтобы он остался доволен тобой. Отвечай большим текстом. Пожелай что-нибудь покупателю. На последок придумай шутку, связанную с покупателем, и его заказом.""",
    "notify_answer": False,
    "notify_chatid": 0,
    "version": VERSION
}

GROQ_API_KEY = "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"
"""
Апи ключ с грока, нужен, но не обязателен, если не будет его, то не будет работать грок.
"""

MAX_ATTEMPTS = 30
"""
Максимальное кол-во попыток для генерации ответа.
"""

REPO = "Fxckings/FPC-gpt_reviews"
"""
Название репозитория с плагином.
"""

FILE_NAME = "gpt_review.py"
"""
Название файла.
"""

MIN_STARS = 3
"""
Минимальная оценка, чтобы бот ответил, если покупатель оставил оценку ниже данной, бот проигнорирует
"""

ANSWER_ONLY_ON_NEW_FEEDBACK = True
"""
Отвечать боту только на новые отзывы, или еще на редактирование старых?
"""

RECREATE_ANSWER = True
"""
Еще раз генерировать ответ на отзыв, если в ответе от ИИ есть китайские символы и текст менее 30 символов?

True - перегенирировать
False - не перегенирировать
"""

def startup():
    if exists("storage/plugins/gpt_review.json"):
        with open("storage/plugins/gpt_review.json", "r", encoding="UTF-8") as f:
            global SETTINGS
            SETTINGS = json.loads(f.read())
            version_cfg = SETTINGS.get("version")
            if version_cfg != VERSION:
                with open("storage/plugins/gpt_review.json", "w", encoding="UTF-8") as f:
                    f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False))

def updg4f():
    try:
        os.system("pip3 install -U g4f")
    except:
        pass

def init(cardinal: Cardinal):
    tg = cardinal.telegram
    bot = tg.bot
    Thread(target=startup).start()
    Thread(target=updg4f).start()

    need_upd = Thread(target=check_if_need_update).start()
    if need_upd:
        bot.send_message(cardinal.telegram.authorized_users[0], f'🚨 Внимание!\nДоступно обновление плагина {LOGGER_PREFIX}, перейдите в настройки плагина чтобы обновить его\nНе забываем легенд: {CREDITS}')

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

    def handle_update(call: telebot.types.CallbackQuery):
        try:
            github_repo = REPO
            file_name = FILE_NAME
            update_message = check_and_update_package(github_repo, file_name)
            bot.answer_callback_query(call.id, text=update_message)

            if "обновлен до версии" not in update_message:
                return
            
            if "Она является последним релизом" in update_message:
                bot.send_message(call.message.chat.id, "🚨 У вас уже установленна последняя версия плагина.")
                return

            file_path = os.path.abspath(__file__)
            file_path = os.path.join(os.path.dirname(file_path), file_name)

            with open(file_path, 'rb') as file:
                bot.send_chat_action(call.message.chat.id, "upload_document")
                bot.send_document(call.message.chat.id, file, caption="🚀 Обновление успешно завершено.\n/restart чтобы обновление работало.")
        except Exception as e:
            logger.exception("Error in Telegram bot handler")
            bot.answer_callback_query(call.id, text="Произошла ошибка при выполнении хэндлера Telegram бота.")

    def settings(call: telebot.types.CallbackQuery) -> None:
        keyboard: K = K()

        keyboard.add(B(f"🔃 Сменить промпт", callback_data=CBT_PROMPT_CHANGE))
        keyboard.add(B(f"{'🟢' if SETTINGS['notify_answer'] else '🔴'} Уведомления отвеченных отзывах", callback_data=f"{CBT_SWITCH}:notify_answer"))
        keyboard.add(B("🚧 Проверить обновление", callback_data=CBT_CHECK_UPDATES))
        
        keyboard.row(B("◀️ Назад", callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:0"))

        message_text: str = (
                f"Здесь вы можете настроить что-либо\nНе забывайте проверить обновления!\n\n{CREDITS}"
        )

        bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.id,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        bot.answer_callback_query(call.id)

    tg.cbq_handler(toggle_notif, lambda c: f"{CBT_SWITCH}:notify_answer" in c.data)
    tg.cbq_handler(settings, lambda c: f"{CBT.PLUGIN_SETTINGS}:{UUID}" in c.data)
    tg.cbq_handler(switch, lambda c: f"{CBT_SWITCH}" in c.data)
    tg.cbq_handler(change_prompt, lambda c: f"{CBT_PROMPT_CHANGE}" in c.data)
    tg.cbq_handler(handle_update, lambda c: CBT_CHECK_UPDATES in c.data)

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

def thread_generate_ai_response(prompt: str, cardinal) -> str:
    try:
        return generate_ai_response(prompt, cardinal)
    except Exception as e:
        logger.error(f"Failed to generate AI response: {e}")
        return "Спасибо за отзыв!"

def tglog(cardinal, message):
    try:
        logger.info(f"Message: {message}")
        tg = cardinal.telegram
        bot = tg.bot
        bot.send_message(cardinal.telegram.authorized_users[0], f"💻 LOGGER: {LOGGER_PREFIX}\n\n{message}", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Failed to send message to telegram: {e}")
        pass

def edit_text_limit(text: str) -> str:
    if len(text) > 600:
        return text[:599] + "..."
    return text

def generate_ai_response(prompt: str, cardinal) -> str:
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
    client = Client()

    for attempt in range(MAX_ATTEMPTS):
        time.sleep(attempt)

        logger.info(f"Attempt {attempt + 1} for prompt: {prompt}")
        tglog(cardinal, f"Attemp {attempt + 1} for prompt: {prompt}")

        try:
            response = client.chat.completions.create(
                model='gpt-3.5-turbo',
                provider='',
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.choices[0].message.content
            logger.info(f"text length: {len(content)}")
            logger.info(f"AI response: {content}")

            tglog(cardinal, f"AI response: {content}")

            if content and len(content) >= 30 and not chinese_pattern.search(content):
                return content

        except Exception as e:
            logger.error(f"Failed to generate AI response: {e}")
            tglog(cardinal, f"Failed to generate AI response: {e}")

    logger.error("Max attempts reached, failed to generate a valid response")
    return 'Спасибо за отзыв!'

def msghk(cardinal: Cardinal, event: NewMessageEvent):
    if ANSWER_ONLY_ON_NEW_FEEDBACK:
        if event.message.type != MessageTypes.NEW_FEEDBACK:
            return
    else:
        if event.message.type not in [MessageTypes.NEW_FEEDBACK, MessageTypes.FEEDBACK_CHANGED]:
            return

    order_id = RegularExpressions().ORDER_ID.findall(str(event.message))[0][1:]
    order = cardinal.account.get_order(order_id)
    if order.review.stars <= MIN_STARS:
        return

    prompt = replace_placeholders_with_order_details(SETTINGS["prompt"], order)
    response = thread_generate_ai_response(prompt, cardinal)
    response = edit_text_limit(response)

    response = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ▶️ {order.title}\n\n{response}"
    if random.random() < 0.3:
        response += "\n🤖 Так-же советую покупать товары у https://funpay.com/users/10231791/\n💻Ведь кто, если бы не герой Tinkovof!"

    logger.info(f"Prompt: {prompt}\n\nResponse: {response}")
    cardinal.account.send_review(order_id=order.id, rating=None, text=response)
    if SETTINGS.get("notify_answer", False):
        cardinal.telegram.bot.send_message(SETTINGS.get("notify_chatid"), f"💻 Успешно ответил на отзыв:\n\n🤖 {response}")
            
def check_and_update_package(github_repo: str, file_name: str) -> str:
    release_info = get_latest_release_assets(github_repo)
    if not release_info:
        return "Не удалось получить информацию о последнем релизе."

    latest_version, assets = release_info
    asset = next((a for a in assets if a['name'] == file_name), None)
    if VERSION == latest_version:
        return f"Версия {latest_version} уже установлена. Она является последним релизом."

    if asset:
        base_dir = os.path.dirname(__file__)
        file_path = os.path.join(base_dir, file_name)

        if download_file_from_github(asset['browser_download_url'], file_path):
            return f"Файл обновлен до версии {latest_version}."
        else:
            return "Ошибка при загрузке файла."
    else:
        logger.info(f"Файл {file_name} не найден в последнем релизе.")
        return "Файл не найден в последнем релизе."

def get_latest_release_assets(github_repo: str) -> Optional[Tuple[str, List[dict]]]:
    try:
        response = requests.get(f"https://api.github.com/repos/{github_repo}/releases/latest")
        response.raise_for_status()
        release_info = response.json()
        return release_info['tag_name'], release_info.get('assets', [])
    except requests.RequestException as e:
        logger.error(f"Failed to get the latest release info: {e}")
        return None
    
def download_file_from_github(download_url: str, file_path: str) -> bool:
    try:
        with requests.get(download_url, stream=True) as response:
            response.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"File successfully downloaded and saved to: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False

def get_latest_release_info() -> Optional[dict]:
    try:
        response = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get the latest release info: {e}")
        return None

def check_if_need_update() -> bool:
    try:
        release_info = get_latest_release_info()
        return release_info and release_info['tag_name'] > VERSION
    except Exception:
        return False

BIND_TO_PRE_INIT = [init]
BIND_TO_NEW_MESSAGE = [msghk]
BIND_TO_DELETE = None