import os
import time
from ftplib import FTP_TLS
from pathlib import Path

_ATTEMPTS = 3
_RETRY_SECONDS = 10


def load_dotenv(path: Path | None = None) -> None:
    env_path = Path('.env') if path is None else path
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, value = stripped.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def upload_json(path: Path) -> None:
    load_dotenv()
    host = os.getenv('FTP_HOST', '').strip()
    username = os.getenv('FTP_USERNAME', '').strip()
    password = os.getenv('FTP_PASSWORD', '')
    if not host or not username or not password:
        print('FTP upload skipped: FTP_HOST, FTP_USERNAME, or FTP_PASSWORD is unset')
        return

    port = int(os.getenv('FTP_PORT', '21'))
    remote_dir = os.getenv('FTP_REMOTE_DIR', '').strip()
    last_error: Exception | None = None

    for attempt in range(1, _ATTEMPTS + 1):
        try:
            _store(path, host, port, username, password, remote_dir)
        except Exception as ex:
            last_error = ex
            print(f'FTP upload attempt {attempt} failed: {ex}')
            if attempt < _ATTEMPTS:
                time.sleep(_RETRY_SECONDS)
            continue
        print(f'Uploaded {path.name} to {host}')
        return

    raise RuntimeError(f'FTP upload failed for {path.name}') from last_error


def _store(
    path: Path,
    host: str,
    port: int,
    username: str,
    password: str,
    remote_dir: str,
) -> None:
    ftps = FTP_TLS()  # noqa: S321
    try:
        ftps.connect(host, port, timeout=60)
        ftps.login(username, password)
        ftps.prot_p()
        if remote_dir:
            ftps.cwd(remote_dir)
        with path.open('rb') as payload:
            ftps.storbinary(f'STOR {path.name}', payload)
    finally:
        try:
            ftps.quit()
        except Exception:
            ftps.close()
