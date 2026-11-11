"""Трекер привычек — приложение для компьютера (и для iPhone через ту же Wi-Fi сеть).

Запуск:
    python habit_app.py              # открыть отдельным окном (Edge) или в браузере
    python habit_app.py --browser    # открыть во вкладке браузера
    python habit_app.py --window     # отдельное окно (нужен pywebview)
    python habit_app.py --lan        # открыть с телефона в той же Wi-Fi сети
    python habit_app.py --no-browser # только сервер

Нужен только стандартный Python 3.10+, сторонние библиотеки не требуются.
Данные хранятся в файле habits.json (папка habit_data рядом с exe или в %LOCALAPPDATA%\\HabitTracker).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import struct
import sys
import threading
import time
import traceback
import webbrowser
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP_NAME = "Трекер привычек"
FROZEN = bool(getattr(sys, "frozen", False))
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = BASE_DIR / "app"
DEFAULT_PORT = 8770


# ------------------------------------------------------------------ папка данных
def _writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _pick_data_root() -> Path:
    cands = []
    if os.environ.get("HABIT_DATA_DIR"):
        cands.append(Path(os.environ["HABIT_DATA_DIR"]))
    exe_dir = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
    # установленная версия (Program Files) пишет в профиль пользователя, переносная — рядом с exe
    installed = (exe_dir / "unins000.exe").exists()
    home = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    profile = Path(home) / "HabitTracker"
    if installed:
        cands.append(profile)
    cands.append(exe_dir / "habit_data")
    cands.append(profile)
    cands.append(Path(os.environ.get("TEMP", "/tmp")) / "HabitTracker")
    for d in cands:
        if _writable(d):
            return d
    return cands[-1]


DATA_ROOT = _pick_data_root()
DATA_FILE = DATA_ROOT / "habits.json"
BACKUP_DIR = DATA_ROOT / "backups"
LOCK = threading.Lock()


def empty_state() -> dict:
    return {"version": 1, "rev": 0, "habits": [], "done": {}, "settings": {}}


def load_state() -> dict:
    try:
        st = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(st, dict) and isinstance(st.get("habits"), list):
            st.setdefault("done", {})
            st.setdefault("settings", {})
            st.setdefault("rev", 0)
            return st
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        # повреждённый файл не затираем — откладываем в сторону
        bad = DATA_FILE.with_suffix(f".broken-{int(time.time())}.json")
        try:
            shutil.copyfile(DATA_FILE, bad)
            log("Файл данных повреждён, копия:", bad, e)
        except OSError:
            pass
    return empty_state()


def save_state(st: dict):
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, DATA_FILE)
    daily_backup()


def daily_backup():
    """Одна резервная копия в день, храним последние 30."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        dst = BACKUP_DIR / f"habits-{time.strftime('%Y-%m-%d')}.json"
        if not dst.exists():
            shutil.copyfile(DATA_FILE, dst)
            old = sorted(BACKUP_DIR.glob("habits-*.json"))[:-30]
            for f in old:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ значок
def _png(w, h, pixel) -> bytes:
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


_ICONS: dict[int, bytes] = {}


def icon_png(size: int = 180) -> bytes:
    """Значок: сетка 3×3 из клеток-дней, отмеченные — зелёные, и галочка."""
    if size in _ICONS:
        return _ICONS[size]
    bg, on, off = (16, 24, 32), (34, 197, 94), (45, 58, 72)
    pattern = [1, 1, 0, 1, 1, 1, 0, 1, 1]
    cell, gap = size * 0.22, size * 0.07
    x0 = (size - (3 * cell + 2 * gap)) / 2

    def px(x, y):
        for i, v in enumerate(pattern):
            cx, cy = x0 + (i % 3) * (cell + gap), x0 + (i // 3) * (cell + gap)
            if cx <= x < cx + cell and cy <= y < cy + cell:
                return on if v else off
        return bg
    _ICONS[size] = _png(size, size, px)
    return _ICONS[size]


def write_ico(path: Path):
    """Файл .ico для exe и установщика (PNG внутри ICO, Windows Vista+)."""
    sizes = [256, 64, 48, 32, 16]
    pngs = [icon_png(s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    dirs = b""
    for s, p in zip(sizes, pngs):
        dirs += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(p), off)
        off += len(p)
    path.write_bytes(head + dirs + b"".join(pngs))


MANIFEST = {
    "name": APP_NAME, "short_name": "Привычки", "start_url": "./", "display": "standalone",
    "background_color": "#101820", "theme_color": "#101820", "lang": "ru",
    "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}],
}


def page_html() -> bytes:
    html = (APP_DIR / "index.html").read_text(encoding="utf-8")
    return html.replace("<head>", "<head><script>window.LOCAL_APP=true</script>", 1).encode("utf-8")


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "HabitTracker/1.0"

    def log_message(self, fmt, *args):  # тихий режим
        pass

    def _send(self, code, body: bytes, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, page_html(), "text/html; charset=utf-8")
        if path == "/api/status":
            return self._json({"status": "ok", "app": APP_NAME, "data": str(DATA_FILE)})
        if path == "/api/state":
            with LOCK:
                return self._json(load_state())
        if path == "/api/export":
            with LOCK:
                body = json.dumps(load_state(), ensure_ascii=False, indent=1).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition",
                             f'attachment; filename="habits-{time.strftime("%Y-%m-%d")}.json"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        if path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png", "/icon-180.png"):
            return self._send(200, icon_png(180), "image/png")
        if path == "/icon-192.png":
            return self._send(200, icon_png(192), "image/png")
        if path == "/icon-512.png":
            return self._send(200, icon_png(512), "image/png")
        if path == "/favicon.ico":
            return self._send(200, icon_png(32), "image/png")
        if path == "/manifest.webmanifest":
            return self._send(200, json.dumps(MANIFEST, ensure_ascii=False).encode("utf-8"),
                              "application/manifest+json")
        return self._send(404, "Не найдено".encode("utf-8"), "text/plain; charset=utf-8")

    def do_PUT(self):  # noqa: N802
        if urlparse(self.path).path != "/api/state":
            return self._json({"ok": False, "err": "not found"}, 404)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 20_000_000:
                return self._json({"ok": False, "err": "слишком большой файл"}, 413)
            new = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(new, dict) or not isinstance(new.get("habits"), list) \
                    or not isinstance(new.get("done", {}), dict):
                return self._json({"ok": False, "err": "неверный формат данных"}, 400)
        except (ValueError, UnicodeDecodeError):
            return self._json({"ok": False, "err": "неверный JSON"}, 400)
        force = "force=1" in (urlparse(self.path).query or "")
        with LOCK:
            cur = load_state()
            if not force and int(new.get("rev", -1)) != int(cur.get("rev", 0)):
                # данные успели измениться на другом устройстве
                return self._json({"ok": False, "code": "conflict", "state": cur}, 409)
            new["rev"] = int(cur.get("rev", 0)) + 1
            new.setdefault("done", {})
            new.setdefault("settings", {})
            new["version"] = 1
            new["saved"] = int(time.time())
            save_state(new)
        return self._json({"ok": True, "rev": new["rev"]})


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return "127.0.0.1"
    finally:
        s.close()


def _already_running(port: int) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as r:
            return APP_NAME.encode("utf-8") in r.read(1000)
    except Exception:  # noqa: BLE001
        return False


def _edge_path() -> str | None:
    if os.name != "nt":
        return None
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            p = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if p.is_file():
                return str(p)
    return None


def open_ui(url: str, browser: bool = False):
    """Открыть трекер отдельным окном (Edge в режиме приложения), иначе — в браузере по умолчанию."""
    import subprocess
    edge = None if browser else _edge_path()
    if edge:
        try:
            subprocess.Popen([edge, f"--app={url}", "--window-size=1100,860"], close_fds=True)
            return
        except OSError:
            pass
    webbrowser.open(url)


def main():
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--lan", action="store_true", help="доступ с телефона в той же Wi-Fi сети")
    ap.add_argument("--window", action="store_true", help="открыть в отдельном окне (pywebview)")
    ap.add_argument("--no-browser", action="store_true", help="только сервер, ничего не открывать")
    ap.add_argument("--browser", action="store_true", help="открыть во вкладке браузера, а не отдельным окном")
    ap.add_argument("--make-ico", metavar="PATH", help="сохранить значок .ico и выйти (для сборки)")
    args = ap.parse_args()
    if args.make_ico:
        write_ico(Path(args.make_ico))
        print("Значок сохранён:", args.make_ico)
        return
    if not (APP_DIR / "index.html").is_file():
        raise RuntimeError(f"Не найдена страница приложения: {APP_DIR / 'index.html'}")
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    srv = None
    port = args.port
    for port in range(args.port, args.port + 20):
        try:
            srv = ThreadingHTTPServer((host, port), Handler)
            break
        except OSError:
            if port == args.port and not args.lan and _already_running(port):
                url = f"http://127.0.0.1:{port}/"
                print("Трекер уже запущен:", url, "— открываю его.")
                if not args.no_browser:
                    open_ui(url, args.browser)
                return
            print(f"Порт {port} занят, пробую следующий…")
    if srv is None:
        raise RuntimeError("Нет свободного порта. Запустите с --port 9000")
    url = f"http://127.0.0.1:{port}/"
    print("=" * 60)
    print(APP_NAME)
    print("Открыт:", url)
    if args.lan:
        print()
        print("  ДЛЯ iPHONE / ANDROID (телефон в той же Wi-Fi сети):")
        print("  1) Откройте в Safari:", f"http://{lan_ip()}:{port}/")
        print("  2) «Поделиться» → «На экран «Домой»» — появится значок «Привычки».")
        print("  Если Windows спросит про брандмауэр — разрешите доступ в частных сетях.")
        print()
    print("Данные:", DATA_FILE)
    print("Не закрывайте это окно, пока пользуетесь трекером.")
    print("=" * 60, flush=True)
    if args.window:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            import webview  # noqa: PLC0415
            webview.create_window(APP_NAME, url, width=1100, height=820)
            webview.start()
            return
        except ImportError:
            print("pywebview не установлен — открываю браузер.")
            webbrowser.open(url)
            threading.Event().wait()
    else:
        if not args.no_browser:
            threading.Timer(0.5, lambda: open_ui(url, args.browser)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nОстановлено.")


def run():
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        return
    except BaseException:  # noqa: BLE001
        text = traceback.format_exc()
        print("\n" + "=" * 60 + "\nОШИБКА ЗАПУСКА ТРЕКЕРА:\n" + text)
        try:
            with open(DATA_ROOT / "error.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
            print("Текст ошибки сохранён в файл:", DATA_ROOT / "error.log")
        except OSError:
            pass
        print("Пришлите этот текст или скриншот этого окна.\n" + "=" * 60)
        if FROZEN or os.name == "nt":
            try:
                input("Нажмите Enter, чтобы закрыть окно…")
            except EOFError:
                pass
        sys.exit(1)


if __name__ == "__main__":
    run()
