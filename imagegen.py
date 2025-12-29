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
    """AI Image Generation with History (Fixed for Heroku & Emoji)"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use for generation",
        "default_prompt_prefix": "Default prompt prefix",
        "no_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>API key not configured!</b>',
        "generating": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Generating image...</b>\n\n<i>Prompt: {}</i>',
        "error": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Error:</b>\n<code>{}</code>',
        "success": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>Success!</b>\n\n<i>Prompt: {}</i>',
        "history_empty": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>History is empty!</b>',
        "history_cleared": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>History cleared!</b>',
        "history_title": '<a href="tg://emoji?id=5334882760735598374">📝</a> <b>Generation History:</b>',
    }
    
    strings_ru = {
        "api_key": "API ключ Google AI Studio",
        "model": "Модель для генерации",
        "default_prompt_prefix": "Префикс промпта по умолчанию",
        "no_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>API ключ не настроен!</b>',
        "generating": '<a href="tg://emoji?id=5386367538735104399">⌛</a> <b>Генерирую изображение...</b>\n\n<i>Промпт: {}</i>',
        "error": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка:</b>\n<code>{}</code>',
        "success": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>Готово!</b>\n\n<i>Промпт: {}</i>',
        "history_empty": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>История пуста!</b>',
        "history_cleared": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>История очищена!</b>',
        "history_title": '<a href="tg://emoji?id=5334882760735598374">📝</a> <b>История генераций:</b>',
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model", "nano-banana-pro-preview", lambda: self.strings("model"), 
                validator=loader.validators.Choice([
                    "nano-banana-pro-preview", "gemini-3-pro-image-preview",
                    "gemini-2.5-flash-image", "imagen-4.0-generate-001"
                ])),
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
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if resp.status != 200: raise ValueError(json.dumps(data, indent=2, ensure_ascii=False))
                return data

    @loader.command(ru_doc=" > Сгенерировать изображение")
    async def ig(self, message: Message):
        """Generate image"""
        args = utils.get_args_raw(message)
        if not args: return await utils.answer(message, "Provide prompt")
        if not self.config["api_key"]: return await utils.answer(message, self.strings("no_api"))

        status_msg = await utils.answer(message, self.strings("generating").format(args))
        try:
            data = await self._call_api(args)
            sid = str(uuid.uuid4())
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
            img_b64 = None
            candidates = sess.get("data", {}).get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                for p in parts:
                    if "inlineData" in p:
                        img_b64 = p["inlineData"].get("data")
                        break
            
            if not img_b64: raise ValueError("Safety block or no image data")

            # Отправляем файл через send_file (самый стабильный метод для Heroku)
            file = io.BytesIO(base64.b64decode(img_b64))
            file.name = "ai.png"
            
            kb = [
                [{"text": "🔄 Regenerate", "callback": self._regen_cb, "args": (sid,)}],
                [{"text": "🗑 Удалить", "callback": self._del_cb, "args": (sid,)}]
            ]
            
            if status_msg: await status_msg.delete()
            
            # Используем inline.form на базе уже отправленного файла или напрямую
            # Для Heroku: байты в file работают лучше, если есть .name
            await self.inline.form(
                text=self.strings("success").format(sess["prompt"]),
                message=message,
                file=file,
                reply_markup=kb
            )
        except Exception as e:
            err = self.strings("error").format(str(e))
            if status_msg: await status_msg.edit(err)
            else: await self._client.send_message(message.chat_id, err)

    async def _hist_cb(self, call: InlineCall, sid):
        await self._render(call.message, sid)

    async def _del_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        self.db.set("ImageGen", "history", [i for i in history if i["id"] != sid])
        await call.delete()

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        await call.edit(self.strings("history_cleared"))

    async def _regen_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        idx = next((i for i, v in enumerate(history) if v["id"] == sid), None)
        if idx is None: return
        await call.answer("Regenerating...")
        try:
            new_data = await self._call_api(history[idx]["prompt"])
            history[idx]["data"] = new_data
            self.db.set("ImageGen", "history", history)
            await self._render(call.message, sid)
        except Exception as e:
            await call.answer(f"Error: {str(e)[:100]}", show_alert=True)
