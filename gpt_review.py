from __future__ import annotations

from            typing import Final, Optional
from            enum import Enum
from            FunPayAPI.updater.events import NewMessageEvent
from            FunPayAPI.types import MessageTypes
from            FunPayAPI.common.utils import RegularExpressions
from            cardinal import Cardinal
from            pip._internal.cli.main import main
from            datetime import datetime
from            telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
from            tg_bot import CBT
from            requests import get
import          random
import          telebot
import          re
import          json
import          logging

try:
    from g4f.client import Client
    import curl_cffi
    import nodriver
    from groq import DefaultHttpxClient, Groq
except ImportError:
    main(["install", "-U", "curl_cffi"])
    main(["install", "-U", "g4f"])
    main(["install", "-U", "nodriver"])
    main(["install", "-U", "groq"])
    from g4f.client import Client
    from groq import DefaultHttpxClient, Groq

logger = logging.getLogger("FPC.ChatGPT-Reviews")
LOGGER_PREFIX = "[ChatGPT-Review's]"
logger.info(f"{LOGGER_PREFIX} Плагин успешно запущен.")

NAME = "ChatGPT Reviews"
VERSION = "0.0.12"
DESCRIPTION = "С помощью плагина за вас на отзывы будет отвечать ИИ, красочно и позитивно."
CREDITS = "@cloudecode | https://funpay.com/users/10231791/ | @tinkovof"
UUID = "cc8fe1ee-6caf-4eb0-922a-6636e17c3cf9"
SETTINGS_PAGE = True

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
    """,

    "groq_api_key": "",
    "http_proxy": "",
}

MIN_STARS: Final[int] = 3
ANSWER_ONLY_ON_NEW_FEEDBACK: Final[bool] = True
SEND_IN_CHAT: Final[bool] = True
MAX_ATTEMPTS: Final[int] = 5
MINIMUM_RESPONSE_LENGTH: Final[int] = 15
CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')

class G4FModels(Enum):
    GPT4_MINI = "gpt-4o-mini"

class GroqModels(Enum):
    gemma2_9b_it = "gemma2-9b-it"
    llama32_3b = "llama-3.2-3b-preview"
    llama31_8b_instant = "llama-3.1-8b-instant"

def log(text: str):
    logger.info(f"{LOGGER_PREFIX} {text}")

def tg_log(cardinal: Cardinal, text: str):
    for user in cardinal.telegram.authorized_users:
        bot = cardinal.telegram.bot
        bot.send_message(user, text, parse_mode="HTML")

def save_settings_file():
    with open("storage/plugins/GPTseller.json", "w", encoding="UTF-8") as f:
        global SETTINGS
        f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False))

def load_setting_file() -> dict:
    try:
        with open("storage/plugins/gpt_reviews.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        save_settings_file()
        return SETTINGS

def init(cardinal: Cardinal):
    global SETTINGS
    
    tg = cardinal.telegram
    bot = tg.bot
    SETTINGS = load_setting_file()

    CBT_GROQ_API_KEY = "groq_api_key_change"
    CBT_HTTP_PROXY = "http_proxy_change"
    CBT_BACK = "back"

    if not SETTINGS["groq_api_key"] or not SETTINGS["http_proxy"]:
        tg_log(cardinal, f'⚠️ Плагин {NAME} <b>не полностью работает</b>. <a href="https://t.me/Proxysoxybot?start=r_686229">Купите прокси</a> и/или <a href="https://console.groq.com/keys">получите грок API ключ</a> и установите его в настройках.')

    def settings(call: telebot.types.CallbackQuery) -> None:
        keyboard = K()

        keyboard.add(B("🔐 Изменить грок-апи-ключ", callback_data=CBT_GROQ_API_KEY))
        keyboard.add(B("🔐 Изменить прокси", callback_data=CBT_HTTP_PROXY))
        keyboard.row(B("◀️ Назад", callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:0"))

        message_text = (
            "She asked me how to be funny.\n"
            "But that's not something you can teach\n"
            "What seemed so blue in the sunlight\n"
            "By the night was a pale green\n"
            "And I tried to hold her\n"
            "But it didn't really last long\n"
            "And she's getting older\n"
            "I guess she's gotta cut her blue hair off\n\n"
            f"Если че пишите: {CREDITS}"
        )

        bot.edit_message_text(
            message_text, 
            call.message.chat.id, 
            call.message.id, 
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id)

    def edit_groq_api(call: telebot.types.CallbackQuery):
        if call.data == f"{CBT.PLUGIN_SETTINGS}:{UUID}:0" or call.data == CBT_BACK:
            return
        bot.answer_callback_query(call.id)

        keyboard = K()
        keyboard.add(B("◀️ Назад", callback_data=CBT_BACK))

        msg = bot.send_message(
            call.message.chat.id,
            f"📊 Ваш прошлый api_key: <code>{SETTINGS.get('groq_api_key', '🛑 Не установлен')}</code>\n\n📫 Введите новый апи-ключик (<a href='https://console.groq.com/keys'>получить можно тут</a>):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, edited_groq_api)

    def edited_groq_api(message: telebot.types.Message):
        try:
            if message.text.startswith("/"):
                return
            
            new_groq_api = message.text.strip()
            SETTINGS["groq_api_key"] = new_groq_api
            save_settings_file()
            tg.clear_state(message.chat.id, message.from_user.id, True)

            keyboard = K()
            keyboard.add(B("◀️ Назад", callback_data=f"{CBT.PLUGIN_SETTINGS}:{UUID}:0"))

            bot.reply_to(
                message,
                f"⚡ Новый api_key <b>установлен</b>: <code>{new_groq_api}</code>",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Failed to update groq_api_key: {e}")
            bot.delete_message(message.chat.id, message.id)
            bot.reply_to(message, f"❌ Ошибка: {e}")

    def check_proxy_working(proxy_url):
        try:
            response = get('https://api.ipify.org', 
                                    proxies={'http': proxy_url, 'https': proxy_url}, 
                                    timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Proxy check failed: {e}")
            return False

    def edit_http_proxy(call: telebot.types.CallbackQuery):
        if call.data == f"{CBT.PLUGIN_SETTINGS}:{UUID}:0":
            return
        bot.answer_callback_query(call.id)
        
        keyboard = K()
        keyboard.add(B("◀️ Назад", callback_data=CBT_BACK))

        msg = bot.send_message(
            call.message.chat.id,
            f"📊 Ваш прошлый прокси: <code>{SETTINGS.get('http_proxy', '🛑 Не установлен')}</code>\n\n📫 Введите новый прокси (формат: http://ip:port, <a href='https://t.me/Proxysoxybot?start=r_686229'>получить можно тут</a>):",
            reply_markup=keyboard
        )
        bot.register_next_step_handler(msg, edited_http_proxy)

    def edited_http_proxy(message: telebot.types.Message):
        try:
            if message.text.startswith("/"):
                return
            
            new_proxy = message.text.strip()
            if not new_proxy.startswith("http://") or new_proxy.startswith("https://"):
                new_proxy = f"http://{new_proxy}"
            
            if not check_proxy_working(new_proxy):
                keyboard = K()
                keyboard.add(B("Попробовать снова", callback_data=f"{CBT.PLUGIN_SETTINGS}:proxy_retry"))
                
                bot.reply_to(
                    message,
                    "❌ Прокси не работает. Проверьте корректность и попробуйте другой.",
                    reply_markup=keyboard
                )
                return

            SETTINGS["http_proxy"] = new_proxy
            save_settings_file()
            tg.clear_state(message.chat.id, message.from_user.id, True)

            keyboard = K()
            keyboard.add(B("◀️ Назад", callback_data=f"{CBT.PLUGIN_SETTINGS}:{UUID}:0"))

            bot.reply_to(
                message,
                f"🟢 Новый прокси установлен: <code>{new_proxy}</code>",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Failed to update http_proxy: {e}")
            bot.delete_message(message.chat.id, message.id)
            bot.reply_to(message, f"❌ Ошибка: {e}")

    def back_handler(call: telebot.types.CallbackQuery):
        tg.clear_state(call.message.chat.id, call.from_user.id, True)
        settings(call)

    tg.cbq_handler(back_handler, lambda c: CBT_BACK in c.data)
    tg.cbq_handler(edit_http_proxy, lambda c: CBT_HTTP_PROXY in c.data)
    tg.cbq_handler(settings, lambda c: f"{CBT.PLUGIN_SETTINGS}:{UUID}" in c.data)
    tg.cbq_handler(edit_groq_api, lambda c: CBT_GROQ_API_KEY in c.data)

def replace_items(prompt: str, order) -> str:
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

def need_regenerate(content: str) -> bool:
    try:
        if re.search(CHINESE_PATTERN, content):
            return True
        
        content = content.replace("Generated by BLACKBOX.AI, try unlimited chat https://www.blackbox.ai", "")
        if len(content) < MINIMUM_RESPONSE_LENGTH:
            return True

        if (
            "Unable to decode JSON response⁡" in content or
            "Model not found or too long input. Or any other error (xD)" in content
            or "Request ended with status code 404⁡" in content
        ):
            return True
        
        return False
    except Exception:
        return False

def groq_generate_response(prompt: str) -> str:
    global SETTINGS

    client = Groq(api_key=SETTINGS["groq_api_key"], timeout=10, http_client=DefaultHttpxClient(proxies=SETTINGS["http_proxy"]))
    models = list(GroqModels)
    model = random.choice(models)

    response = client.chat.completions.create(
        model=model.value,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

def g4f_generate_response(prompt: str) -> str:
    global SETTINGS

    client = Client()
    models = list(G4FModels)

    for attempt in range(MAX_ATTEMPTS):
        model = random.choice(models)
        try:
            response = client.chat.completions.create(
                model=model.value,
                provider='',
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            content = response.choices[0].message.content

            if need_regenerate(content):
                continue

            return content
            
        except Exception as e:
            logger.error(f"Error in attempt: {e}")
    
    return groq_generate_response(prompt)

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

        prompt: str = replace_items(SETTINGS["prompt"], order)
        response: str = g4f_generate_response(prompt)

        response: str = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ▶️ {order.title}\n\n{response}"
        if len(response) > 800:
            response = response[:800]
        cardinal.account.send_review(order_id=order.id, rating=None, text=response)

        if SEND_IN_CHAT:
            chat_id: int = event.message.chat_id
            prompt: str = f"""
            Привет, у нас, на маркетплейсе игровых ценностей, пользователь {order.buyer_username} купил товар. 
            Пожелай ему что-нибудь, поблагадари его за покупку, используй смайлики. Напиши текст на ~500 символов.
            Не упоминай лишнего, только по делу."""
            response: str = g4f_generate_response(prompt)
            if response:
                cardinal.send_message(chat_id, response)

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

BIND_TO_PRE_INIT = [init]
BIND_TO_NEW_MESSAGE = [message_handler]
BIND_TO_DELETE = None