import os
import asyncio
import requests
from requests_oauthlib import OAuth1

BASE_URL = "https://api.x.com/2"


class XAPIError(Exception):
    pass


def _publish_one(text, reply_to_id=None):
    api_key = os.getenv("X_API_KEY")
    api_secret = os.getenv("X_API_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        raise XAPIError("Konfigurasi OAuth 1.0 X belum lengkap.")

    auth = OAuth1(
        api_key,
        api_secret,
        access_token,
        access_token_secret,
    )

    payload = {"text": text}
    if reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    try:
        response = requests.post(
            f"{BASE_URL}/tweets",
            json=payload,
            auth=auth,
            timeout=30,
        )
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise XAPIError(f"Gagal menghubungi API X: {exc}") from exc

    if not response.ok or not result.get("data", {}).get("id"):
        error = result.get("detail") or result.get("title") or result.get("errors")
        raise XAPIError(f"API X menolak publikasi: {error or response.status_code}")

    return result["data"]["id"]


async def publish_thread(parts):
    if not isinstance(parts, list) or not parts or len(parts) > 2:
        raise XAPIError("Utas X harus berisi 1 atau 2 posting.")

    published_ids = []
    previous_id = None

    for index, part in enumerate(parts, start=1):
        if not isinstance(part, str) or not part.strip():
            raise XAPIError(f"Bagian ke-{index} kosong.")
        try:
            post_id = await asyncio.to_thread(
                _publish_one, part.strip(), previous_id
            )
        except Exception as exc:
            raise XAPIError(
                f"Bagian ke-{index} gagal; {len(published_ids)} posting "
                f"mungkin sudah terbit. Periksa akun X sebelum mencoba lagi. "
                f"Detail: {exc}"
            ) from exc

        published_ids.append(post_id)
        previous_id = post_id

    return published_ids
