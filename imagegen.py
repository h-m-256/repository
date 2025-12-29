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
    """генерация/редактирование изображений через модели google"""

    strings = {
        "name": "ImageGen",
        "_api_key": "Google AI Studio API key",
        "no_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>API key not configured!</b>',
        "generating": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Generating image...</b>\n\n<i>Prompt: {}</i>',
        "editing": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Editing image...</b>\n\n<i>Prompt: {}</i>',
        "error": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Error:</b>\n<code>{}</code>',
        "success": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>Success!</b> (Variant {}/{})\n\n<i>Prompt: {}</i>',
        "usage": '<a href="tg://emoji?id=5334882760735598374">📝</a> <b>Usage:</b> <code>.ig [prompt]</code>',
    }
    
    strings_ru = {
        "no_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>API ключ не настроен!</b>',
        "generating": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Генерация изображения...</b>\n\n<i>Промпт: {}</i>',
        "editing": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Редактирование изображения...</b>\n\n<i>Промпт: {}</i>',
        "error": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка:</b>\n<code>{}</code>',
        "success": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>Готово!</b> (Вариант {}/{})\n\n<i>Промпт: {}</i>',
        "usage": '<a href="tg://emoji?id=5334882760735598374">📝</a> <b>Использование:</b> <code>.ig [промпт]</code>',
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "API_KEY", "", lambda: "Google AI Studio API key",
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "MODEL", "gemini-2.0-flash-exp", lambda: "Model to use",
                validator=loader.validators.Choice([
                    "gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash"
                ]),
            ),
        )
        self._sessions = {}

    async def client_ready(self, client, db):
        self._client = client

    async def _call_api(self, prompt: str, image_bytes: bytes = None):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['MODEL']}:generateContent?key={self.config['API_KEY']}"
        parts = [{"text": prompt}]
        if image_bytes:
            parts.append({"inlineData": {"mimeType": "image/png", "data": base64.b64encode(image_bytes).decode()}})
        
        payload = {
            "contents": [{"parts": parts}],
            "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in [
                "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", 
                "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"
            ]],
            "generationConfig": {"candidateCount": 4, "temperature": 1.0}
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise ValueError(json.dumps(data, indent=2))
                return data

    def _extract_image(self, data, index=0):
        candidates = data.get("candidates", [])
        if not candidates or index >= len(candidates):
            return None
        for part in candidates[index].get("content", {}).get("parts", []):
            if "inlineData" in part:
                return base64.b64decode(part["inlineData"]["data"])
        return None

    async def ig(self, message: Message):
        """Generate/Edit image"""
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        photo = await message.download_media(bytes) if message.photo else (await reply.download_media(bytes) if reply and reply.photo else None)

        if not args and not photo:
            return await utils.answer(message, self.strings("usage"))
        if not self.config["API_KEY"]:
            return await utils.answer(message, self.strings("no_api"))

        status_text = self.strings("editing" if photo else "generating").format(args or "Enhance")
        status_msg = await utils.answer(message, status_text)

        try:
            data = await self._call_api(args or "Enhance", photo)
            sid = str(uuid.uuid4())
            self._sessions[sid] = {"data": data, "prompt": args, "photo": photo}
            await self._render_variant(message, sid, 0, status_msg)
        except Exception as e:
            await utils.answer(status_msg, self.strings("error").format(str(e)[:1000]))

    async def _render_variant(self, message, sid, index, status_msg=None):
        sess = self._sessions[sid]
        img = self._extract_image(sess["data"], index)
        if not img:
            return await utils.answer(status_msg, self.strings("error").format("No image in this variant"))

        count = len(sess["data"].get("candidates", []))
        kb = [[
            {"text": "⬅️", "callback": self._switch, "args": (sid, (index - 1) % count)},
            {"text": f"{index + 1}/{count}", "callback": self._switch, "args": (sid, index)},
            {"text": "➡️", "callback": self._switch, "args": (sid, (index + 1) % count)},
        ], [{"text": "🔄 Regenerate", "callback": self._regen, "args": (sid,)}]]

        file = io.BytesIO(img)
        file.name = "ai.png"
        
        caption = self.strings("success").format(index + 1, count, sess["prompt"] or "Enhance")
        
        if status_msg:
            await status_msg.delete()
        
        await self.inline.form(caption, message=message, file=file, reply_markup=kb)

    async def _switch(self, call: InlineCall, sid, index):
        await self._render_variant(call.message, sid, index)

    async def _regen(self, call: InlineCall, sid):
        sess = self._sessions[sid]
        status = await call.answer(self.strings("generating" if not sess["photo"] else "editing").format("..."))
        try:
            new_data = await self._call_api(sess["prompt"] or "Enhance", sess["photo"])
            self._sessions[sid]["data"] = new_data
            await self._render_variant(call.message, sid, 0)
        except Exception as e:
            await call.answer(f"Error: {str(e)[:100]}", show_alert=True)
