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
    """AI Image Generation with Stable History"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use for generation",
        "generating": "⌛ <b>Генерирую новый вариант...</b>\n<i>{}</i>",
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
        """Generate image with stable regenerate button"""
        args = utils.get_args_raw(message)
        if not args: return await utils.answer(message, "Введите промпт")
        if not self.config["api_key"]: return await utils.answer(message, "Настрой API ключ!")
        
        await self._process_gen(message, args)

    async def _process_gen(self, message, prompt, call=None):
        # 1. Информируем пользователя
        if call:
            await call.answer("Генерирую...")
            # В инлайне редактируем текст на статус загрузки
            await call.edit(self.strings("generating").format(prompt))
        else:
            status = await utils.answer(message, self.strings("generating").format(prompt))

        try:
            # 2. Получаем данные от API
            data = await self._call_api(prompt)
            img_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            img_bytes = base64.b64decode(img_b64)
            
            # 3. Сохраняем в историю
            sid = str(uuid.uuid4())
            history = self.db.get("ImageGen", "history", [])
            history.append({"id": sid, "prompt": prompt, "bytes": img_b64})
            self.db.set("ImageGen", "history", history[-10:])

            # 4. Формируем файл
            file = io.BytesIO(img_bytes)
            file.name = "ai.png"

            # 5. Кнопки (Формат Telethon для send_file)
            # В Heroku/Hikka мы используем build_reply_markup из клиента
            buttons = self._client.build_reply_markup([
                [{"text": "🔄 Перегенерировать", "callback": self._regen_cb, "args": (prompt,)}]
            ])

            # Определение ID чата (самый стабильный метод)
            chat_id = utils.get_chat_id(message)

            # 6. Отправка результата
            await self._client.send_file(
                chat_id,
                file,
                caption=self.strings("success").format(prompt),
                buttons=buttons
            )
            
            # Удаляем статусное сообщение
            if not call:
                await status.delete()
            else:
                try:
                    await call.delete()
                except:
                    pass

        except Exception as e:
            err_msg = self.strings("error").format(str(e))
            if not call:
                await utils.answer(status, err_msg)
            else:
                await call.edit(err_msg)

    @loader.command(ru_doc=" > История")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        if not history: return await utils.answer(message, self.strings("history_empty"))
        
        kb = []
        for e in reversed(history):
            kb.append([{"text": f"🖼 {e['prompt'][:30]}", "callback": self._hist_cb, "args": (e['id'],)}])
        
        kb.append([{"text": "🧹 Очистить историю", "callback": self._clear_all_cb}])
        await self.inline.form("<b>📝 История генераций:</b>", message=message, reply_markup=kb)

    async def _regen_cb(self, call: InlineCall, prompt):
        # Передаем оригинальное сообщение для контекста чата
        await self._process_gen(call.message, prompt, call=call)

    async def _hist_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        sess = next((i for i in history if i["id"] == sid), None)
        
        if not sess:
            return await call.answer("Запись не найдена", show_alert=True)

        await call.answer("Отправляю...")
        file = io.BytesIO(base64.b64decode(sess["bytes"]))
        file.name = "hist.png"
        
        # Безопасное получение chat_id для инлайна
        chat_id = utils.get_chat_id(call.message)
        
        buttons = self._client.build_reply_markup([
            [{"text": "🔄 Перегенерировать", "callback": self._regen_cb, "args": (sess['prompt'],)}]
        ])

        await self._client.send_file(
            chat_id, 
            file, 
            caption=f"📜 <b>Из истории</b>\n<i>{sess['prompt']}</i>",
            buttons=buttons
        )

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        await call.edit(self.strings("history_cleared"))
        await call.answer("Очищено")
