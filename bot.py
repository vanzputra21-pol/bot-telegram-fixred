import os
import logging
import sqlite3
import smtplib
import random
import threading
import asyncio
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "Bot is Alpha and Running!"
def run_flask_server():
    app.run(host='0.0.0.0', port=8080)

# Menjalankan Flask di thread terpisah secara latar belakang (daemon)
threading.Thread(target=run_flask_server, daemon=True).start()
# ===================== KONFIGURASI =====================
BOT_TOKEN = os.getenv('BOT_TOKEN')   # dari @BotFather
ADMIN_ID   = 7678868549                       # isi ID Telegram kamu (angka)
COOLDOWN   = 200                     # detik cooldown antar request
START_TIME = datetime.now()

EMAIL_TARGETS = ["support@whatsapp.com", "smb@support.whatsapp.com"]

# ===================== HARGA VIP =======================
VIP_PACKAGES = {
    "vip_7":  {"label": "7 Hari",  "days": 7,  "price": 5000},
    "vip_30": {"label": "30 Hari", "days": 30, "price": 25000},
    "vip_90": {"label": "90 Hari", "days": 90, "price": 75000},
}

# =================== REKENING ADMIN ====================
# Ganti dengan nomor rekening/dompet kamu
PAYMENT_INFO = {
    "gopay":    {"name": "💚 GoPay",       "number": "081933980672", "holder": "MUHAMMAD FADLHAN PUTRA"},
    "dana":     {"name": "❤️ DANA",        "number": "081933980672", "holder": "MUHAMMAD FADLHAN PUTRA"},
    "shopeepay":{"name": "🟣 ShopeePay",   "number": "081933980672", "holder": "MUHAMMAD FADLHAN PUTRA"},
    "bank":     {"name": "🏦 Transfer Bank","number": "901526186400",   "holder": "MUHAMMAD FADLHAN PUTRA", "bank": "SEABANK"},
}
# =======================================================

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ===================== DATABASE ========================
DB = "fixmerah.db"

def db():
    return sqlite3.connect(DB)

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY,
            username  TEXT,
            name      TEXT,
            is_vip    INTEGER DEFAULT 0,
            vip_until TEXT,
            req_count INTEGER DEFAULT 0,
            last_req  TEXT,
            joined    TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS emails (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            email    TEXT UNIQUE,
            password TEXT,
            used     INTEGER DEFAULT 0,
            active   INTEGER DEFAULT 1
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS logs (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            number  TEXT,
            email   TEXT,
            status  TEXT,
            ts      TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS vip_requests (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name    TEXT,
            status  TEXT DEFAULT 'pending',
            ts      TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS payments (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER,
            package   TEXT,
            method    TEXT,
            proof     TEXT,
            status    TEXT DEFAULT 'pending',
            ts        TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

def register(uid, uname, name):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO users (id, username, name) VALUES (?,?,?)", (uid, uname, name))

def get_user(uid):
    with db() as c:
        return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def get_all_users():
    with db() as c:
        return c.execute("SELECT id FROM users").fetchall()

def check_vip(uid):
    u = get_user(uid)
    if not u or not u[3]:
        return False
    if u[4]:
        if datetime.now() > datetime.strptime(u[4], "%Y-%m-%d %H:%M:%S"):
            with db() as c:
                c.execute("UPDATE users SET is_vip=0 WHERE id=?", (uid,))
            return False
    return True

def set_vip(uid, days):
    until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with db() as c:
        c.execute("UPDATE users SET is_vip=1, vip_until=? WHERE id=?", (until, uid))
def remove_vip(uid):
    with db() as c:
        c.execute(
            "UPDATE users SET is_vip=0, vip_until=NULL WHERE id=?",
            (uid,)
        )


def get_cooldown(uid):
    u = get_user(uid)
    if not u or not u[6]:
        return 0
    diff = (datetime.now() - datetime.strptime(u[6], "%Y-%m-%d %H:%M:%S")).total_seconds()
    return max(0, int(COOLDOWN - diff))

def update_req(uid):
    with db() as c:
        c.execute("UPDATE users SET req_count=req_count+1, last_req=? WHERE id=?",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), uid))

def add_email(email, password):
    try:
        with db() as c:
            c.execute("INSERT INTO emails (email, password) VALUES (?,?)", (email, password))
        return True
    except sqlite3.IntegrityError:
        return False

def get_email():
    with db() as c:
        row = c.execute("SELECT email, password FROM emails WHERE active=1 ORDER BY used ASC LIMIT 1").fetchone()
    return {"email": row[0], "password": row[1]} if row else None

def inc_email(email):
    with db() as c:
        c.execute("UPDATE emails SET used=used+1 WHERE email=?", (email,))

def count_emails():
    with db() as c:
        return c.execute("SELECT COUNT(*) FROM emails WHERE active=1").fetchone()[0]

def count_vip():
    with db() as c:
        return c.execute("SELECT COUNT(*) FROM users WHERE is_vip=1").fetchone()[0]

def get_stats():
    with db() as c:
        tu = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        tv = c.execute("SELECT COUNT(*) FROM users WHERE is_vip=1").fetchone()[0]
        tr = c.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        ts = c.execute("SELECT COUNT(*) FROM logs WHERE status='ok'").fetchone()[0]
        te = c.execute("SELECT COUNT(*) FROM emails WHERE active=1").fetchone()[0]
    return tu, tv, tr, ts, te

def add_log(uid, number, email, status):
    with db() as c:
        c.execute("INSERT INTO logs (user_id, number, email, status) VALUES (?,?,?,?)",
                  (uid, number, email, status))

def get_leaderboard():
    with db() as c:
        return c.execute(
            "SELECT name, username, req_count FROM users ORDER BY req_count DESC LIMIT 10"
        ).fetchall()

def get_history(uid, limit=5):
    with db() as c:
        return c.execute(
            "SELECT number, status, ts FROM logs WHERE user_id=? ORDER BY ts DESC LIMIT ?",
            (uid, limit)
        ).fetchall()

def add_vip_request(uid, name):
    with db() as c:
        existing = c.execute("SELECT id FROM vip_requests WHERE user_id=? AND status='pending'", (uid,)).fetchone()
        if existing:
            return False
        c.execute("INSERT INTO vip_requests (user_id, name) VALUES (?,?)", (uid, name))
    return True

def get_pending_vip_requests():
    with db() as c:
        return c.execute("SELECT id, user_id, name, ts FROM vip_requests WHERE status='pending'").fetchall()

def update_vip_request(req_id, status):
    with db() as c:
        c.execute("UPDATE vip_requests SET status=? WHERE id=?", (status, req_id))

def add_payment(uid, package, method, proof):

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO payments (user_id, package, method, proof) VALUES (?,?,?,?)",
        (uid, package, method, proof)
    )

    conn.commit()

    pay_id = cur.lastrowid

    conn.close()

    return pay_id

def get_pending_payments():
    with db() as c:
        return c.execute(
            "SELECT id, user_id, package, method, proof, ts FROM payments WHERE status='pending' ORDER BY ts DESC"
        ).fetchall()

def update_payment(pay_id, status):
    with db() as c:
        c.execute("UPDATE payments SET status=? WHERE id=?", (status, pay_id))

def get_user_payment(uid):
    with db() as c:
        return c.execute(
            "SELECT id, package, method, status, ts FROM payments WHERE user_id=? ORDER BY ts DESC LIMIT 1", (uid,)
        ).fetchone()

def runtime():
    d = datetime.now() - START_TIME
    h, r = divmod(int(d.total_seconds()), 3600)
    m, s = divmod(r, 60)
    return f"{h//24}d {h%24}h {m}m {s}s"

# ===================== EMAIL ===========================
TEMPLATES = [
"""Dear WhatsApp Support,

I am writing to appeal the login restriction on my WhatsApp account.
Phone Number: {number}
Error: "Login not available at this time"
Device: Android

I have not violated any WhatsApp Terms of Service. Please review and restore my account access.

Thank you,
WhatsApp User""",
"""Hello WhatsApp Support Team,

My WhatsApp account ({number}) is showing "Login not available at this time" error.
I kindly request you to lift this restriction as I have not done anything against your policies.

Phone: {number} | Platform: Android | Issue: Login restriction

Please help me regain access. Best regards""",
"""To WhatsApp Support,

I am experiencing a login issue with my WhatsApp number {number}.
The app shows: "Login tidak tersedia untuk saat ini".

I sincerely request your team to review and restore access. I always followed WhatsApp's Terms of Service.

Phone Number: {number} — Thank you for your assistance."""
]

def send_email(number, sender):
    try:
        msg = MIMEMultipart()
        msg["From"]    = sender["email"]
        msg["To"]      = random.choice(EMAIL_TARGETS)
        msg["Subject"] = f"Account Appeal - Login Restriction - {number}"
        msg.attach(MIMEText(random.choice(TEMPLATES).format(number=number), "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(sender["email"], sender["password"])
            s.send_message(msg)
        return True
    except Exception as e:
        log.error(f"Email error: {e}")
        return False

# ===================== PROGRESS BAR ====================
def progress_bar(step, total=5):
    filled = int((step / total) * 10)
    bar = "█" * filled + "░" * (10 - filled)
    pct = int((step / total) * 100)
    return f"[{bar}] {pct}%"

# ===================== KEYBOARDS =======================
def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 CEK ID KAMU",   callback_data="cek_id"),
         InlineKeyboardButton("📊 STATISTIK",     callback_data="statistik")],
        [InlineKeyboardButton("🔴 FIX MERAH",     callback_data="fix_merah")],
        [InlineKeyboardButton("🏆 LEADERBOARD",   callback_data="leaderboard"),
         InlineKeyboardButton("📋 RIWAYAT",       callback_data="riwayat")],
        [InlineKeyboardButton("💰 BELI VIP",      callback_data="beli_vip"),
         InlineKeyboardButton("👑 STATUS VIP",    callback_data="daftar_vip")],
        [InlineKeyboardButton("ℹ️ INFORMASI",     callback_data="information")],
    ])

def kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 KEMBALI", callback_data="back")]])

def kb_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Tambah VIP",      callback_data="a_vip"),
          InlineKeyboardButton("❌ Hapus VIP", callback_data="remove_vip")],
        [InlineKeyboardButton("📧 Tambah Email",    callback_data="a_email"),
          InlineKeyboardButton("📨 Broadcast",       callback_data="a_broadcast")],
        [InlineKeyboardButton("📋 Request VIP",     callback_data="a_vip_requests"),
          InlineKeyboardButton("💰 Bukti Bayar",     callback_data="a_payments")],
        [InlineKeyboardButton("📊 Statistik",       callback_data="a_stats"),
         InlineKeyboardButton("🔙 Kembali",         callback_data="back")],
    ])

# ===================== TEXT HELPERS ====================
def txt_home(uid):
    return (
        f"╔══════════════════════╗\n"
        f"║  🔴 *BOT FIX MERAH WA* 🔴  ║\n"
        f"╚══════════════════════╝\n\n"
        f"➕ DAPATKAN ID TELEGRAM ANDA\n"
        f"➕ LIHAT STATISTIK PENGGUNAAN\n"
        f"➕ KIRIM BANDING KE SUPPORT WHATSAPP\n"
        f"➕ SISTEM VIP DENGAN MASA AKTIF\n"
        f"➕ PROSES CEPAT DAN AMAN\n"
        f"➕ ROTASI EMAIL OTOMATIS\n\n"
        f"➕ *VERSION:* 2.0 VIP\n"
        f"➕ *MODE:* CHAT PRIBADI\n"
        f"➕ *EMAIL TERDAFTAR:* {count_emails()}\n"
        f"➕ *VIP AKTIF:* {count_vip()}\n"
        f"➕ *RUNTIME:* {runtime()}\n"
        f"➕ *STATUS:* {'👑 VIP' if check_vip(uid) else '👤 Member'}"
    )

# ===================== HANDLERS ========================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    register(u.id, u.username or "", u.full_name or "")
    await update.message.reply_text(txt_home(u.id), parse_mode=None, reply_markup=kb_main())

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    log.info(f"/admin from {u.id} (ADMIN_ID={ADMIN_ID})")
    if u.id != ADMIN_ID:
        await update.message.reply_text(
            f"❌ Akses ditolak!\n\n🆔 ID kamu: `{u.id}`\n\nPastikan ADMIN\\_ID di bot.py sudah benar.",
            parse_mode=None
        )
        return
    await update.message.reply_text("⚙️ *ADMIN PANEL*", parse_mode=None, reply_markup=kb_admin())

async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.message.reply_text(f"🆔 ID Telegram kamu: `{u.id}`", parse_mode=None)

# ---- CALLBACK BUTTONS ----
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    u = q.from_user
    d = q.data

    # ---- BACK ----
    if d == "back":
        await q.edit_message_text(txt_home(u.id), parse_mode=None, reply_markup=kb_main())

    # ---- CEK ID ----
    elif d == "cek_id":
        user = get_user(u.id)
        vip_until = user[4] if user and user[4] else "-"
        status = f"👑 VIP (sampai {vip_until})" if check_vip(u.id) else "👤 Member"
        await q.edit_message_text(
            f"🔍 *CEK ID KAMU*\n\n"
            f"👤 Nama: {u.full_name}\n"
            f"🆔 Telegram ID: `{u.id}`\n"
            f"📛 Username: @{u.username or '-'}\n"
            f"💎 Status: {status}\n"
            f"📨 Total Request: {user[5] if user else 0}\n"
            f"📅 Join: {user[7] if user else '-'}",
            parse_mode=None, reply_markup=kb_back()
        )

    # ---- STATISTIK ----
    elif d == "statistik":
        tu, tv, tr, ts, te = get_stats()
        await q.edit_message_text(
            f"📊 *STATISTIK BOT*\n\n"
            f"👥 Total User: {tu}\n"
            f"👑 User VIP: {tv}\n"
            f"📨 Total Request: {tr}\n"
            f"✅ Sukses: {ts}\n"
            f"❌ Gagal: {tr - ts}\n"
            f"📧 Email Aktif: {te}\n"
            f"⏱ Runtime: {runtime()}",
            parse_mode=None, reply_markup=kb_back()
        )

    # ---- LEADERBOARD ----
    elif d == "leaderboard":

        rows = get_leaderboard()

        medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

        text = "🏆 TOP 10 PENGGUNA TERBANYAK\n\n"

        if rows:

            for i, (name, uname, count) in enumerate(rows):

                display = uname if uname else name or "User"

                # Hindari error markdown
                display = str(display).replace("_", "\\_").replace("*", "")

                text += f"{medals[i]} {display} — {count} request\n"

        else:
            text += "Belum ada data"

        await q.edit_message_text(
            text,
            parse_mode=None,
            reply_markup=kb_back()
        )
        
    # ---- RIWAYAT ----
    elif d == "riwayat":
        rows = get_history(u.id)
        lines = ["📋 *RIWAYAT REQUEST KAMU*\n"]
        if rows:
            for number, status, ts in rows:
                icon = "✅" if status == "ok" else "❌"
                lines.append(f"{icon} `{number}`\n   📅 {ts}")
        else:
            lines.append("_Belum ada riwayat request._")
        await q.edit_message_text(
            "\n".join(lines), parse_mode=None, reply_markup=kb_back()
        )

    # ---- DAFTAR VIP ----
    elif d == "daftar_vip":
        if check_vip(u.id):
            user = get_user(u.id)
            await q.edit_message_text(
                f"👑 *KAMU SUDAH VIP!*\n\n"
                f"📅 Aktif sampai: `{user[4]}`\n\n"
                f"Nikmati fitur Fix Merah tanpa batas\\!",
                parse_mode=None, reply_markup=kb_back()
            )
            return
        ok = add_vip_request(u.id, u.full_name or "User")
        if ok:
            await q.edit_message_text(
                f"📩 *PERMINTAAN VIP TERKIRIM!*\n\n"
                f"✅ Request kamu sudah dikirim ke admin\\.\n"
                f"⏳ Tunggu konfirmasi dari admin\\.\n\n"
                f"🆔 ID kamu: `{u.id}`\n"
                f"📌 Tunjukkan ID ini ke admin jika perlu\\.",
                parse_mode=None, reply_markup=kb_back()
            )
            # Notifikasi admin
            try:
                await ctx.bot.send_message(
                    ADMIN_ID,
                    f"🔔 *REQUEST VIP BARU!*\n\n"
                    f"👤 Nama: {u.full_name}\n"
                    f"🆔 ID: `{u.id}`\n"
                    f"📛 Username: @{u.username or '-'}\n\n"
                    f"Buka /admin → Request VIP untuk approve/reject.",
                    parse_mode=None
                )
            except Exception:
                pass
        else:
            await q.edit_message_text(
                "⏳ *Kamu sudah punya request VIP yang pending!*\n\nTunggu admin untuk memproses.",
                parse_mode=None, reply_markup=kb_back()
            )

    # ---- BELI VIP ----
    elif d == "beli_vip":
        if check_vip(u.id):
            user = get_user(u.id)
            await q.edit_message_text(
                f"👑 *STATUS VIP KAMU*\n\n"
                f"✅ Kamu sudah VIP aktif!\n"
                f"📅 Aktif hingga: `{user[4]}`\n\n"
                f"Nikmati semua fitur premium bot ini.",
                parse_mode=None, reply_markup=kb_back()
            )
            return
        # Tampilkan paket VIP
        keyboard = []
        for key, pkg in VIP_PACKAGES.items():
            price_fmt = f"Rp {pkg['price']:,}".replace(",",".")
            keyboard.append([InlineKeyboardButton(
                f"⭐ {pkg['label']} — {price_fmt}",
                callback_data=f"pkg_{key}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 KEMBALI", callback_data="back")])
        await q.edit_message_text(
            "💰 *BELI AKSES VIP*\n\n"
            "Pilih paket VIP yang kamu inginkan:\n\n"
            "⭐ *7 Hari* — Cocok untuk coba\n"
            "⭐ *30 Hari* — Paling populer\n"
            "⭐ *90 Hari* — Paling hemat\n\n"
            "✅ Proses cepat setelah bukti bayar dikonfirmasi admin.",
            parse_mode=None,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ---- PILIH PAKET ----
    elif d.startswith("pkg_"):
        pkg_key = d[4:]
        if pkg_key not in VIP_PACKAGES:
            await q.answer("Paket tidak valid!", show_alert=True)
            return
        pkg = VIP_PACKAGES[pkg_key]
        price_fmt = f"Rp {pkg['price']:,}".replace(",",".")
        ctx.user_data["pkg"] = pkg_key
        # Tampilkan pilihan metode bayar
        keyboard = [
            [InlineKeyboardButton("💚 GoPay",        callback_data="pay_gopay"),
             InlineKeyboardButton("❤️ DANA",         callback_data="pay_dana")],
            [InlineKeyboardButton("🟣 ShopeePay",    callback_data="pay_shopeepay"),
             InlineKeyboardButton("🏦 Transfer Bank",callback_data="pay_bank")],
            [InlineKeyboardButton("🔙 KEMBALI",      callback_data="beli_vip")],
        ]
        await q.edit_message_text(
            f"📦 *PAKET DIPILIH:* {pkg['label']}\n"
            f"💵 *Harga:* {price_fmt}\n\n"
            f"Pilih metode pembayaran:",
            parse_mode=None,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ---- PILIH METODE BAYAR ----
    elif d.startswith("pay_"):
        method = d[4:]
        if method not in PAYMENT_INFO:
            await q.answer("Metode tidak valid!", show_alert=True)
            return
        pkg_key = ctx.user_data.get("pkg")
        if not pkg_key:
            await q.edit_message_text("❌ Sesi habis. Silakan mulai lagi.", reply_markup=kb_back())
            return
        pkg  = VIP_PACKAGES[pkg_key]
        info = PAYMENT_INFO[method]
        price_fmt = f"Rp {pkg['price']:,}".replace(",",".")
        ctx.user_data["pay_method"] = method

        bank_line = f"\n🏦 Bank: *{info.get('bank','')}*" if method == "bank" else ""
        await q.edit_message_text(
            f"💳 *DETAIL PEMBAYARAN*\n\n"
            f"📦 Paket: *{pkg['label']}*\n"
            f"💵 Total: *{price_fmt}*\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{info['name']}{bank_line}\n"
            f"📱 Nomor: `{info['number']}`\n"
            f"👤 A/N: *{info['holder']}*\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"📸 *Cara Konfirmasi:*\n"
            f"Setelah transfer, kirim ke bot ini:\n"
            f"• Foto/screenshot bukti bayar, *ATAU*\n"
            f"• Nomor transaksi pembayaran\n\n"
            f"⏳ Admin akan konfirmasi dalam 1-10 menit.",
            parse_mode=None,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Sudah Bayar, Kirim Bukti", callback_data="confirm_pay"),
                ],[InlineKeyboardButton("🔙 KEMBALI", callback_data=f"pkg_{pkg_key}")]
            ])
        )

    # ---- KONFIRMASI BAYAR ----
    elif d == "confirm_pay":
        pkg_key = ctx.user_data.get("pkg")
        method  = ctx.user_data.get("pay_method")
        if not pkg_key or not method:
            await q.edit_message_text("❌ Sesi habis. Silakan mulai lagi.", reply_markup=kb_back())
            return
        ctx.user_data["state"] = "wait_proof"
        pkg = VIP_PACKAGES[pkg_key]
        price_fmt = f"Rp {pkg['price']:,}".replace(",",".")
        await q.edit_message_text(
            f"📤 *KIRIM BUKTI PEMBAYARAN*\n\n"
            f"📦 Paket: *{pkg['label']}* ({price_fmt})\n\n"
            f"Silakan kirim:\n"
            f"📸 *Foto* screenshot bukti transfer, *ATAU*\n"
            f"🔢 *Nomor transaksi* (contoh: `GPN2024XXXXXXXX`)\n\n"
            f"⚠️ Pastikan bukti terlihat jelas ya!",
            parse_mode=None,
            reply_markup=kb_back()
        )

    # ---- STATUS VIP (tombol lama) ----
    elif d == "daftar_vip":
        if check_vip(u.id):
            user = get_user(u.id)
            await q.edit_message_text(
                f"👑 *STATUS VIP KAMU*\n\n"
                f"✅ Aktif hingga: `{user[4]}`\n\n"
                f"Nikmati semua fitur premium!",
                parse_mode=None, reply_markup=kb_back()
            )
        else:
            pay = get_user_payment(u.id)
            if pay and pay[3] == "pending":
                pkg = VIP_PACKAGES.get(pay[1], {})
                await q.edit_message_text(
                    f"⏳ *PEMBAYARAN SEDANG DIVERIFIKASI*\n\n"
                    f"📦 Paket: {pkg.get('label',pay[1])}\n"
                    f"💳 Metode: {pay[2]}\n"
                    f"📅 Dikirim: {pay[4]}\n\n"
                    f"Sabar ya, admin sedang memproses!",
                    parse_mode=None, reply_markup=kb_back()
                )
            else:
                await q.edit_message_text(
                    "👤 *STATUS: Member Biasa*\n\n"
                    "Kamu belum memiliki akses VIP.\n\n"
                    "Klik *BELI VIP* di menu utama untuk upgrade!",
                    parse_mode=None, reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💰 BELI VIP", callback_data="beli_vip")],
                        [InlineKeyboardButton("🔙 KEMBALI",  callback_data="back")],
                    ])
                )

    # ---- ADMIN: LIHAT BUKTI BAYAR ----
    elif d == "a_payments":
        if u.id != ADMIN_ID:
            await q.answer("❌ Bukan admin!", show_alert=True); return
        pays = get_pending_payments()
        if not pays:
            await q.edit_message_text(
                "💰 *BUKTI PEMBAYARAN*\n\n_Tidak ada pembayaran pending._",
                parse_mode=None, reply_markup=kb_admin()
            )
            return
        lines = ["💰 *PEMBAYARAN PENDING*\n"]
        for pay_id, uid, package, method, proof, ts in pays:
            pkg = VIP_PACKAGES.get(package, {})
            lines.append(
                f"🆔 Pay ID: `{pay_id}` | User: `{uid}`\n"
                f"📦 {pkg.get('label', package)} via {method}\n"
                f"🧾 Bukti: `{proof[:40] if proof else '-'}`\n"
                f"📅 {ts}\n"
            )
        lines.append("\n_Gunakan perintah:_")
        lines.append("`/paybayar PAY_ID HARI` — approve & aktifkan VIP")
        lines.append("`/paytolak PAY_ID` — tolak pembayaran")
        await q.edit_message_text(
            "\n".join(lines), parse_mode=None, reply_markup=kb_admin()
        )

    # ---- FIX MERAH ----
    elif d == "fix_merah":
        if not check_vip(u.id):
            await q.edit_message_text(
                "🔒 *AKSES DITOLAK*\n\n"
                "Fitur Fix Merah hanya untuk member *VIP*\\!\n\n"
                "Klik tombol *DAFTAR VIP* di menu utama untuk request akses\\.",
                parse_mode="", reply_markup=kb_back()
            )
            return
        cd = get_cooldown(u.id)
        if cd > 0:
            m, s = divmod(cd, 60)
            await q.edit_message_text(
                f"⏳ *COOLDOWN AKTIF*\n\n"
                f"Tunggu *{m}m {s}s* lagi sebelum request baru\\.\n\n"
                f"{progress_bar(COOLDOWN - cd, COOLDOWN)}",
                parse_mode=None, reply_markup=kb_back()
            )
            return
        ctx.user_data["state"] = "wait_number"
        await q.edit_message_text(
            "🔴 *FIX MERAH*\n\n"
            "Kirim nomor WhatsApp yang ingin di-fix:\n\n"
            "📱 Format: `628xxxxxxxxxx`\n"
            "📱 Contoh: `6281234567890`\n\n"
            "⚡ Proses otomatis, hasil 1-24 jam.",
            parse_mode=None, reply_markup=kb_back()
        )

    # ---- INFORMASI ----
    elif d == "information":
        await q.edit_message_text(
            "❓ *BANTUAN & INFORMASI*\n\n"
            "🤖 *Tentang Bot:*\n"
            "Bot ini membantu mengirim banding ke support WhatsApp untuk masalah 'Login tidak tersedia'.\n\n"
            "🎯 *Cara Menggunakan:*\n"
            "1. Klik DAFTAR VIP dan tunggu konfirmasi admin\n"
            "2. Setelah VIP aktif, klik FIX MERAH\n"
            "3. Kirim nomor WhatsApp yang bermasalah\n"
            "4. Tunggu hasil 1-24 jam\n\n"
            "⚡ *Fitur Tersedia:*\n"
            "• 🔴 Fix Merah — kirim banding otomatis\n"
            "• 🏆 Leaderboard — top pengguna\n"
            "• 📋 Riwayat — history request kamu\n"
            "• 👑 Daftar VIP — request akses VIP\n"
            "• 📊 Statistik — data penggunaan bot\n\n"
            f"🔧 *Info:*\n"
            f"• Cooldown: `{COOLDOWN}s`\n"
            f"• Email: `{count_emails()}` aktif\n"
            f"• VIP: `{count_vip()}` user\n\n"
            "💬 Hubungi owner jika ada masalah.",
            parse_mode=None, reply_markup=kb_back()
        )

    # ========================
    # ---- ADMIN BUTTONS -----
    # ========================
    elif d == "remove_vip":

        if u.id != ADMIN_ID:
            await q.answer("❌ Bukan admin!", show_alert=True)
            return

        ctx.user_data["admin"] = "wait_remove_vip"

        await q.edit_message_text(
            "❌ *HAPUS VIP*\n\n"
            "Kirim ID Telegram user yang ingin dihapus VIP-nya.\n\n"
            "Contoh:\n"
            "`123456789`",
            parse_mode=None,
            reply_markup=kb_back()
        )
    
    elif d == "a_vip":
        if u.id != ADMIN_ID:
            await q.answer("❌ Bukan admin!", show_alert=True); return
        ctx.user_data["admin"] = "wait_vip_id"
        await q.edit_message_text(
            "👑 *TAMBAH VIP*\n\nKirim Telegram ID user yang ingin di-VIP:",
            parse_mode=None, reply_markup=kb_back()
        )

    elif d == "a_email":
        if u.id != ADMIN_ID:
            await q.answer("❌ Bukan admin!", show_alert=True); return
        ctx.user_data["admin"] = "wait_email"
        await q.edit_message_text(
            "📧 *TAMBAH EMAIL*\n\n"
            "Format: `email@gmail.com:app_password`\n\n"
            "Contoh:\n`myemail@gmail.com:abcdabcdabcdabcd`",
            parse_mode=None, reply_markup=kb_back()
        )

    elif d == "a_broadcast":
        if u.id != ADMIN_ID:
            await q.answer("❌ Bukan admin!", show_alert=True); return
        ctx.user_data["admin"] = "wait_broadcast"
        await q.edit_message_text(
            "📢 *BROADCAST*\n\n"
            "Kirim pesan yang ingin di-broadcast ke semua user:\n\n"
            "_(Emoji dan formatting Markdown didukung)_",
            parse_mode=None, reply_markup=kb_back()
        )

    elif d == "a_vip_requests":
        if u.id != ADMIN_ID:
            await q.answer("❌ Bukan admin!", show_alert=True); return
        reqs = get_pending_vip_requests()
        if not reqs:
            await q.edit_message_text(
                "📋 *REQUEST VIP*\n\n_Tidak ada request VIP yang pending._",
                parse_mode=None, reply_markup=kb_admin()
            )
            return
        lines = ["📋 *REQUEST VIP PENDING*\n"]
        for req_id, uid, name, ts in reqs:
            lines.append(f"🆔 ID: `{uid}` | 👤 {name}\n📅 {ts}\n")
        lines.append("\n_Gunakan perintah berikut untuk approve/reject:_")
        lines.append("`/approve ID_USER HARI`\nContoh: `/approve 123456789 30`")
        lines.append("`/reject ID_USER`\nContoh: `/reject 123456789`")
        await q.edit_message_text(
            "\n".join(lines), parse_mode=None, reply_markup=kb_admin()
        )

    elif d == "a_stats":
        if u.id != ADMIN_ID:
            await q.answer("❌ Bukan admin!", show_alert=True); return
        tu, tv, tr, ts, te = get_stats()
        await q.edit_message_text(
            f"📊 *STATISTIK ADMIN*\n\n"
            f"👥 Total User: {tu}\n"
            f"👑 VIP Aktif: {tv}\n"
            f"📨 Total Request: {tr}\n"
            f"✅ Sukses: {ts}\n"
            f"❌ Gagal: {tr - ts}\n"
            f"📧 Email Aktif: {te}\n"
            f"⏱ Runtime: {runtime()}",
            parse_mode=None, reply_markup=kb_admin()
        )

# ---- APPROVE / REJECT VIP ----
async def cmd_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u.id != ADMIN_ID:
        return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Format: `/approve ID_USER HARI`\nContoh: `/approve 123456789 30`", parse_mode=None)
        return
    try:
        tid  = int(args[0])
        days = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Format salah! ID dan hari harus angka.")
        return

    set_vip(tid, days)
    with db() as c:
        c.execute("UPDATE vip_requests SET status='approved' WHERE user_id=? AND status='pending'", (tid,))

    await update.message.reply_text(
        f"✅ VIP berhasil diberikan!\n🆔 `{tid}` | 📅 {days} hari",
        parse_mode=None, reply_markup=kb_admin()
    )
    try:
        until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        await ctx.bot.send_message(
            tid,
            f"🎉 *SELAMAT! Akses VIP kamu telah diaktifkan!*\n\n"
            f"👑 Status: VIP\n"
            f"📅 Aktif hingga: `{until}`\n\n"
            f"Kamu sekarang bisa menggunakan fitur *Fix Merah*\\!\n"
            f"Ketik /start untuk memulai\\.",
            parse_mode=None
        )
    except Exception:
        pass

async def cmd_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u.id != ADMIN_ID:
        return
    args = ctx.args
    if len(args) < 1:
        await update.message.reply_text("Format: `/reject ID_USER`", parse_mode=None)
        return
    try:
        tid = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID harus angka.")
        return

    with db() as c:
        c.execute("UPDATE vip_requests SET status='rejected' WHERE user_id=? AND status='pending'", (tid,))

    await update.message.reply_text(f"❌ Request VIP dari `{tid}` ditolak.", parse_mode=None)
    try:
        await ctx.bot.send_message(
            tid,
            "❌ *Maaf, request VIP kamu ditolak.*\n\nHubungi admin jika ada pertanyaan.",
            parse_mode=None
        )
    except Exception:
        pass

# ---- PESAN TEKS ----
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u   = update.effective_user
    txt = update.message.text.strip()

    # ---- ADMIN STATE ----
    if u.id == ADMIN_ID:
        state = ctx.user_data.get("admin")

        if state == "wait_vip_id":
            if not txt.isdigit():
                await update.message.reply_text("❌ ID harus angka! Contoh: `123456789`", parse_mode=None)
                return
            ctx.user_data["vip_target"] = int(txt)
            ctx.user_data["admin"] = "wait_vip_days"
            await update.message.reply_text(
                f"✅ Target: `{txt}`\n\nKirim jumlah hari VIP (contoh: `30`):",
                parse_mode=None
            )
            return

        if state == "wait_vip_days":
            if not txt.isdigit():
                await update.message.reply_text("❌ Hari harus angka! Contoh: `30`", parse_mode=None)
                return
            tid  = ctx.user_data.get("vip_target")
            days = int(txt)
            set_vip(tid, days)
            ctx.user_data["admin"] = None
            await update.message.reply_text(
                f"✅ *VIP berhasil ditambahkan!*\n🆔 `{tid}` | 📅 {days} hari",
                parse_mode=None, reply_markup=kb_admin()
            )
            try:
                until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                await ctx.bot.send_message(
                    tid,
                    f"🎉 *SELAMAT! Akses VIP kamu aktif!*\n\n"
                    f"📅 Aktif hingga: `{until}`\n\nKetik /start untuk mulai\\.",
                    parse_mode=None
                )
            except Exception:
                pass
            return

        if state == "wait_remove_vip":

            if not txt.isdigit():

                await update.message.reply_text(
                    "❌ ID harus angka!",
                    parse_mode=None
                )
                return

            target_id = int(txt)

            remove_vip(target_id)

            ctx.user_data["admin"] = None

            await update.message.reply_text(
                f"✅ VIP user `{target_id}` berhasil dihapus.",
                parse_mode=None,
                reply_markup=kb_admin()
            )

            try:
                await ctx.bot.send_message(
                    target_id,
                    "❌ *Akses VIP kamu telah dicabut oleh admin.*",
                    parse_mode=None
                )
            except Exception:
                pass

            return

        if state == "wait_email":
            if ":" not in txt:
                await update.message.reply_text("❌ Format: `email@gmail.com:password`", parse_mode=None)
                return
            email, pwd = txt.split(":", 1)
            ok = add_email(email.strip(), pwd.strip())
            ctx.user_data["admin"] = None
            msg = f"✅ Email `{email.strip()}` ditambahkan!" if ok else "❌ Email sudah terdaftar!"
            await update.message.reply_text(msg, parse_mode=None, reply_markup=kb_admin())
            return

        if state == "wait_broadcast":
            users = get_all_users()
            ctx.user_data["admin"] = None
            sent, fail = 0, 0
            prog_msg = await update.message.reply_text(
                f"📢 *Broadcasting...*\n\n{progress_bar(0, len(users))}\n0/{len(users)} user",
                parse_mode=None
            )
            for i, (uid,) in enumerate(users, 1):
                try:
                    await ctx.bot.send_message(uid,
                        f"📢 *PENGUMUMAN*\n\n{txt}\n\n_— Admin Bot Fix Merah_",
                        parse_mode=None
                    )
                    sent += 1
                except Exception:
                    fail += 1
                if i % 5 == 0 or i == len(users):
                    try:
                        await prog_msg.edit_text(
                            f"📢 *Broadcasting...*\n\n{progress_bar(i, len(users))}\n{i}/{len(users)} user",
                            parse_mode=None
                        )
                    except Exception:
                        pass
                await asyncio.sleep(0.05)

            await prog_msg.edit_text(
                f"✅ *Broadcast Selesai!*\n\n"
                f"📨 Terkirim: {sent}\n"
                f"❌ Gagal: {fail}\n"
                f"👥 Total: {len(users)}",
                parse_mode=None, reply_markup=kb_admin()
            )
            return

    # ---- USER: tunggu bukti bayar (teks/nomor transaksi) ----
    if ctx.user_data.get("state") == "wait_proof":
        pkg_key = ctx.user_data.get("pkg")
        method  = ctx.user_data.get("pay_method")
        ctx.user_data["state"] = None
        pkg = VIP_PACKAGES.get(pkg_key, {})
        price_fmt = f"Rp {pkg.get('price',0):,}".replace(",",".")
        pay_id = add_payment(u.id, pkg_key, method, txt)
        await update.message.reply_text(
            f"✅ *BUKTI PEMBAYARAN DITERIMA!*\n\n"
            f"📦 Paket: *{pkg.get('label','')}* ({price_fmt})\n"
            f"💳 Metode: *{method}*\n"
            f"🔢 No. Transaksi/Bukti: `{txt[:60]}`\n\n"
            f"⏳ Admin akan memverifikasi dalam 1-10 menit.\n"
            f"Kamu akan dapat notifikasi setelah VIP aktif!",
            parse_mode=None, reply_markup=kb_main()
        )
        # Notif ke admin
        try:
            await ctx.bot.send_message(
                ADMIN_ID,
                f"💰 *BUKTI BAYAR BARU!*\n\n"
                f"👤 {u.full_name} (@{u.username or '-'})\n"
                f"🆔 User ID: `{u.id}`\n"
                f"📦 Paket: {pkg.get('label',pkg_key)}\n"
                f"💵 Harga: {price_fmt}\n"
                f"💳 Metode: {method}\n"
                f"🧾 Bukti: `{txt[:100]}`\n\n"
                f"Gunakan `/paybayar {pay_id} {pkg.get('days',30)}` untuk approve\n"
                f"Atau `/paytolak {pay_id}` untuk tolak",
                parse_mode=None
            )
        except Exception:
            pass
        return

    # ---- USER: tunggu bukti bayar (FOTO) ----
    # Handled in on_photo below

    # ---- USER: tunggu nomor WA ----
    if ctx.user_data.get("state") == "wait_number":
        number = txt.replace("+","").replace("-","").replace(" ","")
        if not number.isdigit() or len(number) < 10:
            await update.message.reply_text(
                "❌ Nomor tidak valid!\n\nFormat: `628xxxxxxxxxx`\nContoh: `6281234567890`",
                parse_mode=None
            )
            return

        ctx.user_data["state"] = None

        # Animasi progress
        steps = [
            "🔍 Memeriksa nomor...",
            "📧 Menyiapkan email...",
            "✉️ Mengirim banding...",
            "📡 Menghubungi server WhatsApp...",
            "✅ Menyelesaikan proses..."
        ]
        msg = await update.message.reply_text(
            f"⚡ *MEMPROSES REQUEST*\n\n"
            f"📱 Nomor: `{number}`\n\n"
            f"{progress_bar(0)}\n{steps[0]}",
            parse_mode=None
        )

        async def animate():
            for i, step in enumerate(steps[1:], 1):
                await asyncio.sleep(1.2)
                try:
                    await msg.edit_text(
                        f"⚡ *MEMPROSES REQUEST*\n\n"
                        f"📱 Nomor: `{number}`\n\n"
                        f"{progress_bar(i)}\n{step}",
                        parse_mode=None
                    )
                except Exception:
                    pass

        # Jalankan animasi + kirim email bersamaan
        sender = get_email()
        anim_task = asyncio.create_task(animate())

        if not sender:
            await anim_task
            await msg.edit_text(
                "❌ *Tidak ada email tersedia!*\nHubungi admin.",
                reply_markup=kb_back()
            )
            return

        # Kirim email di thread
        result_holder = {}
        def do_send():
            result_holder["ok"] = send_email(number, sender)

        t = threading.Thread(target=do_send, daemon=True)
        t.start()
        await anim_task
        t.join()

        ok = result_holder.get("ok", False)
        update_req(u.id)
        add_log(u.id, number, sender["email"], "ok" if ok else "fail")
        if ok:
            inc_email(sender["email"])

        if ok:
            result_text = (
                f"✅ *BANDING BERHASIL DIKIRIM\\!*\n\n"
                f"📱 Nomor: `{number}`\n"
                f"📧 Via: `{sender['email']}`\n"
                f"🎯 Target: WhatsApp Support\n"
                f"⏱ Cooldown: {COOLDOWN} detik\n\n"
                f"💡 Proses review WhatsApp 1\\-24 jam\\.\n"
                f"Coba lagi jika belum berhasil\\."
            )
        else:
            result_text = (
                f"❌ *GAGAL MENGIRIM BANDING\\!*\n\n"
                f"📱 Nomor: `{number}`\n"
                f"⚠️ Cek konfigurasi email atau coba lagi\\."
            )

        await msg.edit_text(result_text, parse_mode=None, reply_markup=kb_back())

        # Notifikasi admin
        try:
            icon = "✅" if ok else "❌"
            await ctx.bot.send_message(
                ADMIN_ID,
                f"🔔 *REQUEST FIX MERAH*\n\n"
                f"{icon} Status: {'Sukses' if ok else 'Gagal'}\n"
                f"👤 User: {u.full_name} (@{u.username or '-'})\n"
                f"🆔 ID: `{u.id}`\n"
                f"📱 Nomor: `{number}`\n"
                f"📧 Email: `{sender['email']}`",
                parse_mode=None
            )
        except Exception:
            pass
        return

    await update.message.reply_text("Ketik /start untuk membuka menu.", reply_markup=kb_main())

# ---- APPROVE/REJECT PAYMENT ----
async def cmd_paybayar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u.id != ADMIN_ID:
        return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Format: `/paybayar PAY_ID HARI`\nContoh: `/paybayar 1 30`", parse_mode=None)
        return
    try:
        pay_id = int(args[0])
        days   = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Format salah! ID dan hari harus angka.")
        return

    # Cari data pembayaran
    with db() as c:
        row = c.execute("SELECT user_id, package FROM payments WHERE id=?", (pay_id,)).fetchone()
    if not row:
        await update.message.reply_text("❌ Payment ID tidak ditemukan!")
        return

    uid, pkg_key = row
    set_vip(uid, days)
    update_payment(pay_id, "approved")
    pkg = VIP_PACKAGES.get(pkg_key, {})

    await update.message.reply_text(
        f"✅ Pembayaran disetujui!\n🆔 User: `{uid}` | 📦 {pkg.get('label',pkg_key)} | 📅 {days} hari",
        parse_mode=None, reply_markup=kb_admin()
    )
    until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        await ctx.bot.send_message(
            uid,
            f"🎉 *PEMBAYARAN DIKONFIRMASI!*\n\n"
            f"👑 Status VIP kamu sudah aktif!\n"
            f"📦 Paket: *{pkg.get('label', pkg_key)}*\n"
            f"📅 Aktif hingga: `{until}`\n\n"
            f"Ketik /start untuk mulai menggunakan fitur Fix Merah!",
            parse_mode=None
        )
    except Exception:
        pass

async def cmd_paytolak(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u.id != ADMIN_ID:
        return
    args = ctx.args
    if len(args) < 1:
        await update.message.reply_text("Format: `/paytolak PAY_ID`", parse_mode=None)
        return
    try:
        pay_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID harus angka.")
        return

    with db() as c:
        row = c.execute("SELECT user_id FROM payments WHERE id=?", (pay_id,)).fetchone()
    if not row:
        await update.message.reply_text("❌ Payment ID tidak ditemukan!")
        return

    uid = row[0]
    update_payment(pay_id, "rejected")
    await update.message.reply_text(f"❌ Pembayaran `{pay_id}` ditolak.", parse_mode=None)
    try:
        await ctx.bot.send_message(
            uid,
            "❌ *Maaf, pembayaran kamu ditolak.*\n\n"
            "Kemungkinan bukti tidak valid atau nominal tidak sesuai.\n"
            "Hubungi admin untuk informasi lebih lanjut.",
            parse_mode=None
        )
    except Exception:
        pass

# ---- HANDLER FOTO (bukti bayar berupa gambar) ----
async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if ctx.user_data.get("state") != "wait_proof":
        return

    pkg_key = ctx.user_data.get("pkg")
    method  = ctx.user_data.get("pay_method")
    ctx.user_data["state"] = None

    pkg = VIP_PACKAGES.get(pkg_key, {})
    price_fmt = f"Rp {pkg.get('price',0):,}".replace(",",".")

    # Ambil file_id foto terbesar
    photo     = update.message.photo[-1]
    file_id   = photo.file_id
    pay_id    = add_payment(u.id, pkg_key, method, f"[FOTO:{file_id}]")

    await update.message.reply_text(
        f"✅ *FOTO BUKTI DITERIMA!*\n\n"
        f"📦 Paket: *{pkg.get('label','')}* ({price_fmt})\n"
        f"💳 Metode: *{method}*\n\n"
        f"⏳ Admin akan memverifikasi dalam 1-10 menit.\n"
        f"Kamu akan dapat notifikasi setelah VIP aktif!",
        parse_mode=None, reply_markup=kb_main()
    )

    # Kirim foto ke admin
    try:
        await ctx.bot.send_photo(
            ADMIN_ID,
            photo=file_id,
            caption=(
                f"💰 *BUKTI BAYAR BARU (FOTO)!*\n\n"
                f"👤 {u.full_name} (@{u.username or '-'})\n"
                f"🆔 User ID: `{u.id}`\n"
                f"📦 Paket: {pkg.get('label',pkg_key)}\n"
                f"💵 Harga: {price_fmt}\n"
                f"💳 Metode: {method}\n\n"
                f"Gunakan `/paybayar {pay_id} {pkg.get('days',30)}` untuk approve\n"
                f"Atau `/paytolak {pay_id}` untuk tolak"
            ),
            parse_mode=None
        )
    except Exception:
        pass

# ===================== MAIN ============================
def main():
    if ADMIN_ID == 0:
        print("=" * 50)
        print("⚠️  ADMIN_ID belum diisi!")
        print("Edit bot.py dan isi ADMIN_ID dengan ID Telegram kamu.")
        print("Cara cek ID: chat @userinfobot di Telegram, lalu ketik /start")
        print("=" * 50)

    if BOT_TOKEN == "ISI_TOKEN_BOT_KAMU":
        print("=" * 50)
        print("⚠️  BOT_TOKEN belum diisi!")
        print("Edit bot.py dan isi BOT_TOKEN dari @BotFather")
        print("=" * 50)
        return

    init_db()
    log.info(f"Bot v2.0 starting... ADMIN_ID={ADMIN_ID}")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("admin",   cmd_admin))
    app.add_handler(CommandHandler("id",      cmd_id))
    app.add_handler(CommandHandler("approve",  cmd_approve))
    app.add_handler(CommandHandler("reject",   cmd_reject))
    app.add_handler(CommandHandler("paybayar", cmd_paybayar))
    app.add_handler(CommandHandler("paytolak", cmd_paytolak))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Bot running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
