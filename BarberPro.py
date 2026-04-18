"""
================================================================================
                            BARBER BOT PRO 3.3 (FINAL)
================================================================================
   
   Este sistema foi desenvolvido com exclusividade pela:
   
   🚀  P R I M E   S T U D I O  🚀
   
   Funcionalidades Completas:
   - Agendamento Inteligente
   - Fidelidade Digital
   - Broadcast (Mensagem em Massa)
   - Relatório Financeiro
   - Backup Automático e Manual
   - Gestão de Equipe e Serviços
   - Integração com API de Mapas (ViaCEP)
   
================================================================================
"""

import logging
import sqlite3
import os
import random
import shutil
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, time
import asyncio

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, 
    KeyboardButton, BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
)
from telegram.constants import ChatAction
from telegram.helpers import escape_markdown
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters, PicklePersistence
)

# --- CONFIGURAÇÕES FIXAS ---
TOKEN = ""

# IDs de Segurança
ID_GRUPO_BARBEIROS = AQUI
ADMIN_ID = AQUI

# Pastas
MEDIA_FOLDER = "media"
BACKUP_FOLDER = "backups"
DB_FOLDER = "DB"
DB_NAME = os.path.join(DB_FOLDER, "barbearia_pro.db")

# Estados da Conversa
SELECT_SERVICE, SELECT_BARBER, SELECT_DATE, SELECT_PERIOD, SELECT_TIME, CONFIRM_BOOKING = range(6)
AWAIT_PHOTO_CAPTION = range(6, 7)
WAITING_CONFIG_INPUT, WAITING_SERVICE_NAME, WAITING_SERVICE_PRICE = range(7, 10)
WAITING_BROADCAST_MSG = range(10, 11)
WAITING_NEW_BARBER_NAME = range(11, 12)
WAITING_CEP, WAITING_NUMERO = range(12, 14)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BANCO DE DADOS ---

def setup_database():
    os.makedirs(MEDIA_FOLDER, exist_ok=True)
    os.makedirs(BACKUP_FOLDER, exist_ok=True)
    os.makedirs(DB_FOLDER, exist_ok=True)

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS appointments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_name TEXT, service TEXT, barber_name TEXT, price REAL, date TEXT, time TEXT, status TEXT DEFAULT 'confirmed', reminder_sent INTEGER DEFAULT 0, created_at TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, user_name TEXT, phone TEXT, join_date TEXT, total_cuts INTEGER DEFAULT 0, last_visit TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS portfolio (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT NOT NULL, caption TEXT, upload_date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, price REAL NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS barbers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)''') 
        cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS blocked_days (date TEXT PRIMARY KEY)''')
        
        cursor.execute("SELECT count(*) FROM services")
        if cursor.fetchone()[0] == 0:
            default_services = [("Cabelo", 35.00), ("Barba", 25.00), ("Completo", 50.00)]
            cursor.executemany("INSERT INTO services (name, price) VALUES (?, ?)", default_services)
        
        cursor.execute("SELECT count(*) FROM barbers")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO barbers (name) VALUES (?)", ("Barbeiro Principal",))

        defaults = {
            "nome_barbearia": "Barbearia do Mestre",
            "whatsapp_link": "https://wa.me/5511999999999",
            "endereco": "Rua Exemplo, 123 - Centro",
            "contato": "(11) 99999-9999",
            "sobre_nos": "Somos referência em cortes clássicos e modernos.",
            "horario_abertura": "8",
            "horario_fechamento": "20"
        }
        for key, val in defaults.items():
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
        
        conn.commit()

def get_db_connection():
    return sqlite3.connect(DB_NAME)

def get_setting(key):
    conn = get_db_connection()
    res = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return res[0] if res else ""

def set_setting(key, value):
    conn = get_db_connection()
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()

async def is_admin_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    return str(chat_id) == str(ID_GRUPO_BARBEIROS)

async def is_admin_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=ID_GRUPO_BARBEIROS, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member']: return True
    except: pass
    return False

# --- FUNÇÕES DE BACKUP ---

async def perform_backup() -> tuple[bool, str]:
    try:
        os.makedirs(BACKUP_FOLDER, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_FOLDER, backup_filename)
        shutil.copy(DB_NAME, backup_path)
        return True, backup_filename
    except Exception as e:
        logger.error(f"Erro no backup: {e}")
        return False, str(e)

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    await update.message.reply_text("⏳ Iniciando backup manual...")
    success, info = await perform_backup()
    if success: await update.message.reply_text(f"✅ **Backup realizado!**\nArquivo: `{info}`", parse_mode='Markdown')
    else: await update.message.reply_text(f"❌ **Falha:** `{info}`", parse_mode='Markdown')

async def backup_job_automatic(context: ContextTypes.DEFAULT_TYPE):
    success, info = await perform_backup()
    if success:
        try: await context.bot.send_message(chat_id=ID_GRUPO_BARBEIROS, text=f"💾 **Backup Automático**\nArquivo: `{info}`", parse_mode='Markdown')
        except: pass

# --- FUNÇÕES AUXILIARES ---

def get_price(service_name):
    conn = get_db_connection()
    res = conn.execute("SELECT price FROM services WHERE name = ?", (service_name,)).fetchone()
    conn.close()
    return res[0] if res else 0.0

def get_services_keyboard():
    conn = get_db_connection()
    services = conn.execute("SELECT name, price FROM services").fetchall()
    conn.close()
    keyboard = []
    for name, price in services:
        emoji = "🪒" if "barba" in name.lower() else "✂️"
        keyboard.append([InlineKeyboardButton(f"{emoji} {name} (R$ {price:.2f})", callback_data=f"srv_{name}")])
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel_booking")])
    return InlineKeyboardMarkup(keyboard)

def get_barbers_keyboard():
    conn = get_db_connection()
    barbers = conn.execute("SELECT name FROM barbers").fetchall()
    conn.close()
    keyboard = []
    for (name,) in barbers:
        keyboard.append([InlineKeyboardButton(f"👨‍🎨 {name}", callback_data=f"barber_{name}")])
    keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="back_service")])
    return InlineKeyboardMarkup(keyboard)

def get_dates_keyboard():
    today = datetime.now()
    keyboard = []
    row = []
    conn = get_db_connection()
    blocked = [row[0] for row in conn.execute("SELECT date FROM blocked_days").fetchall()]
    conn.close()
    for i in range(7): 
        d = today + timedelta(days=i)
        d_str, d_full = d.strftime("%d/%m"), d.strftime("%Y-%m-%d")
        wd = d.strftime("%a")
        wd_pt = {"Mon":"Seg","Tue":"Ter","Wed":"Qua","Thu":"Qui","Fri":"Sex","Sat":"Sáb","Sun":"Dom"}.get(wd, wd)
        cb = "date_blocked" if d_full in blocked else f"date_{d_full}"
        lbl = f"🔒 {d_str}" if d_full in blocked else (f"Hoje" if i==0 else f"Amanhã" if i==1 else f"{d_str} ({wd_pt})")
        row.append(InlineKeyboardButton(lbl, callback_data=cb))
        if len(row) == 2: keyboard.append(row); row = []
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="back_barber")])
    return InlineKeyboardMarkup(keyboard)

def get_period_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🌅 Manhã", callback_data="period_morning"), InlineKeyboardButton("☀️ Tarde", callback_data="period_afternoon")], [InlineKeyboardButton("🌙 Noite", callback_data="period_evening")], [InlineKeyboardButton("🔙 Voltar", callback_data="back_date")]])

def get_times_keyboard(date_str, period, barber_name):
    all_times = []
    try: op, cl = int(get_setting("horario_abertura")), int(get_setting("horario_fechamento"))
    except: op, cl = 8, 20
    
    if period == "morning": s, e = op, 11
    elif period == "afternoon": s, e = 12, 17
    elif period == "evening": s, e = 18, cl
    else: s, e = op, cl

    for h in range(s, e + 1):
        for m in [0, 30]:
            if h == cl and m > 0: continue
            all_times.append(f"{h:02d}:{m:02d}")

    conn = get_db_connection()
    occupied = [row[0] for row in conn.execute("SELECT time FROM appointments WHERE date = ? AND barber_name = ? AND status != 'canceled'", (date_str, barber_name)).fetchall()]
    conn.close()
    
    now = datetime.now()
    if date_str == now.strftime("%Y-%m-%d"):
        curr = now.hour * 60 + now.minute
        all_times = [t for t in all_times if (int(t.split(':')[0])*60 + int(t.split(':')[1])) > curr]
    
    available = [t for t in all_times if t not in occupied]
    if not available: return None
    
    keyboard, row = [], []
    for t in available:
        row.append(InlineKeyboardButton(t, callback_data=f"time_{t}"))
        if len(row) == 4: keyboard.append(row); row = []
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="back_period")])
    return InlineKeyboardMarkup(keyboard)

# --- MENU CLIENTE ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if update.callback_query: await update.callback_query.answer()
    
    conn = get_db_connection()
    conn.execute("INSERT OR IGNORE INTO clients (user_id, user_name, join_date) VALUES (?, ?, ?)", (user.id, user.full_name, datetime.now().strftime("%Y-%m-%d")))
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM portfolio ORDER BY id DESC LIMIT 1")
    last_photo = cursor.fetchone()
    conn.commit(); conn.close()
    
    nome_barbearia = get_setting("nome_barbearia")
    text = f"Olá, {user.first_name}! Bem-vindo à **{nome_barbearia}** 💈\n\nEscolha uma opção:"
    
    # MENU SEM BOTÃO ADMIN (SEGURANÇA GARANTIDA)
    keyboard = [[InlineKeyboardButton("📅 Agendar Horário", callback_data="start_booking")], [InlineKeyboardButton("💎 Fidelidade", callback_data="show_loyalty"), InlineKeyboardButton("✂️ Portfólio", callback_data="view_portfolio")], [InlineKeyboardButton("ℹ️ Sobre", callback_data="about_us"), InlineKeyboardButton("📍 Local", callback_data="show_location"), InlineKeyboardButton("💬 Contato", callback_data="talk_to_support")]]
    markup = InlineKeyboardMarkup(keyboard)
    
    media_sent = False
    if os.path.exists(MEDIA_FOLDER):
        files = [f for f in os.listdir(MEDIA_FOLDER) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.mp4', '.gif'))]
        if files:
            try:
                f_path = os.path.join(MEDIA_FOLDER, random.choice(files))
                with open(f_path, 'rb') as f:
                    if f_path.endswith('.mp4'): await context.bot.send_video(chat_id, f, caption=text, reply_markup=markup, parse_mode='Markdown')
                    else: await context.bot.send_photo(chat_id, f, caption=text, reply_markup=markup, parse_mode='Markdown')
                media_sent = True
            except: pass
            
    if not media_sent:
        if last_photo: 
            try: await context.bot.send_photo(chat_id, last_photo[0], caption=text, reply_markup=markup, parse_mode='Markdown')
            except: await context.bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')
        else: await context.bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')

# --- FUNÇÕES DE MENU ---

async def about_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    text_db, nome_db = get_setting("sobre_nos"), get_setting("nome_barbearia")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"💈 **SOBRE A {nome_db.upper()}** 💈\n\n{text_db}", parse_mode='Markdown')

async def talk_to_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    link, tel = get_setting("whatsapp_link"), get_setting("contato")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"💬 **PRECISA DE AJUDA?**\n\nChame a gente no WhatsApp:\n👉 [Clique aqui para conversar]({link})\n📞 Ou ligue: {tel}", parse_mode='Markdown')

async def show_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    addr = get_setting("endereco")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"📍 **ONDE ESTAMOS:**\n\n{addr}\n\n[🗺️ Abrir no Google Maps](https://maps.google.com)", parse_mode='Markdown')

async def show_loyalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    user_id = update.effective_user.id
    conn = get_db_connection()
    res = conn.execute("SELECT total_cuts FROM clients WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    cuts = res[0] if res else 0
    needed = 10
    progress = cuts % needed
    bar = "✂️" * progress + "⚪" * (needed - progress)
    msg = f"💎 **FIDELIDADE**\n\nCortes: {cuts}\nProgresso: {progress}/{needed}\n{bar}\n\n"
    if progress == 0 and cuts > 0: msg += "🎉 PARABÉNS! Próximo corte grátis!"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode='Markdown')

# --- FUNÇÃO PORTFÓLIO (REINSERIDA) ---

async def view_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, caption FROM portfolio ORDER BY id DESC LIMIT 5")
    photos = cursor.fetchall()
    conn.close()
    if not photos: 
        await context.bot.send_message(chat_id=update.effective_chat.id, text="📸 **Portfólio**\n\nAinda não postamos fotos recentes. Fique ligado!", parse_mode='Markdown')
    else:
        for file_id, caption in photos: 
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=file_id, caption=caption or "")
            await asyncio.sleep(0.3)

# --- FLUXO DE AGENDAMENTO ---

async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    await update.effective_message.reply_text("✂️ Escolha o **serviço**:", reply_markup=get_services_keyboard(), parse_mode='Markdown')
    return SELECT_SERVICE

async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_booking": await query.edit_message_text("Agendamento cancelado."); return ConversationHandler.END
    context.user_data['booking_service'] = query.data.split("_", 1)[1]
    conn = get_db_connection()
    barbers = conn.execute("SELECT name FROM barbers").fetchall()
    conn.close()
    if len(barbers) > 1:
        await query.edit_message_text(f"✅ Serviço: **{context.user_data['booking_service']}**\n\n👨‍🎨 Com **qual profissional**?", reply_markup=get_barbers_keyboard(), parse_mode='Markdown')
        return SELECT_BARBER
    else:
        context.user_data['booking_barber'] = barbers[0][0]
        return await ask_date(query, context)

async def select_barber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back_service": await query.edit_message_text("Escolha o serviço:", reply_markup=get_services_keyboard()); return SELECT_SERVICE
    context.user_data['booking_barber'] = query.data.split("_", 1)[1]
    return await ask_date(query, context)

async def ask_date(query, context):
    await query.edit_message_text(f"✂️ Serviço: **{context.user_data['booking_service']}**\n👨‍🎨 Barbeiro: **{context.user_data['booking_barber']}**\n\n📅 Escolha a **data**:", reply_markup=get_dates_keyboard(), parse_mode='Markdown')
    return SELECT_DATE

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    barber_count = conn.execute("SELECT count(*) FROM barbers").fetchone()[0]
    conn.close()
    if query.data == "back_barber":
        if barber_count > 1: await query.edit_message_text("Escolha o barbeiro:", reply_markup=get_barbers_keyboard()); return SELECT_BARBER
        else: await query.edit_message_text("Escolha o serviço:", reply_markup=get_services_keyboard()); return SELECT_SERVICE
    if query.data == "date_blocked": await query.answer("Dia fechado!", show_alert=True); return SELECT_DATE
    date_str = query.data.split("_")[1]
    context.user_data['booking_date'] = date_str
    d_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m")
    await query.edit_message_text(f"📅 Data: **{d_display}**\n\nQual **período**?", reply_markup=get_period_keyboard(), parse_mode='Markdown')
    return SELECT_PERIOD

async def select_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back_date": await query.edit_message_text("Escolha a data:", reply_markup=get_dates_keyboard()); return SELECT_DATE
    period = query.data.split("_")[1]
    context.user_data['booking_period'] = period
    date_str = context.user_data['booking_date']
    barber = context.user_data['booking_barber']
    keyboard = get_times_keyboard(date_str, period, barber)
    if not keyboard: await query.edit_message_text(f"❌ Sem horários para o **{barber}**.\nTente outro:", reply_markup=get_period_keyboard(), parse_mode='Markdown'); return SELECT_PERIOD
    await query.edit_message_text(f"⏰ Escolha o horário com **{barber}**:", reply_markup=keyboard, parse_mode='Markdown')
    return SELECT_TIME

async def select_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back_period": await query.edit_message_text("Escolha o período:", reply_markup=get_period_keyboard()); return SELECT_PERIOD
    time_str = query.data.split("_")[1]
    context.user_data['booking_time'] = time_str
    conn = get_db_connection()
    conflict = conn.execute("SELECT id FROM appointments WHERE date=? AND time=? AND barber_name=? AND status!='canceled'", (context.user_data['booking_date'], time_str, context.user_data['booking_barber'])).fetchone()
    conn.close()
    if conflict: await query.edit_message_text("⚠️ Horário acabou de ser pego! Escolha outro:", reply_markup=get_times_keyboard(context.user_data['booking_date'], context.user_data['booking_period'], context.user_data['booking_barber'])); return SELECT_TIME
    d = context.user_data
    date_fmt = datetime.strptime(d['booking_date'], "%Y-%m-%d").strftime("%d/%m")
    price = get_price(d['booking_service'])
    txt = (f"📝 **CONFIRMAÇÃO**\n\n✂️ {d['booking_service']} (R$ {price:.2f})\n👨‍🎨 {d['booking_barber']}\n📅 {date_fmt} às {d['booking_time']}\n👤 {update.effective_user.full_name}\n\nConfirmar?")
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Sim", callback_data="confirm_yes"), InlineKeyboardButton("❌ Não", callback_data="cancel_booking")]]), parse_mode='Markdown')
    return CONFIRM_BOOKING

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_booking": await query.edit_message_text("Agendamento cancelado."); return ConversationHandler.END
    user = query.from_user
    data = context.user_data
    price = get_price(data['booking_service'])
    conn = get_db_connection()
    if conn.execute("SELECT id FROM appointments WHERE date=? AND time=? AND barber_name=? AND status!='canceled'", (data['booking_date'], data['booking_time'], data['booking_barber'])).fetchone():
        conn.close()
        await query.edit_message_text("⚠️ Ops! Alguém foi mais rápido.", reply_markup=get_times_keyboard(data['booking_date'], data['booking_period'], data['booking_barber']))
        return SELECT_TIME
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO appointments (user_id, user_name, service, barber_name, price, date, time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (user.id, user.full_name, data['booking_service'], data['booking_barber'], price, data['booking_date'], data['booking_time'], agora))
    conn.execute("UPDATE clients SET total_cuts = total_cuts + 1, last_visit = ? WHERE user_id = ?", (data['booking_date'], user.id))
    cuts = conn.execute("SELECT total_cuts FROM clients WHERE user_id = ?", (user.id,)).fetchone()[0]
    conn.commit(); conn.close()
    bonus_text = "\n\n🎉 **PARABÉNS! 10 CORTES!** Prêmio liberado!" if cuts % 10 == 0 else ""
    data_fmt = datetime.strptime(data['booking_date'], '%Y-%m-%d').strftime('%d/%m')
    await query.edit_message_text(f"✅ **AGENDADO!**\n\nDia {data_fmt} às {data['booking_time']} com {data['booking_barber']}.{bonus_text}", parse_mode='Markdown')
    try:
        safe_name = escape_markdown(user.full_name, version=2)
        safe_service = escape_markdown(data['booking_service'], version=2)
        username_txt = f"(@{escape_markdown(user.username, version=2)})" if user.username else ""
        msg_grupo = f"🔔 *NOVO CORTES AGENDADO\\!* 🔔\n\n👤 *Cliente:* {safe_name} {username_txt}\n✂️ *Serviço:* {safe_service}\n📅 *Data:* {escape_markdown(data_fmt, version=2)}\n⏰ *Horário:* {escape_markdown(data['booking_time'], version=2)}"
        await context.bot.send_message(chat_id=ID_GRUPO_BARBEIROS, text=msg_grupo, parse_mode='MarkdownV2')
    except Exception as e: logger.error(f"Erro notificação grupo: {e}")
    return ConversationHandler.END

# --- ADMIN E EXTRAS ---

async def help_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    msg = "💡 **DICA RÁPIDA:**\n\nUse o comando **/painel** para acessar todas as funções de gerenciamento sem precisar decorar códigos!\n\n_Desenvolvido por PrimeStudio_ 🚀"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    if update.callback_query: await update.callback_query.answer()
    keyboard = [
        [InlineKeyboardButton("📅 Hoje", callback_data="admin_agenda_today"), InlineKeyboardButton("🌅 Amanhã", callback_data="admin_agenda_tomorrow")],
        [InlineKeyboardButton("🗓️ Semana", callback_data="admin_agenda_week"), InlineKeyboardButton("🚫 Bloquear Dias", callback_data="admin_manage_blocked_days")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_start"), InlineKeyboardButton("👨‍🎨 Equipe (Barbeiros)", callback_data="admin_manage_barbers")],
        [InlineKeyboardButton("⚙️ Configurações", callback_data="admin_config_menu"), InlineKeyboardButton("📸 Add Foto", callback_data="admin_add_photo")]
    ]
    msg = "🔐 **Painel do Barbeiro**\n\nGerencie sua barbearia por aqui. Toque numa opção:"
    if update.callback_query: await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else: await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_financial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    conn = get_db_connection()
    daily = conn.execute("SELECT SUM(price) FROM appointments WHERE date = ? AND status != 'canceled'", (today,)).fetchone()[0] or 0.0
    monthly = conn.execute("SELECT SUM(price) FROM appointments WHERE date LIKE ? AND status != 'canceled'", (f"{month}%",)).fetchone()[0] or 0.0
    conn.close()
    msg = f"💰 **FINANCEIRO**\n\nHoje: R$ {daily:.2f}\nMês: R$ {monthly:.2f}"
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="admin_back")]]), parse_mode='Markdown')

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 Envie a mensagem para TODOS os clientes agora (texto/foto/video).")
    return WAITING_BROADCAST_MSG

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    conn = get_db_connection()
    clients = conn.execute("SELECT user_id FROM clients").fetchall()
    conn.close()
    success = 0
    status = await update.message.reply_text(f"🚀 Enviando para {len(clients)}...")
    for (uid,) in clients:
        try:
            if update.message.photo: await context.bot.send_photo(uid, update.message.photo[-1].file_id, caption=update.message.caption)
            elif update.message.video: await context.bot.send_video(uid, update.message.video.file_id, caption=update.message.caption)
            else: await context.bot.send_message(uid, update.message.text)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await context.bot.edit_message_text(f"✅ Enviado para {success} clientes.", chat_id=update.effective_chat.id, message_id=status.message_id)
    return ConversationHandler.END

async def manage_barbers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    barbers = conn.execute("SELECT id, name FROM barbers").fetchall()
    conn.close()
    
    txt = "👨‍🎨 **Equipe Atual:**\n\n"
    keyboard = []
    
    # Lista barbeiros com botão de deletar
    for bid, bname in barbers:
        txt += f"- {bname}\n"
        keyboard.append([InlineKeyboardButton(f"🗑️ Apagar {bname}", callback_data=f"del_barber_{bid}")])
        
    keyboard.append([InlineKeyboardButton("➕ Adicionar Novo Barbeiro", callback_data="add_barber_start")])
    keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="admin_back")])
    
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def add_barber_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Digite o NOME do novo barbeiro aqui no chat:")
    return WAITING_NEW_BARBER_NAME

async def add_barber_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    name = update.message.text
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO barbers (name) VALUES (?)", (name,))
        conn.commit()
        await update.message.reply_text(f"✅ Barbeiro **{name}** adicionado com sucesso!", parse_mode='Markdown')
    except:
        await update.message.reply_text("❌ Erro ao adicionar. Talvez o nome já exista.")
    finally:
        conn.close()
    
    # Volta para o painel principal
    await admin_panel_command(update, context)
    return ConversationHandler.END

async def delete_barber_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    barber_id = query.data.split("_")[2]
    conn = get_db_connection()
    
    # Proteção: Não deixa apagar se for o último barbeiro
    count = conn.execute("SELECT count(*) FROM barbers").fetchone()[0]
    if count <= 1:
        await query.answer("⚠️ Você não pode apagar o último barbeiro!", show_alert=True)
        conn.close()
        return

    conn.execute("DELETE FROM barbers WHERE id = ?", (barber_id,))
    conn.commit()
    conn.close()
    
    await manage_barbers_menu(update, context)

async def admin_config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🏷️ Nome da Loja", callback_data="cfg_nome_barbearia"), InlineKeyboardButton("📱 WhatsApp Link", callback_data="cfg_whatsapp_link")],
        [InlineKeyboardButton("📍 Endereço", callback_data="cfg_endereco"), InlineKeyboardButton("📞 Contato", callback_data="cfg_contato")],
        [InlineKeyboardButton("ℹ️ Sobre Nós", callback_data="cfg_sobre_nos"), InlineKeyboardButton("🕒 Horários", callback_data="cfg_horarios")],
        [InlineKeyboardButton("💰 Serviços e Preços", callback_data="cfg_services_list")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="admin_back")]
    ]
    await query.edit_message_text("⚙️ **Configurações**\n\nO que você quer alterar?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "admin_financial": await admin_financial(update, context)
    elif data == "admin_manage_barbers": await manage_barbers_menu(update, context)
    elif data == "admin_broadcast_start": await broadcast_start(update, context)
    elif data == "admin_manage_blocked_days": await show_block_days_menu(update, context)
    elif data == "admin_back": await admin_panel_command(update, context)
    elif data.startswith("toggle_block_"): await toggle_block_callback(update, context)
    elif data == "admin_config_menu": await admin_config_menu(update, context)
    elif data == "add_barber_start": await add_barber_start(update, context)
    elif data.startswith("del_barber_"): await delete_barber_callback(update, context)
    
    elif data == "cfg_services_list":
        conn = get_db_connection()
        servs = conn.execute("SELECT name, price FROM services").fetchall()
        conn.close()
        msg = "💰 **Serviços Atuais:**\n" + "\n".join([f"• {n}: R$ {p:.2f}" for n, p in servs]) + "\n\nPara alterar, use os comandos `/setservico` e `/delservico` por enquanto."
        await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="admin_config_menu")]]))
    elif data.startswith("admin_agenda_"):
        conn = get_db_connection()
        if "week" in data:
            start = datetime.now().strftime("%Y-%m-%d")
            end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            appts = conn.execute("SELECT date, time, user_name, service, barber_name FROM appointments WHERE date >= ? AND date <= ? AND status != 'canceled' ORDER BY date, time", (start, end)).fetchall()
            msg = "🗓️ **Semana:**\n" + ("\n".join([f"{datetime.strptime(d,'%Y-%m-%d').strftime('%d/%m')} {t} - {n} ({b})" for d,t,n,s,b in appts]) if appts else "Vazia")
        else:
            t = datetime.now() if "today" in data else datetime.now()+timedelta(days=1)
            appts = conn.execute("SELECT time, user_name, service, barber_name FROM appointments WHERE date = ? AND status != 'canceled' ORDER BY time", (t.strftime("%Y-%m-%d"),)).fetchall()
            msg = f"📅 **Dia:**\n" + ("\n".join([f"{t} - {n} ({b})" for t,n,s,b in appts]) if appts else "Vazio")
        conn.close()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="admin_back")]]), parse_mode='Markdown')

async def admin_add_photo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📸 Envie a foto:")
    return AWAIT_PHOTO_CAPTION

async def admin_receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return AWAIT_PHOTO_CAPTION
    conn = get_db_connection()
    conn.execute("INSERT INTO portfolio (file_id, caption, upload_date) VALUES (?, ?, ?)", (update.message.photo[-1].file_id, update.message.caption, datetime.now().strftime("%Y-%m-%d")))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ Foto salva!")
    return ConversationHandler.END

# --- CONFIG INTERATIVA ---

async def config_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.replace("cfg_", "")
    
    if key == "endereco":
        await query.edit_message_text("📮 **Endereço Inteligente**\n\nPor favor, digite o **CEP** (somente números):", parse_mode='Markdown')
        return WAITING_CEP
    
    context.user_data['config_key'] = key
    names = {"nome_barbearia": "Nome da Barbearia", "whatsapp_link": "Link do WhatsApp", "contato": "Telefone de Contato", "sobre_nos": "Texto 'Sobre Nós'", "horarios": "Horários (formato: inicio fim, ex: 9 19)"}
    await query.edit_message_text(f"✍️ **Alterar {names.get(key, key)}**\n\nPor favor, digite o novo valor aqui no chat:", parse_mode='Markdown')
    return WAITING_CONFIG_INPUT

async def config_save_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    new_value = update.message.text
    key = context.user_data.get('config_key')
    if key == "horarios":
        try:
            s, e = new_value.split()
            set_setting("horario_abertura", s); set_setting("horario_fechamento", e)
            msg = f"✅ Horários atualizados: **{s}h às {e}h**"
        except: msg = "❌ Formato inválido. Use apenas dois números separados por espaço (ex: 9 19)."
    else:
        set_setting(key, new_value)
        msg = "✅ Configuração salva com sucesso!"
    await update.message.reply_text(msg, parse_mode='Markdown')
    keyboard = [[InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="admin_config_menu")]]
    await update.message.reply_text("Toque abaixo para continuar configurando:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# --- HANDLERS CEP ---
async def receive_cep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    cep = update.message.text.replace("-", "").strip()
    if not cep.isdigit() or len(cep) != 8: await update.message.reply_text("❌ CEP inválido."); return WAITING_CEP
    try:
        with urllib.request.urlopen(f"https://viacep.com.br/ws/{cep}/json/") as response:
            data = json.loads(response.read().decode())
        if "erro" in data: await update.message.reply_text("❌ CEP não encontrado."); return WAITING_CEP
        context.user_data['temp_address'] = data
        await update.message.reply_text(f"📍 {data['logradouro']}, {data['bairro']}\n🏠 Digite o **NÚMERO**:", parse_mode='Markdown')
        return WAITING_NUMERO
    except: await update.message.reply_text("❌ Erro ao consultar CEP."); return WAITING_CEP

async def receive_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    num = update.message.text
    d = context.user_data.get('temp_address')
    full = f"{d['logradouro']}, {num} - {d['bairro']}, {d['localidade']} - {d['uf']}"
    link = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(full)}"
    set_setting("endereco", f"{full}\n\n[🗺️ Abrir no Google Maps]({link})")
    await update.message.reply_text(f"✅ Endereço salvo!\n{full}", parse_mode='Markdown')
    return ConversationHandler.END

async def cancel_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

# --- GESTÃO DE SERVIÇOS (TEXT COMMANDS) ---

async def set_servico_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    try:
        args = context.args
        if len(args) < 2: return
        price = float(args[-1].replace(',', '.'))
        name = " ".join(args[:-1])
        conn = get_db_connection()
        conn.execute("INSERT INTO services (name, price) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET price=excluded.price", (name, price))
        conn.commit(); conn.close()
        await update.message.reply_text(f"✅ {name}: R$ {price:.2f}")
    except: pass

async def del_servico_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    name = " ".join(context.args)
    conn = get_db_connection()
    conn.execute("DELETE FROM services WHERE name = ?", (name,))
    conn.commit(); conn.close()
    await update.message.reply_text(f"🗑️ {name} removido.")

async def list_servicos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    conn = get_db_connection()
    servs = conn.execute("SELECT name, price FROM services").fetchall()
    conn.close()
    msg = "\n".join([f"{n}: R$ {p:.2f}" for n, p in servs])
    await update.message.reply_text(msg or "Nenhum serviço.")

# --- BLOQUEIO DE DIAS ---

async def show_block_days_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    blocked = [row[0] for row in conn.execute("SELECT date FROM blocked_days").fetchall()]
    conn.close()
    today = datetime.now()
    keyboard, row = [], []
    for i in range(14):
        d_val = today + timedelta(days=i)
        d_str, d_full = d_val.strftime("%d/%m"), d_val.strftime("%Y-%m-%d")
        btn_txt = f"❌ {d_str}" if d_full in blocked else f"✅ {d_str}"
        row.append(InlineKeyboardButton(btn_txt, callback_data=f"toggle_block_{d_full}"))
        if len(row)==3: keyboard.append(row); row=[]
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="admin_back")])
    await update.callback_query.edit_message_text("📅 **Bloquear/Desbloquear Dias**\n\n✅ = Aberto\n❌ = Fechado\n\nToque para mudar:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def toggle_block_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    date = query.data.split("_")[2]
    conn = get_db_connection()
    if conn.execute("SELECT 1 FROM blocked_days WHERE date = ?", (date,)).fetchone(): conn.execute("DELETE FROM blocked_days WHERE date = ?", (date,))
    else: conn.execute("INSERT INTO blocked_days (date) VALUES (?)", (date,))
    conn.commit(); conn.close()
    await show_block_days_menu(update, context)

# --- JOBS & STARTUP ---

async def announce_startup(context: ContextTypes.DEFAULT_TYPE):
    try:
        startup_text = "🚀 **SISTEMA INICIADO** 🚀\n\n✅ O **BarberBot Pro 2.0** está online e operante.\n💻 Desenvolvido por: **PrimeStudio**\n\n💈 Pronto para gerenciar agendamentos!"
        await context.bot.send_message(chat_id=ID_GRUPO_BARBEIROS, text=startup_text, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ ERRO ao enviar mensagem de BOOT: {e}")

async def send_daily_agenda_job(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db_connection()
    appts = conn.execute("SELECT time, user_name, service, barber_name FROM appointments WHERE date = ? AND status != 'canceled' ORDER BY time", (today,)).fetchall()
    conn.close()
    m, a, n = [], [], []
    for t, name, srv, barb in appts:
        entry = f"⏰ `{t}` - {name} ({srv}) - {barb}"
        h = int(t.split(':')[0])
        if h < 12: m.append(entry)
        elif h < 18: a.append(entry)
        else: n.append(entry)
    msg = f"📅 **AGENDA DO DIA ({datetime.now().strftime('%d/%m')})**\n\n🌅 **Manhã:**\n" + ("\n".join(m) if m else "_(Livre)_")
    msg += "\n\n☀️ **Tarde:**\n" + ("\n".join(a) if a else "_(Livre)_")
    msg += "\n\n🌙 **Noite:**\n" + ("\n".join(n) if n else "_(Livre)_")
    try: await context.bot.send_message(chat_id=ID_GRUPO_BARBEIROS, text=msg, parse_mode='Markdown')
    except Exception as e: logger.error(f"Erro job agenda: {e}")

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    target = datetime.now() + timedelta(hours=1)
    appts = conn.execute("SELECT id, user_id, service, time FROM appointments WHERE date = ? AND (time = ? OR time = ?) AND reminder_sent = 0", (target.strftime("%Y-%m-%d"), target.strftime("%H:%M"), target.strftime("%H:00"))).fetchall()
    for aid, uid, srv, time in appts:
        try:
            await context.bot.send_message(uid, f"⏰ **LEMBRETE!**\n\nSeu corte de **{srv}** é em 1 hora (às {time}).\nNão se atrase! 💈")
            conn.execute("UPDATE appointments SET reminder_sent = 1 WHERE id = ?", (aid,))
        except: pass
    conn.commit(); conn.close()

async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [BotCommand("start", "Iniciar agendamento")],
        scope=BotCommandScopeAllPrivateChats()
    )
    try:
        await application.bot.set_my_commands(
            [
                BotCommand("painel", "Abrir Painel"),
                BotCommand("hoje", "Ver Agenda Hoje"),
                BotCommand("amanha", "Ver Agenda Amanhã"),
                BotCommand("backup", "Fazer Backup Manual"),
                BotCommand("bloquear", "Gerenciar Dias"),
                BotCommand("ajuda", "Ajuda"),
                BotCommand("start", "Reiniciar Bot")
            ],
            scope=BotCommandScopeChat(chat_id=ID_GRUPO_BARBEIROS)
        )
    except Exception: pass

async def quick_agenda_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_context(update, context): return
    date_db = datetime.now().strftime("%Y-%m-%d")
    conn = get_db_connection()
    appts = conn.execute("SELECT time, user_name, service FROM appointments WHERE date = ? AND status != 'canceled' ORDER BY time", (date_db,)).fetchall()
    conn.close()
    msg = f"📅 **Agenda Hoje:**\n\n" + ("\n".join([f"⏰ `{t}` - {n} ({s})" for t, n, s in appts]) if appts else "Vazia.")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Não entendi. Toque em /start para abrir o menu.", parse_mode='Markdown')

def main():
    setup_database()
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    if application.job_queue:
        application.job_queue.run_once(announce_startup, when=5)
        application.job_queue.run_repeating(reminder_job, interval=900, first=10)
        application.job_queue.run_daily(backup_job_automatic, time=time(hour=0, minute=0))
        application.job_queue.run_daily(send_daily_agenda_job, time=time(hour=5, minute=0))

    config_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(config_start_input, pattern="^cfg_")],
        states={
            WAITING_CONFIG_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_save_input)],
            WAITING_CEP: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_cep)],
            WAITING_NUMERO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_number)]
        },
        fallbacks=[CommandHandler("cancelar", cancel_config)]
    )

    booking_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_booking, pattern="^start_booking$")],
        states={
            SELECT_SERVICE: [CallbackQueryHandler(select_service)],
            SELECT_BARBER: [CallbackQueryHandler(select_barber)],
            SELECT_DATE: [CallbackQueryHandler(select_date)],
            SELECT_PERIOD: [CallbackQueryHandler(select_period)],
            SELECT_TIME: [CallbackQueryHandler(select_time)],
            CONFIRM_BOOKING: [CallbackQueryHandler(confirm_booking)],
        },
        fallbacks=[CallbackQueryHandler(start_booking, pattern="cancel_booking")]
    )
    
    broadcast_h = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, pattern="^admin_broadcast_start$")],
        states={WAITING_BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_send)]},
        fallbacks=[CommandHandler("cancelar", start)]
    )
    
    barber_add_h = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_barber_start, pattern="^add_barber_start$")],
        states={WAITING_NEW_BARBER_NAME: [MessageHandler(filters.TEXT, add_barber_save)]},
        fallbacks=[CommandHandler("cancelar", start)]
    )
    
    photo_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_photo_start, pattern="admin_add_photo")],
        states={AWAIT_PHOTO_CAPTION: [MessageHandler(filters.PHOTO, admin_receive_photo)]},
        fallbacks=[CommandHandler("cancelar", start)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("painel", admin_panel_command))
    application.add_handler(CommandHandler("hoje", quick_agenda_command))
    application.add_handler(CommandHandler("ajuda", help_admin_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("setservico", set_servico_command))
    application.add_handler(CommandHandler("delservico", del_servico_command))
    application.add_handler(CommandHandler("servicos", list_servicos_command))

    application.add_handler(config_handler)
    application.add_handler(booking_handler)
    application.add_handler(broadcast_h)
    application.add_handler(barber_add_h)
    application.add_handler(photo_handler)
    
    application.add_handler(CallbackQueryHandler(show_loyalty, pattern="^show_loyalty$"))
    application.add_handler(CallbackQueryHandler(about_us, pattern="^about_us$"))
    application.add_handler(CallbackQueryHandler(talk_to_support, pattern="^talk_to_support$"))
    application.add_handler(CallbackQueryHandler(view_portfolio, pattern="^view_portfolio$"))
    application.add_handler(CallbackQueryHandler(show_location, pattern="^show_location$"))
    application.add_handler(CallbackQueryHandler(admin_panel_command, pattern="^admin_panel$"))
    
    application.add_handler(CallbackQueryHandler(admin_config_menu, pattern="^admin_config_menu$"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(toggle_block_callback, pattern="^toggle_block_"))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))

    print("Bot Rodando...")
    application.run_polling()

if __name__ == "__main__":
    main()