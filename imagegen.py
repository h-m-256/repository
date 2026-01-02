# meta developer: @h_m_256
# requires: Pillow
# написано с помощью ии ☃️
import aiohttp
import base64
import uuid
import logging
import json
import asyncio
import io
from PIL import Image
from .. import loader, utils
from telethon.tl.types import Message
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

@loader.tds
class ImageGenMod(loader.Module):
    """Генерация/редактирование изображений через модели от гугл"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use",
        "quality": "Image upload quality (Input)",
        "prefix": "Initial prompt prefix (style, quality, etc)",
        "gen_new": "🎨 <b>Генерация...</b>\n<i>{}</i>",
        "gen_var": "🎨 <b>Генерация нового варианта...</b>\n<i>{}</i>",
        "uploading": "📤 <b>Обработка и загрузка...</b>",
        "error": "❌ <b>Ошибка:</b>\n<blockquote expandable>{}</blockquote>",
        "error_long": "❌ <b>Ошибка слишком длинная!</b>\nСкачайте лог ниже.",
        "success": "✅ <b>Готово!</b>\n<i>{}</i>",
        "success_with_text": "✅ <b>Готово!</b>\n<i>{}</i>\n\n<blockquote expandable>{}</blockquote>",
        "history_empty": "❌ История пуста!",
        "history_cleared": "✅ История очищена!",
        "history_item": "🖼 <b>История [{}/{}]</b>\n<i>{}</i>",
        "history_item_text": "🖼 <b>История [{}/{}]</b>\n<i>{}</i>\n\n<blockquote expandable>{}</blockquote>",
        "no_api": "❌ <b>Не установлен API ключ!</b>",
        "btn_regen": "🔄 Еще вариант",
        "btn_back": "🔙 Меню",
        "btn_list": "📂 Список",
        "btn_clear": "🗑 Очистить все",
        "btn_del_one": "🗑",
        "btn_close": "❌ Закрыть",
        "btn_loading": "🕘",
        "btn_slideshow": "🎞 Галерея",
        "btn_log": "📥 Лог в Избранное",
        "log_caption": "📄 <b>Полный лог ошибки ImageGen</b>",
        "btn_back_hist": "🔙 В историю",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model", "gemini-2.5-flash-image", lambda: self.strings("model"), validator=loader.validators.Choice([
                "gemini-2.5-flash-image",
                "gemini-2.5-flash-image-preview",
                "gemini-3-pro-image-preview",
                "nano-banana-pro-preview",
                "imagen-4.0-generate-001",
                "imagen-4.0-ultra-generate-001",
                "imagen-4.0-fast-generate-001"
            ])),
            loader.ConfigValue("quality", "Low", lambda: self.strings("quality"), validator=loader.validators.Choice(["Low", "Medium", "High", "Original"])),
            loader.ConfigValue("prefix", "", lambda: self.strings("prefix")),
        )
        self.sessions = {}
        self.url_cache = {}
        self.error_cache = {}

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

    def _resize_image(self, img_bytes):
        setting = self.config["quality"]
        if setting == "Original":
            return img_bytes
        
        # Настройки ресайза: (Max Size, JPEG Quality)
        presets = {
            "Low": (800, 75),
            "Medium": (1024, 85),
            "High": (1280, 90)
        }
        size, qual = presets.get(setting, (800, 75))

        try:
            img = Image.open(io.BytesIO(img_bytes))
            img.thumbnail((size, size))
            out = io.BytesIO()
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            img.save(out, format='JPEG', quality=qual)
            return out.getvalue()
        except Exception as e:
            logger.error(f"Resize failed: {e}")
            return img_bytes

    # --- UPLOADERS ---
    async def _up_catbox(self, session, img_bytes):
        data = aiohttp.FormData()
        data.add_field('reqtype', 'fileupload')
        data.add_field('fileToUpload', img_bytes, filename='image.png', content_type='image/png')
        async with session.post('https://catbox.moe/user/api.php', data=data, timeout=15) as resp:
            if resp.status == 200: return await resp.text()
        return None

    async def _up_0x0(self, session, img_bytes):
        data = aiohttp.FormData()
        data.add_field('file', img_bytes, filename='image.png', content_type='image/png')
        async with session.post('https://0x0.st', data=data, timeout=15) as resp:
            if resp.status == 200: return await resp.text()
        return None

    async def _up_x0(self, session, img_bytes):
        data = aiohttp.FormData()
        data.add_field('file', img_bytes, filename='image.png', content_type='image/png')
        async with session.post('https://x0.at', data=data, timeout=15) as resp:
            if resp.status == 200: return await resp.text()
        return None

    async def _upload_image(self, img_bytes):
        async with aiohttp.ClientSession() as session:
            queue = [self._up_catbox, self._up_0x0, self._up_x0]
            for uploader in queue:
                try:
                    url = await uploader(session, img_bytes)
                    if url and url.startswith("http"): return url.strip()
                except: continue
            return None

    # --- API ---
    async def _call_api(self, prompt: str, input_image_bytes=None):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['model']}:generateContent?key={self.config['api_key']}"
        parts = [{"text": prompt}]
        
        if input_image_bytes:
            resized_bytes = await utils.run_sync(self._resize_image, input_image_bytes)
            b64_img = base64.b64encode(resized_bytes).decode('utf-8')
            parts.insert(0, {"inlineData": {"mimeType": "image/jpeg", "data": b64_img}})

        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"}
        ]
        payload = {
            "contents": [{"parts": parts}],
            "safetySettings": safety_settings,
            "generationConfig": {"candidateCount": 1, "temperature": 1.0}
        }
        
        max_retries = 3
        async with aiohttp.ClientSession() as session:
            for attempt in range(max_retries):
                try:
                    async with session.post(url, json=payload, timeout=90) as resp:
                        if resp.status == 429:
                            await asyncio.sleep((attempt + 1) * 2)
                            continue
                        try: return await resp.json()
                        except: return {"error": {"message": f"HTTP {resp.status}"}}
                except Exception as e: return {"error": {"message": str(e)}}
            return {"error": {"message": "Resource exhausted (429) after retries."}}

    # --- COMMANDS ---
    @loader.command(ru_doc="<промпт> [реплай на фото] - Генерация/Редактирование")
    async def ig(self, message: Message):
        """Generate or edit image"""
        args = utils.get_args_raw(message)
        if not args and not self.config["prefix"]: return await utils.answer(message, "Введите промпт")
        if not self.config["api_key"]: return await utils.answer(message, self.strings("no_api"))
        
        user_prompt = args.strip() if args.strip() else "..."
        api_prompt = (self.config["prefix"] + " " + args).strip()
        
        input_bytes = None
        reply = await message.get_reply_message()
        if (reply and reply.media) or message.media:
            target = reply if reply and reply.media else message
            try:
                if target.photo or (target.document and target.document.mime_type.startswith('image/')):
                    input_bytes = await self._client.download_media(target, file=bytes)
            except: pass

        msg = await self.inline.form(
            text=self.strings("gen_new").format(utils.escape_html(user_prompt)),
            message=message,
            reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]]
        )
        
        sid = str(uuid.uuid4())
        self.sessions[sid] = {"api_prompt": api_prompt, "display_prompt": user_prompt, "images": [], "index": -1, "input_img": input_bytes, "from_history": False}
        await self._process_gen(msg, sid)

    async def _process_gen(self, target, sid):
        if sid not in self.sessions: return await self._safe_close(target)
        session = self.sessions[sid]
        
        try:
            data = await self._call_api(session["api_prompt"], session.get("input_img"))
            if not data or "error" in data:
                err_msg = json.dumps(data, indent=2, ensure_ascii=False) if data else "Empty response"
                raise ValueError(err_msg)

            # --- МУЛЬТИМОДАЛЬНЫЙ ПАРСИНГ ---
            img_b64 = None
            text_resp = ""
            
            try:
                # Берем части первого кандидата
                parts = data["candidates"][0]["content"]["parts"]
                for part in parts:
                    if "inlineData" in part:
                        img_b64 = part["inlineData"]["data"]
                    if "text" in part:
                        text_resp += part["text"]
            except (KeyError, IndexError, TypeError):
                 err_msg = json.dumps(data, indent=2, ensure_ascii=False)
                 raise ValueError(f"Invalid response structure.\n{err_msg}")

            if not img_b64:
                 # Если картинки нет, но есть текст - кидаем ошибку с текстом
                 if text_resp: raise ValueError(f"No image, only text:\n{text_resp}")
                 else: raise ValueError("No image data found.")
            # -------------------------------

            img_bytes = base64.b64decode(img_b64)
            hist_id = str(uuid.uuid4())
            history = self.db.get("ImageGen", "history", [])
            # Сохраняем в историю и промпт, и текстовый ответ модели
            history.append({"id": hist_id, "prompt": session["display_prompt"], "bytes": img_b64, "text_resp": text_resp})
            self.db.set("ImageGen", "history", history[-30:])

            if hasattr(target, "edit"):
                await target.edit(self.strings("uploading"), reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])

            img_url = await self._upload_image(img_bytes)
            if not img_url: raise ValueError("Upload failed")
            
            self.url_cache[hist_id] = img_url
            session["images"].append({"url": img_url, "text": text_resp})
            session["index"] = len(session["images"]) - 1
            
            await self._update_gen_view(target, sid)

        except Exception as e:
            error_text = str(e)
            kb = []
            text_to_show = self.strings("error").format(utils.escape_html(error_text))
            
            if len(error_text) > 1000:
                err_id = str(uuid.uuid4())
                self.error_cache[err_id] = error_text
                text_to_show = self.strings("error_long")
                kb.append([{"text": self.strings("btn_log"), "callback": self._dl_error, "args": (err_id,)}])

            kb.append([{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)}])
            if session.get("from_history"):
                kb.append([{"text": self.strings("btn_back_hist"), "callback": self._back_to_menu}])
            else:
                kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])
            
            await target.edit(text=text_to_show, reply_markup=kb)

    async def _dl_error(self, call: InlineCall, err_id):
        if err_id not in self.error_cache: return await call.answer("Error expired", show_alert=True)
        content = self.error_cache[err_id]
        file = io.BytesIO(content.encode('utf-8'))
        file.name = "error_log.txt"
        try:
            await self._client.send_file("me", file, caption=self.strings("log_caption"))
            await call.answer("Log sent to Saved Messages!")
        except Exception as e: await call.answer(f"Failed: {e}", show_alert=True)

    async def _update_gen_view(self, target, sid):
        if sid not in self.sessions: return
        s = self.sessions[sid]
        idx = s["index"]
        total = len(s["images"])
        
        current_data = s["images"][idx]
        img_url = current_data["url"]
        ai_text = current_data.get("text", "")
        
        safe_prompt = utils.escape_html(s["display_prompt"])
        
        # Формируем подпись
        if ai_text:
             text_to_show = self.strings("success_with_text").format(safe_prompt, utils.escape_html(ai_text.strip()))
        else:
             text_to_show = self.strings("success").format(safe_prompt)
        
        nav_row = []
        if total > 1:
            nav_row.append({"text": "⬅️", "callback": self._nav_gen_cb, "args": (sid, -1)})
            nav_row.append({"text": f"{idx + 1}/{total}", "callback": self._dummy_cb})
            nav_row.append({"text": "➡️", "callback": self._nav_gen_cb, "args": (sid, 1)})

        kb = []
        if nav_row: kb.append(nav_row)
        kb.append([{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)}])
        
        if s.get("from_history"):
            kb.append([{"text": self.strings("btn_back_hist"), "callback": self._back_to_menu}])
        
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

        await target.edit(
            text=text_to_show,
            photo=img_url,
            reply_markup=kb
        )

    async def _nav_gen_cb(self, call: InlineCall, sid, direction):
        if sid not in self.sessions: return await call.answer("Expired")
        s = self.sessions[sid]
        new_idx = s["index"] + direction
        if 0 <= new_idx < len(s["images"]):
            s["index"] = new_idx
            await self._update_gen_view(call, sid)
        else: await call.answer("Край")

    async def _regen_cb(self, call: InlineCall, sid):
        if sid not in self.sessions: return await call.answer("Expired", show_alert=True)
        s = self.sessions[sid]
        await call.answer("Генерация...")
        
        await call.edit(
            self.strings("gen_var").format(utils.escape_html(s["display_prompt"])), 
            reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]]
        )
        await self._process_gen(call, sid)

    # --- HISTORY ---
    @loader.command(ru_doc=" - История генераций")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        if not history: return await utils.answer(message, self.strings("history_empty"))
        
        msg = await self.inline.form(self.strings("uploading"), message=message, reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])
        
        class FakeCall:
            def __init__(self, msg): self.message = msg
            async def edit(self, *args, **kwargs): await self.message.edit(*args, **kwargs)
            async def answer(self, *args, **kwargs): pass
            async def delete(self): await self.message.delete()
        
        await self._render_history_slide(FakeCall(msg), 0)

    async def _show_history_menu(self, target):
        history = self.db.get("ImageGen", "history", [])
        text = self.strings("history_empty") if not history else "<b>📝 История генераций:</b>"
        
        kb = []
        if history:
            for e in reversed(history[-5:]):
                p = e.get('prompt', '...')
                prompt_preview = (p[:25] + '..') if len(p) > 25 else p
                kb.append([{"text": f"🖼 {utils.escape_html(prompt_preview)}", "callback": self._view_hist_item, "args": (e['id'],)}])
            kb.append([{"text": self.strings("btn_slideshow"), "callback": self._start_slideshow}])
            kb.append([{"text": self.strings("btn_clear"), "callback": self._clear_all_cb}])
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

        await target.edit(text, reply_markup=kb)

    async def _start_slideshow(self, call: InlineCall):
        history = self.db.get("ImageGen", "history", [])
        if not history: return await call.answer("Empty")
        await self._render_history_slide(call, 0)

    async def _view_hist_item(self, call: InlineCall, item_id):
        history = self.db.get("ImageGen", "history", [])
        idx = next((i for i, x in enumerate(history) if x["id"] == item_id), -1)
        if idx == -1: return await call.answer("Not found")
        await self._render_history_slide(call, idx)

    async def _render_history_slide(self, call: InlineCall, index):
        history = self.db.get("ImageGen", "history", [])
        if not history: return await self._show_history_menu(call)
        
        index = max(0, min(index, len(history) - 1))
        item = history[index]
        img_url = self.url_cache.get(item["id"])
        
        if not img_url:
            await call.edit(self.strings("uploading"), reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])
            try:
                img_bytes = base64.b64decode(item["bytes"])
                img_url = await self._upload_image(img_bytes)
                if img_url: self.url_cache[item["id"]] = img_url
            except: pass
        
        if not img_url: return await call.answer("Ошибка загрузки", show_alert=True)

        safe_prompt = utils.escape_html(item.get('prompt', 'image'))
        ai_text = item.get("text_resp", "")

        if ai_text:
            text_to_show = self.strings("history_item_text").format(index + 1, len(history), safe_prompt, utils.escape_html(ai_text.strip()))
        else:
            text_to_show = self.strings("history_item").format(index + 1, len(history), safe_prompt)

        nav = []
        if index > 0:
            nav.append({"text": "⬅️", "callback": self._hist_nav, "args": (index - 1,)})
        nav.append({"text": f"{index + 1}/{len(history)}", "callback": self._dummy_cb})
        if index < len(history) - 1:
            nav.append({"text": "➡️", "callback": self._hist_nav, "args": (index + 1,)})

        kb = [nav]
        actions = []
        actions.append({"text": self.strings("btn_del_one"), "callback": self._del_one_cb, "args": (item['id'],)})
        actions.append({"text": self.strings("btn_regen"), "callback": self._regen_from_hist, "args": (item.get('prompt', ''),)})
        actions.append({"text": self.strings("btn_list"), "callback": self._back_to_menu})
        kb.append(actions)
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])
        
        await call.edit(
            text=text_to_show,
            photo=img_url,
            reply_markup=kb
        )

    async def _hist_nav(self, call: InlineCall, new_index):
        await self._render_history_slide(call, new_index)

    async def _back_to_menu(self, call: InlineCall):
        await self._show_history_menu(call)

    async def _del_one_cb(self, call: InlineCall, item_id):
        history = self.db.get("ImageGen", "history", [])
        idx = next((i for i, x in enumerate(history) if x["id"] == item_id), -1)
        if idx == -1: return await call.answer("Not found")
        
        history.pop(idx)
        self.db.set("ImageGen", "history", history)
        if item_id in self.url_cache: del self.url_cache[item_id]
        
        await call.answer("Удалено!")
        if not history: await self._show_history_menu(call)
        else:
            new_idx = idx if idx < len(history) else idx - 1
            await self._render_history_slide(call, new_idx)

    async def _regen_from_hist(self, call: InlineCall, prompt):
        sid = str(uuid.uuid4())
        self.sessions[sid] = {"api_prompt": prompt, "display_prompt": prompt, "images": [], "index": -1, "input_img": None, "from_history": True}
        await self._regen_cb(call, sid)

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        self.url_cache.clear()
        await call.answer(self.strings("history_cleared"), show_alert=True)
        # Просто перерисовываем меню, оно само увидит что история пуста и покажет соответствующий текст
        await self._show_history_menu(call)

    async def _dummy_cb(self, call: InlineCall): await call.answer()
    async def _safe_close(self, call: InlineCall):
        try: await call.delete()
        except: await call.answer("Error")
