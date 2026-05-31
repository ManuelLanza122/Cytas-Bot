import os
import re
import sqlite3
import random
from datetime import datetime
import telebot
from telebot import types
import pytz

# ==========================================
# ⚙️ CONFIGURACIÓN PRINCIPAL Y PRECIOS (VALORES ALTOS)
# ==========================================
TOKEN = "TU_TELEGRAM_BOT_TOKEN_AQUÍ"          # 👈 Tu Token de BotFather
ID_ADMIN = 123456789                     # 👈 Tu ID de Telegram (numérico)
ID_CANAL_SOLICITUDES = -1002345678901    # 👈 Canal para auditar comprobantes (-100...)

bot = telebot.TeleBot(TOKEN)
ZONA_HORARIA = pytz.timezone('America/Bogota')

# 💰 NUEVA TABLA DE TARIFAS ELEVADAS
COSTO_LIKE = 5                           # 💚 Sube de 2 a 5 monedas
COSTO_SUPERLIKE = 50                     # 💌 Sube de 30 a 50 monedas
COSTO_FILTRO_BUSQUEDA = 30               # 🎯 Sube de 15 a 30 monedas
COSTO_RULETA = 25                        # 🎰 Sube de 10 a 25 monedas
COSTO_MENSAJE = 2                        # 💬 Sube de 1 a 2 monedas por mensaje enviado
MINIMO_RETIRABLE_MONEDAS = 2500          

# 🎁 EXPANDIDO: CATÁLOGO COMPLETO DE 20 REGALOS TRADUCIDO AL MOTOR DINÁMICO
CATALOGO_REGALOS = {
    1: ("🌹 Rosa Roja", 10),
    2: ("🍫 Chocolates Finos", 20),
    3: ("☕ Café Caliente", 30),
    4: ("🍦 Helado Dulce", 40),
    5: ("🍕 Rebanada de Pizza", 50),
    6: ("🍔 Combo Hamburguesa", 80),
    7: ("🍿 Cine & Palomitas", 100),
    8: ("🧸 Peluche Lindo", 150),
    9: ("💐 Ramo de Flores", 200),
    10: ("🎵 Serenata Virtual", 250),
    11: ("🍾 Botella de Champaña", 400),
    12: ("🍣 Tabla de Sushi Premium", 500),
    13: ("👠 Tacones de Diseñador", 750),
    14: ("⌚ Reloj de Lujo", 1000),
    15: ("📱 iPhone de Última Generación", 1500),
    16: ("🛫 Boleto de Avión (Viaje)", 2000),
    17: ("💎 Anillo de Diamantes", 3000),
    18: ("🚗 Auto Deportivo", 5000),
    19: ("🏰 Mansión Privada", 8000),
    20: ("🛥️ Yate Virtual VIP", 10000)
}

PAQUETES_MONEDAS = {
    "pack_100": {"monedas": 100, "precio": "$2.000 COP / $0.50 USD"},  
    "pack_300": {"monedas": 300, "precio": "$5.000 COP / $1.20 USD"},
    "pack_1000": {"monedas": 1000, "precio": "$15.000 COP / $3.50 USD"}
}

# ==========================================
# 🗄️ MANEJO DE BASE DE DATOS (SQLite)
# ==========================================
def conectar_db():
    conn = sqlite3.connect('dating_premium.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id_telegram INTEGER PRIMARY KEY,
            nombre TEXT,
            edad INTEGER,
            genero TEXT,
            busca TEXT,
            descripcion TEXT,
            ciudad TEXT,
            foto_id TEXT,
            monedas INTEGER DEFAULT 50,
            monedas_regalo INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'normal',
            ultima_recompensa TEXT,
            filtro_ciudad TEXT DEFAULT 'Todos',
            filtro_edad TEXT DEFAULT 'Todos'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS solicitudes_match_link (
            id_solicitud INTEGER PRIMARY KEY AUTOINCREMENT,
            id_recibe INTEGER,
            id_envia INTEGER,
            tipo_sol TEXT DEFAULT 'link',
            estado TEXT DEFAULT 'pendiente',
            UNIQUE(id_recibe, id_envia)
        )
    ''')
    
    cursor.execute('CREATE TABLE IF NOT EXISTS interacciones (de_id INTEGER, para_id INTEGER, tipo TEXT, PRIMARY KEY (de_id, para_id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS chats_activos (user1_id INTEGER, user2_id INTEGER, fecha_inicio TEXT, PRIMARY KEY (user1_id, user2_id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS solicitudes_recarga (id_solicitud INTEGER PRIMARY KEY AUTOINCREMENT, id_telegram INTEGER, monto INTEGER, comprobante_foto_id TEXT, fecha_pago TEXT, estado TEXT DEFAULT "pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS solicitudes_retiro (id INTEGER PRIMARY KEY AUTOINCREMENT, id_telegram INTEGER, cantidad_monedas INTEGER, datos_pago TEXT, estado TEXT DEFAULT "pendiente")')
    cursor.execute('CREATE TABLE IF NOT EXISTS historial_regalos (id_regalo_envio INTEGER PRIMARY KEY AUTOINCREMENT, id_envia INTEGER, id_recibe INTEGER, regalo_id INTEGER, costo_total INTEGER, ganancia_recibida INTEGER, fecha TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS referidos_pendientes (id_invitado INTEGER PRIMARY KEY, id_invitador INTEGER, fecha_click TEXT, estado_registro TEXT DEFAULT "pendiente")')
    
    conn.commit()
    return conn, cursor

conectar_db()[0].close()

# ==========================================
# ⚙️ LÓGICA AUXILIAR Y SEGURIDAD
# ==========================================
def obtener_usuario_completo(chat_id):
    conn, cursor = conectar_db()
    cursor.execute("SELECT estado, monedas, filtro_ciudad, filtro_edad, ciudad FROM usuarios WHERE id_telegram = ?", (chat_id,))
    res = cursor.fetchone()
    conn.close()
    return res if res else ("normal", 0, "Todos", "Todos", "")

def actualizar_estado(chat_id, nuevo_estado):
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET estado = ? WHERE id_telegram = ?", (nuevo_estado, chat_id))
    conn.commit()
    conn.close()

def cobrar_monedas(chat_id, costo):
    conn, cursor = conectar_db()
    cursor.execute("SELECT monedas FROM usuarios WHERE id_telegram = ?", (chat_id,))
    res = cursor.fetchone()
    if res and res[0] >= costo:
        nuevo_saldo = res[0] - costo
        cursor.execute("UPDATE usuarios SET monedas = ? WHERE id_telegram = ?", (nuevo_saldo, chat_id))
        conn.commit()
        conn.close()
        return True, nuevo_saldo
    conn.close()
    return False, 0

def obtener_pareja_chat(chat_id):
    conn, cursor = conectar_db()
    cursor.execute("SELECT user2_id FROM chats_activos WHERE user1_id = ?", (chat_id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("SELECT user1_id FROM chats_activos WHERE user2_id = ?", (chat_id,))
        res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def filtrar_contacto(texto):
    if not texto: return False
    return bool(re.search(r"(io|com|net|org|me|co|t\.me|wa\.me|@[a-zA-Z0-9_]+)", texto, re.IGNORECASE))

# ==========================================
# 📱 INTERFACES Y MENÚS RE-ESTRUCTURADOS
# ==========================================
def menu_principal():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🔍 Buscar Citas"), types.KeyboardButton("👤 Mi Perfil"))
    markup.add(types.KeyboardButton("📥 Solicitudes"), types.KeyboardButton("🔗 Mi Link de Match"))
    markup.add(types.KeyboardButton("🎡 Recompensa & Ruleta"), types.KeyboardButton("🪙 Recargar Monedas"))
    markup.add(types.KeyboardButton("💰 Retirar Fondos"), types.KeyboardButton("🏆 Top Compradores"))
    markup.add(types.KeyboardButton("🔊 Invitar Amigos"))
    return markup

def menu_chat_activo():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🎁 Enviar Regalo"), types.KeyboardButton("👤 Ver Perfil de mi Cita"))
    markup.add(types.KeyboardButton("❌ Terminar Chat"))
    return markup

# ==========================================
# 🚀 FLUJO INICIAL /START
# ==========================================
@bot.message_handler(commands=['start'])
def inicio(message):
    chat_id = message.chat.id
    texto = message.text.split()
    conn, cursor = conectar_db()
    cursor.execute("SELECT estado FROM usuarios WHERE id_telegram = ?", (chat_id,))
    user = cursor.fetchone()
    
    id_objetivo_match = None
    if len(texto) > 1 and texto[1].startswith("match_"):
        try: id_objetivo_match = int(texto[1].split("_")[1])
        except: pass

    if not user:
        ref_txt = f"MATCH_LINK:{id_objetivo_match}" if id_objetivo_match else ""
        cursor.execute("INSERT INTO usuarios (id_telegram, estado, descripcion) VALUES (?, 'reg_nombre', ?)", (chat_id, ref_txt))
        conn.commit()
        bot.send_message(chat_id, "¡Bienvenido a la comunidad Premium de Citas! 👋\nVamos a configurar tu cuenta.\n\n¿Cómo te llamas?")
    else:
        actualizar_estado(chat_id, "normal")
        if id_objetivo_match and id_objetivo_match != chat_id:
            cursor.execute("INSERT OR IGNORE INTO solicitudes_match_link (id_recibe, id_envia, tipo_sol) VALUES (?, ?, 'link')", (id_objetivo_match, chat_id))
            conn.commit()
            bot.send_message(chat_id, "✨ **¡Solicitud por link directo enviada con éxito!**", reply_markup=menu_principal(), parse_mode="Markdown")
            bot.send_message(id_objetivo_match, "🔔 **¡Alguien tocó tu link directo!** Revisa la pestaña '📥 Solicitudes'.")
        else:
            bot.send_message(chat_id, "¡Hola de nuevo! Usa el menú inferior para navegar.", reply_markup=menu_principal())
    conn.close()

# ==========================================
# 📥 FLUJO REGISTRO PASO A PASO
# ==========================================
@bot.message_handler(func=lambda m: obtener_usuario_completo(m.chat.id)[0].startswith('reg_'))
def flujo_registro(message):
    chat_id = message.chat.id
    estado = obtener_usuario_completo(chat_id)[0]
    texto = message.text
    conn, cursor = conectar_db()
    
    if estado == "reg_nombre":
        cursor.execute("UPDATE usuarios SET nombre = ?, estado = 'reg_edad' WHERE id_telegram = ?", (texto, chat_id))
        conn.commit()
        bot.send_message(chat_id, f"Mucho gusto {texto}. ¿Cuántos años tienes? (Envía un número real)")
    elif estado == "reg_edad":
        if not texto.isdigit() or not (18 <= int(texto) <= 99):
            bot.send_message(chat_id, "❌ Edad inválida. Debes ser mayor de 18 años:")
            conn.close()
            return
        cursor.execute("UPDATE usuarios SET edad = ?, estado = 'reg_genero' WHERE id_telegram = ?", (int(texto), chat_id))
        conn.commit()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Hombre 👱‍♂️", callback_data="gen_Hombre"), types.InlineKeyboardButton("Mujer 👩‍🦰", callback_data="gen_Mujer"))
        bot.send_message(chat_id, "Selecciona tu género:", reply_markup=markup)
    elif estado == "reg_desc":
        cursor.execute("UPDATE usuarios SET descripcion = ?, estado = 'reg_ciudad' WHERE id_telegram = ?", (texto, chat_id))
        conn.commit()
        bot.send_message(chat_id, "📍 ¿En qué ciudad te encuentras? (Ejemplo: `Arboletes, Antioquia`):")
    elif estado == "reg_ciudad":
        cursor.execute("UPDATE usuarios SET ciudad = ?, estado = 'reg_foto' WHERE id_telegram = ?", (texto, chat_id))
        conn.commit()
        bot.send_message(chat_id, "📸 Envía la foto nítida que verán las demás personas en tu perfil:")
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('gen_') or call.data.startswith('busca_'))
def procesar_callbacks_registro(call):
    chat_id = call.message.chat.id
    data = call.data
    conn, cursor = conectar_db()
    bot.delete_message(chat_id, call.message.message_id)
    
    if data.startswith('gen_'):
        gen = data.split('_')[1]
        cursor.execute("UPDATE usuarios SET genero = ?, estado = 'busca_busca' WHERE id_telegram = ?", (gen, chat_id))
        conn.commit()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Hombres 👱‍♂️", callback_data="busca_Hombre"), types.InlineKeyboardButton("Mujeres 👩‍🦰", callback_data="busca_Mujer"), types.InlineKeyboardButton("Ambos 🧑‍🤝‍🧑", callback_data="busca_Ambos"))
        bot.send_message(chat_id, "¿A quién te gustaría conocer?", reply_markup=markup)
    elif data.startswith('busca_'):
        busca = data.split('_')[1]
        cursor.execute("UPDATE usuarios SET busca = ?, estado = 'reg_desc' WHERE id_telegram = ?", (busca, chat_id))
        conn.commit()
        bot.send_message(chat_id, "Escribe una descripción breve (tus gustos o qué buscas):")
    conn.close()

@bot.message_handler(content_types=['photo'], func=lambda m: obtener_usuario_completo(m.chat.id)[0] == 'reg_foto')
def recibir_foto_registro(message):
    chat_id = message.chat.id
    foto_id = message.photo[-1].file_id
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET foto_id = ?, estado = 'normal' WHERE id_telegram = ?", (foto_id, chat_id))
    conn.commit()
    conn.close()
    bot.send_message(chat_id, "🎉 **¡Tu perfil comercial ha sido creado!** Te regalamos 50 monedas iniciales.", reply_markup=menu_principal())

# ==========================================
# 🎯 ENGINE DE CITAS PREMIUM CON FILTROS (OPCIÓN 3)
# ==========================================
def obtener_perfil_filtrado(chat_id):
    conn, cursor = conectar_db()
    cursor.execute("SELECT busca, filtro_ciudad, filtro_edad, ciudad FROM usuarios WHERE id_telegram = ?", (chat_id,))
    busca, f_ciudad, f_edad, mi_ciudad = cursor.fetchone()
    
    query = """
        SELECT id_telegram, nombre, edad, descripcion, ciudad, foto_id 
        FROM usuarios 
        WHERE id_telegram != ? AND foto_id IS NOT NULL AND estado != 'reg_nombre' AND estado != 'reg_foto'
        AND id_telegram NOT IN (SELECT para_id FROM interacciones WHERE de_id = ?)
    """
    parametros = [chat_id, chat_id]
    
    if busca != "Ambos":
        query += " AND genero = ?"
        parametros.append(busca)
        
    if f_ciudad == "Activo":
        query += " AND ciudad LIKE ?"
        parametros.append(f"%{mi_ciudad}%")
        
    if f_edad != "Todos":
        if "-" in f_edad:
            min_edad, max_edad = map(int, f_edad.split("-"))
            query += " AND edad >= ? AND edad <= ?"
            parametros.extend([min_edad, max_edad])
        elif f_edad.endswith("+"):
            min_edad = int(f_edad.replace("+", ""))
            query += " AND edad >= ?"
            parametros.append(min_edad)
        
    query += " ORDER BY RANDOM() LIMIT 1"
    cursor.execute(query, parametros)
    res = cursor.fetchone()
    conn.close()
    return res

def lanzar_pantalla_swipe(chat_id):
    _, _, f_ciudad, f_edad, _ = obtener_usuario_completo(chat_id)
    perfil = obtener_perfil_filtrado(chat_id)
    
    if not perfil:
        bot.send_message(chat_id, "✨ No encontramos perfiles nuevos con tus filtros actuales. Prueba ampliando la búsqueda.", reply_markup=menu_principal())
        return
        
    pid, nombre, edad, desc, ciudad, foto = perfil
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        types.InlineKeyboardButton("❌ Pasar", callback_data=f"sw_dislike_{pid}"),
        types.InlineKeyboardButton(f"💚 Like ({COSTO_LIKE} 🪙)", callback_data=f"sw_like_{pid}")
    )
    markup.add(types.InlineKeyboardButton(f"💌 Enviar Super Like (⭐ {COSTO_SUPERLIKE} 🪙)", callback_data=f"sw_super_{pid}"))
    
    status_radar = "🎯 Radar Local Activo" if f_ciudad == "Activo" else "🌐 Radar Global"
    texto_perfil = f"🔥 **{nombre}**, {edad} años\n📍 Ubicación: `{ciudad}`\n📡 Filtros: `{status_radar} / Edad: {f_edad}`\n\n📝 _{desc}_"
    bot.send_photo(chat_id, foto, caption=texto_perfil, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('sw_'))
def procesar_voto_swipe(call):
    chat_id = call.message.chat.id
    partes = call.data.split('_')
    accion = partes[1]
    target_id = int(partes[2])
    bot.delete_message(chat_id, call.message.message_id)
    conn, cursor = conectar_db()
    
    if accion == "dislike":
        cursor.execute("INSERT OR REPLACE INTO interacciones (de_id, para_id, tipo) VALUES (?, ?, 'dislike')", (chat_id, target_id))
        conn.commit()
        conn.close()
        lanzar_pantalla_swipe(chat_id)
        
    elif accion == "like":
        pago, _ = cobrar_monedas(chat_id, COSTO_LIKE)
        if not pago:
            conn.close()
            bot.send_message(chat_id, f"⚠️ No tienes saldo para dar Like. Requiere {COSTO_LIKE} monedas. Recarga en el menú.")
            return
        cursor.execute("INSERT OR REPLACE INTO interacciones (de_id, para_id, tipo) VALUES (?, ?, 'like')", (chat_id, target_id))
        conn.commit()
        
        cursor.execute("SELECT tipo FROM interacciones WHERE de_id = ? AND para_id = ?", (target_id, chat_id))
        inv = cursor.fetchone()
        if inv and inv[0] == 'like':
            fecha = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M")
            cursor.execute("INSERT OR REPLACE INTO chats_activos (user1_id, user2_id, fecha_inicio) VALUES (?, ?, ?)", (chat_id, target_id, fecha))
            cursor.execute("UPDATE usuarios SET estado = 'chateando' WHERE id_telegram IN (?, ?)", (chat_id, target_id))
            conn.commit()
            conn.close()
            bot.send_message(chat_id, "🥳 **¡ES UN MATCH MUTUO!** 🎉\nSe abrió el canal de chat privado.", reply_markup=menu_chat_activo())
            bot.send_message(target_id, "🥳 **¡ALGUIEN TE CORRESPONDIÓ EL LIKE!** 🎉\nVe a hablar con tu nueva cita.", reply_markup=menu_chat_activo())
            return
        conn.close()
        lanzar_pantalla_swipe(chat_id)
        
    elif accion == "super":
        pago, _ = cobrar_monedas(chat_id, COSTO_SUPERLIKE)
        if not pago:
            conn.close()
            bot.send_message(chat_id, f"⚠️ El Super Like directo requiere `{COSTO_SUPERLIKE} monedas`.")
            return
            
        cursor.execute("INSERT OR IGNORE INTO solicitudes_match_link (id_recibe, id_envia, tipo_sol) VALUES (?, ?, 'superlike')", (target_id, chat_id))
        conn.commit()
        conn.close()
        
        bot.send_message(chat_id, "💌 **¡Super Like enviado!** Su perfil fue impactado de inmediato en su bandeja de entrada.")
        try: bot.send_message(target_id, "⭐ **¡ALGUIEN TE HA ENVIADO UN SUPER LIKE!** ⭐\nLe gustas tanto que pagó para saltarse el Match. Revisa '📥 Solicitudes'.")
        except: pass
        lanzar_pantalla_swipe(chat_id)

# ==========================================
# 🎮 INTERRUPTOR CONTROLADOR DE BOTONES TEXTO
# ==========================================
@bot.message_handler(func=lambda m: obtener_usuario_completo(m.chat.id)[0] == 'normal')
def procesar_botones_menu(message):
    chat_id = message.chat.id
    texto = message.text

    if texto == "🔍 Buscar Citas":
        _, _, f_ciudad, f_edad, mi_ciudad = obtener_usuario_completo(chat_id)
        markup_f = types.InlineKeyboardMarkup(row_width=1)
        
        txt_btn_c = "🎯 Desactivar Radar Local" if f_ciudad == "Activo" else f"📍 Filtrar por mi Ciudad ({COSTO_FILTRO_BUSQUEDA} 🪙)"
        markup_f.add(types.InlineKeyboardButton(txt_btn_c, callback_data="toggle_filtro_ciudad"))
        markup_f.add(types.InlineKeyboardButton(f"🎂 Cambiar Rango de Edad (Actual: {f_edad})", callback_data="menu_filtro_edad"))
        markup_f.add(types.InlineKeyboardButton("🚀 Iniciar Escáner de Perfiles", callback_data="start_scanning"))
        
        bot.send_message(chat_id, f"🧭 **PANEL DE BÚSQUEDA AVANZADA**\n\nTu ubicación registrada: `{mi_ciudad}`\nFiltro de localización actual: **{f_ciudad}**\nFiltro de Edad: **{f_edad}**", reply_markup=markup_f, parse_mode="Markdown")

    elif texto == "🎡 Recompensa & Ruleta":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🎁 Reclamar Recompensa Diaria (Gratis)", callback_data="claim_daily"),
                   types.InlineKeyboardButton(f"🎰 Girar la Ruleta de la Suerte ({COSTO_RULETA} 🪙)", callback_data="spin_wheel"))
        bot.send_message(chat_id, "🎡 **MÓDULO DE ENTRETENIMIENTO DIARIO**\n\nGana monedas gratis cada 24 horas o apuesta en el casino para multiplicar tu balance activa y rápidamente:", reply_markup=markup)

    elif texto == "👤 Mi Perfil":
        conn, cursor = conectar_db()
        cursor.execute("SELECT nombre, edad, descripcion, ciudad, monedas, monedas_regalo, foto_id FROM usuarios WHERE id_telegram = ?", (chat_id,))
        n, e, d, c, m, mr, f = cursor.fetchone()
        conn.close()
        
        txt_tarjeta = f"👤 **Tu Tarjeta Comercial:**\n━━━━━━━━━━━━━━━━━━━━\nID: `{chat_id}`\n📛 **Nombre:** {n}\n🎂 **Edad:** {e} años\n📍 **Ciudad:** `{c}`\n📝 **Bio:** _{d}_\n━━━━━━━━━━━━━━━━━━━━\n🪙 **Saldo:** `{m} 🪙` | 💰 **Regalos:** `{mr} 🪙`"
        markup_p = types.InlineKeyboardMarkup()
        markup_p.add(types.InlineKeyboardButton("🔄 Reestablecer Cuenta", callback_data="perf_reiniciar"))
        bot.send_photo(chat_id, f, caption=txt_tarjeta, reply_markup=markup_p, parse_mode="Markdown")

    elif texto == "🔗 Mi Link de Match":
        me = bot.get_me()
        bot.send_message(chat_id, f"🔗 **TU ENLACE DE CONEXIÓN DIRECTO**\n\n`https://t.me/{me.username}?start=match_{chat_id}`", parse_mode="Markdown")

    elif texto == "📥 Solicitudes":
        conn, cursor = conectar_db()
        cursor.execute("""
            SELECT s.id_solicitud, u.id_telegram, u.nombre, u.edad, u.foto_id, s.tipo_sol 
            FROM solicitudes_match_link s JOIN usuarios u ON s.id_envia = u.id_telegram
            WHERE s.id_recibe = ? AND s.estado = 'pendiente' LIMIT 1
        """, (chat_id,))
        sol = cursor.fetchone()
        conn.close()
        
        if not sol:
            bot.send_message(chat_id, "📥 No tienes solicitudes pendientes en este momento.")
            return
            
        idsol, uid_envia, nombre, edad, foto, tipo = sol
        markup_s = types.InlineKeyboardMarkup(row_width=2)
        markup_s.add(types.InlineKeyboardButton("❌ Declinar", callback_data=f"lnk_rech_{idsol}"), types.InlineKeyboardButton("✅ Aceptar Chat", callback_data=f"lnk_aprob_{idsol}"))
        
        letrero = "⭐ ¡TE ENVIARON UN SUPER LIKE DIRECTO!" if tipo == "superlike" else "✨ ¡QUIEREN CONECTAR POR TU ENLACE!"
        bot.send_photo(chat_id, foto, caption=f"📬 **{letrero}**\n\n👤 **Nombre:** {nombre}\n🎂 **Edad:** {edad} años", reply_markup=markup_s, parse_mode="Markdown")

    elif texto == "🪙 Recargar Monedas":
        markup = types.InlineKeyboardMarkup(row_width=1)
        for k, pack in PAQUETES_MONOMEDAS = PAQUETES_MONEDAS.items():
            markup.add(types.InlineKeyboardButton(f"🪙 {pack['monedas']} Monedas ({pack['precio']})", callback_data=f"buy_{k}_{pack['monedas']}"))
        bot.send_message(chat_id, "🪙 **CENTRAL DE COMPRAS**\nTransferir a Nequi: `3001234567`.\nSelecciona el monto reportado:", reply_markup=markup)

    elif texto == "💰 Retirar Fondos":
        conn, cursor = conectar_db()
        cursor.execute("SELECT monedas_regalo FROM usuarios WHERE id_telegram = ?", (chat_id,))
        saldo_r = cursor.fetchone()[0]
        conn.close()
        if saldo_r < MINIMO_RETIRABLE_MONEDAS:
            bot.send_message(chat_id, f"⚠️ Mínimo de retiro: `{MINIMO_RETIRABLE_MONEDAS} monedas`. Tu saldo: `{saldo_r}`.")
        else:
            actualizar_estado(chat_id, "w_retiro")
            bot.send_message(chat_id, "Indica tu Nombre completo, Cédula y número de Nequi/Daviplata:")

    elif texto == "🏆 Top Compradores":
        conn, cursor = conectar_db()
        cursor.execute("SELECT nombre, monedas FROM usuarios ORDER BY monedas DESC LIMIT 5")
        top = cursor.fetchall()
        conn.close()
        resumen = "🏆 **TOP 5 DE CLIENTES VIP:**\n"
        for idx, u in enumerate(top): resumen += f"{idx+1}. **{u[0]}** - `{u[1]}` 🪙\n"
        bot.send_message(chat_id, resumen, parse_mode="Markdown")

    elif texto == "🔊 Invitar Amigos":
        me = bot.get_me()
        bot.send_message(chat_id, f"📢 **SISTEMA DE REFERIDOS**\nGana **50 monedas gratis** compartiendo tu enlace:\n`https://t.me/{me.username}?start={chat_id}`", parse_mode="Markdown")

# ==========================================
# ⚙️ CALLBACK ROUTER GLOBAL
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def router_callbacks_global(call):
    chat_id = call.message.chat.id
    data = call.data
    conn, cursor = conectar_db()
    
    if data == "toggle_filtro_ciudad":
        bot.delete_message(chat_id, call.message.message_id)
        _, _, f_ciudad, _, _ = obtener_usuario_completo(chat_id)
        
        if f_ciudad == "Todos":
            pago, _ = cobrar_monedas(chat_id, COSTO_FILTRO_BUSQUEDA)
            if not pago:
                bot.send_message(chat_id, f"⚠️ El radar por Ciudad requiere `{COSTO_FILTRO_BUSQUEDA} monedas`.")
                conn.close()
                return
            cursor.execute("UPDATE usuarios SET filtro_ciudad = 'Activo' WHERE id_telegram = ?", (chat_id,))
            bot.answer_callback_query(call.id, "🎯 Radar por ciudad encendido!")
        else:
            cursor.execute("UPDATE usuarios SET filtro_ciudad = 'Todos' WHERE id_telegram = ?", (chat_id,))
            bot.answer_callback_query(call.id, "Radar expandido globalmente.")
            
        conn.commit()
        conn.close()
        message = call.message
        message.text = "🔍 Buscar Citas"
        procesar_botones_menu(message)
        
    elif data == "menu_filtro_edad":
        bot.delete_message(chat_id, call.message.message_id)
        conn.close()
        markup_e = types.InlineKeyboardMarkup(row_width=2)
        markup_e.add(
            types.InlineKeyboardButton("18 a 25 años", callback_data="setage_18-25"),
            types.InlineKeyboardButton("26 a 35 años", callback_data="setage_26-35"),
            types.InlineKeyboardButton("Mayores de 36", callback_data="setage_36+"),
            types.InlineKeyboardButton("Todos los rangos", callback_data="setage_Todos")
        )
        bot.send_message(chat_id, f"🎯 **FILTRO DE EDAD PREMIUM**\n\nConfigura el rango preferido (Costo: {COSTO_FILTRO_BUSQUEDA} 🪙):", reply_markup=markup_e)

    elif data.startswith("setage_"):
        bot.delete_message(chat_id, call.message.message_id)
        nuevo_rango = data.split('_')[1]
        
        if nuevo_rango != "Todos":
            pago, _ = cobrar_monedas(chat_id, COSTO_FILTRO_BUSQUEDA)
            if not pago:
                bot.send_message(chat_id, f"⚠️ Cambiar filtros de edad requiere `{COSTO_FILTRO_BUSQUEDA} monedas`.")
                conn.close()
                return
                
        cursor.execute("UPDATE usuarios SET filtro_edad = ? WHERE id_telegram = ?", (nuevo_rango, chat_id))
        conn.commit()
        conn.close()
        
        bot.send_message(chat_id, f"✅ Rango de edad actualizado a: `{nuevo_rango}`")
        message = call.message
        message.text = "🔍 Buscar Citas"
        procesar_botones_menu(message)

    elif data == "start_scanning":
        bot.delete_message(chat_id, call.message.message_id)
        conn.close()
        lanzar_pantalla_swipe(chat_id)
        
    elif data == "claim_daily":
        cursor.execute("SELECT ultima_recompensa, monedas FROM usuarios WHERE id_telegram = ?", (chat_id,))
        ult, actual = cursor.fetchone()
        hoy = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d")
        
        if ult == hoy:
            bot.answer_callback_query(call.id, "❌ Ya reclamaste tu recompensa de hoy. ¡Vuelve mañana!", show_alert=True)
        else:
            premio = random.randint(2, 5)
            cursor.execute("UPDATE usuarios SET monedas = monedas + ?, ultima_recompensa = ? WHERE id_telegram = ?", (premio, hoy, chat_id))
            conn.commit()
            bot.answer_callback_query(call.id, f"🎉 ¡Felicidades! Sumaste {premio} monedas de regalo.")
            bot.edit_message_text(f"🎁 **Recompensa diaria cobrada.**\nRecibiste `{premio} monedas` de regalo. ¡Vuelve mañana por más!", chat_id, call.message.message_id)
        conn.close()
        
    elif data == "spin_wheel":
        pago, _ = cobrar_monedas(chat_id, COSTO_RULETA)
        if not pago:
            bot.answer_callback_query(call.id, f"❌ Requiere {COSTO_RULETA} monedas para apostar.")
            conn.close()
            return
            
        # Modificados los premios de la ruleta en base al costo mayor
        multiplicadores = [0, 0, 25, 50, 125] 
        resultado = random.choice(multiplicadores)
        
        if resultado > 0:
            cursor.execute("UPDATE usuarios SET monedas = monedas + ? WHERE id_telegram = ?", (resultado, chat_id))
            conn.commit()
            msg_res = f"🎰 **¡LA RULETA REVENTÓ GANADORA!** 🎰\n\nInversión: `{COSTO_RULETA} 🪙`.\nResultado: ¡Ganaste **{resultado} monedas** 🪙!"
        else:
            msg_res = f"🎰 **Casilla vacía...** 🎰\n\nInversión: `{COSTO_RULETA} 🪙`.\nResultado: Perdiste tu apuesta. ¡Inténtalo otra vez!"
            
        bot.answer_callback_query(call.id, "🎰 ¡Ruleta girada!")
        bot.edit_message_text(msg_res, chat_id, call.message.message_id)
        conn.close()

    elif data.startswith('gift_'):
        partes = data.split('_')
        regalo_id = int(partes[1])
        target_id = int(partes[2])
        bot.delete_message(chat_id, call.message.message_id)
        
        nombre_regalo, costo = CATALOGO_REGALOS[regalo_id]
        pago, _ = cobrar_monedas(chat_id, costo)
        
        if not pago:
            bot.send_message(chat_id, f"⚠️ No tienes suficientes monedas para enviar {nombre_regalo} ({costo} 🪙).")
            conn.close()
            return
            
        ganancia_receptor = int(costo * 0.8)
        fecha_actual = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M")
        
        cursor.execute("UPDATE usuarios SET monedas_regalo = monedas_regalo + ? WHERE id_telegram = ?", (ganancia_receptor, target_id))
        cursor.execute("INSERT INTO historial_regalos (id_envia, id_recibe, regalo_id, costo_total, ganancia_recibida, fecha) VALUES (?, ?, ?, ?, ?, ?)", 
                       (chat_id, target_id, regalo_id, costo, ganancia_receptor, fecha_actual))
        conn.commit()
        conn.close()
        
        bot.send_message(chat_id, f"🎁 ¡Le has enviado {nombre_regalo} a tu cita con éxito!")
        try: bot.send_message(target_id, f"🎁 **¡Has recibido un regalo virtual!**\n\nTe enviaron: {nombre_regalo}.\nSe han sumado `{ganancia_receptor} monedas` a tu balance acumulado para retiros por Nequi.")
        except: pass

    elif data.startswith("buy_"):
        partes = data.split('_')
        monedas = int(partes[3])
        cursor.execute("UPDATE usuarios SET estado = ? WHERE id_telegram = ?", (f"pago_{monedas}", chat_id))
        conn.commit()
        conn.close()
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, f"Envía la foto del comprobante de transferencia para cargar tus `{monedas} monedas`:")
        
    elif data.startswith("lnk_"):
        partes = data.split('_')
        accion, idsol = partes[1], int(partes[2])
        cursor.execute("SELECT id_envia, estado FROM solicitudes_match_link WHERE id_solicitud = ?", (idsol,))
        sol = cursor.fetchone()
        
        if sol and sol[1] == 'pendiente':
            id_envia = sol[0]
            if accion == "aprob":
                fecha = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M")
                cursor.execute("UPDATE solicitudes_match_link SET estado = 'aceptada' WHERE id_solicitud = ?", (idsol,))
                cursor.execute("INSERT OR REPLACE INTO chats_activos (user1_id, user2_id, fecha_inicio) VALUES (?, ?, ?)", (chat_id, id_envia, fecha))
                cursor.execute("UPDATE usuarios SET estado = 'chateando' WHERE id_telegram IN (?, ?)", (chat_id, id_envia))
                conn.commit()
                bot.send_message(chat_id, "🥳 Chat privado abierto.", reply_markup=menu_chat_activo())
                bot.send_message(id_envia, "🥳 ¡Aceptaron tu solicitud de chat directo!", reply_markup=menu_chat_activo())
            else:
                cursor.execute("UPDATE solicitudes_match_link SET estado = 'rechazada' WHERE id_solicitud = ?", (idsol,))
                conn.commit()
                bot.send_message(chat_id, "Solicitud declinada.", reply_markup=menu_principal())
        conn.close()
        
    elif data == "perf_reiniciar":
        cursor.execute("DELETE FROM usuarios WHERE id_telegram = ?", (chat_id,))
        cursor.execute("DELETE FROM interacciones WHERE de_id = ? OR para_id = ?", (chat_id, chat_id))
        conn.commit()
        conn.close()
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, "🔄 Tu cuenta ha sido borrada por completo. Usa /start para crear un nuevo perfil.")
    else:
        conn.close()

# ==========================================
# 💰 MANEJO DE COMPROBANTES Y RETIROS
# ==========================================
@bot.message_handler(content_types=['photo'], func=lambda m: obtener_usuario_completo(m.chat.id)[0].startswith('pago_'))
def recibir_voucher_pago(message):
    chat_id = message.chat.id
    estado = obtener_usuario_completo(chat_id)[0]
    monedas = int(estado.split('_')[1])
    foto_id = message.photo[-1].file_id
    fecha = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M")
    
    conn, cursor = conectar_db()
    cursor.execute("INSERT INTO solicitudes_recarga (id_telegram, monto, comprobante_foto_id, fecha_pago) VALUES (?, ?, ?, ?)", (chat_id, monedas, foto_id, fecha))
    conn.commit()
    conn.close()
    
    actualizar_estado(chat_id, "normal")
    bot.send_message(chat_id, "✅ Comprobante enviado a auditoría. Se te notificará una vez aprobado por administración.", reply_markup=menu_principal())

@bot.message_handler(func=lambda m: obtener_usuario_completo(m.chat.id)[0] == 'w_retiro')
def procesar_datos_retiro(message):
    chat_id = message.chat.id
    datos = message.text
    conn, cursor = conectar_db()
    cursor.execute("SELECT monedas_regalo FROM usuarios WHERE id_telegram = ?", (chat_id,))
    saldo_r = cursor.fetchone()[0]
    
    if saldo_r >= MINIMO_RETIRABLE_MONEDAS:
        cursor.execute("UPDATE usuarios SET monedas_regalo = 0 WHERE id_telegram = ?", (chat_id,))
        cursor.execute("INSERT INTO solicitudes_retiro (id_telegram, cantidad_monedas, datos_pago) VALUES (?, ?, ?)", (chat_id, saldo_r, datos))
        conn.commit()
        bot.send_message(chat_id, "✅ Solicitud de retiro en proceso de pago.", reply_markup=menu_principal())
        bot.send_message(ID_ADMIN, f"💰 **RETIRO SOLICITADO:** User: `{chat_id}`, Cantidad: `{saldo_r}`, Datos: {datos}")
    conn.close()
    actualizar_estado(chat_id, "normal")

# ==========================================
# 💬 INTERMEDIADOR DE CHAT PRIVADO CON COBRO ALTO
# ==========================================
@bot.message_handler(func=lambda m: obtener_usuario_completo(m.chat.id)[0] == 'chateando')
def intermediador_chat_privado(message):
    chat_id = message.chat.id
    texto = message.text
    receptor = obtener_pareja_chat(chat_id)
    
    if not receptor:
        actualizar_estado(chat_id, "normal")
        bot.send_message(chat_id, "La conversación ha terminado.", reply_markup=menu_principal())
        return

    if texto == "❌ Terminar Chat":
        conn, cursor = conectar_db()
        cursor.execute("DELETE FROM chats_activos WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)", (chat_id, receptor, receptor, chat_id))
        conn.commit()
        conn.close()
        actualizar_estado(chat_id, "normal")
        actualizar_estado(receptor, "normal")
        bot.send_message(chat_id, "Chat terminado con éxito.", reply_markup=menu_principal())
        bot.send_message(receptor, "Tu cita ha cerrado la conversación.", reply_markup=menu_principal())
        return

    elif texto == "👤 Ver Perfil de mi Cita":
        conn, cursor = conectar_db()
        cursor.execute("SELECT nombre, edad, descripcion, ciudad, foto_id FROM usuarios WHERE id_telegram = ?", (receptor,))
        n, e, d, c, f = cursor.fetchone()
        conn.close()
        txt = f"💝 **Estás hablando con:**\n━━━━━━━━━━━━━\n📛 {n}, {e} años\n📍 `{c}`\n📝 _{d}_"
        bot.send_photo(chat_id, f, caption=txt, parse_mode="Markdown")
        return

    elif texto == "🎁 Enviar Regalo":
        markup_regalos = types.InlineKeyboardMarkup(row_width=2)
        for rid, info in CATALOGO_REGALOS.items():
            markup_regalos.add(types.InlineKeyboardButton(f"{info[0]} ({info[1]} 🪙)", callback_data=f"gift_{rid}_{receptor}"))
        bot.send_message(chat_id, "🎁 **TIENDA DE REGALOS**\nElige un detalle para enviar a tu cita. Ella recibirá el 80% de su valor convertible en saldo retirable:", reply_markup=markup_regalos)
        return

    if filtrar_contacto(texto):
        bot.send_message(chat_id, "🚫 No se permite compartir redes sociales o enlaces aquí.")
        return

    # Cobro estructurado de 2 monedas por mensaje enviado (Lógica de producción corregida)
    pago, _ = cobrar_monedas(chat_id, COSTO_MENSAJE)
    if pago:
        try: bot.send_message(receptor, f"💬 **Tu cita:** {texto}")
        except: pass
    else:
        bot.send_message(chat_id, f"🚨 Te quedaste sin monedas para seguir chateando. Cada mensaje cuesta `{COSTO_MENSAJE} 🪙`. ¡Ve a recargar saldo!")

# ==========================================
# 🔄 INICIO DE POLLING PERPETUO
# ==========================================
if __name__ == "__main__":
    print("🚀 Servidor VIP en línea con Precios Altos, Catálogo Completo y Sistema Unificado...")
    bot.infinity_polling(skip_pending=True)