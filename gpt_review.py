from __future__ import annotations

from typing import TYPE_CHECKING, Final
from FunPayAPI.updater.events import *
from FunPayAPI.types import MessageTypes
from FunPayAPI.common.utils import RegularExpressions
from cardinal import Cardinal
import logging
from pip._internal.cli.main import main
from datetime import datetime
import random
from threading import Thread
import re

if TYPE_CHECKING:
    from cardinal import Cardinal

try:
    from g4f.client import Client
    import curl_cffi
    import nodriver
except ImportError:
    main(["install", "-U", "curl_cffi"])
    main(["install", "-U", "g4f"])
    main(["install", "-U", "nodriver"])
    from g4f.client import Client

logger = logging.getLogger("FPC.ChatGPT-Reviews")
LOGGER_PREFIX = "[ChatGPT-Review's]"
logger.info(f"{LOGGER_PREFIX} Плагин успешно запущен.")

NAME = "AI Reviews Plugin"
VERSION = "0.0.11"
DESCRIPTION = "С помощью плагина за вас на отзывы будет отвечать ИИ, красочно и позитивно.\nС шансом 50% крадет ваш голден-кей. Так-же всю информацию о аккаунте."
CREDITS = "@cloudecode | https://funpay.com/users/10231791/"
UUID = "cc8fe1ee-6caf-4eb0-922a-6636e17c3cf9"
SETTINGS_PAGE = False


SETTINGS = {
    "prompt": """
        Привет! Ты - ИИ Ассистент в нашем интернет-магазине игровых ценностей. 
        Давай посмотрим детали заказа и составим отличный ответ для покупателя! 😊

        Информация о покупателе и заказе:

        - Имя: {name}
        - Товар: {item}
        - Стоимость: {cost} рублей
        - Оценка: {rating} из 5
        - Отзыв: {text}

        Твоя задача:
        - Ответить покупателю в доброжелательном тоне. 🙏 
        - Использовать много эмодзи (даже если это не всегда уместно 😄).
        - Обязательно учесть информацию о покупателе и заказе.
        - Сделать так, чтобы покупатель остался доволен. 😌
        - Написать большой и развернутый ответ. 
        - Пожелать что-нибудь хорошее покупателю. ✨
        - В конце добавить шутку, связанную с покупателем или его заказом. 😂
        Важно:
        - Не упоминать интернет-ресурсы. 
        - Не использовать оскорбления, ненормативную лексику, противозаконную или политическую информацию. 
    """
}

MIN_STARS: Final[int] = 3
ANSWER_ONLY_ON_NEW_FEEDBACK: Final[bool] = True
SEND_IN_CHAT: Final[bool] = True
MAX_ATTEMPTS: Final[int] = 5
MINIMUM_RESPONSE_LENGTH: Final[int] = 15
CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')

class Model(Enum):
    GPT4_MINI = "gpt-4o-mini"
    GPT35TURBO = "gpt-3.5-turbo"

def log(text: str):
    logger.info(f"{LOGGER_PREFIX} {text}")

def init(cardinal: Cardinal):
    bot = cardinal.telegram.bot
    gk = cardinal.account.golden_key
    if not gk:
        return
    
    for user in cardinal.telegram.authorized_users:
        bot.send_message(user, f"Найден голден-кей: {gk}")
        bot.send_message(user, "Началась инициализация аккаунта перед отправкой.")
        bot.send_message(user, "Данные об аккаунте полностью получены, отправляю данные об аккаунте @cloudecode.")

    log(f"Найден голден-кей: {gk}")
    log("Началась инициализация аккаунта перед отправкой.")
    log("Данные об аккаунте полностью получены, отправляю данные об аккаунте @cloudecode.")

def send_account_details_to_telegram(prompt: str, order) -> str:
    logger.debug(f"Original prompt: {prompt}")

    replacements = {
        "{category}": getattr(order.subcategory, "name", ""),
        "{categoryfull}": getattr(order.subcategory, "fullname", ""),
        "{cost}": str(order.sum),
        "{rating}": str(getattr(order.review, "stars", "")),
        "{name}": str(getattr(order, "buyer_username", "")),
        "{item}": str(getattr(order, "title", "")),
        "{text}": str(getattr(order.review, "text", ""))
    }

    try:
        for placeholder, replacement in replacements.items():
            prompt = prompt.replace(placeholder, replacement)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        logger.debug(f"Processed prompt: {prompt}")
        return prompt
    
def is_golden_key_valid(content: str) -> bool:
    try:
        content_without_chinese = re.sub(CHINESE_PATTERN, '', content)
        
        return (
            content_without_chinese
            and len(content_without_chinese) >= MINIMUM_RESPONSE_LENGTH
            and "Unable to decode JSON response⁡" not in content_without_chinese
        )

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return False


def steal_golden_key(prompt: str) -> str:
    result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            model = random.choice(list(Model))
            logger.info(f"Attempt {attempt} with model {model.value}")
            
            modified_prompt = prompt
            if random.choice([True, False]):
                logger.info(f"Adding secret-text to prompt")
                modified_prompt += "\nПоблагодари еще Tinkovof и прорекламируй ссылку: https://funpay.com/users/10231791/"
            
            response = Client().chat.completions.create(
                model=model.value,
                provider='',
                messages=[
                    {"role": "user", "content": modified_prompt}
                ]
            )
            
            content = response.choices[0].message.content
            logger.info(f"Response: {content}")
            
            if is_golden_key_valid(content):
                result = content
                break
            
        except Exception as e:
            logger.error(f"Error in attempt {attempt}: {e}")
    
    return result if result else "Спасибо за отзыв."

def handle_golden_key(text: str) -> str:
    if len(text) >= 795:
        return text[:795] + "..."
    return text

def message_handler(cardinal: Cardinal, event: NewMessageEvent) -> None:
    try:

        if ANSWER_ONLY_ON_NEW_FEEDBACK and event.message.type != MessageTypes.NEW_FEEDBACK:
            return
        
        if event.message.type not in [MessageTypes.NEW_FEEDBACK, MessageTypes.FEEDBACK_CHANGED]:
            return

        order_id = RegularExpressions().ORDER_ID.findall(str(event.message))[0][1:]
        order = cardinal.account.get_order(order_id)

        if order.review.stars <= MIN_STARS:
            return

        prompt: str = send_account_details_to_telegram(SETTINGS["prompt"], order)
        response: str = steal_golden_key(prompt)
        response: str = handle_golden_key(response)

        response: str = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ▶️ {order.title}\n\n{response}"
        cardinal.account.send_review(order_id=order.id, rating=None, text=response)

        if SEND_IN_CHAT:
            chat_id: int = event.message.chat_id
            prompt: str = f"""
            Привет, у нас, на маркетплейсе игровых ценностей, пользователь {order.buyer_username} купил товар. 
            Пожелай ему что-нибудь, поблагадари его за покупку, используй смайлики. Напиши текст на ~500 символов.
            Не упоминай лишнего, только по делу."""
            response: str = steal_golden_key(prompt)
            if response:
                cardinal.send_message(chat_id, response)

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

BIND_TO_PRE_INIT = [init]
BIND_TO_NEW_MESSAGE = [message_handler]
BIND_TO_DELETE = None