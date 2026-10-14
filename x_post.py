import hashlib
import hmac
import io
import os
import secrets
import time
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path
from urllib.parse import quote

import httpx
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patheffects
from matplotlib.patches import FancyBboxPatch

from ftp_upload import load_dotenv

_API_URL = 'https://api.twitter.com/2/tweets'
_MEDIA_URL = 'https://upload.twitter.com/1.1/media/upload.json'
_DIGIT_EMOJI = {
    '0': '0️⃣',
    '1': '1️⃣',
    '2': '2️⃣',
    '3': '3️⃣',
    '4': '4️⃣',
    '5': '5️⃣',
    '6': '6️⃣',
    '7': '7️⃣',
    '8': '8️⃣',
    '9': '9️⃣',
}


def _percent_encode(value: str) -> str:
    return quote(str(value), safe='~-._')


def _oauth_header(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    access_token_secret: str,
    extra_params: dict[str, str] | None = None,
) -> str:
    oauth = {
        'oauth_consumer_key': consumer_key,
        'oauth_nonce': secrets.token_hex(16),
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': str(int(time.time())),
        'oauth_token': access_token,
        'oauth_version': '1.0',
    }
    params = {**oauth, **(extra_params or {})}
    param_string = '&'.join(
        f'{_percent_encode(key)}={_percent_encode(value)}'
        for key, value in sorted(params.items())
    )
    base_string = '&'.join([
        method.upper(),
        _percent_encode(url),
        _percent_encode(param_string),
    ])
    signing_key = (
        f'{_percent_encode(consumer_secret)}&{_percent_encode(access_token_secret)}'
    )
    digest = hmac.new(
        signing_key.encode(),
        base_string.encode(),
        hashlib.sha1,
    ).digest()
    oauth['oauth_signature'] = b64encode(digest).decode()
    return 'OAuth ' + ', '.join(
        f'{_percent_encode(key)}="{_percent_encode(value)}"'
        for key, value in sorted(oauth.items())
    )


def _should_post_now() -> bool:
    raw = os.getenv('X_POST_UTC_HOURS', '12').strip()
    if not raw:
        return True
    hours = {int(part.strip()) for part in raw.split(',') if part.strip()}
    return datetime.now(UTC).hour in hours


def _credentials() -> tuple[str, str, str, str] | None:
    load_dotenv()
    consumer_key = os.getenv('X_API_KEY', '').strip()
    consumer_secret = os.getenv('X_API_KEY_SECRET', '').strip()
    access_token = os.getenv('X_ACCESS_TOKEN', '').strip()
    access_token_secret = os.getenv('X_ACCESS_TOKEN_SECRET', '').strip()
    if not all((consumer_key, consumer_secret, access_token, access_token_secret)):
        return None
    return consumer_key, consumer_secret, access_token, access_token_secret


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return f'{day}{suffix}'


def _heading_date(price_date: datetime) -> datetime:
    if price_date.tzinfo is None:
        price_date = price_date.replace(tzinfo=UTC)
    return price_date.astimezone(UTC) + timedelta(days=1)


def _format_tweet_date(day: datetime) -> str:
    return f'{day.strftime("%b")} {_ordinal(day.day)}, {day.year}'


def _format_card_date(day: datetime) -> str:
    return f'{day.strftime("%B")} {_ordinal(day.day)}, {day.year}'


def _bold_math(text: str) -> str:
    out: list[str] = []
    for char in text:
        if 'A' <= char <= 'Z':
            out.append(chr(0x1D400 + (ord(char) - ord('A'))))
        elif 'a' <= char <= 'z':
            out.append(chr(0x1D41A + (ord(char) - ord('a'))))
        else:
            out.append(char)
    return ''.join(out)


def _score_emojis(score: int) -> str:
    return ''.join(_DIGIT_EMOJI[digit] for digit in str(score))


def _format_price(price: float) -> str:
    return f'${round(price):,}'


def build_tweet_text(confidence: float, price: float, price_date: datetime) -> str:
    score = ceil(confidence * 100)
    day = _heading_date(price_date)
    return (
        'Daily #CBBI status update:\n'
        f'\n{_bold_math("CONFIDENCE SCORE")}: {_score_emojis(score)}\n'
        f' 🗓 {_format_tweet_date(day)}\n'
        f'\nThe price of #Bitcoin is {_format_price(price)}'
    )


def render_confidence_card(
    confidence: float,
    price_date: datetime,
    path: Path | None = None,
) -> bytes:
    score = ceil(confidence * 100)
    day = _heading_date(price_date)
    width, height = 1080, 1080
    fig = plt.figure(figsize=(width / 100, height / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis('off')

    bg = '#2f4c6c'
    ax.add_patch(
        FancyBboxPatch(
            (0, 0),
            width,
            height,
            boxstyle='square,pad=0',
            linewidth=0,
            facecolor=bg,
        )
    )

    stripe = np.zeros((height, width, 4), dtype=float)
    yy, xx = np.mgrid[0:height, 0:width]
    band = ((xx + yy * 0.55) // 70) % 2 == 0
    stripe[band] = (0.15, 0.25, 0.36, 0.35)
    ax.imshow(stripe, extent=(0, width, 0, height), origin='upper', zorder=0)

    face = '#ffe1c5'
    shadow = '#dd8861'
    ax.text(
        width / 2,
        height * 0.78,
        'CONFIDENCE WE ARE AT THE PEAK:',
        ha='center',
        va='center',
        fontsize=22,
        fontname='Bahnschrift',
        color=face,
        zorder=2,
    )

    score_text = ax.text(
        width / 2 - 8,
        height * 0.48,
        str(score),
        ha='center',
        va='center',
        fontsize=280,
        fontname='Bahnschrift',
        fontweight='bold',
        color=face,
        zorder=2,
    )
    score_text.set_path_effects([
        patheffects.withStroke(linewidth=18, foreground=shadow),
        patheffects.Normal(),
    ])
    for offset in range(1, 9):
        ax.text(
            width / 2 - 8 + offset * 2.2,
            height * 0.48 - offset * 2.2,
            str(score),
            ha='center',
            va='center',
            fontsize=280,
            fontname='Bahnschrift',
            fontweight='bold',
            color=shadow,
            alpha=0.9,
            zorder=1,
        )

    ax.text(
        width / 2,
        height * 0.22,
        _format_card_date(day),
        ha='center',
        va='center',
        fontsize=42,
        fontname='Bahnschrift',
        fontweight='bold',
        color=face,
        zorder=2,
    )
    ax.text(
        width / 2,
        height * 0.08,
        'CBBI.info',
        ha='center',
        va='center',
        fontsize=18,
        fontname='Bahnschrift',
        color='#8fa0b5',
        zorder=2,
    )

    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', dpi=100)
    plt.close(fig)
    png = buffer.getvalue()
    if path is not None:
        path.write_bytes(png)
    return png


def _upload_media(
    png: bytes,
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    access_token_secret: str,
) -> str:
    headers = {
        'Authorization': _oauth_header(
            'POST',
            _MEDIA_URL,
            consumer_key,
            consumer_secret,
            access_token,
            access_token_secret,
        ),
    }
    response = httpx.post(
        _MEDIA_URL,
        headers=headers,
        files={'media': ('cbbi.png', png, 'image/png')},
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f'X media upload failed ({response.status_code}): {response.text[:500]}'
        )
    media_id = response.json().get('media_id_string') or str(
        response.json().get('media_id', '')
    )
    if not media_id:
        raise RuntimeError('X media upload returned no media id')
    return media_id


def post_confidence_tweet(
    confidence: float,
    price: float,
    price_date: datetime,
    *,
    force: bool = False,
) -> bool:
    """
    Post the daily CBBI confidence score to X when credentials are set.
    Returns True when a tweet was created.
    """
    creds = _credentials()
    if creds is None:
        print('X post skipped: API credentials are unset')
        return False
    if not force and not _should_post_now():
        print('X post skipped: outside X_POST_UTC_HOURS')
        return False

    consumer_key, consumer_secret, access_token, access_token_secret = creds
    text = build_tweet_text(confidence, price, price_date)
    png = render_confidence_card(confidence, price_date)
    media_id = _upload_media(
        png,
        consumer_key,
        consumer_secret,
        access_token,
        access_token_secret,
    )
    headers = {
        'Authorization': _oauth_header(
            'POST',
            _API_URL,
            consumer_key,
            consumer_secret,
            access_token,
            access_token_secret,
        ),
        'Content-Type': 'application/json',
    }
    payload = {
        'text': text,
        'media': {'media_ids': [media_id]},
    }
    response = httpx.post(_API_URL, headers=headers, json=payload, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(
            f'X post failed ({response.status_code}): {response.text[:500]}'
        )

    tweet_id = response.json().get('data', {}).get('id', '')
    print(f'Posted CBBI score to X{f" ({tweet_id})" if tweet_id else ""}')
    return True
