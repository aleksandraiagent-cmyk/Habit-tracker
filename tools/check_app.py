"""Проверка трекера в настоящем браузере (Playwright): добавление, отметки, серия, сохранение, второе устройство.

    python tools/check_app.py [http://127.0.0.1:8770/] [папка_для_скриншотов]

Приложение должно быть уже запущено. Сценарий работает на пустых данных.
"""
import datetime
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8770/"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "check_out")
OUT.mkdir(parents=True, exist_ok=True)


def state():
    with urllib.request.urlopen(URL + "api/state") as r:
        return json.loads(r.read().decode("utf-8"))


def launch(p):
    for ch in ("msedge", "chrome", None):
        try:
            return p.chromium.launch(channel=ch) if ch else p.chromium.launch()
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("не удалось запустить браузер")


errors = []
with sync_playwright() as p:
    br = launch(p)
    pg = br.new_page(viewport={"width": 1100, "height": 900})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(URL)
    pg.wait_for_selector("text=Начните с первой привычки")

    # готовая привычка с количеством и своя привычка
    pg.click("button.tpl:has-text('Пить воду')")
    pg.click("button[data-a=add]")
    pg.fill("#fName", "Зарядка утром")
    pg.click(".dlg button.chip.emo >> nth=2")
    start = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    pg.fill("#fCreated", start)
    pg.click(".dlg button:has-text('Добавить')")
    pg.wait_for_selector(".card:has-text('Зарядка утром')")

    # отметить «Зарядку» и выпить 8 стаканов
    pg.click(".card:has-text('Зарядка утром') button.check")
    for _ in range(8):
        pg.click(".card:has-text('Пить воду') button[data-a=inc]")
    pg.wait_for_selector("text=2 из 2 выполнено")

    # вчерашний день — для серии
    pg.click("button[data-a=prev]")
    pg.click(".card:has-text('Зарядка утром') button.check")
    pg.wait_for_timeout(1200)

    st = state()
    names = [h["name"] for h in st["habits"]]
    assert names == ["Пить воду", "Зарядка утром"], names
    water = st["habits"][0]["id"]
    assert max(st["done"][water].values()) == 8, st["done"]
    print("Сохранено на сервере, ревизия", st["rev"])

    # второе устройство видит те же данные и вносит изменение
    pg2 = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    pg2.goto(URL)
    pg2.wait_for_selector(".card:has-text('Зарядка утром')")
    pg2.click(".card:has-text('Пить воду') button[data-a=dec]")
    pg2.wait_for_timeout(1200)
    pg2.screenshot(path=str(OUT / "phone-today.png"), full_page=True)

    # первое устройство меняет данные со старой ревизией — конфликт должен разрешиться без потерь
    pg.click("button[data-a=next]")
    pg.click("button[data-a=add]")
    pg.fill("#fName", "Чтение")
    pg.click(".dlg button:has-text('Добавить')")
    pg.wait_for_timeout(1500)
    st = state()
    assert [h["name"] for h in st["habits"]] == ["Пить воду", "Зарядка утром", "Чтение"], st["habits"]
    assert max(st["done"][water].values()) == 7, "изменение со второго устройства потерялось"
    print("Изменения с двух устройств объединены")

    pg.screenshot(path=str(OUT / "today.png"), full_page=True)
    pg.click("nav button[data-v=week]")
    pg.wait_for_selector(".wk table")
    pg.screenshot(path=str(OUT / "week.png"), full_page=True)
    pg.click("nav button[data-v=stats]")
    pg.wait_for_selector(".hcard")
    streak = pg.locator(".hcard:has-text('Зарядка утром') .nums b").first.inner_text()
    assert streak == "2", f"серия должна быть 2, а показано {streak}"
    pg.screenshot(path=str(OUT / "stats.png"), full_page=True)
    pg.click("nav button[data-v=manage]")
    pg.screenshot(path=str(OUT / "manage.png"), full_page=True)

    # после перезагрузки всё на месте
    pg.reload()
    pg.wait_for_selector(".card:has-text('Чтение')")
    br.close()

if errors:
    raise SystemExit("Ошибки JavaScript на странице:\n" + "\n".join(errors))
print("OK: трекер работает, скриншоты в", OUT)
