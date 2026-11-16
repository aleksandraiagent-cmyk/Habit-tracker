"""Материалы для страницы приложения в Google Play: значок 512×512, обложка 1024×500, скриншоты телефона 1080×1920.

    python store/make_store_assets.py      (нужны собранная app/index.html и Playwright)

Скриншоты снимаются с настоящей страницы приложения на примерных данных (как в Android-приложении).
"""
import base64
import datetime as dt
import functools
import http.server
import json
import random
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "google-play"
sys.path.insert(0, str(ROOT / "mobile"))
import make_icons  # noqa: E402


def sample_state():
    """Примерные данные: 5 привычек с историей за 6 недель и 2 лекарства."""
    rnd = random.Random(7)
    today = dt.date.today()
    k = lambda d: d.isoformat()  # noqa: E731
    created = k(today - dt.timedelta(days=42))
    habits = []
    for i, (name, cat, tod, freq, days, rate) in enumerate([
        ("Выпить стакан воды", "health", "morning", "daily", [], 0.92),
        ("Утренняя зарядка", "sport", "morning", "daily", [], 0.75),
        ("Прогулка 30 минут", "sport", "day", "daily", [], 0.7),
        ("Чтение 20 минут", "productivity", "evening", "daily", [], 0.85),
        ("Медитация 10 минут", "mind", "any", "days", [1, 3, 5], 0.9),
    ]):
        hist = {}
        for n in range(1, 43):
            d = today - dt.timedelta(days=n)
            if freq == "days" and (d.isoweekday() % 7) not in days:
                continue
            if n <= 9 - i or rnd.random() < rate:
                hist[k(d)] = True
        if i in (0, 1):
            hist[k(today)] = True
        habits.append({"id": f"h{i}", "name": name, "category": cat, "timeOfDay": tod, "freq": freq, "days": days,
                       "times": 3, "createdAt": created, "archived": False, "history": hist})
    meds = [
        {"id": "m1", "name": "Витамин D", "dose": "1 капсула", "note": "после завтрака", "times": ["09:00"], "days": [],
         "alarm": True, "color": "#fbbf24"},
        {"id": "m2", "name": "Омега-3", "dose": "2 капсулы", "note": "во время еды", "times": ["13:00", "20:00"], "days": [],
         "alarm": True, "color": "#38bdf8"},
    ]
    return {"habits": habits, "theme": "light", "zeroed": True, "meds": meds,
            "medLog": {k(today): {"m1@09:00": "09:04"}}, "alarmsOn": True, "medalSeen": 30}


# Подставляем «Android»: уведомления разрешены, как в установленном приложении
NATIVE_MOCK = """window.androidBridge = {};
(() => { const impl = {
  LocalNotifications: { checkPermissions: async () => ({display: 'granted'}), requestPermissions: async () => ({display: 'granted'}),
    createChannel: async () => ({}), getPending: async () => ({notifications: []}), cancel: async () => ({}), schedule: async () => ({}),
    checkExactNotificationSetting: async () => ({exact_alarm: 'granted'}), changeExactNotificationSetting: async () => ({exact_alarm: 'granted'}) },
  App: { minimizeApp: async () => ({}) }, NativeBiometric: { isAvailable: async () => ({isAvailable: false}) } };
  window.Capacitor = { PluginHeaders: Object.keys(impl).map(n => ({name: n, methods: [...Object.keys(impl[n]).map(m => ({name: m, rtype: 'promise'})), {name: 'addListener'}]})),
    nativePromise: (p, m, o) => Promise.resolve().then(() => impl[p][m](o || {})), nativeCallback: () => Promise.resolve('cb') }; })();"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(directory):
    handler = functools.partial(Quiet, directory=str(directory))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "icon-512.png").write_bytes(make_icons.png(512, 512, make_icons.draw(512, make_icons.BG, 0.62), False))
    print("готово: icon-512.png")

    srv = serve(ROOT / "app")
    url = f"http://127.0.0.1:{srv.server_address[1]}/index.html"
    state = json.dumps(sample_state(), ensure_ascii=False)
    icon64 = base64.b64encode((OUT / "icon-512.png").read_bytes()).decode()
    with sync_playwright() as p:
        br = None
        for ch in ("chrome", "msedge", None):
            try:
                br = p.chromium.launch(channel=ch) if ch else p.chromium.launch()
                break
            except Exception:  # noqa: BLE001
                continue
        ctx = br.new_context(locale="ru-RU", viewport={"width": 360, "height": 640}, device_scale_factor=3, color_scheme="light")
        ctx.add_init_script(NATIVE_MOCK + f"\ntry {{ localStorage.setItem('habit-tracker-v1', {json.dumps(state)}); }} catch (e) {{}}")
        pg = ctx.new_page()
        pg.clock.install(time=dt.datetime.combine(dt.date.today(), dt.time(10, 30)))
        pg.goto(url)
        pg.wait_for_selector("text=Прогресс за сегодня")
        shots = [("Сегодня", "1-segodnya"), ("Таблетки", "2-tabletki"), ("Медали", "3-medali"), ("Статистика", "4-statistika")]
        for tab, name in shots:
            pg.click(f'role=tab[name="{tab}"]')
            pg.clock.run_for(1500)
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(OUT / f"screenshot-{name}.png"))
            print(f"готово: screenshot-{name}.png")
        pg.click('role=tab[name="Сегодня"]')
        dark = br.new_context(locale="ru-RU", viewport={"width": 360, "height": 640}, device_scale_factor=3, color_scheme="dark")
        dark.add_init_script(NATIVE_MOCK + f"\ntry {{ localStorage.setItem('habit-tracker-v1', {json.dumps(state.replace('\"theme\": \"light\"', '\"theme\": \"dark\"'))}); }} catch (e) {{}}")
        dp = dark.new_page()
        dp.clock.install(time=dt.datetime.combine(dt.date.today(), dt.time(21, 15)))
        dp.goto(url)
        dp.wait_for_selector("text=Прогресс за сегодня")
        dp.clock.run_for(1500)
        dp.wait_for_timeout(300)
        dp.screenshot(path=str(OUT / "screenshot-5-temnaya-tema.png"))
        print("готово: screenshot-5-temnaya-tema.png")

        # обложка 1024×500
        fg = br.new_page(viewport={"width": 1024, "height": 500})
        phone = base64.b64encode((OUT / "screenshot-1-segodnya.png").read_bytes()).decode()
        fg.set_content(f"""<html><body style="margin:0;width:1024px;height:500px;overflow:hidden;font-family:-apple-system,Roboto,'Segoe UI',sans-serif;
          background:linear-gradient(120deg,#eef2ff 0%,#f5f5f7 45%,#ecfdf5 100%);position:relative">
          <div style="position:absolute;left:64px;top:110px;width:520px">
            <div style="display:flex;align-items:center;gap:18px">
              <img src="data:image/png;base64,{icon64}" style="width:84px;height:84px;border-radius:20px;box-shadow:0 10px 30px -10px rgba(0,0,0,.35)">
              <div style="font-size:56px;font-weight:800;letter-spacing:-1.5px;color:#18181b">Привычки</div>
            </div>
            <div style="margin-top:26px;font-size:30px;line-height:1.25;font-weight:700;color:#27272a">Серии, медали и напоминания о таблетках</div>
            <div style="margin-top:14px;font-size:20px;line-height:1.4;color:#52525b">Без регистрации и рекламы — всё хранится на вашем телефоне</div>
          </div>
          <img src="data:image/png;base64,{phone}" style="position:absolute;right:70px;top:38px;width:300px;border-radius:28px;
            box-shadow:0 30px 60px -20px rgba(0,0,0,.35),0 0 0 8px #18181b">
        </body></html>""")
        fg.wait_for_timeout(300)
        fg.screenshot(path=str(OUT / "feature-graphic-1024x500.png"))
        print("готово: feature-graphic-1024x500.png")
        br.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
