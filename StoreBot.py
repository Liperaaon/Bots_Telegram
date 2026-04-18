"""
================================================================================
        STORE BOT PRO 19.2 (GIFT CARDS & RECUPERAÇÃO DE CARRINHO)
================================================================================
   
   Novidades desta versão:
   1. 🎁 Sistema de Gift Cards (Admin cria, Cliente resgata crédito).
   2. 🔔 Recuperação de Carrinho Abandonado (Mensagem automática após X tempo).
   3. 💰 Uso de Saldo/Cashback no Checkout.

================================================================================
"""

import telebot
from telebot import types
import sqlite3
import time
from datetime import datetime, timedelta
import threading
import qrcode
import io
import os
import shutil
import random
import logging
import math
import csv
import string

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# =============================================================================
# CONFIGURAÇÕES INICIAIS
# =============================================================================

API_TOKEN = 
ADMIN_GROUP_ID = 

# Caminhos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, "DB")
BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")
DB_NAME = "loja_bot_enterprise.db" 
DB_PATH = os.path.join(DB_FOLDER, DB_NAME)

# Bot
bot = telebot.TeleBot(API_TOKEN, threaded=False)

# --- ESTADO EM MEMÓRIA ---
# Carrinho: {user_id: {'itens': [...], 'last_update': timestamp}}
carrinho_sessao = {}       
pagamentos_pendentes = {}   
db_lock = threading.Lock()

ITEMS_PER_PAGE = 5
ABANDONED_CART_DELAY_HOURS = 1 # Tempo para considerar carrinho abandonado

# =============================================================================
# MOTOR DE BANCO DE DADOS
# =============================================================================

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row 
    return conn

def setup_database():
    if not os.path.exists(DB_FOLDER): os.makedirs(DB_FOLDER)
    if not os.path.exists(BACKUP_FOLDER): os.makedirs(BACKUP_FOLDER)

    with db_lock:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS clientes (user_id INTEGER PRIMARY KEY, nome TEXT, username TEXT, telefone TEXT, data_cadastro DATETIME, ultimo_acesso DATETIME, compras_total INTEGER DEFAULT 0, valor_gasto_total REAL DEFAULT 0.0, saldo_cashback REAL DEFAULT 0.0)''')
            c.execute('''CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, descricao TEXT, preco REAL NOT NULL, preco_promocional REAL, estoque INTEGER DEFAULT 0, conteudo TEXT, tipo TEXT DEFAULT 'digital', categoria TEXT DEFAULT 'geral', status TEXT DEFAULT 'ativo', data_criacao DATETIME, foto_id TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, data_venda DATETIME, valor_total REAL, metodo_pagamento TEXT DEFAULT 'pix', status TEXT DEFAULT 'pendente', cupom_usado TEXT, txid_pix TEXT, produto TEXT, valor_pago REAL, comprador_nome TEXT, comprador_id INTEGER, FOREIGN KEY(cliente_id) REFERENCES clientes(user_id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS venda_itens (id INTEGER PRIMARY KEY AUTOINCREMENT, venda_id INTEGER, produto_id INTEGER, quantidade INTEGER, preco_unitario REAL, subtotal REAL, FOREIGN KEY(venda_id) REFERENCES vendas(id), FOREIGN KEY(produto_id) REFERENCES produtos(id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT, descricao TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS welcome_media (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, file_type TEXT, legenda TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS cupons (codigo TEXT PRIMARY KEY, tipo_desconto TEXT DEFAULT 'porcentagem', valor REAL, usos_maximos INTEGER DEFAULT 999999, usos_atuais INTEGER DEFAULT 0, data_expiracao DATETIME, ativo BOOLEAN DEFAULT 1)''')
            
            # NOVA TABELA: GIFT CARDS
            c.execute('''CREATE TABLE IF NOT EXISTS gift_cards (codigo TEXT PRIMARY KEY, valor REAL, criado_em DATETIME, resgatado_por INTEGER, resgatado_em DATETIME, status TEXT DEFAULT 'ativo')''')

            migrations = ["ALTER TABLE produtos ADD COLUMN foto_id TEXT", "ALTER TABLE vendas ADD COLUMN comprador_id INTEGER", "ALTER TABLE vendas ADD COLUMN comprador_nome TEXT", "ALTER TABLE clientes ADD COLUMN saldo_cashback REAL DEFAULT 0.0"]
            for sql in migrations:
                try: c.execute(sql)
                except sqlite3.OperationalError: pass

            defaults = {
                "pix_key": "seu@email.com", "pix_name": "Seu Nome", "pix_city": "Sao Paulo", 
                "store_name": "BotStore", "welcome_text": "Olá! Bem-vindo à {store_name}.", 
                "support_url": "https://t.me/seusuario", "loyalty_goal": "5", "welcome_media_enabled": "false",
                "coupons_enabled": "false", "loyalty_enabled": "false"
            }
            for k, v in defaults.items(): c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
            conn.commit()
    print(f"✅ Banco de Dados inicializado em: {DB_PATH}")

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def registrar_cliente_acesso(user):
    try:
        with db_lock:
            with get_db_connection() as conn:
                agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor = conn.execute("UPDATE clientes SET nome=?, username=?, ultimo_acesso=? WHERE user_id=?", (user.first_name, user.username, agora, user.id))
                if cursor.rowcount == 0: conn.execute("INSERT INTO clientes (user_id, nome, username, data_cadastro, ultimo_acesso) VALUES (?, ?, ?, ?, ?)", (user.id, user.first_name, user.username, agora, agora))
                conn.commit()
    except: pass

def get_config(key):
    try:
        with db_lock:
            with get_db_connection() as conn: res = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return res[0] if res else ""
    except: return ""

def set_config(key, value):
    try:
        with db_lock:
            with get_db_connection() as conn:
                conn.execute("INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))
                conn.commit()
    except: pass

def realizar_backup():
    try:
        if not os.path.exists(DB_PATH): return None
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(BACKUP_FOLDER, f"backup_{timestamp}.db")
        with db_lock: shutil.copy2(DB_PATH, path)
        return path
    except: return None

def gerar_relatorio_csv():
    try:
        filepath = os.path.join(BACKUP_FOLDER, f"vendas_{datetime.now().strftime('%Y%m%d')}.csv")
        with db_lock:
            with get_db_connection() as conn:
                vendas = conn.execute("SELECT v.id, v.data_venda, v.comprador_nome, v.valor_total, v.status, v.produto FROM vendas v ORDER BY v.data_venda DESC").fetchall()
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Data', 'Cliente', 'Valor', 'Status', 'Produtos'])
            for v in vendas:
                writer.writerow([v[0], v[1], v[2], f"{v[3]:.2f}", v[4], v[5]])
        return filepath
    except Exception as e:
        logging.error(f"Erro CSV: {e}")
        return None

# =============================================================================
# GIFT CARDS (LÓGICA)
# =============================================================================

def gerar_codigo_gift(tamanho=8):
    chars = string.ascii_uppercase + string.digits
    return 'GIFT-' + ''.join(random.choice(chars) for _ in range(tamanho))

@bot.message_handler(commands=['criar_gift'])
def admin_criar_gift(message):
    if message.chat.id != ADMIN_GROUP_ID: return
    try:
        valor = float(message.text.split()[1])
        codigo = gerar_codigo_gift()
        
        with db_lock:
            with get_db_connection() as conn:
                conn.execute("INSERT INTO gift_cards (codigo, valor, criado_em) VALUES (?, ?, ?)", 
                             (codigo, valor, datetime.now()))
                conn.commit()
        
        bot.reply_to(message, f"🎁 **Gift Card Criado!**\n\nCódigo: `{codigo}`\nValor: R$ {valor:.2f}\n\nEnvie este código para o cliente resgatar.")
    except:
        bot.reply_to(message, "❌ Uso correto: `/criar_gift 50.00`")

# =============================================================================
# RECUPERAÇÃO DE CARRINHO (JOB)
# =============================================================================

def job_recuperacao_carrinho():
    while True:
        try:
            agora = datetime.now()
            limite = agora - timedelta(hours=ABANDONED_CART_DELAY_HOURS)
            
            usuarios_para_remover = []
            
            # Itera sobre carrinhos em memória
            # (Em produção ideal, carrinhos estariam no DB, mas aqui usamos memória por simplicidade)
            for uid, dados in carrinho_sessao.items():
                # Se tiver itens E última atualização for antiga E ainda não foi notificado
                if dados.get('itens') and dados.get('last_update') < limite and not dados.get('notificado'):
                    try:
                        # Gera oferta de recuperação
                        total = sum(i['preco'] for i in dados['itens'])
                        novo_total = total * 0.95 # 5% desconto
                        
                        mk = types.InlineKeyboardMarkup()
                        mk.add(types.InlineKeyboardButton(f"🔥 Fechar por R$ {novo_total:.2f}", callback_data="checkout_recuperacao"))
                        
                        txt = (f"🔔 **Ei, psiu!**\n\n"
                               f"Vi que você esqueceu uns itens no carrinho...\n"
                               f"O que acha de fechar agora com **5% DE DESCONTO**?\n\n"
                               f"De: ~R$ {total:.2f}~\n"
                               f"Por: **R$ {novo_total:.2f}**")
                        
                        bot.send_message(uid, txt, reply_markup=mk, parse_mode="Markdown")
                        dados['notificado'] = True # Marca para não mandar de novo
                        
                    except Exception as e:
                        print(f"Erro ao notificar {uid}: {e}")
                        # Se não conseguir mandar msg (bloqueio), remove carrinho
                        usuarios_para_remover.append(uid)
            
            # Limpeza de memória
            for uid in usuarios_para_remover:
                del carrinho_sessao[uid]
                
        except Exception as e:
            print(f"Erro no job de recuperação: {e}")
        
        time.sleep(300) # Roda a cada 5 minutos

threading.Thread(target=job_recuperacao_carrinho, daemon=True).start()

# =============================================================================
# PAINEL ADMINISTRATIVO
# =============================================================================

@bot.message_handler(commands=['painel', 'admin'])
def painel_principal(message):
    if message.chat.id != ADMIN_GROUP_ID: return 
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📦 Produtos", callback_data="admin_prods"),
               types.InlineKeyboardButton("🎟️ Cupões", callback_data="admin_coupons"))
    markup.add(types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
               types.InlineKeyboardButton("📥 Baixar Relatório", callback_data="admin_csv"))
    markup.add(types.InlineKeyboardButton("💾 Backup DB", callback_data="admin_backup"),
               types.InlineKeyboardButton("⚙️ Config", callback_data="admin_config"))
    markup.add(types.InlineKeyboardButton("❌ Fechar", callback_data="admin_close"))
    
    try:
        with db_lock:
            with get_db_connection() as conn:
                leads = conn.execute("SELECT count(*) FROM clientes").fetchone()[0]
                vendas = conn.execute("SELECT count(*) FROM vendas WHERE status='pago'").fetchone()[0]
        bot.send_message(message.chat.id, f"🚀 **PAINEL ULTIMATE 19.2**\n👥 Clientes: {leads} | 🛒 Vendas: {vendas}", reply_markup=markup, parse_mode="Markdown")
    except: bot.send_message(message.chat.id, "❌ Erro painel.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_router(call):
    if call.message.chat.id != ADMIN_GROUP_ID: return
    d = call.data
    
    try:
        if d == "admin_main": painel_principal(call.message); bot.delete_message(call.message.chat.id, call.message.message_id)
        elif d == "admin_close": bot.delete_message(call.message.chat.id, call.message.message_id)
        elif d == "admin_prods":
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("➕ Novo Produto", callback_data="act_add"), types.InlineKeyboardButton("📋 Listar", callback_data="act_list"))
            mk.add(types.InlineKeyboardButton("✏️ Editar", callback_data="act_edit_menu"), types.InlineKeyboardButton("🗑️ Excluir", callback_data="act_del"))
            mk.add(types.InlineKeyboardButton("🔙", callback_data="admin_main"))
            bot.edit_message_text("📦 **Gestão de Produtos**", call.message.chat.id, call.message.message_id, reply_markup=mk)
        elif d == "admin_coupons":
            mk = types.InlineKeyboardMarkup(row_width=1)
            mk.add(types.InlineKeyboardButton("➕ Criar Cupão", callback_data="cup_add"), types.InlineKeyboardButton("📋 Listar", callback_data="cup_list"), types.InlineKeyboardButton("🗑️ Apagar", callback_data="cup_del"), types.InlineKeyboardButton("🔙", callback_data="admin_main"))
            bot.edit_message_text("🎟️ **Gestão de Cupões**", call.message.chat.id, call.message.message_id, reply_markup=mk)
        elif d == "admin_broadcast":
            msg = bot.send_message(call.message.chat.id, "📢 **Broadcast**\nEnvie a mensagem para todos:\n/cancelar para sair")
            bot.register_next_step_handler(msg, step_broadcast_send)
        elif d == "admin_backup":
            p = realizar_backup()
            if p: 
                with open(p, 'rb') as f: bot.send_document(call.message.chat.id, f, caption="📦 Backup DB")
            painel_principal(call.message)
        elif d == "admin_csv":
            p = gerar_relatorio_csv()
            if p:
                with open(p, 'rb') as f: bot.send_document(call.message.chat.id, f, caption="📊 Relatório de Vendas (CSV)")
            else: bot.answer_callback_query(call.id, "Erro ao gerar relatório.")
            painel_principal(call.message)
        elif d == "admin_config":
            st_c = get_config("coupons_enabled"); em_c = "🟢" if st_c == "true" else "🔴"
            st_l = get_config("loyalty_enabled"); em_l = "🟢" if st_l == "true" else "🔴"
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("🏷️ Nome Loja", callback_data="cfg_store_name"), types.InlineKeyboardButton("📷 Mídia Start", callback_data="cfg_media_menu"))
            mk.add(types.InlineKeyboardButton("💬 Texto Start", callback_data="cfg_welcome_text"), types.InlineKeyboardButton("🔑 Chave PIX", callback_data="cfg_pix_key"))
            mk.add(types.InlineKeyboardButton("👤 Beneficiário", callback_data="cfg_pix_name"), types.InlineKeyboardButton("🏆 Meta Fidelidade", callback_data="cfg_loyalty_goal"))
            mk.add(types.InlineKeyboardButton(f"🎟️ Cupões: {em_c}", callback_data="cfg_toggle_coupons"), types.InlineKeyboardButton(f"💎 Fidelidade: {em_l}", callback_data="cfg_toggle_loyalty"))
            mk.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="admin_main"))
            bot.edit_message_text("⚙️ **Configuração Avançada**", call.message.chat.id, call.message.message_id, reply_markup=mk)
    except Exception as e: print(f"Erro router admin: {e}")

# --- CONFIGURAÇÃO ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('cfg_'))
def config_handler(call):
    k = call.data.replace("cfg_", "")
    if k in ["toggle_coupons", "toggle_loyalty"]:
        key = "coupons_enabled" if k == "toggle_coupons" else "loyalty_enabled"
        curr = get_config(key)
        new_val = "false" if curr == "true" else "true"
        set_config(key, new_val)
        bot.answer_callback_query(call.id, "Alterado!")
        # Refresh
        st_c = get_config("coupons_enabled"); em_c = "🟢" if st_c == "true" else "🔴"
        st_l = get_config("loyalty_enabled"); em_l = "🟢" if st_l == "true" else "🔴"
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🏷️ Nome Loja", callback_data="cfg_store_name"), types.InlineKeyboardButton("📷 Mídia Start", callback_data="cfg_media_menu"))
        mk.add(types.InlineKeyboardButton("💬 Texto Start", callback_data="cfg_welcome_text"), types.InlineKeyboardButton("🔑 Chave PIX", callback_data="cfg_pix_key"))
        mk.add(types.InlineKeyboardButton("👤 Beneficiário", callback_data="cfg_pix_name"), types.InlineKeyboardButton("🏆 Meta Fidelidade", callback_data="cfg_loyalty_goal"))
        mk.add(types.InlineKeyboardButton(f"🎟️ Cupões: {em_c}", callback_data="cfg_toggle_coupons"), types.InlineKeyboardButton(f"💎 Fidelidade: {em_l}", callback_data="cfg_toggle_loyalty"))
        mk.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="admin_main"))
        bot.edit_message_text("⚙️ **Configuração Avançada**", call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    if k == "media_menu":
        st = get_config("welcome_media_enabled"); em = "🟢" if st == "true" else "🔴"; tog = "false" if st == "true" else "true"
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton(f"Status: {em}", callback_data=f"cfg_set_welcome_media_enabled_{tog}"))
        mk.add(types.InlineKeyboardButton("➕ Add Mídia", callback_data="act_add_media"), types.InlineKeyboardButton("🗑️ Limpar", callback_data="act_clear_media"))
        mk.add(types.InlineKeyboardButton("🔙", callback_data="admin_config"))
        bot.edit_message_text(f"📷 **Mídia /start**\nAtivado: {em}", call.message.chat.id, call.message.message_id, reply_markup=mk)
        return
    
    if k.startswith("set_welcome_media_enabled_"):
        set_config("welcome_media_enabled", k.split("_")[-1])
        bot.answer_callback_query(call.id, "Salvo!"); admin_router(type('obj', (object,), {'data': 'admin_config', 'message': call.message})())
        return

    bot.register_next_step_handler(bot.send_message(call.message.chat.id, f"✍️ Novo valor para **{k}**:"), step_save_config, k)

def step_save_config(m, k): set_config(k, m.text); bot.reply_to(m, "✅ Salvo!"); painel_principal(m)
def step_save_media(m):
    fid = m.photo[-1].file_id if m.photo else m.video.file_id if m.video else None
    ftype = 'photo' if m.photo else 'video' if m.video else None
    if fid:
        with db_lock:
            with get_db_connection() as conn: conn.execute("INSERT INTO welcome_media (file_id, file_type) VALUES (?, ?)", (fid, ftype)); conn.commit()
        bot.reply_to(m, "✅ Mídia salva!"); painel_principal(m)

def step_broadcast_send(m):
    if m.text == "/cancelar": return bot.reply_to(m, "Cancelado.")
    with db_lock:
        with get_db_connection() as conn: clients = conn.execute("SELECT user_id FROM clientes").fetchall()
    ok = 0
    for c in clients:
        try:
            if m.content_type == 'text': bot.send_message(c[0], m.text)
            elif m.content_type == 'photo': bot.send_photo(c[0], m.photo[-1].file_id, caption=m.caption)
            ok += 1; time.sleep(0.05)
        except: pass
    bot.reply_to(m, f"✅ Enviado para {ok} clientes.")

# --- PRODUTOS E CUPONS (FUNÇÕES AUXILIARES) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(('act_', 'cup_')))
def product_coupon_router(call):
    if call.message.chat.id != ADMIN_GROUP_ID: return
    act = call.data
    
    # PRODUTOS
    if act == "act_list":
        with db_lock:
            with get_db_connection() as conn: prods = conn.execute("SELECT id, nome, preco, estoque FROM produtos WHERE status='ativo'").fetchall()
        txt = "📋 **Catálogo:**\n\n" + ("\n".join([f"🆔 `{p[0]}` | {p[1]} | R${p[2]} | Est: {p[3]}" for p in prods]) if prods else "Vazio")
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙", callback_data="admin_prods")))
    elif act == "act_add": bot.register_next_step_handler(bot.send_message(call.message.chat.id, "📦 Nome:"), step_nome)
    elif act == "act_edit_menu": bot.register_next_step_handler(bot.send_message(call.message.chat.id, "✏️ ID:"), step_edit_select)
    elif act == "act_del": bot.register_next_step_handler(bot.send_message(call.message.chat.id, "🗑️ ID:"), step_del_input)
    elif act == "act_add_media": bot.register_next_step_handler(bot.send_message(call.message.chat.id, "📸 Envie Foto/Vídeo:"), step_save_media)
    elif act == "act_clear_media":
        with db_lock:
            with get_db_connection() as conn: conn.execute("DELETE FROM welcome_media"); conn.commit()
        bot.answer_callback_query(call.id, "Limpo!"); painel_principal(call.message)
    
    # CUPONS
    elif act == "cup_list":
        with db_lock:
            with get_db_connection() as conn: cups = conn.execute("SELECT codigo, valor, usos_atuais FROM cupons WHERE ativo=1").fetchall()
        txt = "🎟️ **Cupões Ativos:**\n\n" + ("\n".join([f"• `{c[0]}`: {c[1]}% OFF (Usado {c[2]}x)" for c in cups]) if cups else "Nenhum.")
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙", callback_data="admin_coupons")))
    elif act == "cup_add": bot.register_next_step_handler(bot.send_message(call.message.chat.id, "🎟️ Envie: `CODIGO PORCENTAGEM`"), step_cup_add)
    elif act == "cup_del": bot.register_next_step_handler(bot.send_message(call.message.chat.id, "🗑️ Envie o CÓDIGO:"), step_cup_del)

def step_nome(m): bot.register_next_step_handler(bot.reply_to(m, "💰 Preço (Ex: 10.00):"), step_preco, m.text)
def step_preco(m, n): bot.register_next_step_handler(bot.reply_to(m, "🔢 Estoque:"), step_estoque, n, float(m.text.replace(',', '.')))
def step_estoque(m, n, p): bot.register_next_step_handler(bot.reply_to(m, "📂 Conteúdo (Link/Texto):"), step_conteudo, n, p, int(m.text))
def step_conteudo(m, n, p, e): bot.register_next_step_handler(bot.reply_to(m, "📸 Envie a **FOTO** (ou digite 'pular'):"), step_foto, n, p, e, m.text)
def step_foto(m, n, p, e, c):
    fid = m.photo[-1].file_id if m.content_type == 'photo' else None
    with db_lock:
        with get_db_connection() as conn: conn.execute("INSERT INTO produtos (nome, preco, estoque, conteudo, data_criacao, foto_id) VALUES (?, ?, ?, ?, ?, ?)", (n, p, e, c, datetime.now(), fid)); conn.commit()
    bot.reply_to(m, "✅ Produto cadastrado!"); painel_principal(m)

def step_edit_select(m):
    with db_lock:
        with get_db_connection() as conn: p = conn.execute("SELECT * FROM produtos WHERE id=?", (int(m.text),)).fetchone()
    if p: bot.register_next_step_handler(bot.reply_to(m, f"✏️ Editando **{p[1]}**\nEnvie: `PRECO ESTOQUE`"), step_edit_save, int(m.text))
def step_edit_save(m, pid):
    p, e = m.text.split()
    with db_lock:
        with get_db_connection() as conn: conn.execute("UPDATE produtos SET preco=?, estoque=? WHERE id=?", (float(p), int(e), pid)); conn.commit()
    bot.reply_to(m, "✅ Atualizado!")
def step_del_input(m):
    with db_lock:
        with get_db_connection() as conn: conn.execute("DELETE FROM produtos WHERE id=?", (m.text,)); conn.commit()
    bot.reply_to(m, "🗑 Deletado.")

def step_cup_add(m):
    c, v = m.text.split()
    with db_lock:
        with get_db_connection() as conn: conn.execute("INSERT INTO cupons (codigo, valor, tipo_desconto, ativo) VALUES (?, ?, 'porcentagem', 1)", (c.upper(), float(v))); conn.commit()
    bot.reply_to(m, "✅ Cupom criado!"); painel_principal(m)
def step_cup_del(m):
    with db_lock:
        with get_db_connection() as conn: conn.execute("DELETE FROM cupons WHERE codigo=?", (m.text.upper(),)); conn.commit()
    bot.reply_to(m, "🗑 Deletado.")

# =============================================================================
# ÁREA DO CLIENTE (START & MENU)
# =============================================================================

@bot.message_handler(commands=['start'])
def inicio_loja(message):
    if message.chat.type != 'private': return
    registrar_cliente_acesso(message.from_user)
    
    try:
        s_name = get_config("store_name") or "Loja"
        w_text = get_config("welcome_text") or "Bem vindo!"
        txt = w_text.replace("{store_name}", s_name).replace("{user_name}", message.from_user.first_name)
        
        media = None
        if get_config("welcome_media_enabled") == "true":
            with db_lock:
                with get_db_connection() as conn: media = conn.execute("SELECT file_id, file_type FROM welcome_media ORDER BY RANDOM() LIMIT 1").fetchone()

        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("🛒 ACESSAR LOJA", callback_data="abrir_loja_pg_0"))
        
        btns = [types.InlineKeyboardButton("📦 Pedidos", callback_data="meus_pedidos")]
        if get_config("loyalty_enabled") == "true": btns.append(types.InlineKeyboardButton("💎 Fidelidade", callback_data="fidelidade"))
        mk.row(*btns)
        
        # BOTÕES AUXILIARES
        mk.add(types.InlineKeyboardButton("🛒 Ver Carrinho", callback_data="ver_carrinho"))
        mk.add(types.InlineKeyboardButton("🎁 Resgatar Gift Card", callback_data="resgatar_gift"), types.InlineKeyboardButton("🆘 Suporte", callback_data="suporte_start"))
        
        if media:
            if media[1] == 'photo': bot.send_photo(message.chat.id, media[0], caption=txt, reply_markup=mk, parse_mode="Markdown")
            else: bot.send_video(message.chat.id, media[0], caption=txt, reply_markup=mk, parse_mode="Markdown")
        else: bot.send_message(message.chat.id, txt, reply_markup=mk, parse_mode="Markdown")
    except Exception as e: print(f"Erro start: {e}"); bot.send_message(message.chat.id, "Bem vindo!", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data == "inicio")
def back_start(c): inicio_loja(c.message); bot.delete_message(c.message.chat.id, c.message.message_id)

# =============================================================================
# LOJA COM PAGINAÇÃO E CARRINHO
# =============================================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith('abrir_loja'))
def loja_paginada(c):
    try:
        pg = int(c.data.split('_')[-1]) if 'pg' in c.data else 0
        
        with db_lock:
            with get_db_connection() as conn: 
                all_prods = conn.execute("SELECT id, nome, preco, estoque FROM produtos WHERE status='ativo'").fetchall()
        
        total_p = len(all_prods)
        total_pages = math.ceil(total_p / ITEMS_PER_PAGE)
        start = pg * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        prods_pg = all_prods[start:end]
        
        mk = types.InlineKeyboardMarkup()
        if not all_prods: txt = "🚫 **Loja Vazia.**"
        else:
            txt = f"🛒 **CATÁLOGO (Pág {pg+1}/{total_pages})**\nEscolha um item:"
            for p in prods_pg:
                btn = f"🚫 {p[1]}" if p[3] <= 0 else f"📦 {p[1]} - R$ {p[2]:.2f}"
                cb = "sem_estoque" if p[3] <= 0 else f"ver_{p[0]}"
                mk.add(types.InlineKeyboardButton(btn, callback_data=cb))
            
            nav = []
            if pg > 0: nav.append(types.InlineKeyboardButton("⬅️ Ant", callback_data=f"abrir_loja_pg_{pg-1}"))
            if end < total_p: nav.append(types.InlineKeyboardButton("Prox ➡️", callback_data=f"abrir_loja_pg_{pg+1}"))
            if nav: mk.row(*nav)
            
        mk.add(types.InlineKeyboardButton("🛒 Ver Carrinho", callback_data="ver_carrinho"))
        mk.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="inicio"))
        
        try: bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=mk, parse_mode="Markdown")
        except: bot.send_message(c.message.chat.id, txt, reply_markup=mk, parse_mode="Markdown")
    except Exception as e: print(f"Erro loja: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith('ver_'))
def ver_produto(c):
    if c.data == "ver_carrinho": return ver_carrinho(c)
    try:
        pid = c.data.split('_')[1]
        with db_lock:
            with get_db_connection() as conn: p = conn.execute("SELECT * FROM produtos WHERE id=?", (pid,)).fetchone()
        
        if not p or p[5] <= 0: return bot.answer_callback_query(c.id, "Esgotado.")
        
        # Estado temporário para compra rápida
        carrinho_sessao[c.message.chat.id] = {'itens': [], 'last_update': datetime.now(), 'notificado': False} # Garante estrutura
        
        txt = f"📦 **{p[1]}**\n\n💰 Valor: **R$ {p[3]:.2f}**\n📦 Disponível: {p[5]}\n\n{p[2] if p[2] else ''}"
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("➕ Adicionar ao Carrinho", callback_data=f"add_carrinho_{pid}"))
        mk.add(types.InlineKeyboardButton("✅ Comprar Agora", callback_data=f"checkout_direto_{pid}"))
        mk.add(types.InlineKeyboardButton("🔙 Loja", callback_data="abrir_loja_pg_0"))
        
        bot.delete_message(c.message.chat.id, c.message.message_id)
        if p[11]: bot.send_photo(c.message.chat.id, p[11], caption=txt, reply_markup=mk, parse_mode="Markdown")
        else: bot.send_message(c.message.chat.id, txt, reply_markup=mk, parse_mode="Markdown")
    except: pass

# --- CARRINHO DE COMPRAS (ESTRUTURA NOVA) ---
@bot.callback_query_handler(func=lambda c: c.data.startswith('add_carrinho_'))
def add_carrinho(c):
    pid = int(c.data.split('_')[-1])
    uid = c.message.chat.id
    with db_lock:
        with get_db_connection() as conn: p = conn.execute("SELECT id, nome, preco FROM produtos WHERE id=?", (pid,)).fetchone()
    
    if uid not in carrinho_sessao: carrinho_sessao[uid] = {'itens': [], 'last_update': datetime.now(), 'notificado': False}
    
    carrinho_sessao[uid]['itens'].append({'id': p[0], 'nome': p[1], 'preco': p[2]})
    carrinho_sessao[uid]['last_update'] = datetime.now()
    
    bot.answer_callback_query(c.id, f"✅ {p[1]} adicionado!", show_alert=True)
    ver_carrinho(c)

@bot.callback_query_handler(func=lambda c: c.data == 'ver_carrinho')
def ver_carrinho(c):
    uid = c.message.chat.id
    sessao = carrinho_sessao.get(uid)
    
    if not sessao or not sessao['itens']:
        bot.answer_callback_query(c.id, "Carrinho vazio!")
        return loja_paginada(c)
    
    items = sessao['itens']
    total = sum(i['preco'] for i in items)
    
    # Verifica saldo cashback
    saldo = 0.0
    with db_lock:
        with get_db_connection() as conn: 
            res = conn.execute("SELECT saldo_cashback FROM clientes WHERE user_id=?", (uid,)).fetchone()
            if res: saldo = res[0]

    txt = "🛒 **SEU CARRINHO:**\n\n" + "\n".join([f"• {i['nome']} (R${i['preco']:.2f})" for i in items])
    txt += f"\n\n💰 **Total: R$ {total:.2f}**"
    if saldo > 0: txt += f"\n💎 Saldo em conta: R$ {saldo:.2f}"
    
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("✅ Finalizar Compra", callback_data="checkout_carrinho"))
    mk.add(types.InlineKeyboardButton("🗑️ Esvaziar", callback_data="limpar_carrinho"))
    mk.add(types.InlineKeyboardButton("🔙 Continuar Comprando", callback_data="abrir_loja_pg_0"))
    
    try: bot.edit_message_text(txt, uid, c.message.message_id, reply_markup=mk, parse_mode="Markdown")
    except: 
        bot.delete_message(uid, c.message.message_id)
        bot.send_message(uid, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == 'limpar_carrinho')
def limpar_carrinho(c):
    if c.message.chat.id in carrinho_sessao: del carrinho_sessao[c.message.chat.id]
    bot.answer_callback_query(c.id, "Carrinho limpo!")
    loja_paginada(c)

# --- GIFT CARD RESGATE ---
@bot.callback_query_handler(func=lambda c: c.data == 'resgatar_gift')
def resgatar_gift_start(c):
    msg = bot.send_message(c.message.chat.id, "🎁 **RESGATAR GIFT CARD**\n\nEnvie o código do seu gift card abaixo:")
    bot.register_next_step_handler(msg, resgatar_gift_check)

def resgatar_gift_check(m):
    codigo = m.text.strip().upper()
    uid = m.from_user.id
    
    with db_lock:
        with get_db_connection() as conn:
            gift = conn.execute("SELECT valor FROM gift_cards WHERE codigo = ? AND status = 'ativo'", (codigo,)).fetchone()
            
            if gift:
                valor = gift[0]
                conn.execute("UPDATE gift_cards SET status='resgatado', resgatado_por=?, resgatado_em=? WHERE codigo=?", 
                             (uid, datetime.now(), codigo))
                conn.execute("UPDATE clientes SET saldo_cashback = saldo_cashback + ? WHERE user_id=?", (valor, uid))
                conn.commit()
                bot.reply_to(m, f"✅ **Sucesso!**\nVocê resgatou R$ {valor:.2f} em créditos.\nUse no checkout!")
            else:
                bot.reply_to(m, "❌ **Código inválido ou já usado.**")

# --- CHECKOUT (COM SALDO E RECUPERAÇÃO) ---
@bot.callback_query_handler(func=lambda c: c.data.startswith('checkout_') or c.data == "usar_saldo")
def checkout(c):
    uid = c.message.chat.id
    
    # Lógica para definir itens e total
    if c.data.startswith('checkout_direto_'):
        pid = int(c.data.split('_')[-1])
        with db_lock:
            with get_db_connection() as conn: p = conn.execute("SELECT id, nome, preco FROM produtos WHERE id=?", (pid,)).fetchone()
        itens_pedido = [{'id': p[0], 'nome': p[1], 'preco': p[2]}]
        total = p[2]
    elif c.data == 'checkout_recuperacao':
        # Recuperação de carrinho (já com desconto aplicado visualmente, mas vamos recalcular para segurança)
        if uid not in carrinho_sessao: return bot.answer_callback_query(c.id, "Sessão expirada.")
        itens_pedido = carrinho_sessao[uid]['itens']
        total = sum(i['preco'] for i in itens_pedido) * 0.95 # Aplica 5% real
    elif c.data == 'usar_saldo':
        # Recupera dados pendentes para aplicar saldo
        dados = pagamentos_pendentes.get(uid)
        if not dados: return
        itens_pedido = dados['itens']
        total = dados['total_original'] # Pega total sem desconto de saldo ainda
    else:
        # Checkout normal do carrinho
        if uid not in carrinho_sessao or not carrinho_sessao[uid]['itens']: return
        itens_pedido = carrinho_sessao[uid]['itens']
        total = sum(i['preco'] for i in itens_pedido)

    # Lógica de Saldo
    saldo_usado = 0.0
    saldo_disponivel = 0.0
    
    # Se clicou em "usar saldo" ou é a primeira vez no checkout
    with db_lock:
        with get_db_connection() as conn:
            res = conn.execute("SELECT saldo_cashback FROM clientes WHERE user_id=?", (uid,)).fetchone()
            if res: saldo_disponivel = res[0]

    # Se clicou em "usar saldo", abate
    if c.data == "usar_saldo" and saldo_disponivel > 0:
        if saldo_disponivel >= total:
            saldo_usado = total
            total = 0.0 # Pago 100% com saldo
        else:
            saldo_usado = saldo_disponivel
            total -= saldo_disponivel
    
    # Salva estado para pagamento
    pagamentos_pendentes[uid] = {
        'itens': itens_pedido, 
        'total': total, 
        'total_original': total + saldo_usado, # Para restaurar se cancelar
        'saldo_usado': saldo_usado
    }
    
    # Se total for 0, aprova direto!
    if total <= 0:
        aprovar_compra_saldo_total(c, uid)
        return

    # Pergunta sobre saldo se ainda não usou e tem disponivel
    if saldo_disponivel > 0 and saldo_usado == 0 and c.data != 'checkout_recuperacao': # Na recuperação já tem desconto, evita complexidade
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton(f"💎 Usar Saldo (R${saldo_disponivel:.2f})", callback_data="usar_saldo"))
        mk.add(types.InlineKeyboardButton("➡️ Pagar Total no PIX", callback_data="gerar_pix_final"))
        bot.edit_message_text(f"💰 Total: R$ {total:.2f}\n\nVocê tem saldo em conta. Deseja usar?", uid, c.message.message_id, reply_markup=mk)
        return

    # Se for checkout direto/carrinho normal e tiver cupom ativo
    if c.data != 'checkout_recuperacao' and get_config("coupons_enabled") == "true" and saldo_usado == 0:
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("🎟️ Tenho Cupom", callback_data="add_cupom_carrinho"), types.InlineKeyboardButton("🚫 Sem Cupom", callback_data="gerar_pix_final"))
        bot.edit_message_text(f"💰 Total: R$ {total:.2f}\n\nDeseja usar cupom?", uid, c.message.message_id, reply_markup=mk)
    else:
        gerar_pix_final(c.message, uid)

def aprovar_compra_saldo_total(c, uid):
    dados = pagamentos_pendentes.get(uid)
    # Desconta saldo do banco
    with db_lock:
        with get_db_connection() as conn:
            conn.execute("UPDATE clientes SET saldo_cashback = saldo_cashback - ? WHERE user_id=?", (dados['saldo_usado'], uid))
            conn.commit()
            
    # Simula "comprovante recebido" e aprova
    bot.send_message(uid, "💎 **Pagamento realizado com Saldo!** Processando...")
    # Chama função de entrega (reaproveitando logica existente)
    entregar_produtos(uid, dados, "SALDO")

@bot.callback_query_handler(func=lambda c: c.data == "gerar_pix_final")
def callback_pix(c): gerar_pix_final(c.message, c.message.chat.id)

def gerar_pix_final(message, uid):
    dados = pagamentos_pendentes.get(uid)
    if not dados: return
    
    payload = gerar_payload_pix(dados['total'])
    qr = qrcode.make(payload); bio = io.BytesIO(); qr.save(bio, 'PNG'); bio.seek(0)
    
    txt = f"✅ **PEDIDO GERADO!**\n\n📦 Itens: {len(dados['itens'])}\n💰 **Total a Pagar: R$ {dados['total']:.2f}**\n"
    if dados.get('saldo_usado', 0) > 0: txt += f"💎 Saldo usado: R$ {dados['saldo_usado']:.2f}\n"
    
    txt += "\n1️⃣ Copie o código.\n2️⃣ Pague no app.\n3️⃣ **Envie o comprovante AQUI.**"
    bot.send_photo(uid, bio, caption=txt, parse_mode="Markdown")
    bot.send_message(uid, f"`{payload}`", parse_mode="Markdown")

# --- APROVAÇÃO DE PAGAMENTO ---
@bot.message_handler(content_types=['photo', 'document'], chat_types=['private'])
def receber_comprovante(m):
    uid = m.chat.id
    if uid not in pagamentos_pendentes: return
    dados = pagamentos_pendentes[uid]
    
    lista_itens = "\n".join([f"• {i['nome']}" for i in dados['itens']])
    txt = f"🔔 **NOVO COMPROVANTE**\n👤 {m.from_user.first_name}\n💰 R$ {dados['total']:.2f}\n\n📦 Itens:\n{lista_itens}"
    
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("✅ Aprovar", callback_data=f"apv_{uid}"), types.InlineKeyboardButton("❌ Recusar", callback_data=f"neg_{uid}"))
    
    bot.forward_message(ADMIN_GROUP_ID, uid, m.message_id)
    bot.send_message(ADMIN_GROUP_ID, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith(('apv_', 'neg_')))
def decisao(c):
    if c.message.chat.id != ADMIN_GROUP_ID: return
    act, uid_str = c.data.split('_'); uid = int(uid_str)
    
    if act == 'neg':
        bot.edit_message_text("❌ RECUSADO", c.message.chat.id, c.message.message_id)
        bot.send_message(uid, "❌ Pagamento Recusado.")
        return

    # APROVAÇÃO
    if uid in pagamentos_pendentes:
        dados = pagamentos_pendentes[uid]
        
        # Se usou saldo parcial, desconta agora
        if dados.get('saldo_usado', 0) > 0:
            with db_lock:
                with get_db_connection() as conn:
                    conn.execute("UPDATE clientes SET saldo_cashback = saldo_cashback - ? WHERE user_id=?", (dados['saldo_usado'], uid))
                    conn.commit()
                    
        entregar_produtos(uid, dados, "PIX")
        bot.edit_message_text("✅ ENTREGUE", c.message.chat.id, c.message.message_id)

def entregar_produtos(uid, dados, metodo):
    try:
        links_entrega = []
        with db_lock:
            with get_db_connection() as conn:
                # Cria Venda Mestre
                nomes_prods = ", ".join([i['nome'] for i in dados['itens']])
                cur = conn.execute("INSERT INTO vendas (cliente_id, data_venda, valor_total, status, produto, valor_pago, metodo_pagamento) VALUES (?, ?, ?, 'pago', ?, ?, ?)", 
                             (uid, datetime.now(), dados['total'], nomes_prods, dados['total'], metodo))
                venda_id = cur.lastrowid
                
                # Processa Itens
                for item in dados['itens']:
                    conn.execute("UPDATE produtos SET estoque = estoque - 1 WHERE id = ?", (item['id'],))
                    conn.execute("INSERT INTO venda_itens (venda_id, produto_id, quantidade, preco_unitario, subtotal) VALUES (?, ?, 1, ?, ?)",
                                (venda_id, item['id'], item['preco'], item['preco']))
                    
                    res = conn.execute("SELECT conteudo FROM produtos WHERE id=?", (item['id'],)).fetchone()
                    conteudo = res[0] if res else "Erro: Conteúdo não encontrado."
                    links_entrega.append(f"📦 **{item['nome']}**:\n{conteudo}")

                conn.execute("UPDATE clientes SET compras_total = compras_total + 1 WHERE user_id = ?", (uid,))
                conn.commit()
        
        msg_entrega = f"🎉 **PAGAMENTO APROVADO!**\n\n" + "\n\n".join(links_entrega)
        bot.send_message(uid, msg_entrega, parse_mode="Markdown")
        
        if uid in pagamentos_pendentes: del pagamentos_pendentes[uid]
        if uid in carrinho_sessao: del carrinho_sessao[uid]
        
    except Exception as e: 
        print(f"Erro entrega: {e}")

# --- SUPORTE ---
@bot.callback_query_handler(func=lambda c: c.data == "suporte_start")
def suporte_start(c):
    msg = bot.send_message(c.message.chat.id, "🆘 **SUPORTE**\n\nEscreva sua mensagem abaixo:")
    bot.register_next_step_handler(msg, suporte_enviar)

def suporte_enviar(m):
    try:
        txt = f"🆘 **CHAMADO**\n👤: {m.from_user.first_name} (ID: `{m.chat.id}`)\n📝: {m.text}"
        bot.send_message(ADMIN_GROUP_ID, txt, parse_mode="Markdown")
        bot.reply_to(m, "✅ Enviado!")
    except: pass

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_GROUP_ID and m.reply_to_message)
def admin_responder_suporte(m):
    try:
        orig = m.reply_to_message.text
        if "ID: `" in orig:
            uid = int(orig.split("ID: `")[1].split("`")[0])
            bot.send_message(uid, f"👨‍💻 **SUPORTE:**\n\n{m.text}")
            bot.reply_to(m, "✅ Respondido.")
    except: pass

# --- UTILS ---
def gerar_payload_pix(valor):
    chave = get_config('pix_key')
    nome = get_config('pix_name')[0:25].upper()
    cidade = get_config('pix_city')[0:15].upper()
    txid = f"LOJA{int(time.time())}"
    valor_str = f"{valor:.2f}"
    payload = f"00020126{len('0014BR.GOV.BCB.PIX01'+str(len(chave))+chave):02}0014BR.GOV.BCB.PIX01{len(chave):02}{chave}52040000530398654{len(valor_str):02}{valor_str}5802BR59{len(nome):02}{nome}60{len(cidade):02}{cidade}62{len('05'+str(len(txid))+txid):02}05{len(txid):02}{txid}6304"
    polinomio = 0x1021; resultado = 0xFFFF
    for byte in payload.encode('utf-8'):
        resultado ^= (byte << 8)
        for _ in range(8):
            if (resultado & 0x8000): resultado = (resultado << 1) ^ polinomio
            else: resultado <<= 1
    return payload + f"{resultado & 0xFFFF:04X}"

# --- OUTROS HANDLERS ---
@bot.callback_query_handler(func=lambda c: c.data == "meus_pedidos")
def meus_pedidos(c):
    with db_lock:
        with get_db_connection() as conn: res = conn.execute("SELECT produto, valor_pago FROM vendas WHERE cliente_id=? ORDER BY id DESC LIMIT 5", (c.message.chat.id,)).fetchall()
    txt = "🤷‍♂️ **Sem compras.**" if not res else "🛍 **Últimas Compras:**\n\n" + "\n".join([f"✅ {r[0]} (R${r[1]:.2f})" for r in res])
    bot.edit_message_text(txt, c.message.chat.id, c.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙", callback_data="inicio")), parse_mode="Markdown")

if __name__ == "__main__":
    print("🚀 Inicializando Store Bot Pro 19.2 (Gift & Recovery)...")
    setup_database()
    print("✅ Banco de Dados verificado.")
    print("🤖 Bot iniciado!")
    bot.infinity_polling()