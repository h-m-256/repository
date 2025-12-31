# meta developer: @h_m_256
# все снизу написано с помощью ии ☃️
import aiohttp
import base64
import uuid
import logging
import json
import io
from .. import loader, utils
from telethon.tl.types import Message
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

@loader.tds
class ImageGenMod(loader.Module):
    """AI Image Generation"""

    strings = {
        "name": "ImageGen",
        "api_key": "Google AI Studio API key",
        "model": "Model to use",
        "prefix": "Initial prompt prefix (style, quality, etc)",
        "gen_new": "🎨 <b>Генерация изображения...</b>\n<i>{}</i>",
        "gen_var": "🎨 <b>Генерация нового варианта...</b>\n<i>{}</i>",
        "uploading": "📤 <b>Обработка и загрузка...</b>",
        "error": "❌ <b>Ошибка API:</b>\n<blockquote expandable>{}</blockquote>",
        "success": "✅ <b>Готово!</b>\n<i>{}</i>",
        "history_empty": "❌ История пуста!",
        "history_cleared": "✅ История очищена!",
        "history_item": "🖼 <b>Просмотр из истории</b>\n<i>{}</i>",
        "no_api": "❌ <b>Не установлен API ключ!</b>",
        "btn_regen": "🔄 Еще вариант",
        "btn_back": "🔙 Назад",
        "btn_clear": "🗑 Очистить всё",
        "btn_close": "❌ Закрыть",
        "btn_loading": "⌛ Генерация...",
        "no_media": "❌ Не удалось загрузить медиа.",
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
            loader.ConfigValue("prefix", "", lambda: self.strings("prefix")),
        )
        self.sessions = {}

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

    async def _upload_to_catbox(self, img_bytes):
        try:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('fileToUpload', img_bytes, filename='image.png', content_type='image/png')
            
            async with aiohttp.ClientSession() as session:
                async with session.post('https://catbox.moe/user/api.php', data=data) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.text()
        except Exception:
            return None

    async def _call_api(self, prompt: str, input_image_bytes=None):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['model']}:generateContent?key={self.config['api_key']}"
        
        parts = [{"text": prompt}]
        
        if input_image_bytes:
            b64_img = base64.b64encode(input_image_bytes).decode('utf-8')
            parts.insert(0, {
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": b64_img
                }
            })

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
            
            hist_id = str(uuid.uuid4())
            history = self.db.get("ImageGen", "history", [])
            history.append({"id": hist_id, "prompt": prompt, "bytes": img_b64})
            self.db.set("ImageGen", "history", history[-20:])

            if hasattr(target, "edit"): 
                await target.edit(self.strings("uploading"), reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])

            img_url = await self._upload_to_catbox(img_bytes)
            
            if not img_url:
                raise ValueError("Upload failed")

            session["images"].append(img_url)
            session["index"] = len(session["images"]) - 1
            
            await self._update_view(target, sid)

        except Exception as e:
            error_text = str(e)
            kb = [[{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)}],
                  [{"text": self.strings("btn_close"), "callback": self._safe_close}]]
            
            await target.edit(
                text=self.strings("error").format(utils.escape_html(error_text)),
                reply_markup=kb
            )

    async def _update_view(self, target, sid):
        if sid not in self.sessions:
            return
            
        s = self.sessions[sid]
        idx = s["index"]
        total = len(s["images"])
        img_url = s["images"][idx]
        safe_prompt = utils.escape_html(s["prompt"])
        
        nav_row = []
        if total > 1:
            nav_row.append({"text": "⬅️", "callback": self._nav_cb, "args": (sid, -1)})
            nav_row.append({"text": f"{idx + 1}/{total}", "callback": self._dummy_cb})
            nav_row.append({"text": "➡️", "callback": self._nav_cb, "args": (sid, 1)})

        kb = []
        if nav_row:
            kb.append(nav_row)
            
        kb.append([{"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)}])
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

        await target.edit(
            text=self.strings("success").format(safe_prompt),
            photo=img_url,
            reply_markup=kb
        )

    async def _nav_cb(self, call: InlineCall, sid, direction):
        if sid not in self.sessions:
            return await call.answer("Сессия истекла", show_alert=True)
            
        s = self.sessions[sid]
        new_idx = s["index"] + direction
        
        if 0 <= new_idx < len(s["images"]):
            s["index"] = new_idx
            await self._update_view(call, sid)
        else:
            await call.answer("Край")

    async def _regen_cb(self, call: InlineCall, sid):
        if sid not in self.sessions:
            # Пытаемся восстановить сессию из аргументов, если это возможно, или создаем новую
            # Но здесь промпт нужен. Если сессии нет, лучше сообщить.
            return await call.answer("Сессия перезагружена. Используйте команду заново.", show_alert=True)
            
        safe_prompt = utils.escape_html(self.sessions[sid]["prompt"])
        await call.answer("Генерация...")
        
        # Скрываем фото во время генерации (если ядро позволит) или просто меняем текст
        await call.edit(
            self.strings("gen_var").format(safe_prompt), 
            reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]]
        )
        await self._process_gen(call, sid)

    async def _dummy_cb(self, call: InlineCall):
        await call.answer()

    async def _safe_close(self, call: InlineCall):
        try:
            await call.delete()
        except:
            await call.answer("Ошибка удаления", show_alert=True)

    @loader.command(ru_doc=" - История генераций")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        if not history:
            return await utils.answer(message, self.strings("history_empty"))
        
        await self._show_history_menu(message, history)

    async def _show_history_menu(self, call_or_msg, history):
        kb = []
        for e in reversed(history):
            prompt_preview = (e['prompt'][:25] + '..') if len(e['prompt']) > 25 else e['prompt']
            kb.append([{"text": f"🖼 {utils.escape_html(prompt_preview)}", "callback": self._hist_cb, "args": (e['id'],)}])
        
        kb.append([{"text": self.strings("btn_clear"), "callback": self._clear_all_cb}])
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])
        
        text = "<b>📝 История генераций:</b>"
        
        if isinstance(call_or_msg, Message):
            await self.inline.form(text, message=call_or_msg, reply_markup=kb)
        else:
            # Трюк: чтобы убрать фото, передаем пустую строку в photo, если ядро позволяет,
            # иначе просто текст. В большинстве версий hikka edit_message_text вызывается если media нет.
            # Но если сообщение было с фото, надо менять media.
            # Попробуем отправить InputMediaString или просто текст.
            try:
                await call_or_msg.edit(text, reply_markup=kb, photo="") 
            except:
                # Если photo="" вызывает ошибку, удаляем и шлем новое (крайний случай)
                # Но лучше попытаться просто текст
                await call_or_msg.edit(text, reply_markup=kb)

    async def _hist_cb(self, call: InlineCall, sid):
        history = self.db.get("ImageGen", "history", [])
        sess = next((i for i in history if i["id"] == sid), None)
        
        if not sess:
            return await call.answer("Запись удалена", show_alert=True)

        await call.answer("Загружаю...")
        
        try:
            img_bytes = base64.b64decode(sess["bytes"])
            img_url = await self._upload_to_catbox(img_bytes)
            
            if not img_url:
                 return await call.answer("Ошибка восстановления ссылки", show_alert=True)

            safe_prompt = utils.escape_html(sess['prompt'])
            
            kb = [
                # Восстановление сессии для регена из истории невозможно без input image,
                # поэтому просто копируем промпт в буфер или запускаем новую команду
                # Но так как мы не можем запустить команду от юзера, кнопку регена тут делать сложно с пагинацией.
                # Сделаем простую кнопку регена новой сессией
                [{"text": self.strings("btn_regen"), "callback": self._regen_from_hist, "args": (sess['prompt'],)}],
                [{"text": self.strings("btn_back"), "callback": self._back_to_hist_cb}],
                [{"text": self.strings("btn_close"), "callback": self._safe_close}]
            ]
            
            await call.edit(
                text=self.strings("history_item").format(safe_prompt),
                photo=img_url,
                reply_markup=kb
            )
        except Exception as e:
            await call.answer(f"Error: {e}", show_alert=True)

    async def _regen_from_hist(self, call: InlineCall, prompt):
        # Запуск новой сессии из истории
        sid = str(uuid.uuid4())
        self.sessions[sid] = {
            "prompt": prompt,
            "images": [],
            "index": -1,
            "input_img": None # Из истории картинку-исходник не достать
        }
        await self._regen_cb(call, sid)

    async def _back_to_hist_cb(self, call: InlineCall):
        history = self.db.get("ImageGen", "history", [])
        if not history:
             return await call.edit(self.strings("history_empty"), reply_markup=[[{"text": self.strings("btn_close"), "callback": self._safe_close}]], photo="")
        await self._show_history_menu(call, history)

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        await call.edit(self.strings("history_cleared"), reply_markup=[[{"text": self.strings("btn_close"), "callback": self._safe_close}]], photo="")
