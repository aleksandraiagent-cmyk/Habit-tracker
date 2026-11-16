"""Проверка трекера как приложения для телефона (Playwright): языки, тема, будильники привычек, мелодии,
защита входа (код, рисунок, биометрия), уведомления через мост Capacitor.

    python tools/check_features.py [папка_со_страницей=mobile/www] [папка_для_скриншотов=check_out]

Страница открывается с локального сервера; функции телефона подменяются на уровне моста Capacitor
(window.androidBridge + PluginHeaders + nativePromise), то есть код страницы идёт тем же путём, что на устройстве.
"""
import datetime
import functools
import http.server
import re
import struct
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
WWW = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "mobile" / "www")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "check_out")
OUT.mkdir(parents=True, exist_ok=True)
TODAY = datetime.date.today()
AT = lambda h, m: datetime.datetime(TODAY.year, TODAY.month, TODAY.day, h, m, 0)  # noqa: E731
results, errors = [], []


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(WWW)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/index.html"


def step(name, fn):
    try:
        fn()
        results.append(("OK", name, ""))
    except Exception as e:  # noqa: BLE001
        results.append(("FAIL", name, str(e).split("\n")[0][:300]))


def launch(p):
    for ch in ("chrome", "msedge", None):
        try:
            return p.chromium.launch(channel=ch) if ch else p.chromium.launch()
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("не удалось запустить браузер")


def page(br, locale="ru-RU", init=None, at=None, **kw):
    ctx = br.new_context(locale=locale, viewport={"width": 390, "height": 844}, **kw)
    if init:
        ctx.add_init_script(init)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(f"{locale}: {e}"))
    if at:
        pg.clock.install(time=at)
    return pg


def cyrillic(pg):
    """Русские буквы в видимом тексте и подсказках (кроме названия языка «Русский»)."""
    txt = pg.evaluate("""() => { const a = [document.body.innerText];
      document.querySelectorAll('[aria-label],[title],[placeholder]').forEach(e => a.push(e.getAttribute('aria-label') || '', e.getAttribute('title') || '', e.getAttribute('placeholder') || ''));
      return a.join('\\n'); }""")
    return sorted(set(re.findall(r"[^\n]*[А-Яа-яЁё][^\n]*", txt.replace("Русский", ""))))[:6]


def tab(pg, k):
    pg.click(f'[role=tab][data-tab="{k}"]')
    pg.wait_for_timeout(250)


def wav(path):
    n = 8000
    data = b"".join(struct.pack("<h", int(8000 * ((i // 20) % 2 * 2 - 1))) for i in range(n))
    path.write_bytes(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
                     + b"data" + struct.pack("<I", len(data)) + data)
    return path


NATIVE = """
window.androidBridge = {};
window.__ln = {scheduled: [], channels: [], perms: 0, exact: 'granted', asked: 0};
window.__app = {minimized: 0}; window.__bio = {calls: 0, pass: true}; window.__listeners = {};
(() => {
  const impl = {
    LocalNotifications: {
      checkPermissions: async () => ({display: 'prompt'}),
      requestPermissions: async () => { __ln.perms++; return {display: 'granted'}; },
      createChannel: async c => { __ln.channels.push(c.id); },
      getPending: async () => ({notifications: __ln.scheduled.map(n => ({id: n.id}))}),
      cancel: async ({notifications}) => { const ids = new Set(notifications.map(n => n.id)); __ln.scheduled = __ln.scheduled.filter(n => !ids.has(n.id)); },
      schedule: async ({notifications}) => { __ln.scheduled.push(...notifications.map(n => ({...n, at: new Date(n.schedule.at).toISOString(), hour: new Date(n.schedule.at).getHours()}))); },
      checkExactNotificationSetting: async () => ({exact_alarm: __ln.exact}),
      changeExactNotificationSetting: async () => { __ln.asked++; __ln.exact = 'granted'; return {exact_alarm: 'granted'}; },
    },
    App: { minimizeApp: async () => { __app.minimized++; } },
    NativeBiometric: {
      isAvailable: async () => ({isAvailable: true, biometryType: 3}),
      verifyIdentity: async () => { __bio.calls++; if (!__bio.pass) throw new Error('auth failed'); },
    },
  };
  window.Capacitor = {
    PluginHeaders: Object.keys(impl).map(n => ({name: n, methods: [...Object.keys(impl[n]).map(m => ({name: m, rtype: 'promise'})), {name: 'addListener'}, {name: 'removeListener', rtype: 'promise'}]})),
    nativePromise: (p, m, o) => Promise.resolve().then(() => impl[p][m](o || {})),
    nativeCallback: (p, m, o, cb) => { if (m === 'addListener') __listeners[p + ':' + o.eventName] = cb; return Promise.resolve('cb'); },
  };
})();
"""


def draw(pg, dots):
    """Провести рисунок по точкам сетки 3×3 (0..8)."""
    box = pg.locator("[data-pattern]").bounding_box()
    pt = lambda i: (box["x"] + box["width"] * (44 + 88 * (i % 3)) / 264, box["y"] + box["height"] * (44 + 88 * (i // 3)) / 264)  # noqa: E731
    pg.mouse.move(*pt(dots[0]))
    pg.mouse.down()
    for d in dots[1:]:
        pg.mouse.move(*pt(d), steps=6)
    pg.mouse.up()
    pg.wait_for_timeout(350)


def pin(pg, code):
    for c in code:
        pg.click(f'[data-key="{c}"]')


with sync_playwright() as p:
    srv, URL = serve()
    br = launch(p)

    # ---------- языки ----------
    def lang_check(locale, word, direction):
        pg = page(br, locale)
        pg.goto(URL)
        pg.wait_for_selector(f"text={word}")
        assert pg.evaluate("document.documentElement.dir") == direction, "направление текста"
        bad = []
        for k in ("today", "pills", "medals", "stats", "archive"):
            tab(pg, k)
            bad += cyrillic(pg)
        tab(pg, "today")
        pg.locator('[role=tab][data-tab="today"]').wait_for()
        pg.locator("button.fixed").click()          # новая привычка
        pg.wait_for_selector("[role=dialog]")
        pg.locator("[role=dialog] [role=switch]").click()
        bad += cyrillic(pg)
        pg.keyboard.press("Escape")
        tab(pg, "pills")
        pg.locator("button.fixed").click()          # новое лекарство
        pg.wait_for_selector("[role=dialog]")
        bad += cyrillic(pg)
        pg.keyboard.press("Escape")
        pg.locator("header button").last.click()    # настройки
        pg.wait_for_selector("[data-langs]")
        bad += cyrillic(pg)
        pg.screenshot(path=str(OUT / f"settings-{locale}.png"))
        pg.keyboard.press("Escape")
        pg.locator("footer button").click()         # политика
        pg.wait_for_selector("[role=dialog]")
        bad += cyrillic(pg)
        pg.keyboard.press("Escape")
        tab(pg, "today")
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / f"today-{locale}.png"))
        assert not bad, f"непереведённый текст: {sorted(set(bad))[:5]}"
        pg.context.close()
    step("английский: весь интерфейс переведён", lambda: lang_check("en-US", "Today's progress", "ltr"))
    step("иврит: весь интерфейс переведён, письмо справа налево", lambda: lang_check("he-IL", "ההתקדמות היום", "rtl"))

    # ---------- настройки: язык и тема ----------
    pg = page(br, at=AT(7, 58))
    pg.goto(URL)
    pg.wait_for_selector("text=Прогресс за сегодня")
    settings = lambda: (pg.click('button[aria-label="Настройки"], button[aria-label="Settings"]'), pg.wait_for_selector("[data-langs]"))  # noqa: E731

    def switch_lang():
        settings()
        pg.click('[data-lang="en"]')
        pg.wait_for_selector("text=Settings")
        pg.keyboard.press("Escape")
        pg.wait_for_selector("text=Today's progress")
        pg.reload()
        pg.wait_for_selector("text=Today's progress")     # язык сохранился
        settings()
        pg.click('[data-lang="ru"]')
        pg.wait_for_selector("text=Настройки")
    step("переключение языка в настройках сохраняется", switch_lang)

    def theme():
        dark = lambda: pg.evaluate("document.documentElement.classList.contains('dark')")  # noqa: E731
        pg.click('[data-theme="dark"]')
        assert dark(), "тёмная тема не включилась"
        pg.click('[data-theme="light"]')
        assert not dark(), "светлая тема не включилась"
        pg.click('[data-theme="auto"]')
        assert not dark(), "авто: система светлая"
        pg.emulate_media(color_scheme="dark")
        pg.wait_for_timeout(200)
        assert dark(), "авто: должна следовать за системой"
        pg.emulate_media(color_scheme="light")
    step("тема: тёмная, светлая, автоматическая", theme)

    # ---------- мелодия ----------
    def melody():
        sel = pg.locator('[role=dialog][aria-label="Настройки"] select')
        sel.select_option("chime")
        assert pg.evaluate("JSON.parse(localStorage.getItem('habit-tracker-v1')).sound") == "chime"
        sel.select_option("custom")
        pg.wait_for_selector("text=Файл не выбран")
        pg.set_input_files("[data-melody-file]", str(wav(OUT / "my-song.wav")))
        pg.wait_for_selector("text=my-song.wav")
        pg.keyboard.press("Escape")
        pg.reload()
        pg.wait_for_selector("text=Прогресс за сегодня")
        stored = pg.evaluate("""() => new Promise(res => { const r = indexedDB.open('habit-tracker', 1);
          r.onsuccess = () => { const q = r.result.transaction('files').objectStore('files').get('melody'); q.onsuccess = () => res(q.result ? q.result.size : 0); }; })""")
        assert stored > 1000, f"мелодия не сохранилась на устройстве ({stored})"
        settings()
        pg.wait_for_selector("text=my-song.wav")
        pg.keyboard.press("Escape")
    step("мелодия: выбор сигнала и своя песня из файла", melody)

    # ---------- будильник привычки ----------
    def habit_alarm():
        pg.locator("button.fixed").click()
        pg.fill("#hname", "Прогулка")
        pg.locator("[role=dialog] [role=switch]").click()
        pg.fill("#hremind", "08:00")
        pg.click("button:has-text('Добавить привычку')")
        pg.wait_for_selector("text=Прогулка")
        pg.clock.fast_forward("03:00")
        pg.wait_for_timeout(500)
        dlg = pg.locator("[role=alertdialog]")
        assert dlg.count() == 1 and "Прогулка" in dlg.inner_text() and "08:00" in dlg.inner_text(), "будильник привычки не сработал"
        assert pg.evaluate("document.querySelector('audio') === null")   # своя мелодия играет через Audio() без тега
        pg.screenshot(path=str(OUT / "habit-alarm.png"))
        dlg.locator("button:has-text('Выполнено')").click()
        pg.wait_for_timeout(600)
        if pg.locator("text=Отлично!").count():
            pg.click("text=Отлично!")
        assert pg.locator('button[aria-label="Снять отметку: Прогулка"]').count() == 1, "привычка не отмечена"
    step("будильник привычки: звонит и отмечает выполнение", habit_alarm)

    def edit_habit():
        pg.locator('button[aria-label="Действия"]').first.click()
        pg.click("text=Изменить")
        pg.wait_for_selector('[role=dialog][aria-label="Привычка"]')
        pg.locator("[role=dialog] [role=switch]").click()
        pg.fill("#hremind", "21:30")
        pg.click("[role=dialog] button[type=submit]")
        pg.wait_for_timeout(300)
        assert pg.locator("text=21:30").count() == 1, "время будильника не видно на карточке"
    step("будильник на уже существующей привычке (меню «Изменить»)", edit_habit)

    # ---------- защита входа ----------
    def lock_pin():
        settings()
        pg.click("[role=dialog] >> text=Код")
        pg.wait_for_selector("text=Придумайте код")
        pin(pg, "2580")
        pg.click("text=Далее")
        pg.wait_for_selector("text=Повторите код")
        pin(pg, "2580")
        pg.click("[data-lock-setup] >> text=Сохранить")
        pg.wait_for_selector("text=Включена: код")
        assert "2580" not in pg.evaluate("localStorage.getItem('habit-lock-v1')"), "код хранится в открытом виде"
        pg.reload()
        pg.wait_for_selector("[data-lock-screen]")
        assert pg.locator("text=Прогулка").count() == 0, "данные видны под экраном блокировки"
        pin(pg, "1111")
        pg.wait_for_selector("text=Неверный код")
        pg.screenshot(path=str(OUT / "lock-pin.png"))
        pin(pg, "2580")
        pg.wait_for_selector("text=Прогресс за сегодня")
    step("защита кодом: блокировка, неверный и верный код", lock_pin)

    def lock_pattern():
        settings()
        pg.click("[role=dialog] >> text=Рисунок")
        pg.wait_for_selector("text=Нарисуйте рисунок")
        draw(pg, [0, 1])
        pg.wait_for_selector("[data-lock-setup] >> text=Соедините не меньше 4 точек")
        draw(pg, [0, 1, 2, 5, 8])
        pg.wait_for_selector("text=Повторите рисунок")
        draw(pg, [0, 1, 2, 5, 8])
        pg.wait_for_selector("text=Включена: рисунок")
        pg.reload()
        pg.wait_for_selector("[data-lock-screen]")
        draw(pg, [6, 7, 8, 5])
        pg.wait_for_selector("text=Неверный рисунок")
        pg.screenshot(path=str(OUT / "lock-pattern.png"))
        draw(pg, [0, 1, 2, 5, 8])
        pg.wait_for_selector("text=Прогресс за сегодня")
    step("защита рисунком: блокировка, неверный и верный рисунок", lock_pattern)

    def lock_background():
        pg.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => window.__hid}); window.__hid = true; document.dispatchEvent(new Event('visibilitychange'))")
        pg.clock.fast_forward("01:00")
        pg.evaluate("window.__hid = false; document.dispatchEvent(new Event('visibilitychange'))")
        pg.wait_for_selector("[data-lock-screen]")
        draw(pg, [0, 1, 2, 5, 8])
        pg.wait_for_selector("text=Прогресс за сегодня")
    step("приложение блокируется снова после минуты в фоне", lock_background)

    def lock_off_and_reset():
        settings()
        pg.click("text=Выключить защиту")
        pg.wait_for_selector("[data-lock-status] >> text=Выключена")
        pg.reload()
        pg.wait_for_selector("text=Прогресс за сегодня")
        assert pg.locator("[data-lock-screen]").count() == 0
        settings()
        pg.click("[role=dialog] >> text=Код")
        pin(pg, "1234")
        pg.click("text=Далее")
        pin(pg, "1234")
        pg.click("[data-lock-setup] >> text=Сохранить")
        pg.reload()
        pg.wait_for_selector("[data-lock-screen]")
        pg.click("text=Забыли код?")
        pg.click("text=Сбросить и удалить данные")
        pg.wait_for_selector("text=Прогресс за сегодня")
        assert pg.locator("text=Прогулка").count() == 0 and pg.evaluate("localStorage.getItem('habit-lock-v1')") is None, "сброс не удалил данные"
    step("выключение защиты и сброс при забытом коде", lock_off_and_reset)
    pg.context.close()

    # ---------- приложение на телефоне (мост Capacitor) ----------
    pg = page(br, init=NATIVE, at=AT(7, 0))
    pg.goto(URL)
    pg.wait_for_selector("text=Прогресс за сегодня")
    sched = lambda: (pg.clock.run_for(2000), pg.wait_for_timeout(300), pg.evaluate("__ln.scheduled"))[2]  # noqa: E731

    def native_meds():
        tab(pg, "pills")
        pg.click("button:has-text('Добавить лекарство')")
        pg.fill("#mname", "Витамин D")
        pg.fill('input[aria-label="Время 1"]', "08:00")
        pg.click("button:has-text('Ещё время')")
        pg.fill('input[aria-label="Время 2"]', "20:00")
        pg.click("button:has-text('Добавить в расписание')")
        s = sched()
        assert len(s) == 28, f"уведомлений {len(s)}, ожидалось 28"
        assert pg.evaluate("__ln.channels") == ["meds"] and pg.evaluate("__ln.perms") == 1
        assert s[0]["hour"] == 8 and s[0]["body"] == "08:00 · Витамин D · 1 таблетка" and s[0]["isExactNotification"] is True, s[0]
        assert pg.locator("text=даже если приложение закрыто").count() == 1
    step("телефон: уведомления о лекарствах на 14 дней через мост Capacitor", native_meds)

    def native_habit():
        tab(pg, "today")
        pg.locator("button.fixed").click()
        pg.fill("#hname", "Прогулка")
        pg.locator("[role=dialog] [role=switch]").click()
        pg.fill("#hremind", "18:30")
        pg.click("button:has-text('Добавить привычку')")
        s = sched()
        hb = [n for n in s if "Прогулка" in n["body"]]
        assert len(s) == 42 and len(hb) == 14 and hb[0]["title"] == "Напоминание о привычке" and hb[0]["body"] == "18:30 · Прогулка", (len(s), len(hb))
        pg.click('button[aria-label="Отметить выполнение: Прогулка"]')
        pg.clock.run_for(600)                          # окно «Новая медаль» появляется с задержкой
        pg.wait_for_selector("text=Отлично!")
        pg.click("text=Отлично!")
        s = sched()
        assert len([n for n in s if "Прогулка" in n["body"]]) == 13, "выполненная сегодня привычка всё ещё напоминает"
    step("телефон: уведомления о привычках, выполненная сегодня не напоминает", native_habit)

    def native_exact():
        pg.evaluate("__ln.exact = 'denied'")
        tab(pg, "pills")                               # карточка проверяет разрешение при открытии вкладки
        pg.locator('[role=switch][aria-label="Будильник"]').click()
        sched()
        pg.locator('[role=switch][aria-label="Будильник"]').click()
        s = sched()
        assert s and all(n["isExactNotification"] is False for n in s) and pg.evaluate("__ln.asked") == 0
        tab(pg, "today")
        tab(pg, "pills")
        pg.click("text=Разрешить точные напоминания")
        s = sched()
        assert all(n["isExactNotification"] is True for n in s) and pg.locator("text=Разрешить точные напоминания").count() == 0
    step("телефон: без разрешения — обычные напоминания, кнопка «Разрешить точные»", native_exact)

    def native_back():
        back = lambda: (pg.evaluate("__listeners['App:backButton']()"), pg.wait_for_timeout(300))  # noqa: E731
        pg.click('button[aria-label="Настройки"]')
        pg.wait_for_selector("[data-langs]")
        back()
        assert pg.locator("[data-langs]").count() == 0 and pg.evaluate("__app.minimized") == 0, "«Назад» не закрыл настройки"
        back()
        assert pg.evaluate("__app.minimized") == 1, "«Назад» не свернул приложение"
    step("телефон: кнопка «Назад» закрывает окно, затем сворачивает", native_back)

    def native_bio():
        pg.click('button[aria-label="Настройки"]')
        pg.click("[role=dialog] >> text=Код")
        pin(pg, "4321")
        pg.click("text=Далее")
        pin(pg, "4321")
        pg.click("[data-lock-setup] >> text=Сохранить")
        sw = pg.locator('[role=switch][aria-label="Вход по отпечатку или лицу"]')
        sw.wait_for()
        sw.click()
        pg.wait_for_timeout(300)
        assert pg.evaluate("__bio.calls") == 1 and sw.get_attribute("aria-checked") == "true", "биометрия не включилась"
        pg.screenshot(path=str(OUT / "settings-lock.png"), full_page=True)
        pg.reload()                                   # биометрия проходит — вход без кода
        pg.wait_for_selector("text=Прогресс за сегодня")
        assert pg.evaluate("__bio.calls") == 1
        pg.add_init_script("__bio.pass = false;")     # биометрия не прошла — остаётся код
        pg.reload()
        pg.wait_for_selector("[data-lock-screen]")
        pg.wait_for_selector("text=Войти по биометрии")
        assert pg.locator("text=Прогресс за сегодня").count() == 0
        pin(pg, "4321")
        pg.wait_for_selector("text=Прогресс за сегодня")
    step("телефон: вход по отпечатку или лицу, при отказе — по коду", native_bio)
    pg.context.close()

    # iPhone: не больше 60 запланированных уведомлений, ближайшие
    def ios_limit():
        ios = NATIVE.replace("window.androidBridge = {};", "window.webkit = {messageHandlers: {bridge: {postMessage() {}}}};")
        pg = page(br, init=ios, at=AT(7, 0))
        pg.goto(URL)
        pg.wait_for_selector("text=Прогресс за сегодня")
        assert pg.evaluate("Capacitor.getPlatform()") == "ios"
        tab(pg, "pills")
        pg.click("button:has-text('Добавить лекарство')")
        pg.fill("#mname", "Тест")
        for _ in range(4):
            pg.click("button:has-text('Ещё время')")
        pg.click("button:has-text('Добавить в расписание')")
        pg.clock.run_for(2000)
        pg.wait_for_timeout(300)
        s = pg.evaluate("__ln.scheduled")
        assert len(s) == 60 and s[0]["hour"] == 8, len(s)
        pg.context.close()
    step("iPhone: не больше 60 уведомлений, ближайшие первыми", ios_limit)

    br.close()
    srv.shutdown()

for r in results:
    print(f"{r[0]:4} {r[1]}" + (f" — {r[2]}" if r[2] else ""))
if errors:
    print("Ошибки на странице:\n  " + "\n  ".join(sorted(set(errors))[:10]))
if errors or any(r[0] != "OK" for r in results):
    raise SystemExit(1)
print("OK: все проверки прошли, скриншоты в", OUT)
