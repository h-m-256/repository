#        __                
#       / /_     ____ ____ 
#      / __ \   / __ `/ _ \
#     / / / /  / /_/ /  __/
#    /_/ /_/   \__,_/\___/ 
#
# meta developer: @h_m_256
#
# поцаны вайбкодить имба, я сам вайбкодер
import aiohttp
import base64
import uuid
import logging
import json
import asyncio
import io
import random
import textwrap
import re
import time
from PIL import Image
from .. import loader, utils
from telethon.tl.types import Message
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

@loader.tds
class ImageGenMod(loader.Module):
    """Генератор и редактор изображений с историей (опционально) с помощью моделей от google + pollinations (pollinations бесплатен, без ключа, модели pollinations не поддерживают редактирование)"""

    strings = {
        "name": "ImageGen",
        "api_key": "API ключ Google AI Studio (для .ig)",
        "model_google": "Модель Google по умолчанию",
        "model_pollinations": "Модель Pollinations (для .igp)",
        "quality": "Качество загружаемых фото (для .ig)",
        "prefix": "Префикс промпта (стиль и т.д.)",
        "storage_mode": "Режим хранения истории. 1. Base64 - надежно, но занимает много хранилища (размер бекапа юзербота может значительно увеличится). 2. URL - экономно, занимает мало хранилища, но не так надёжно, как первый вариант. 3. None - не сохранять историю",
        "history_limit": "Лимит записей в истории",
        "custom_emojis": "Использовать premium эмодзи exteragram (отключите если вас банит за ссылки в чатах)",
        "use_quote": "Использовать форматирование цитат (blockquote)",
        
        # Генерация
        "gen_new": '<blockquote><a href="tg://emoji?id=5431456208487716895">🎨</a> <b>Генерация...</b></blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>',
        
        "gen_var": '<blockquote><a href="tg://emoji?id=5431456208487716895">🎨</a> <b>Генерация (Новый вариант)...</b></blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>',
        
        "success": '<blockquote><a href="tg://emoji?id=5427009714745517609">✅</a> <b>Готово!</b></blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>',
        
        "success_with_text": '<blockquote><a href="tg://emoji?id=5427009714745517609">✅</a> <b>Готово!</b></blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>\n\n📜 <b>Ответ ИИ (Стр. {}/{}):</b>\n<blockquote expandable>{}</blockquote>',
        
        # Редактирование
        "edit_new": '<blockquote><a href="tg://emoji?id=5431456208487716895">🎨</a> <b>Редактирование...</b></blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>',
        
        "edit_var": '<blockquote><a href="tg://emoji?id=5431456208487716895">🎨</a> <b>Редактирование (Новый вариант)...</b></blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>',
        
        "edit_success": '<blockquote><a href="tg://emoji?id=5775949822993371030">🖼</a> <b>Изображение отредактировано!</b></blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>',
        
        "edit_success_text": '<blockquote><a href="tg://emoji?id=5775949822993371030">🖼</a> <b>Изображение отредактировано!</b></blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>\n\n📜 <b>Ответ ИИ (Стр. {}/{}):</b>\n<blockquote expandable>{}</blockquote>',

        # Только текст / Ошибки
        "only_text_response": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>Изображение не сгенерировано (только текст):</b></blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>\n\n📜 <b>Ответ ИИ (Стр. {}/{}):</b>\n<blockquote expandable>{}</blockquote>',
        
        "error_no_data": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка:</b> Данные не получены.</blockquote>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>',

        "uploading": '<blockquote><a href="tg://emoji?id=5433614747381538714">📤</a> <b>Обработка и загрузка...</b></blockquote>',
        "uploading_wait": '<blockquote><a href="tg://emoji?id=5433614747381538714">📤</a> <b>Лимит хостинга. Ждем {}сек...</b></blockquote>',
        
        "error": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка:</b></blockquote>\n<blockquote expandable>{}</blockquote>',
        
        "error_censored": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка (Цензура):</b></blockquote>\n<blockquote expandable>{}</blockquote>\n<i>Попробуйте изменить запрос.</i>',
        
        "error_long": '<blockquote><a href="tg://emoji?id=5210952531676504517">❌</a> <b>Ошибка слишком длинная!</b></blockquote>\nСкачайте лог ниже.',
        
        # История
        "history_empty": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>История пуста!</b>',
        "history_disabled": '<blockquote><a href="tg://emoji?id=5420323339723881652">⚠️</a> <b>История выключена</b></blockquote>\nВключите <code>storage_mode</code> в <code>.cfg ImageGen</code>',
        "history_disabled_warn": '\n\n<a href="tg://emoji?id=5420323339723881652">⚠️</a> <i>История выключена, новые записи сохраняться не будут.</i>',
        
        "history_cleared": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>История очищена!</b>',
        "history_cleared_n": '<a href="tg://emoji?id=5427009714745517609">✅</a> <b>Удалено последних записей: {}</b>',
        
        "history_item": '<a href="tg://emoji?id=5775949822993371030">🖼</a> <b>История [{}/{}]</b>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>',
        
        "history_item_text": '<a href="tg://emoji?id=5775949822993371030">🖼</a> <b>История [{}/{}]</b>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>\n\n📜 <b>Ответ ИИ (Стр. {}/{}):</b>\n<blockquote expandable>{}</blockquote>',
        
        "history_text_only": '📝 <b>История (Текст) [{}/{}]</b>\n<blockquote><a href="tg://emoji?id=5361837567463399422">🔮</a> <b>Модель:</b> {}</blockquote>\n<blockquote expandable>📝 <b>Промпт:</b> <i>{}</i></blockquote>\n\n📜 <b>Ответ ИИ (Стр. {}/{}):</b>\n<blockquote expandable>{}</blockquote>',
        
        "img_load_fail": "\n\n⚠️ <b>Ошибка:</b> Изображение недоступно (ссылка истекла или невалидна).",
        
        "no_api": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Не установлен API ключ для Google!</b>',
        
        # Кнопки (Обычные эмодзи)
        "btn_regen": "🔄 Еще вариант",
        "btn_back": "🔙 Меню",
        "btn_list": "📂 Список",
        "btn_clear": "🗑 Очистить все",
        "btn_del_one": "🗑",
        "btn_close": "❌ Закрыть",
        "btn_loading": "🕘",
        "btn_slideshow": "🎞 Галерея",
        "btn_log": "📥 Лог в Избранное",
        "log_caption": '<a href="tg://emoji?id=5956561916573782596">📄</a> <b>Полный лог ошибки ImageGen</b>',
        "btn_back_hist": "🔙 В историю",
        "btn_model": "⚙️ Модель",
        "select_model": '<blockquote><a href="tg://emoji?id=5341715473882955310">⚙️</a> <b>Выберите модель для перегенерации:</b></blockquote>',
        "model_hidden_warn": '\n\n<a href="tg://emoji?id=5420323339723881652">⚠️</a> <i>Модели Pollinations скрыты, так как они не поддерживают редактирование изображений.</i>',
        "arg_err": '<a href="tg://emoji?id=5210952531676504517">❌</a> <b>Аргумент должен быть числом > 0</b>',
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", lambda: self.strings("api_key"), validator=loader.validators.Hidden()),
            loader.ConfigValue("model_google", "gemini-2.5-flash-image", lambda: self.strings("model_google"), validator=loader.validators.Choice([
                "gemini-2.5-flash-image",
                "gemini-2.5-flash-image-preview",
                "gemini-3-pro-image-preview",
                "nano-banana-pro-preview"
            ])),
            loader.ConfigValue("model_pollinations", "flux", lambda: self.strings("model_pollinations"), validator=loader.validators.Choice([
                "flux", "turbo", "midjourney", "deliberate"
            ])),
            loader.ConfigValue("storage_mode", "None", lambda: self.strings("storage_mode"), validator=loader.validators.Choice(["Base64", "URL", "None"])),
            loader.ConfigValue("history_limit", 20, lambda: self.strings("history_limit"), validator=loader.validators.Integer(minimum=1)),
            loader.ConfigValue("quality", "Low", lambda: self.strings("quality"), validator=loader.validators.Choice(["Low", "Medium", "High", "Original"])),
            loader.ConfigValue("prefix", "", lambda: self.strings("prefix")),
            loader.ConfigValue("custom_emojis", True, lambda: self.strings("custom_emojis"), validator=loader.validators.Boolean()),
            loader.ConfigValue("use_quote", True, lambda: self.strings("use_quote"), validator=loader.validators.Boolean()),
        )
        self.sessions = {}
        self.url_cache = {}
        self.error_cache = {}
        self._upload_lock = asyncio.Lock()
        self._last_up_time = 0

    async def client_ready(self, client, db):
        self._client = client
        self.db = db

    def _get_str(self, key, *args):
        text = self.strings(key).format(*args)
        if not self.config["custom_emojis"]:
            text = re.sub(r'<a href="tg://emoji\?id=\d+">(.+?)</a>', r'\1', text)
        if not self.config["use_quote"]:
            text = text.replace("<blockquote>", "").replace("</blockquote>", "")
            text = text.replace("<blockquote expandable>", "")
        return text

    def _resize_image(self, img_bytes):
        setting = self.config["quality"]
        if setting == "Original": return img_bytes
        presets = {"Low": (800, 75), "Medium": (1024, 85), "High": (1280, 90)}
        size, qual = presets.get(setting, (800, 75))
        try:
            img = Image.open(io.BytesIO(img_bytes))
            img.thumbnail((size, size))
            out = io.BytesIO()
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            img.save(out, format='JPEG', quality=qual)
            return out.getvalue()
        except: return img_bytes

    def _smart_split(self, text, limit=800):
        if not text: return []
        chunks = []
        current_chunk = ""
        for word in text.split(' '):
            if len(current_chunk) + len(word) < limit:
                current_chunk += word + " "
            else:
                chunks.append(current_chunk)
                current_chunk = word + " "
        if current_chunk: chunks.append(current_chunk)
        return chunks

    # --- UPLOADERS ---
    
    async def _up_x0(self, session, img_bytes):
        data = aiohttp.FormData()
        data.add_field('file', img_bytes, filename='image.png', content_type='image/png')
        try:
            async with session.post('https://x0.at', data=data, timeout=30) as resp:
                if resp.status == 200: return await resp.text()
        except: pass
        return None

    async def _up_tmpfiles(self, session, img_bytes):
        data = aiohttp.FormData()
        data.add_field('file', img_bytes, filename='image.jpg', content_type='image/jpeg')
        try:
            async with session.post('https://tmpfiles.org/api/v1/upload', data=data, timeout=30) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    url = res['data']['url']
                    return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        except: pass
        return None

    async def _up_catbox(self, session, img_bytes):
        data = aiohttp.FormData()
        data.add_field('reqtype', 'fileupload')
        data.add_field('fileToUpload', img_bytes, filename='image.png', content_type='image/png')
        try:
            async with session.post('https://catbox.moe/user/api.php', data=data, timeout=60) as resp:
                if resp.status == 200:
                    return await resp.text()
                else:
                    logger.error(f"Catbox Error: {resp.status} - {await resp.text()}")
        except Exception as e:
            logger.error(f"Catbox Exception: {e}")
        return None

    async def _up_0x0(self, session, img_bytes):
        data = aiohttp.FormData()
        data.add_field('file', img_bytes, filename='image.png', content_type='image/png')
        try:
            async with session.post('https://0x0.st', data=data, timeout=30) as resp:
                if resp.status == 200: return await resp.text()
        except: pass
        return None

    async def _upload_image(self, img_bytes, permanent=False, target=None):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with aiohttp.ClientSession(headers=headers) as session:
            
            # Если это постоянная загрузка (URL режим) - используем лок и таймер
            if permanent:
                async with self._upload_lock:
                    now = time.time()
                    diff = now - self._last_up_time
                    if diff < 15:
                        wait_time = 15 - diff
                        if target:
                            # Уведомляем пользователя
                            try:
                                await target.edit(self._get_str("uploading_wait", int(wait_time+1)), reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])
                            except: pass
                        await asyncio.sleep(wait_time)
                    
                    self._last_up_time = time.time()
                    
                    # URL Mode Order
                    queue = [self._up_catbox, self._up_0x0, self._up_x0]
                    for uploader in queue:
                        try:
                            url = await uploader(session, img_bytes)
                            if url and url.startswith("http"): return url.strip()
                        except: continue
                    return None # Failed all permanent
            
            else:
                # Temporary Mode (Fast, no lock)
                queue = [self._up_x0, self._up_tmpfiles, self._up_catbox, self._up_0x0]
                for uploader in queue:
                    try:
                        url = await uploader(session, img_bytes)
                        if url and url.startswith("http"): return url.strip()
                    except: continue
                return None

    # --- APIs ---
    async def _call_google(self, model_name: str, prompt: str, input_image_bytes=None):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.config['api_key']}"
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
                        return await resp.json()
                except Exception as e: return {"error": {"message": str(e)}}
            return {"error": {"message": "Resource exhausted (429)"}}

    async def _call_pollinations(self, model_name: str, prompt: str):
        seed = random.randint(0, 999999999)
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=1280&height=1280&seed={seed}&model={model_name}&nologo=True"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=60) as resp:
                    if resp.status == 200: return await resp.read()
                    else:
                        text = await resp.text()
                        return {"error": {"message": f"Pollinations Error {resp.status}: {text[:200]}"}}
            except Exception as e: return {"error": {"message": str(e)}}

    # --- COMMANDS ---

    @loader.command(ru_doc="<промпт> [реплай на фото] - Генерация или редактирование через модели Google (Gemini Image или же Nano banana)")
    async def ig(self, message: Message):
        """Generate via Google (Gemini)"""
        await self._init_gen(message, provider="google")

    @loader.command(ru_doc="<промпт> - Генерация через Pollinations")
    async def igp(self, message: Message):
        """Generate via Pollinations"""
        await self._init_gen(message, provider="pollinations")

    @loader.command(ru_doc="[N] - Очистить историю (все или N последних)")
    async def igclear(self, message: Message):
        """[N] - Clear history (all or last N)"""
        args = utils.get_args_raw(message)
        history = self.db.get("ImageGen", "history", [])
        
        if not history: return await utils.answer(message, self._get_str("history_empty"))

        if not args:
            self.db.set("ImageGen", "history", [])
            self.url_cache.clear()
            return await utils.answer(message, self._get_str("history_cleared"))
        
        try:
            n = int(args)
            if n <= 0: raise ValueError
        except:
            return await utils.answer(message, self._get_str("arg_err"))
        
        new_history = history[:-n]
        self.db.set("ImageGen", "history", new_history)
        await utils.answer(message, self._get_str("history_cleared_n", n))

    async def _init_gen(self, message, provider):
        args = utils.get_args_raw(message)
        if not args and not self.config["prefix"]: return await utils.answer(message, "Введите промпт")
        
        if provider == "google" and not self.config["api_key"]:
            return await utils.answer(message, self._get_str("no_api"))
        
        user_prompt = args.strip() if args.strip() else "..."
        full_prompt = (self.config["prefix"] + " " + args).strip()
        
        input_bytes = None
        if provider == "google":
            reply = await message.get_reply_message()
            if (reply and reply.media) or message.media:
                target = reply if reply and reply.media else message
                try:
                    if target.photo or (target.document and target.document.mime_type.startswith('image/')):
                        input_bytes = await self._client.download_media(target, file=bytes)
                except: pass

        model_name = self.config["model_google"] if provider == "google" else self.config["model_pollinations"]
        status_key = "edit_new" if input_bytes else "gen_new"

        msg = await self.inline.form(
            text=self._get_str(status_key, utils.escape_html(user_prompt), model_name),
            message=message,
            reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]]
        )
        
        sid = str(uuid.uuid4())
        self.sessions[sid] = {
            "provider": provider,
            "api_prompt": full_prompt, 
            "display_prompt": user_prompt, 
            "images": [], 
            "index": -1, 
            "input_img": input_bytes, 
            "from_history": False,
            "model": model_name,
            "text_page": 0
        }
        await self._process_gen(msg, sid)

    async def _process_gen(self, target, sid):
        if sid not in self.sessions: return await self._safe_close(target)
        session = self.sessions[sid]
        provider = session["provider"]
        model = session["model"]
        
        try:
            img_bytes = None
            text_resp = ""

            if provider == "google":
                data = await self._call_google(model, session["api_prompt"], session.get("input_img"))
                if isinstance(data, dict) and "error" in data:
                    raise ValueError(json.dumps(data, indent=2, ensure_ascii=False))
                try:
                    parts = data["candidates"][0]["content"]["parts"]
                    img_b64 = None
                    for part in parts:
                        if "inlineData" in part: img_b64 = part["inlineData"]["data"]
                        if "text" in part: text_resp += part["text"]
                    if img_b64: img_bytes = base64.b64decode(img_b64)
                    elif not text_resp: raise ValueError("No data found")
                except Exception as e:
                     if not isinstance(e, ValueError): raise ValueError(f"Structure Error: {data}")
                     raise e

            elif provider == "pollinations":
                data = await self._call_pollinations(model, session["api_prompt"])
                if isinstance(data, dict) and "error" in data:
                    raise ValueError(data["error"]["message"])
                img_bytes = data
            
            # --- Saving Logic ---
            storage = str(self.config["storage_mode"])
            hist_id = str(uuid.uuid4())
            
            db_b64 = None
            db_url = None
            display_url = None
            
            if hasattr(target, "edit"):
                await target.edit(self._get_str("uploading"), reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])

            # 1. URL Mode (Try Permanent)
            if storage == "URL" and img_bytes:
                db_url = await self._upload_image(img_bytes, permanent=True, target=target)
                if db_url:
                    display_url = db_url 
                else:
                    # FALLBACK: If perm upload failed, convert to Base64 mode logic for this item
                    # to prevent losing the image in history
                    db_b64 = base64.b64encode(img_bytes).decode('utf-8')
                    # Try uploading to temp for display
                    display_url = await self._upload_image(img_bytes, permanent=False)
            
            # 2. Base64 Mode
            elif storage == "Base64" and img_bytes:
                db_b64 = base64.b64encode(img_bytes).decode('utf-8')
                display_url = await self._upload_image(img_bytes, permanent=False)

            # 3. None Mode / Fallback
            if not display_url and img_bytes:
                display_url = await self._upload_image(img_bytes, permanent=False)
            
            if not display_url and not img_bytes:
                display_url = "https://raw.githubusercontent.com/h-m-256/repository/refs/heads/main/media/empty.png"

            if storage != "None":
                history = self.db.get("ImageGen", "history", [])
                history.append({
                    "id": hist_id, 
                    "prompt": session["display_prompt"], 
                    "bytes": db_b64, 
                    "url": db_url,
                    "text_resp": text_resp,
                    "provider": provider,
                    "model": model,
                    "is_edit": bool(session.get("input_img"))
                })
                limit = self.config["history_limit"]
                self.db.set("ImageGen", "history", history[-limit:])
            
            if display_url:
                self.url_cache[hist_id] = display_url

            session["images"].append({"url": display_url, "text": text_resp})
            session["index"] = len(session["images"]) - 1
            session["text_page"] = 0
            
            await self._update_gen_view(target, sid)

        except Exception as e:
            error_text = str(e)
            kb = []
            
            censor_keys = ["block reason", "prohibited content", "violated Google's"]
            if any(k in error_text for k in censor_keys):
                text_to_show = self._get_str("error_censored", utils.escape_html(error_text))
            else:
                text_to_show = self._get_str("error", utils.escape_html(error_text))
            
            if len(error_text) > 1000:
                err_id = str(uuid.uuid4())
                self.error_cache[err_id] = error_text
                text_to_show = self._get_str("error_long")
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
            await self._client.send_file("me", file, caption=self._get_str("log_caption"))
            await call.answer("Лог отправлен в Избранное!")
        except Exception as e: await call.answer(f"Failed: {e}", show_alert=True)

    async def _update_gen_view(self, target, sid):
        if sid not in self.sessions: return
        s = self.sessions[sid]
        idx = s["index"]
        
        current_data = s["images"][idx]
        img_url = current_data.get("url")
        ai_text = current_data.get("text", "")
        safe_prompt = utils.escape_html(s["display_prompt"])
        model_name = s.get("model", "Unknown")
        is_edit = s.get("input_img") is not None
        
        text_page = s.get("text_page", 0)
        chunk_size = 800
        text_chunks = self._smart_split(ai_text, 800)
        total_text_pages = len(text_chunks)
        if text_page >= total_text_pages: text_page = max(0, total_text_pages - 1)
        s["text_page"] = text_page
        current_text = text_chunks[text_page] if text_chunks else ""
        
        is_empty_img = "empty.png" in str(img_url)

        if not is_empty_img:
            if is_edit: key = "edit_success_text" if ai_text else "edit_success"
            else: key = "success_with_text" if ai_text else "success"
        else:
            if ai_text: key = "only_text_response"
            else: key = "error_no_data"

        if ai_text:
            text_to_show = self._get_str(key, model_name, safe_prompt, text_page + 1, total_text_pages, utils.escape_html(current_text.strip()))
        else:
             text_to_show = self._get_str(key, model_name, safe_prompt)
        
        kb = []
        total_imgs = len(s["images"])
        
        if total_imgs > 1:
            nav_row = []
            nav_row.append({"text": "⬅️ Вариант", "callback": self._nav_gen_cb, "args": (sid, -1)})
            nav_row.append({"text": f"{idx + 1}/{total_imgs}", "callback": self._dummy_cb})
            nav_row.append({"text": "Вариант ➡️", "callback": self._nav_gen_cb, "args": (sid, 1)})
            kb.append(nav_row)
        
        if total_text_pages > 1:
             text_nav = []
             text_nav.append({"text": "📝 <", "callback": self._nav_text_cb, "args": (sid, -1)})
             text_nav.append({"text": f"Стр {text_page + 1}/{total_text_pages}", "callback": self._dummy_cb})
             text_nav.append({"text": "> 📝", "callback": self._nav_text_cb, "args": (sid, 1)})
             kb.append(text_nav)

        ctrl_row = []
        ctrl_row.append({"text": self.strings("btn_regen"), "callback": self._regen_cb, "args": (sid,)})
        ctrl_row.append({"text": self.strings("btn_model"), "callback": self._model_menu, "args": (sid,)})
        kb.append(ctrl_row)
        
        if s.get("from_history"):
            kb.append([{"text": self.strings("btn_back_hist"), "callback": self._back_to_menu}])
        
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

        try:
            await target.edit(
                text=text_to_show,
                photo=img_url,
                reply_markup=kb,
                file=None if not img_url else None
            )
        except Exception as e:
            if "WebpageCurlFailed" in str(e) or "MediaCaptionTooLong" in str(e):
                error_msg = self.strings("img_load_fail")
                await target.edit(
                    text=text_to_show + error_msg,
                    reply_markup=kb,
                    file=None
                )
            else:
                await target.edit(text=f"Render Error: {e}", reply_markup=kb)

    # --- NAV HANDLERS ---
    async def _nav_gen_cb(self, call: InlineCall, sid, direction):
        if sid not in self.sessions: return await call.answer("Expired")
        s = self.sessions[sid]
        new_idx = s["index"] + direction
        if 0 <= new_idx < len(s["images"]):
            s["index"] = new_idx
            s["text_page"] = 0
            await self._update_gen_view(call, sid)
        else: await call.answer("Край")

    async def _nav_text_cb(self, call: InlineCall, sid, direction):
        if sid not in self.sessions: return await call.answer("Expired")
        s = self.sessions[sid]
        idx = s["index"]
        ai_text = s["images"][idx].get("text", "")
        
        text_chunks = self._smart_split(ai_text, 800)
        total_pages = len(text_chunks)
        
        new_page = s["text_page"] + direction
        if 0 <= new_page < total_pages:
            s["text_page"] = new_page
            await self._update_gen_view(call, sid)
        else: await call.answer("Край текста")

    # --- UNIVERSAL MODEL SWITCHER ---
    async def _model_menu(self, call: InlineCall, sid):
        if sid not in self.sessions: return await call.answer("Expired", show_alert=True)
        s = self.sessions[sid]
        is_edit_mode = s.get("input_img") is not None
        
        kb = [
            [{"text": "🍌 Nano Banana Pro", "callback": self._set_model_cb, "args": (sid, "nano-banana-pro-preview", "google")}],
            [{"text": "💎 Gemini 3 Pro", "callback": self._set_model_cb, "args": (sid, "gemini-3-pro-image-preview", "google")}],
            [{"text": "⚡️ Gemini 2.5 Flash", "callback": self._set_model_cb, "args": (sid, "gemini-2.5-flash-image", "google")}]
        ]
        
        text_msg = self._get_str("select_model")
        
        if not is_edit_mode:
            kb.extend([
                [{"text": "🌌 Flux (Pollinations)", "callback": self._set_model_cb, "args": (sid, "flux", "pollinations")}],
                [{"text": "🚀 Turbo (Pollinations)", "callback": self._set_model_cb, "args": (sid, "turbo", "pollinations")}],
                [{"text": "🎨 Midjourney (Pollinations)", "callback": self._set_model_cb, "args": (sid, "midjourney", "pollinations")}],
                [{"text": "🎭 Deliberate (Pollinations)", "callback": self._set_model_cb, "args": (sid, "deliberate", "pollinations")}]
            ])
        else:
            text_msg += self._get_str("model_hidden_warn")
            
        kb.append([{"text": "🔙 Назад", "callback": self._back_to_gen, "args": (sid,)}])
        await call.edit(text=text_msg, reply_markup=kb)

    async def _set_model_cb(self, call: InlineCall, sid, model_name, provider):
        if sid not in self.sessions: return await call.answer("Expired", show_alert=True)
        self.sessions[sid]["model"] = model_name
        self.sessions[sid]["provider"] = provider
        await self._regen_cb(call, sid)

    async def _back_to_gen(self, call: InlineCall, sid):
        if sid not in self.sessions: return await call.answer("Expired")
        await self._update_gen_view(call, sid)

    async def _regen_cb(self, call: InlineCall, sid):
        if sid not in self.sessions: return await call.answer("Expired", show_alert=True)
        s = self.sessions[sid]
        status_key = "edit_var" if s.get("input_img") else "gen_var"
        await call.answer(f"Генерация ({s['model']})...")
        await call.edit(
            self._get_str(status_key, utils.escape_html(s["display_prompt"]), s["model"]), 
            reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]]
        )
        await self._process_gen(call, sid)

    # --- HISTORY ---
    @loader.command(ru_doc=" - История генераций")
    async def ighist(self, message: Message):
        """View history"""
        history = self.db.get("ImageGen", "history", [])
        storage = str(self.config["storage_mode"])
        
        if not history: 
            if storage == "None":
                return await utils.answer(message, self._get_str("history_disabled"))
            return await utils.answer(message, self._get_str("history_empty"))
        
        msg = await self.inline.form(self._get_str("uploading"), message=message, reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])
        
        class FakeCall:
            def __init__(self, msg): self.message = msg
            async def edit(self, *args, **kwargs): await self.message.edit(*args, **kwargs)
            async def answer(self, *args, **kwargs): pass
            async def delete(self): await self.message.delete()
        
        await self._render_history_slide(FakeCall(msg), 0, 0)

    async def _show_history_menu(self, target, page=0):
        history = self.db.get("ImageGen", "history", [])
        text = self._get_str("history_empty") if not history else "<b>📝 История генераций:</b>"
        
        if str(self.config["storage_mode"]) == "None":
            text += self._get_str("history_disabled_warn")

        list_img = "https://raw.githubusercontent.com/h-m-256/repository/refs/heads/main/media/list_mode.png"
        
        kb = []
        if history:
            limit = 5
            rev_history = list(reversed(history))
            total_items = len(rev_history)
            total_pages = (total_items + limit - 1) // limit
            
            if page < 0: page = 0
            if page >= total_pages: page = max(0, total_pages - 1)
            
            offset = page * limit
            chunk = rev_history[offset : offset + limit]
            
            for e in chunk:
                p = e.get('prompt', '...')
                prov = e.get("provider", "google")
                is_edit = e.get("is_edit", False)
                if not e.get("bytes") and not e.get("url"): icon = "📝"
                elif is_edit: icon = "✏️"
                elif prov == "pollinations": icon = "💠"
                else: icon = "🖼"
                
                prompt_preview = (p[:20] + '..') if len(p) > 20 else p
                kb.append([{"text": f"{icon} {utils.escape_html(prompt_preview)}", "callback": self._view_hist_item, "args": (e['id'],)}])
            
            nav_row = []
            if page > 0:
                nav_row.append({"text": "⬅️", "callback": self._menu_nav_cb, "args": (page - 1,)})
            if total_pages > 1:
                nav_row.append({"text": f"{page + 1}/{total_pages}", "callback": self._dummy_cb})
            if page < total_pages - 1:
                nav_row.append({"text": "➡️", "callback": self._menu_nav_cb, "args": (page + 1,)})
            if nav_row: kb.append(nav_row)

            kb.append([{"text": self.strings("btn_slideshow"), "callback": self._start_slideshow}])
            kb.append([{"text": self.strings("btn_clear"), "callback": self._clear_all_cb}])
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])

        await target.edit(text, reply_markup=kb, photo=list_img)

    async def _menu_nav_cb(self, call: InlineCall, page):
        await self._show_history_menu(call, page)

    async def _start_slideshow(self, call: InlineCall):
        history = self.db.get("ImageGen", "history", [])
        if not history: return await call.answer("Empty")
        await self._render_history_slide(call, 0, 0)

    async def _view_hist_item(self, call: InlineCall, item_id):
        history = self.db.get("ImageGen", "history", [])
        idx = next((i for i, x in enumerate(history) if x["id"] == item_id), -1)
        if idx == -1: return await call.answer("Not found")
        await self._render_history_slide(call, idx, 0)

    async def _hist_nav_text(self, call: InlineCall, idx, direction, current_page):
        new_page = current_page + direction
        await self._render_history_slide(call, idx, new_page)

    async def _render_history_slide(self, call: InlineCall, index, text_page=0):
        history = self.db.get("ImageGen", "history", [])
        if not history: return await self._show_history_menu(call)
        
        index = max(0, min(index, len(history) - 1))
        item = history[index]
        
        img_url = self.url_cache.get(item["id"])
        
        if not img_url and item.get("url"):
            img_url = item.get("url")
            self.url_cache[item["id"]] = img_url
            
        if not img_url and item.get("bytes"):
            await call.edit(self._get_str("uploading"), reply_markup=[[{"text": self.strings("btn_loading"), "callback": self._dummy_cb}]])
            try:
                img_bytes = base64.b64decode(item["bytes"])
                img_url = await self._upload_image(img_bytes, permanent=False)
                if img_url: self.url_cache[item["id"]] = img_url
            except: pass
        
        if not img_url and not item.get("bytes"):
             img_url = "https://raw.githubusercontent.com/h-m-256/repository/refs/heads/main/media/empty.png"
        
        is_empty = "empty.png" in str(img_url)
        safe_prompt = utils.escape_html(item.get('prompt', 'image'))
        ai_text = item.get("text_resp", "")
        model_name = item.get("model", "Неизвестно")

        text_chunks = self._smart_split(ai_text, 800)
        total_text_pages = len(text_chunks)
        if text_page >= total_text_pages: text_page = max(0, total_text_pages - 1)
        if text_page < 0: text_page = 0
        current_text = text_chunks[text_page] if text_chunks else ""

        if not is_empty:
            if ai_text:
                text_to_show = self._get_str("history_item_text", index + 1, len(history), model_name, safe_prompt, text_page + 1, total_text_pages, utils.escape_html(current_text.strip()))
            else:
                text_to_show = self._get_str("history_item", index + 1, len(history), model_name, safe_prompt)
        else:
            text_to_show = self._get_str("history_text_only", index + 1, len(history), model_name, safe_prompt, text_page + 1, total_text_pages, utils.escape_html(current_text.strip()))

        kb = []
        
        if len(history) > 1:
            nav = []
            nav.append({"text": "⬅️", "callback": self._hist_nav, "args": (index - 1,)})
            nav.append({"text": f"{index + 1}/{len(history)}", "callback": self._dummy_cb})
            nav.append({"text": "➡️", "callback": self._hist_nav, "args": (index + 1,)})
            if nav: kb.append(nav)

        if total_text_pages > 1:
             text_nav = []
             text_nav.append({"text": "📝 <", "callback": self._hist_nav_text, "args": (index, -1, text_page)})
             text_nav.append({"text": f"Стр {text_page + 1}/{total_text_pages}", "callback": self._dummy_cb})
             text_nav.append({"text": "> 📝", "callback": self._hist_nav_text, "args": (index, 1, text_page)})
             kb.append(text_nav)

        actions = []
        actions.append({"text": self.strings("btn_del_one"), "callback": self._del_one_cb, "args": (item['id'],)})
        prov = item.get("provider", "google")
        actions.append({"text": self.strings("btn_regen"), "callback": self._regen_from_hist, "args": (item.get('prompt', ''), prov)})
        actions.append({"text": self.strings("btn_list"), "callback": self._back_to_menu})
        kb.append(actions)
        kb.append([{"text": self.strings("btn_close"), "callback": self._safe_close}])
        
        try:
            await call.edit(
                text=text_to_show,
                photo=img_url,
                reply_markup=kb,
                file=None if not img_url else None
            )
        except Exception as e:
            if "WebpageCurlFailed" in str(e) or "MediaCaptionTooLong" in str(e):
                error_msg = self.strings("img_load_fail")
                await call.edit(
                    text=text_to_show + error_msg,
                    reply_markup=kb,
                    file=None
                )
            else:
                await call.answer(f"Render Error: {e}", show_alert=True)

    async def _hist_nav(self, call: InlineCall, new_index):
        await self._render_history_slide(call, new_index, 0)

    async def _back_to_menu(self, call: InlineCall):
        await self._show_history_menu(call, 0)

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
            await self._render_history_slide(call, new_idx, 0)

    async def _regen_from_hist(self, call: InlineCall, prompt, provider):
        sid = str(uuid.uuid4())
        model = self.config["model_google"] if provider == "google" else self.config["model_pollinations"]
        self.sessions[sid] = {"provider": provider, "api_prompt": prompt, "display_prompt": prompt, "images": [], "index": -1, "input_img": None, "from_history": True, "model": model, "text_page": 0}
        await self._regen_cb(call, sid)

    async def _clear_all_cb(self, call: InlineCall):
        self.db.set("ImageGen", "history", [])
        self.url_cache.clear()
        await call.answer(self.strings("history_cleared"), show_alert=True)
        await self._show_history_menu(call)

    async def _dummy_cb(self, call: InlineCall): await call.answer()
    async def _safe_close(self, call: InlineCall):
        try: await call.delete()
        except: await call.answer("Error")
