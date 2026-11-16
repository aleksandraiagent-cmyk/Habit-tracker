# «Привычки» на iPhone

Приложение для iPhone собирается из той же страницы, что и Android, проект лежит в `mobile/ios`.
GitHub Actions («Сборка iOS») при каждом изменении собирает его на Mac, запускает на симуляторе iPhone
и сохраняет скриншот (артефакт **ios-simulator-check**).

## Почему нельзя просто скачать файл, как APK

Apple разрешает ставить приложения на iPhone только с подписью разработчика. Для этого нужен
**Apple Developer Program — 99 $ в год**. С ним приложение ставится на iPhone через **TestFlight**
(до 10 000 тестировщиков, сборка действует 90 дней), а потом публикуется в App Store.

## Что сделать (один раз)

1. **Вступить в Apple Developer Program**: https://developer.apple.com/programs/enroll/ (Apple ID с двухфакторной
   защитой, оплата, проверка 1–2 дня).
2. **Создать приложение в App Store Connect**: https://appstoreconnect.apple.com → «Приложения» → «+» → «Новое приложение»:
   - Платформа: iOS; Название: `Привычки — трекер и таблетки`; Основной язык: русский
   - Идентификатор пакета (Bundle ID): `app.habittracker.mobile` (если его нет в списке — создайте на
     https://developer.apple.com/account/resources/identifiers, тип App IDs → App, Explicit: `app.habittracker.mobile`)
   - SKU: `privychki`
3. **Создать ключ API**: App Store Connect → «Пользователи и доступ» → «Интеграции» → «App Store Connect API»
   → «+». Название `GitHub`, доступ **«Администратор»** (нужен, чтобы сборка сама создала сертификат подписи).
   Скачайте файл `AuthKey_XXXXXXXXXX.p8` — **скачать его можно только один раз**, сохраните на флешку рядом с ключом Android.
   На той же странице запишите **Issuer ID** и **Key ID**.
4. **Team ID**: https://developer.apple.com/account → «Membership details» → **Team ID** (10 символов).
5. **Добавить 4 секрета** на https://github.com/aleksandraiagent-cmyk/Habit-tracker/settings/secrets/actions:

   | Name | Secret |
   |---|---|
   | `APPLE_TEAM_ID` | Team ID |
   | `ASC_KEY_ID` | Key ID |
   | `ASC_ISSUER_ID` | Issuer ID |
   | `ASC_KEY_P8` | всё содержимое файла `AuthKey_….p8` (открыть Блокнотом, скопировать целиком) |

6. Напишите Claude «ключи Apple добавлены» — он запустит сборку. Она подпишет приложение и отправит его в
   App Store Connect; через 10–30 минут сборка появится в разделе **TestFlight**.

## Поставить на свой iPhone

1. Установите на iPhone приложение **TestFlight** из App Store.
2. App Store Connect → ваше приложение → **TestFlight** → «Внутреннее тестирование» → «+» → добавьте себя (свой Apple ID).
3. На iPhone придёт приглашение — откройте его в TestFlight и нажмите «Установить».

## Публикация в App Store

App Store Connect → приложение → «Распространение» → заполнить страницу (можно взять тексты из `store/README.md`,
скриншоты для iPhone 6.9″ — 1320×2868 Claude сделает отдельно), политика конфиденциальности —
https://github.com/aleksandraiagent-cmyk/Habit-tracker/blob/claude/habit-tracker-app-zpj1he/PRIVACY.md,
«Конфиденциальность приложения» → **«Данные не собираются»**, выбрать сборку из TestFlight → «Отправить на проверку»
(обычно 1–3 дня).

## Особенности iOS

- Напоминания о таблетках приходят уведомлениями и при закрытом приложении. iOS хранит не больше 64 запланированных
  уведомлений, поэтому приложение планирует ближайшие 60 и добавляет следующие каждый раз, когда вы его открываете.
- Данные хранятся только на iPhone. При удалении приложения они удаляются.
