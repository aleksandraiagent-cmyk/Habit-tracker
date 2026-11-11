"""Проверка трекера в настоящем браузере (Playwright). Приложение должно быть запущено на пустых данных.

    python tools/check_app.py [http://127.0.0.1:8770/] [папка_для_скриншотов]

Проверяет: привычки и отметки, медали (без повторной выдачи), меню «⋯», таблетки и будильник
(в том числе когда вкладка «спала» в минуту приёма и перенос «Через 10 мин»), сохранение в файл,
работу с двух устройств одновременно (объединение изменений).
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
TODAY = datetime.date.today()
AT = lambda h, m: datetime.datetime(TODAY.year, TODAY.month, TODAY.day, h, m, 0)  # noqa: E731

results, errors = [], []


def state():
    with urllib.request.urlopen(URL + "api/state") as r:
        return json.loads(r.read().decode("utf-8"))


def step(name, fn):
    try:
        fn()
        results.append(("OK", name, ""))
    except Exception as e:  # noqa: BLE001
        results.append(("FAIL", name, str(e).split("\n")[0][:300]))


def launch(p):
    for ch in ("msedge", "chrome", None):
        try:
            return p.chromium.launch(channel=ch) if ch else p.chromium.launch()
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("не удалось запустить браузер")


def watch(pg, tag):
    pg.on("pageerror", lambda e: errors.append(f"{tag}: {e}"))
    pg.on("console", lambda m: m.type == "error" and "fonts.g" not in m.text and "409" not in m.text and errors.append(f"{tag}: {m.text}"))


def ringing(pg):
    return pg.locator("text=Пора принять").count() > 0


with sync_playwright() as p:
    br = launch(p)
    pg = br.new_context(viewport={"width": 1100, "height": 900}).new_page()
    watch(pg, "компьютер")
    pg.clock.install(time=AT(7, 58))
    pg.goto(URL)
    pg.wait_for_selector("text=Прогресс за сегодня")
    water = 'button[aria-label$=": Выпить стакан воды"]'

    def first_mark():
        pg.click(water)
        pg.wait_for_selector("text=Новая медаль!", timeout=3000)
        pg.screenshot(path=str(OUT / "medal.png"))
        pg.click("text=Отлично!")
    step("отметка привычки и медаль «1 день»", first_mark)

    def medal_once():
        pg.click(water)
        pg.wait_for_timeout(200)
        pg.click(water)
        pg.wait_for_timeout(700)
        assert pg.locator("text=Новая медаль!").count() == 0, "медаль выдана повторно"
    step("медаль не выдаётся повторно после снятия и новой отметки", medal_once)

    def menu_close():
        pg.locator('button[aria-label="Действия"]').nth(1).click()
        pg.wait_for_selector("text=В архив", timeout=2000)
        pg.mouse.click(15, 880)
        pg.wait_for_timeout(300)
        assert pg.locator("text=В архив").count() == 0, "меню не закрылось"
    step("меню «⋯» закрывается кликом мимо", menu_close)

    def add_habit():
        pg.click("button:has-text('Новая привычка')")
        pg.fill("#hname", "Прогулка")
        pg.click("button:has-text('X раз/нед')")
        pg.click("button:has-text('Добавить привычку')")
        pg.wait_for_selector("text=Прогулка", timeout=2000)
    step("добавление привычки «X раз в неделю»", add_habit)

    def add_med():
        pg.click('role=tab[name="Таблетки"]')
        pg.click("button:has-text('Добавить лекарство')")
        pg.fill("#mname", "Витамин D")
        pg.fill('input[aria-label="Время 1"]', "08:00")
        pg.click("button:has-text('Добавить в расписание')")
        pg.wait_for_selector("text=Расписание на сегодня", timeout=2000)
    step("добавление лекарства на 08:00", add_med)

    def alarm_sleep():
        pg.clock.fast_forward("03:00")   # вкладка «спала» с 07:58 до 08:01
        pg.wait_for_timeout(400)
        assert ringing(pg), "будильник не сработал"
        pg.screenshot(path=str(OUT / "alarm.png"))
    step("будильник срабатывает, даже если вкладка спала в 08:00", alarm_sleep)

    def snooze():
        pg.click("button:has-text('Через 10 мин')")
        pg.wait_for_timeout(200)
        assert not ringing(pg)
        for _ in range(64):
            pg.clock.run_for(10_000)
        pg.wait_for_timeout(300)
        assert ringing(pg), "не зазвонил через 10 минут"
        pg.click("button:has-text('Принял(а)')")
        pg.wait_for_selector("text=Принято 1", timeout=2000)
    step("«Через 10 мин» и «Принял(а)»", snooze)

    pg.wait_for_timeout(1500)
    st = state()
    step("данные сохранены в habits.json", lambda: (
        len(st["habits"]) == 5 and st["meds"][0]["name"] == "Витамин D" and st["medalSeen"] == 1) or (_ for _ in ()).throw(
        AssertionError(f"на сервере: {len(st['habits'])} привычек, meds={st.get('meds')}, medalSeen={st.get('medalSeen')}")))

    for tab, name in (("Медали", "medals"), ("Статистика", "stats"), ("Архив", "archive"), ("Сегодня", "today")):
        step(f"вкладка «{tab}»", lambda tab=tab, name=name: (
            pg.click(f'role=tab[name="{tab}"]'), pg.wait_for_timeout(300),
            pg.screenshot(path=str(OUT / f"{name}.png"), full_page=True)))

    # второе устройство (iPhone)
    ph = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True).new_page()
    watch(ph, "телефон")
    ph.goto(URL)
    ph.wait_for_selector("text=Прогулка")

    def two_devices():
        # телефон отмечает «Утреннюю зарядку», компьютер одновременно (со старыми данными) — «Чтение»
        ph.click('button[aria-label$=": Утренняя зарядка"]')
        pg.click('button[aria-label$=": Чтение 20 минут"]')
        ph.wait_for_timeout(2500)
        pg.wait_for_timeout(2500)
        h = {x["name"]: x for x in state()["habits"]}
        k = TODAY.isoformat()
        assert h["Утренняя зарядка"]["history"].get(k) and h["Чтение 20 минут"]["history"].get(k), \
            "одно из одновременных изменений потерялось"
        ph.reload()
        ph.wait_for_selector("text=Прогресс за сегодня")
        assert ph.locator('button[aria-label="Снять отметку: Чтение 20 минут"]').count() == 1, "телефон не видит отметку с компьютера"
        ph.screenshot(path=str(OUT / "phone.png"))
    step("одновременные изменения с двух устройств объединяются", two_devices)

    def persist():
        pg.reload()
        pg.wait_for_selector("text=Прогулка")
        assert pg.locator('button[aria-label="Снять отметку: Утренняя зарядка"]').count() == 1
    step("после перезапуска страницы всё на месте", persist)
    br.close()

bad = [r for r in results if r[0] != "OK"]
for r in results:
    print(f"{r[0]:4} {r[1]}" + (f" — {r[2]}" if r[2] else ""))
if errors:
    print("Ошибки на странице:\n  " + "\n  ".join(sorted(set(errors))))
if bad or errors:
    raise SystemExit(1)
print("OK: трекер работает, скриншоты в", OUT)
