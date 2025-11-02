# meta developer: h_m_256.t.me && @RoflPlugins
# meta banner: https://i.imgur.com/barcode.jpg

from .. import loader, utils
from telethon.tl.types import Message

__version__ = (1, 4, 88)

MK_LANG_RU = {
    "а": "I", "б": "l", "в": "Il", "г": "lI", "д": "II", "е": "ll", "ё": "IIl",
    "ж": "lIl", "з": "IIll", "и": "Ill", "й": "lII", "к": "lIlI", "л": "IIlI",
    "м": "IllI", "н": "lIIl", "о": "lll", "п": "IIIl", "р": "IlIl", "с": "IIlIl",
    "т": "lIIlI", "у": "IllII", "ф": "IIIll", "х": "lIll", "ц": "IIlII", "ч": "IlII",
    "ш": "llll", "щ": "IIlIIl", "ъ": "llIl", "ы": "Illl", "ь": "lIIIl", "э": "IlIll",
    "ю": "IIlIll", "я": "IllIIl",
}

MK_LANG_EN = {
    "a": "Illll", "b": "IIIII", "c": "lIIII", "d": "IlIII", "e": "IIlIIlII",
    "f": "IIIllI", "g": "IlllI", "h": "lIllI", "i": "lllIl", "j": "IIIlI",
    "k": "lIIll", "l": "IllIl", "m": "IlIllI", "n": "lIlII", "o": "IIlIII",
    "p": "IllIII", "q": "lllII", "r": "IIIlll", "s": "IlIIl", "t": "lIIIlI",
    "u": "IllIIlI", "v": "IIlIllI", "w": "llIIlI", "x": "IlllIl", "y": "IIIlII",
    "z": "lIllII",
}

MK_LANG = {**MK_LANG_RU, **MK_LANG_EN}
REV_LANG = {v: k for k, v in MK_LANG.items()}


def to_barcode(text: str) -> str:
    """Перевод текста в штрихкодовый язык"""
    result = []
    words = text.split(" ")
    for word in words:
        if word.startswith(("/", "@", ".", "http")) and len(word) > 1:
            result.append(word)
        else:
            encoded = [MK_LANG.get(ch.lower(), ch) for ch in word]
            result.append("|".join(encoded))
    return " ".join(result)


def from_barcode(text: str) -> str:
    """Перевод из штрихкодового языка в обычный текст"""
    words = text.split(" ")
    result = []
    for word in words:
        if word.startswith(("/", "@", ".", "http")) and len(word) > 1:
            result.append(word)
        else:
            letters = word.split("|")
            decoded = [REV_LANG.get(letter, letter) for letter in letters]
            result.append("".join(decoded))
    return " ".join(result)


def is_barcode(text: str) -> bool:
    """Проверка, является ли текст штрихкодовым"""
    if not text:
        return False
    return "|" in text and any(char in text for char in ["I", "l"])


@loader.tds
class BarcodeLangMod(loader.Module):
    """порт шрихкодового языка от h_m_256.t.me 🙏🙏🙏🙏🙏🙏🙏🙏🙏🙏, оригинал @roflplugins"""

    strings = {
        "name": "BarcodeLang",
        "state": "<b>🔘 Штрихкодовый язык: {}</b>",
        "on": "✅ включен",
        "off": "❌ выключен",
        "translated": "<b>📊 Переведено:</b>\n<code>{}</code>",
        "to_barcode": "<b>📊 В штрихкод:</b>\n<code>{}</code>",
        "no_text": "<b>❌ Ответьте на сообщение или укажите текст</b>",
        "inline_title_encode": "📊 {preview}",
        "inline_title_decode": "📖 {preview}",
        "inline_desc_encode": "Текст → Штрихкод",
        "inline_desc_decode": "Штрихкод → Текст",
        "inline_help_title": "📊 Штрихкодовый переводчик",
        "inline_help_desc": "Введите текст для автоматического перевода",
        "inline_help_text": (
            "<b>💡 Штрихкодовый переводчик</b>\n\n"
            "<i>Введите текст после команды для автоматического перевода:\n"
            "• Обычный текст → штрихкод\n"
            "• Штрихкод → обычный текст</i>\n\n"
            "<b>Пример:</b>\n"
            "<code>@{bot} barcode привет</code>"
        ),
    }

    strings_ru = {
        "state": "<b>🔘 Штрихкодовый язык: {}</b>",
        "on": "✅ включен",
        "off": "❌ выключен",
        "translated": "<b>📊 Переведено:</b>\n<code>{}</code>",
        "to_barcode": "<b>📊 В штрихкод:</b>\n<code>{}</code>",
        "no_text": "<b>❌ Ответьте на сообщение или укажите текст</b>",
        "inline_title_encode": "📊 {preview}",
        "inline_title_decode": "📖 {preview}",
        "inline_desc_encode": "Текст → Штрихкод",
        "inline_desc_decode": "Штрихкод → Текст",
        "inline_help_title": "📊 Штрихкодовый переводчик",
        "inline_help_desc": "Введите текст для автоматического перевода",
        "inline_help_text": (
            "<b>💡 Штрихкодовый переводчик</b>\n\n"
            "<i>Введите текст после команды для автоматического перевода:\n"
            "• Обычный текст → штрихкод\n"
            "• Штрихкод → обычный текст</i>\n\n"
            "<b>Пример:</b>\n"
            "<code>@{bot} barcode привет</code>"
        ),
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "auto_translate",
                False,
                "Автоматически переводить все сообщения в штрихкодовый язык",
                validator=loader.validators.Boolean(),
            ),
        )

    async def client_ready(self, client, db):
        self._client = client
        self._db = db

    @loader.command(ru_doc="Включить/выключить автоматический перевод")
    async def blauto(self, message: Message):
        """Toggle automatic barcode translation"""
        current = self.config["auto_translate"]
        self.config["auto_translate"] = not current
        
        state = self.strings["on"] if not current else self.strings["off"]
        await utils.answer(message, self.strings["state"].format(state))

    @loader.command(ru_doc="[текст] - Перевести текст в штрихкодовый язык")
    async def bl(self, message: Message):
        """[text] - Translate text to barcode language"""
        args = utils.get_args_raw(message)
        
        if not args:
            if message.is_reply:
                reply = await message.get_reply_message()
                args = reply.text
            else:
                await utils.answer(message, self.strings["no_text"])
                return
        
        translated = to_barcode(args)
        await utils.answer(message, translated)

    @loader.command(ru_doc="Перевести сообщение из штрихкодового языка (ответ на сообщение)")
    async def dbl(self, message: Message):
        """Decode message from barcode language (reply to message)"""
        if not message.is_reply:
            args = utils.get_args_raw(message)
            if not args:
                await utils.answer(message, self.strings["no_text"])
                return
            text = args
        else:
            reply = await message.get_reply_message()
            text = reply.text
        
        if not text:
            await utils.answer(message, self.strings["no_text"])
            return
        
        decoded = from_barcode(text)
        await utils.answer(message, self.strings["translated"].format(decoded))

    @loader.watcher(only_messages=True, out=True)
    async def watcher(self, message: Message):
        """Автоматически переводит исходящие сообщения"""
        if not self.config["auto_translate"]:
            return
        
        if not message.text:
            return
        
        if message.text.startswith("."):
            return
        
        if is_barcode(message.text):
            return
        
        translated = to_barcode(message.text)
        await message.edit(translated)

    @loader.inline_handler(ru_doc="[текст] - Инлайн перевод в/из штрихкода (автоопределение)")
    async def barcode(self, query):
        """[text] - Inline translation to/from barcode (auto-detect)"""
        text = query.args.strip() if hasattr(query, 'args') else ""
        
        if not text:
            bot_username = (await self.inline.bot.get_me()).username
            return {
                "title": self.strings["inline_help_title"],
                "description": self.strings["inline_help_desc"],
                "message": self.strings["inline_help_text"].format(bot=bot_username),
                "thumb": "https://img.icons8.com/?size=100&id=kDMAGBvpqAyW&format=png&color=000000",
            }
        
        if is_barcode(text):
            translated = from_barcode(text)
            icon = "📖"
            description = self.strings["inline_desc_decode"]
        else:
            translated = to_barcode(text)
            icon = "📊"
            description = self.strings["inline_desc_encode"]
        
        preview = translated[:30] + ("..." if len(translated) > 30 else "")
        
        return {
            "title": self.strings[f"inline_title_{'decode' if is_barcode(text) else 'encode'}"].format(preview=preview),
            "description": description,
            "message": translated,
            "thumb": "https://emojiguide.org/images/emoji/7/1rw4x4s1lq61g7.png",
        }