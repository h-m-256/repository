#meta developer: @h_m_256
# 🔑 Copyright geymini 3 flash/pro

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
    """AI Image Gen with Aspect Ratios (Stable Build)"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use for generation",
        "no_api": "❌ API ключ не настроен!",
        "generating": "⌛ <b>Генерирую...</b>\nРазмер: {aspect}\n<i>{prompt}</i>",
        "error": "❌ <b>Ошибка:</b> <code>{}</code>",
        "success": "✅ <b>Готово!</b>\nРазмер: {aspect}\n<i>{prompt}</i>",
        "history_empty": "❌ История пуста!",
        "history_cleared": "✅ История очищена!",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model", "nano-banana-pro-preview", lambda: self.strings("model")),
        )

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

    async def _call_api(self, prompt: str, aspect: str = "1:1"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['model']}:generateContent?key={self.config['api_key']}"
        
        ratio_map = {"1:1": "square 1:1", "16:9": "cinematic 16:9", "9:16": "vertical 9:16"}
        full_prompt = f"Aspect ratio {ratio_map.get(aspect, '1:1')}. {prompt}"
        
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {"candidateCount": 1, "temperature": 1.0}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ValueError(f"API Error {resp.status}")
                return await resp.json()

    @loader.command(ru_doc=" > Сгенерировать изображение")
    async def ig(self, message: Message):
        """Generate image with aspect ratio selection"""
        args = utils.get_args_raw(message)
        if not args: return await utils.answer(message, "Введите промпт")
        if not self.config["api_key"]: return await utils.answer(message, self.strings("no_api"))
        
        # Запускаем стандартную генерацию
        await self._process_gen(message, args, "1:1")

    async def _process_gen(self, message, prompt, aspect, call=None):
        status_text = self.strings("generating").format(prompt=prompt, aspect=aspect)
        
        if not call:
            status = await utils.answer(message, status_text)
        else:
            await call.edit(status_text)
            status = call

        try:
            data = await self._call_api(prompt, aspect)
            img_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            img_bytes = base64.b64decode(img_b64)
            
            sid = str(uuid.uuid4())
            history = self.db.get("ImageGen", "history", [])
            history.append({"id": sid, "prompt": prompt, "bytes": img_b64, "aspect": aspect})
            self.db.set("ImageGen", "history", history[-10:])

            file = io.BytesIO(img_bytes)
            file.name = "ai.png"

            # Создаем кнопки напрямую через Telethon формат для send_file
            buttons = [
                [
                    self._client.build_reply_markup([
                        {"text": "1:1", "callback": self._regen_cb, "args": (prompt, "1:1")},
                        {"text": "16:9", "callback": self._regen_cb, "args": (prompt, "16:9")},
                        {"text": "9:16", "callback": self._regen_cb, "args": (prompt, "9:16")}
                    ])
                ]
            ]
            
            # В Hikka/Heroku лучше использовать такой метод формирования кнопок для send_file:
            markup = self._client.build_reply_markup([
                [
                    {"text": "🔄 1:1", "callback": self._regen_cb, "args": (prompt, "1:1")},
                    {"text": "🔄 16:9", "callback": self._regen_cb, "args": (prompt, "16:9")},
                    {"text": "🔄 9:16", "callback": self._regen_cb, "args": (prompt, "9:16")}
                ]
            ])

            chat_id = utils.get_chat_id(message)
            await self._client.send_file(
                chat_id, 
                file, 
                caption=self.strings("success").format(prompt=prompt, aspect=aspect),
                buttons=markup
            )
            
            if not call: await status.delete()
            else: await call.delete()

        except Exception as e:
            await utils.answer(status, self.strings("error").format(str(e)))

    @loader.command(ru_doc=" > История")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        if not history: return await utils.answer(message, self.strings("history_empty"))
        
        kb = []
        for e in reversed(history):
            # БЕЗОПАСНОЕ получение аспекта для старой истории
            asp = e.get("aspect", "1:1")
            kb.append([{"text": f"🖼 {e['prompt'][:25]} ({asp})", "callback": self._hist_cb, "args": (e['id'],)}])
        
        kb.append([{"text": "🧹 Очистить историю", "callback": self._clear_all_cb}])
        await self.inline.form("<b>📝 История генераций:</b>", message=message, reply_markup=kb)

    async def _regen_cb(self, call: InlineCall, prompt, aspect):
        await call.answer(f"Меняю формат на {aspect}...")
        # Передаем call.original_call.message как объект сообщения
        await self._process_gen(call.original_call.message, prompt, aspect, call=call)

    async def _hist_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        sess = next((i for i in history if i["id"] == sid), None)
        
        if not sess:
            return await call.answer("Не найдено", show_alert=True)

        await call.answer("Отправляю...")
        
        file = io.BytesIO(base64.b64decode(sess["bytes"]))
        file.name = "hist.png"
        
        chat_id = utils.get_chat_id(call.original_call.message)
        asp = sess.get("aspect", "1:1")

        await self._client.send_file(
            chat_id, 
            file, 
            caption=f"📜 <b>Из истории</b>\nПромпт: <i>{sess['prompt']}</i>\nРазмер: {asp}"
        )

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        await call.edit(self.strings("history_cleared"), reply_markup=[])
