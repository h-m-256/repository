#meta developer: @h_m_256

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
    """AI Image Generation with History & Regenerate"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use for generation",
        "generating": "⌛ <b>Генерирую...</b>\n<i>{}</i>",
        "error": "❌ <b>Ошибка:</b> <code>{}</code>",
        "success": "✅ <b>Готово!</b>\n<i>{}</i>",
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

    async def _call_api(self, prompt: str):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['model']}:generateContent?key={self.config['api_key']}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
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
        """Generate image with regenerate button"""
        args = utils.get_args_raw(message)
        if not args: return await utils.answer(message, "Введите промпт")
        if not self.config["api_key"]: return await utils.answer(message, "Настрой API ключ!")
        
        await self._process_gen(message, args)

    async def _process_gen(self, message, prompt, call=None):
        if call:
            await call.answer("Генерирую новый вариант...")
            # Чтобы не было бесконечных часиков, редактируем сообщение
            await call.edit(self.strings("generating").format(prompt))
        else:
            status = await utils.answer(message, self.strings("generating").format(prompt))

        try:
            data = await self._call_api(prompt)
            img_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            img_bytes = base64.b64decode(img_b64)
            
            sid = str(uuid.uuid4())
            history = self.db.get("ImageGen", "history", [])
            history.append({"id": sid, "prompt": prompt, "bytes": img_b64})
            self.db.set("ImageGen", "history", history[-10:])

            file = io.BytesIO(img_bytes)
            file.name = "ai.png"

            # Кнопка для перегенерации
            kb = [[{"text": "🔄 Перегенерировать", "callback": self._regen_cb, "args": (prompt,)}]]

            # Отправляем через встроенный метод Hikka, который умеет и в фото, и в кнопки
            chat_id = message.chat_id if not call else call.message.chat.id
            
            await self._client.send_file(
                chat_id,
                file,
                caption=self.strings("success").format(prompt),
                buttons=self.inline.generate_markup(kb) if hasattr(self.inline, "generate_markup") else kb
            )
            
            # Удаляем старое текстовое сообщение "Генерирую..."
            if not call: await status.delete()
            else: await call.delete()

        except Exception as e:
            err_msg = self.strings("error").format(str(e))
            if not call: await utils.answer(status, err_msg)
            else: await call.edit(err_msg)

    @loader.command(ru_doc=" > История")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        if not history: return await utils.answer(message, self.strings("history_empty"))
        
        kb = []
        for e in reversed(history):
            kb.append([{"text": f"🖼 {e['prompt'][:30]}", "callback": self._hist_cb, "args": (e['id'],)}])
        
        kb.append([{"text": "🧹 Очистить историю", "callback": self._clear_all_cb}])
        await self.inline.form("<b>📝 История:</b>", message=message, reply_markup=kb)

    async def _regen_cb(self, call: InlineCall, prompt):
        # Важно передать call.message, чтобы подхватить правильный чат
        await self._process_gen(call.message, prompt, call=call)

    async def _hist_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        sess = next((i for i in history if i["id"] == sid), None)
        
        if not sess:
            return await call.answer("Запись не найдена", show_alert=True)

        await call.answer("Отправляю...")
        file = io.BytesIO(base64.b64decode(sess["bytes"]))
        file.name = "hist.png"
        
        # Самый безопасный способ отправки в тот же чат
        await self._client.send_file(
            call.message.chat.id, 
            file, 
            caption=f"📜 <b>Из истории</b>\n<i>{sess['prompt']}</i>",
            buttons=[[{"text": "🔄 Перегенерировать", "callback": self._regen_cb, "args": (sess['prompt'],)}]]
        )

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        await call.edit(self.strings("history_cleared"))
        await call.answer("Очищено")
