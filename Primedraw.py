import json 
import logging
import sqlite3
import os
import asyncio
import csv
import io
import random
import re
import uuid
import qrcode
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeChat, BotCommandScopeAllPrivateChats
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler
from telegram.error import Forbidden, BadRequest

# ------------------------------------------------------------------
# 🤖 PrimeDraw Pro ⭐ (VERSÃO COMERCIAL)
# 💻 Desenvolvido por: Prime Studios
# ------------------------------------------------------------------

# --- CONFIGURAÇÕES DO SISTEMA (PREENCHA AQUI) ---
TOKEN = 'SEU_TOKEN_AQUI'  # ⚠️ COLOQUE O TOKEN DO BOT AQUI
ADMIN_GROUP_ID = 000000000  # ⚠️ COLOQUE O ID DO GRUPO DE ADM AQUI (Ex: -100123456789)
LOG_CHANNEL_ID = 000000000  # ⚠️ COLOQUE O ID DO CANAL DE LOGS AQUI
DB_PATH = 'sorteios.db'

# --- CONFIGURAÇÃO DE LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ESTADOS DAS CONVERSAS ---
# Edição
EDIT_CHOICE, EDIT_INPUT = range(2)
# Pix Admin
SET_PIX_KEY, SET_PIX_NAME, SET_PIX_CITY = range(2, 5)
# Cadastro Usuário
REG_NAME, REG_CPF, REG_INSTAGRAM = range(5, 8)
# Cupom
COUPON_INPUT = range(8, 9)

# --- UTILITÁRIOS PIX (BR CODE) ---
def gerar_br_code(chave, valor, nome, cidade, txid="***"):
    if txid == "***":
        txid = re.sub(r'[^a-zA-Z0-9]', '', str(uuid.uuid4()))[:25]
        
    nome = nome[:25].upper().replace(" ", "")
    cidade = cidade[:15].upper().replace(" ", "")
    valor_str = f"{valor:.2f}"
    
    payload = f"00020126{len(chave)+14}0014BR.GOV.BCB.PIX01{len(chave)}{chave}52040000530398654{len(valor_str):02}{valor_str}5802BR59{len(nome):02}{nome}60{len(cidade):02}{cidade}62{len(txid)+4:02}05{len(txid):02}{txid}6304"
    
    polinomio = 0x1021
    resultado = 0xFFFF
    for char in payload:
        resultado ^= (ord(char) << 8)
        for _ in range(8):
            if (resultado & 0x8000):
                resultado = (resultado << 1) ^ polinomio
            else:
                resultado <<= 1
    crc16 = f"{resultado & 0xFFFF:04X}"
    return payload + crc16

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS participants (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        first_name TEXT, 
        full_name TEXT, 
        cpf TEXT,
        instagram TEXT,
        join_date TEXT, 
        status TEXT DEFAULT 'active', 
        payment_status TEXT DEFAULT 'free',
        last_nudge TEXT
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS required_channels (channel_id TEXT PRIMARY KEY, title TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, reason TEXT, date TEXT)''')
    
    # Tabela de Histórico de Sorteios
    cursor.execute('''CREATE TABLE IF NOT EXISTS draw_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, 
        winners TEXT, reserves TEXT, total_participants INTEGER, settings_snapshot TEXT
    )''')

    # Tabela de Cupons
    cursor.execute('''CREATE TABLE IF NOT EXISTS coupons (
        code TEXT PRIMARY KEY, discount_percent INTEGER, uses INTEGER DEFAULT 0
    )''')

    # Tabela de Estatísticas de Usuário (Fidelidade)
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_stats (
        user_id INTEGER PRIMARY KEY, 
        total_participations INTEGER DEFAULT 0,
        first_seen TEXT
    )''')

    # Migrações Automáticas
    cols = [
        ("payment_status", "TEXT DEFAULT 'free'"),
        ("full_name", "TEXT"),
        ("cpf", "TEXT"),
        ("instagram", "TEXT"),
        ("last_nudge", "TEXT")
    ]
    for col, type_def in cols:
        try: cursor.execute(f"ALTER TABLE participants ADD COLUMN {col} {type_def}")
        except sqlite3.OperationalError: pass

    # Configurações Padrão
    defaults = {
        'active_giveaway': 'false', 'max_participants': '0', 'strict_mode': 'false',
        'entry_price': '0.00', 'winners_count': '1', 'reserves_count': '1',
        'giveaway_title': 'Sorteio Especial', 'giveaway_desc': 'Clique abaixo para participar!',
        'scheduled_date': '', 'pix_key': 'SUA_CHAVE_AQUI', 'pix_name': 'Nome Loja', 'pix_city': 'Cidade'
    }
    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    
    conn.commit()
    conn.close()

init_db()

# --- FUNÇÕES AUXILIARES ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

async def log_action(context, message):
    try: await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=f"📝 **LOG:** {message}", parse_mode='Markdown')
    except: pass

async def is_admin(update):
    return update.effective_chat.id == ADMIN_GROUP_ID

async def check_membership(context, user_id):
    conn = get_db()
    channels = conn.execute("SELECT channel_id, title FROM required_channels").fetchall()
    conn.close()
    if not channels: return {'success': True}
    missing = []
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(ch['channel_id'], user_id)
            if member.status not in ['creator', 'administrator', 'member', 'restricted']:
                missing.append(ch['title'])
        except: missing.append(ch['title'])
    return {'success': not missing, 'missing': missing}

def check_fraud(user_id):
    conn = get_db()
    banned = conn.execute("SELECT reason FROM blacklist WHERE user_id = ?", (user_id,)).fetchone()
    strict = get_setting('strict_mode', conn) == 'true'
    conn.close()
    if banned: return {'safe': False, 'reason': f"🚫 Você foi banido: {banned['reason']}"}
    return {'safe': True, 'strict': strict}

def get_setting(key, db_conn=None):
    close = False
    if not db_conn: db_conn = get_db(); close = True
    res = db_conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if close: db_conn.close()
    return res['value'] if res else None

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit(); conn.close()

def update_user_stats(user_id):
    conn = get_db()
    exists = conn.execute("SELECT 1 FROM user_stats WHERE user_id = ?", (user_id,)).fetchone()
    if exists:
        conn.execute("UPDATE user_stats SET total_participations = total_participations + 1 WHERE user_id = ?", (user_id,))
    else:
        conn.execute("INSERT INTO user_stats (user_id, total_participations, first_seen) VALUES (?, 1, ?)", (user_id, datetime.now().strftime('%Y-%m-%d')))
    conn.commit(); conn.close()

# --- DIAGNÓSTICO E JOBS ---
async def recovery_job(context: ContextTypes.DEFAULT_TYPE):
    """Recuperação de Carrinho: Avisa quem não pagou"""
    conn = get_db()
    # Pega usuários pendentes há mais de 30min que ainda não receberam aviso (last_nudge null)
    limit_time = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M')
    pendings = conn.execute("SELECT * FROM participants WHERE payment_status = 'pending' AND join_date < ? AND last_nudge IS NULL", (limit_time,)).fetchall()
    
    for p in pendings:
        try:
            await context.bot.send_message(p['user_id'], "👋 Olá! Vi que você iniciou sua inscrição mas não enviou o comprovante.\n\nTeve algum problema? Se precisar de ajuda, use o botão de suporte no menu principal! 🎟️")
            conn.execute("UPDATE participants SET last_nudge = ? WHERE user_id = ?", (datetime.now().strftime('%Y-%m-%d %H:%M'), p['user_id']))
            conn.commit()
        except: pass # Usuário bloqueou o bot
    conn.close()

async def post_init(application: Application):
    await application.bot.set_my_commands([BotCommand("start", "▶️ Iniciar")], scope=BotCommandScopeAllPrivateChats())
    admin_cmds = [
        BotCommand("painel", "⚙️ Painel"), BotCommand("agendar", "🗓️ Agendar"),
        BotCommand("broadcast", "📢 Broadcast"), BotCommand("ban", "🚫 Banir"),
        BotCommand("unban", "✅ Desbanir"), BotCommand("ranking", "🏆 Top Fiéis"), BotCommand("addcupom", "🎟️ Add Cupom"),
        BotCommand("search", "🔍 Buscar"), BotCommand("addchannel", "➕ Add Canal")
    ]
    try: await application.bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=ADMIN_GROUP_ID))
    except: pass
    
    # Inicia Job de Recuperação
    if application.job_queue:
        application.job_queue.run_repeating(recovery_job, interval=1800, first=60) # A cada 30min

    conn = get_db()
    scheduled = get_setting('scheduled_date', conn)
    if scheduled:
        try:
            run_time = datetime.fromisoformat(scheduled)
            if run_time > datetime.now():
                application.job_queue.run_once(auto_draw_job, run_time, chat_id=ADMIN_GROUP_ID, name="scheduled_draw")
    
        except: pass
    conn.close()

# --- COMANDOS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == ADMIN_GROUP_ID:
        await update.message.reply_text("👑 **Admin:** Use /painel", parse_mode='Markdown'); return

    conn = get_db()
    title = get_setting('giveaway_title', conn)
    active = get_setting('active_giveaway', conn)
    price = float(get_setting('entry_price', conn))
    desc = get_setting('giveaway_desc', conn)
    conn.close()

    if active != 'true':
        await update.message.reply_text(f"🛑 **{title}**\n\nSorteio encerrado.", parse_mode='Markdown'); return

    price_text = "Grátis" if price == 0 else f"R$ {price:.2f}"
    btn_text = "📝 PARTICIPAR (Grátis)" if price == 0 else f"🎟️ COMPRAR TICKET ({price_text})"

    text = f"🎉 **{title}** 🎉\n\n{desc}\n\n💰 **Valor:** {price_text}\n👇 Participe:"
    kb = [[InlineKeyboardButton(btn_text, callback_data='join')],
          [InlineKeyboardButton("📜 Regras", callback_data='show_rules'), InlineKeyboardButton("🆘 Suporte", callback_data='support_link')]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    conn = get_db()
    settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    total_users = conn.execute("SELECT COUNT(*) as t FROM participants WHERE status='active'").fetchone()['t']
    pending = conn.execute("SELECT COUNT(*) as t FROM participants WHERE payment_status='pending'").fetchone()['t']
    conn.close()

    status_icon = "🟢" if settings['active_giveaway'] == 'true' else "🔴"
    status_text = "ATIVO" if settings['active_giveaway'] == 'true' else "PAUSADO"
    price = float(settings.get('entry_price', 0))
    schedule_text = settings.get('scheduled_date', 'Não definido')
    if schedule_text != 'Não definido' and schedule_text != '':
        try:
            # Formata data para ficar mais legível
            dt = datetime.fromisoformat(schedule_text)
            schedule_text = dt.strftime('%d/%m às %H:%M')
        except: pass
    else:
        schedule_text = "---"

    # TEXTO DO PAINEL REFORMULADO E MAIS INTUITIVO
    text = (
        f"💎 **PRIME STUDIOS - PAINEL DE CONTROLE** 💎\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{status_icon} **STATUS DO SISTEMA:** `{status_text}`\n\n"
        f"📊 **Estatísticas em Tempo Real:**\n"
        f"├ 👥 **Participantes:** `{total_users}`\n"
        f"├ ⏳ **Pagamentos Pendentes:** `{pending}`\n"
        f"└ 💰 **Valor do Ticket:** `R$ {price:.2f}`\n\n"
        f"🗓️ **Agendamento:** `{schedule_text}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *Selecione uma ação abaixo:*"
    )

    # BOTÕES REORGANIZADOS POR CATEGORIA
    kb = [
        # Controle Principal
        [InlineKeyboardButton(f'{status_icon} Ligar/Desligar Sorteio', callback_data='toggle_status')],
        
        # Ações de Divulgação
        [InlineKeyboardButton('📢 Postar no Canal', callback_data='post_button'), InlineKeyboardButton('⚙️ Configurações', callback_data='menu_settings')],
        
        # Gestão do Sorteio
        [InlineKeyboardButton('🎲 REALIZAR SORTEIO', callback_data='run_draw'), InlineKeyboardButton('👁️ Ver Inscritos', callback_data='menu_monitor')],
        
        # Ferramentas Extras
        [InlineKeyboardButton('🗓️ Agendar', callback_data='menu_schedule'), InlineKeyboardButton('📤 Baixar Planilha', callback_data='export_data:csv:all')],
        
        # Perigo/Reset
        [InlineKeyboardButton('🔁 Reiniciar Tudo (Novo Sorteio)', callback_data='menu_repeat'), InlineKeyboardButton('🗑️ Reset Total', callback_data='reset_all')]
    ]
    
    if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    conn = get_db()
    strict_mode = get_setting('strict_mode', conn) == 'true'
    conn.close()
    
    strict_icon = "✅" if strict_mode else "❌"
    text = "⚙️ **CONFIGURAÇÕES DO SISTEMA**\n\nO que você deseja ajustar?"
    kb = [
        [InlineKeyboardButton("💳 Chave Pix e Dados", callback_data='config_pix_start')],
        [InlineKeyboardButton("📝 Título e Descrição", callback_data='edit_start_menu')],
        [InlineKeyboardButton(f"🛡️ Modo Anti-Fake: {strict_icon}", callback_data='toggle_strict')],
        [InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data='painel')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

# --- CADASTRO (NOME, CPF, INSTAGRAM) ---

async def registration_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    conn = get_db()
    
    if get_setting('active_giveaway', conn) != 'true':
        conn.close(); await query.answer('⛔ Fechado.', show_alert=True); return ConversationHandler.END
    
    chk = check_fraud(user.id)
    if not chk['safe']: conn.close(); await query.answer(chk['reason'], show_alert=True); return ConversationHandler.END
    
    # Verifica cadastro existente
    u_data = conn.execute("SELECT * FROM participants WHERE user_id = ?", (user.id,)).fetchone()
    conn.close()

    if u_data and u_data['full_name'] and u_data['cpf']:
        # Se já tiver cadastro completo, pula para pagamento
        await execute_join_logic(update, context, u_data)
        return ConversationHandler.END
    
    await query.answer()
    await query.message.reply_text("👋 Olá! Vamos fazer seu cadastro rápido.\n\n👤 **Digite seu NOME COMPLETO:**")
    return REG_NAME

async def receive_reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_name'] = update.message.text.strip()
    await update.message.reply_text("✅ OK.\n\n🆔 **Digite seu CPF (Apenas números):**")
    return REG_CPF

async def receive_reg_cpf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cpf = re.sub(r'[^0-9]', '', update.message.text.strip())
    if len(cpf) != 11:
        await update.message.reply_text("❌ CPF inválido (precisa ter 11 dígitos). Tente novamente:")
        return REG_CPF
    context.user_data['reg_cpf'] = cpf
    await update.message.reply_text("📸 **Qual seu Instagram?** (Ex: @seu_perfil):")
    return REG_INSTAGRAM

async def receive_reg_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    insta = update.message.text.strip()
    user = update.effective_user
    name = context.user_data['reg_name']
    cpf = context.user_data['reg_cpf']
    
    conn = get_db()
    exists = conn.execute("SELECT user_id FROM participants WHERE user_id = ?", (user.id,)).fetchone()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    if exists:
        conn.execute("UPDATE participants SET full_name=?, cpf=?, instagram=? WHERE user_id=?", (name, cpf, insta, user.id))
    else:
        conn.execute("INSERT INTO participants (user_id, username, first_name, full_name, cpf, instagram, join_date, payment_status) VALUES (?, ?, ?, ?, ?, ?, ?, 'free')", 
                     (user.id, user.username, user.first_name, name, cpf, insta, now_str))
    conn.commit()
    u_data = conn.execute("SELECT * FROM participants WHERE user_id = ?", (user.id,)).fetchone()
    conn.close()
    
    await update.message.reply_text("✅ **Cadastro Concluído!**")
    await execute_join_logic(update, context, u_data)
    return ConversationHandler.END

async def cancel_reg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelado."); return ConversationHandler.END

# --- LÓGICA DE PAGAMENTO E CUPONS ---

async def execute_join_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data):
    user = update.effective_user
    chat_id = update.effective_chat.id
    conn = get_db()
    price = float(get_setting('entry_price', conn))
    
    # Verifica cupons aplicados na sessão
    discount = context.user_data.get('applied_discount', 0)
    final_price = price * (1 - discount/100)
    
    if user_data['payment_status'] == 'paid':
        await context.bot.send_message(chat_id, '✅ Você já está participando!')
        conn.close(); return
        
    check = await check_membership(context, user.id)
    if not check['success']:
        await context.bot.send_message(chat_id, f"❌ Entre nos canais obrigatórios primeiro!\n\nUse /start novamente.")
        conn.close(); return

    if final_price > 0:
        pix_key = get_setting('pix_key', conn)
        if not pix_key or pix_key == 'SUA_CHAVE_AQUI':
             await context.bot.send_message(chat_id, '⚠️ Erro de configuração do Pix.')
             conn.close(); return

        payload = gerar_br_code(pix_key, final_price, get_setting('pix_name', conn), get_setting('pix_city', conn))
        conn.execute("UPDATE participants SET payment_status = 'pending' WHERE user_id = ?", (user.id,)); conn.commit()
        
        try:
            img = qrcode.make(payload)
            bio = io.BytesIO(); img.save(bio, 'PNG'); bio.seek(0)
            
            caption = (
                f"🎟️ **PAGAMENTO TICKET**\n\n"
                f"👤 {user_data['full_name']}\n"
                f"💰 Valor: **R$ {final_price:.2f}**\n"
            )
            if discount > 0: caption += f"🏷️ Desconto: {discount}%\n"
            caption += "\n1️⃣ Copie o código\n2️⃣ Pague no App\n3️⃣ **ENVIE O COMPROVANTE AQUI!**"
            
            kb = []
            if discount == 0: # Só mostra botão de cupom se não tiver aplicado
                kb.append([InlineKeyboardButton("🎟️ Tenho Cupom", callback_data='ask_coupon')])
            
            await context.bot.send_photo(chat_id=user.id, photo=bio, caption=caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb) if kb else None)
            await context.bot.send_message(chat_id=user.id, text=f"`{payload}`", parse_mode='Markdown')
        except Forbidden: await context.bot.send_message(chat_id, '❌ Me chame no privado!')
    else:
        conn.execute("UPDATE participants SET payment_status = 'paid' WHERE user_id = ?", (user.id,))
        update_user_stats(user.id) # Registra fidelidade
        conn.commit()
        await context.bot.send_message(chat_id, f"✅ **Confirmado!**\nSua participação é gratuita.\nBoa sorte! 🍀")
    conn.close()

# Handler do Cupom
async def ask_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🎟️ **Digite o código do seu cupom:**")
    return COUPON_INPUT

async def receive_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    user = update.effective_user
    conn = get_db()
    cupom = conn.execute("SELECT * FROM coupons WHERE code = ?", (code,)).fetchone()
    
    if cupom:
        context.user_data['applied_discount'] = cupom['discount_percent']
        conn.execute("UPDATE coupons SET uses = uses + 1 WHERE code = ?", (code,))
        conn.commit()
        u_data = conn.execute("SELECT * FROM participants WHERE user_id = ?", (user.id,)).fetchone()
        conn.close()
        
        await update.message.reply_text(f"✅ Cupom **{code}** aplicado! ({cupom['discount_percent']}% OFF)")
        await execute_join_logic(update, context, u_data) # Recalcula Pix
        return ConversationHandler.END
    else:
        conn.close()
        await update.message.reply_text("❌ Cupom inválido. Tente novamente ou digite /cancelar.")
        return COUPON_INPUT

async def cancel_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado.")
    return ConversationHandler.END

# --- NOVOS COMANDOS ADMIN ---

async def add_coupon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    try:
        # /addcupom NATAL10 10
        code = context.args[0].upper()
        percent = int(context.args[1])
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO coupons (code, discount_percent) VALUES (?, ?)", (code, percent))
        conn.commit(); conn.close()
        await update.message.reply_text(f"✅ Cupom **{code}** criado com {percent}% de desconto.")
    except: await update.message.reply_text("⚠️ Uso: `/addcupom CODIGO PORCENTAGEM`")

async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    conn = get_db()
    # Pega top 10 do user_stats
    rows = conn.execute("SELECT p.full_name, s.total_participations FROM user_stats s JOIN participants p ON s.user_id = p.user_id ORDER BY s.total_participations DESC LIMIT 10").fetchall()
    conn.close()
    
    if not rows: return await update.message.reply_text("📉 Sem dados de ranking ainda.")
    
    txt = "🏆 **TOP 10 USUÁRIOS MAIS FIÉIS** 🏆\n\n"
    for i, r in enumerate(rows):
        txt += f"{i+1}. **{r['full_name']}**: {r['total_participations']} participações\n"
    await update.message.reply_text(txt, parse_mode='Markdown')

# --- CONFIGURAÇÃO DE SORTEIO (EDIT) ---

async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    settings = dict(get_db().execute("SELECT key, value FROM settings").fetchall())
    kb = [[InlineKeyboardButton("Título", callback_data='edit_key:giveaway_title'), InlineKeyboardButton("Descrição", callback_data='edit_key:giveaway_desc')],
          [InlineKeyboardButton("Preço", callback_data='edit_key:entry_price'), InlineKeyboardButton("Ganhadores", callback_data='edit_key:winners_count'), InlineKeyboardButton("Suplentes", callback_data='edit_key:reserves_count')],
          [InlineKeyboardButton("⬅️ Voltar", callback_data='back_to_settings')]]
    await query.edit_message_text(f"📝 **Configurar Sorteio**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); return EDIT_CHOICE

async def edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == 'back_to_settings': await settings_menu(update, context); return ConversationHandler.END
    context.user_data['editing_key'] = query.data.split(':')[1]
    await query.edit_message_text("✍️ Digite o novo valor:"); return EDIT_INPUT

async def edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting(context.user_data['editing_key'], update.message.text)
    await update.message.reply_text("✅ Salvo!"); 
    # Pequeno hack para re-exibir o menu
    await update.message.reply_text("Voltando...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data='edit_start_menu')]]))
    return ConversationHandler.END

async def edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado."); return ConversationHandler.END

# --- CONFIGURAÇÃO DO PIX ---

async def config_pix_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.edit_message_text("🔑 Envie a CHAVE PIX:"); return SET_PIX_KEY

async def receive_pix_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['k'] = update.message.text; await update.message.reply_text("👤 Nome do Beneficiário:"); return SET_PIX_NAME
async def receive_pix_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['n'] = update.message.text; await update.message.reply_text("🏙️ Cidade:"); return SET_PIX_CITY
async def receive_pix_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('pix_key', context.user_data['k']))
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('pix_name', context.user_data['n']))
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('pix_city', update.message.text))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ Pix Configurado!"); await admin_panel(update, context); return ConversationHandler.END

async def cancel_config_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Cancelado.")
    await admin_panel(update, context)
    return ConversationHandler.END

# --- COMANDOS DE SEGURANÇA E OUTROS ---

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    try:
        user_id = int(context.args[0])
        reason = " ".join(context.args[1:]) or "Violação"
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO blacklist (user_id, reason, date) VALUES (?, ?, ?)", (user_id, reason, datetime.now().strftime('%Y-%m-%d')))
        conn.execute("DELETE FROM participants WHERE user_id = ?", (user_id,))
        conn.commit(); conn.close()
        await update.message.reply_text(f"🚫 Banido `{user_id}`.", parse_mode='Markdown')
    except: await update.message.reply_text("⚠️ Uso: `/ban <ID> <Motivo>`")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    try:
        user_id = int(context.args[0])
        conn = get_db(); conn.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,)); conn.commit(); conn.close()
        await update.message.reply_text(f"✅ Desbanido `{user_id}`.", parse_mode='Markdown')
    except: pass

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    try:
        user_id = int(context.args[0])
        conn = get_db()
        user = conn.execute("SELECT * FROM participants WHERE user_id = ?", (user_id,)).fetchone()
        banned = conn.execute("SELECT * FROM blacklist WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if banned: await update.message.reply_text(f"🚫 BANIDO: {banned['reason']}")
        elif user: await update.message.reply_text(f"✅ INSCRITO: {user['full_name']} (CPF: {user['cpf']})")
        else: await update.message.reply_text("🤷‍♂️ Não encontrado.")
    except: await update.message.reply_text("⚠️ Uso: `/search <ID>`")

async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    try:
        parts = update.message.text.split(' ', 2)
        channel_id, title = parts[1], parts[2]
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO required_channels (channel_id, title) VALUES (?, ?)", (channel_id, title))
        conn.commit(); conn.close()
        await update.message.reply_text(f"✅ Canal '{title}' adicionado.")
    except: await update.message.reply_text("⚠️ Uso: `/addchannel <ID> <Nome>`")

async def proof_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private' or not update.message.photo: return
    user = update.effective_user
    conn = get_db()
    p = conn.execute("SELECT * FROM participants WHERE user_id = ? AND payment_status = 'pending'", (user.id,)).fetchone()
    conn.close()
    if p:
        await update.message.reply_text("⏳ Recebido! Aguarde análise.")
        caption = f"🧾 **COMPROVANTE**\n👤 {p['full_name']}\n🆔 CPF: {p['cpf']}\n📸 Insta: {p['instagram']}"
        kb = [[InlineKeyboardButton("✅ Aprovar", callback_data=f"appr_{user.id}"), InlineKeyboardButton("❌ Recusar", callback_data=f"rej_{user.id}")]]
        await context.bot.send_photo(chat_id=ADMIN_GROUP_ID, photo=update.message.photo[-1].file_id, caption=caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def main_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == 'join': pass # Deixa passar para ConversationHandler
    elif data == 'ask_coupon': pass # Deixa passar para ConversationHandler
    elif data.startswith('appr_') or data.startswith('rej_'):
        action, uid = data.split('_'); uid = int(uid); conn = get_db()
        if action == 'appr':
            conn.execute("UPDATE participants SET payment_status='paid' WHERE user_id=?", (uid,))
            update_user_stats(uid)
            try: await context.bot.send_message(uid, "✅ Aprovado! Boa sorte!")
            except: pass
            await query.edit_message_caption(caption=query.message.caption + "\n\n✅ APROVADO")
        else:
            conn.execute("DELETE FROM participants WHERE user_id=?", (uid,))
            try: await context.bot.send_message(uid, "❌ Recusado.")
            except: pass
            await query.edit_message_caption(caption=query.message.caption + "\n\n❌ RECUSADO")
        conn.commit(); conn.close()
    
    elif data == 'painel': await admin_panel(update, context)
    elif data == 'menu_settings': await settings_menu(update, context)
    elif data == 'menu_edit': await edit_start(update, context) # Legacy
    elif data == 'edit_start_menu': await edit_start(update, context); return EDIT_CHOICE
    elif data == 'config_pix_start': await config_pix_start(update, context); return SET_PIX_KEY
    elif data == 'toggle_status':
        conn = get_db(); curr = get_setting('active_giveaway', conn); new_s = 'false' if curr == 'true' else 'true'
        set_setting('active_giveaway', new_s); conn.close(); await admin_panel(update, context)
    elif data == 'toggle_strict':
        conn = get_db(); curr = get_setting('strict_mode', conn); new_s = 'false' if curr == 'true' else 'true'
        set_setting('strict_mode', new_s); conn.close(); await settings_menu(update, context)
    elif data == 'post_button':
        conn = get_db(); t = get_setting('giveaway_title', conn); p = float(get_setting('entry_price', conn)); d = get_setting('giveaway_desc', conn); conn.close()
        btn = "📝 PARTICIPAR" if p == 0 else f"🎟️ COMPRAR (R$ {p:.2f})"
        await query.message.reply_text(f"🎉 **{t}**\n\n{d}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn, callback_data='join')]]))
    elif data == 'run_draw': await run_draw_logic(context, query.message.chat_id)
    elif data == 'menu_monitor': await monitor_live(update, context)
    elif data == 'menu_repeat': await repeat_menu(update, context)
    elif data == 'do_repeat': await repeat_execute(update, context)
    elif data == 'menu_schedule': await query.answer("Use /agendar DD/MM/AAAA HH:MM", show_alert=True)
    elif data == 'reset_all': await query.answer("⚠️ Use /reset no chat (segurança)", show_alert=True)
    elif data == 'export_data:csv:all':
        conn = get_db()
        rows = conn.execute("SELECT user_id, full_name, cpf, join_date FROM participants").fetchall()
        conn.close()
        if not rows: return await query.answer("Vazio.")
        output = io.StringIO()
        writer = csv.writer(output); writer.writerow(['ID', 'Nome', 'CPF', 'Data'])
        for r in rows: writer.writerow([r['user_id'], r['full_name'], r['cpf'], r['join_date']])
        output.seek(0); bytes_output = io.BytesIO(output.getvalue().encode('utf-8'))
        await context.bot.send_document(chat_id=query.message.chat_id, document=bytes_output, filename=f"export.csv")
    else: await query.answer()

async def monitor_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    conn = get_db()
    rows = conn.execute("SELECT full_name, payment_status FROM participants ORDER BY rowid DESC LIMIT 10").fetchall()
    conn.close()
    text = "👁️ **Últimos Inscritos:**\n\n" + ("\n".join([f"👤 {r['full_name']} ({r['payment_status'].upper()})" for r in rows]) if rows else "Nenhum.")
    kb = [[InlineKeyboardButton("⬅️ Voltar", callback_data='painel'), InlineKeyboardButton("🔄 Atualizar", callback_data='menu_monitor')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def repeat_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    kb = [[InlineKeyboardButton("✅ LIMPAR E REPETIR", callback_data='do_repeat')], [InlineKeyboardButton("Cancelar", callback_data='painel')]]
    await query.edit_message_text("🔁 **Repetir Sorteio?**\nIsso apaga todos os participantes atuais.", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def repeat_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    conn = get_db()
    conn.execute("DELETE FROM participants") 
    set_setting('active_giveaway', 'true')
    conn.commit(); conn.close()
    await query.answer("Reiniciado!", show_alert=True)
    await admin_panel(update, context)

async def run_draw_logic(context, chat_id):
    conn = get_db()
    winners_qty = int(get_setting('winners_count', conn) or 1)
    reserves_qty = int(get_setting('reserves_count', conn) or 1)
    pool = conn.execute("SELECT * FROM participants WHERE status = 'active' AND payment_status = 'paid'").fetchall()
    
    if len(pool) < winners_qty:
        await context.bot.send_message(chat_id, "❌ Participantes insuficientes.")
        conn.close(); return

    msg = await context.bot.send_message(chat_id, "🎰 **SORTEANDO...**", parse_mode='Markdown')
    await asyncio.sleep(2)
    random.shuffle(pool)
    final_winners, final_reserves = [], []
    await context.bot.edit_message_text("🔍 **Validando...**", chat_id=chat_id, message_id=msg.message_id, parse_mode='Markdown')
    
    for candidate in list(pool):
        check = await check_membership(context, candidate['user_id'])
        if check['success']:
            if len(final_winners) < winners_qty: final_winners.append(candidate)
            elif len(final_reserves) < reserves_qty: final_reserves.append(candidate)
            else: break

    if not final_winners:
        await context.bot.edit_message_text("❌ Todos desclassificados.", chat_id=chat_id, message_id=msg.message_id)
        conn.close(); return

    w_txt = ", ".join([f"{w['full_name']}" for w in final_winners])
    r_txt = ", ".join([f"{r['full_name']}" for r in final_reserves])
    conn.execute("INSERT INTO draw_history (date, winners, reserves, total_participants, settings_snapshot) VALUES (?, ?, ?, ?, ?)",
                 (datetime.now().strftime('%d/%m/%Y %H:%M'), w_txt, r_txt, len(pool), f"W:{winners_qty} R:{reserves_qty}"))
    conn.commit(); conn.close()

    out_text = "🏆 **RESULTADO FINAL** 🏆\n\n"
    for i, w in enumerate(final_winners): out_text += f"🥇 **{i+1}º:** {w['full_name']}\n🆔 CPF: `{w['cpf']}`\n\n"
    if final_reserves: out_text += "\n🛡️ **Suplentes:**\n" + "\n".join([f"🔹 {r['full_name']}" for r in final_reserves])
    await context.bot.edit_message_text(out_text, chat_id=chat_id, message_id=msg.message_id, parse_mode='Markdown')
    for w in final_winners:
        try: await context.bot.send_message(w['user_id'], "🎉 **VOCÊ GANHOU!** 🏆\nFale com o admin.")
        except: pass

async def auto_draw_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    await context.bot.send_message(chat_id, "⏰ **HORA DO SORTEIO!**")
    await run_draw_logic(context, chat_id)
    set_setting('scheduled_date', '')

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    try:
        date_str = " ".join(context.args)
        run_time = datetime.strptime(date_str, '%d/%m/%Y %H:%M')
        if run_time < datetime.now(): return await update.message.reply_text("⚠️ Data passada.")
        jobs = context.job_queue.get_jobs_by_name("scheduled_draw")
        for job in jobs: job.schedule_removal()
        context.job_queue.run_once(auto_draw_job, run_time, chat_id=ADMIN_GROUP_ID, name="scheduled_draw")
        set_setting('scheduled_date', run_time.isoformat())
        await update.message.reply_text(f"✅ Agendado: **{date_str}**", parse_mode='Markdown')
    except: await update.message.reply_text("⚠️ Use: `/agendar DD/MM/AAAA HH:MM`")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    msg = update.message.text.replace('/broadcast', '').strip()
    if not msg: return
    conn = get_db()
    users = conn.execute("SELECT user_id FROM participants").fetchall()
    conn.close()
    await update.message.reply_text(f"📢 Enviando para {len(users)}...")
    for u in users:
        try: await context.bot.send_message(u['user_id'], f"📢 **AVISO:**\n\n{msg}", parse_mode='Markdown')
        except: pass
    await update.message.reply_text("✅ Concluído.")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 `{update.effective_chat.id}`", parse_mode='Markdown')

# --- MAIN ---
def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    
    reg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(registration_start, pattern='^join$')],
        states={
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reg_name)],
            REG_CPF: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reg_cpf)],
            REG_INSTAGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reg_instagram)]
        },
        fallbacks=[CommandHandler('cancel', cancel_reg)]
    )

    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_start, pattern='^edit_start_menu$')],
        states={
            EDIT_CHOICE: [CallbackQueryHandler(edit_choice, pattern='^edit_key:')],
            EDIT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_input)]
        },
        fallbacks=[CallbackQueryHandler(edit_cancel, pattern='^cancel_edit$')]
    )
    
    pix_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(config_pix_start, pattern='^config_pix_start$')],
        states={
            SET_PIX_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pix_key)],
            SET_PIX_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pix_name)],
            SET_PIX_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pix_city)],
        },
        fallbacks=[CallbackQueryHandler(cancel_config_pix, pattern='^cancel_config_pix$')]
    )

    coupon_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_coupon, pattern='^ask_coupon$')],
        states={COUPON_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_coupon)]},
        fallbacks=[CommandHandler('cancel', cancel_coupon)]
    )
    
    app.add_handler(reg_conv)
    app.add_handler(coupon_conv)
    app.add_handler(edit_conv)
    app.add_handler(pix_conv)
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("painel", admin_panel))
    app.add_handler(CommandHandler("addcupom", add_coupon_command))
    app.add_handler(CommandHandler("ranking", ranking_command))
    
    app.add_handler(CommandHandler("agendar", schedule_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("addchannel", add_channel_command))
    
    app.add_handler(CallbackQueryHandler(main_button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, proof_handler))
    
    print("🚀 BOT PREMIUM (FINAL) INICIADO")
    app.run_polling()

if __name__ == '__main__':
    main()