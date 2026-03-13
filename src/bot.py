import os
import asyncio
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BOT_NAME = os.getenv("BOT_NAME", "Grace")
BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Asia/Jakarta")
GLOBAL_RPM_LIMIT = max(1, int(os.getenv("GLOBAL_RPM_LIMIT", "4")))
USER_COOLDOWN_SEC = max(1.0, float(os.getenv("USER_COOLDOWN_SEC", "8")))

IDENTITY_TEXT = (
    "Saya adalah Grace, asisten AI DPNP yang dibuat oleh Brann. "
    "Saya siap membantu menjawab pertanyaan dan memberikan penjelasan dengan jelas."
)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
gemini_model: Optional[genai.GenerativeModel] = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(GEMINI_MODEL)

request_timestamps: deque[float] = deque()
last_user_request: dict[int, float] = {}
gemini_lock = asyncio.Lock()
NAME_TRIGGER_PUNCTUATION = ".,:;!?-"


@dataclass
class AIResult:
    text: str
    is_private_warning: bool = False
    is_error: bool = False


def _has_name_trigger(text: str) -> bool:
    bot_name_lower = BOT_NAME.lower()
    lowered = text.lower()
    if not lowered.startswith(bot_name_lower):
        return False
    if len(text) == len(BOT_NAME):
        return False
    return text[len(BOT_NAME)] in NAME_TRIGGER_PUNCTUATION


def should_respond(message: discord.Message, me: discord.ClientUser) -> bool:
    content = (message.content or "").strip()
    if not content:
        return False

    # Trigger saat bot di-mention.
    if me.mentioned_in(message):
        return True

    # Trigger saat user memanggil nama bot di awal pesan dengan tanda baca.
    return _has_name_trigger(content)


def normalize_prompt(message: discord.Message, me: discord.ClientUser) -> str:
    text = (message.content or "").strip()

    # Hapus mention bot kalau ada.
    text = text.replace(f"<@{me.id}>", "").replace(f"<@!{me.id}>", "").strip()

    # Hapus nama bot di awal, misalnya "Grace, ..." atau "Grace. ...".
    if _has_name_trigger(text):
        text = text[len(BOT_NAME):].lstrip(" ,:.-")

    return text.strip()


def is_intro_question(prompt: str) -> bool:
    p = prompt.lower()
    keywords = [
        "siapa kamu",
        "siapa dirimu",
        "kamu siapa",
        "siapa anda",
        "siapa dirimu sebenarnya",
        "nama kamu",
        "namamu siapa",
        "kenalan",
        "perkenalkan",
        "ceritakan tentang dirimu",
        "siapa yang membuatmu",
        "siapa pembuatmu",
        "who are you",
        "introduce yourself",
    ]
    return any(k in p for k in keywords)


def _is_limit_message(text: str) -> bool:
    lowered = text.lower()
    keywords = ["limit gemini", "quota", "rate", "resource_exhausted", "429"]
    return any(k in lowered for k in keywords)


def _get_time_period(hour: int) -> str:
    if 0 <= hour < 4:
        return "dini hari"
    if 4 <= hour < 11:
        return "pagi"
    if 11 <= hour < 15:
        return "siang"
    if 15 <= hour < 18:
        return "sore"
    return "malam"


def _get_now_in_timezone() -> tuple[datetime, str]:
    timezone_name = BOT_TIMEZONE
    try:
        now = datetime.now(ZoneInfo(BOT_TIMEZONE))
    except ZoneInfoNotFoundError:
        now = datetime.now().astimezone()
        timezone_name = str(now.tzinfo) if now.tzinfo else "local"
    return now, timezone_name


def _format_datetime_parts() -> tuple[datetime, str, str, str, str, str]:
    weekdays = [
        "Senin",
        "Selasa",
        "Rabu",
        "Kamis",
        "Jumat",
        "Sabtu",
        "Minggu",
    ]
    months = [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ]

    now, timezone_name = _get_now_in_timezone()
    weekday = weekdays[now.weekday()]
    month = months[now.month - 1]
    time_period = _get_time_period(now.hour)
    timestamp = now.strftime("%H:%M:%S")
    tz_abbr = now.tzname() or timezone_name
    return now, timezone_name, weekday, month, time_period, f"{timestamp} {tz_abbr}"


def _get_current_datetime_context() -> str:
    now, timezone_name, weekday, month, time_period, timestamp = _format_datetime_parts()
    return (
        f"Waktu saat ini adalah {weekday}, {now.day} {month} {now.year}, "
        f"pukul {timestamp} ({time_period}) di zona waktu {timezone_name}."
    )


def is_datetime_question(prompt: str) -> bool:
    p = prompt.lower()
    keywords = [
        "jam berapa",
        "pukul berapa",
        "waktu sekarang",
        "jam sekarang",
        "tanggal berapa",
        "tanggal sekarang",
        "hari apa",
        "hari ini hari apa",
        "sekarang hari apa",
        "tanggal dan waktu",
        "waktu saat ini",
        "what time",
        "what date",
        "current time",
        "current date",
        "sekarang dini hari",
        "sekarang pagi",
        "sekarang siang",
        "sekarang sore",
        "sekarang malam",
    ]
    return any(k in p for k in keywords)


def build_datetime_reply() -> str:
    now, _, weekday, month, time_period, timestamp = _format_datetime_parts()
    return (
        f"Sekarang hari {weekday}, {now.day} {month} {now.year}, "
        f"pukul {timestamp}. Saat ini masih {time_period}."
    )


async def ask_ai(user_prompt: str) -> AIResult:
    if not gemini_model:
        return AIResult(
            "GEMINI_API_KEY belum diset. Isi GEMINI_API_KEY di file .env agar Grace bisa menjawab dengan AI.",
            is_error=True,
        )
    if not GEMINI_API_KEY.startswith("AIza"):
        return AIResult(
            "GEMINI_API_KEY tidak valid. Gunakan API key dari Google AI Studio (biasanya berawalan 'AIza').",
            is_error=True,
        )

    try:
        datetime_context = _get_current_datetime_context()
        system_prompt = (
            "Kamu adalah Grace, asisten AI DPNP yang dibuat oleh Brann. "
            "Jawab dengan ramah, natural, jelas, dan tetap to the point. "
            "Gunakan bahasa Indonesia kecuali user meminta bahasa lain. "
            f"{datetime_context} "
            "Jika user menanyakan tanggal, hari, jam, atau waktu sekarang, gunakan konteks waktu tersebut sebagai acuan utama. "
            f"Jika user menanyakan siapa kamu, identitasmu, atau siapa pembuatmu, jawab secara konsisten dengan kalimat ini: {IDENTITY_TEXT}"
        )
        full_prompt = f"{system_prompt}\n\nPertanyaan user: {user_prompt}"
        async with gemini_lock:
            response = await asyncio.to_thread(
                gemini_model.generate_content,
                full_prompt,
                generation_config={"temperature": 0.7},
            )
    except Exception as exc:
        err = str(exc).lower()
        if "api key" in err or "permission" in err or "unauth" in err:
            return AIResult(
                "GEMINI_API_KEY tidak valid atau belum punya izin. Cek key di Google AI Studio.",
                is_error=True,
            )
        if "quota" in err or "rate" in err or "429" in err or "resource_exhausted" in err:
            return AIResult(
                "Limit Gemini API sedang tercapai. Coba lagi beberapa saat lagi.",
                is_private_warning=True,
                is_error=True,
            )
        return AIResult("Gagal menghubungi layanan Gemini. Coba lagi sebentar ya.", is_error=True)

    try:
        answer = getattr(response, "text", "") or ""
    except Exception as exc:
        err = str(exc).lower()
        if "quota" in err or "rate" in err or "429" in err or "resource_exhausted" in err:
            return AIResult(
                "Limit Gemini API sedang tercapai. Coba lagi beberapa saat lagi.",
                is_private_warning=True,
                is_error=True,
            )
        if "safety" in err or "blocked" in err:
            return AIResult("Jawaban dibatasi oleh safety Gemini. Coba ubah pertanyaannya ya.", is_error=True)
        return AIResult("Gemini mengembalikan respons kosong. Coba lagi dengan pertanyaan yang lebih spesifik.", is_error=True)

    answer = answer.strip()
    if not answer:
        return AIResult("Gemini mengembalikan respons kosong. Coba lagi dengan pertanyaan yang lebih spesifik.", is_error=True)
    if len(answer) > 1900:
        answer = answer[:1900] + "\n\n...[jawaban dipotong karena terlalu panjang]"
    return AIResult(answer)


def _allow_request(user_id: int) -> tuple[bool, Optional[str]]:
    now = time.time()
    cutoff = now - 60
    while request_timestamps and request_timestamps[0] < cutoff:
        request_timestamps.popleft()

    user_last = last_user_request.get(user_id, 0.0)
    if now - user_last < USER_COOLDOWN_SEC:
        wait_sec = int(USER_COOLDOWN_SEC - (now - user_last)) + 1
        return False, f"Grace lagi menunggu cooldown. Coba lagi {wait_sec} detik lagi ya."

    if len(request_timestamps) >= GLOBAL_RPM_LIMIT:
        return False, (
            "Grace sedang membatasi request untuk menghindari limit Gemini. "
            "Coba lagi sebentar ya."
        )

    request_timestamps.append(now)
    last_user_request[user_id] = now
    return True, None


async def _send_private_warning(user: discord.abc.User, text: str) -> None:
    try:
        await user.send(text)
    except (discord.Forbidden, discord.HTTPException):
        # Jika DM user tertutup, jangan kirim warning ke channel publik.
        return


@client.event
async def on_ready() -> None:
    assert client.user is not None
    print(f"Login sebagai {client.user} ({client.user.id})")


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    # Jangan merespons pesan broadcast seperti @everyone/@here.
    if message.mention_everyone:
        return

    me = client.user
    if me is None:
        return

    if not should_respond(message, me):
        return

    prompt = normalize_prompt(message, me)

    # Jika user hanya memanggil nama bot tanpa pertanyaan.
    if not prompt:
        await message.reply(IDENTITY_TEXT)
        return

    # Intro wajib ketika user bertanya identitas bot.
    if is_intro_question(prompt):
        await message.reply(IDENTITY_TEXT)
        return

    if is_datetime_question(prompt):
        await message.reply(build_datetime_reply())
        return

    ok, warning_text = _allow_request(message.author.id)
    if not ok:
        await _send_private_warning(message.author, warning_text or "Grace sedang sibuk. Coba lagi ya.")
        return

    try:
        result = await ask_ai(prompt)
    except Exception as exc:
        print(f"Error saat memproses pertanyaan: {exc}")
        result = AIResult("Maaf, terjadi error saat memproses pertanyaan. Coba lagi sebentar ya.", is_error=True)

    # Proteksi tambahan: jika ada pesan limit dari jalur mana pun, paksa kirim private.
    if isinstance(result, str):
        result = AIResult(result)
    if _is_limit_message(result.text):
        result.is_private_warning = True

    if result.is_private_warning or result.is_error:
        await _send_private_warning(message.author, result.text)
        return

    try:
        await message.reply(result.text)
    except discord.HTTPException:
        await _send_private_warning(
            message.author,
            "Maaf, saya gagal mengirim jawaban ke channel. Coba pertanyaan yang lebih singkat.",
        )


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN belum diisi di file .env")

    client.run(DISCORD_TOKEN)
