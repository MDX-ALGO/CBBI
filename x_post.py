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
from matplotlib.patches import FancyBboxPatch
from matplotlib.transforms import Affine2D

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


def _draw_v_background(ax, width: float, height: float) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (0, 0),
            width,
            height,
            boxstyle='square,pad=0',
            linewidth=0,
            facecolor='#2f4c6c',
            zorder=0,
        )
    )
    center_x = width / 2
    # Match the site header: thin diagonals that meet in a V at the center.
    spacing = height / 15
    for color, x_scale in (('#26405a', 1.0), ('#395c83', -1.0)):
        for step in range(-24, 48):
            y0 = height + step * spacing
            ax.plot(
                [center_x, center_x + x_scale * width],
                [y0, y0 - height * 0.95],
                color=color,
                linewidth=0.8,
                solid_capstyle='round',
                zorder=1,
            )


def render_confidence_card(
    confidence: float,
    price_date: datetime,
    path: Path | None = None,
) -> bytes:
    score = ceil(confidence * 100)
    day = _heading_date(price_date)
    # Same canvas as the existing CBBI_daily card mockup.
    width, height = 750, 420
    fig = plt.figure(figsize=(width / 100, height / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis('off')
    _draw_v_background(ax, width, height)

    face = '#ffe1c5'
    shadow = '#dd8861'
    muted = '#8fa0b5'
    cx = width / 2

    ax.text(
        cx,
        height - 57,
        'CONFIDENCE WE ARE AT THE PEAK:',
        ha='center',
        va='center',
        fontsize=13,
        fontname='Bahnschrift',
        color=face,
        zorder=3,
    )

    # Anchor is nudged so the drawn glyph center lands near the mockup's 196.5px.
    score_y = height - 221
    stretch = Affine2D().scale(1.2, 1.0).translate(cx * (1 - 1.2), 0) + ax.transData
    for offset in range(10, 0, -1):
        ax.text(
            cx + offset,
            score_y - offset,
            str(score),
            ha='center',
            va='center',
            fontsize=205,
            fontname='Bahnschrift',
            fontweight='bold',
            color=shadow,
            zorder=2,
            transform=stretch,
        )
    ax.text(
        cx,
        score_y,
        str(score),
        ha='center',
        va='center',
        fontsize=205,
        fontname='Bahnschrift',
        fontweight='bold',
        color=face,
        zorder=3,
        transform=stretch,
    )

    ax.text(
        cx,
        height - 351,
        _format_card_date(day),
        ha='center',
        va='center',
        fontsize=28,
        fontname='Bahnschrift',
        fontweight='bold',
        color=face,
        zorder=3,
    )
    ax.text(
        cx,
        22,
        'CBBI.info',
        ha='center',
        va='center',
        fontsize=12,
        fontname='Bahnschrift',
        color=muted,
        zorder=3,
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
