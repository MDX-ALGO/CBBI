"""Serve /app/output over HTTP and refresh it on a UTC schedule.

Railway's domain points at this process. The process stays up, so the cron
schedule on the service must stay empty. A cron run is required to exit, and a
later run is skipped while this server is still running.
"""

import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUTPUT = Path('/app/output')
PORT = int(os.environ.get('PORT', '8080'))
RUN_HOURS = (1, 12)
_job_lock = threading.Lock()


class OutputHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT), **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} {fmt % args}', flush=True)


def run_job():
    with _job_lock:
        print('running main.py', flush=True)
        completed = subprocess.run([sys.executable, 'main.py'], check=False)
        print(f'main.py exited {completed.returncode}', flush=True)


def _next_run(after: datetime) -> datetime:
    candidates = []
    for day_offset in (0, 1):
        day = after.date() + timedelta(days=day_offset)
        for hour in RUN_HOURS:
            candidate = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
            if candidate > after:
                candidates.append(candidate)
    return min(candidates)


def scheduler():
    while True:
        now = datetime.now(UTC)
        target = _next_run(now)
        print(f'next index run at {target.isoformat()}', flush=True)
        time.sleep((target - now).total_seconds())
        run_job()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=run_job, name='initial-run', daemon=True).start()
    threading.Thread(target=scheduler, name='scheduler', daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), OutputHandler)  # noqa: S104
    print(f'listening on 0.0.0.0:{PORT}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
