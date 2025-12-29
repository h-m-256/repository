#meta developer: @h_m_256
#вайбкод лень edition

import asyncio
import aiohttp
import io
import base64
import json
import uuid
from .. import loader, utils
from telethon.tl.types import Message
from ..inline.types import InlineCall

@loader.tds
class ImageGenMod(loader.Module):
    """AI Image Generation with History (Fixed for Heroku)"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use for generation",
        "no_api": "<b>❌ API key not configured!</b>",
        "generating": "<b>⏳ Generating image...</b>\n\n<i>Prompt: {}</i>",
        "error": "<b>❌ Error:</b>\n<code>{}</code>",
        "success": "<b>✅ Image generated!</b>\n\n<i>Prompt: {}</i>",
        "history_empty": "<b>❌ History is empty!</b>",
        "history_cleared": "<b>✅ History has been cleared!</b>",
        "history_title": "<b>📝 Generation History:</b>",
    }
    
    strings_ru = {
        "api_key": "API ключ Google AI Studio",
        "model": "Модель для генерации",
        "no_api": "<b>❌ API ключ не настроен!</b>",
        "generating": "<b>⏳ Генерирую изображение...</b>\n\n<i>Промпт: {}</i>",
        "error": "<b>❌ Ошибка:</b>\n<code>{}</code>",
        "success": "<b>✅ Изображение готово!</b>\n\n<i>Промпт: {}</i>",
        "history_empty": "<b>❌ История пуста!</b>",
        "history_cleared": "<b>✅ История очищена!</b>",
        "history_title": "<b>📝 История генераций:</b>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model", "gemini-2.5-flash-image", lambda: self.strings("model"), 
                validator=loader.validators.Choice(["gemini-2.5-flash-image", "imagen-4.0-generate-001", "imagen-4.0-ultra-generate-001"])),
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
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if resp.status != 200: raise ValueError(json.dumps(data, indent=2))
                return data

    @loader.command(ru_doc=" > Сгенерировать изображение")
    async def ig(self, message: Message):
        """Generate image"""
        args = utils.get_args_raw(message)
        if not args: return await utils.answer(message, "Provide a prompt")
        if not self.config["api_key"]: return await utils.answer(message, self.strings("no_api"))

        status_msg = await utils.answer(message, self.strings("generating").format(args))
        try:
            data = await self._call_api(args)
            sid = str(uuid.uuid4())
            
            # Сохраняем в историю
            history = self.db.get("ImageGen", "history", [])
            history.append({"id": sid, "prompt": args, "data": data})
            self.db.set("ImageGen", "history", history[-15:])
            
            await self._render(message, sid, status_msg)
        except Exception as e:
            await utils.answer(status_msg, self.strings("error").format(str(e)[:500]))

    @loader.command(ru_doc=" > История генераций")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        if not history: return await utils.answer(message, self.strings("history_empty"))
        
        kb = [[{"text": f"🖼 {e['prompt'][:25]}...", "callback": self._hist_cb, "args": (e['id'],)}] for e in reversed(history)]
        kb.append([{"text": "🧹 Очистить историю", "callback": self._clear_all_cb}])
        
        await self.inline.form(self.strings("history_title"), message=message, reply_markup=kb)

    async def _render(self, message, sid, status_msg=None):
        history = self.db.get("ImageGen", "history", [])
        sess = next((i for i in history if i["id"] == sid), None)
        if not sess: return

        try:
            # Извлекаем данные изображения
            img_b64 = sess["data"]["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            img_bytes = base64.b64decode(img_b64)
            
            # Чтобы избежать ошибки Heroku с BytesIO, отправляем через обычный client.send_file
            # и прикрепляем инлайн-кнопки через form
            kb = [[{"text": "🗑 Удалить", "callback": self._del_cb, "args": (sid,)}]]
            caption = self.strings("success").format(sess["prompt"])

            if status_msg: await status_msg.delete()

            # Используем нативный метод отправки с поддержкой инлайна
            await self.inline.form(
                text=caption,
                message=message,
                file=img_bytes, # Hikka сама сконвертирует это правильно
                reply_markup=kb
            )
        except Exception as e:
            await utils.answer(message, self.strings("error").format("Safety block or API error"))

    async def _hist_cb(self, call: InlineCall, sid):
        await self._render(call.message, sid)

    async def _del_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        self.db.set("ImageGen", "history", [i for i in history if i["id"] != sid])
        await call.delete()

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        # Исправлено: пишем "Очищено", а не просто "История пуста"
        await call.edit(self.strings("history_cleared"))
