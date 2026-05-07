"""
Bot Telegram - Manajemen Kontak VCF
=====================================
Fitur:
- /to_vcf     - Konversi file ke .vcf
- /to_txt     - Konversi file ke .txt
- /admin      - Fitur admin/navy
- /manual     - Input kontak manual
- /add        - Tambah kontak ke .vcf
- /delete     - Hapus kontak dari file
- /renamectc  - Ganti nama kontak
- /renamefile - Ganti nama file
- /merge      - Gabungkan file
- /split      - Pecah file
- /count      - Hitung jumlah kontak
- /nodup      - Hapus kontak duplikat
- /getname    - Extract nama file
- /generate   - Generate nama file
- /getcontent - Ekstrak isi file .txt
- /setting    - Menu pengaturan
- /status     - Cek status akun
- /vip        - Daftar paket premium
- /referral   - Undang teman, dapat koin

Requirements:
    pip install python-telegram-bot==20.7
    
Cara pakai:
    1. Ganti TOKEN dengan token bot kamu dari @BotFather
    2. Jalankan: python bot_telegram.py
"""

import os
import re
import uuid
import logging
import hashlib
from datetime import datetime
from collections import defaultdict

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ==================== KONFIGURASI ====================
TOKEN = "8603565885:AAH4WYmzOBeWxS6QkgQLUqpuZjWMIABchCA"
ADMIN_IDS = [7678868549]  # Ganti dengan Telegram ID admin

# ==================== LOGGING ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==================== STATE CONVERSATION ====================
(
    MANUAL_NAMA, MANUAL_NOMOR,
    ADD_NAMA, ADD_NOMOR,
    DELETE_INPUT,
    RENAME_CTC_LAMA, RENAME_CTC_BARU,
    RENAME_FILE_NAMA,
    MERGE_FILE,
    SPLIT_JUMLAH,
    GETCONTENT_FILE,
    GENERATE_AWALAN,
    SETTING_MENU,
) = range(13)

# ==================== STORAGE SEMENTARA (pakai database di produksi) ====================
user_data_store = defaultdict(lambda: {
    "kontak": [],          # list of {"nama": str, "nomor": str}
    "file_nama": "kontak",  # nama file default
    "vip": False,
    "koin": 0,
    "referral_code": "",
    "referred_by": None,
    "join_date": datetime.now().strftime("%Y-%m-%d"),
})

# Simpan referral code → user_id
referral_map = {}

# ==================== HELPER FUNCTIONS ====================

def get_user(user_id: int) -> dict:
    """Ambil data user, buat jika belum ada."""
    if not user_data_store[user_id]["referral_code"]:
        code = hashlib.md5(str(user_id).encode()).hexdigest()[:8].upper()
        user_data_store[user_id]["referral_code"] = code
        referral_map[code] = user_id
    return user_data_store[user_id]


def kontak_ke_vcf_text(kontak_list: list) -> str:
    """Ubah list kontak ke format VCF string."""
    vcf_lines = []
    for k in kontak_list:
        vcf_lines.append("BEGIN:VCARD")
        vcf_lines.append("VERSION:3.0")
        vcf_lines.append(f"FN:{k['nama']}")
        vcf_lines.append(f"N:{k['nama']};;;")
        vcf_lines.append(f"TEL;TYPE=CELL:{k['nomor']}")
        vcf_lines.append("END:VCARD")
    return "\n".join(vcf_lines)


def parse_vcf(content: str) -> list:
    """Parse isi VCF menjadi list kontak."""
    kontak_list = []
    current = {}
    for line in content.splitlines():
        line = line.strip()
        if line == "BEGIN:VCARD":
            current = {}
        elif line.startswith("FN:"):
            current["nama"] = line[3:]
        elif line.startswith("TEL"):
            nomor = line.split(":")[-1]
            current["nomor"] = nomor
        elif line == "END:VCARD":
            if "nama" in current and "nomor" in current:
                kontak_list.append(current)
            current = {}
    return kontak_list


def parse_txt(content: str) -> list:
    """Parse file .txt (format: Nama|Nomor atau Nomor saja per baris)."""
    kontak_list = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            parts = line.split("|", 1)
            kontak_list.append({"nama": parts[0].strip(), "nomor": parts[1].strip()})
        else:
            kontak_list.append({"nama": line, "nomor": line})
    return kontak_list


def format_menu() -> str:
    return (
        "📋 *MENU UTAMA*\n\n"
        "🔄 *Konversi File*\n"
        "`/to_vcf` — Konversi file ke .vcf\n"
        "`/to_txt` — Konversi file ke .txt\n\n"
        "📝 *Manajemen Kontak*\n"
        "`/manual` — Input kontak manual\n"
        "`/add` — Tambah kontak ke file\n"
        "`/delete` — Hapus kontak dari file\n"
        "`/renamectc` — Ganti nama kontak\n"
        "`/nodup` — Hapus duplikat\n\n"
        "📁 *Manajemen File*\n"
        "`/renamefile` — Ganti nama file\n"
        "`/merge` — Gabungkan file\n"
        "`/split` — Pecah file\n"
        "`/count` — Hitung jumlah kontak\n"
        "`/getname` — Extract nama file\n"
        "`/generate` — Generate nama file\n"
        "`/getcontent` — Ekstrak isi file .txt\n\n"
        "👤 *Akun*\n"
        "`/status` — Cek status akun\n"
        "`/setting` — Pengaturan\n"
        "`/vip` — Paket premium\n"
        "`/referral` — Undang teman\n\n"
        "🔐 *Admin*\n"
        "`/admin` — Panel admin"
    )


# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id)

    # Proses referral jika ada
    if context.args:
        kode = context.args[0].upper()
        u = get_user(user.id)
        if kode in referral_map and referral_map[kode] != user.id and not u["referred_by"]:
            u["referred_by"] = referral_map[kode]
            u["koin"] += 10
            referrer = get_user(referral_map[kode])
            referrer["koin"] += 20
            await context.bot.send_message(
                referral_map[kode],
                f"🎉 Teman kamu bergabung menggunakan kode referral!\n"
                f"Kamu mendapat *20 koin*. Total koin: *{referrer['koin']}*",
                parse_mode="Markdown",
            )

    text = (
        f"👋 Halo, *{user.first_name}*!\n\n"
        "Selamat datang di *Bot Manajemen Kontak VCF* 📱\n\n"
        "Bot ini membantu kamu mengelola, konversi, dan manipulasi file kontak (.vcf & .txt) dengan mudah.\n\n"
        + format_menu()
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_menu(), parse_mode="Markdown")


# ─── /to_vcf ───
async def to_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 Kirimkan file *.txt* atau *.vcf* yang ingin dikonversi ke format VCF.\n\n"
        "Format .txt yang didukung:\n"
        "`Nama|Nomor` (satu per baris)\natau `Nomor` saja per baris.",
        parse_mode="Markdown",
    )
    context.user_data["waiting_for"] = "to_vcf"


# ─── /to_txt ───
async def to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 Kirimkan file *.vcf* yang ingin dikonversi ke format TXT.",
        parse_mode="Markdown",
    )
    context.user_data["waiting_for"] = "to_txt"


# ─── /count ───
async def count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Kirimkan file *.vcf* atau *.txt* untuk dihitung jumlah kontaknya.",
        parse_mode="Markdown",
    )
    context.user_data["waiting_for"] = "count"


# ─── /nodup ───
async def nodup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧹 Kirimkan file *.vcf* atau *.txt* untuk dihapus kontrak duplikatnya.",
        parse_mode="Markdown",
    )
    context.user_data["waiting_for"] = "nodup"


# ─── /getname ───
async def getname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏷️ Kirimkan file *.vcf* untuk diekstrak nama-nama kontaknya.",
        parse_mode="Markdown",
    )
    context.user_data["waiting_for"] = "getname"


# ─── /getcontent ───
async def getcontent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 Kirimkan file *.txt* untuk diekstrak isinya.",
        parse_mode="Markdown",
    )
    context.user_data["waiting_for"] = "getcontent"


# ─── /merge ───
async def merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["merge_files"] = []
    await update.message.reply_text(
        "🔀 *Gabungkan File*\n\n"
        "Kirimkan file-file *.vcf* atau *.txt* satu per satu.\n"
        "Setelah selesai, ketik /merge_done untuk menggabungkan.",
        parse_mode="Markdown",
    )
    context.user_data["waiting_for"] = "merge"


async def merge_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = context.user_data.get("merge_files", [])
    if len(files) < 2:
        await update.message.reply_text("⚠️ Kirimkan minimal 2 file untuk digabungkan.")
        return

    all_kontak = []
    for kontak_list in files:
        all_kontak.extend(kontak_list)

    vcf_content = kontak_ke_vcf_text(all_kontak)
    filename = f"merged_{datetime.now().strftime('%Y%m%d%H%M%S')}.vcf"
    await update.message.reply_document(
        document=vcf_content.encode(),
        filename=filename,
        caption=f"✅ Berhasil menggabungkan *{len(files)} file* dengan total *{len(all_kontak)} kontak*.",
        parse_mode="Markdown",
    )
    context.user_data["merge_files"] = []
    context.user_data.pop("waiting_for", None)


# ─── /split ───
async def split_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✂️ *Pecah File VCF*\n\nKirimkan file *.vcf* yang ingin dipecah.",
        parse_mode="Markdown",
    )
    context.user_data["waiting_for"] = "split_file"


# ─── /generate ───
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Nama Acak", callback_data="gen_random"),
         InlineKeyboardButton("Nama Tanggal", callback_data="gen_date")],
        [InlineKeyboardButton("Nama + Nomor Urut", callback_data="gen_seq")],
    ]
    await update.message.reply_text(
        "⚙️ *Generate Nama File*\n\nPilih format nama file:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def generate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    now = datetime.now()
    if data == "gen_random":
        nama = f"kontak_{uuid.uuid4().hex[:8]}.vcf"
    elif data == "gen_date":
        nama = f"kontak_{now.strftime('%Y%m%d_%H%M%S')}.vcf"
    elif data == "gen_seq":
        uid = query.from_user.id
        u = get_user(uid)
        idx = len(u["kontak"]) + 1
        nama = f"kontak_{idx:04d}.vcf"
    else:
        nama = "kontak.vcf"
    await query.edit_message_text(
        f"✅ Nama file yang di-generate:\n`{nama}`", parse_mode="Markdown"
    )


# ─── /renamefile ───
async def renamefile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✏️ Ketik nama file baru (tanpa ekstensi, akan otomatis ditambahkan .vcf):"
    )
    return RENAME_FILE_NAMA


async def renamefile_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    lama = u["file_nama"]
    baru = update.message.text.strip()
    u["file_nama"] = baru
    await update.message.reply_text(
        f"✅ Nama file diubah dari `{lama}.vcf` → `{baru}.vcf`",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ─── /manual ───
async def manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Masukkan *nama* kontak:")
    return MANUAL_NAMA


async def manual_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_nama"] = update.message.text.strip()
    await update.message.reply_text("📞 Masukkan *nomor* telepon (contoh: 08123456789):")
    return MANUAL_NOMOR


async def manual_nomor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    nomor = update.message.text.strip()
    nama = context.user_data.get("new_nama", "Kontak")
    u = get_user(user_id)
    u["kontak"].append({"nama": nama, "nomor": nomor})

    vcf_content = kontak_ke_vcf_text(u["kontak"])
    filename = f"{u['file_nama']}.vcf"
    await update.message.reply_document(
        document=vcf_content.encode(),
        filename=filename,
        caption=f"✅ Kontak *{nama}* ({nomor}) berhasil ditambahkan!\nTotal kontak: *{len(u['kontak'])}*",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ─── /add ───
async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("➕ Masukkan *nama* kontak yang ingin ditambahkan:")
    return ADD_NAMA


async def add_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["add_nama"] = update.message.text.strip()
    await update.message.reply_text("📞 Masukkan *nomor* teleponnya:")
    return ADD_NOMOR


async def add_nomor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    nomor = update.message.text.strip()
    nama = context.user_data.get("add_nama", "Kontak")
    u = get_user(user_id)
    u["kontak"].append({"nama": nama, "nomor": nomor})
    await update.message.reply_text(
        f"✅ Kontak *{nama}* ({nomor}) ditambahkan. Total: *{len(u['kontak'])}*",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ─── /delete ───
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🗑️ Ketik *nama* atau *nomor* kontak yang ingin dihapus:"
    )
    return DELETE_INPUT


async def delete_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query_str = update.message.text.strip().lower()
    u = get_user(user_id)
    sebelum = len(u["kontak"])
    u["kontak"] = [
        k for k in u["kontak"]
        if query_str not in k["nama"].lower() and query_str not in k["nomor"]
    ]
    dihapus = sebelum - len(u["kontak"])
    await update.message.reply_text(
        f"✅ *{dihapus}* kontak berhasil dihapus. Sisa: *{len(u['kontak'])}*",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ─── /renamectc ───
async def renamectc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ Masukkan *nama lama* kontak:")
    return RENAME_CTC_LAMA


async def renamectc_lama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["rename_lama"] = update.message.text.strip()
    await update.message.reply_text("✏️ Masukkan *nama baru*:")
    return RENAME_CTC_BARU


async def renamectc_baru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lama = context.user_data.get("rename_lama", "")
    baru = update.message.text.strip()
    u = get_user(user_id)
    count_rename = 0
    for k in u["kontak"]:
        if k["nama"].lower() == lama.lower():
            k["nama"] = baru
            count_rename += 1
    if count_rename:
        await update.message.reply_text(
            f"✅ *{count_rename}* kontak berganti nama dari `{lama}` → `{baru}`",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(f"⚠️ Kontak `{lama}` tidak ditemukan.", parse_mode="Markdown")
    return ConversationHandler.END


# ─── /status ───
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    tipe = "👑 VIP" if u["vip"] else "🆓 Gratis"
    text = (
        f"👤 *Status Akun*\n\n"
        f"Nama: *{user.first_name}*\n"
        f"ID: `{user.id}`\n"
        f"Tipe: {tipe}\n"
        f"💰 Koin: *{u['koin']}*\n"
        f"📇 Kontak tersimpan: *{len(u['kontak'])}*\n"
        f"📁 Nama file: `{u['file_nama']}.vcf`\n"
        f"📅 Bergabung: {u['join_date']}\n"
        f"🔗 Kode referral: `{u['referral_code']}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── /vip ───
async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⭐ Basic – 50 Koin/bulan", callback_data="vip_basic")],
        [InlineKeyboardButton("💎 Pro – 100 Koin/bulan", callback_data="vip_pro")],
        [InlineKeyboardButton("🏆 Ultimate – 200 Koin/bulan", callback_data="vip_ultimate")],
    ]
    text = (
        "✨ *Paket Premium*\n\n"
        "🆓 *Gratis*: Maks 100 kontak/file, fitur dasar\n\n"
        "⭐ *Basic* (50 Koin/bln):\n"
        "• Maks 1.000 kontak/file\n"
        "• Akses /merge & /split\n\n"
        "💎 *Pro* (100 Koin/bln):\n"
        "• Maks 10.000 kontak/file\n"
        "• Semua fitur Basic\n"
        "• Prioritas antrian\n\n"
        "🏆 *Ultimate* (200 Koin/bln):\n"
        "• Tidak terbatas\n"
        "• Semua fitur Pro\n"
        "• Support 24/7"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def vip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    u = get_user(user_id)
    paket_harga = {"vip_basic": 50, "vip_pro": 100, "vip_ultimate": 200}
    paket_nama = {"vip_basic": "Basic", "vip_pro": "Pro", "vip_ultimate": "Ultimate"}
    paket = query.data
    harga = paket_harga.get(paket, 0)
    if u["koin"] >= harga:
        u["koin"] -= harga
        u["vip"] = True
        await query.edit_message_text(
            f"✅ Berhasil berlangganan paket *{paket_nama[paket]}*!\n"
            f"Koin tersisa: *{u['koin']}*",
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            f"❌ Koin tidak cukup!\nKamu punya *{u['koin']}* koin, butuh *{harga}* koin.\n"
            f"Gunakan /referral untuk mendapatkan koin gratis.",
            parse_mode="Markdown",
        )


# ─── /referral ───
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    code = u["referral_code"]
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"
    text = (
        f"🔗 *Program Referral*\n\n"
        f"Kode kamu: `{code}`\n"
        f"Link undangan:\n{link}\n\n"
        f"💰 *Hadiah:*\n"
        f"• Kamu dapat *20 koin* per teman yang bergabung\n"
        f"• Teman baru dapat *10 koin* bonus\n\n"
        f"💼 Koin kamu saat ini: *{u['koin']}*\n\n"
        f"Bagikan link di atas ke teman-temanmu!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── /setting ───
async def setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📁 Ganti Nama File", callback_data="set_rename"),
         InlineKeyboardButton("🗑️ Hapus Semua Kontak", callback_data="set_clear")],
        [InlineKeyboardButton("📊 Info Akun", callback_data="set_info")],
    ]
    await update.message.reply_text(
        "⚙️ *Menu Pengaturan*\n\nPilih opsi:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    u = get_user(user_id)
    if query.data == "set_rename":
        await query.edit_message_text("✏️ Kirim nama file baru (tanpa ekstensi .vcf):")
        context.user_data["waiting_for"] = "setting_rename"
    elif query.data == "set_clear":
        keyboard = [
            [InlineKeyboardButton("✅ Ya, Hapus", callback_data="set_clear_confirm"),
             InlineKeyboardButton("❌ Batal", callback_data="set_cancel")]
        ]
        await query.edit_message_text(
            f"⚠️ Yakin ingin menghapus *{len(u['kontak'])}* kontak?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    elif query.data == "set_clear_confirm":
        u["kontak"] = []
        await query.edit_message_text("✅ Semua kontak berhasil dihapus.")
    elif query.data == "set_cancel":
        await query.edit_message_text("❌ Dibatalkan.")
    elif query.data == "set_info":
        user = query.from_user
        await query.edit_message_text(
            f"📊 *Info Akun*\n\nID: `{user.id}`\nNama: {user.first_name}\n"
            f"Koin: *{u['koin']}*\nKontak: *{len(u['kontak'])}*\nVIP: {'Ya' if u['vip'] else 'Tidak'}",
            parse_mode="Markdown",
        )


# ─── /admin ───
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Kamu tidak punya akses admin.")
        return
    total_user = len(user_data_store)
    total_kontak = sum(len(u["kontak"]) for u in user_data_store.values())
    total_vip = sum(1 for u in user_data_store.values() if u["vip"])
    text = (
        f"🔐 *Panel Admin*\n\n"
        f"👥 Total Pengguna: *{total_user}*\n"
        f"📇 Total Kontak: *{total_kontak}*\n"
        f"👑 Pengguna VIP: *{total_vip}*\n\n"
        f"_Gunakan fitur admin dengan bijak._"
    )
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("👑 Beri VIP", callback_data="admin_givevip")],
        [InlineKeyboardButton("💰 Beri Koin", callback_data="admin_givecoin")],
    ]
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("Akses ditolak!", show_alert=True)
        return
    if query.data == "admin_broadcast":
        await query.edit_message_text("📢 Ketik pesan yang ingin di-broadcast ke semua user:")
        context.user_data["waiting_for"] = "admin_broadcast"
    elif query.data == "admin_givevip":
        await query.edit_message_text("👑 Ketik ID user yang ingin diberi VIP:")
        context.user_data["waiting_for"] = "admin_givevip"
    elif query.data == "admin_givecoin":
        await query.edit_message_text("💰 Ketik format: `ID_USER JUMLAH_KOIN`\nContoh: `123456789 100`")
        context.user_data["waiting_for"] = "admin_givecoin"


# ─── HANDLER FILE MASUK ───
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    waiting = context.user_data.get("waiting_for")

    if not doc:
        return

    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()
    content = file_bytes.decode("utf-8", errors="ignore")
    fname = doc.file_name or "file"
    user_id = update.effective_user.id
    u = get_user(user_id)

    # Tentukan tipe file
    is_vcf = fname.lower().endswith(".vcf")
    is_txt = fname.lower().endswith(".txt")

    if waiting == "to_vcf":
        if is_txt:
            kontak_list = parse_txt(content)
        elif is_vcf:
            kontak_list = parse_vcf(content)
        else:
            await update.message.reply_text("⚠️ Format file tidak didukung. Kirim file .vcf atau .txt")
            return
        vcf_out = kontak_ke_vcf_text(kontak_list)
        out_name = fname.rsplit(".", 1)[0] + ".vcf"
        await update.message.reply_document(
            document=vcf_out.encode(),
            filename=out_name,
            caption=f"✅ Berhasil dikonversi ke VCF!\nTotal kontak: *{len(kontak_list)}*",
            parse_mode="Markdown",
        )
        context.user_data.pop("waiting_for", None)

    elif waiting == "to_txt":
        if is_vcf:
            kontak_list = parse_vcf(content)
        elif is_txt:
            kontak_list = parse_txt(content)
        else:
            await update.message.reply_text("⚠️ Format file tidak didukung.")
            return
        lines = [f"{k['nama']}|{k['nomor']}" for k in kontak_list]
        txt_out = "\n".join(lines)
        out_name = fname.rsplit(".", 1)[0] + ".txt"
        await update.message.reply_document(
            document=txt_out.encode(),
            filename=out_name,
            caption=f"✅ Berhasil dikonversi ke TXT!\nTotal kontak: *{len(kontak_list)}*",
            parse_mode="Markdown",
        )
        context.user_data.pop("waiting_for", None)

    elif waiting == "count":
        if is_vcf:
            kontak_list = parse_vcf(content)
        else:
            kontak_list = parse_txt(content)
        await update.message.reply_text(
            f"📊 *Hasil Hitung*\n\nFile: `{fname}`\nJumlah kontak: *{len(kontak_list)}*",
            parse_mode="Markdown",
        )
        context.user_data.pop("waiting_for", None)

    elif waiting == "nodup":
        if is_vcf:
            kontak_list = parse_vcf(content)
        else:
            kontak_list = parse_txt(content)
        seen = set()
        unique = []
        for k in kontak_list:
            key = k["nomor"].strip()
            if key not in seen:
                seen.add(key)
                unique.append(k)
        duplikat = len(kontak_list) - len(unique)
        if is_vcf:
            out = kontak_ke_vcf_text(unique)
            out_name = fname.rsplit(".", 1)[0] + "_nodup.vcf"
        else:
            out = "\n".join(f"{k['nama']}|{k['nomor']}" for k in unique)
            out_name = fname.rsplit(".", 1)[0] + "_nodup.txt"
        await update.message.reply_document(
            document=out.encode(),
            filename=out_name,
            caption=f"✅ Selesai!\nDuplikat dihapus: *{duplikat}*\nKontak unik: *{len(unique)}*",
            parse_mode="Markdown",
        )
        context.user_data.pop("waiting_for", None)

    elif waiting == "getname":
        if is_vcf:
            kontak_list = parse_vcf(content)
        else:
            kontak_list = parse_txt(content)
        names = "\n".join(k["nama"] for k in kontak_list[:50])
        extra = f"\n... dan {len(kontak_list)-50} lainnya" if len(kontak_list) > 50 else ""
        await update.message.reply_text(
            f"🏷️ *Nama-nama Kontak* (`{fname}`):\n\n{names}{extra}",
            parse_mode="Markdown",
        )
        context.user_data.pop("waiting_for", None)

    elif waiting == "getcontent":
        if is_txt:
            preview = content[:2000]
            extra = "\n... (terpotong)" if len(content) > 2000 else ""
            await update.message.reply_text(
                f"📄 *Isi file* `{fname}`:\n\n```\n{preview}{extra}\n```",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text("⚠️ Hanya mendukung file .txt")
        context.user_data.pop("waiting_for", None)

    elif waiting == "merge":
        if is_vcf:
            kontak_list = parse_vcf(content)
        else:
            kontak_list = parse_txt(content)
        context.user_data.setdefault("merge_files", []).append(kontak_list)
        idx = len(context.user_data["merge_files"])
        await update.message.reply_text(
            f"✅ File ke-{idx} diterima (*{len(kontak_list)}* kontak).\n"
            f"Kirim file berikutnya atau ketik /merge_done",
            parse_mode="Markdown",
        )

    elif waiting == "split_file":
        if is_vcf:
            kontak_list = parse_vcf(content)
        else:
            kontak_list = parse_txt(content)
        context.user_data["split_kontak"] = kontak_list
        await update.message.reply_text(
            f"✅ File diterima (*{len(kontak_list)}* kontak).\n"
            f"Pecah menjadi berapa bagian? (ketik angka)"
        )
        context.user_data["waiting_for"] = "split_count"

    else:
        await update.message.reply_text(
            "📎 File diterima. Gunakan perintah seperti /to_vcf, /to_txt, /count, dll. lalu kirim ulang file."
        )


# ─── HANDLER TEXT UMUM ───
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    waiting = context.user_data.get("waiting_for")
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if waiting == "split_count":
        try:
            n = int(text)
            kontak_list = context.user_data.get("split_kontak", [])
            if n < 2 or n > len(kontak_list):
                await update.message.reply_text(f"⚠️ Masukkan angka antara 2 dan {len(kontak_list)}.")
                return
            size = len(kontak_list) // n
            for i in range(n):
                bagian = kontak_list[i * size: (i + 1) * size if i < n - 1 else len(kontak_list)]
                vcf_out = kontak_ke_vcf_text(bagian)
                await update.message.reply_document(
                    document=vcf_out.encode(),
                    filename=f"bagian_{i+1}.vcf",
                    caption=f"📦 Bagian {i+1}/{n} — *{len(bagian)}* kontak",
                    parse_mode="Markdown",
                )
            context.user_data.pop("waiting_for", None)
            context.user_data.pop("split_kontak", None)
        except ValueError:
            await update.message.reply_text("⚠️ Masukkan angka yang valid.")

    elif waiting == "setting_rename":
        u = get_user(user_id)
        lama = u["file_nama"]
        u["file_nama"] = text
        await update.message.reply_text(
            f"✅ Nama file diubah: `{lama}.vcf` → `{text}.vcf`", parse_mode="Markdown"
        )
        context.user_data.pop("waiting_for", None)

    elif waiting == "admin_broadcast" and user_id in ADMIN_IDS:
        for uid in user_data_store:
            try:
                await context.bot.send_message(uid, f"📢 *Pengumuman:*\n\n{text}", parse_mode="Markdown")
            except Exception:
                pass
        await update.message.reply_text(f"✅ Broadcast dikirim ke {len(user_data_store)} pengguna.")
        context.user_data.pop("waiting_for", None)

    elif waiting == "admin_givevip" and user_id in ADMIN_IDS:
        try:
            target_id = int(text)
            get_user(target_id)["vip"] = True
            await update.message.reply_text(f"✅ User `{target_id}` kini VIP.", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("⚠️ ID tidak valid.")
        context.user_data.pop("waiting_for", None)

    elif waiting == "admin_givecoin" and user_id in ADMIN_IDS:
        try:
            parts = text.split()
            target_id = int(parts[0])
            jumlah = int(parts[1])
            get_user(target_id)["koin"] += jumlah
            await update.message.reply_text(
                f"✅ *{jumlah}* koin diberikan ke user `{target_id}`.", parse_mode="Markdown"
            )
        except (ValueError, IndexError):
            await update.message.reply_text("⚠️ Format salah. Contoh: `123456789 100`")
        context.user_data.pop("waiting_for", None)


# ==================== MAIN ====================

def main():
    app = Application.builder().token(TOKEN).build()

    # Conversation: /manual
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("manual", manual)],
        states={
            MANUAL_NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_nama)],
            MANUAL_NOMOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_nomor)],
        },
        fallbacks=[],
    ))

    # Conversation: /add
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add", add_cmd)],
        states={
            ADD_NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_nama)],
            ADD_NOMOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_nomor)],
        },
        fallbacks=[],
    ))

    # Conversation: /delete
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete", delete_cmd)],
        states={
            DELETE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_input)],
        },
        fallbacks=[],
    ))

    # Conversation: /renamectc
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("renamectc", renamectc)],
        states={
            RENAME_CTC_LAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, renamectc_lama)],
            RENAME_CTC_BARU: [MessageHandler(filters.TEXT & ~filters.COMMAND, renamectc_baru)],
        },
        fallbacks=[],
    ))

    # Conversation: /renamefile
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("renamefile", renamefile)],
        states={
            RENAME_FILE_NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, renamefile_input)],
        },
        fallbacks=[],
    ))

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("to_vcf", to_vcf))
    app.add_handler(CommandHandler("to_txt", to_txt))
    app.add_handler(CommandHandler("count", count))
    app.add_handler(CommandHandler("nodup", nodup))
    app.add_handler(CommandHandler("getname", getname))
    app.add_handler(CommandHandler("getcontent", getcontent))
    app.add_handler(CommandHandler("merge", merge))
    app.add_handler(CommandHandler("merge_done", merge_done))
    app.add_handler(CommandHandler("split", split_cmd))
    app.add_handler(CommandHandler("generate", generate))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("vip", vip))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("setting", setting))
    app.add_handler(CommandHandler("admin", admin))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(generate_callback, pattern="^gen_"))
    app.add_handler(CallbackQueryHandler(vip_callback, pattern="^vip_"))
    app.add_handler(CallbackQueryHandler(setting_callback, pattern="^set_"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))

    # File & text handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🤖 Bot berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
