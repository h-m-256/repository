# ----------------------
#
#        __
#       / /_     ____ ____
#      / __ \   / __ `/ _ \
#     / / / /  / /_/ /  __/
#    /_/ /_/   \__,_/\___/
#
# meta developer: @h_m_256
# requires: google-genai aiohttp-socks
# full vibecode (gavno)
# meta banner: https://raw.githubusercontent.com/h-m-256/repository/main/media/banner.jpg
# meta fhsdesc: порно, nsfw, генерация, grok, gemini, gptimage, ai, ии
#
# ----------------------

import aiohttp
import asyncio
import base64
import contextvars
import inspect
import io
import json
import logging
import re
import shlex
import uuid

from PIL import Image
from telethon.tl.types import Message

from google import genai
from google.genai import types
from aiohttp_socks import ProxyConnector

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

BASE_OPENAI_URL = "https://api.openai.com/v1"
BASE_XAI_URL = "https://api.x.ai/v1"

DEFAULT_GROK_VIDEO_OPTIONS = {
    "duration": 10,
    "aspect_ratio": "16:9",
    "resolution": "480p",
    "timeout": 300,
}

DEFAULT_GPT_IMAGE_OPTIONS = {
    "size": "1024x1024",
    "quality": "high",
    "background": "auto",
    "timeout": 180,
}

DEFAULT_WAVESPEED_GROK_OPTIONS = {
    "aspect_ratio": "",
    "output_format": "jpeg",
    "timeout": 180,
}

DEFAULT_WAVESPEED_GROK_VIDEO_OPTIONS = {
    "duration": 6,
    "aspect_ratio": "16:9",
    "resolution": "720p",
    "timeout": 420,
}

VALID_GROK_VIDEO_ASPECTS = {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"}
VALID_GROK_VIDEO_RESOLUTIONS = {"480p", "720p"}

VALID_WAVESPEED_GROK_ASPECTS = {
    "2:1",
    "20:9",
    "16:9",
    "4:3",
    "3:2",
    "1:1",
    "2:3",
    "3:4",
    "9:16",
    "9:20",
    "1:2",
}
VALID_WAVESPEED_GROK_FORMATS = {"jpeg", "png"}

VALID_WAVESPEED_GROK_VIDEO_DURATIONS = {6, 10}
VALID_WAVESPEED_GROK_VIDEO_ASPECTS = {"16:9", "1:1", "9:16"}
VALID_WAVESPEED_GROK_VIDEO_RESOLUTIONS = {"480p", "720p"}


@loader.tds
class ImageGenMod(loader.Module):
    """
    Генератор и редактор изображений/видео с поддержкой разных моделей, например, бесплатно аниме-NSFW (для порно можно юзать почему нет) без цензуры, Grok (в нем довольно мало цензуры), Gemini, GPT Image либо простенькая модель через Wavespeed: Qwen Image без цензуры с Qwen Image Edit (макс для раздевания людей подходит, порно чет не умеет)
    """

    __version__ = (2, 0, 0)

    strings = {
        "name": "ImageGen",
        "api_key": "API-ключи Google AI Studio (можно несколько через запятую / пробел / Enter). Получить: https://aistudio.google.com/app/apikey — у бесплатных ключей почти нет квот",
        "model_google": "Модель Google по умолчанию",
        "quality": "Качество загружаемых фото (для .ig)",
        "system_instruction": "Системный промпт",
        "history": "Сохранять историю генераций",
        "history_limit": "Лимит записей в истории",
        "custom_emojis": "Использовать кастомные (Premium) эмодзи",
        "use_quote": "Использовать форматирование цитат (blockquote)",
        "inline_mode": "Инлайн-режим (меню с кнопками)",
        "google_search": "Использовать инструмент Google Search",
        "xai_api_key": "API-ключи xAI (Grok / Grok Video), можно несколько через запятую / пробел / Enter. Получить: https://console.x.ai — нужен платный ключ с балансом",
        "model_grok_video": "Модель Grok Video по умолчанию",
        "wavespeed_api_key": "API-ключи Wavespeed, можно несколько через запятую / пробел / Enter. Получить: https://wavespeed.ai/accesskey",
        "hf_token": "Токен HuggingFace (необязательно, можно несколько через запятую / пробел / Enter) для WaiNSFW. Получить: https://huggingface.co/settings/tokens",
        "openai_api_key": "API-ключи OpenAI для GPT Image (можно несколько через запятую / пробел / Enter). Получить: https://platform.openai.com/api-keys (нужен баланс на ключе)",
        "model_gpt_image": "Модель OpenAI GPT Image",

        "attach_success": '<blockquote><a href="tg://emoji?id=5427009714745517609">✅</a> <b>Фото прикреплено!</b> (Всего: {0})</blockquote>',
        "detach_success": '<blockquote><a href="tg://emoji?id=5427009714745517609">✅</a> <b>Все фото откреплены!</b></blockquote>',
        "attach_err": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ответьте на фото или документ!</b></blockquote>',
        "grok_limit": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Для Grok можно использовать максимум 3 изображения!</b>\nОткрепите лишние через <code>{0}igdetach</code></blockquote>',
        "wavespeed_grok_limit": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Для Grok Imagine через Wavespeed можно использовать только 1 изображение!</b>\nОткрепите лишние через <code>{0}igdetach</code></blockquote>',

        "gen_new": '<blockquote><a href="tg://emoji?id=5431456208487716895">🎨</a> <b>Генерация...</b></blockquote>{1}{2}\n{0}',
        "gen_var": '<blockquote><a href="tg://emoji?id=5431456208487716895">🎨</a> <b>Генерация (новый вариант)...</b></blockquote>{1}{2}\n{0}',
        "success": '<blockquote><a href="tg://emoji?id=5427009714745517609">✅</a> <b>Готово!</b></blockquote>{1}{2}\n{0}',
        "success_with_text": '<blockquote><a href="tg://emoji?id=5427009714745517609">✅</a> <b>Готово!</b></blockquote>{1}{2}\n{0}\n\n📜 <b>Ответ ИИ (стр. {3}/{4}):</b>\n<blockquote>{5}</blockquote>',

        "edit_new": '<blockquote><a href="tg://emoji?id=5431456208487716895">🎨</a> <b>Редактирование...</b></blockquote>{1}{2}\n{0}',
        "edit_var": '<blockquote><a href="tg://emoji?id=5431456208487716895">🎨</a> <b>Редактирование (новый вариант)...</b></blockquote>{1}{2}\n{0}',
        "edit_success": '<blockquote><a href="tg://emoji?id=5775949822993371030">🖼</a> <b>Изображение отредактировано!</b></blockquote>{1}{2}\n{0}',
        "edit_success_text": '<blockquote><a href="tg://emoji?id=5775949822993371030">🖼</a> <b>Изображение отредактировано!</b></blockquote>{1}{2}\n{0}\n\n📜 <b>Ответ ИИ (стр. {3}/{4}):</b>\n<blockquote>{5}</blockquote>',

        "video_success": '<blockquote>🎬 <b>Видео готово!</b></blockquote>{1}{2}\n{0}\n\n⏱ <b>Длительность:</b> {3}',
        "video_success_text": '<blockquote>🎬 <b>Видео готово!</b></blockquote>{1}{2}\n{0}\n\n⏱ <b>Длительность:</b> {3}\n\n📜 <b>Ответ ИИ (стр. {4}/{5}):</b>\n<blockquote>{6}</blockquote>',

        "only_text_response": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>Изображение не сгенерировано (только текст):</b></blockquote>{1}{2}\n{0}\n\n📜 <b>Ответ ИИ (стр. {3}/{4}):</b>\n<blockquote>{5}</blockquote>',
        "only_text_header_direct": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>Только текст</b></blockquote>{1}{2}\n{0}\n\n📜 <b>Ответ:</b>',
        "error_no_data": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка:</b> данные не получены.</blockquote>{1}{2}\n{0}',

        "uploading": '<blockquote><a href="tg://emoji?id=5433614747381538714">📤</a> <b>Обработка и загрузка...</b></blockquote>',

        "censor_retry": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>Цензура. Повтор ({0}/{1})...</b></blockquote>{3}\n{2}',
        "error": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка:</b>\n{0}</blockquote>',
        "error_censored": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка (цензура):</b>\n{0}</blockquote>\n<i>Попробуйте изменить запрос.</i>',
        "error_429": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>Ошибка (лимиты API):</b>\n{0}</blockquote>\n<i>Подождите немного или используйте другой ключ / платный тариф.</i>',
        "error_hidden": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Проверь логи</b></blockquote>',
        "flag_parse_error": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка флагов:</b>\n{0}</blockquote>',

        "xai_limit": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>У ключа xAI закончился баланс или лимит.</b></blockquote>\n<i>Используйте другой ключ с балансом.</i>',
        "xai_invalid": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ключ xAI невалидный.</b></blockquote>\n<i>Нужен новый API-ключ.</i>',

        "wavespeed_limit": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>У ключа Wavespeed закончились кредиты или сработал лимит.</b></blockquote>\n<i>Можно пополнить баланс или попробовать новый аккаунт Wavespeed: новым аккаунтам обычно дают $1 trial credit бесплатно. Возьмите новый API-ключ и укажите его в конфиге.</i>{0}',
        "wavespeed_invalid": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ключ Wavespeed невалидный.</b></blockquote>\n<i>Нужен новый API-ключ.</i>{0}',
        "google_invalid": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ключ Google невалидный.</b></blockquote>\n<i>Нужен новый API-ключ.</i>',
        "google_limit": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>У ключа Google закончилась квота.</b></blockquote>\n<i>Подождите или используйте другой ключ / платный тариф.</i>',
        "openai_invalid": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ключ OpenAI невалидный.</b></blockquote>\n<i>Нужен новый API-ключ.</i>',
        "openai_limit": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>У ключа OpenAI закончился баланс или лимит.</b></blockquote>\n<i>Используйте другой ключ с балансом или пополните billing.</i>',
        "openai_verification": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>Для GPT Image нужна верификация организации OpenAI.</b></blockquote>\n<i>Пройдите verification в консоли OpenAI или используйте другой ключ / модель.</i>',
        "wainsfw_error_no_key": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>WaiNSFW временно недоступен или закончилась квота.</b></blockquote>\n<i>Попробуйте подождать или добавить ключ HuggingFace.</i>{0}',
        "wainsfw_error_with_key": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>WaiNSFW временно недоступен или закончилась квота.</b></blockquote>\n<i>Попробуйте подождать или установить другой ключ в конфиге.</i>',

        "history_empty": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>История пуста!</b>',
        "history_disabled": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>История выключена</b></blockquote>',
        "history_disabled_warn": '\n\n<a href="tg://emoji?id=5420323339723881652">⚠️</a> <i>История выключена, новые записи сохраняться не будут.</i>',
        "history_cleared": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>История очищена!</b>',
        "history_cleared_n": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>Удалено последних записей: {0}</b>',
        "history_index_err": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Номер должен быть от 1 до {0}</b>',
        "select_page": '<blockquote><a href="tg://emoji?id=5771858080664915483">📄</a> <b>Выберите страницу истории:</b></blockquote>',

        "lang_warn": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>{0} работает только с английскими промптами.</b></blockquote>\n<b>Обнаружен неанглийский текст в запросе.</b>{1}\n\nПродолжить всё равно?',
        "btn_continue_anyway": "✅ Всё равно продолжить",
        "btn_cancel": "❌ Отмена",

        "history_item": '<blockquote><a href="tg://emoji?id=5775949822993371030">🖼</a> <b>История [{0}/{1}]</b></blockquote>{2}\n{3}',
        "history_item_text": '<blockquote><a href="tg://emoji?id=5775949822993371030">🖼</a> <b>История [{0}/{1}]</b></blockquote>{2}\n{3}\n\n📜 <b>Ответ ИИ (стр. {4}/{5}):</b>\n<blockquote>{6}</blockquote>',
        "history_text_only": '<blockquote>📝 <b>История (текст) [{0}/{1}]</b></blockquote>{2}\n{3}\n\n📜 <b>Ответ ИИ (стр. {4}/{5}):</b>\n<blockquote>{6}</blockquote>',
        "history_video_item": '<blockquote>🎬 <b>История [{0}/{1}]</b></blockquote>{2}\n{3}\n\n⏱ <b>Длительность:</b> {4}',
        "history_video_item_text": '<blockquote>🎬 <b>История [{0}/{1}]</b></blockquote>{2}\n{3}\n\n⏱ <b>Длительность:</b> {4}\n\n📜 <b>Ответ ИИ (стр. {5}/{6}):</b>\n<blockquote>{7}</blockquote>',

        "no_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Не установлен API-ключ для Google!</b>',
        "no_gpt_image_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Не установлен API-ключ OpenAI для GPT Image!</b>',
        "btn_regen": "🔄 Еще вариант",
        "btn_back": "🔙 Меню",
        "btn_list": "📂 Список",
        "btn_clear": "🗑 Очистить все",
        "btn_del_one": "🗑",
        "btn_close": "❌ Закрыть",
        "btn_loading": "🕘",
        "btn_show_prompt": "👁 Показать промпт",
        "btn_hide_prompt": "🙈 Скрыть промпт",
        "btn_slideshow": "🎞 Галерея",
        "btn_log": "📥 Скачать лог",
        "log_caption": '<a href="tg://emoji?id=5956561916573782596">📄</a> <b>Полный лог ошибки</b>',
        "btn_back_hist": "🔙 В историю",
        "btn_model": "⚙️ Модель",
        "select_model": '<blockquote><a href="tg://emoji?id=5341715473882955310">⚙️</a> <b>Выберите модель.</b></blockquote>\n<i>Для части провайдеров модель меняется только через конфиг модуля.</i>',
        "arg_err": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Аргумент должен быть числом > 0</b>',
        "alert_cleared": "История очищена!",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("xai_api_key", "", lambda: self.strings("xai_api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue(
                "model_grok",
                "grok-imagine-image",
                lambda: "Модель Grok по умолчанию",
            ),
            loader.ConfigValue(
                "model_grok_video",
                "grok-imagine-video",
                lambda: self.strings("model_grok_video"),
            ),
            loader.ConfigValue("wavespeed_api_key", "", lambda: self.strings("wavespeed_api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue(
                "wavespeed_grok_t2i_model",
                "x-ai/grok-imagine-image/text-to-image",
                lambda: "Модель Wavespeed Grok Imagine text-to-image",
            ),
            loader.ConfigValue(
                "wavespeed_grok_edit_model",
                "x-ai/grok-imagine-image/edit",
                lambda: "Модель Wavespeed Grok Imagine edit",
            ),
            loader.ConfigValue(
                "wavespeed_grok_video_t2v_model",
                "x-ai/grok-imagine-video/text-to-video",
                lambda: "Модель Wavespeed Grok Imagine Video text-to-video",
            ),
            loader.ConfigValue(
                "wavespeed_grok_video_i2v_model",
                "x-ai/grok-imagine-video/image-to-video",
                lambda: "Модель Wavespeed Grok Imagine Video image-to-video",
            ),
            loader.ConfigValue(
                "wavespeed_grok_video_edit_model",
                "x-ai/grok-imagine-video/edit-video",
                lambda: "Модель Wavespeed Grok Imagine Video edit-video",
            ),
            loader.ConfigValue("hf_token", "", lambda: self.strings("hf_token"), validator=loader.validators.Hidden()),
            loader.ConfigValue("openai_api_key", "", lambda: self.strings("openai_api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("proxy", "", lambda: "Прокси URL (http://... или socks5://...) для обхода блокировок", validator=loader.validators.Hidden()),
            loader.ConfigValue(
                "model_google",
                "gemini-2.5-flash-image",
                lambda: self.strings("model_google"),
            ),
            loader.ConfigValue(
                "model_gpt_image",
                "gpt-image-1",
                lambda: self.strings("model_gpt_image"),
            ),
            loader.ConfigValue(
                "wavespeed_model_t2i",
                "wavespeed-ai/qwen-image/text-to-image-2512",
                lambda: "Модель Wavespeed text-to-image",
            ),
            loader.ConfigValue(
                "wavespeed_model_i2i",
                "wavespeed-ai/qwen-image/edit-2511",
                lambda: "Модель Wavespeed image-to-image",
            ),
            loader.ConfigValue("wavespeed_size", "864*1152", lambda: "Размер изображения Wavespeed (например, 864*1152)"),
            loader.ConfigValue("retry_censor_limit", 10, lambda: "Количество автоматических попыток при ошибке модерации/цензуры", validator=loader.validators.Integer(minimum=1)),
            loader.ConfigValue("history", False, lambda: self.strings("history"), validator=loader.validators.Boolean()),
            loader.ConfigValue("history_limit", 20, lambda: self.strings("history_limit"), validator=loader.validators.Integer(minimum=1)),
            loader.ConfigValue("quality", "Low", lambda: self.strings("quality"), validator=loader.validators.Choice(["Low", "Medium", "High", "Original"])),
            loader.ConfigValue("system_instruction", "", lambda: self.strings("system_instruction")),
            loader.ConfigValue("google_search", True, lambda: self.strings("google_search"), validator=loader.validators.Boolean()),
            loader.ConfigValue("custom_emojis", True, lambda: self.strings("custom_emojis"), validator=loader.validators.Boolean()),
            loader.ConfigValue("use_quote", True, lambda: self.strings("use_quote"), validator=loader.validators.Boolean()),
            loader.ConfigValue("inline_mode", True, lambda: self.strings("inline_mode"), validator=loader.validators.Boolean()),
        )
        self.sessions = {}
        self.url_cache = {}
        self.error_cache = {}
        self.attached_images = []
        self.pending_lang_confirms = {}
        self._managed_tasks = set()

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

    def _spawn_managed_task(self, coro, sid=None, fresh_context=False):
        loop = asyncio.get_running_loop()
        try:
            if fresh_context:
                task = loop.create_task(coro, context=contextvars.Context())
            else:
                task = loop.create_task(coro)
        except TypeError:
            task = loop.create_task(coro)

        self._managed_tasks.add(task)

        if sid in self.sessions:
            self.sessions[sid]["task"] = task

        def _done(done_task):
            self._managed_tasks.discard(done_task)

            if sid in self.sessions and self.sessions[sid].get("task") is done_task:
                self.sessions[sid]["task"] = None

            try:
                done_task.result()
            except asyncio.CancelledError:
                logger.info("managed task cancelled sid=%s", sid)
            except Exception:
                logger.exception("managed task failed sid=%s", sid)

        task.add_done_callback(_done)
        return task

    async def on_unload(self):
        tasks = set()

        for task in list(self._managed_tasks):
            if task and not task.done():
                tasks.add(task)

        for session in self.sessions.values():
            session["cancel"] = True
            task = session.get("task")
            if task and not task.done():
                tasks.add(task)

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.sessions.clear()
        self.pending_lang_confirms.clear()
        self._managed_tasks.clear()

    def _guess_prefix_from_message(self, message: Message, command_names=None) -> str:
        raw = (getattr(message, "raw_text", None) or getattr(message, "text", None) or "").strip()
        command_names = list(command_names or [])

        if raw and command_names:
            for cmd in sorted(set(command_names), key=len, reverse=True):
                for pref_len in range(1, min(8, len(raw)) + 1):
                    maybe_prefix = raw[:pref_len]
                    rest = raw[pref_len:]
                    if rest.lower().startswith(cmd.lower()):
                        next_char = rest[len(cmd):len(cmd) + 1]
                        if next_char in ("", " ", "\n", "\t"):
                            return maybe_prefix

        db_variants = [
            ("hikka.main", "command_prefix"),
            ("heroku.main", "command_prefix"),
            ("main", "command_prefix"),
        ]
        for owner, key in db_variants:
            try:
                value = self.db.get(owner, key, None)
            except TypeError:
                try:
                    value = self.db.get(owner, key)
                except Exception:
                    value = None
            except Exception:
                value = None

            if isinstance(value, str) and value:
                return value

        return "."

    def _get_prefix_html(self, message: Message = None, command_names=None) -> str:
        return utils.escape_html(self._guess_prefix_from_message(message, command_names))

    def _cfg_hint(self, message: Message, config_key: str, command_names=None) -> str:
        prefix = self._get_prefix_html(message, command_names)
        return f'\n\n<i>Открой <code>{prefix}cfg {utils.escape_html(self.strings("name"))} {utils.escape_html(config_key)}</code></i>'

    def _missing_key_text(self, base_text: str, message: Message, config_key: str, command_names=None) -> str:
        return f"{base_text}{self._cfg_hint(message, config_key, command_names)}"

    def _history_cfg_hint(self, message: Message = None, command_names=None) -> str:
        prefix = self._get_prefix_html(message, command_names or ["ighist"])
        return (
            f'<i>Открой <code>{prefix}cfg '
            f'{utils.escape_html(self.strings("name"))} history</code> и включи параметр.</i>'
        )

    def _history_disabled_text(self, message: Message = None) -> str:
        return f"{self._get_str('history_disabled')}\n{self._history_cfg_hint(message, ['ighist'])}"

    def _history_disabled_warn_text(self, message: Message = None) -> str:
        return f"{self._get_str('history_disabled_warn')}\n{self._history_cfg_hint(message, ['ighist'])}"

    def _split_multi_values(self, value: str):
        raw = str(value or "").strip()
        if not raw:
            return []

        result = []
        seen = set()

        for item in re.split(r"[,\s]+", raw):
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)

        return result

    def _get_secret_values(self, *config_keys):
        result = []
        seen = set()

        for config_key in config_keys:
            try:
                raw = self.config[config_key]
            except Exception:
                raw = ""

            for item in self._split_multi_values(raw):
                if item not in seen:
                    seen.add(item)
                    result.append(item)

        return result

    def _get_secret_values_or_default(self, config_key: str, default=None):
        values = self._get_secret_values(config_key)
        return values if values else list(default or [])

    def _get_openai_keys(self):
        return self._get_secret_values("openai_api_key")

    def _get_wavespeed_cfg_hint(self, message: Message = None, command_names=None) -> str:
        names = list(command_names or [])
        names.extend(["iwgrok", "iwg", "iwgrokv", "iwgv", "iw", "igrok", "igrokv"])
        names = list(dict.fromkeys(names))
        return self._cfg_hint(message, "wavespeed_api_key", names)

    def _get_wavespeed_grok_alt_hint(self, message: Message = None) -> str:
        prefix = self._get_prefix_html(message, ["igrok", "iwgrok", "iwg"])
        module_name = utils.escape_html(self.strings("name"))

        return (
            "\n\n"
            f'<i>Или используйте Grok из Wavespeed через '
            f'<code>{prefix}iwgrok</code>, указав перед этим ключ через '
            f'<code>{prefix}cfg {module_name} wavespeed_api_key</code> (за простую регистрацию через Google/GitHub дают до 1$).</i>'
        )

    def _get_wavespeed_grok_video_alt_hint(self, message: Message = None) -> str:
        prefix = self._get_prefix_html(message, ["igrokv", "iwgrokv", "iwgv"])
        module_name = utils.escape_html(self.strings("name"))

        return (
            "\n\n"
            f'<i>Или используйте Grok Video из Wavespeed через '
            f'<code>{prefix}iwgrokv</code>, указав перед этим ключ через '
            f'<code>{prefix}cfg {module_name} wavespeed_api_key</code> (за простую регистрацию через Google/GitHub дают до 1$).</i>'
        )

    def _append_wavespeed_grok_alt_hint(self, text: str, message: Message = None) -> str:
        return f"{text}{self._get_wavespeed_grok_alt_hint(message)}"

    def _append_wavespeed_grok_video_alt_hint(self, text: str, message: Message = None) -> str:
        return f"{text}{self._get_wavespeed_grok_video_alt_hint(message)}"

    def _get_negative_prompt(self, request_options=None) -> str:
        if not isinstance(request_options, dict):
            return ""
        return str(request_options.get("negative_prompt") or "").strip()

    def _stringify_exception(self, exc: Exception) -> str:
        if exc is None:
            return "Неизвестная ошибка."

        try:
            text = str(exc).strip()
        except Exception:
            text = ""

        if not text:
            text = getattr(exc, "message", "") or repr(exc)

        if not text:
            text = exc.__class__.__name__

        return text or "Неизвестная ошибка."

    def _contains_any(self, text: str, patterns) -> bool:
        text = (text or "").lower()
        return any(pattern in text for pattern in patterns)

    def _extract_error_message(self, payload=None, fallback=None, status=None):
        variants = []

        def _push(value):
            if value is None:
                return
            if isinstance(value, (dict, list)):
                try:
                    value = json.dumps(value, ensure_ascii=False)
                except Exception:
                    value = str(value)
            value = str(value).strip()
            if value and value not in variants:
                variants.append(value)

        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                _push(err.get("message"))
                _push(err.get("detail"))
                _push(err.get("error"))
                _push(err.get("type"))
                _push(err.get("code"))
            else:
                _push(err)

            _push(payload.get("message"))
            _push(payload.get("detail"))
            _push(payload.get("status"))
            _push(payload.get("error_description"))

            data = payload.get("data")
            if isinstance(data, dict):
                _push(data.get("error"))
                _push(data.get("message"))
        else:
            _push(payload)

        _push(fallback)

        message = next((x for x in variants if x), "")
        if not message:
            message = "Неизвестная ошибка."

        if status and not message.lower().startswith("http "):
            message = f"HTTP {status}: {message}"

        return message[:2000]

    async def _read_json_or_text(self, response):
        raw_text = await response.text()
        try:
            return json.loads(raw_text), raw_text
        except Exception:
            return None, raw_text

    def _log_suppressed(self, context: str, level=logging.WARNING):
        logger.log(level, "%s", context, exc_info=True)

    def _normalize_visual_text(self, text: str) -> str:
        if not self.config["use_quote"]:
            text = text.replace("<blockquote>", "").replace("</blockquote>", "").replace("<blockquote expandable>", "")
        if not self.config["custom_emojis"]:
            text = re.sub(r'<a href="tg://emoji\?id=\d+">(.+?)</a>', r"\1", text)
        return text.strip()

    def _format_duration(self, seconds) -> str:
        if seconds is None:
            return "—"
        try:
            val = float(seconds)
        except Exception:
            return str(seconds)
        if abs(val - int(val)) < 1e-9:
            return f"{int(val)}с"
        return f"{val:.1f}с"

    def _parse_flags(self, raw_args: str, specs):
        raw_args = (raw_args or "").strip()
        if not raw_args:
            return {}, ""

        if not specs:
            return {}, raw_args

        alias_map = {}
        for spec in specs:
            for alias in spec.get("aliases", []):
                alias_map[alias] = spec

        try:
            tokens = shlex.split(raw_args, posix=True)
        except ValueError as e:
            raise ValueError(f"Некорректные кавычки: {e}") from e

        options = {}
        prompt_tokens = []
        i = 0

        while i < len(tokens):
            token = tokens[i]

            if token == "--":
                prompt_tokens.extend(tokens[i + 1:])
                break

            spec = alias_map.get(token)
            if not spec:
                prompt_tokens.append(token)
                i += 1
                continue

            if i + 1 >= len(tokens):
                raise ValueError(f"Не указано значение для флага {token}")

            value = tokens[i + 1].strip()
            if not value:
                raise ValueError(f"Пустое значение для флага {token}")

            kind = spec.get("kind", "str")
            if kind == "int":
                try:
                    value = int(value)
                except Exception as e:
                    raise ValueError(f"Флаг {token} должен быть числом") from e

            options[spec["dest"]] = value
            i += 2

        return options, " ".join(prompt_tokens).strip()

    def _normalize_grok_video_options(self, options=None):
        result = dict(DEFAULT_GROK_VIDEO_OPTIONS)
        options = options or {}

        if "duration" in options:
            value = int(options["duration"])
            if not 1 <= value <= 15:
                raise ValueError("Флаг -d / --duration должен быть от 1 до 15")
            result["duration"] = value

        if "aspect_ratio" in options:
            value = str(options["aspect_ratio"]).strip()
            if value not in VALID_GROK_VIDEO_ASPECTS:
                raise ValueError("Флаг -ar / --aspect-ratio должен быть одним из: 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3")
            result["aspect_ratio"] = value

        if "resolution" in options:
            value = str(options["resolution"]).strip().lower()
            if value not in VALID_GROK_VIDEO_RESOLUTIONS:
                raise ValueError("Флаг -r / --resolution должен быть 480p или 720p")
            result["resolution"] = value

        if "timeout" in options:
            value = int(options["timeout"])
            if not 60 <= value <= 900:
                raise ValueError("Флаг -t / --timeout должен быть от 60 до 900")
            result["timeout"] = value

        return result

    def _normalize_gpt_image_options(self, options=None):
        result = dict(DEFAULT_GPT_IMAGE_OPTIONS)
        options = options or {}

        if "size" in options:
            value = str(options["size"]).strip()
            if not value:
                raise ValueError("Флаг -s / --size не может быть пустым")
            result["size"] = value

        if "quality" in options:
            value = str(options["quality"]).strip().lower()
            if not value:
                raise ValueError("Флаг -q / --quality не может быть пустым")
            result["quality"] = value

        if "background" in options:
            value = str(options["background"]).strip().lower()
            if not value:
                raise ValueError("Флаг -bg / --background не может быть пустым")
            result["background"] = value

        if "timeout" in options:
            value = int(options["timeout"])
            if not 30 <= value <= 900:
                raise ValueError("Флаг -t / --timeout должен быть от 30 до 900")
            result["timeout"] = value

        return result

    def _normalize_wavespeed_grok_options(self, options=None):
        result = dict(DEFAULT_WAVESPEED_GROK_OPTIONS)
        options = options or {}

        if "aspect_ratio" in options:
            value = str(options["aspect_ratio"]).strip()
            if value and value not in VALID_WAVESPEED_GROK_ASPECTS:
                raise ValueError(
                    "Флаг -ar / --aspect-ratio должен быть одним из: "
                    "2:1, 20:9, 16:9, 4:3, 3:2, 1:1, 2:3, 3:4, 9:16, 9:20, 1:2"
                )
            result["aspect_ratio"] = value

        if "output_format" in options:
            value = str(options["output_format"]).strip().lower()
            if value not in VALID_WAVESPEED_GROK_FORMATS:
                raise ValueError("Флаг -f / --format должен быть jpeg или png")
            result["output_format"] = value

        if "timeout" in options:
            value = int(options["timeout"])
            if not 30 <= value <= 900:
                raise ValueError("Флаг -t / --timeout должен быть от 30 до 900")
            result["timeout"] = value

        return result

    def _normalize_wavespeed_grok_video_options(self, options=None):
        result = dict(DEFAULT_WAVESPEED_GROK_VIDEO_OPTIONS)
        options = options or {}

        if "duration" in options:
            value = int(options["duration"])
            if value not in VALID_WAVESPEED_GROK_VIDEO_DURATIONS:
                raise ValueError("Флаг -d / --duration должен быть 6 или 10")
            result["duration"] = value

        if "aspect_ratio" in options:
            value = str(options["aspect_ratio"]).strip()
            if value and value not in VALID_WAVESPEED_GROK_VIDEO_ASPECTS:
                raise ValueError("Флаг -ar / --aspect-ratio должен быть одним из: 16:9, 1:1, 9:16")
            result["aspect_ratio"] = value

        if "resolution" in options:
            value = str(options["resolution"]).strip().lower()
            if value not in VALID_WAVESPEED_GROK_VIDEO_RESOLUTIONS:
                raise ValueError("Флаг -r / --resolution должен быть 480p или 720p")
            result["resolution"] = value

        if "timeout" in options:
            value = int(options["timeout"])
            if not 60 <= value <= 1800:
                raise ValueError("Флаг -t / --timeout должен быть от 60 до 1800")
            result["timeout"] = value

        return result

    def _parse_provider_args(self, provider: str, raw_args: str):
        specs = []

        if provider in {"google", "grok", "grok_video", "wavespeed", "gpt_image"}:
            specs.append({"aliases": ["-m", "--model"], "dest": "model", "kind": "str"})

        if provider == "grok_video":
            specs.extend([
                {"aliases": ["-d", "--duration"], "dest": "duration", "kind": "int"},
                {"aliases": ["-ar", "--aspect-ratio"], "dest": "aspect_ratio", "kind": "str"},
                {"aliases": ["-r", "--resolution"], "dest": "resolution", "kind": "str"},
                {"aliases": ["-t", "--timeout"], "dest": "timeout", "kind": "int"},
            ])

        if provider == "wavespeed_grok_video":
            specs.extend([
                {"aliases": ["-d", "--duration"], "dest": "duration", "kind": "int"},
                {"aliases": ["-ar", "--aspect-ratio"], "dest": "aspect_ratio", "kind": "str"},
                {"aliases": ["-r", "--resolution"], "dest": "resolution", "kind": "str"},
                {"aliases": ["-t", "--timeout"], "dest": "timeout", "kind": "int"},
            ])

        if provider == "gpt_image":
            specs.extend([
                {"aliases": ["-s", "--size"], "dest": "size", "kind": "str"},
                {"aliases": ["-q", "--quality"], "dest": "quality", "kind": "str"},
                {"aliases": ["-bg", "--background"], "dest": "background", "kind": "str"},
                {"aliases": ["-t", "--timeout"], "dest": "timeout", "kind": "int"},
            ])

        if provider == "wainsfw":
            specs.extend([
                {"aliases": ["-n", "--negative"], "dest": "negative_prompt", "kind": "str"},
            ])

        if provider == "wavespeed_grok":
            specs.extend([
                {"aliases": ["-ar", "--aspect-ratio"], "dest": "aspect_ratio", "kind": "str"},
                {"aliases": ["-f", "--format", "-of", "--output-format"], "dest": "output_format", "kind": "str"},
                {"aliases": ["-t", "--timeout"], "dest": "timeout", "kind": "int"},
            ])

        parsed, prompt = self._parse_flags(raw_args, specs)
        model_override = parsed.pop("model", None)

        if provider == "grok_video":
            request_options = self._normalize_grok_video_options(parsed)
        elif provider == "wavespeed_grok_video":
            request_options = self._normalize_wavespeed_grok_video_options(parsed)
        elif provider == "gpt_image":
            request_options = self._normalize_gpt_image_options(parsed)
        elif provider == "wainsfw":
            negative_prompt = str(parsed.get("negative_prompt") or "").strip()
            request_options = {"negative_prompt": negative_prompt} if negative_prompt else {}
        elif provider == "wavespeed_grok":
            request_options = self._normalize_wavespeed_grok_options(parsed)
        else:
            request_options = {}

        return prompt, model_override, request_options

    def _get_grok_video_options(self, request_options=None):
        try:
            return self._normalize_grok_video_options(request_options or {})
        except Exception:
            logger.exception("failed to normalize grok video options, using defaults")
            return dict(DEFAULT_GROK_VIDEO_OPTIONS)

    def _get_gpt_image_options(self, request_options=None):
        try:
            return self._normalize_gpt_image_options(request_options or {})
        except Exception:
            logger.exception("failed to normalize gpt image options, using defaults")
            return dict(DEFAULT_GPT_IMAGE_OPTIONS)

    def _get_wavespeed_grok_options(self, request_options=None):
        try:
            return self._normalize_wavespeed_grok_options(request_options or {})
        except Exception:
            logger.exception("failed to normalize wavespeed grok options, using safe defaults")
            return dict(DEFAULT_WAVESPEED_GROK_OPTIONS)

    def _get_wavespeed_grok_video_options(self, request_options=None, mode="text_to_video"):
        base = dict(DEFAULT_WAVESPEED_GROK_VIDEO_OPTIONS)
        if mode == "video_edit":
            base["resolution"] = "480p"

        merged = dict(base)
        if isinstance(request_options, dict):
            merged.update(request_options)

        try:
            normalized = self._normalize_wavespeed_grok_video_options(merged)
        except Exception:
            logger.exception("failed to normalize wavespeed grok video options, using safe defaults")
            normalized = dict(base)

        if mode == "image_to_video":
            normalized["aspect_ratio"] = ""
        elif mode == "video_edit":
            normalized["aspect_ratio"] = ""

        return normalized

    def _get_grok_video_meta_str(self, session_state: dict, mode: str) -> str:
        if mode == "video_edit":
            return "\n<blockquote>🎞 <b>Режим:</b> редактирование видео</blockquote>"

        options = self._get_grok_video_options(session_state.get("request_options"))
        seconds = self._format_duration(options["duration"])
        return (
            f"\n<blockquote>📐 <b>{utils.escape_html(options['aspect_ratio'])}</b> | "
            f"🎚 <b>{utils.escape_html(options['resolution'])}</b> | "
            f"⏱ <b>{seconds}</b></blockquote>"
        )

    def _render_grok_video_status_text(self, prompt_block: str, model_str: str, attach_str: str, session_state: dict, mode: str, progress=None) -> str:
        mode_map = {
            "text_to_video": "Генерация видео...",
            "image_to_video": "Генерация видео из фото...",
            "video_edit": "Редактирование видео...",
        }
        base = mode_map.get(mode, "Генерация видео...")
        if progress is not None:
            base = f"{base} {progress}%"

        text = f"<blockquote>🎬 <b>{base}</b></blockquote>{model_str}{attach_str}{self._get_grok_video_meta_str(session_state, mode)}\n{prompt_block}"
        return self._normalize_visual_text(text)

    def _get_wavespeed_grok_video_meta_str(self, session_state: dict, mode: str) -> str:
        options = self._get_wavespeed_grok_video_options(session_state.get("request_options"), mode)

        if mode == "video_edit":
            return f'\n<blockquote>🎚 <b>{utils.escape_html(options["resolution"])}</b></blockquote>'

        if mode == "image_to_video":
            return (
                f'\n<blockquote>🎚 <b>{utils.escape_html(options["resolution"])}</b> | '
                f'⏱ <b>{self._format_duration(options["duration"])}</b></blockquote>'
            )

        return (
            f'\n<blockquote>📐 <b>{utils.escape_html(options["aspect_ratio"])}</b> | '
            f'🎚 <b>{utils.escape_html(options["resolution"])}</b> | '
            f'⏱ <b>{self._format_duration(options["duration"])}</b></blockquote>'
        )

    def _render_wavespeed_grok_video_status_text(self, prompt_block: str, model_str: str, attach_str: str, session_state: dict, mode: str) -> str:
        mode_map = {
            "text_to_video": "Генерация видео...",
            "image_to_video": "Генерация видео из фото...",
            "video_edit": "Редактирование видео...",
        }
        text = (
            f"<blockquote>🎬 <b>{mode_map.get(mode, 'Генерация видео...')}</b></blockquote>"
            f"{model_str}{attach_str}{self._get_wavespeed_grok_video_meta_str(session_state, mode)}\n{prompt_block}"
        )
        return self._normalize_visual_text(text)

    def _get_loading_markup(self):
        return [[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]]

    async def _try_create_inline_target(self, message: Message, text: str, reply_markup=None, retries: int = 3, delay: float = 0.35):
        if not self.config["inline_mode"] or not message:
            return None

        reply_markup = reply_markup if reply_markup is not None else self._get_loading_markup()

        for attempt in range(1, retries + 1):
            try:
                target = await self.inline.form(
                    text=text,
                    message=message,
                    reply_markup=reply_markup,
                )
                if target:
                    return target

                logger.warning("inline.form returned empty target (attempt %s/%s)", attempt, retries)
            except Exception:
                logger.exception("inline.form failed (attempt %s/%s)", attempt, retries)

            if attempt < retries:
                await asyncio.sleep(delay)

        return None

    async def _create_status_target(self, message: Message, text: str):
        inline_target = await self._try_create_inline_target(
            message,
            text,
            reply_markup=self._get_loading_markup(),
        )
        if inline_target:
            return inline_target, True

        try:
            target = await utils.answer(message, text)
            return target, False
        except Exception:
            logger.exception("failed to create regular status target")
            raise

    async def _try_promote_session_to_inline(self, current_target, session: dict, text: str, reply_markup=None):
        origin_message = session.get("origin_message")
        if not origin_message or not self.config["inline_mode"]:
            return None

        new_target = await self._try_create_inline_target(
            origin_message,
            text,
            reply_markup=reply_markup if reply_markup is not None else self._get_loading_markup(),
        )
        if not new_target:
            return None

        if current_target and current_target is not new_target and hasattr(current_target, "delete"):
            try:
                await current_target.delete()
            except Exception:
                logger.exception("failed to delete old non-inline target after inline promotion")

        return new_target

    async def _send_error_to_origin(self, s: dict, text: str):
        chat_id = s.get("origin_chat_id")
        if not chat_id:
            logger.warning("fallback error send skipped: origin_chat_id missing")
            return False

        try:
            await self._client.send_message(
                chat_id,
                text,
                reply_to=s.get("origin_reply_to"),
            )
            return True
        except Exception:
            logger.exception("failed to send fallback error message")
            return False

    async def _send_result_to_origin(self, s: dict, media_bytes, text_resp: str, media_type="image", duration=None):
        chat_id = s.get("origin_chat_id")
        if not chat_id:
            logger.warning("fallback result send skipped: origin_chat_id missing")
            return False

        try:
            await self._send_direct_result(
                None,
                s,
                media_bytes,
                text_resp,
                media_type=media_type,
                duration=duration,
                chat_id=chat_id,
                reply_to_msg_id=s.get("origin_reply_to"),
                delete_target=False,
            )
            return True
        except Exception:
            logger.exception("failed to send fallback result to origin")
            return False

    async def _aclose_if_possible(self, obj):
        if not obj:
            return

        for method_name in ("aclose", "close"):
            method = getattr(obj, method_name, None)
            if not callable(method):
                continue

            try:
                result = method()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                self._log_suppressed(
                    f"failed to close object via {method_name} ({type(obj).__name__})",
                    logging.DEBUG,
                )

            break

    async def _stop_session_task(self, sid):
        session = self.sessions.get(sid)
        if not session:
            return

        task = session.get("task")
        current_task = asyncio.current_task()

        if task and not task.done():
            session["cancel"] = True

            if task is current_task:
                session["task"] = None
                return

            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        session["task"] = None

    def _get_connector(self):
        proxy = self.config["proxy"]
        if proxy:
            try:
                return ProxyConnector.from_url(proxy)
            except Exception:
                logger.exception("proxy connector init failed")
        return None

    def _hist_real_index(self, history, display_index: int) -> int:
        if not history:
            return 0
        display_index = max(0, min(display_index, len(history) - 1))
        return len(history) - 1 - display_index

    def _hist_display_index(self, history, real_index: int) -> int:
        if not history:
            return 0
        real_index = max(0, min(real_index, len(history) - 1))
        return len(history) - 1 - real_index

    def _provider_display_name(self, provider: str) -> str:
        return {
            "wavespeed": "Wavespeed",
            "wavespeed_grok": "Grok Imagine (Wavespeed)",
            "wavespeed_grok_video": "Grok Imagine Video (Wavespeed)",
            "wainsfw": "WAI NSFW",
            "grok": "Grok",
            "grok_video": "Grok Video",
            "google": "Google",
            "gpt_image": "GPT Image",
        }.get(provider, provider)

    def _prompt_has_non_english_letters(self, prompt: str) -> bool:
        for ch in prompt or "":
            if ch.isalpha() and not ch.isascii():
                return True
        return False

    def _build_lang_prompt_preview(self, prompt: str) -> str:
        prompt = utils.escape_html((prompt or "").strip())
        if not prompt:
            return ""
        return f"\n<blockquote expandable>{prompt}</blockquote>"

    def _render_lang_warning(self, provider: str, prompt: str) -> str:
        return self._get_str(
            "lang_warn",
            self._provider_display_name(provider),
            self._build_lang_prompt_preview(prompt),
        )

    def _get_model_str(self, model):
        return f'\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {utils.escape_html(str(model))}</blockquote>'

    def _get_attach_str(self, num):
        if not num:
            return ""
        return f'\n<blockquote><a href="tg://emoji?id=5877495434124988415">📎</a> <b>Прикреплено файлов:</b> {num}</blockquote>'

    def _get_prompt_label(self, enhanced_prompt=None):
        return "Обычный промпт" if (enhanced_prompt or "").strip() else "Промпт"

    def _is_empty_image(self, url):
        return "empty.png" in str(url)

    def _has_prompt(self, original_prompt, enhanced_prompt=None, negative_prompt=None):
        original_prompt = (original_prompt or "").strip()
        enhanced_prompt = (enhanced_prompt or "").strip()
        negative_prompt = (negative_prompt or "").strip()
        return bool((original_prompt and original_prompt != "...") or enhanced_prompt or negative_prompt)

    def _is_prompt_long(self, original_prompt, enhanced_prompt=None, negative_prompt=None, short_limit=200):
        original_prompt = (original_prompt or "").strip()
        enhanced_prompt = (enhanced_prompt or "").strip()
        negative_prompt = (negative_prompt or "").strip()
        return (
            len(original_prompt) > short_limit
            or (enhanced_prompt and len(enhanced_prompt) > short_limit)
            or (negative_prompt and len(negative_prompt) > short_limit)
        )

    def _get_message_limit(self, has_media=False):
        return 1000 if has_media else 3900

    def _get_status_prompt_block(self, original_prompt, enhanced_prompt=None, negative_prompt=None, short_limit=200):
        return self._build_prompt_block(
            original_prompt,
            enhanced_prompt,
            negative_prompt=negative_prompt,
            show_full=False,
            short_limit=short_limit,
        )

    def _get_public_error_text(self, error_text: str) -> str:
        error_text = (error_text or "Неизвестная ошибка.").strip()
        if error_text.lower() in {"error(check logs)", "error (check logs)", "error(checklogs)"}:
            error_text = "Неизвестная ошибка."

        error_text = utils.escape_html(error_text)
        if len(error_text) > 1500:
            error_text = error_text[:1500] + "..."
        return error_text

    def _render_error_message(self, raw_error_text: str, provider: str = None, origin_message: Message = None) -> str:
        raw_error_text = (raw_error_text or "Неизвестная ошибка.").strip()
        lowered_error = raw_error_text.lower()

        if self._contains_any(lowered_error, ["отменено пользователем", "cancelled by user", "canceled by user"]):
            return self._get_str("error", self._get_public_error_text(raw_error_text))

        if provider == "wainsfw":
            if self._get_secret_values("hf_token"):
                return self._get_str("wainsfw_error_with_key")
            hint = self._cfg_hint(origin_message, "hf_token", ["iwa"]) if origin_message else ""
            return self._get_str("wainsfw_error_no_key", hint)

        if provider in {"grok", "grok_video"}:
            if self._contains_any(
                lowered_error,
                [
                    "used all available credits",
                    "monthly spending limit",
                    "reached its monthly spending limit",
                    "insufficient credits",
                ],
            ):
                text = self._get_str("xai_limit")
                if provider == "grok":
                    return self._append_wavespeed_grok_alt_hint(text, origin_message)
                return self._append_wavespeed_grok_video_alt_hint(text, origin_message)

            if self._contains_any(
                lowered_error,
                [
                    "invalid api key",
                    "incorrect api key",
                    "invalid_authentication",
                    "invalid authentication",
                    "unauthorized",
                    "authentication",
                ],
            ):
                text = self._get_str("xai_invalid")
                if provider == "grok":
                    return self._append_wavespeed_grok_alt_hint(text, origin_message)
                return self._append_wavespeed_grok_video_alt_hint(text, origin_message)

        if provider in {"wavespeed", "wavespeed_grok", "wavespeed_grok_video"}:
            if provider == "wavespeed":
                cfg_hint = self._get_wavespeed_cfg_hint(origin_message, ["iw"])
            elif provider == "wavespeed_grok":
                cfg_hint = self._get_wavespeed_cfg_hint(origin_message, ["iwgrok", "iwg"])
            else:
                cfg_hint = self._get_wavespeed_cfg_hint(origin_message, ["iwgrokv", "iwgv"])

            if self._contains_any(
                lowered_error,
                [
                    "insufficient credits",
                    "please top up",
                    "http 429",
                    "too many requests",
                    "rate limit",
                    "trial credit",
                ],
            ):
                return self._get_str("wavespeed_limit", cfg_hint)

            if self._contains_any(
                lowered_error,
                [
                    "invalid api key",
                    "invalid access key",
                    "unauthorized",
                    "unauthenticated",
                    "forbidden",
                    "http 401",
                ],
            ):
                return self._get_str("wavespeed_invalid", cfg_hint)

        if provider == "google":
            if self._contains_any(
                lowered_error,
                [
                    "api key not found",
                    "please pass a valid api key",
                    "api_key_invalid",
                ],
            ):
                return self._get_str("google_invalid")

            if self._contains_any(
                lowered_error,
                [
                    "resource_exhausted",
                    "quota exceeded",
                    "rate limit",
                    "http 429",
                    "exhausted",
                ],
            ):
                return self._get_str("google_limit")

        if provider == "gpt_image":
            if self._contains_any(
                lowered_error,
                [
                    "organization verification",
                    "complete the api organization verification",
                    "must complete the api organization verification",
                ],
            ):
                return self._get_str("openai_verification")

            if self._contains_any(
                lowered_error,
                [
                    "incorrect api key provided",
                    "invalid_api_key",
                    "invalid authentication",
                    "api key provided is invalid",
                    "authenticationerror",
                    "revoked",
                    "expired",
                    "http 401",
                ],
            ):
                return self._get_str("openai_invalid")

            if self._contains_any(
                lowered_error,
                [
                    "insufficient_quota",
                    "billing_hard_limit_reached",
                    "exceeded your current quota",
                    "rate limit reached",
                    "rate_limit_exceeded",
                    "http 429",
                ],
            ):
                return self._get_str("openai_limit")

        censor_keys = [
            "block reason",
            "prohibited",
            "violated",
            "unable to show",
            "safety",
            "rejected by content moderation",
            "moderation",
        ]
        limit_keys = [
            "429",
            "resource_exhausted",
            "quota exceeded",
            "exhausted",
            "insufficient_quota",
            "billing_hard_limit_reached",
            "used all available credits",
            "monthly spending limit",
            "insufficient credits",
            "rate limit reached",
        ]

        if any(k in lowered_error for k in limit_keys):
            key = "error_429"
        elif any(k in lowered_error for k in censor_keys):
            key = "error_censored"
        else:
            key = "error"

        rendered = self._get_str(key, self._get_public_error_text(raw_error_text))
        if provider == "grok" and key == "error_429":
            rendered = self._append_wavespeed_grok_alt_hint(rendered, origin_message)
        elif provider == "grok_video" and key == "error_429":
            rendered = self._append_wavespeed_grok_video_alt_hint(rendered, origin_message)

        return rendered

    def _get_str(self, key, *args):
        text = self.strings(key).format(*args)

        if not self.config["custom_emojis"]:
            text = re.sub(r'<a href="tg://emoji\?id=\d+">(.+?)</a>', r"\1", text)

        if not self.config["use_quote"]:
            text = text.replace("<blockquote>", "").replace("</blockquote>", "").replace("<blockquote expandable>", "")

        return text.strip()

    def _resize_image(self, img_bytes):
        setting = self.config["quality"]
        if setting == "Original":
            return img_bytes

        presets = {
            "Low": (800, 75),
            "Medium": (1024, 85),
            "High": (1280, 90),
        }
        size, qual = presets.get(setting, (800, 75))

        try:
            img = Image.open(io.BytesIO(img_bytes))
            img.thumbnail((size, size))
            out = io.BytesIO()
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(out, format="JPEG", quality=qual)
            return out.getvalue()
        except Exception:
            self._log_suppressed("failed to resize image, using original bytes", logging.DEBUG)
            return img_bytes

    def _smart_split(self, text, limit=800):
        text = (text or "").strip()
        if not text:
            return []

        chunks = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break

            cut = text.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit

            chunk = text[:cut].strip()
            if chunk:
                chunks.append(chunk)

            text = text[cut:].strip()

        return chunks

    def _truncate_text(self, text, limit):
        text = (text or "").strip()
        if not text:
            return "..."
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    def _extract_google_text(self, response):
        try:
            text = getattr(response, "text", None)
            if text:
                return str(text).strip()
        except Exception:
            self._log_suppressed("failed to extract response.text from Google response", logging.DEBUG)

        chunks = []
        try:
            candidates = getattr(response, "candidates", None) or []
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None) or []
                for part in parts:
                    part_text = getattr(part, "text", None)
                    if part_text:
                        chunks.append(str(part_text))
        except Exception:
            self._log_suppressed("failed to extract candidates.parts text from Google response", logging.DEBUG)

        return "\n".join(chunks).strip()

    def _build_prompt_file_text(self, original_prompt, enhanced_prompt=None, negative_prompt=None):
        original_prompt = (original_prompt or "").strip()
        enhanced_prompt = (enhanced_prompt or "").strip()
        negative_prompt = (negative_prompt or "").strip()

        parts = []

        if original_prompt and original_prompt != "...":
            parts.append(f"{self._get_prompt_label(enhanced_prompt)}:\n{original_prompt}")

        if enhanced_prompt:
            parts.append(f"Улучшенный промпт:\n{enhanced_prompt}")

        if negative_prompt:
            parts.append(f"Негативный промпт:\n{negative_prompt}")

        if not parts:
            parts.append("Промпт отсутствует.")

        return "\n\n".join(parts)

    def _build_prompt_block(self, original_prompt, enhanced_prompt=None, negative_prompt=None, show_full=False, short_limit=200):
        original_prompt = (original_prompt or "").strip()
        enhanced_prompt = (enhanced_prompt or "").strip()
        negative_prompt = (negative_prompt or "").strip()

        if not self._has_prompt(original_prompt, enhanced_prompt, negative_prompt):
            return ""

        open_tag = "<blockquote>" if show_full else "<blockquote expandable>"

        def _fmt(text):
            text = (text or "").strip()
            if not text:
                return ""
            value = text if show_full else self._truncate_text(text, short_limit)
            return utils.escape_html(value)

        parts = []

        if original_prompt and original_prompt != "...":
            parts.append(
                f'{open_tag}📝 <b>{self._get_prompt_label(enhanced_prompt)}:</b> <i>{_fmt(original_prompt)}</i></blockquote>'
            )

        if enhanced_prompt:
            parts.append(f'{open_tag}✨ <b>Улучшенный промпт:</b> <i>{_fmt(enhanced_prompt)}</i></blockquote>')

        if negative_prompt:
            parts.append(f'{open_tag}🚫 <b>Негативный промпт:</b> <i>{_fmt(negative_prompt)}</i></blockquote>')

        return "\n".join(parts)

    def _can_show_session_prompt_inline(self, s):
        negative_prompt = self._get_negative_prompt(s.get("request_options"))
        if not self._has_prompt(s.get("display_prompt"), s.get("enhanced_prompt"), negative_prompt):
            return False

        idx = s.get("index", -1)
        data = s["images"][idx] if 0 <= idx < len(s.get("images", [])) else {}

        media_url = data.get("url")
        media_type = data.get("media_type", "image")
        ai_text = data.get("text", "")
        model = data.get("model", s.get("model", "Unknown"))
        duration = data.get("duration")
        has_media = bool(media_url) and not self._is_empty_image(media_url)

        text_page = s.get("text_page", 0)
        text_chunks = self._smart_split(ai_text, 800)
        total_text_pages = len(text_chunks)

        if text_page >= total_text_pages:
            text_page = max(0, total_text_pages - 1)

        current_text = text_chunks[text_page] if text_chunks else ""
        is_edit = bool(s.get("input_imgs") or s.get("input_video"))

        prompt_block = self._build_prompt_block(
            s.get("display_prompt"),
            s.get("enhanced_prompt"),
            negative_prompt=negative_prompt,
            show_full=True,
            short_limit=200,
        )
        if not prompt_block:
            return False

        model_str = self._get_model_str(model)
        attach_str = self._get_attach_str(len(s.get("input_imgs", [])) + (1 if s.get("input_video") else 0))

        if media_type == "video":
            if ai_text:
                key = "video_success_text"
                args = [prompt_block, model_str, attach_str, self._format_duration(duration), text_page + 1, max(1, total_text_pages), utils.escape_html(current_text.strip())]
            else:
                key = "video_success"
                args = [prompt_block, model_str, attach_str, self._format_duration(duration)]
        else:
            if has_media:
                key = (
                    "edit_success_text" if is_edit and ai_text
                    else "edit_success" if is_edit
                    else "success_with_text" if ai_text
                    else "success"
                )
            else:
                key = "only_text_response" if ai_text else "error_no_data"

            args = [prompt_block, model_str, attach_str]
            if ai_text:
                args.extend([text_page + 1, max(1, total_text_pages), utils.escape_html(current_text.strip())])

        rendered = self._get_str(key, *args)
        return len(rendered) <= self._get_message_limit(has_media)

    def _can_show_history_prompt_inline(self, item, display_index, text_page=0):
        negative_prompt = self._get_negative_prompt(item.get("request_options"))
        if not self._has_prompt(item.get("prompt", ""), item.get("enhanced_prompt"), negative_prompt):
            return False

        history = self.db.get("ImageGen", "history", [])
        media_url = self.url_cache.get(item["id"]) or item.get("url")
        has_media = bool(item.get("bytes")) or (bool(media_url) and not self._is_empty_image(media_url))
        media_type = item.get("media_type", "image")
        duration = item.get("duration")
        ai_text = item.get("text_resp", "")
        model = item.get("model", "Неизвестно")

        prompt_block = self._build_prompt_block(
            item.get("prompt", ""),
            item.get("enhanced_prompt"),
            negative_prompt=negative_prompt,
            show_full=True,
            short_limit=200,
        )
        if not prompt_block:
            return False

        text_chunks = self._smart_split(ai_text, 800)
        total_text = len(text_chunks)

        if text_page >= total_text:
            text_page = max(0, total_text - 1)

        curr_text = text_chunks[text_page] if text_chunks else ""
        model_str = self._get_model_str(model)

        if media_type == "video":
            if ai_text:
                key = "history_video_item_text"
                args = [
                    display_index + 1,
                    len(history),
                    model_str,
                    prompt_block,
                    self._format_duration(duration),
                    text_page + 1,
                    max(1, total_text),
                    utils.escape_html(curr_text.strip()),
                ]
            else:
                key = "history_video_item"
                args = [display_index + 1, len(history), model_str, prompt_block, self._format_duration(duration)]
        else:
            if ai_text:
                key = "history_item_text" if has_media else "history_text_only"
                args = [
                    display_index + 1,
                    len(history),
                    model_str,
                    prompt_block,
                    text_page + 1,
                    max(1, total_text),
                    utils.escape_html(curr_text.strip()),
                ]
            else:
                key = "history_item"
                args = [display_index + 1, len(history), model_str, prompt_block]

        rendered = self._get_str(key, *args)
        return len(rendered) <= self._get_message_limit(has_media)

    async def _safe_edit(self, target, text, **kwargs):
        if not target or not hasattr(target, "edit"):
            logger.warning("_safe_edit skipped: target has no edit()")
            return False

        attempts = []

        def add_attempt(payload: dict):
            if payload not in attempts:
                attempts.append(payload)

        original = dict(kwargs)
        add_attempt(original)

        if "reply_markup" in original:
            no_markup = dict(original)
            no_markup.pop("reply_markup", None)
            add_attempt(no_markup)

            buttons_markup = dict(no_markup)
            buttons_markup["buttons"] = original["reply_markup"]
            add_attempt(buttons_markup)

        if not attempts:
            attempts.append({})

        for attempt in attempts:
            try:
                await target.edit(text, **attempt)
                return True
            except Exception:
                logger.debug("_safe_edit failed with kwargs=%s", tuple(attempt.keys()), exc_info=True)

        return False

    async def _safe_edit_media(self, target, text, reply_markup=None, photo=None, video=None):
        if not target or not hasattr(target, "edit"):
            logger.warning("_safe_edit_media skipped: target has no edit()")
            return False

        attempts = []

        def add_attempt(payload: dict):
            if payload not in attempts:
                attempts.append(payload)

        media_key = "video" if video is not None else "photo" if photo is not None else None
        media_value = video if video is not None else photo

        if media_key is not None:
            base = {media_key: media_value}
            if reply_markup is not None:
                with_reply_markup = dict(base)
                with_reply_markup["reply_markup"] = reply_markup
                add_attempt(with_reply_markup)

                with_buttons = dict(base)
                with_buttons["buttons"] = reply_markup
                add_attempt(with_buttons)

            add_attempt(base)

        if reply_markup is not None:
            add_attempt({"reply_markup": reply_markup})
            add_attempt({"buttons": reply_markup})

        add_attempt({})

        for attempt in attempts:
            try:
                await target.edit(text, **attempt)

                if media_key is not None and media_key not in attempt:
                    logger.warning("media edit fallback succeeded without media")
                    return False

                return True
            except Exception:
                logger.debug("_safe_edit_media failed with kwargs=%s", tuple(attempt.keys()), exc_info=True)

        return False

    async def _up_catbox(self, session, file_bytes, filename, content_type):
        data = aiohttp.FormData()
        data.add_field("reqtype", "fileupload")
        data.add_field("fileToUpload", file_bytes, filename=filename, content_type=content_type)
        try:
            async with session.post("https://catbox.moe/user/api.php", data=data, timeout=60) as resp:
                if resp.status == 200:
                    return await resp.text()
                logger.warning("catbox upload failed with HTTP %s", resp.status)
        except Exception:
            self._log_suppressed("catbox upload failed")
        return None

    async def _up_0x0(self, session, file_bytes, filename, content_type):
        data = aiohttp.FormData()
        data.add_field("file", file_bytes, filename=filename, content_type=content_type)
        try:
            async with session.post("https://0x0.st", data=data, timeout=60) as resp:
                if resp.status == 200:
                    return await resp.text()
                logger.warning("0x0 upload failed with HTTP %s", resp.status)
        except Exception:
            self._log_suppressed("0x0 upload failed")
        return None

    async def _up_x0(self, session, file_bytes, filename, content_type):
        data = aiohttp.FormData()
        data.add_field("file", file_bytes, filename=filename, content_type=content_type)
        try:
            async with session.post("https://x0.at", data=data, timeout=60) as resp:
                if resp.status == 200:
                    return await resp.text()
                logger.warning("x0.at upload failed with HTTP %s", resp.status)
        except Exception:
            self._log_suppressed("x0.at upload failed")
        return None

    async def _up_tmpfiles(self, session, file_bytes, filename, content_type):
        data = aiohttp.FormData()
        data.add_field("file", file_bytes, filename=filename, content_type=content_type)
        try:
            async with session.post("https://tmpfiles.org/api/v1/upload", data=data, timeout=60) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    url = res["data"]["url"]
                    return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                logger.warning("tmpfiles upload failed with HTTP %s", resp.status)
        except Exception:
            self._log_suppressed("tmpfiles upload failed")
        return None

    async def _upload_temp_file(self, file_bytes, filename, content_type):
        headers = {"User-Agent": "Mozilla/5.0"}
        tasks = []
        valid_url = None

        async with aiohttp.ClientSession(headers=headers, connector=self._get_connector()) as session:
            try:
                tasks = [
                    asyncio.create_task(self._up_x0(session, file_bytes, filename, content_type)),
                    asyncio.create_task(self._up_tmpfiles(session, file_bytes, filename, content_type)),
                    asyncio.create_task(self._up_catbox(session, file_bytes, filename, content_type)),
                    asyncio.create_task(self._up_0x0(session, file_bytes, filename, content_type)),
                ]

                for task in asyncio.as_completed(tasks):
                    try:
                        res = await task
                        if res and str(res).startswith("http"):
                            valid_url = str(res).strip()
                            break
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.exception("upload worker failed")
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

        if not valid_url:
            logger.warning("failed to upload file to all temporary hosts")

        return valid_url

    async def _upload_image(self, img_bytes):
        return await self._upload_temp_file(img_bytes, "image.jpg", "image/jpeg")

    async def _upload_video(self, video_bytes):
        return await self._upload_temp_file(video_bytes, "video.mp4", "video/mp4")

    async def _call_wainsfw(self, session_state, prompt: str):
        base_url = "https://menyu-wainsfw.hf.space/gradio_api/call/infer"
        tokens = self._get_secret_values("hf_token") or [""]
        negative_prompt = self._get_negative_prompt(session_state.get("request_options")) or "lowres, bad quality, worst quality"
        last_error = "Превышено время ожидания WaiNSFW."

        for token in tokens:
            if session_state.get("cancel"):
                return None, "Отменено пользователем."

            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            try:
                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    payload = {
                        "data": [
                            prompt,
                            negative_prompt,
                            True,
                            0,
                            832,
                            1216,
                            7.0,
                            28,
                            True,
                        ]
                    }

                    async with session.post(
                        base_url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as r:
                        data, raw_text = await self._read_json_or_text(r)
                        if r.status >= 400:
                            last_error = self._extract_error_message(data, raw_text[:500], r.status)
                            continue

                        event_id = (data or {}).get("event_id") if isinstance(data, dict) else None
                        if not event_id:
                            last_error = f"Ошибка WaiNSFW: не удалось получить event_id. {(raw_text or data)!s}"
                            continue

                    async with session.get(
                        f"{base_url}/{event_id}",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=None),
                    ) as r:
                        if r.status >= 400:
                            body = await r.text()
                            last_error = self._extract_error_message(None, body[:500], r.status)
                            continue

                        event = None
                        terminal_event = False

                        async for line in r.content:
                            if session_state.get("cancel"):
                                return None, "Отменено пользователем."

                            line = line.decode("utf-8", errors="ignore").strip()
                            if line.startswith("event:"):
                                event = line[6:].strip()
                            elif line.startswith("data:") and event == "complete":
                                terminal_event = True
                                payload_raw = line[5:].strip()

                                try:
                                    result = json.loads(payload_raw)
                                except Exception:
                                    result = None

                                if not result:
                                    last_error = "WaiNSFW вернул пустой результат."
                                    break

                                img_url = None
                                try:
                                    img_url = result[0].get("url")
                                except Exception:
                                    img_url = None

                                if not img_url:
                                    last_error = f"WaiNSFW: URL не найден в ответе: {result}"
                                    break

                                async with session.get(img_url, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as img_resp:
                                    if img_resp.status == 200:
                                        img_bytes = await img_resp.read()
                                        return img_bytes, ""

                                    body = await img_resp.text()
                                    last_error = self._extract_error_message(None, body[:500], img_resp.status)
                                    break

                            elif line.startswith("data:") and event == "error":
                                terminal_event = True
                                payload_raw = line[5:].strip()

                                try:
                                    err_payload = json.loads(payload_raw)
                                except Exception:
                                    err_payload = None

                                last_error = self._extract_error_message(
                                    err_payload,
                                    "Ошибка WaiNSFW: нет квоты или Space недоступен.",
                                )
                                break

                        if terminal_event:
                            continue

                        last_error = "Превышено время ожидания WaiNSFW."
            except Exception as e:
                if session_state.get("cancel"):
                    return None, "Отменено пользователем."
                last_error = self._stringify_exception(e)

        return None, last_error

    async def _call_wavespeed(self, session_state, prompt: str, input_imgs=None):
        api_keys = self._get_secret_values("wavespeed_api_key")
        if not api_keys:
            return None, "Не установлен API-ключ Wavespeed!"

        is_edit = bool(input_imgs)
        model = session_state.get("model") or (self.config["wavespeed_model_i2i"] if is_edit else self.config["wavespeed_model_t2i"])
        last_error = "Неизвестная ошибка Wavespeed."

        payload = {
            "prompt": prompt,
            "size": self.config["wavespeed_size"],
            "seed": -1,
            "enable_safety_checker": False,
        }

        if is_edit:
            image_urls = []
            for img_bytes in input_imgs:
                url = await self._upload_image(img_bytes)
                if url:
                    image_urls.append(url)

            if not image_urls:
                return None, "Не удалось загрузить исходное изображение на временный хостинг для Wavespeed."

            payload["images"] = image_urls

        endpoint = f"https://api.wavespeed.ai/api/v3/{model}"

        for api_key in api_keys:
            if session_state.get("cancel"):
                return None, "Отменено пользователем."

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            try:
                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    async with session.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=90),
                    ) as resp:
                        data, raw_text = await self._read_json_or_text(resp)

                        if resp.status != 200:
                            last_error = self._extract_error_message(data, raw_text[:500], resp.status)
                            continue

                        if not isinstance(data, dict) or data.get("code") != 200:
                            last_error = self._extract_error_message(data, raw_text[:500], resp.status)
                            continue

                        task_id = data.get("data", {}).get("id")
                        if not task_id:
                            last_error = f"Не получен ID задачи: {data}"
                            continue

                    poll_url = f"https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"
                    failed = False

                    for _ in range(90):
                        if session_state.get("cancel"):
                            return None, "Отменено пользователем."

                        await asyncio.sleep(2)

                        async with session.get(poll_url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as poll_resp:
                            poll_data, raw_poll_text = await self._read_json_or_text(poll_resp)

                            if poll_resp.status != 200:
                                last_error = self._extract_error_message(poll_data, raw_poll_text[:500], poll_resp.status)
                                failed = True
                                break

                            status = (poll_data or {}).get("data", {}).get("status")

                            if status == "completed":
                                outputs = (poll_data or {}).get("data", {}).get("outputs", [])
                                if not outputs:
                                    last_error = "Задача выполнена, но изображения не найдены."
                                    failed = True
                                    break

                                img_url = outputs[0]
                                async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=120)) as img_resp:
                                    if img_resp.status == 200:
                                        img_bytes = await img_resp.read()
                                        return img_bytes, ""

                                    body = await img_resp.text()
                                    last_error = self._extract_error_message(None, body[:500], img_resp.status)
                                    failed = True
                                    break

                            if status in ["failed", "error", "canceled"]:
                                last_error = f"Ошибка генерации Wavespeed: {(poll_data or {}).get('data', {}).get('error', status)}"
                                failed = True
                                break

                    if failed:
                        continue

                    last_error = "Превышено время ожидания Wavespeed (timeout)."
            except Exception as e:
                if session_state.get("cancel"):
                    return None, "Отменено пользователем."
                last_error = self._stringify_exception(e)

        return None, last_error

    async def _call_wavespeed_grok(self, session_state, prompt: str, input_imgs=None):
        api_keys = self._get_secret_values("wavespeed_api_key")
        if not api_keys:
            return None, "Не установлен API-ключ Wavespeed!"

        input_imgs = list(input_imgs or [])
        if len(input_imgs) > 1:
            return None, "Для Grok Imagine через Wavespeed можно использовать только 1 изображение."

        is_edit = bool(input_imgs)
        model = session_state.get("model") or (
            self.config["wavespeed_grok_edit_model"] if is_edit else self.config["wavespeed_grok_t2i_model"]
        )
        options = self._get_wavespeed_grok_options(session_state.get("request_options"))
        last_error = "Неизвестная ошибка Wavespeed Grok Imagine."

        payload = {
            "prompt": prompt,
        }

        if is_edit:
            source_bytes = await utils.run_sync(self._resize_image, input_imgs[0])
            image_url = await self._upload_image(source_bytes)
            if not image_url:
                return None, "Не удалось загрузить исходное изображение на временный хостинг для Wavespeed Grok Imagine."

            payload["image"] = image_url
        else:
            if options.get("aspect_ratio"):
                payload["aspect_ratio"] = options["aspect_ratio"]
            if options.get("output_format"):
                payload["output_format"] = options["output_format"]

        endpoint = f"https://api.wavespeed.ai/api/v3/{model}"

        for api_key in api_keys:
            if session_state.get("cancel"):
                return None, "Отменено пользователем."

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            try:
                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    async with session.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=90),
                    ) as resp:
                        data, raw_text = await self._read_json_or_text(resp)

                        if resp.status != 200:
                            last_error = self._extract_error_message(data, raw_text[:500], resp.status)
                            continue

                        if not isinstance(data, dict) or data.get("code") != 200:
                            last_error = self._extract_error_message(data, raw_text[:500], resp.status)
                            continue

                        data_obj = data.get("data") or {}
                        task_id = data_obj.get("id")
                        if not task_id:
                            last_error = f"Не получен ID задачи Wavespeed Grok Imagine: {data}"
                            continue

                        poll_url = (
                            (data_obj.get("urls") or {}).get("get")
                            or f"https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"
                        )
                        if isinstance(poll_url, str) and poll_url.startswith("/"):
                            poll_url = f"https://api.wavespeed.ai{poll_url}"

                failed = False
                timeout = int(options.get("timeout") or DEFAULT_WAVESPEED_GROK_OPTIONS["timeout"])
                max_polls = max(1, timeout // 2)

                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    for _ in range(max_polls):
                        if session_state.get("cancel"):
                            return None, "Отменено пользователем."

                        await asyncio.sleep(2)

                        async with session.get(
                            poll_url,
                            headers={"Authorization": f"Bearer {api_key}"},
                            timeout=aiohttp.ClientTimeout(total=60),
                        ) as poll_resp:
                            poll_data, raw_poll_text = await self._read_json_or_text(poll_resp)

                            if poll_resp.status not in {200, 202}:
                                last_error = self._extract_error_message(
                                    poll_data,
                                    raw_poll_text[:500],
                                    poll_resp.status,
                                )
                                failed = True
                                break

                            data_obj = (poll_data or {}).get("data") or {}
                            status = str(data_obj.get("status") or "").strip().lower()
                            if poll_resp.status == 202 and not status:
                                status = "processing"

                            if status == "completed":
                                outputs = data_obj.get("outputs") or []
                                if isinstance(outputs, str):
                                    outputs = [outputs]

                                if not outputs:
                                    last_error = "Задача Wavespeed Grok Imagine выполнена, но изображение не найдено."
                                    failed = True
                                    break

                                first_output = outputs[0]
                                if isinstance(first_output, dict):
                                    img_url = (
                                        first_output.get("url")
                                        or first_output.get("image")
                                        or first_output.get("output")
                                    )
                                else:
                                    img_url = first_output

                                if not img_url:
                                    last_error = "Wavespeed Grok Imagine вернул пустой URL результата."
                                    failed = True
                                    break

                                async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=120)) as img_resp:
                                    if img_resp.status == 200:
                                        return await img_resp.read(), ""

                                    body = await img_resp.text()
                                    last_error = self._extract_error_message(None, body[:500], img_resp.status)
                                    failed = True
                                    break

                            if status in {"failed", "error", "canceled", "cancelled"}:
                                last_error = f"Ошибка Wavespeed Grok Imagine: {data_obj.get('error') or status}"
                                failed = True
                                break

                if failed:
                    continue

                last_error = "Превышено время ожидания Wavespeed Grok Imagine (timeout)."
            except Exception as e:
                if session_state.get("cancel"):
                    return None, "Отменено пользователем."
                last_error = self._stringify_exception(e)

        return None, last_error

    async def _call_wavespeed_grok_video(self, session_state, prompt: str, input_imgs=None, input_video=None):
        api_keys = self._get_secret_values("wavespeed_api_key")
        if not api_keys:
            return None, None, "Не установлен API-ключ Wavespeed!"

        input_imgs = list(input_imgs or [])
        input_video = input_video or None

        if input_video:
            mode = "video_edit"
            model = session_state.get("model") or self.config["wavespeed_grok_video_edit_model"]
        elif input_imgs:
            mode = "image_to_video"
            model = session_state.get("model") or self.config["wavespeed_grok_video_i2v_model"]
        else:
            mode = "text_to_video"
            model = session_state.get("model") or self.config["wavespeed_grok_video_t2v_model"]

        options = self._get_wavespeed_grok_video_options(session_state.get("request_options"), mode)
        last_error = "Неизвестная ошибка Wavespeed Grok Imagine Video."

        payload = {
            "prompt": prompt,
        }

        if mode == "video_edit":
            video_url = await self._upload_video(input_video)
            if not video_url:
                return None, None, "Не удалось загрузить исходное видео на временный хостинг для Wavespeed Grok Imagine Video."
            payload["video"] = video_url
            payload["resolution"] = options["resolution"]

        elif mode == "image_to_video":
            source_bytes = await utils.run_sync(self._resize_image, input_imgs[0])
            image_url = await self._upload_image(source_bytes)
            if not image_url:
                return None, None, "Не удалось загрузить исходное изображение на временный хостинг для Wavespeed Grok Imagine Video."
            payload["image"] = image_url
            payload["duration"] = options["duration"]
            payload["resolution"] = options["resolution"]

        else:
            payload["duration"] = options["duration"]
            payload["resolution"] = options["resolution"]
            if options.get("aspect_ratio"):
                payload["aspect_ratio"] = options["aspect_ratio"]

        endpoint = f"https://api.wavespeed.ai/api/v3/{model}"

        for api_key in api_keys:
            if session_state.get("cancel"):
                return None, None, "Отменено пользователем."

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            try:
                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    async with session.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        data, raw_text = await self._read_json_or_text(resp)

                        if resp.status != 200:
                            last_error = self._extract_error_message(data, raw_text[:500], resp.status)
                            continue

                        if not isinstance(data, dict) or data.get("code") != 200:
                            last_error = self._extract_error_message(data, raw_text[:500], resp.status)
                            continue

                        data_obj = data.get("data") or {}
                        task_id = data_obj.get("id")
                        if not task_id:
                            last_error = f"Не получен ID задачи Wavespeed Grok Imagine Video: {data}"
                            continue

                        poll_url = (
                            (data_obj.get("urls") or {}).get("get")
                            or f"https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"
                        )
                        if isinstance(poll_url, str) and poll_url.startswith("/"):
                            poll_url = f"https://api.wavespeed.ai{poll_url}"

                failed = False
                timeout = int(options.get("timeout") or DEFAULT_WAVESPEED_GROK_VIDEO_OPTIONS["timeout"])
                max_polls = max(1, timeout // 2)

                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    for _ in range(max_polls):
                        if session_state.get("cancel"):
                            return None, None, "Отменено пользователем."

                        await asyncio.sleep(2)

                        async with session.get(
                            poll_url,
                            headers={"Authorization": f"Bearer {api_key}"},
                            timeout=aiohttp.ClientTimeout(total=60),
                        ) as poll_resp:
                            poll_data, raw_poll_text = await self._read_json_or_text(poll_resp)

                            if poll_resp.status not in {200, 202}:
                                last_error = self._extract_error_message(
                                    poll_data,
                                    raw_poll_text[:500],
                                    poll_resp.status,
                                )
                                failed = True
                                break

                            data_obj = (poll_data or {}).get("data") or {}
                            status = str(data_obj.get("status") or "").strip().lower()
                            if poll_resp.status == 202 and not status:
                                status = "processing"

                            if status == "completed":
                                outputs = data_obj.get("outputs") or []
                                if isinstance(outputs, str):
                                    outputs = [outputs]

                                if not outputs:
                                    last_error = "Задача Wavespeed Grok Imagine Video выполнена, но видео не найдено."
                                    failed = True
                                    break

                                first_output = outputs[0]
                                if isinstance(first_output, dict):
                                    video_url = (
                                        first_output.get("url")
                                        or first_output.get("video")
                                        or first_output.get("output")
                                    )
                                else:
                                    video_url = first_output

                                if not video_url:
                                    last_error = "Wavespeed Grok Imagine Video вернул пустой URL результата."
                                    failed = True
                                    break

                                result_duration = (
                                    data_obj.get("duration")
                                    or (options.get("duration") if mode in {"text_to_video", "image_to_video"} else None)
                                )

                                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=300)) as video_resp:
                                    if video_resp.status == 200:
                                        return await video_resp.read(), result_duration, ""

                                    body = await video_resp.text()
                                    last_error = self._extract_error_message(None, body[:500], video_resp.status)
                                    failed = True
                                    break

                            if status in {"failed", "error", "canceled", "cancelled"}:
                                last_error = f"Ошибка Wavespeed Grok Imagine Video: {data_obj.get('error') or status}"
                                failed = True
                                break

                if failed:
                    continue

                last_error = "Превышено время ожидания Wavespeed Grok Imagine Video (timeout)."
            except Exception as e:
                if session_state.get("cancel"):
                    return None, None, "Отменено пользователем."
                last_error = self._stringify_exception(e)

        return None, None, last_error

    async def _call_google(self, model_name: str, prompt: str, input_imgs=None):
        keys = self._get_secret_values("api_key")
        if not keys:
            return {"error": {"message": "Не установлен API-ключ!"}}

        sys_instr = self.config["system_instruction"]
        contents = []

        if input_imgs:
            for img_bytes in input_imgs:
                resized_bytes = await utils.run_sync(self._resize_image, img_bytes)
                contents.append(types.Part.from_bytes(data=resized_bytes, mime_type="image/jpeg"))

        contents.append(prompt)

        safety = [
            types.SafetySetting(category=c, threshold="BLOCK_NONE")
            for c in [
                "HARM_CATEGORY_HARASSMENT",
                "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "HARM_CATEGORY_DANGEROUS_CONTENT",
                "HARM_CATEGORY_CIVIC_INTEGRITY",
            ]
        ]

        config = types.GenerateContentConfig(
            temperature=1.0,
            safety_settings=safety,
        )

        if sys_instr:
            config.system_instruction = sys_instr

        if self.config["google_search"]:
            config.tools = [types.Tool(google_search=types.GoogleSearch())]

        last_error = "Неизвестная ошибка Google."

        for key in keys:
            client = None
            aclient = None
            try:
                client_kwargs = {"api_key": key}
                if self.config["proxy"]:
                    client_kwargs["http_options"] = {"proxy": self.config["proxy"]}

                client = genai.Client(**client_kwargs)
                aclient = client.aio

                response = await aclient.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                return response
            except Exception as e:
                last_error = self._stringify_exception(e)
            finally:
                await self._aclose_if_possible(aclient)
                await self._aclose_if_possible(client)

        return {"error": {"message": last_error}}

    async def _call_grok(self, model_name: str, prompt: str, input_imgs=None):
        api_keys = self._get_secret_values("xai_api_key")
        if not api_keys:
            return None, "Не установлен API-ключ xAI!"

        endpoint = f"{BASE_XAI_URL}/images/generations"
        payload_base = {
            "model": model_name,
            "prompt": prompt,
            "response_format": "b64_json",
            "n": 1,
        }

        if input_imgs:
            endpoint = f"{BASE_XAI_URL}/images/edits"
            if len(input_imgs) == 1:
                resized_bytes = await utils.run_sync(self._resize_image, input_imgs[0])
                b64_str = base64.b64encode(resized_bytes).decode("utf-8")
                payload_base["image"] = {
                    "url": f"data:image/jpeg;base64,{b64_str}",
                    "type": "image_url",
                }
            else:
                payload_base["images"] = []
                for img_bytes in input_imgs:
                    resized_bytes = await utils.run_sync(self._resize_image, img_bytes)
                    b64_str = base64.b64encode(resized_bytes).decode("utf-8")
                    payload_base["images"].append({
                        "url": f"data:image/jpeg;base64,{b64_str}",
                        "type": "image_url",
                    })

        last_error = "Неизвестная ошибка xAI."

        for api_key in api_keys:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            payload = json.loads(json.dumps(payload_base))

            try:
                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    async with session.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        data, raw_text = await self._read_json_or_text(resp)

                        if resp.status != 200:
                            last_error = self._extract_error_message(data, raw_text[:500], resp.status)
                            continue

                        if not isinstance(data, dict) or "data" not in data:
                            last_error = f"Неожиданный формат ответа: {data or raw_text[:500]}"
                            continue

                        try:
                            img_bytes = base64.b64decode(data["data"][0]["b64_json"])
                        except Exception as e:
                            last_error = f"Ошибка декодирования ответа xAI: {self._stringify_exception(e)}"
                            continue

                        return img_bytes, ""
            except Exception as e:
                last_error = self._stringify_exception(e)

        return None, last_error

    async def _call_grok_video(self, session_state, prompt: str, target, input_imgs=None, input_video=None):
        api_keys = self._get_secret_values("xai_api_key")
        if not api_keys:
            return None, None, "Не установлен API-ключ xAI!"

        def _extract_request_id(data):
            if not isinstance(data, dict):
                return None

            for key in ("request_id", "id", "video_id"):
                value = data.get(key)
                if value:
                    return str(value)

            for key in ("data", "job", "result"):
                nested = data.get(key)
                if isinstance(nested, dict):
                    for nested_key in ("request_id", "id", "video_id"):
                        value = nested.get(nested_key)
                        if value:
                            return str(value)

            return None

        def _extract_status(data, raw_text=""):
            if isinstance(data, dict):
                for key in ("status", "state"):
                    value = data.get(key)
                    if value is not None:
                        return str(value).strip().lower()

                for key in ("data", "job", "result"):
                    nested = data.get(key)
                    if isinstance(nested, dict):
                        for nested_key in ("status", "state"):
                            value = nested.get(nested_key)
                            if value is not None:
                                return str(value).strip().lower()

            raw = (raw_text or "").strip().lower()
            if raw and len(raw) <= 128:
                return raw

            return None

        def _extract_progress(data):
            if not isinstance(data, dict):
                return None

            candidates = [data]
            for key in ("data", "job", "result", "video"):
                nested = data.get(key)
                if isinstance(nested, dict):
                    candidates.append(nested)

            for obj in candidates:
                for key in ("progress", "percent", "percentage"):
                    value = obj.get(key)
                    if value is None:
                        continue

                    try:
                        value = float(value)
                        if 0 <= value <= 1:
                            value *= 100
                        value = int(round(value))
                        if 0 <= value <= 100:
                            return value
                    except Exception:
                        pass

            return None

        def _extract_result(data):
            if not isinstance(data, dict):
                return None, None

            candidates = [data]
            for key in ("data", "job", "result", "output", "video"):
                nested = data.get(key)
                if isinstance(nested, dict):
                    candidates.append(nested)

            for obj in candidates:
                video = obj.get("video")
                if isinstance(video, dict):
                    url = video.get("url") or video.get("download_url")
                    duration = video.get("duration") or obj.get("duration")
                    if url:
                        return url, duration

                url = obj.get("url") or obj.get("download_url")
                duration = obj.get("duration")
                if url:
                    return url, duration

            return None, None

        model = session_state.get("model") or self.config["model_grok_video"]
        options = self._get_grok_video_options(session_state.get("request_options"))
        duration = options["duration"]
        aspect_ratio = options["aspect_ratio"]
        resolution = options["resolution"]
        timeout = options["timeout"]

        mode = "text_to_video"
        endpoint = f"{BASE_XAI_URL}/videos/generations"
        payload_base = {
            "model": model,
            "prompt": prompt,
        }

        if input_video:
            mode = "video_edit"
            endpoint = f"{BASE_XAI_URL}/videos/edits"
            video_url = await self._upload_video(input_video)
            if not video_url:
                return None, None, "Не удалось загрузить исходное видео на временный хостинг."

            payload_base["video"] = {"url": video_url}
        elif input_imgs:
            mode = "image_to_video"
            image_bytes = await utils.run_sync(self._resize_image, input_imgs[0])
            b64_str = base64.b64encode(image_bytes).decode("utf-8")
            payload_base["image"] = {"url": f"data:image/jpeg;base64,{b64_str}"}
            payload_base["duration"] = duration
            payload_base["aspect_ratio"] = aspect_ratio
            payload_base["resolution"] = resolution
        else:
            payload_base["duration"] = duration
            payload_base["aspect_ratio"] = aspect_ratio
            payload_base["resolution"] = resolution

        pending_statuses = {
            "pending",
            "queued",
            "submitted",
            "processing",
            "running",
            "in_progress",
            "in-progress",
            "starting",
            "created",
            "accepted",
        }
        done_statuses = {"done", "completed", "complete", "succeeded", "success", "finished"}
        failed_statuses = {"failed", "error", "expired", "cancelled", "canceled", "rejected"}

        last_error = "Неизвестная ошибка Grok Video."

        for api_key in api_keys:
            if session_state.get("cancel"):
                return None, None, "Отменено пользователем."

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            payload = json.loads(json.dumps(payload_base))

            try:
                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    async with session.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        data, raw_text = await self._read_json_or_text(resp)

                        if resp.status not in {200, 202}:
                            last_error = self._extract_error_message(data, raw_text[:500], resp.status)
                            continue

                        request_id = _extract_request_id(data)
                        if not request_id:
                            last_error = f"Не получен request_id: {data or raw_text[:500]}"
                            continue

                    elapsed = 0
                    last_stage = None
                    last_progress = None
                    failed = False
                    real_progress_started = False

                    while elapsed < timeout:
                        if session_state.get("cancel"):
                            return None, None, "Отменено пользователем."

                        async with session.get(
                            f"{BASE_XAI_URL}/videos/{request_id}",
                            headers={"Authorization": headers["Authorization"]},
                            timeout=aiohttp.ClientTimeout(total=60),
                        ) as resp:
                            data, raw_text = await self._read_json_or_text(resp)

                            if resp.status not in {200, 202}:
                                last_error = self._extract_error_message(data, raw_text[:500], resp.status)
                                failed = True
                                break

                        status = _extract_status(data, raw_text)
                        if not status and resp.status == 202:
                            status = "pending"

                        status = (status or "").strip().lower()
                        raw_progress = _extract_progress(data)

                        display_progress = last_progress
                        if raw_progress is not None:
                            if real_progress_started:
                                if 0 < raw_progress < 100:
                                    display_progress = raw_progress
                            elif 0 < raw_progress < 100:
                                real_progress_started = True
                                display_progress = raw_progress

                        if status != last_stage or display_progress != last_progress:
                            last_stage = status
                            last_progress = display_progress
                            try:
                                negative_prompt = self._get_negative_prompt(session_state.get("request_options"))
                                prompt_block = self._get_status_prompt_block(
                                    session_state.get("display_prompt"),
                                    session_state.get("enhanced_prompt"),
                                    negative_prompt=negative_prompt,
                                    short_limit=200,
                                )
                                model_str = self._get_model_str(model)
                                attach_str = self._get_attach_str(
                                    len(session_state.get("input_imgs", [])) + (1 if session_state.get("input_video") else 0)
                                )
                                kb = [[{"text": "❌ Отменить", "callback": self._cancel_gen_cb, "args": (session_state["sid"],)}]]
                                await self._safe_edit(
                                    target,
                                    self._render_grok_video_status_text(
                                        prompt_block,
                                        model_str,
                                        attach_str,
                                        session_state,
                                        mode,
                                        progress=display_progress,
                                    ),
                                    reply_markup=kb,
                                )
                            except Exception:
                                logger.exception("failed to update grok video status")

                        if status in done_statuses:
                            video_url, video_duration = _extract_result(data)
                            if not video_url:
                                last_error = f"Видео URL не найден в ответе: {data or raw_text[:500]}"
                                failed = True
                                break

                            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=300)) as vresp:
                                if vresp.status != 200:
                                    body = await vresp.text()
                                    last_error = self._extract_error_message(None, body[:500], vresp.status)
                                    failed = True
                                    break

                                video_bytes = await vresp.read()

                            return video_bytes, video_duration, ""

                        if status in failed_statuses:
                            err = None
                            if isinstance(data, dict):
                                err = data.get("error")
                                if isinstance(err, dict):
                                    err = err.get("message") or err.get("detail") or str(err)

                                if not err:
                                    for key in ("data", "job", "result"):
                                        nested = data.get(key)
                                        if isinstance(nested, dict):
                                            nested_err = nested.get("error")
                                            if isinstance(nested_err, dict):
                                                nested_err = nested_err.get("message") or nested_err.get("detail") or str(nested_err)
                                            if nested_err:
                                                err = nested_err
                                                break

                            last_error = f"Ошибка Grok Video: {err or status or raw_text[:300] or 'unknown'}"
                            failed = True
                            break

                        if resp.status == 202 or status in pending_statuses or not status:
                            await asyncio.sleep(5)
                            elapsed += 5
                            continue

                        await asyncio.sleep(5)
                        elapsed += 5

                    if failed:
                        continue

                    last_error = "Превышено время ожидания Grok Video (timeout)."
            except Exception as e:
                if session_state.get("cancel"):
                    return None, None, "Отменено пользователем."
                last_error = self._stringify_exception(e)

        return None, None, last_error

    async def _call_gpt_image(self, model_name: str, prompt: str, input_imgs=None, request_options=None):
        api_keys = self._get_openai_keys()
        if not api_keys:
            return None, "Не установлен API-ключ OpenAI!"

        options = self._get_gpt_image_options(request_options)
        timeout = options["timeout"]
        size = options["size"]
        quality = options["quality"]
        background = options["background"]

        prepared_imgs = list((input_imgs or [])[:16])
        last_error = "Неизвестная ошибка GPT Image."

        for api_key in api_keys:
            headers = {"Authorization": f"Bearer {api_key}"}

            try:
                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    if prepared_imgs:
                        form = aiohttp.FormData()
                        form.add_field("model", str(model_name))
                        form.add_field("prompt", str(prompt))
                        form.add_field("n", "1")

                        if size:
                            form.add_field("size", size)
                        if quality:
                            form.add_field("quality", quality)
                        if background:
                            form.add_field("background", background)

                        for idx, img_bytes in enumerate(prepared_imgs, start=1):
                            form.add_field(
                                "image[]",
                                img_bytes,
                                filename=f"image_{idx}.jpg",
                                content_type="image/jpeg",
                            )

                        async with session.post(
                            f"{BASE_OPENAI_URL}/images/edits",
                            data=form,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=timeout),
                        ) as resp:
                            result, raw_text = await self._read_json_or_text(resp)
                    else:
                        payload = {
                            "model": model_name,
                            "prompt": prompt,
                            "n": 1,
                        }
                        if size:
                            payload["size"] = size
                        if quality:
                            payload["quality"] = quality
                        if background:
                            payload["background"] = background

                        async with session.post(
                            f"{BASE_OPENAI_URL}/images/generations",
                            json=payload,
                            headers={**headers, "Content-Type": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=timeout),
                        ) as resp:
                            result, raw_text = await self._read_json_or_text(resp)

                    if resp.status >= 400:
                        last_error = self._extract_error_message(result, raw_text[:500], resp.status)
                        continue

                    if isinstance(result, dict) and result.get("error"):
                        last_error = self._extract_error_message(result)
                        continue

                    data_list = result.get("data") if isinstance(result, dict) else None
                    if not isinstance(data_list, list) or not data_list:
                        last_error = f"Пустой ответ OpenAI Images: {result or raw_text[:500]}"
                        continue

                    first_item = data_list[0] or {}
                    b64_json = first_item.get("b64_json")
                    if b64_json:
                        try:
                            return base64.b64decode(b64_json), ""
                        except Exception as e:
                            last_error = f"Ошибка декодирования GPT Image: {self._stringify_exception(e)}"
                            continue

                    img_url = first_item.get("url")
                    if img_url:
                        async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=120)) as img_resp:
                            if img_resp.status == 200:
                                return await img_resp.read(), ""

                            body = await img_resp.text()
                            last_error = self._extract_error_message(None, body[:500], img_resp.status)
                            continue

                    last_error = self._extract_error_message(result, "Изображение не найдено в ответе OpenAI.")
            except Exception as e:
                last_error = self._stringify_exception(e)

        return None, last_error

    async def _run_init_gen_safe(self, message: Message, provider: str):
        try:
            await self._init_gen(message, provider)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("init_gen failed provider=%s", provider)
            try:
                await utils.answer(
                    message,
                    self._render_error_message(
                        self._stringify_exception(e),
                        provider=provider,
                        origin_message=message,
                    ),
                )
            except Exception:
                logger.exception("failed to send init_gen fallback error")

    async def _run_start_generation_safe(self, **kwargs):
        message = kwargs.get("message")
        provider = kwargs.get("provider")
        try:
            await self._start_generation(**kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("start_generation failed provider=%s", provider)
            try:
                if message:
                    await utils.answer(
                        message,
                        self._render_error_message(
                            self._stringify_exception(e),
                            provider=provider,
                            origin_message=message,
                        ),
                    )
            except Exception:
                logger.exception("failed to send start_generation fallback error")

    @loader.command(ru_doc="[реплай на фото] - Прикрепить фото для генерации")
    async def igattach(self, message: Message):
        """[реплай на фото] - Прикрепить фото для следующих генераций"""
        reply = await message.get_reply_message()
        if not reply or not reply.media:
            return await utils.answer(message, self._get_str("attach_err"))

        try:
            if reply.photo or (reply.document and (reply.document.mime_type or "").startswith("image/")):
                img_bytes = await self._client.download_media(reply, file=bytes)
                self.attached_images.append(img_bytes)
                await utils.answer(message, self._get_str("attach_success", len(self.attached_images)))
            else:
                await utils.answer(message, self._get_str("attach_err"))
        except Exception as e:
            logger.exception("attach error")
            await utils.answer(message, self._render_error_message(self._stringify_exception(e)))

    @loader.command(ru_doc=" - Открепить все фото")
    async def igdetach(self, message: Message):
        """Открепить все прикрепленные фото"""
        self.attached_images.clear()
        await utils.answer(message, self._get_str("detach_success"))

    @loader.command(ru_doc=" - Экспорт истории в .json")
    async def igexport(self, message: Message):
        """Экспортировать историю генераций в JSON"""
        history = self.db.get("ImageGen", "history", [])
        if not history:
            return await utils.answer(message, self._get_str("history_empty"))

        data = json.dumps(history, ensure_ascii=False, indent=4)
        f = io.BytesIO(data.encode("utf-8"))
        f.name = "imagegen_history.json"

        await self._client.send_file(
            message.chat.id,
            f,
            caption=f"<blockquote>📦 <b>Экспорт истории ImageGen</b></blockquote>\n<i>Всего записей:</i> <b>{len(history)}</b>",
            reply_to=message.reply_to_msg_id,
        )

        if message.out:
            await message.delete()

    @loader.command(ru_doc="[реплай на .json] - Импорт истории")
    async def igimport(self, message: Message):
        """[реплай на .json] - Импортировать историю генераций"""
        reply = await message.get_reply_message()
        if not reply or not reply.document or not reply.file.name.endswith(".json"):
            return await utils.answer(message, "<blockquote>❌ <b>Ответьте на файл .json!</b></blockquote>")

        try:
            data = await self._client.download_file(reply.document)
            history = json.loads(data.decode("utf-8"))
            if not isinstance(history, list):
                raise ValueError("Файл не содержит список истории")

            curr_history = self.db.get("ImageGen", "history", [])
            curr_ids = {x.get("id") for x in curr_history if isinstance(x, dict) and "id" in x}

            added = 0
            for item in history:
                if isinstance(item, dict) and "id" in item and item["id"] not in curr_ids:
                    curr_history.append(item)
                    curr_ids.add(item["id"])
                    added += 1

            limit = self.config["history_limit"]
            curr_history = curr_history[-limit:]

            self.db.set("ImageGen", "history", curr_history)
            await utils.answer(
                message,
                f"<blockquote>✅ <b>История успешно импортирована!</b></blockquote>\n"
                f"<i>Добавлено новых:</i> <b>{added}</b>\n"
                f"<i>Всего в базе:</i> <b>{len(curr_history)}</b> (Лимит: {limit})",
            )
        except Exception as e:
            logger.exception("import error")
            await utils.answer(message, self._render_error_message(self._stringify_exception(e)))

    @loader.command(ru_doc="<промпт> [-m MODEL] [реплай на фото] - Генерация через Google")
    async def ig(self, message: Message):
        """<промпт> [-m MODEL] [реплай на фото] - Сгенерировать через Google"""
        self._spawn_managed_task(self._run_init_gen_safe(message, "google"), fresh_context=True)

    @loader.command(ru_doc="<промпт> [-m MODEL] [реплай на фото] - Генерация через Grok (xAI)")
    async def igrok(self, message: Message):
        """<промпт> [-m MODEL] [реплай на фото] - Сгенерировать через Grok"""
        self._spawn_managed_task(self._run_init_gen_safe(message, "grok"), fresh_context=True)

    @loader.command(
        alias="iwg",
        ru_doc="<промпт> [-ar RATIO] [-f FORMAT] [-t SEC] [реплай на фото] - Grok Imagine через Wavespeed"
    )
    async def iwgrok(self, message: Message):
        """<промпт> [-ar RATIO] [-f FORMAT] [-t SEC] [реплай на фото] - Grok Imagine через Wavespeed"""
        self._spawn_managed_task(self._run_init_gen_safe(message, "wavespeed_grok"), fresh_context=True)

    @loader.command(ru_doc="<промпт> [-m MODEL] [-d SEC] [-ar RATIO] [-r RES] [-t SEC] [реплай на фото/видео] - Grok Video")
    async def igrokv(self, message: Message):
        """<промпт> [-m MODEL] [-d SEC] [-ar RATIO] [-r RES] [-t SEC] [реплай на фото/видео] - Сгенерировать видео через Grok Video"""
        self._spawn_managed_task(self._run_init_gen_safe(message, "grok_video"), fresh_context=True)

    @loader.command(
        alias="iwgv",
        ru_doc="<промпт> [-d SEC] [-ar RATIO] [-r RES] [-t SEC] [реплай на фото/видео] - Grok Imagine Video через Wavespeed"
    )
    async def iwgrokv(self, message: Message):
        """<промпт> [-d SEC] [-ar RATIO] [-r RES] [-t SEC] [реплай на фото/видео] - Grok Imagine Video через Wavespeed"""
        self._spawn_managed_task(self._run_init_gen_safe(message, "wavespeed_grok_video"), fresh_context=True)

    @loader.command(ru_doc="<промпт> [-m MODEL] [реплай на фото] - Генерация через Wavespeed")
    async def iw(self, message: Message):
        """<промпт> [-m MODEL] [реплай на фото] - Сгенерировать через Wavespeed"""
        self._spawn_managed_task(self._run_init_gen_safe(message, "wavespeed"), fresh_context=True)

    @loader.command(ru_doc="<промпт> [-n NEGATIVE] - Генерация аниме-изображений через WAI NSFW Space")
    async def iwa(self, message: Message):
        """<промпт> [-n NEGATIVE] - Сгенерировать аниме через WaiNSFW"""
        self._spawn_managed_task(self._run_init_gen_safe(message, "wainsfw"), fresh_context=True)

    @loader.command(alias="gptimg", ru_doc="<промпт> [-m MODEL] [-s SIZE] [-q QUALITY] [-bg BACKGROUND] [-t SEC] [реплай на фото] - GPT Image")
    async def igpt(self, message: Message):
        """<промпт> [-m MODEL] [-s SIZE] [-q QUALITY] [-bg BACKGROUND] [-t SEC] [реплай на фото] - Генерация/редактирование через GPT Image"""
        self._spawn_managed_task(self._run_init_gen_safe(message, "gpt_image"), fresh_context=True)

    @loader.command(ru_doc="[N] - Очистить историю")
    async def igclear(self, message: Message):
        """[N] - Очистить историю"""
        args = utils.get_args_raw(message)
        history = self.db.get("ImageGen", "history", [])

        if not history:
            return await utils.answer(message, self._get_str("history_empty"))

        if not args:
            self.db.set("ImageGen", "history", [])
            self.url_cache.clear()
            return await utils.answer(message, self._get_str("history_cleared"))

        try:
            n = int(args)
            if n <= 0:
                raise ValueError
        except Exception:
            return await utils.answer(message, self._get_str("arg_err"))

        self.db.set("ImageGen", "history", history[:-n])
        await utils.answer(message, self._get_str("history_cleared_n", n))

    @loader.command(ru_doc="[N] - История генераций (1 = последняя)")
    async def ighist(self, message: Message):
        """[N] - Открыть историю (1 = последняя)"""
        history = self.db.get("ImageGen", "history", [])
        if not history:
            if not self.config["history"]:
                return await utils.answer(message, self._history_disabled_text(message))
            return await utils.answer(message, self._get_str("history_empty"))

        args = utils.get_args_raw(message).strip()
        display_index = 0

        if args:
            try:
                n = int(args)
                if n <= 0:
                    raise ValueError
            except Exception:
                return await utils.answer(message, self._get_str("arg_err"))

            if n > len(history):
                return await utils.answer(message, self._get_str("history_index_err", len(history)))

            display_index = n - 1

        msg = await self.inline.form(
            self._get_str("uploading"),
            message=message,
            reply_markup=self._get_loading_markup(),
        )

        class FakeCall:
            def __init__(self, msg_obj):
                self.message = msg_obj

            async def edit(self, *args, **kwargs):
                await self.message.edit(*args, **kwargs)

            async def answer(self, *args, **kwargs):
                pass

            async def delete(self):
                await self.message.delete()

        await self._render_history_slide(FakeCall(msg), display_index)

    async def _confirm_lang_continue_cb(self, call: InlineCall, token: str):
        data = self.pending_lang_confirms.pop(token, None)
        if not data:
            return await call.answer("Запрос истек", show_alert=True)

        await call.answer("Продолжаю...")

        if self.config["inline_mode"]:
            self._spawn_managed_task(
                self._run_start_generation_safe(
                    message=data["message"],
                    provider=data["provider"],
                    user_prompt=data["user_prompt"],
                    full_prompt=data["full_prompt"],
                    input_imgs=data["input_imgs"],
                    input_video=data.get("input_video"),
                    model=data["model"],
                    request_options=data.get("request_options", {}),
                    status_target=call,
                    status_target_inline=True,
                ),
                fresh_context=True,
            )
            return

        try:
            await call.delete()
        except Exception:
            logger.exception("failed to delete language warning form before non-inline generation")

        self._spawn_managed_task(
            self._run_start_generation_safe(
                message=data["message"],
                provider=data["provider"],
                user_prompt=data["user_prompt"],
                full_prompt=data["full_prompt"],
                input_imgs=data["input_imgs"],
                input_video=data.get("input_video"),
                model=data["model"],
                request_options=data.get("request_options", {}),
            ),
            fresh_context=True,
        )

    async def _cancel_lang_continue_cb(self, call: InlineCall, token: str):
        self.pending_lang_confirms.pop(token, None)
        await self._safe_close(call)

    async def _start_generation(
        self,
        message,
        provider: str,
        user_prompt: str,
        full_prompt: str,
        input_imgs: list,
        model: str,
        request_options=None,
        input_video=None,
        status_target=None,
        status_target_inline: bool = False,
    ):
        enhanced_prompt = None
        api_prompt = full_prompt
        request_options = request_options or {}
        negative_prompt = self._get_negative_prompt(request_options)

        prompt_block = self._get_status_prompt_block(
            user_prompt,
            enhanced_prompt,
            negative_prompt=negative_prompt,
            short_limit=200,
        )

        model_str = self._get_model_str(model)
        attach_str = self._get_attach_str(len(input_imgs) + (1 if input_video else 0))

        if provider == "grok_video":
            mode = "video_edit" if input_video else "image_to_video" if input_imgs else "text_to_video"
            status_text = self._render_grok_video_status_text(prompt_block, model_str, attach_str, {"request_options": request_options}, mode, progress=None)
        elif provider == "wavespeed_grok_video":
            mode = "video_edit" if input_video else "image_to_video" if input_imgs else "text_to_video"
            status_text = self._render_wavespeed_grok_video_status_text(prompt_block, model_str, attach_str, {"request_options": request_options}, mode)
        else:
            status_key = "edit_new" if (input_imgs or input_video) else "gen_new"
            status_text = self._get_str(status_key, prompt_block, model_str, attach_str)

        sid = str(uuid.uuid4())
        self.sessions[sid] = {
            "sid": sid,
            "api_prompt": api_prompt,
            "display_prompt": user_prompt,
            "enhanced_prompt": enhanced_prompt,
            "images": [],
            "index": -1,
            "input_imgs": input_imgs,
            "input_video": input_video,
            "from_history": False,
            "model": model,
            "request_options": request_options,
            "text_page": 0,
            "provider": provider,
            "cancel": False,
            "show_full_prompt": False,
            "task": None,
            "direct_result": False,
            "origin_chat_id": getattr(message, "chat_id", None),
            "origin_reply_to": getattr(message, "reply_to_msg_id", None),
            "origin_message": message,
            "last_media_bytes": None,
            "last_media_type": None,
            "last_media_duration": None,
            "pending_display": False,
        }

        target = status_target
        target_inline = status_target_inline

        if target:
            if target_inline:
                await self._safe_edit(
                    target,
                    status_text,
                    reply_markup=self._get_loading_markup(),
                )
            else:
                await self._safe_edit(target, status_text)
        else:
            target, target_inline = await self._create_status_target(message, status_text)

        self.sessions[sid]["direct_result"] = not target_inline

        logger.info(
            "session created sid=%s provider=%s model=%s input_imgs=%s input_video=%s direct_result=%s",
            sid,
            provider,
            model,
            len(input_imgs),
            bool(input_video),
            self.sessions[sid]["direct_result"],
        )

        self._spawn_managed_task(self._process_gen(target, sid), sid=sid, fresh_context=False)

    async def _init_gen(self, message, provider="google"):
        raw_args = utils.get_args_raw(message)

        try:
            raw_prompt, model_override, request_options = self._parse_provider_args(provider, raw_args)
        except Exception as e:
            return await utils.answer(
                message,
                self._get_str("flag_parse_error", utils.escape_html(self._stringify_exception(e))),
            )

        if provider == "google" and not self._get_secret_values("api_key"):
            return await utils.answer(
                message,
                self._missing_key_text(self._get_str("no_api"), message, "api_key", ["ig"]),
            )

        if provider == "grok" and not self._get_secret_values("xai_api_key"):
            text = self._missing_key_text(
                "❌ <b>Не установлен API-ключ для xAI!</b>",
                message,
                "xai_api_key",
                ["igrok"],
            )
            return await utils.answer(message, self._append_wavespeed_grok_alt_hint(text, message))

        if provider == "grok_video" and not self._get_secret_values("xai_api_key"):
            text = self._missing_key_text(
                "❌ <b>Не установлен API-ключ для xAI!</b>",
                message,
                "xai_api_key",
                ["igrokv"],
            )
            return await utils.answer(message, self._append_wavespeed_grok_video_alt_hint(text, message))

        if provider == "wavespeed" and not self._get_secret_values("wavespeed_api_key"):
            return await utils.answer(
                message,
                self._missing_key_text(
                    "❌ <b>Не установлен API-ключ для Wavespeed!</b>",
                    message,
                    "wavespeed_api_key",
                    ["iw"],
                ),
            )

        if provider == "wavespeed_grok" and not self._get_secret_values("wavespeed_api_key"):
            return await utils.answer(
                message,
                self._missing_key_text(
                    "❌ <b>Не установлен API-ключ для Wavespeed!</b>",
                    message,
                    "wavespeed_api_key",
                    ["iwgrok", "iwg"],
                ),
            )

        if provider == "wavespeed_grok_video" and not self._get_secret_values("wavespeed_api_key"):
            return await utils.answer(
                message,
                self._missing_key_text(
                    "❌ <b>Не установлен API-ключ для Wavespeed!</b>",
                    message,
                    "wavespeed_api_key",
                    ["iwgrokv", "iwgv"],
                ),
            )

        if provider == "gpt_image" and not self._get_openai_keys():
            return await utils.answer(
                message,
                self._missing_key_text(
                    self._get_str("no_gpt_image_api"),
                    message,
                    "openai_api_key",
                    ["igpt", "gptimg"],
                ),
            )

        input_imgs = self.attached_images.copy()
        input_video = None

        reply = await message.get_reply_message()
        if (reply and reply.media) or message.media:
            target_media = reply if reply and reply.media else message
            try:
                mime = ""
                if target_media.document and target_media.document.mime_type:
                    mime = target_media.document.mime_type

                is_image = bool(target_media.photo or mime.startswith("image/"))
                is_video = bool(mime.startswith("video/"))

                if provider in {"grok_video", "wavespeed_grok_video"}:
                    if is_video:
                        input_video = await self._client.download_media(target_media, file=bytes)
                    elif is_image:
                        img_bytes = await self._client.download_media(target_media, file=bytes)
                        input_imgs.append(img_bytes)
                else:
                    if is_image:
                        img_bytes = await self._client.download_media(target_media, file=bytes)
                        input_imgs.append(img_bytes)
            except Exception:
                logger.exception("failed to download input media in _init_gen")

        if provider == "gpt_image" and len(input_imgs) > 16:
            input_imgs = input_imgs[-16:]

        if not raw_prompt and not self.config["system_instruction"]:
            return await utils.answer(message, "Введите промпт")

        if provider == "grok" and len(input_imgs) > 3:
            return await utils.answer(
                message,
                self._get_str("grok_limit", self._get_prefix_html(message, ["igrok", "igdetach"])),
            )

        if provider == "wavespeed_grok" and len(input_imgs) > 1:
            return await utils.answer(
                message,
                self._get_str("wavespeed_grok_limit", self._get_prefix_html(message, ["iwgrok", "iwg", "igdetach"])),
            )

        if model_override:
            model = model_override
        elif provider == "wavespeed":
            model = self.config["wavespeed_model_i2i"] if input_imgs else self.config["wavespeed_model_t2i"]
        elif provider == "wavespeed_grok":
            model = self.config["wavespeed_grok_edit_model"] if input_imgs else self.config["wavespeed_grok_t2i_model"]
        elif provider == "wavespeed_grok_video":
            if input_video:
                model = self.config["wavespeed_grok_video_edit_model"]
            elif input_imgs:
                model = self.config["wavespeed_grok_video_i2v_model"]
            else:
                model = self.config["wavespeed_grok_video_t2v_model"]
        elif provider == "wainsfw":
            model = "WaiNSFW"
        elif provider == "gpt_image":
            model = self.config["model_gpt_image"]
        elif provider == "grok_video":
            model = self.config["model_grok_video"]
        else:
            model = self.config["model_google"] if provider == "google" else self.config["model_grok"]

        full_prompt = raw_prompt
        user_prompt = full_prompt if full_prompt else "..."

        if provider in {"wavespeed", "wainsfw"} and full_prompt and self._prompt_has_non_english_letters(full_prompt):
            token = str(uuid.uuid4())
            self.pending_lang_confirms[token] = {
                "message": message,
                "provider": provider,
                "user_prompt": user_prompt,
                "full_prompt": full_prompt,
                "input_imgs": input_imgs,
                "input_video": input_video,
                "model": model,
                "request_options": request_options,
            }

            warning_text = self._render_lang_warning(provider, full_prompt)
            try:
                form = await self.inline.form(
                    warning_text,
                    message=message,
                    reply_markup=[
                        [{"text": self.strings("btn_continue_anyway"), "callback": self._confirm_lang_continue_cb, "args": (token,)}],
                        [{"text": self.strings("btn_cancel"), "callback": self._cancel_lang_continue_cb, "args": (token,)}],
                    ],
                )
                if form:
                    return
            except Exception:
                logger.exception("failed to show language confirmation form")

            self.pending_lang_confirms.pop(token, None)
            return await utils.answer(message, warning_text)

        await self._start_generation(
            message=message,
            provider=provider,
            user_prompt=user_prompt,
            full_prompt=full_prompt,
            input_imgs=input_imgs,
            input_video=input_video,
            model=model,
            request_options=request_options,
        )

    async def _cancel_gen_cb(self, call: InlineCall, sid):
        if sid in self.sessions:
            session = self.sessions[sid]
            session["cancel"] = True
            session["last_error"] = "Отменено пользователем."
            session["pending_display"] = True

            task = session.get("task")
            if task and not task.done():
                task.cancel()

            rendered_error = self._render_error_message(
                session["last_error"],
                provider=session.get("provider"),
                origin_message=session.get("origin_message"),
            )

            kb = [
                [{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)}],
                [{"text": self.strings("btn_model"), "callback": self._model_menu, "args": (sid,)}],
            ]

            if session.get("from_history"):
                kb.append([{"text": self.strings("btn_back_hist"), "callback": self._back_to_menu}])
            else:
                kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

            ok = await self._safe_edit(call, rendered_error, reply_markup=kb)
            if ok:
                session["pending_display"] = False

            await call.answer("Отменяем...", show_alert=False)
        else:
            await call.answer("Сессия истекла", show_alert=True)

    async def _process_gen(self, target, sid):
        if sid not in self.sessions:
            return await self._safe_close(target)

        s = self.sessions[sid]
        current_task = asyncio.current_task()
        if current_task:
            s["task"] = current_task
        s["cancel"] = False

        logger.info(
            "generation started sid=%s provider=%s model=%s direct_result=%s",
            sid,
            s.get("provider"),
            s.get("model"),
            s.get("direct_result"),
        )

        try:
            media_bytes = None
            media_type = "image"
            media_duration = None
            text_resp = ""

            max_retries = self.config["retry_censor_limit"]
            attempt = 1

            while attempt <= max_retries:
                if s.get("cancel"):
                    raise ValueError("Отменено пользователем.")

                try:
                    if s.get("provider") == "grok":
                        media_type = "image"
                        media_bytes, err = await self._call_grok(s["model"], s["api_prompt"], s.get("input_imgs"))
                        if err:
                            raise ValueError(err)

                    elif s.get("provider") == "grok_video":
                        media_type = "video"
                        media_bytes, media_duration, err = await self._call_grok_video(
                            s,
                            s["api_prompt"],
                            target,
                            s.get("input_imgs"),
                            s.get("input_video"),
                        )
                        if err:
                            raise ValueError(err)

                    elif s.get("provider") == "wavespeed":
                        media_type = "image"
                        media_bytes, err = await self._call_wavespeed(s, s["api_prompt"], s.get("input_imgs"))
                        if err:
                            raise ValueError(err)

                    elif s.get("provider") == "wavespeed_grok":
                        media_type = "image"
                        media_bytes, err = await self._call_wavespeed_grok(
                            s,
                            s["api_prompt"],
                            s.get("input_imgs"),
                        )
                        if err:
                            raise ValueError(err)

                    elif s.get("provider") == "wavespeed_grok_video":
                        media_type = "video"
                        media_bytes, media_duration, err = await self._call_wavespeed_grok_video(
                            s,
                            s["api_prompt"],
                            s.get("input_imgs"),
                            s.get("input_video"),
                        )
                        if err:
                            raise ValueError(err)

                    elif s.get("provider") == "wainsfw":
                        media_type = "image"
                        media_bytes, err = await self._call_wainsfw(s, s["api_prompt"])
                        if err:
                            raise ValueError(err)

                    elif s.get("provider") == "gpt_image":
                        media_type = "image"
                        media_bytes, err = await self._call_gpt_image(
                            s["model"],
                            s["api_prompt"],
                            s.get("input_imgs"),
                            s.get("request_options"),
                        )
                        if err:
                            raise ValueError(err)

                    else:
                        media_type = "image"
                        data = await self._call_google(s["model"], s["api_prompt"], s.get("input_imgs"))
                        if isinstance(data, dict) and "error" in data:
                            raise ValueError(data["error"]["message"])

                        try:
                            candidates = getattr(data, "candidates", None)
                            if not candidates:
                                prompt_feedback = getattr(data, "prompt_feedback", None)
                                reason = getattr(prompt_feedback, "block_reason", "Unknown block") if prompt_feedback else "No candidates returned"
                                raise ValueError(f"Запрос заблокирован (причина блокировки: {reason})")

                            candidate = candidates[0]
                            content = getattr(candidate, "content", None)
                            parts = getattr(content, "parts", None) or []

                            for part in parts:
                                if getattr(part, "inline_data", None):
                                    media_bytes = part.inline_data.data
                                elif getattr(part, "text", None):
                                    text_resp += part.text

                            if not media_bytes and not text_resp:
                                reason = getattr(candidate, "finish_reason", "Unknown")
                                raise ValueError(f"Пустой ответ от API (finish_reason: {reason})")

                        except ValueError:
                            raise
                        except Exception as e:
                            raise ValueError(f"Ошибка структуры ответа: {e}")

                    break

                except Exception as e:
                    error_text = str(e)
                    censor_keys = [
                        "block reason",
                        "prohibited",
                        "violated",
                        "unable to show",
                        "safety",
                        "rejected by content moderation",
                        "moderation",
                    ]
                    is_censor = any(k in error_text.lower() for k in censor_keys)

                    if is_censor and s.get("provider") not in {"grok_video", "wavespeed_grok_video"} and attempt < max_retries:
                        attempt += 1

                        negative_prompt = self._get_negative_prompt(s.get("request_options"))
                        prompt_block = self._get_status_prompt_block(
                            s["display_prompt"],
                            s.get("enhanced_prompt"),
                            negative_prompt=negative_prompt,
                            short_limit=200,
                        )
                        model_str = self._get_model_str(s["model"])
                        text = self._get_str("censor_retry", attempt, max_retries, prompt_block, model_str)

                        kb = [[{"text": "❌ Отменить", "callback": self._cancel_gen_cb, "args": (sid,)}]]
                        await self._safe_edit(target, text, reply_markup=kb)

                        for _ in range(15):
                            if s.get("cancel"):
                                break
                            await asyncio.sleep(0.1)

                        if s.get("cancel"):
                            raise ValueError("Отменено пользователем.")

                        continue

                    raise

            logger.info(
                "generation success sid=%s provider=%s model=%s media_type=%s has_media=%s text_len=%s",
                sid,
                s.get("provider"),
                s.get("model"),
                media_type,
                bool(media_bytes),
                len(text_resp or ""),
            )

            if s.get("direct_result") and self.config["inline_mode"]:
                promoted_target = await self._try_promote_session_to_inline(
                    target,
                    s,
                    self._get_str("uploading"),
                )
                if promoted_target:
                    target = promoted_target
                    s["direct_result"] = False

            if s.get("direct_result"):
                await self._send_direct_result(
                    target,
                    s,
                    media_bytes,
                    text_resp,
                    media_type=media_type,
                    duration=media_duration,
                )
                if self.config["history"]:
                    db_url = await (self._upload_video(media_bytes) if media_type == "video" else self._upload_image(media_bytes)) if media_bytes else None
                    history = self.db.get("ImageGen", "history", [])
                    history.append({
                        "id": str(uuid.uuid4()),
                        "prompt": s["display_prompt"],
                        "enhanced_prompt": s.get("enhanced_prompt"),
                        "api_prompt": s.get("api_prompt"),
                        "bytes": None,
                        "url": db_url,
                        "text_resp": text_resp,
                        "model": s["model"],
                        "request_options": s.get("request_options", {}),
                        "is_edit": bool(s.get("input_imgs") or s.get("input_video")),
                        "provider": s.get("provider", "google"),
                        "media_type": media_type,
                        "duration": media_duration,
                    })
                    self.db.set("ImageGen", "history", history[-self.config["history_limit"]:])
                self.sessions.pop(sid, None)
                return

            hist_id = str(uuid.uuid4())
            display_url = None

            if hasattr(target, "edit"):
                await self._safe_edit(
                    target,
                    self._get_str("uploading"),
                    reply_markup=self._get_loading_markup(),
                )

            if media_bytes:
                display_url = await (self._upload_video(media_bytes) if media_type == "video" else self._upload_image(media_bytes))

            if media_bytes and not display_url:
                logger.warning("failed to upload generated media for inline view sid=%s, fallback to direct send", sid)
                sent = await self._send_result_to_origin(
                    s,
                    media_bytes,
                    text_resp,
                    media_type=media_type,
                    duration=media_duration,
                )
                if sent:
                    if self.config["history"]:
                        history = self.db.get("ImageGen", "history", [])
                        history.append({
                            "id": hist_id,
                            "prompt": s["display_prompt"],
                            "enhanced_prompt": s.get("enhanced_prompt"),
                            "api_prompt": s.get("api_prompt"),
                            "bytes": None,
                            "url": None,
                            "text_resp": text_resp,
                            "model": s["model"],
                            "request_options": s.get("request_options", {}),
                            "is_edit": bool(s.get("input_imgs") or s.get("input_video")),
                            "provider": s.get("provider", "google"),
                            "media_type": media_type,
                            "duration": media_duration,
                        })
                        self.db.set("ImageGen", "history", history[-self.config["history_limit"]:])

                    await self._safe_close(target)
                    self.sessions.pop(sid, None)
                    return

            if not display_url and not media_bytes and media_type != "video":
                display_url = "https://raw.githubusercontent.com/h-m-256/repository/refs/heads/main/media/empty.png"

            if self.config["history"]:
                history = self.db.get("ImageGen", "history", [])
                history.append({
                    "id": hist_id,
                    "prompt": s["display_prompt"],
                    "enhanced_prompt": s.get("enhanced_prompt"),
                    "api_prompt": s.get("api_prompt"),
                    "bytes": None,
                    "url": display_url,
                    "text_resp": text_resp,
                    "model": s["model"],
                    "request_options": s.get("request_options", {}),
                    "is_edit": bool(s.get("input_imgs") or s.get("input_video")),
                    "provider": s.get("provider", "google"),
                    "media_type": media_type,
                    "duration": media_duration,
                })
                self.db.set("ImageGen", "history", history[-self.config["history_limit"]:])

            if display_url:
                self.url_cache[hist_id] = display_url

            s["last_media_bytes"] = media_bytes
            s["last_media_type"] = media_type
            s["last_media_duration"] = media_duration
            s["pending_display"] = True
            s["images"].append({
                "url": display_url,
                "text": text_resp,
                "model": s["model"],
                "media_type": media_type,
                "duration": media_duration,
            })
            s["index"] = len(s["images"]) - 1
            s["text_page"] = 0
            s.pop("last_error", None)

            await self._update_gen_view(target, sid)

        except asyncio.CancelledError:
            logger.info("generation cancelled sid=%s", sid)
            raise
        except Exception as e:
            raw_error_text = self._stringify_exception(e)

            if raw_error_text == "Отменено пользователем.":
                logger.info(
                    "generation cancelled by user sid=%s provider=%s model=%s",
                    sid,
                    s.get("provider"),
                    s.get("model"),
                )
            elif isinstance(e, ValueError):
                logger.error(
                    "generation error sid=%s provider=%s model=%s: %s",
                    sid,
                    s.get("provider"),
                    s.get("model"),
                    raw_error_text,
                )
            else:
                logger.exception(
                    "generation error sid=%s provider=%s model=%s",
                    sid,
                    s.get("provider"),
                    s.get("model"),
                )

            rendered_error = self._render_error_message(
                raw_error_text,
                provider=s.get("provider"),
                origin_message=s.get("origin_message"),
            )

            s["last_error"] = raw_error_text
            s["pending_display"] = True

            if s.get("direct_result") and self.config["inline_mode"]:
                promoted_target = await self._try_promote_session_to_inline(
                    target,
                    s,
                    rendered_error,
                )
                if promoted_target:
                    target = promoted_target
                    s["direct_result"] = False

            if s.get("direct_result"):
                ok = await self._safe_edit(target, rendered_error)
                if not ok:
                    await self._send_error_to_origin(s, rendered_error)
                s["pending_display"] = False
                self.sessions.pop(sid, None)
                return

            kb = [
                [{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)}],
                [{"text": self.strings("btn_model"), "callback": self._model_menu, "args": (sid,)}],
            ]

            if s.get("from_history"):
                kb.append([{"text": self.strings("btn_back_hist"), "callback": self._back_to_menu}])
            else:
                kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

            ok = await self._safe_edit(target, rendered_error, reply_markup=kb)
            if not ok:
                await self._send_error_to_origin(s, rendered_error)

            s["pending_display"] = False
        finally:
            current = asyncio.current_task()
            if sid in self.sessions and self.sessions[sid].get("task") is current:
                self.sessions[sid]["task"] = None

    async def _send_direct_result(
        self,
        target,
        s,
        media_bytes,
        text_resp,
        *,
        media_type="image",
        duration=None,
        chat_id=None,
        reply_to_msg_id=None,
        delete_target=True,
    ):
        negative_prompt = self._get_negative_prompt(s.get("request_options"))
        prompt_block = self._get_status_prompt_block(
            s["display_prompt"],
            s.get("enhanced_prompt"),
            negative_prompt=negative_prompt,
            short_limit=200,
        )

        is_edit = bool(s.get("input_imgs") or s.get("input_video"))
        model_str = self._get_model_str(s["model"])
        attach_str = self._get_attach_str(len(s.get("input_imgs", [])) + (1 if s.get("input_video") else 0))

        if media_type == "video":
            key = "video_success_text" if text_resp else "video_success"
            text_args = [prompt_block, model_str, attach_str, self._format_duration(duration)]
            if text_resp:
                text_args.extend([1, 1, utils.escape_html(text_resp)[:200]])
        else:
            if media_bytes:
                key = (
                    "edit_success_text" if is_edit and text_resp
                    else "edit_success" if is_edit
                    else "success_with_text" if text_resp
                    else "success"
                )
            else:
                key = "only_text_response" if text_resp else "error_no_data"

            text_args = [prompt_block, model_str, attach_str]
            if text_resp:
                text_args.extend([1, 1, utils.escape_html(text_resp)[:200]])

        caption = self._get_str(key, *text_args)

        if chat_id is None and target is not None:
            chat_id = getattr(getattr(target, "chat", None), "id", None)
        if reply_to_msg_id is None and target is not None:
            reply_to_msg_id = getattr(target, "reply_to_msg_id", None)

        if not chat_id:
            raise RuntimeError("Не удалось определить chat_id для отправки результата.")

        if delete_target and target is not None and hasattr(target, "delete"):
            try:
                await target.delete()
            except Exception:
                logger.exception("failed to delete status message before sending result")

        if media_type == "video" and media_bytes:
            out = io.BytesIO(media_bytes)
            out.name = "video.mp4"

            if len(caption) > 1000 and text_resp:
                caption = self._get_str("video_success", prompt_block, model_str, attach_str, self._format_duration(duration))

            await self._client.send_file(
                chat_id,
                out,
                caption=caption,
                reply_to=reply_to_msg_id,
                supports_streaming=True,
                force_document=False,
            )

            if text_resp and len(caption) <= 1000:
                chunks = self._smart_split(text_resp, 4000)
                for chunk in chunks:
                    await self._client.send_message(
                        chat_id,
                        f"📜 <b>Ответ:</b>\n<blockquote>{utils.escape_html(chunk)}</blockquote>",
                    )
            return

        if media_bytes:
            out = io.BytesIO(media_bytes)
            out.name = "image.jpg"

            if len(caption) > 1000 and text_resp:
                fallback_key = "edit_success" if is_edit else "success"
                caption = self._get_str(fallback_key, prompt_block, model_str, attach_str)

            await self._client.send_file(
                chat_id,
                out,
                caption=caption,
                reply_to=reply_to_msg_id,
                force_document=False,
            )

            if text_resp and len(caption) <= 1000:
                chunks = self._smart_split(text_resp, 4000)
                for chunk in chunks:
                    await self._client.send_message(
                        chat_id,
                        f"📜 <b>Ответ:</b>\n<blockquote>{utils.escape_html(chunk)}</blockquote>",
                    )

        elif text_resp:
            chunks = self._smart_split(text_resp, 4000)
            header = self._get_str("only_text_header_direct", prompt_block, model_str, attach_str)
            await self._client.send_message(chat_id, header, reply_to=reply_to_msg_id)
            for chunk in chunks:
                await self._client.send_message(chat_id, f"<blockquote>{utils.escape_html(chunk)}</blockquote>")
        else:
            await self._client.send_message(
                chat_id,
                self._get_str("error_no_data", prompt_block, model_str, attach_str),
                reply_to=reply_to_msg_id,
            )

    async def _dl_prompt_cb(self, call: InlineCall, sid):
        if sid not in self.sessions:
            return await call.answer("Сессия истекла", show_alert=True)

        prompt_text = self._build_prompt_file_text(
            self.sessions[sid].get("display_prompt"),
            self.sessions[sid].get("enhanced_prompt"),
            negative_prompt=self._get_negative_prompt(self.sessions[sid].get("request_options")),
        )

        f = io.BytesIO(prompt_text.encode("utf-8"))
        f.name = "prompt.txt"

        try:
            chat_id = None
            if hasattr(call, "form") and call.form.get("message"):
                chat_id = call.form["message"].chat_id
            if not chat_id:
                chat_id = getattr(getattr(call, "message", None), "chat_id", None)
            if not chat_id:
                chat_id = getattr(call, "sender_id", None)

            await self._client.send_file(chat_id, f, caption="📝 <b>Ваш промпт</b>")
            await call.answer("Отправлено!")
        except Exception as e:
            logger.exception("failed to send prompt file")
            await call.answer(f"Ошибка отправки: {e}", show_alert=True)

    async def _hist_dl_prompt(self, call: InlineCall, item_id):
        history = self.db.get("ImageGen", "history", [])
        item = next((x for x in history if x["id"] == item_id), None)
        if not item:
            return await call.answer("Не найдено", show_alert=True)

        prompt_text = self._build_prompt_file_text(
            item.get("prompt", ""),
            item.get("enhanced_prompt"),
            negative_prompt=self._get_negative_prompt(item.get("request_options")),
        )

        f = io.BytesIO(prompt_text.encode("utf-8"))
        f.name = "prompt.txt"

        try:
            chat_id = None
            if hasattr(call, "form") and call.form.get("message"):
                chat_id = call.form["message"].chat_id
            if not chat_id:
                chat_id = getattr(getattr(call, "message", None), "chat_id", None)
            if not chat_id:
                chat_id = getattr(call, "sender_id", None)

            await self._client.send_file(chat_id, f, caption="📝 <b>Промпт из истории</b>")
            await call.answer("Отправлено!")
        except Exception as e:
            logger.exception("failed to send history prompt file")
            await call.answer(f"Ошибка отправки: {e}", show_alert=True)

    async def _show_full_prompt_cb(self, call: InlineCall, sid):
        if sid not in self.sessions:
            return await call.answer("Сессия истекла", show_alert=True)

        session = self.sessions[sid]
        negative_prompt = self._get_negative_prompt(session.get("request_options"))
        if not self._has_prompt(session.get("display_prompt"), session.get("enhanced_prompt"), negative_prompt):
            return await call.answer("Промпт отсутствует", show_alert=True)

        if not self._can_show_session_prompt_inline(session):
            return await self._dl_prompt_cb(call, sid)

        self.sessions[sid]["show_full_prompt"] = True
        await self._update_gen_view(call, sid)

    async def _hide_full_prompt_cb(self, call: InlineCall, sid):
        if sid not in self.sessions:
            return await call.answer("Сессия истекла", show_alert=True)
        self.sessions[sid]["show_full_prompt"] = False
        await self._update_gen_view(call, sid)

    async def _update_gen_view(self, target, sid):
        if sid not in self.sessions:
            return

        s = self.sessions[sid]

        if not s.get("images"):
            rendered_error = self._render_error_message(
                s.get("last_error", "Неизвестная ошибка."),
                provider=s.get("provider"),
                origin_message=s.get("origin_message"),
            )
            kb = [
                [{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)}],
                [{"text": self.strings("btn_model"), "callback": self._model_menu, "args": (sid,)}],
                [{"text": self.strings("btn_close"), "callback": self._safe_close}],
            ]
            ok = await self._safe_edit(target, rendered_error, reply_markup=kb)
            if not ok and s.get("pending_display"):
                await self._send_error_to_origin(s, rendered_error)
            s["pending_display"] = False
            return

        idx = s["index"]
        data = s["images"][idx]
        media_url = data.get("url")
        media_type = data.get("media_type", "image")
        duration = data.get("duration")
        ai_text = data.get("text", "")
        model = data.get("model", s.get("model", "Unknown"))
        negative_prompt = self._get_negative_prompt(s.get("request_options"))

        text_page = s.get("text_page", 0)
        text_chunks = self._smart_split(ai_text, 800)
        total_text_pages = len(text_chunks)

        if text_page >= total_text_pages:
            text_page = max(0, total_text_pages - 1)
        s["text_page"] = text_page

        current_text = text_chunks[text_page] if text_chunks else ""
        is_empty_img = self._is_empty_image(media_url)
        has_media = bool(media_url) and not is_empty_img
        is_edit = bool(s.get("input_imgs") or s.get("input_video"))

        prompt_exists = self._has_prompt(s.get("display_prompt"), s.get("enhanced_prompt"), negative_prompt)
        prompt_block = self._build_prompt_block(
            s["display_prompt"],
            s.get("enhanced_prompt"),
            negative_prompt=negative_prompt,
            show_full=s.get("show_full_prompt", False),
            short_limit=200,
        )

        show_prompt_button = prompt_exists and (
            self._is_prompt_long(s.get("display_prompt"), s.get("enhanced_prompt"), negative_prompt, short_limit=200)
            or s.get("show_full_prompt")
        )

        model_str = self._get_model_str(model)
        attach_str = self._get_attach_str(len(s.get("input_imgs", [])) + (1 if s.get("input_video") else 0))

        if media_type == "video":
            if ai_text:
                key = "video_success_text"
                text_args = [prompt_block, model_str, attach_str, self._format_duration(duration), text_page + 1, total_text_pages, utils.escape_html(current_text.strip())]
            else:
                key = "video_success"
                text_args = [prompt_block, model_str, attach_str, self._format_duration(duration)]
        else:
            if has_media:
                key = (
                    "edit_success_text" if is_edit and ai_text
                    else "edit_success" if is_edit
                    else "success_with_text" if ai_text
                    else "success"
                )
            else:
                key = "only_text_response" if ai_text else "error_no_data"

            text_args = [prompt_block, model_str, attach_str]
            if ai_text:
                text_args.extend([text_page + 1, total_text_pages, utils.escape_html(current_text.strip())])

        text_to_show = self._get_str(key, *text_args)

        kb = []

        if len(s["images"]) > 1:
            kb.append([
                {"text": "⬅️ Вариант", "callback": self._nav_gen_cb, "args": (sid, -1)},
                {"text": f"{idx + 1}/{len(s['images'])}", "callback": self._dummy_cb},
                {"text": "Вариант ➡️", "callback": self._nav_gen_cb, "args": (sid, 1)},
            ])

        if total_text_pages > 1:
            kb.append([
                {"text": "📝 <", "callback": self._nav_text_cb, "args": (sid, -1)},
                {"text": f"Стр {text_page + 1}/{total_text_pages}", "callback": self._dummy_cb},
                {"text": "> 📝", "callback": self._nav_text_cb, "args": (sid, 1)},
            ])

        if show_prompt_button:
            kb.append([{
                "text": self.strings("btn_hide_prompt") if s.get("show_full_prompt") else self.strings("btn_show_prompt"),
                "callback": self._hide_full_prompt_cb if s.get("show_full_prompt") else self._show_full_prompt_cb,
                "args": (sid,),
            }])

        kb.append([
            {"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)},
            {"text": self.strings("btn_model"), "callback": self._model_menu, "args": (sid,)},
        ])

        if s.get("from_history"):
            kb.append([{"text": self.strings("btn_back_hist"), "callback": self._back_to_menu}])
        else:
            kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

        ok = await self._safe_edit_media(
            target,
            text_to_show,
            reply_markup=kb,
            video=media_url if media_type == "video" else None,
            photo=media_url if media_type != "video" else None,
        )
        if ok:
            s["pending_display"] = False
            return

        if s.get("pending_display"):
            logger.warning("failed to update generation view sid=%s, sending direct fallback result", sid)
            await self._send_result_to_origin(
                s,
                s.get("last_media_bytes"),
                ai_text,
                media_type=s.get("last_media_type", "image"),
                duration=s.get("last_media_duration"),
            )
            s["pending_display"] = False

    async def _nav_gen_cb(self, call: InlineCall, sid, direction):
        if sid not in self.sessions:
            return await call.answer("Сессия истекла")

        s = self.sessions[sid]
        new_index = s["index"] + direction

        if 0 <= new_index < len(s["images"]):
            s["index"] = new_index
            s["text_page"] = 0
            await self._update_gen_view(call, sid)
        else:
            await call.answer("Край")

    async def _nav_text_cb(self, call: InlineCall, sid, direction):
        if sid not in self.sessions:
            return await call.answer("Сессия истекла")

        s = self.sessions[sid]
        ai_text = s["images"][s["index"]].get("text", "")
        total = len(self._smart_split(ai_text, 800))
        new_page = s["text_page"] + direction

        if 0 <= new_page < total:
            s["text_page"] = new_page
            await self._update_gen_view(call, sid)
        else:
            await call.answer("Край текста")

    async def _model_menu(self, call: InlineCall, sid):
        if sid not in self.sessions:
            return await call.answer("Сессия истекла", show_alert=True)

        session = self.sessions[sid]
        provider = session.get("provider", "google")

        if provider == "grok":
            kb = [
                [{"text": "🎨 Grok Imagine", "callback": self._set_model_cb, "args": (sid, "grok-imagine-image")}],
                [{"text": "🎨 Grok 2 Image", "callback": self._set_model_cb, "args": (sid, "grok-2-image")}],
            ]
        elif provider == "grok_video":
            kb = [
                [{"text": "🎬 Grok Imagine Video", "callback": self._set_model_cb, "args": (sid, "grok-imagine-video")}],
            ]
        elif provider == "wavespeed_grok":
            is_edit_mode = bool(session.get("input_imgs"))
            kb = [[{
                "text": "🎨 Grok Imagine Edit (из конфига)" if is_edit_mode else "🎨 Grok Imagine T2I (из конфига)",
                "callback": self._dummy_cb,
            }]]
        elif provider == "wavespeed_grok_video":
            if session.get("input_video"):
                label = "🎬 Grok Imagine Video Edit (из конфига)"
            elif session.get("input_imgs"):
                label = "🎬 Grok Imagine Video I2V (из конфига)"
            else:
                label = "🎬 Grok Imagine Video T2V (из конфига)"
            kb = [[{"text": label, "callback": self._dummy_cb}]]
        elif provider == "wavespeed":
            kb = [[{"text": "Текущая (Wavespeed)", "callback": self._dummy_cb}]]
        elif provider == "wainsfw":
            kb = [[{"text": "Текущая (WaiNSFW)", "callback": self._dummy_cb}]]
        elif provider == "gpt_image":
            kb = [
                [{"text": "🖼 GPT Image 1", "callback": self._set_model_cb, "args": (sid, "gpt-image-1")}],
            ]
        else:
            kb = [
                [{"text": "🍌 Nano Banana Pro", "callback": self._set_model_cb, "args": (sid, "nano-banana-pro-preview")}],
                [{"text": "💎 Gemini 3 Pro", "callback": self._set_model_cb, "args": (sid, "gemini-3-pro-image-preview")}],
                [{"text": "⚡️ Gemini 3.1 Flash", "callback": self._set_model_cb, "args": (sid, "gemini-3.1-flash-image-preview")}],
                [{"text": "⚡️ Gemini 2.5 Flash", "callback": self._set_model_cb, "args": (sid, "gemini-2.5-flash-image")}],
            ]

        kb.append([{"text": "🔙 Назад", "callback": self._back_to_gen, "args": (sid,)}])
        await self._safe_edit(call, self._get_str("select_model"), reply_markup=kb)

    async def _set_model_cb(self, call: InlineCall, sid, model_name):
        if sid not in self.sessions:
            return await call.answer("Сессия истекла", show_alert=True)

        self.sessions[sid]["model"] = model_name
        await self._regen_cb(call, sid)

    async def _back_to_gen(self, call: InlineCall, sid):
        await self._update_gen_view(call, sid)

    async def _regen_cb(self, call: InlineCall, sid):
        if sid not in self.sessions:
            return await call.answer("Сессия истекла", show_alert=True)

        await self._stop_session_task(sid)

        s = self.sessions[sid]
        await call.answer(f"Генерация ({s['model']})...")

        negative_prompt = self._get_negative_prompt(s.get("request_options"))
        prompt_block = self._get_status_prompt_block(
            s["display_prompt"],
            s.get("enhanced_prompt"),
            negative_prompt=negative_prompt,
            short_limit=200,
        )
        model_str = self._get_model_str(s["model"])
        attach_str = self._get_attach_str(len(s.get("input_imgs", [])) + (1 if s.get("input_video") else 0))

        if s.get("provider") == "grok_video":
            mode = "video_edit" if s.get("input_video") else "image_to_video" if s.get("input_imgs") else "text_to_video"
            text = self._render_grok_video_status_text(prompt_block, model_str, attach_str, s, mode, progress=None)
            await self._safe_edit(call, text, reply_markup=self._get_loading_markup())
        elif s.get("provider") == "wavespeed_grok_video":
            mode = "video_edit" if s.get("input_video") else "image_to_video" if s.get("input_imgs") else "text_to_video"
            text = self._render_wavespeed_grok_video_status_text(prompt_block, model_str, attach_str, s, mode)
            await self._safe_edit(call, text, reply_markup=self._get_loading_markup())
        else:
            key = "edit_var" if (s.get("input_imgs") or s.get("input_video")) else "gen_var"
            await self._safe_edit(
                call,
                self._get_str(key, prompt_block, model_str, attach_str),
                reply_markup=self._get_loading_markup(),
            )

        self._spawn_managed_task(self._process_gen(call, sid), sid=sid, fresh_context=True)

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        self.url_cache.clear()
        await call.answer(self.strings("alert_cleared"), show_alert=True)
        await self._show_history_menu(call)

    async def _hist_show_prompt(self, call: InlineCall, display_index, text_page):
        history = self.db.get("ImageGen", "history", [])
        if not history:
            return await self._show_history_menu(call)

        display_index = max(0, min(display_index, len(history) - 1))
        real_index = self._hist_real_index(history, display_index)
        item = history[real_index]

        if not self._can_show_history_prompt_inline(item, display_index, text_page):
            return await self._hist_dl_prompt(call, item["id"])

        await self._render_history_slide(call, display_index, text_page, show_prompt=True)

    async def _hist_hide_prompt(self, call: InlineCall, display_index, text_page):
        await self._render_history_slide(call, display_index, text_page, show_prompt=False)

    async def _render_history_slide(self, call, display_index, text_page=0, show_prompt=False):
        history = self.db.get("ImageGen", "history", [])
        if not history:
            return await self._show_history_menu(call)

        display_index = max(0, min(display_index, len(history) - 1))
        real_index = self._hist_real_index(history, display_index)
        item = history[real_index]

        media_url = self.url_cache.get(item["id"])
        if not media_url and item.get("url"):
            media_url = item.get("url")
            self.url_cache[item["id"]] = media_url

        if not media_url and item.get("bytes"):
            await self._safe_edit(
                call,
                self._get_str("uploading"),
                reply_markup=self._get_loading_markup(),
            )
            try:
                raw_bytes = base64.b64decode(item["bytes"])
                if item.get("media_type") == "video":
                    media_url = await self._upload_video(raw_bytes)
                else:
                    media_url = await self._upload_image(raw_bytes)
                self.url_cache[item["id"]] = media_url
            except Exception:
                self._log_suppressed("failed to restore/upload history media from bytes")

        if not media_url and not item.get("bytes") and item.get("media_type", "image") != "video":
            media_url = "https://raw.githubusercontent.com/h-m-256/repository/refs/heads/main/media/empty.png"

        ai_text = item.get("text_resp", "")
        model = item.get("model", "Неизвестно")
        media_type = item.get("media_type", "image")
        duration = item.get("duration")
        negative_prompt = self._get_negative_prompt(item.get("request_options"))
        is_empty_img = self._is_empty_image(media_url)
        has_media = bool(media_url) and not is_empty_img

        prompt_exists = self._has_prompt(item.get("prompt", ""), item.get("enhanced_prompt"), negative_prompt)
        prompt_block = self._build_prompt_block(
            item.get("prompt", ""),
            item.get("enhanced_prompt"),
            negative_prompt=negative_prompt,
            show_full=show_prompt,
            short_limit=200,
        )

        show_prompt_button = prompt_exists and (
            self._is_prompt_long(item.get("prompt", ""), item.get("enhanced_prompt"), negative_prompt, short_limit=200)
            or show_prompt
        )

        text_chunks = self._smart_split(ai_text, 800)
        total_text = len(text_chunks)
        if text_page >= total_text:
            text_page = max(0, total_text - 1)
        curr_text = text_chunks[text_page] if text_chunks else ""

        model_str = self._get_model_str(model)

        if media_type == "video":
            if ai_text:
                key = "history_video_item_text"
                args = [
                    display_index + 1,
                    len(history),
                    model_str,
                    prompt_block,
                    self._format_duration(duration),
                    text_page + 1,
                    total_text,
                    utils.escape_html(curr_text.strip()),
                ]
            else:
                key = "history_video_item"
                args = [display_index + 1, len(history), model_str, prompt_block, self._format_duration(duration)]
        else:
            if ai_text:
                key = "history_item_text" if has_media else "history_text_only"
                args = [
                    display_index + 1,
                    len(history),
                    model_str,
                    prompt_block,
                    text_page + 1,
                    total_text,
                    utils.escape_html(curr_text.strip()),
                ]
            else:
                key = "history_item"
                args = [display_index + 1, len(history), model_str, prompt_block]

        kb = []

        if len(history) > 1:
            nav = []
            if display_index > 0:
                nav.append({"text": "⬅️", "callback": self._hist_nav, "args": (display_index - 1,)})
            nav.append({"text": f"{display_index + 1}/{len(history)}", "callback": self._dummy_cb})
            if display_index < len(history) - 1:
                nav.append({"text": "➡️", "callback": self._hist_nav, "args": (display_index + 1,)})
            kb.append(nav)

        if total_text > 1:
            kb.append([
                {"text": "📝 <", "callback": self._hist_nav_text, "args": (display_index, -1, text_page, show_prompt)},
                {"text": f"Стр {text_page + 1}/{total_text}", "callback": self._dummy_cb},
                {"text": "> 📝", "callback": self._hist_nav_text, "args": (display_index, 1, text_page, show_prompt)},
            ])

        if show_prompt_button:
            kb.append([{
                "text": self.strings("btn_hide_prompt") if show_prompt else self.strings("btn_show_prompt"),
                "callback": self._hist_hide_prompt if show_prompt else self._hist_show_prompt,
                "args": (display_index, text_page),
            }])

        kb.append([
            {"text": self.strings("btn_del_one"), "callback": self._del_one_cb, "args": (item["id"],)},
            {"text": self.strings("btn_regen"), "callback": self._regen_from_hist, "args": (item["id"],)},
            {"text": self.strings("btn_list"), "callback": self._back_to_menu},
        ])
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

        await self._safe_edit_media(
            call,
            self._get_str(key, *args),
            reply_markup=kb,
            video=media_url if media_type == "video" else None,
            photo=media_url if media_type != "video" else None,
        )

    async def _show_history_page_picker(self, target, current_page=0):
        history = self.db.get("ImageGen", "history", [])
        if not history:
            return await self._show_history_menu(target)

        limit = 5
        total_pages = (len(history) + limit - 1) // limit
        current_page = max(0, min(current_page, total_pages - 1))

        kb = []
        row = []

        for page in range(total_pages):
            if page == current_page:
                row.append({"text": f"·{page + 1}·", "callback": self._dummy_cb})
            else:
                row.append({"text": str(page + 1), "callback": self._menu_nav_cb, "args": (page,)})

            if len(row) >= 5:
                kb.append(row)
                row = []

        if row:
            kb.append(row)

        kb.append([
            {"text": self.strings("btn_back"), "callback": self._menu_nav_cb, "args": (current_page,)},
            {"text": self.strings("btn_close"), "callback": self._safe_close},
        ])

        await self._safe_edit_media(
            target,
            self._get_str("select_page"),
            reply_markup=kb,
            photo="https://raw.githubusercontent.com/h-m-256/repository/refs/heads/main/media/list_mode.png",
        )

    async def _show_history_menu(self, target, page=0):
        history = self.db.get("ImageGen", "history", [])
        text = self._get_str("history_empty") if not history else "<b>📝 История генераций:</b>"

        hint_message = getattr(target, "message", None) or target

        if not self.config["history"]:
            text += self._history_disabled_warn_text(hint_message)

        kb = []
        if history:
            limit = 5
            rev = list(reversed(history))
            total_pages = (len(rev) + limit - 1) // limit

            if page < 0:
                page = 0
            if page >= total_pages:
                page = max(0, total_pages - 1)

            chunk = rev[page * limit:(page + 1) * limit]

            for pos, entry in enumerate(chunk, start=page * limit + 1):
                media_type = entry.get("media_type", "image")
                icon = "🎬" if media_type == "video" else "🖼"
                if not entry.get("bytes") and not entry.get("url"):
                    icon = "📝"
                elif entry.get("is_edit"):
                    icon = "🎞" if media_type == "video" else "✏️"

                prompt_preview = entry.get("prompt", "...")[:20] + ".."
                btn_text = f"{icon} {prompt_preview}"

                kb.append([{
                    "text": btn_text,
                    "callback": self._view_hist_item,
                    "args": (entry["id"],),
                }])

            nav = []
            if page > 0:
                nav.append({"text": "⬅️", "callback": self._menu_nav_cb, "args": (page - 1,)})
            if total_pages > 1:
                nav.append({"text": f"{page + 1}/{total_pages}", "callback": self._menu_pages_cb, "args": (page,)})
            if page < total_pages - 1:
                nav.append({"text": "➡️", "callback": self._menu_nav_cb, "args": (page + 1,)})
            if nav:
                kb.append(nav)

            kb.append([{"text": self.strings("btn_slideshow"), "callback": self._start_slideshow}])
            kb.append([{"text": self.strings("btn_clear"), "callback": self._clear_all_cb}])

        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

        await self._safe_edit_media(
            target,
            text,
            reply_markup=kb,
            photo="https://raw.githubusercontent.com/h-m-256/repository/refs/heads/main/media/list_mode.png",
        )

    async def _menu_nav_cb(self, call: InlineCall, page):
        await self._show_history_menu(call, page)

    async def _menu_pages_cb(self, call: InlineCall, current_page):
        await self._show_history_page_picker(call, current_page)

    async def _start_slideshow(self, call: InlineCall):
        await self._render_history_slide(call, 0)

    async def _view_hist_item(self, call: InlineCall, item_id):
        history = self.db.get("ImageGen", "history", [])
        idx = next((i for i, x in enumerate(history) if x["id"] == item_id), -1)
        if idx == -1:
            return await call.answer("Не найдено")

        display_index = self._hist_display_index(history, idx)
        await self._render_history_slide(call, display_index)

    async def _hist_nav_text(self, call: InlineCall, display_index, d, p, show_prompt=False):
        await self._render_history_slide(call, display_index, p + d, show_prompt)

    async def _hist_nav(self, call: InlineCall, display_index):
        await self._render_history_slide(call, display_index)

    async def _back_to_menu(self, call: InlineCall):
        await self._show_history_menu(call)

    async def _del_one_cb(self, call: InlineCall, item_id):
        history = self.db.get("ImageGen", "history", [])
        idx = next((i for i, x in enumerate(history) if x["id"] == item_id), -1)
        if idx == -1:
            return await call.answer("Не найдено")

        display_index = self._hist_display_index(history, idx)

        history.pop(idx)
        self.db.set("ImageGen", "history", history)

        if item_id in self.url_cache:
            del self.url_cache[item_id]

        await call.answer("Удалено!")

        if not history:
            await self._show_history_menu(call)
        else:
            new_display_index = min(display_index, len(history) - 1)
            await self._render_history_slide(call, new_display_index)

    async def _regen_from_hist(self, call: InlineCall, item_id):
        history = self.db.get("ImageGen", "history", [])
        item = next((x for x in history if x["id"] == item_id), None)
        if not item:
            return await call.answer("Не найдено")

        provider = item.get("provider", "google")

        if provider == "wavespeed":
            model = item.get("model", self.config["wavespeed_model_i2i"] if item.get("is_edit") else self.config["wavespeed_model_t2i"])
        elif provider == "wavespeed_grok":
            model = item.get(
                "model",
                self.config["wavespeed_grok_edit_model"] if item.get("is_edit") else self.config["wavespeed_grok_t2i_model"],
            )
        elif provider == "wavespeed_grok_video":
            model = item.get(
                "model",
                self.config["wavespeed_grok_video_edit_model"] if item.get("is_edit") else self.config["wavespeed_grok_video_t2v_model"],
            )
        elif provider == "wainsfw":
            model = "WaiNSFW"
        elif provider == "gpt_image":
            model = item.get("model", self.config["model_gpt_image"])
        elif provider == "grok_video":
            model = item.get("model", self.config["model_grok_video"])
        else:
            model = item.get("model", self.config["model_google"] if provider == "google" else self.config["model_grok"])

        prompt = item.get("prompt", "")
        enhanced_prompt = item.get("enhanced_prompt")
        api_prompt = item.get("api_prompt") or enhanced_prompt or prompt

        sid = str(uuid.uuid4())
        self.sessions[sid] = {
            "sid": sid,
            "api_prompt": api_prompt,
            "display_prompt": prompt,
            "enhanced_prompt": enhanced_prompt,
            "images": [],
            "index": -1,
            "input_imgs": [],
            "input_video": None,
            "from_history": True,
            "model": model,
            "request_options": item.get("request_options", {}),
            "text_page": 0,
            "provider": provider,
            "cancel": False,
            "show_full_prompt": False,
            "task": None,
            "direct_result": False,
            "origin_chat_id": getattr(getattr(call, "message", None), "chat_id", None),
            "origin_reply_to": getattr(getattr(call, "message", None), "reply_to_msg_id", None),
            "origin_message": getattr(call, "message", None),
            "last_media_bytes": None,
            "last_media_type": None,
            "last_media_duration": None,
            "pending_display": False,
        }

        await self._regen_cb(call, sid)

    async def _dl_error(self, call: InlineCall, err_id):
        if err_id not in self.error_cache:
            return await call.answer("Ошибка устарела", show_alert=True)

        content = self.error_cache[err_id]
        f = io.BytesIO(content.encode("utf-8"))
        f.name = "error.txt"

        try:
            chat_id = None
            if hasattr(call, "form") and call.form.get("message"):
                chat_id = call.form["message"].chat_id
            if not chat_id:
                chat_id = getattr(getattr(call, "message", None), "chat_id", None)
            if not chat_id:
                chat_id = getattr(call, "sender_id", None)

            await self._client.send_file(chat_id, f, caption=self._get_str("log_caption"))
            await call.answer("Отправлено!")
        except Exception as e:
            logger.exception("failed to send error log file")
            await call.answer(f"Ошибка отправки файла: {e}", show_alert=True)

    async def _dummy_cb(self, call: InlineCall):
        await call.answer()

    async def _safe_close(self, call: InlineCall):
        try:
            await call.delete()
        except Exception:
            logger.exception("failed to close/delete message")
            try:
                await call.answer("Ошибка")
            except Exception:
                logger.exception("failed to answer after close error")
