# PromoBot

Bot Telegram untuk membuat draf promosi dengan Google Gemini dan memublikasikannya ke Threads serta X setelah persetujuan pengguna.

## Fitur
- Pembuatan draf dengan Gemini API
- Interaksi melalui Telegram
- Integrasi publikasi Threads
- Integrasi publikasi X
- Menjalankan aplikasi melalui Docker Compose

## Struktur
- main.py: logika utama bot
- threads_api.py: integrasi Threads
- x_api.py: integrasi X
- exchange_threads.py: utilitas pertukaran token Threads
- requirements.txt: dependensi Python
- Dockerfile: konfigurasi image
- docker-compose.yml: konfigurasi Docker Compose

## Konfigurasi
Simpan kredensial dalam file .env lokal. Jangan unggah API key atau token ke GitHub.

## Menjalankan
Jalankan: sudo docker compose up -d --build

## Keamanan
Gunakan repositori GitHub Private dan periksa file sebelum melakukan commit.
