import os
import telebot
from telebot import types
import imaplib
import email
from email.header import decode_header
import threading
import time
import re
import io
import html
from bs4 import BeautifulSoup
from database import EmailDatabase, ADMIN_ID, ALLOWED_DOMAINS

# --- КОНФИГУРАЦИЯ ---
EMAIL_USER = os.environ.get('EMAIL_USER', 'your_email@yandex.ru')
EMAIL_PASS = os.environ.get('EMAIL_PASS', 'YOUR_EMAIL_APP_PASSWORD_HERE')
IMAP_SERVER = 'imap.yandex.ru'

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', 'YOUR_BOT_TOKEN_HERE')

WEBAPP_URL = "https://tunnel3.dreampartners.online"

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)
email_db = EmailDatabase()

# --- ЛОГИКА УПРАВЛЕНИЯ ЯЩИКАМИ ---

def register_new_alias(user_id, email, force=False):
    email = email.lower().strip()
    
    # Check if taken
    existing_owner = email_db.get_owner(email)
    if existing_owner and existing_owner != user_id and not force:
        return False, "занято"
    
    # Check domain (unless admin main email)
    if email != EMAIL_USER:
        domain = email.split('@')[-1]
        if domain not in ALLOWED_DOMAINS:
            return False, "неверный домен"

    # Add to DB
    if email_db.add_alias(user_id, email):
        return True, "ок"
    return False, "ошибка базы данных"

def delete_user_alias(user_id, email):
    email = email.lower().strip()
    if email == EMAIL_USER and user_id == ADMIN_ID:
        return False, "нельзя удалить основной ящик"
    
    if email_db.delete_alias(user_id, email):
        return True, "удалено"
    return False, "не найдено или ошибка"

# --- КЛАСС РАБОТЫ С ПОЧТОЙ ---
class MailManager:
    def __init__(self):
        self.mail = None

    def connect(self):
        try:
            self.mail = imaplib.IMAP4_SSL(IMAP_SERVER)
            self.mail.login(EMAIL_USER, EMAIL_PASS)
            return True
        except Exception as e:
            print(f"IMAP Error: {e}")
            return False

    def get_last_uid(self):
        try:
            if not self.mail: self.connect()
            self.mail.select("INBOX")
            status, messages = self.mail.uid('search', None, "ALL")
            if status == "OK":
                uids = messages[0].split()
                if uids: return int(uids[-1])
            return 0
        except:
            return 0

    def get_emails_for_alias(self, alias, limit=20, offset=0):
        try:
            if not self.mail: self.connect()
            self.mail.select("INBOX")
            # Search by TO header
            # Note: This might be slow if mailbox is huge.
            # Using CHARSET UTF-8 for search if needed, but email addresses are ASCII usually.
            status, messages = self.mail.uid('search', None, f'(TO "{alias}")')
            
            if status == "OK":
                uids = messages[0].split()
                # Sort descending (newest first)
                uids.sort(key=int, reverse=True)
                
                # Pagination
                start = offset
                end = offset + limit
                page_uids = uids[start:end]
                
                result = []
                for uid in page_uids:
                    try:
                        res, msg_data = self.mail.uid('fetch', str(int(uid)), '(RFC822.HEADER)')
                        header_data = msg_data[0][1]
                        msg = email.message_from_bytes(header_data)
                        
                        subject = self.decode_str(msg["Subject"])
                        from_ = self.decode_str(msg["From"])
                        
                        result.append({
                            "uid": int(uid),
                            "subject": subject if subject else "(без темы)",
                            "from": from_ if from_ else "(неизвестно)"
                        })
                    except: pass
                
                return result, len(uids)
            return [], 0
        except Exception as e:
            print(f"Search Error: {e}")
            return [], 0

    def get_email_content(self, uid):
        try:
            if not self.mail: self.connect()
            self.mail.select("INBOX")
            res, msg_data = self.mail.uid('fetch', str(uid), '(RFC822)')
            if res == 'OK':
                return self.parse_email(msg_data[0][1])
            return None
        except:
            return None

    def decode_str(self, s):
        if s is None: return ""
        decoded_list = decode_header(s)
        header_value = ""
        for decoded, charset in decoded_list:
            if isinstance(decoded, bytes):
                try:
                    header_value += decoded.decode(charset or 'utf-8')
                except:
                    header_value += decoded.decode('utf-8', errors='ignore')
            else:
                header_value += str(decoded)
        return header_value

    def extract_email_address(self, raw_str):
        """Извлекает чистый email из строки вида 'Name <email@domain.com>'"""
        match = re.search(r'<([^>]+)>', raw_str)
        if match:
            return match.group(1).lower().strip()
        # Если скобок нет, возможно это просто email
        if '@' in raw_str:
            return raw_str.lower().strip()
        return None

    def parse_email(self, raw_email):
        msg = email.message_from_bytes(raw_email)
        
        subject = self.decode_str(msg["Subject"])
        from_ = self.decode_str(msg["From"])
        to_raw = self.decode_str(msg["To"])
        to_email = self.extract_email_address(to_raw)
        
        # Также проверяем X-Original-To или Delivered-To для точности пересылки
        if not to_email:
             delivered_to = msg.get("Delivered-To") or msg.get("X-Original-To")
             if delivered_to:
                 to_email = self.extract_email_address(str(delivered_to))

        body_text = ""
        body_html = None
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition"))
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        if content_type == "text/plain" and "attachment" not in disposition:
                            body_text += payload.decode('utf-8', errors='ignore')
                        elif content_type == "text/html" and "attachment" not in disposition:
                            body_html = payload
                except: pass
        else:
            payload = msg.get_payload(decode=True)
            if msg.get_content_type() == "text/html":
                body_html = payload
            else:
                body_text = payload.decode('utf-8', errors='ignore')

        if not body_text and body_html:
            try:
                soup = BeautifulSoup(body_html, "html.parser")
                body_text = soup.get_text(separator="\n").strip()
            except: pass

        return {
            "subject": subject,
            "from": from_,
            "to_raw": to_raw,
            "to_email": to_email,
            "text": body_text.strip(),
            "html": body_html
        }

# --- UI & LOGIC ---

def extract_links(html_bytes, text_body):
    """Ищет ссылки активации/подтверждения"""
    links = []
    seen = set()
    
    # Ключевые слова для кнопок
    keywords = ['confirm', 'verify', 'activate', 'login', 'sign in', 'подтвердить', 'активировать', 'войти']
    
    # 1. Парсим HTML если есть
    if html_bytes:
        try:
            soup = BeautifulSoup(html_bytes, "html.parser")
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text().strip().lower()
                
                # Если текст ссылки содержит ключевое слово
                score = 0
                if any(k in text for k in keywords):
                    score = 2
                elif any(k in href.lower() for k in keywords):
                    score = 1
                
                if score > 0 and href not in seen:
                    label = text if len(text) < 30 and text else "🔗 action"
                    if "http" in href:
                        links.append({"url": href, "label": label, "score": score})
                        seen.add(href)
        except: pass

    # 2. Если HTML не дал результатов, ищем в тексте регуляркой
    if not links:
        urls = re.findall(r'(https?://[^\s<>"]+)', text_body)
        for url in urls:
            if url not in seen:
                 # Простая эвристика
                 score = 0
                 if any(k in url.lower() for k in keywords):
                     score = 1
                 if score > 0:
                     links.append({"url": url, "label": "🔗 link", "score": score})
                     seen.add(url)

    # Сортируем по важности и берем топ 3
    links.sort(key=lambda x: x['score'], reverse=True)
    return links[:3]

def smart_format_text(text):
    # Escape HTML first
    text = html.escape(text)
    # Коды (wrap digits in code)
    text = re.sub(r'(?<!\d)(\d{4,8})(?!\d)', r'<code>\1</code>', text)
    # Обрезка
    if len(text) > 3000:
        text = text[:3000] + "...\n(полный текст в файле)"
    return text

# --- КЛАВИАТУРЫ ---

def kb_main_menu():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("📬 мои ящики", callback_data="my_emails"))
    markup.row(types.InlineKeyboardButton("✨ создать ящик", callback_data="create_email"))
    markup.row(types.InlineKeyboardButton("📱 веб-приложение", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    return markup

def kb_my_emails(user_id):
    markup = types.InlineKeyboardMarkup()
    emails = email_db.get_user_aliases(user_id)
    if not emails:
        markup.row(types.InlineKeyboardButton("у вас нет ящиков 🤷‍♂️", callback_data="empty"))
    else:
        for em in emails:
            # em is dict now: {"addr": "...", "active": True}
            addr = em["addr"]
            status_icon = "🟢" if em.get("active", True) else "🔴"
            markup.row(types.InlineKeyboardButton(f"{status_icon} {addr}", callback_data=f"view_email_{addr}"))
    markup.row(types.InlineKeyboardButton("🔙 назад", callback_data="menu"))
    return markup

def kb_email_control(user_id, email):
    markup = types.InlineKeyboardMarkup()
    is_active = email_db.is_alias_active(user_id, email)
    toggle_text = "❌ выключить" if is_active else "✅ включить"
    
    markup.row(types.InlineKeyboardButton("📜 список писем", callback_data=f"list_emails_{email}_0"))
    markup.row(types.InlineKeyboardButton(toggle_text, callback_data=f"toggle_{email}"))
    markup.row(types.InlineKeyboardButton("🗑 удалить", callback_data=f"ask_del_{email}"))
    markup.row(types.InlineKeyboardButton("🔙 назад", callback_data="my_emails"))
    return markup

def kb_email_list(email, page, total, emails):
    markup = types.InlineKeyboardMarkup()
    
    for em in emails:
        # em: {uid, subject, from}
        subject = em['subject'][:20] + "..." if len(em['subject']) > 20 else em['subject']
        btn_text = f"{em['from'].split('<')[0].strip()}: {subject}"
        markup.row(types.InlineKeyboardButton(btn_text, callback_data=f"read_{email}_{em['uid']}"))
    
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(types.InlineKeyboardButton("⬅️", callback_data=f"list_emails_{email}_{page-1}"))
    
    # Simple check if there are more pages (assuming limit 10)
    if (page + 1) * 10 < total:
        nav_row.append(types.InlineKeyboardButton("➡️", callback_data=f"list_emails_{email}_{page+1}"))
        
    if nav_row:
        markup.row(*nav_row)
        
    markup.row(types.InlineKeyboardButton("🔙 назад", callback_data=f"view_email_{email}"))
    return markup

def kb_read_email(email, uid):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔙 к списку", callback_data=f"back_list_{email}")) 
    return markup

def kb_confirm_delete(email):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("да, удалить", callback_data=f"confirm_del_{email}"))
    markup.row(types.InlineKeyboardButton("нет, отмена", callback_data=f"view_email_{email}"))
    return markup

def kb_domains():
    markup = types.InlineKeyboardMarkup()
    for d in ALLOWED_DOMAINS:
        markup.row(types.InlineKeyboardButton(f"@{d}", callback_data=f"domain_{d}"))
    markup.row(types.InlineKeyboardButton("🔙 назад", callback_data="menu"))
    return markup

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if email_db.is_user_blocked(message.from_user.id):
        bot.send_message(message.chat.id, "⛔️ Вы заблокированы администратором.")
        return

    email_db.upsert_user(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name, 
        message.from_user.last_name
    )
    bot.send_message(
        message.chat.id,
        "📬 <b>привет!</b>\n\nэто приватный почтовый бот.\nсоздавай свои ящики и получай письма прямо здесь.",
        parse_mode="HTML",
        reply_markup=kb_main_menu()
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.message.chat.id
    
    if email_db.is_user_blocked(user_id):
        bot.answer_callback_query(call.id, "⛔️ Вы заблокированы", show_alert=True)
        return

    email_db.upsert_user(
        call.from_user.id, 
        call.from_user.username, 
        call.from_user.first_name, 
        call.from_user.last_name
    )
    
    if call.data == "menu":
        bot.edit_message_text("главное меню:", user_id, call.message.message_id, reply_markup=kb_main_menu())

    elif call.data == "my_emails":
        bot.edit_message_text("ваши ящики:", user_id, call.message.message_id, reply_markup=kb_my_emails(user_id))

    elif call.data.startswith("view_email_"):
        email = call.data.split("view_email_")[1]
        is_active = email_db.is_alias_active(user_id, email)
        status_text = "активен 🟢" if is_active else "отключен 🔴"
        
        info_text = (
            f"📧 <b>Ящик:</b> <code>{email}</code>\n"
            f"Статус: {status_text}\n\n"
            "Выберите действие:"
        )
        bot.edit_message_text(info_text, user_id, call.message.message_id, parse_mode="HTML", reply_markup=kb_email_control(user_id, email))

    elif call.data.startswith("toggle_"):
        email = call.data.split("toggle_")[1]
        new_state = email_db.toggle_alias_active(user_id, email)
        # Refresh view
        is_active = new_state
        status_text = "активен 🟢" if is_active else "отключен 🔴"
        info_text = (
            f"📧 <b>Ящик:</b> <code>{email}</code>\n"
            f"Статус: {status_text}\n\n"
            "Выберите действие:"
        )
        bot.edit_message_text(info_text, user_id, call.message.message_id, parse_mode="HTML", reply_markup=kb_email_control(user_id, email))

    elif call.data.startswith("ask_del_"):
        email = call.data.split("ask_del_")[1]
        bot.edit_message_text(f"❓ Вы точно хотите удалить ящик <code>{email}</code>?", user_id, call.message.message_id, parse_mode="HTML", reply_markup=kb_confirm_delete(email))

    elif call.data.startswith("confirm_del_"):
        email = call.data.split("confirm_del_")[1]
        success, reason = delete_user_alias(user_id, email)
        if success:
            bot.answer_callback_query(call.id, f"✅ {email} удален")
            bot.edit_message_text("ваши ящики:", user_id, call.message.message_id, reply_markup=kb_my_emails(user_id))
        else:
            bot.answer_callback_query(call.id, f"❌ ошибка: {reason}")
            bot.edit_message_text("ваши ящики:", user_id, call.message.message_id, reply_markup=kb_my_emails(user_id))

    elif call.data.startswith("list_emails_"):
        parts = call.data.split("_")
        page = int(parts[-1])
        email = "_".join(parts[2:-1])
        
        # Чтение из БД
        emails, total = email_db.get_emails_for_alias(email, limit=10, offset=page*10)
        
        if not emails and page == 0:
            bot.answer_callback_query(call.id, "Писем нет 🤷‍♂️")
            return

        text_msg = f"📨 Письма для <code>{email}</code> (стр. {page+1}):"
        markup = kb_email_list(email, page, total, emails)
        
        if call.message.content_type == 'text':
            bot.edit_message_text(text_msg, user_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        else:
            try: bot.delete_message(user_id, call.message.message_id)
            except: pass
            bot.send_message(user_id, text_msg, parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("read_"):
        parts = call.data.split("_")
        uid = parts[-1]
        email = "_".join(parts[1:-1])
        
        # Чтение из БД
        content = email_db.get_email_by_uid(uid)
        
        if content:
            text_preview = smart_format_text(content['text'])
            caption = (
                f"📨 <b>Просмотр письма</b>\n"
                f"👤 <b>От:</b> {html.escape(content['from'])}\n"
                f"📌 <b>Тема:</b> {html.escape(content['subject'])}\n"
                f"──────────────────\n"
                f"{text_preview}"
            )
            
            action_links = extract_links(content['html'], content['text'])
            kb = types.InlineKeyboardMarkup()
            for link in action_links:
                kb.add(types.InlineKeyboardButton(link['label'], url=link['url']))
            kb.row(types.InlineKeyboardButton("🔙 назад", callback_data=f"list_emails_{email}_0"))
            
            try: bot.delete_message(user_id, call.message.message_id)
            except: pass

            if content['html']:
                file_obj = io.BytesIO(content['html'])
                file_obj.name = "message.html"
                bot.send_document(user_id, file_obj, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                bot.send_message(user_id, caption, parse_mode="HTML", reply_markup=kb)
        else:
            bot.answer_callback_query(call.id, "Не удалось загрузить письмо")

    elif call.data.startswith("back_list_"):
        email = call.data.split("back_list_")[1]
        
        # Чтение из БД
        emails, total = email_db.get_emails_for_alias(email, limit=10, offset=0)
        
        bot.edit_message_text(f"📨 Письма для <code>{email}</code>:", user_id, call.message.message_id, parse_mode="HTML", reply_markup=kb_email_list(email, 0, total, emails))

    elif call.data == "create_email":
        bot.edit_message_text("выберите домен:", user_id, call.message.message_id, reply_markup=kb_domains())

    elif call.data.startswith("domain_"):
        domain = call.data.split("_")[1]
        msg = bot.send_message(user_id, f"введите желаемый логин для <code>@{domain}</code>\n(например: <code>alex</code>):", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_create_email, domain)

def process_create_email(message, domain):
    user_id = message.chat.id
    login = message.text.strip().lower()
    
    # Валидация логина (только буквы, цифры, точки)
    if not re.match(r'^[a-z0-9.]+$', login):
        bot.send_message(user_id, "❌ недопустимые символы. попробуйте снова.", reply_markup=kb_main_menu())
        return

    full_email = f"{login}@{domain}"
    success, reason = register_new_alias(user_id, full_email)
    
    if success:
        bot.send_message(user_id, f"✅ <b>успешно!</b>\nящик <code>{full_email}</code> создан.\nписьма будут приходить сюда.", parse_mode="HTML", reply_markup=kb_main_menu())
    else:
        bot.send_message(user_id, f"❌ ошибка: {reason}", reply_markup=kb_main_menu())


# --- ПОЧТОВЫЙ ЛУП ---
is_running = True

def mail_check_loop():
    print("🚀 Mail Monitor Started")
    
    # --- СИНХРОНИЗАЦИЯ ПРИ ЗАПУСКЕ ---
    # Мы хотим получить все письма, которых у нас нет, но без фанатизма (например, за последние 30 дней или все)
    # Так как пользователь просил "хранить все", попробуем синхронизировать от последнего локального UID.
    
    initial_mm = MailManager()
    if initial_mm.connect():
        initial_mm.mail.select("INBOX")
        
        last_local_uid = email_db.get_last_uid()
        print(f"📥 Last Local UID: {last_local_uid}")
        
        # Получаем все UID с сервера
        status, messages = initial_mm.mail.uid('search', None, "ALL")
        if status == "OK":
            all_server_uids = [int(u) for u in messages[0].split()]
            if all_server_uids:
                max_server_uid = max(all_server_uids)
                
                # Если локальная база пуста или отстает, нужно подтянуть
                # Чтобы не грузить всё сразу, можно грузить только новые. 
                # Но пользователь хочет "хранить всё". Если база пуста, это займет время.
                # Для начала сделаем синхронизацию только НОВЫХ с момента последнего запуска.
                # Если база пуста (last_local_uid == 0), то загрузим, скажем, последние 50 писем для старта,
                # чтобы не ждать вечность.
                
                if last_local_uid == 0:
                    uids_to_sync = sorted(all_server_uids)[-50:] # Start with last 50
                    print(f"📥 Initial Sync: fetching last {len(uids_to_sync)} emails...")
                else:
                    uids_to_sync = [u for u in all_server_uids if u > last_local_uid]
                    print(f"📥 Syncing {len(uids_to_sync)} new emails...")

                for uid in uids_to_sync:
                    try:
                        res, msg_data = initial_mm.mail.uid('fetch', str(uid), '(RFC822)')
                        parsed = initial_mm.parse_email(msg_data[0][1])
                        
                        # Определяем владельца
                        to_addr = parsed['to_email']
                        owner_id = email_db.get_owner(to_addr)
                        
                        # Сохраняем в БД даже если нет владельца (на будущее) или если владелец админ
                        # Но если владельца нет, ставим owner_id=0 или None
                        if not owner_id:
                             if parsed['to_raw'] and EMAIL_USER in parsed['to_raw']:
                                owner_id = ADMIN_ID
                             else:
                                owner_id = 0 # Unknown
                        
                        email_db.add_email(
                            uid, owner_id, to_addr, parsed['from'], 
                            parsed['subject'], parsed['text'], parsed['html']
                        )
                        print(f"✅ Synced UID {uid}")
                        
                        # Обновляем last_local_uid чтобы монитор подхватил только новее этого
                        if uid > last_local_uid:
                            last_local_uid = uid
                            
                    except Exception as e:
                        print(f"Sync Error UID {uid}: {e}")
        
        initial_mm.mail.close()
        initial_mm.mail.logout()
    
    last_uid = last_local_uid
    print(f"🏁 Sync Complete. Monitoring from UID: {last_uid}")

    while is_running:
        try:
            mm = MailManager()
            if mm.connect():
                mm.mail.select("INBOX")
                status, messages = mm.mail.uid('search', None, "ALL")
                
                if status == "OK":
                    current_uids = [int(u) for u in messages[0].split()]
                    new_uids = [u for u in current_uids if u > last_uid]
                    
                    for uid in new_uids:
                        try:
                            res, msg_data = mm.mail.uid('fetch', str(uid), '(RFC822)')
                            parsed = mm.parse_email(msg_data[0][1])
                            
                            # Роутинг
                            to_addr = parsed['to_email']
                            owner_id = email_db.get_owner(to_addr)
                            
                            # Сохраняем в БД СРАЗУ
                            email_db.add_email(
                                uid, owner_id if owner_id else 0, to_addr, parsed['from'], 
                                parsed['subject'], parsed['text'], parsed['html']
                            )
                            
                            # Проверка статуса ящика для уведомления
                            if owner_id and not email_db.is_alias_active(owner_id, to_addr):
                                print(f"Skipping notification for inactive address: {to_addr}")
                                if uid > last_uid: last_uid = uid
                                continue
                            
                            if not owner_id:
                                if parsed['to_raw'] and EMAIL_USER in parsed['to_raw']:
                                    owner_id = ADMIN_ID
                                else:
                                    owner_id = ADMIN_ID 
                            
                            # Формирование контента
                            text_preview = smart_format_text(parsed['text'])
                            
                            # Ищем кнопки
                            action_links = extract_links(parsed['html'], parsed['text'])
                            kb = types.InlineKeyboardMarkup()
                            for link in action_links:
                                kb.add(types.InlineKeyboardButton(link['label'], url=link['url']))
                            
                            caption = (
                                f"📨 <b>новое письмо!</b>\n\n"
                                f"📬 <b>на:</b> <code>{to_addr}</code>\n"
                                f"👤 <b>от:</b> {html.escape(parsed['from'])}\n"
                                f"📌 <b>тема:</b> {html.escape(parsed['subject'])}\n"
                                f"──────────────────\n"
                                f"{text_preview}"
                            )
                            
                            # Отправка
                            try:
                                if parsed['html']:
                                    file_obj = io.BytesIO(parsed['html'])
                                    file_obj.name = "message.html"
                                    bot.send_document(owner_id, file_obj, caption=caption, parse_mode="HTML", reply_markup=kb)
                                else:
                                    bot.send_message(owner_id, caption, parse_mode="HTML", reply_markup=kb)
                            except Exception as e:
                                print(f"Send Error to {owner_id}: {e}")

                            if uid > last_uid:
                                last_uid = uid
                                
                        except Exception as e:
                            print(f"Error processing UID {uid}: {e}")

                mm.mail.close()
                mm.mail.logout()
            
        except Exception as e:
            print(f"Loop Error: {e}")
        
        time.sleep(5)

if __name__ == '__main__':
    # Запуск потока
    t = threading.Thread(target=mail_check_loop)
    t.daemon = True
    t.start()

    # Запуск бота
    print("🤖 Bot Polling Started...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Bot Polling Error: {e}")
