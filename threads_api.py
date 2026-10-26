import os
import asyncio
import requests

BASE_URL = "https://graph.threads.net/v1.0"


class ThreadsAPIError(Exception):
    pass


def _publish_one(text, reply_to_id=None):
    user_id = os.getenv("THREADS_USER_ID")
    token = os.getenv("THREADS_ACCESS_TOKEN")

    if not user_id or not token:
        raise ThreadsAPIError("Konfigurasi Threads belum tersedia.")

    data = {
        "media_type": "TEXT",
        "text": text,
        "access_token": token,
    }
    if reply_to_id:
        data["reply_to_id"] = reply_to_id

    response = requests.post(
        f"{BASE_URL}/{user_id}/threads", data=data, timeout=30
    )
    try:
        result = response.json()
    except ValueError:
        raise ThreadsAPIError(
            f"Respons pembuatan posting tidak valid (HTTP {response.status_code})."
        )

    if not response.ok or not result.get("id"):
        error = result.get("error", {})
        raise ThreadsAPIError(
            error.get("message", f"HTTP {response.status_code}")
        )

    response = requests.post(
        f"{BASE_URL}/{user_id}/threads_publish",
        data={
            "creation_id": result["id"],
            "access_token": token,
        },
        timeout=30,
    )
    try:
        result = response.json()
    except ValueError:
        raise ThreadsAPIError(
            f"Respons publikasi tidak valid (HTTP {response.status_code})."
        )

    if not response.ok or not result.get("id"):
        error = result.get("error", {})
        raise ThreadsAPIError(
            error.get("message", f"HTTP {response.status_code}")
        )

    return result["id"]


async def post_text(text, reply_to_id=None):
    return await asyncio.to_thread(_publish_one, text, reply_to_id)


async def publish_thread(parts):
    if not isinstance(parts, list) or not parts:
        raise ThreadsAPIError("Isi utas kosong.")

    published_ids = []
    previous_id = None

    for index, part in enumerate(parts, start=1):
        if not isinstance(part, str) or not part.strip():
            raise ThreadsAPIError(f"Bagian ke-{index} kosong.")
        try:
            post_id = await post_text(part.strip(), previous_id)
        except Exception as exc:
            raise ThreadsAPIError(
                f"Bagian ke-{index} gagal; {len(published_ids)} bagian "
                f"sudah terbit. Periksa Threads sebelum mencoba lagi. Detail: {exc}"
            ) from exc

        published_ids.append(post_id)
        previous_id = post_id

    return published_ids
