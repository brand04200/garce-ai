# Grace AI Bot (Discord)

Bot Discord sederhana bernama **Grace**.

Fitur:

- Menjawab saat dipanggil dengan format yang jelas, misalnya `Grace, bantu saya`, `Grace. bantu saya`, atau mention bot.
- Pesan yang hanya berisi `Grace` tidak akan memicu bot.
- Saat ditanya siapa dirinya, bot akan memperkenalkan diri:
  - `Saya adalah Grace, asisten AI DPNP yang dibuat oleh Brann. Saya siap membantu menjawab pertanyaan dan memberikan penjelasan dengan jelas.`
- Mengetahui tanggal, jam, dan periode waktu saat ini secara real-time, termasuk konteks seperti dini hari, pagi, siang, sore, atau malam.
- Menjawab pertanyaan user dengan AI (Gemini API).

## 1) Setup

1. Masuk ke folder project:
   - `cd grace-ai-bot`
2. Buat virtual environment (opsional tapi disarankan):
   - `python -m venv .venv`
   - Windows PowerShell: `.venv\\Scripts\\Activate.ps1`
3. Install dependency:
   - `pip install -r requirements.txt`
4. Copy `.env.example` jadi `.env`, lalu isi token:
   - `DISCORD_TOKEN`
   - `GEMINI_API_KEY`
   - Opsional: `BOT_TIMEZONE` untuk zona waktu bot, default `Asia/Jakarta`

## 2) Jalankan

- `python -m src.bot`

## 2.1) Deploy ke Railway

1. Push project `grace-ai-bot` ke GitHub.
2. Buka Railway lalu buat project baru dari repository GitHub tersebut.
3. Pastikan root directory mengarah ke folder `grace-ai-bot` jika repository berisi lebih dari satu project.
4. Railway akan install dependency dari `requirements.txt` dan menjalankan process dari `Procfile`:
   - `worker: python -m src.bot`
5. Tambahkan environment variables berikut di Railway:
   - `DISCORD_TOKEN`
   - `GEMINI_API_KEY`
   - `BOT_NAME=Grace`
   - `BOT_TIMEZONE=Asia/Jakarta` (opsional)
   - `GLOBAL_RPM_LIMIT=4` (opsional)
   - `USER_COOLDOWN_SEC=8` (opsional)
6. Deploy service, lalu cek tab logs sampai muncul pesan login bot Discord.

Catatan:

- Jangan upload file `.env` ke repository.
- Bot Discord seperti ini lebih cocok dijalankan sebagai `worker`, bukan aplikasi web.
- Jika repository Anda private, hubungkan akun GitHub ke Railway lebih dulu.

## 3) Cara pakai

- Mention bot, atau ketik pesan yang diawali nama bot lalu tanda baca.
- Contoh:
  - `Grace, apa itu machine learning?`
  - `Grace. siapa kamu?`
  - `Grace, sekarang jam berapa?`
  - `Grace, sekarang tanggal berapa?`
  - `@Grace tolong jelaskan Python`

## 4) Dapatkan Gemini API Key

1. Buka Google AI Studio dan buat API key.
2. Masukkan key tersebut ke `GEMINI_API_KEY` pada file `.env`.
