#meta developer: @h_m_256
#🔑 копурайт геймини 3 флеш/про

import asyncio
import aiohttp
import io
import base64
import json
import uuid
import time
from .. import loader, utils
from telethon.tl.types import Message
from ..inline.types import InlineCall

@loader.tds
class ImageGenMod(loader.Module):
    """AI Image Generation & History with Google Models"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use for generation",
        "default_prompt_prefix": "Default prompt prefix",
        "no_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>API key not configured!</b>',
        "generating": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Generating image...</b>\n\n<i>Prompt: {}</i>',
        "editing": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Editing image...</b>\n\n<i>Prompt: {}</i>',
        "error": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Error:</b>\n<code>{}</code>',
        "success": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>Success!</b>\n\n<i>Prompt: {}</i>',
        "usage": '<a href="tg://emoji?id=5334882760735598374">📝</a> <b>Usage:</b> <code>.ig [prompt]</code>',
        "history_empty": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>History is empty!</b>',
        "history_title": '<a href="tg://emoji?id=5334882760735598374">📝</a> <b>Generation History:</b>',
    }
    
    strings_ru = {
        "api_key": "API ключ Google AI Studio",
        "model": "Модель для генерации",
        "default_prompt_prefix": "Префикс промпта по умолчанию",
        "no_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>API ключ не настроен!</b>',
        "generating": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Генерация изображения...</b>\n\n<i>Промпт: {}</i>',
        "editing": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Редактирование изображения...</b>\n\n<i>Промпт: {}</i>',
        "error": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка:</b>\n<code>{}</code>',
        "success": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>Готово!</b>\n\n<i>Промпт: {}</i>',
        "usage": '<a href="tg://emoji?id=5334882760735598374">📝</a> <b>Использование:</b> <code>.ig [промпт]</code>',
        "history_empty": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>История пуста!</b>',
        "history_title": '<a href="tg://emoji?id=5334882760735598374">📝</a> <b>История генераций:</b>',
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model", "gemini-2.5-flash-image", lambda: self.strings("model"), 
                validator=loader.validators.Choice(["gemini-2.0-flash-exp", "gemini-2.5-flash-image", "gemini-2.5-flash-image-preview", "gemini-3-pro-image-preview", "nano-banana-pro-preview", "imagen-4.0-generate-001", "imagen-4.0-ultra-generate-001", "imagen-4.0-fast-generate-001"])),
            loader.ConfigValue("default_prompt_prefix", "", lambda: self.strings("default_prompt_prefix")),
        )

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

    async def _call_api(self, prompt: str, image_bytes: bytes = None):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['model']}:generateContent?key={self.config['api_key']}"
        full_prompt = f"{self.config['default_prompt_prefix']} {prompt}".strip()
        parts = [{"text": full_prompt}]
        if image_bytes:
            parts.append({"inlineData": {"mimeType": "image/png", "data": base64.b64encode(image_bytes).decode()}})
        
        payload = {
            "contents": [{"parts": parts}],
            "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]],
            "generationConfig": {"candidateCount": 1, "temperature": 1.0}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if resp.status != 200: raise ValueError(json.dumps(data, indent=2, ensure_ascii=False))
                return data

    @loader.command(ru_doc=" > Сгенерировать или изменить фото")
    async def ig(self, message: Message):
        """Generate/Edit image"""
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        photo = await (message.download_media(bytes) if message.photo else (reply.download_media(bytes) if reply and reply.photo else None))

        if not args and not photo: return await utils.answer(message, self.strings("usage"))
        if not self.config["api_key"]: return await utils.answer(message, self.strings("no_api"))

        prompt = args or "Enhance image"
        status_msg = await utils.answer(message, self.strings("editing" if photo else "generating").format(prompt))

        try:
            data = await self._call_api(prompt, photo)
            history = self.db.get("ImageGen", "history", [])
            sid = str(uuid.uuid4())
            history.append({"id": sid, "prompt": prompt, "data": data, "photo": base64.b64encode(photo).decode() if photo else None})
            self.db.set("ImageGen", "history", history[-20:])
            await self._render(message, sid, status_msg)
        except Exception as e:
            await utils.answer(status_msg, self.strings("error").format(str(e)[:1000]))

    @loader.command(ru_doc=" > Посмотреть историю")
    async def ighist(self, message: Message):
        """History"""
        history = self.db.get("ImageGen", "history", [])
        if not history: return await utils.answer(message, self.strings("history_empty"))
        kb = [[{"text": f"🖼 {e['prompt'][:30]}", "callback": self._hist_cb, "args": (e['id'],)}] for e in reversed(history)]
        await self.inline.form(self.strings("history_title"), message=message, reply_markup=kb)

    async def _render(self, message, sid, status_msg=None):
        history = self.db.get("ImageGen", "history", [])
        sess = next((i for i in history if i["id"] == sid), None)
        
        target = status_msg or message

        if not sess:
            err = self.strings("error").format("Session not found")
            return await (target.edit(err) if hasattr(target, 'edit') else utils.answer(message, err))

        try:
            img_b64 = None
            candidates = sess.get("data", {}).get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                for p in parts:
                    if "inlineData" in p:
                        img_b64 = p["inlineData"].get("data")
                        break
            
            if not img_b64:
                raise KeyError("No inlineData found")

            file = io.BytesIO(base64.b64decode(img_b64))
            file.name = "ai.png"
            
            kb = [
                [{"text": "🔄 Regenerate", "callback": self._regen_cb, "args": (sid,)}],
                [{"text": "🗑 Удалить", "callback": self._del_cb, "args": (sid,)}]
            ]
            
            if status_msg: await status_msg.delete()
            
            await self.inline.form(self.strings("success").format(sess["prompt"]), message=message, file=file, reply_markup=kb)
            
        except Exception:
            err_msg = self.strings("error").format("No image data in response. Content might be filtered.")
            if hasattr(target, 'edit'): await target.edit(err_msg)
            else: await utils.answer(message, err_msg)

    async def _hist_cb(self, call: InlineCall, sid):
        await self._render(call.message, sid)

    async def _del_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        history = [i for i in history if i["id"] != sid]
        self.db.set("ImageGen", "history", history)
        await call.delete()

    async def _regen_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        idx = next((i for i, v in enumerate(history) if v["id"] == sid), None)
        if idx is None: return

        await call.answer("Regenerating...")
        try:
            photo_raw = history[idx].get("photo")
            photo = base64.b64decode(photo_raw) if photo_raw else None
            new_data = await self._call_api(history[idx]["prompt"], photo)
            history[idx]["data"] = new_data
            self.db.set("ImageGen", "history", history)
            await self._render(call.message, sid)
        except Exception as e:
            await call.answer(f"Error: {str(e)[:100]}", show_alert=True)
