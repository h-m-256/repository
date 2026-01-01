# meta developer: @h_m_256
# еще один вайбкод модуль (но еще больше кривой)
from .. import loader, utils
from telethon.tl.types import ChatBannedRights, Message, Channel, PeerChannel
from telethon.tl.functions.channels import EditBannedRequest, GetParticipantRequest, GetFullChannelRequest
from datetime import datetime, timedelta
import aiohttp
import json
import asyncio
import html
import re

@loader.tds
class AntiSpamMod(loader.Module):
    """антиспам модуль с проверкой с помощью геймини, кучу ненужных  настроек и т.д"""
    
    strings = {"name": "AntiSpam"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "use_inline_buttons", True, "Использовать инлайн кнопки (если выкл - просто текст)", validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "mute_hours", 1, "Время мута (часы)", validator=loader.validators.Integer(minimum=0)
            ),
            loader.ConfigValue(
                "ban_hours", 1, "Время бана (часы)", validator=loader.validators.Integer(minimum=0)
            ),
            loader.ConfigValue(
                "punish_type", "mute", "Наказание: mute / ban / warn", validator=loader.validators.Choice(["mute", "ban", "warn"])
            ),
            loader.ConfigValue(
                "log_chat", None, "ID чата для логов (числовой ID)"
            ),
            loader.ConfigValue(
                "log_level", "info", "Уровень логирования", 
                validator=loader.validators.Choice(["none", "errors", "info", "debug"])
            ),
            loader.ConfigValue(
                "spam_trigger", 5, "Сообщений подряд для детекта СПАМА", validator=loader.validators.Integer(minimum=1)
            ),
            loader.ConfigValue(
                "spam_period", 7, "Время (сек) накопления для СПАМА", validator=loader.validators.Integer(minimum=1)
            ),
            loader.ConfigValue(
                "flood_trigger", 5, "Сообщений подряд для детекта ФЛУДА", validator=loader.validators.Integer(minimum=1)
            ),
            loader.ConfigValue(
                "flood_period", 5, "Время (сек) накопления для ФЛУДА", validator=loader.validators.Integer(minimum=1)
            ),
            loader.ConfigValue(
                "enabled_chats", [], "ID чатов с включенным антиспамом", validator=loader.validators.Series(loader.validators.Integer())
            ),
            loader.ConfigValue(
                "whitelist", [], "ID пользователей-исключений (постоянные)", validator=loader.validators.Series(loader.validators.Integer())
            ),
            loader.ConfigValue(
                "delete_history_seconds", 0, "Удалять историю за N секунд (0=выкл)", validator=loader.validators.Integer(minimum=0)
            ),
            loader.ConfigValue(
                "ignore_channel_messages", True, "Игнорировать каналы/анонимов", validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "check_ban_rights", True, "Проверять права бота на бан", validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "ai_check_flood", False, "Проверять флуд через Gemini AI", validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "gemini_api_key", "", "API ключи Gemini (через запятую)", validator=loader.validators.Hidden()
            ),
            loader.ConfigValue(
                "gemini_model",
                "gemini-2.0-flash",
                "Модель Gemini",
                validator=loader.validators.Choice([
                    "gemini-2.0-flash", "gemini-2.0-pro", "gemini-2.5-flash", 
                    "gemini-2.5-flash-lite", "gemini-2.5-pro", 
                    "gemini-flash-latest", "gemini-pro-latest"
                ])
            ),
            loader.ConfigValue(
                "detect_sticker_spam", True, "Детект спама стикерами", validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "log_ai_non_flood", False, "Логировать пропуски AI", validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "timezone", "UTC+3", "Часовой пояс", validator=loader.validators.Choice([
                    "UTC+0", "UTC+3", "UTC+5", "UTC+8"
                ])
            ),
            loader.ConfigValue(
                "cleanup_delay", 5, "Задержка доп. очистки (сек)", validator=loader.validators.Integer(minimum=1, maximum=60)
            ),
            loader.ConfigValue(
                "show_deleted_count", True, "Показывать кол-во удаленных", validator=loader.validators.Boolean()
            )
        )
        self.spam_data = {}
        self.local_logs = []
        self.punished_users = {}
        self.processing_users = set()
        self.temp_whitelist = {}
        self.linked_channels = {}
        self.ai_check_in_progress = {}
        self.admin_cache = {} 
        self.alert_cache = {} 
        self.current_api_key_index = 0
        self.exhausted_keys = set()

    async def client_ready(self, client, db):
        self.client = client
        self._db = db
        self.me_id = (await client.get_me()).id

    def _get_api_keys(self):
        keys = self.config["gemini_api_key"]
        if not keys: return []
        if isinstance(keys, list): return keys
        return [k.strip() for k in keys.split(",") if k.strip()]
    
    def _get_next_api_key(self):
        keys = self._get_api_keys()
        if not keys: return None
        available_keys = [k for k in keys if k not in self.exhausted_keys]
        if not available_keys: return None
        self.current_api_key_index = self.current_api_key_index % len(available_keys)
        key = available_keys[self.current_api_key_index]
        self.current_api_key_index = (self.current_api_key_index + 1) % len(available_keys)
        return key
    
    def _apply_timezone(self, dt):
        try:
            offset = int(self.config["timezone"].replace("UTC", ""))
            return dt + timedelta(hours=offset)
        except: return dt
    
    def _format_datetime(self, dt):
        return self._apply_timezone(dt).strftime('%Y-%m-%d %H:%M:%S')

    def _normalize_chat_id(self, chat_id):
        s = str(chat_id)
        return int(s[4:]) if s.startswith("-100") else int(s)

    def _is_chat_enabled(self, chat_id):
        return self._normalize_chat_id(chat_id) in self.config["enabled_chats"]

    async def is_admin(self, chat_id, user_id):
        now = datetime.now()
        if (chat_id, user_id) in self.admin_cache:
            res, ts = self.admin_cache[(chat_id, user_id)]
            if (now - ts).total_seconds() < 300: return res
        try:
            p = await self.client(GetParticipantRequest(chat_id, user_id))
            res = getattr(p.participant, "admin_rights", None) is not None or getattr(p.participant, "rank", None) or isinstance(p.participant, (Channel, PeerChannel))
            self.admin_cache[(chat_id, user_id)] = (res, now)
            return res
        except: return False

    async def get_linked_channel(self, chat_id):
        if chat_id in self.linked_channels: return self.linked_channels[chat_id]
        try:
            full = await self.client(GetFullChannelRequest(chat_id))
            lid = getattr(full.full_chat, 'linked_chat_id', None)
            self.linked_channels[chat_id] = lid
            return lid
        except: return None

    async def check_flood_with_ai(self, messages, chat_id, user_id):
        key = (chat_id, user_id)
        if key in self.ai_check_in_progress: return False
        self.ai_check_in_progress[key] = True
        
        try:
            api_key = self._get_next_api_key()
            if not api_key: return True
            
            texts = [t for _, t, _, _ in messages if t and t.strip()]
            if len(texts) < 3: return True
            
            prompt = f"""Task: Detect malicious SPAM/FLOOD.
MESSAGES: {json.dumps(texts[:15], ensure_ascii=False)}
Reply strictly: "YES" (ban) or "NO" (skip).
"""
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['gemini_model']}:generateContent?key={api_key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ans = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").upper()
                        if "NO" in ans: return False
                        return True
                    elif resp.status == 429:
                        self.exhausted_keys.add(api_key)
                        return await self.check_flood_with_ai(messages, chat_id, user_id)
        except Exception as e:
            await self._log_ai(f"AI Error: {e}", "errors")
        finally:
            self.ai_check_in_progress.pop(key, None)
        return True

    async def _log_ai(self, msg, level="info"):
        if self.config["log_level"] == "none": return
        if self.config["log_level"] == "errors" and level != "errors": return
        if self.config["log_chat"]:
            try: await self.client.send_message(self.config["log_chat"], f"🤖 <b>AI ({level}):</b> {html.escape(str(msg))}")
            except: pass

    async def watcher(self, event):
        chat_id = getattr(event, "chat_id", None)
        if not getattr(event, "is_group", False) or not self._is_chat_enabled(chat_id): return
        if event.out: return
        
        sender_id = getattr(event, "sender_id", None)
        if not sender_id or sender_id == self.me_id: return

        if sender_id in self.config["whitelist"]: return
        if sender_id in self.temp_whitelist:
            if datetime.now() < self.temp_whitelist[sender_id]: return
            else: del self.temp_whitelist[sender_id]

        if (chat_id, sender_id) in self.processing_users or (chat_id, sender_id) in self.ai_check_in_progress: return

        if sender_id == await self.get_linked_channel(chat_id): return

        try: sender = await event.get_sender()
        except: return
        
        if self.config["ignore_channel_messages"] and isinstance(sender, Channel): return
        if await self.is_admin(chat_id, sender_id): return

        now = datetime.now()
        
        if (chat_id, sender_id) in self.punished_users:
            if (now - self.punished_users[(chat_id, sender_id)]).total_seconds() < 10: return

        user_data = self.spam_data.get((chat_id, sender_id), {"messages": []})
        if event.grouped_id and user_data.get("lgid") == event.grouped_id: return
        user_data["lgid"] = event.grouped_id
        
        media_type = self._get_media_type(event)
        text = getattr(event, "message", "") or ""
        user_data["messages"].append((now, text, event.id, media_type))
        
        mp = max(self.config["spam_period"], self.config["flood_period"])
        user_data["messages"] = [m for m in user_data["messages"] if (now - m[0]).total_seconds() <= mp]
        self.spam_data[(chat_id, sender_id)] = user_data
        
        msgs = user_data["messages"]
        count = len(msgs)
        
        reason = None
        
        if not reason and self.config["detect_sticker_spam"] and count >= self.config["spam_trigger"]:
            rec = msgs[-self.config["spam_trigger"]:]
            stk = [m[3] for m in rec if m[3] and m[3].startswith("sticker:")]
            if len(stk) >= self.config["spam_trigger"] and len(set(stk)) == 1:
                reason = "sticker_spam"

        if not reason and count >= self.config["spam_trigger"]:
            rec = msgs[-self.config["spam_trigger"]:]
            txt = [m[1] for m in rec if m[1]]
            if len(txt) >= self.config["spam_trigger"] and len(set(txt)) == 1:
                reason = "spam"

        ai_skip = False
        if not reason and count >= self.config["flood_trigger"]:
            rec = msgs[-self.config["flood_trigger"]:]
            if self.config["ai_check_flood"] and self._get_api_keys():
                is_bad = await self.check_flood_with_ai(rec, chat_id, sender_id)
                if is_bad: reason = "flood"
                else: ai_skip = True
            else:
                reason = "flood"

        if reason:
            if (chat_id, sender_id) in self.processing_users: return
            
            self.processing_users.add((chat_id, sender_id))
            self.punished_users[(chat_id, sender_id)] = now
            
            msg_ids = [m[2] for m in msgs if m[2]]
            del_content = [(m[1] if m[1] else f"[{m[3]}]") for m in msgs]
            
            chat_title = getattr(await event.get_chat(), 'title', 'Chat')
            
            alert_msg, log_msg = await self.punish(chat_id, chat_title, sender, reason, msg_ids, del_content)
            
            asyncio.create_task(self._delayed_cleanup(chat_id, sender_id, alert_msg, log_msg, len(msg_ids)))
            
            self.spam_data.pop((chat_id, sender_id), None)
            await asyncio.sleep(2)
            self.processing_users.discard((chat_id, sender_id))
            
        elif ai_skip and self.config["log_ai_non_flood"]:
            if self.config["log_chat"]:
                 u = self._escape(getattr(sender, 'first_name', str(sender_id)))
                 c = self._escape(getattr(await event.get_chat(), 'title', str(chat_id)))
                 await self.client.send_message(self.config["log_chat"], f"✅ <b>AI Пропустил:</b>\n👤 {u}\n💬 {c}")

    async def punish(self, chat_id, chat_title, user, reason, msg_ids, del_content):
        try: await self.client.delete_messages(chat_id, msg_ids)
        except: pass

        until = datetime.now() + timedelta(hours=self.config["mute_hours"] if self.config["punish_type"] == "mute" else self.config["ban_hours"])
        rights = ChatBannedRights(until_date=until, send_messages=True) if self.config["punish_type"] == "mute" else ChatBannedRights(until_date=until, view_messages=True)
        
        ptxt = "получил мут" if self.config["punish_type"] == "mute" else "забанен"
        try:
            await self.client(EditBannedRequest(chat_id, user.id, rights))
        except: ptxt = "(нет прав)"

        txt_tpl = "🛡 <a href='tg://user?id={}'>{}</a> {} за <b>{}</b>.\n⏳ До: {}\n🗑 Удалено: {}"
        uname = self._escape(getattr(user, 'first_name', 'User'))
        
        alert_text = txt_tpl.format(user.id, uname, ptxt, reason.upper(), self._format_datetime(until), len(msg_ids))
        self.alert_cache[(chat_id, user.id)] = alert_text

        alert_msg = None
        if self.config["use_inline_buttons"]:
            try:
                alert_msg = await self.inline.form(
                    text=alert_text, message=chat_id,
                    reply_markup=[[{"text": "🔓 Разбанить", "callback": self.unban_cb, "args": (chat_id, user.id)}]]
                )
            except: pass
        else:
            try: alert_msg = await self.client.send_message(chat_id, alert_text)
            except: pass

        log_msg = None
        if self.config["log_chat"]:
            log_idx = len(self.local_logs)
            self.local_logs.append(del_content)
            if len(self.local_logs) > 50: self.local_logs.pop(0)
            
            log_txt = (f"⛔ <b>Антиспам</b>\n👤 <a href='tg://user?id={user.id}'>{uname}</a>\n"
                       f"💬 {self._escape(chat_title)}\n⚠ {reason.upper()}\n🗑 Удалено: {len(msg_ids)}")
            
            if self.config["use_inline_buttons"]:
                try:
                    log_msg = await self.inline.form(
                        text=log_txt, message=self.config["log_chat"],
                        reply_markup=[[{"text": "📜 Лог сообщений", "callback": self.show_log_cb, "args": (log_idx,)}]]
                    )
                except: pass
            else:
                try: log_msg = await self.client.send_message(self.config["log_chat"], log_txt)
                except: pass
        
        return alert_msg, log_msg

    async def _delayed_cleanup(self, chat_id, user_id, alert_msg, log_msg, initial_count):
        await asyncio.sleep(self.config["cleanup_delay"])
        extra_count = 0
        try:
            msgs = []
            async for m in self.client.iter_messages(chat_id, from_user=user_id, limit=100):
                msgs.append(m.id)
            if msgs:
                extra_count = len(msgs)
                for i in range(0, len(msgs), 100):
                    await self.client.delete_messages(chat_id, msgs[i:i+100])
        except: pass
        
        total = initial_count + extra_count
        if extra_count > 0:
            new_text_end = f"\n🗑 Удалено: {total}"
            
            def update_txt(txt, new_cnt):
                return re.sub(r"🗑 Удалено: \d+", f"🗑 Удалено: {new_cnt}", txt)

            if alert_msg and self.config["show_deleted_count"]:
                try:
                    if (chat_id, user_id) in self.alert_cache:
                        self.alert_cache[(chat_id, user_id)] = update_txt(self.alert_cache[(chat_id, user_id)], total)
                    
                    if self.config["use_inline_buttons"]:
                        await self.client.edit_message(alert_msg.chat_id, alert_msg.id, update_txt(alert_msg.text, total))
                    else:
                        await alert_msg.edit(update_txt(alert_msg.text, total))
                except: pass

            if log_msg:
                try:
                    await self.client.edit_message(log_msg.chat_id, log_msg.id, update_txt(log_msg.text, total))
                except: pass

    async def unban_cb(self, call, chat_id, user_id):
        self.punished_users.pop((chat_id, user_id), None)
        self.processing_users.discard((chat_id, user_id))
        
        if self.config["check_ban_rights"] and not await self.has_ban_rights(chat_id, call.from_user.id):
             return await call.answer("❌ Нет прав!", show_alert=True)
        
        try:
            await self.client(EditBannedRequest(chat_id, user_id, ChatBannedRights(until_date=0)))
            
            adm = self._escape(call.from_user.first_name)
            txt = self.alert_cache.get((chat_id, user_id), "⚠️ <i>Информация устарела</i>")
            await call.edit(txt + f"\n\n<b>~ Снято админом {adm}</b>")
            self.alert_cache.pop((chat_id, user_id), None)
        except Exception as e:
            await call.answer(f"Error: {e}", show_alert=True)

    async def show_log_cb(self, call, idx):
        if idx >= len(self.local_logs): return await call.answer("Лог устарел", show_alert=True)
        
        msgs = self.local_logs[idx]
        text = "\n".join([f"• {self._escape(m[:100])}" for m in msgs])
        
        if len(text) > 190:
            await call.answer("Лог длинный, отправляю сообщением...", show_alert=True)
            try: await self.client.send_message(call.chat_id, f"📜 <b>Лог сообщений:</b>\n{text}")
            except: pass
        else:
            await call.answer(text, show_alert=True)

    @loader.command()
    async def asfree(self, message):
        """<time/off> - Добавить в вайтлист (время: 10m, 1h). Без времени - навсегда."""
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        uid = reply.sender_id if reply else (int(args.split()[0]) if args and args.split()[0].isdigit() else None)
        
        if not uid: return await utils.answer(message, "❌ Укажите ID или реплай.")
        
        self.punished_users.pop((message.chat_id, uid), None)
        self.processing_users.discard((message.chat_id, uid))
        
        time_arg = None
        for arg in args.split():
            if re.match(r"^\d+[smhd]$", arg):
                time_arg = arg
                break
        
        if time_arg:
            val = int(time_arg[:-1])
            unit = time_arg[-1]
            sec = val * (60 if unit == 'm' else 3600 if unit == 'h' else 86400 if unit == 'd' else 1)
            until = datetime.now() + timedelta(seconds=sec)
            self.temp_whitelist[uid] = until
            await utils.answer(message, f"✅ {uid} в вайтлисте на {time_arg}")
        else:
            if uid in self.config["whitelist"]:
                self.config["whitelist"].remove(uid)
                await utils.answer(message, f"➖ {uid} удален из WL")
            else:
                self.config["whitelist"].append(uid)
                await utils.answer(message, f"➕ {uid} добавлен в WL (навсегда)")

    @loader.command()
    async def antispamtoggle(self, message):
        """Вкл/Выкл в текущем чате"""
        cid = self._normalize_chat_id(message.chat_id)
        if cid in self.config["enabled_chats"]:
            self.config["enabled_chats"].remove(cid)
            await utils.answer(message, f"❌ AntiSpam OFF ({cid})")
        else:
            self.config["enabled_chats"].append(cid)
            await utils.answer(message, f"✅ AntiSpam ON ({cid})")

    async def has_ban_rights(self, chat_id, user_id):
        try:
            p = (await self.client(GetParticipantRequest(chat_id, user_id))).participant
            return getattr(p.admin_rights, 'ban_users', False) or False
        except: return False

    def _get_media_type(self, event):
        if getattr(event, 'sticker', None): return f"sticker:{getattr(event.sticker, 'id', 0)}"
        if getattr(event, 'photo', None): return "photo"
        return "media" if getattr(event, 'media', None) else None
    
    def _escape(self, text):
        return html.escape(str(text)) if text else "Unknown"