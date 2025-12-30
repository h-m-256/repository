# meta developer: @h_m_256

import aiohttp
import base64
import uuid
from aiogram.types import BufferedInputFile
from .. import loader, utils
from telethon.tl.types import Message
from ..inline.types import InlineCall

@loader.tds
class ImageGenMod(loader.Module):
    """AI Image Generation (Stable Inline Version)"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use for generation",
        "generating": "⌛ <b>Генерирую новый вариант...</b>\n<i>{}</i>",
        "error": "❌ <b>Ошибка:</b> <code>{}</code>",
        "success": "✅ <b>Готово!</b>\n<i>{}</i>",
        "history_empty": "❌ История пуста!",
        "history_cleared": "✅ История очищена!",
        "history_item": "🖼 <b>Просмотр из истории</b>\n<i>{}</i>",
        "no_api": "❌ <b>Не установлен API ключ!</b>\nВведи команду конфигурации или установи его в конфиге."
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model", "nano-banana-pro-preview", lambda: self.strings("model")),
        )

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

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
        """Generate image with stable regenerate button"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "Введите промпт")
        if not self.config["api_key"]:
            return await utils.answer(message, self.strings("no_api"))
        
        # Экранируем HTML в промпте, чтобы не сломать разметку сообщения
        safe_args = utils.escape_html(args)

        # Создаем форму ожидания
        msg = await self.inline.form(
            text=self.strings("generating").format(safe_args),
            message=message
        )
        
        # Запускаем процесс генерации
        await self._process_gen(msg, args)

    async def _process_gen(self, target, prompt):
        """
        target: InlineMessage (от inline.form) или InlineCall (от кнопки)
        prompt: сырой текст запроса
        """
        try:
            data = await self._call_api(prompt)
            
            if not data:
                raise ValueError("Empty response from API")
            
            if "error" in data:
                raise ValueError(data["error"])

            # Проверяем структуру ответа (Google Gemini Vision/Imagen format)
            try:
                img_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            except (KeyError, IndexError):
                raise ValueError("API не вернуло изображение. Возможно, модель не поддерживает генерацию или сработал Safety Filter.")

            img_bytes = base64.b64decode(img_b64)
            
            # Сохраняем в историю
            sid = str(uuid.uuid4())
            history = self.db.get("ImageGen", "history", [])
            # Сохраняем только последние 10 записей
            history.append({"id": sid, "prompt": prompt, "bytes": img_b64})
            self.db.set("ImageGen", "history", history[-10:])

            # Формируем объект файла для Aiogram 3.x
            # Это ключевой момент, который исправляет ошибку 'Abstract InputFile'
            photo_file = BufferedInputFile(img_bytes, filename=f"{sid}.png")

            # Кнопки
            kb = [[{"text": "🔄 Перегенерировать", "callback": self._regen_cb, "args": (prompt,)}]]

            safe_prompt = utils.escape_html(prompt)
            
            # Редактируем сообщение
            await target.edit(
                text=self.strings("success").format(safe_prompt),
                photo=photo_file,
                reply_markup=kb
            )

        except Exception as e:
            # Если произошла ошибка, выводим её в инлайн окне
            error_text = utils.escape_html(str(e)[:200])
            await target.edit(
                text=self.strings("error").format(error_text),
                reply_markup=[[{"text": "🔙 Закрыть", "action": "close"}]]
            )

    @loader.command(ru_doc=" - История генераций")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        if not history:
            return await utils.answer(message, self.strings("history_empty"))
        
        kb = []
        for e in reversed(history):
            # Обрезаем длинные промпты для красивой кнопки
            prompt_preview = (e['prompt'][:25] + '..') if len(e['prompt']) > 25 else e['prompt']
            kb.append([{"text": f"🖼 {prompt_preview}", "callback": self._hist_cb, "args": (e['id'],)}])
        
        kb.append([{"text": "🗑 Очистить всё", "callback": self._clear_all_cb}])
        kb.append([{"text": "❌ Закрыть", "action": "close"}])
        
        await self.inline.form("<b>📝 История генераций:</b>", message=message, reply_markup=kb)

    async def _regen_cb(self, call: InlineCall, prompt):
        safe_prompt = utils.escape_html(prompt)
        # Уведомление внизу экрана
        await call.answer("Генерирую новый вариант...")
        # Меняем текст и убираем кнопки, чтобы не жали повторно
        await call.edit(self.strings("generating").format(safe_prompt), reply_markup=[])
        await self._process_gen(call, prompt)

    async def _hist_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        sess = next((i for i in history if i["id"] == sid), None)
        
        if not sess:
            return await call.answer("Запись устарела или удалена", show_alert=True)

        await call.answer("Загружаю...")
        
        try:
            img_bytes = base64.b64decode(sess["bytes"])
            # Используем BufferedInputFile для фикса ошибки ядра
            photo_file = BufferedInputFile(img_bytes, filename=f"{sid}.png")
            
            safe_prompt = utils.escape_html(sess['prompt'])
            
            kb = [
                [{"text": "🔄 Перегенерировать", "callback": self._regen_cb, "args": (sess['prompt'],)}],
                [{"text": "🔙 К списку", "callback": self._back_to_hist_cb}]
            ]
            
            await call.edit(
                text=self.strings("history_item").format(safe_prompt),
                photo=photo_file,
                reply_markup=kb
            )
        except Exception as e:
            await call.answer(f"Ошибка загрузки: {e}", show_alert=True)

    async def _back_to_hist_cb(self, call: InlineCall):
        # Возвращает меню истории (без картинки, только текст)
        history = self.db.get("ImageGen", "history", [])
        if not history:
             return await call.edit(self.strings("history_empty"), reply_markup=[[{"text": "Close", "action": "close"}]])

        kb = []
        for e in reversed(history):
            prompt_preview = (e['prompt'][:25] + '..') if len(e['prompt']) > 25 else e['prompt']
            kb.append([{"text": f"🖼 {prompt_preview}", "callback": self._hist_cb, "args": (e['id'],)}])
        
        kb.append([{"text": "🗑 Очистить всё", "callback": self._clear_all_cb}])
        kb.append([{"text": "❌ Закрыть", "action": "close"}])

        # При переходе от фото к тексту, photo=None не уберет фото в edit, 
        # но edit_message_text (который вызывается внутри ядра при отсутствии media) это сделает.
        # Однако ядро hikka может капризничать при смене типа медиа -> текст. 
        # Если это не сработает, нужно переоткрывать форму, но попробуем так:
        await call.edit("<b>📝 История генераций:</b>", reply_markup=kb)

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        await call.edit(self.strings("history_cleared"), reply_markup=[[{"text": "Закрыть", "action": "close"}]])
