# meta developer: @h_m_256
# все снизу написано с помощью ии ☃️
import aiohttp
import base64
import uuid
import logging
import json
import asyncio
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
        "provider": "Image hosting provider (Auto = fallback chain)",
        "prefix": "Initial prompt prefix (style, quality, etc)",
        "gen_new": "🎨 <b>Генерация изображения...</b>\n<i>{}</i>",
        "gen_var": "🎨 <b>Генерация нового варианта...</b>\n<i>{}</i>",
        "uploading": "📤 <b>Обработка и загрузка...</b>",
        "error": "❌ <b>Ошибка API:</b>\n<blockquote expandable>{}</blockquote>",
        "success": "✅ <b>Готово!</b>\n<i>{}</i>",
        "history_empty": "❌ История пуста!",
        "history_cleared": "✅ История очищена!",
        "history_item": "🖼 <b>История [{}/{}]</b>\n<i>{}</i>",
        "no_api": "❌ <b>Не установлен API ключ!</b>",
        "btn_regen": "🔄 Еще вариант",
        "btn_back": "🔙 Меню",
        "btn_clear": "🗑 Очистить",
        "btn_close": "❌ Закрыть",
        "btn_loading": "⌛ Генерация...",
        "btn_slideshow": "🎞 Режим просмотра",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model", "nano-banana-pro-preview", lambda: self.strings("model"), validator=loader.validators.Choice([
                "gemini-2.5-flash-image",
                "gemini-2.5-flash-image-preview",
                "gemini-3-pro-image-preview",
                "nano-banana-pro-preview",
                "imagen-4.0-generate-001",
                "imagen-4.0-ultra-generate-001",
                "imagen-4.0-fast-generate-001"
            ])),
            loader.ConfigValue("provider", "Auto", lambda: self.strings("provider"), validator=loader.validators.Choice([
                "Auto", "Catbox", "0x0", "x0"
            ])),
            loader.ConfigValue("prefix", "", lambda: self.strings("prefix")),
        )
        self.sessions = {}
        self.url_cache = {} 

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

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
        provider = self.config["provider"]
        
        async with aiohttp.ClientSession() as session:
            # Определяем порядок попыток
            queue = []
            if provider == "Auto":
                queue = [self._up_catbox, self._up_0x0, self._up_x0]
            elif provider == "Catbox":
                queue = [self._up_catbox]
            elif provider == "0x0":
                queue = [self._up_0x0]
            elif provider == "x0":
                queue = [self._up_x0]

            # Пробуем по очереди
            for uploader in queue:
                try:
                    url = await uploader(session, img_bytes)
                    if url and url.startswith("http"):
                        return url.strip()
                except Exception as e:
                    logger.debug(f"Upload failed: {e}")
                    continue
            
            return None

    # --- API ---

    async def _call_api(self, prompt: str, input_image_bytes=None):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['model']}:generateContent?key={self.config['api_key']}"
        parts = [{"text": prompt}]
        
        if input_image_bytes:
            b64_img = base64.b64encode(input_image_bytes).decode('utf-8')
            parts.insert(0, {"inlineData": {"mimeType": "image/jpeg", "data": b64_img}})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"candidateCount": 1, "temperature": 1.0}
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=90) as resp:
                try:
                    return await resp.json()
                except:
                    return {"error": {"message": f"HTTP {resp.status}"}}

    # --- COMMANDS ---

    @loader.command(ru_doc="<промпт> [реплай на фото] - Генерация/Редактирование")
    async def ig(self, message: Message):
        """Generate or edit image"""
        args = utils.get_args_raw(message)
        if not args and not self.config["prefix"]:
            return await utils.answer(message, "Введите промпт")
        if not self.config["api_key"]:
            return await utils.answer(message, self.strings("no_api"))
        
        full_prompt = (self.config["prefix"] + " " + args).strip()
        safe_prompt = utils.escape_html(full_prompt)
        
        input_bytes = None
        reply = await message.get_reply_message()
        if (reply and reply.media) or message.media:
            target = reply if reply and reply.media else message
            try:
                if target.photo or (target.document and target.document.mime_type.startswith('image/')):
                    input_bytes = await self._client.download_media(target, file=bytes)
            except:
                pass

        msg = await self.inline.form(
            text=self.strings("gen_new").format(safe_prompt),
            message=message,
            reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]]
        )
        
        sid = str(uuid.uuid4())
        self.sessions[sid] = {
            "prompt": full_prompt,
            "images": [], 
            "index": -1,
            "input_img": input_bytes
        }
        
        await self._process_gen(msg, sid)

    async def _process_gen(self, target, sid):
        if sid not in self.sessions:
            return await self._safe_close(target)
            
        session = self.sessions[sid]
        prompt = session["prompt"]
        input_img = session.get("input_img")

        try:
            data = await self._call_api(prompt, input_img)
            
            if not data or "error" in data:
                err_msg = json.dumps(data, indent=2, ensure_ascii=False) if data else "Empty response"
                raise ValueError(err_msg)

            try:
                img_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            except (KeyError, IndexError, TypeError):
                err_msg = json.dumps(data, indent=2, ensure_ascii=False)
                raise ValueError(f"No image data found.\n{err_msg}")

            img_bytes = base64.b64decode(img_b64)
            
            # Сохранение в историю
            hist_id = str(uuid.uuid4())
            history = self.db.get("ImageGen", "history", [])
            history.append({"id": hist_id, "prompt": prompt, "bytes": img_b64})
            self.db.set("ImageGen", "history", history[-30:])

            if hasattr(target, "edit"): 
                await target.edit(self.strings("uploading"), reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])

            img_url = await self._upload_image(img_bytes)
            
            if not img_url:
                raise ValueError(f"Upload failed (Provider: {self.config['provider']})")
            
            self.url_cache[hist_id] = img_url

            session["images"].append(img_url)
            session["index"] = len(session["images"]) - 1
            
            await self._update_gen_view(target, sid)

        except Exception as e:
            error_text = str(e)
            kb = [[{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)}],
                  [{"text": self.strings("btn_close"), "callback": self._safe_close}]]
            
            await target.edit(
                text=self.strings("error").format(utils.escape_html(error_text)),
                reply_markup=kb
            )

    async def _update_gen_view(self, target, sid):
        if sid not in self.sessions: return
        s = self.sessions[sid]
        idx = s["index"]
        total = len(s["images"])
        img_url = s["images"][idx]
        safe_prompt = utils.escape_html(s["prompt"])
        
        nav_row = []
        if total > 1:
            nav_row.append({"text": "⬅️", "callback": self._nav_gen_cb, "args": (sid, -1)})
            nav_row.append({"text": f"{idx + 1}/{total}", "callback": self._dummy_cb})
            nav_row.append({"text": "➡️", "callback": self._nav_gen_cb, "args": (sid, 1)})

        kb = []
        if nav_row: kb.append(nav_row)
        kb.append([{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)}])
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

        await target.edit(
            text=self.strings("success").format(safe_prompt),
            photo=img_url,
            reply_markup=kb
        )

    async def _nav_gen_cb(self, call: InlineCall, sid, direction):
        if sid not in self.sessions: return await call.answer("Session expired")
        s = self.sessions[sid]
        new_idx = s["index"] + direction
        if 0 <= new_idx < len(s["images"]):
            s["index"] = new_idx
            await self._update_gen_view(call, sid)
        else:
            await call.answer("Край")

    async def _regen_cb(self, call: InlineCall, sid):
        if sid not in self.sessions:
            return await call.answer("Session expired", show_alert=True)
        await call.answer("Генерация...")
        safe_prompt = utils.escape_html(self.sessions[sid]["prompt"])
        await call.edit(
            self.strings("gen_var").format(safe_prompt), 
            reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]]
        )
        await self._process_gen(call, sid)

    # --- HISTORY ---

    @loader.command(ru_doc=" - История генераций")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        if not history:
            return await utils.answer(message, self.strings("history_empty"))
        await self._show_history_menu(message)

    async def _show_history_menu(self, target, is_update=False):
        history = self.db.get("ImageGen", "history", [])
        if not history:
            if is_update:
                return await target.edit(self.strings("history_empty"), reply_markup=[[{"text": "Close", "callback": self._safe_close}]])
            return

        kb = []
        for e in reversed(history[-5:]):
            prompt_preview = (e['prompt'][:25] + '..') if len(e['prompt']) > 25 else e['prompt']
            kb.append([{"text": f"🖼 {utils.escape_html(prompt_preview)}", "callback": self._view_hist_item, "args": (e['id'],)}])
        
        kb.append([{"text": self.strings("btn_slideshow"), "callback": self._start_slideshow}])
        kb.append([{"text": self.strings("btn_clear"), "callback": self._clear_all_cb}])
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])
        
        text = "<b>📝 История генераций:</b>"

        if not is_update:
            await self.inline.form(text, message=target, reply_markup=kb)
        else:
            try:
                chat_id = target.original_call.message.chat.id
                await target.delete()
                await self._client.send_message(chat_id, text, reply_markup=self.inline.generate_markup(kb))
            except:
                await target.edit(text, reply_markup=kb)

    async def _start_slideshow(self, call: InlineCall):
        history = self.db.get("ImageGen", "history", [])
        if not history: return await call.answer("Empty")
        await self._render_history_slide(call, len(history) - 1)

    async def _view_hist_item(self, call: InlineCall, item_id):
        history = self.db.get("ImageGen", "history", [])
        idx = next((i for i, x in enumerate(history) if x["id"] == item_id), -1)
        if idx == -1: return await call.answer("Not found")
        await self._render_history_slide(call, idx)

    async def _render_history_slide(self, call: InlineCall, index):
        history = self.db.get("ImageGen", "history", [])
        if not history: return await self._show_history_menu(call, True)
        
        index = max(0, min(index, len(history) - 1))
        item = history[index]
        
        img_url = self.url_cache.get(item["id"])
        
        if not img_url:
            await call.edit(self.strings("uploading"), reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])
            try:
                img_bytes = base64.b64decode(item["bytes"])
                img_url = await self._upload_image(img_bytes)
                if img_url:
                    self.url_cache[item["id"]] = img_url
            except Exception:
                pass
        
        if not img_url:
            return await call.answer("Ошибка загрузки изображения", show_alert=True)

        safe_prompt = utils.escape_html(item['prompt'])
        
        nav = []
        if index > 0:
            nav.append({"text": "⬅️", "callback": self._hist_nav, "args": (index - 1,)})
        nav.append({"text": f"{index + 1}/{len(history)}", "callback": self._dummy_cb})
        if index < len(history) - 1:
            nav.append({"text": "➡️", "callback": self._hist_nav, "args": (index + 1,)})

        kb = [nav]
        kb.append([{"text": self.strings("btn_regen"), "callback": self._regen_from_hist, "args": (item['prompt'],)}])
        kb.append([{"text": self.strings("btn_back"), "callback": self._back_to_menu}])
        
        await call.edit(
            text=self.strings("history_item").format(index + 1, len(history), safe_prompt),
            photo=img_url,
            reply_markup=kb
        )

    async def _hist_nav(self, call: InlineCall, new_index):
        await self._render_history_slide(call, new_index)

    async def _back_to_menu(self, call: InlineCall):
        await self._show_history_menu(call, is_update=True)

    async def _regen_from_hist(self, call: InlineCall, prompt):
        sid = str(uuid.uuid4())
        self.sessions[sid] = {"prompt": prompt, "images": [], "index": -1, "input_img": None}
        await self._regen_cb(call, sid)

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        self.url_cache.clear()
        await self._show_history_menu(call, is_update=True)

    async def _dummy_cb(self, call: InlineCall):
        await call.answer()

    async def _safe_close(self, call: InlineCall):
        try:
            await call.delete()
        except:
            await call.answer("Error")
