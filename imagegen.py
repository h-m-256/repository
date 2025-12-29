#meta developer: @h_m_256
#все снизу сгенерировано ии ☃️

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
    """AI Image Generation (Final Stability Fix)"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use for generation",
        "default_prompt_prefix": "Default prompt prefix",
        "no_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>API ключ не настроен!</b>',
        "generating": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Генерирую...</b>\n<i>{}</i>',
        "error": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка:</b> <code>{}</code>',
        "success": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>Готово!</b>\n<i>{}</i>',
        "history_empty": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>История пуста!</b>',
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model", "nano-banana-pro-preview", lambda: self.strings("model")),
            loader.ConfigValue("default_prompt_prefix", "", lambda: self.strings("default_prompt_prefix")),
        )

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

    async def _call_api(self, prompt: str):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['model']}:generateContent?key={self.config['api_key']}"
        full_prompt = f"{self.config['default_prompt_prefix']} {prompt}".strip()
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {"candidateCount": 1, "temperature": 1.0}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ValueError(f"API Error {resp.status}: {text[:100]}")
                return await resp.json()

    @loader.command(ru_doc=" > Сгенерировать изображение")
    async def ig(self, message: Message):
        """Generate image"""
        args = utils.get_args_raw(message)
        if not args: return await utils.answer(message, "Введите промпт")
        if not self.config["api_key"]: return await utils.answer(message, self.strings("no_api"))

        # Используем обычный ответ для статуса (надежнее всего)
        status = await utils.answer(message, self.strings("generating").format(args))
        
        try:
            data = await self._call_api(args)
            
            img_b64 = None
            try:
                img_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            except (KeyError, IndexError):
                raise ValueError("No image in response. Safety filter?")

            img_bytes = base64.b64decode(img_b64)
            file = io.BytesIO(img_bytes)
            file.name = "ai.png"

            # Сохраняем в историю
            sid = str(uuid.uuid4())
            history = self.db.get("ImageGen", "history", [])
            history.append({"id": sid, "prompt": args, "bytes": img_b64})
            self.db.set("ImageGen", "history", history[-10:])

            # Отправляем через Telethon (гарантированный успех)
            await self._client.send_file(
                message.chat_id, 
                file, 
                caption=self.strings("success").format(args),
                reply_to=message.id
            )
            await status.delete()

        except Exception as e:
            await utils.answer(status, self.strings("error").format(str(e)))

    @loader.command(ru_doc=" > История")
    async def ighist(self, message: Message):
        """History"""
        history = self.db.get("ImageGen", "history", [])
        if not history: return await utils.answer(message, self.strings("history_empty"))
        
        kb = []
        for e in reversed(history):
            kb.append([{"text": f"🖼 {e['prompt'][:30]}", "callback": self._hist_cb, "args": (e['id'],)}])
        
        await self.inline.form("<b>📝 История:</b>", message=message, reply_markup=kb)

    async def _hist_cb(self, call: InlineCall, sid):
        await call.answer("Отправляю...")
        history = self.db.get("ImageGen", "history", [])
        sess = next((i for i in history if i["id"] == sid), None)
        
        if sess:
            file = io.BytesIO(base64.b64decode(sess["bytes"]))
            file.name = "hist.png"
            await self._client.send_file(call.original_call.message.chat.id, file, caption=f"Из истории: {sess['prompt']}")
        else:
            await call.answer("Не найдено", show_alert=True)
