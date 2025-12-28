#meta developer: @h_m_256

import asyncio
import aiohttp
import io
import base64
import json
from PIL import Image
from .. import loader, utils
from telethon.tl.types import Message

@loader.tds
class ImageGenMod(loader.Module):
    """генерация/редактирование фото через модели google"""

    strings = {
        "name": "ImageGen",
        "_api_key": "Google AI Studio API key",
        "_model_name": "Model to use for generation",
        "_default_prompt": "Default prompt prefix",
        "no_api": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>API key not configured!</b>\n\nGet your API key at https://aistudio.google.com/ and add it to config",
        "generating": "<a href=\"tg://emoji?id=5386367538735104399\">⌛</a> <b>Generating/Editing image...</b>\n\n<i>Prompt: {}</i>",
        "error": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Error:</b>\n<code>{}</code>",
        "usage": "<a href=\"tg://emoji?id=5334882760735598374\">📝</a> <b>Usage:</b>\n<code>.ig [prompt]</code> (or reply to photo)\n\n<b>Example:</b>\n<code>.ig a cute cat in space</code>",
        "success": "<a href=\"tg://emoji?id=5427009714745517609\">✅</a> <b>Success!</b>\n\n<i>Prompt: {}</i>",
    }
    
    strings_ru = {
        "_api_key": "API ключ Google AI Studio",
        "_model_name": "Модель для генерации",
        "_default_prompt": "Префикс промпта по умолчанию",
        "no_api": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>API ключ не настроен!</b>\n\nПолучите API ключ на https://aistudio.google.com/ и добавьте в конфиг",
        "generating": "<a href=\"tg://emoji?id=5386367538735104399\">⌛</a> <b>Генерация/Редактирование...</b>\n\n<i>Промпт: {}</i>",
        "error": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Ошибка:</b>\n<code>{}</code>",
        "usage": "<a href=\"tg://emoji?id=5334882760735598374\">📝</a> <b>Использование:</b>\n<code>.ig [промпт]</code> (или реплай на фото)\n\n<b>Пример:</b>\n<code>.ig милый кот в космосе</code>",
        "success": "<a href=\"tg://emoji?id=5427009714745517609\">✅</a> <b>Готово!</b>\n\n<i>Промпт: {}</i>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "API_KEY",
                "",
                lambda: self.strings("_api_key"),
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "MODEL",
                "gemini-2.5-flash-image",
                lambda: self.strings("_model_name"),
                validator=loader.validators.Choice([
                    "gemini-2.5-flash-image",
                    "gemini-2.5-flash-image-preview",
                    "gemini-3-pro-image-preview",
                    "nano-banana-pro-preview",
                    "imagen-4.0-generate-001",
                    "imagen-4.0-ultra-generate-001",
                    "imagen-4.0-fast-generate-001"
                ]),
            ),
            loader.ConfigValue(
                "DEFAULT_PROMPT_PREFIX",
                "",
                lambda: self.strings("_default_prompt"),
            ),
        )

    async def client_ready(self, client, db):
        self._client = client

    async def _generate_image(self, prompt: str, image_bytes: bytes = None) -> bytes:
        if not self.config["API_KEY"]:
            raise ValueError("API key not configured")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['MODEL']}:generateContent"
        headers = {"Content-Type": "application/json"}
        full_prompt = self.config["DEFAULT_PROMPT_PREFIX"] + " " + prompt if self.config["DEFAULT_PROMPT_PREFIX"] else prompt
        
        parts = [{"text": full_prompt}]
        
        if image_bytes:
            parts.append({
                "inlineData": {
                    "mimeType": "image/png",
                    "data": base64.b64encode(image_bytes).decode("utf-8")
                }
            })

        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
        
        payload = {
            "contents": [{"parts": parts}],
            "safetySettings": safety_settings,
            "generationConfig": {
                "temperature": 1.0,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 8192,
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{url}?key={self.config['API_KEY']}", 
                headers=headers, 
                json=payload
            ) as response:
                data = await response.json()
                
                if response.status != 200:
                    raise ValueError(f"API Error {response.status}: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
                if "candidates" not in data or not data["candidates"]:
                    feedback = data.get("promptFeedback", "Hard filter triggered")
                    raise ValueError(f"No candidates. Feedback: {json.dumps(feedback, indent=2, ensure_ascii=False)}")
                
                candidate = data["candidates"][0]
                parts_out = candidate.get("content", {}).get("parts", [])
                
                for part in parts_out:
                    if "inlineData" in part:
                        return base64.b64decode(part["inlineData"]["data"])
                
                raise ValueError(f"No image in response. Response: {json.dumps(data, indent=2, ensure_ascii=False)}")

    @loader.command(ru_doc=" > Сгенерировать или изменить фото через AI")
    async def ig(self, message: Message):
        """Generate or edit image using AI"""
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        
        photo_bytes = None
        if message.photo:
            photo_bytes = await message.download_media(bytes)
        elif reply and reply.photo:
            photo_bytes = await reply.download_media(bytes)

        if not args and not photo_bytes:
            await utils.answer(message, self.strings("usage"))
            return
        
        if not self.config["API_KEY"]:
            await utils.answer(message, self.strings("no_api"))
            return
        
        status_msg = await utils.answer(message, self.strings("generating").format(args or "Image modification"))
        
        try:
            prompt = args if args else "enhance this image"
            
            image_res = await self._generate_image(prompt, photo_bytes)
            
            out_file = io.BytesIO(image_res)
            out_file.name = "ai_output.png"
            
            await self._client.send_message(
                message.peer_id,
                file=out_file,
                message=self.strings("success").format(prompt),
                reply_to=message.reply_to_msg_id,
                force_document=False
            )
            await status_msg.delete()
            
        except Exception as e:
            await utils.answer(status_msg, self.strings("error").format(str(e)[:3500]))