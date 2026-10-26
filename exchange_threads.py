
import getpass
import requests

short_token = getpass.getpass("Token Threads pendek: ")
app_secret = getpass.getpass("Threads App Secret: ")

response = requests.get(
    "https://graph.threads.net/access_token",
    params={
        "grant_type": "th_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token,
    },
    timeout=30,
)

try:
    result = response.json()
except ValueError:
    print("Respons Meta bukan JSON. HTTP:", response.status_code)
    raise SystemExit(1)

if not response.ok or "access_token" not in result:
    print("Pertukaran gagal. HTTP:", response.status_code)
    print("Pesan:", result.get("error", {}).get("message", "Respons tidak terduga"))
    raise SystemExit(1)

print("\nPertukaran berhasil.")
print("Token panjang tersedia; masa berlaku (detik):", result.get("expires_in"))
new_token = result["access_token"]

confirm = input("Simpan token baru ke .env sekarang? Ketik YA: ")
if confirm == "YA":
    from pathlib import Path
    env_path = Path("/project/.env")
    lines = env_path.read_text().splitlines()
    found = False

    for i, line in enumerate(lines):
        if line.startswith("THREADS_ACCESS_TOKEN="):
            lines[i] = "THREADS_ACCESS_TOKEN=" + new_token
            found = True
            break

    if not found:
        print("Variabel THREADS_ACCESS_TOKEN tidak ditemukan; .env tidak diubah.")
        raise SystemExit(1)

    env_path.write_text("\n".join(lines) + "\n")
    env_path.chmod(0o600)
    print("Token baru tersimpan di .env.")
else:
    print("Tidak ada perubahan pada .env.")
