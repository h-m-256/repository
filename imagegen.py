# meta developer: @h_m_256

import aiohttp
import base64
import uuid
import logging
from .. import loader, utils
from telethon.tl.types import Message
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

@loader.tds
class ImageGenMod(loader.Module):
    """AI Image Generation (Stable Inline Version with URL Bypass)"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use for generation",
        "generating": "⌛ <b>Генерирую новый вариант...</b>\n<i>{}</i>",
        "uploading": "📤 <b>Загружаю изображение...</b>",
        "error": "❌ <b>Ошибка:</b> <code>{}</code>",
        "success": "✅ <b>Готово!</b>\n<i>{}</i>",
        "history_empty": "❌ История пуста!",
        "history_cleared": "✅ История очищена!",
        "history_item": "🖼 <b>Просмотр из истории</b>\n<i>{}</i>",
        "no_api": "❌ <b>Не установлен API ключ!</b>\nВведи команду конфигурации или установи его в конфиге.",
        "btn_regen": "🔄 Перегенерировать",
        "btn_back": "🔙 Назад",
        "btn_clear": "🗑 Очистить всё",
        "btn_close": "❌ Закрыть",
        "session_expired": "❌ <b>Сессия истекла</b>\nБот был перезагружен, эта кнопка больше не работает."
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model", "nano-banana-pro-preview", lambda: self.strings("model")),
        )

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

    async def _upload_to_catbox(self, img_bytes):
        """Uploads bytes to catbox and returns URL to bypass InputFile core crash"""
        try:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('fileToUpload', img_bytes, filename='image.png', content_type='image/png')

            async with aiohttp.ClientSession() as session:
                async with session.post('https://catbox.moe/user/api.php', data=data) as resp:
                    if resp.status != 200:
                        logger.error(f"Catbox upload failed: {resp.status}")
                        return None
                    return await resp.text()
        except Exception as e:
            logger.exception("Catbox upload error")
            return None

    async def _call_api(self, prompt: str):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['model']}:generateContent?key={self.config['api_key']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"candidateCount": 1, "temperature": 1.0}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    try:
                        err = await resp.json()
                        return {"error": err.get("error", {}).get("message", f"HTTP {resp.status}")}
                    except:
                        return {"error": f"HTTP Error {resp.status}"}
                return await resp.json()

    @loader.command(ru_doc="<промпт> - Сгенерировать изображение")
    async def ig(self, message: Message):
        """Generate image"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "Введите промпт")
        if not self.config["api_key"]:
            return await utils.answer(message, self.strings("no_api"))

        safe_args = utils.escape_html(args)

        # Начинаем с формы. Если бот перезагрузится, эта форма перестанет отвечать на кнопки,
        # но это неизбежно для RAM-хранилища.
        msg = await self.inline.form(
            text=self.strings("generating").format(safe_args),
            message=message
        )

        await self._process_gen(msg, args)

    async def _process_gen(self, target, prompt):
        try:
            # 1. Запрос к AI
            data = await self._call_api(prompt)

            if not data or "error" in data:
                raise ValueError(data.get("error", "Unknown API Error") if data else "Empty response")

            try:
                img_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            except (KeyError, IndexError):
                raise ValueError("Модель не вернула изображение (возможно, Safety Filter).")

            img_bytes = base64.b64decode(img_b64)

            # 2. Сохранение в историю (храним base64 для быстродействия истории)
            sid = str(uuid.uuid4())
            history = self.db.get("ImageGen", "history", [])
            history.append({"id": sid, "prompt": prompt, "bytes": img_b64})
            self.db.set("ImageGen", "history", history[-10:])

            # 3. Обход сломанного ядра: Загрузка на Catbox
            # Мы обновляем сообщение, чтобы юзер видел прогресс
            try:
                await target.edit(self.strings("uploading"))
            except:
                pass # Игнорируем, если не удалось обновить текст (не критично)

            img_url = await self._upload_to_catbox(img_bytes)

            if not img_url:
                # Фолбэк (на всякий случай, если кэтбокс лежит): пробуем просто текст
                raise ValueError("Ошибка загрузки изображения на сервер.")

            # 4. Вывод результата
            kb = [[{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (prompt,)}],
                  [{"text": self.strings("btn_close"), "action": "close"}]]

            safe_prompt = utils.escape_html(prompt)

            # Передаем URL в photo. Ядро увидит строку и не будет пытаться делать InputFile(io.BytesIO)
            status = await target.edit(
                text=self.strings("success").format(safe_prompt),
                photo=img_url,
                reply_markup=kb
            )

            if not status:
                # Если edit вернул False (тихая ошибка ядра)
                await target.edit(
                    text=f"{self.strings('success').format(safe_prompt)}\n\n⚠️ <b>Не удалось загрузить превью (ошибка ядра), но вот ссылка:</b> {img_url}",
                    reply_markup=kb
                )

        except Exception as e:
            logger.exception("ImageGen Process Error")
            error_text = utils.escape_html(str(e)[:200])
            # Восстанавливаем кнопки, чтобы интерфейс не завис
            kb = [[{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (prompt,)}],
                  [{"text": self.strings("btn_close"), "action": "close"}]]

            await target.edit(
                text=self.strings("error").format(error_text),
                reply_markup=kb
            )

    @loader.command(ru_doc=" - История генераций")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        if not history:
            return await utils.answer(message, self.strings("history_empty"))

        await self._show_history_menu(message, history)

    async def _show_history_menu(self, call_or_msg, history):
        kb = []
        for e in reversed(history):
            prompt_preview = (e['prompt'][:25] + '..') if len(e['prompt']) > 25 else e['prompt']
            kb.append([{"text": f"🖼 {utils.escape_html(prompt_preview)}", "callback": self._hist_cb, "args": (e['id'],)}])

        kb.append([{"text": self.strings("btn_clear"), "callback": self._clear_all_cb}])
        kb.append([{"text": self.strings("btn_close"), "action": "close"}])

        text = "<b>📝 История генераций:</b>"

        if isinstance(call_or_msg, Message):
            await self.inline.form(text, message=call_or_msg, reply_markup=kb)
        else:
            # Это InlineCall
            # Важно: если мы переходим от фото к тексту, edit может сбоить в некоторых ядрах.
            # Попробуем передать photo=None явно, если ядро это поддерживает, или просто text.
            await call_or_msg.edit(text, reply_markup=kb, photo="")

    async def _regen_cb(self, call: InlineCall, prompt):
        # Проверяем, жива ли сессия (обычно да, раз колбэк сработал)
        safe_prompt = utils.escape_html(prompt)
        await call.answer("Генерирую...")
        await call.edit(self.strings("generating").format(safe_prompt), reply_markup=[])
        await self._process_gen(call, prompt)

    async def _hist_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        sess = next((i for i in history if i["id"] == sid), None)

        if not sess:
            return await call.answer("Запись устарела", show_alert=True)

        await call.answer("Загружаю...")

        try:
            # Загружаем картинку заново на кэтбокс, так как в базе храним только base64
            # (ссылки кэтбокса вечные, но мы их не храним, чтобы базу не путать, хотя можно было бы)
            img_bytes = base64.b64decode(sess["bytes"])
            img_url = await self._upload_to_catbox(img_bytes)

            if not img_url:
                 return await call.answer("Ошибка загрузки изображения", show_alert=True)

            safe_prompt = utils.escape_html(sess['prompt'])

            kb = [
                [{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sess['prompt'],)}],
                [{"text": self.strings("btn_back"), "callback": self._back_to_hist_cb}],
                [{"text": self.strings("btn_close"), "action": "close"}]
            ]

            await call.edit(
                text=self.strings("history_item").format(safe_prompt),
                photo=img_url,
                reply_markup=kb
            )
        except Exception as e:
            logger.exception("History load error")
            await call.answer(f"Error: {e}", show_alert=True)

    async def _back_to_hist_cb(self, call: InlineCall):
        history = self.db.get("ImageGen", "history", [])
        if not history:
             return await call.edit(self.strings("history_empty"), reply_markup=[[{"text": "Close", "action": "close"}]])
        await self._show_history_menu(call, history)

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        await call.edit(self.strings("history_cleared"), reply_markup=[[{"text": self.strings("btn_close"), "action": "close"}]])
