
import os
import json
import sqlite3
import asyncio
from datetime import datetime
from pathlib import Path

from google import genai
from threads_api import publish_thread, ThreadsAPIError
from x_api import publish_thread as publish_x_thread, XAPIError
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
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

DATA_DIR = Path("/app/data")
IMAGE_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "promobot.db"

IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER,
                caption TEXT,
                image_path TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Saya PromoBot.\n\n"
        "Kirim foto dengan caption untuk mengarsipkannya.\n\n"
        "Perintah:\n"
        "/buatutas topik promosi - Buat utas maksimal 2 bagian\n"
        "/draf - Lihat draf terbaru\n"
        "/arsip - Lihat arsip foto\n"
        "/start - Bantuan"
    )


async def save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    photo = message.photo[-1]
    caption = message.caption or ""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_id = message.from_user.id
    filepath = IMAGE_DIR / f"{timestamp}_{user_id}.jpg"

    file = await context.bot.get_file(photo.file_id)
    await file.download_to_drive(custom_path=str(filepath))

    with db() as conn:
        conn.execute(
            """INSERT INTO posts
            (telegram_user_id, caption, image_path, created_at)
            VALUES (?, ?, ?, ?)""",
            (
                user_id,
                caption,
                str(filepath),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

    await message.reply_text("Foto dan caption berhasil diarsipkan.")


def generate_thread(topic):
    client = genai.Client(api_key=GEMINI_KEY)

    prompt = f"""
Buat maksimal 2 posting dalam bahasa Indonesia berdasarkan topik:
{topic}

Ketentuan:
- Buat 1 atau 2 posting sesuai kebutuhan topik. Jika cukup satu, buat satu saja.
- Posting 1: gagasan utama atau pembuka yang menarik.
- Posting 2 (jika diperlukan): penjelasan lanjutan atau penutup.
- Hindari pengulangan, klaim tanpa dasar, dan fakta yang dibuat-buat.
- Setiap posting harus bisa berdiri sebagai teks singkat.
- Jangan menambahkan nomor di dalam teks posting.
- Kembalikan hanya JSON valid dengan format:
  {{"posts": ["teks 1", "teks 2"]}}
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    result = json.loads(response.text)
    posts = result["posts"]

    if not (1 <= len(posts) <= 2) or not all(
        isinstance(item, str) and item.strip() for item in posts
    ):
        raise ValueError("Gemini harus menghasilkan 1 atau 2 posting.")

    return [item.strip() for item in posts]


async def create_thread(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    topic = " ".join(context.args).strip()

    if not topic:
        await update.message.reply_text(
            "Masukkan topik setelah perintah.\n"
            "Contoh: /buatutas manfaat menanam sayuran di rumah"
        )
        return

    if not GEMINI_KEY:
        await update.message.reply_text(
            "GEMINI_API_KEY belum diatur di file .env."
        )
        return

    status = await update.message.reply_text(
        "Sedang menyusun maksimal 2 posting. Mohon tunggu..."
    )

    try:
        posts = await asyncio.to_thread(generate_thread, topic)
    except Exception as exc:
        print(f"Kesalahan Gemini: {exc}")
        await status.edit_text(
            "Gagal membuat draf. Periksa API key, kuota Gemini, "
            "nama model, dan log Docker."
        )
        return

    content = json.dumps(posts, ensure_ascii=False)

    with db() as conn:
        cursor = conn.execute(
            """INSERT INTO thread_drafts
            (telegram_user_id, topic, content, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)""",
            (
                update.effective_user.id,
                topic,
                content,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        draft_id = cursor.lastrowid

    text = f"DRAF UTAS #{draft_id}\nTopik: {topic}\n\n"

    for i, post in enumerate(posts, start=1):
        text += f"{i}/{len(posts)}\n{post}\n\n"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Setujui draf",
                callback_data=f"approve:{draft_id}",
            ),
            InlineKeyboardButton(
                "Batalkan",
                callback_data=f"cancel:{draft_id}",
            ),
        ]
    ])

    await status.delete()
    await update.message.reply_text(
        text,
        reply_markup=keyboard,
    )


async def draft_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    try:
        action, draft_id_text = query.data.split(":", 1)
        draft_id = int(draft_id_text)
    except (ValueError, AttributeError):
        await query.edit_message_text("Perintah tombol tidak valid.")
        return

    user_id = query.from_user.id

    with db() as conn:
        row = conn.execute(
            """SELECT telegram_user_id, topic, content, status
            FROM thread_drafts WHERE id = ?""",
            (draft_id,),
        ).fetchone()

    if not row:
        await query.edit_message_text("Draf tidak ditemukan.")
        return

    owner_id, topic, content, status = row

    if owner_id != user_id:
        await query.answer("Draf ini bukan milikmu.", show_alert=True)
        return

    if status != "pending":
        await query.answer("Draf ini sudah diproses.", show_alert=True)
        return

    if action == "cancel":
        with db() as conn:
            conn.execute(
                "UPDATE thread_drafts SET status='cancelled' "
                "WHERE id=? AND status='pending'",
                (draft_id,),
            )
        await query.edit_message_text(f"Draf #{draft_id} dibatalkan.")
        return

    if action != "approve":
        await query.edit_message_text("Aksi tidak dikenal.")
        return

    try:
        posts = json.loads(content)
        if not isinstance(posts, list) or not (1 <= len(posts) <= 2):
            raise ValueError("Draf harus berisi 1 atau 2 posting.")
        if not all(isinstance(post, str) and post.strip() for post in posts):
            raise ValueError("Ada posting kosong dalam draf.")
    except (ValueError, TypeError) as exc:
        await query.edit_message_text(
            f"Draf #{draft_id} tidak valid: {exc}"
        )
        return

    await query.edit_message_text(
        f"Draf #{draft_id} sedang diterbitkan ke Threads dan X. Mohon tunggu."
    )

    threads_ids = None
    x_ids = None
    errors = []

    try:
        threads_ids = await publish_thread(posts)
    except Exception as exc:
        errors.append(f"Threads gagal: {exc}")
        print(f"Publikasi Threads gagal untuk draf #{draft_id}: {exc}")

    try:
        x_ids = await publish_x_thread(posts)
    except Exception as exc:
        errors.append(f"X gagal: {exc}")
        print(f"Publikasi X gagal untuk draf #{draft_id}: {exc}")

    # Jangan biarkan tombol persetujuan mengulang publikasi jika salah satu
    # platform berhasil. Jika keduanya gagal, draf tetap pending untuk diperiksa.
    if threads_ids or x_ids:
        with db() as conn:
            conn.execute(
                "UPDATE thread_drafts SET status='approved' "
                "WHERE id=? AND status='pending'",
                (draft_id,),
            )

    report = [
        f"Hasil publikasi draf #{draft_id}",
        f"Topik: {topic}",
        (
            f"Threads: {len(threads_ids)}/{len(posts)} posting berhasil"
            if threads_ids is not None
            else "Threads: gagal atau hasil tidak pasti"
        ),
        (
            f"X: {len(x_ids)}/{len(posts)} posting berhasil"
            if x_ids is not None
            else "X: gagal atau hasil tidak pasti"
        ),
    ]

    if errors:
        report.append("Periksa akun terkait sebelum mencoba lagi:")
        report.extend(errors)

    if threads_ids or x_ids:
        report.append("Status draf: approved (untuk mencegah publikasi ganda).")
    else:
        report.append(
            "Status draf tetap pending. Periksa kedua akun sebelum mencoba lagi."
        )

    await query.message.reply_text("\n".join(report))


async def show_draft(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    with db() as conn:
        row = conn.execute(
            """SELECT id, topic, content, status
            FROM thread_drafts
            WHERE telegram_user_id = ?
            ORDER BY id DESC LIMIT 1""",
            (update.effective_user.id,),
        ).fetchone()

    if not row:
        await update.message.reply_text("Belum ada draf.")
        return

    draft_id, topic, content, status = row
    posts = json.loads(content)

    text = f"DRAF UTAS #{draft_id}\nTopik: {topic}\nStatus: {status}\n\n"
    for i, post in enumerate(posts, start=1):
        text += f"{i}/{len(posts)}\n{post}\n\n"

    keyboard = None
    if status == "pending":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Setujui draf",
                    callback_data=f"approve:{draft_id}",
                ),
                InlineKeyboardButton(
                    "Batalkan",
                    callback_data=f"cancel:{draft_id}",
                ),
            ]
        ])

    await update.message.reply_text(text, reply_markup=keyboard)


async def archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as conn:
        rows = conn.execute(
            """SELECT id, caption, created_at FROM posts
            ORDER BY id DESC LIMIT 10"""
        ).fetchall()

    if not rows:
        await update.message.reply_text("Arsip masih kosong.")
        return

    result = ["10 arsip terbaru:"]
    for post_id, caption, created_at in rows:
        result.append(
            f"\n#{post_id} | {created_at}\n{caption or '(tanpa caption)'}"
        )

    await update.message.reply_text("\n".join(result))


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN belum diatur.")

    init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buatutas", create_thread))
    app.add_handler(CommandHandler("draf", show_draft))
    app.add_handler(CommandHandler("arsip", archive))
    app.add_handler(CallbackQueryHandler(draft_callback))
    app.add_handler(MessageHandler(filters.PHOTO, save_photo))

    print("PromoBot berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
