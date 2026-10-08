# Extreme Sudoku — генерация и публикация новых задач

Руководство для владельца проекта: как самостоятельно создать новую партию задач, сертифицировать
их, добавить в production и опубликовать на GitHub Pages.

> **Генерация и сертификация выполняются локальным Python-кодом проекта. ИИ для обычного запуска
> генератора не требуется.**

Для **Easy и Medium** используйте новый [раздел 20](#20-easy-и-medium-phase-10).
Разделы 1–19 описывают исходный сценарий **Extreme**; его сертификация не изменилась.
Общий production validator теперь проверяет смешанную базу: стандартную verification для Easy/Medium
и прежнюю certification для Extreme/Ultra Extreme. Поле `datasetKind` осталось прежним ради совместимости.

Команды написаны для
Windows PowerShell и запускаются **из корня проекта** (`C:\Develop\Extreme Sudoku`). Если какая-то
команда вдруг отвечает ошибкой аргументов — сверьтесь с `python -m generator <команда> --help`:
флаги здесь взяты оттуда, а не из старых ТЗ.

## Содержание

1. [Как это устроено](#1-как-это-устроено)
2. [Требования](#2-требования)
3. [Быстрый запуск новой партии](#3-быстрый-запуск-новой-партии)
4. [production-batch](#4-production-batch)
5. [Seeds и воспроизводимость](#5-seeds-и-воспроизводимость)
6. [Research archive и отчёты](#6-research-archive-и-отчёты)
7. [Как выбирать задачи](#7-как-выбирать-задачи)
8. [Границы сертификации (важно)](#8-границы-сертификации-важно)
9. [Что проверяет certification](#9-что-проверяет-certification)
10. [Ручная сертификация одной задачи](#10-ручная-сертификация-одной-задачи-certify)
11. [production-merge](#11-production-merge)
12. [Безопасный сценарий merge](#12-безопасный-сценарий-merge)
13. [Backup и откат](#13-backup-и-откат)
14. [Validator](#14-validator)
15. [Тесты frontend и сборка](#15-тесты-и-сборка)
16. [Git и GitHub Pages](#16-git-и-github-pages)
17. [Smoke-тест публичного сайта](#17-smoke-тест-публичного-сайта)
18. [Если что-то пошло не так](#18-если-что-то-пошло-не-так)
19. [Полный пример: новая партия и 3 задачи в production](#19-полный-пример-новая-партия-и-3-задачи-в-production)

---

## 1. Как это устроено

```text
Generate → uniqueness → Human Solver → rating → shortlist → certification
        → research archive → production merge → validation → frontend
```

| Этап | Что происходит | Кто делает |
|---|---|---|
| Generate | Случайное полное решение, затем удаление подсказок (clues) | `production-batch` |
| Uniqueness | Exact solver проверяет, что решение единственное (и задача минимальна) | `production-batch` |
| Human Solver + rating | «Человеческие» техники решают задачу; по ним считается рейтинг (Deep) | `production-batch` |
| Shortlist | Кандидаты упорядочиваются по suitability score, берутся лучшие `--shortlist` | `production-batch` |
| Certification | Независимая строгая проверка логической сложности (раздел 9) | `production-batch` (пробная и обычная) |
| Research archive | Все кандидаты и причины отказов складываются в `data/research/phase9_candidates.json` | `production-batch` |
| Production merge | **Новая** свежая сертификация выбранных задач и добавление в базу | `production-merge` |
| Validation | Повторная сертификация всей базы | `scripts/validate_production_database.py` |
| Frontend | Статический сайт играет только задачи из `data/production/puzzles.json` | `web/`, Pages |

`production-batch` **никогда не пишет в production**. В `data/production/puzzles.json` пишет только
`production-merge`.

### Термины: чем отличаются статусы

| Термин | Значение |
|---|---|
| generated candidate | Сгенерированная и (возможно) уникальная задача, ещё без доказательств сложности. Просто строка из 81 цифры. |
| preliminary candidate | Задача с оценкой Human Solver/Deep (`PRELIMINARY`). Это *оценка пути*, а не доказательство: другой логический путь может оказаться проще. |
| `SEARCH_INCONCLUSIVE` («INCONCLUSIVE») | Поиск альтернативных путей упёрся в лимит и не дал ни доказательства, ни опровержения. **Не сертификат.** |
| `CERTIFICATION_TIMEOUT` | Не хватило времени (бюджет по умолчанию 60 с). Также не сертификат; статус нельзя «повысить» вручную. |
| `CERTIFIED_EXTREME` | Подтверждено, что любая реализованная модель логики требует техники уровня Extreme (минимальный обязательный рейтинг ≥ 30). Допускается в production. |
| `CERTIFIED_ULTRA_EXTREME` | То же с обязательным рейтингом ≥ 36. Допускается в production, но на практике сейчас недостижим (раздел 8). |
| production puzzle | Запись в `data/production/puzzles.json`, прошедшая **свежую** сертификацию внутри `production-merge`. Только такие играет сайт. |

Остальные статусы certifier: `REJECTED`, `UNRATED`, `INVALID_PROOF` — в production тоже не допускаются.

---

## 2. Требования

* **Python 3.10+** (проверено на 3.11). Внешних зависимостей у генератора **нет**, `pip install` не нужен.
  Виртуальное окружение не требуется.
* **Node.js 20+** — только для тестов frontend и сборки Pages (`npm` нужен лишь чтобы запустить `npm test`).
* **Playwright** — только для browser-тестов (необязательно):
  ```powershell
  python -m pip install playwright
  python -m playwright install chromium webkit
  ```
* **git** — для коммита и публикации. Утилита `gh` (GitHub CLI) необязательна и может быть не установлена.
* Рабочая директория для всех команд — корень проекта:
  ```powershell
  cd "C:\Develop\Extreme Sudoku"
  python --version
  ```
  Если `python` не найден, используйте `py -3` вместо `python`.

Долгие запуски можно оставлять работать на ночь: `production-batch` ограничен `--runtime-budget`
(по умолчанию 3600 с) и возобновляется после прерывания (раздел 4).

---

## 3. Быстрый запуск новой партии

Минимальный реальный сценарий (подробности и объяснения — в следующих разделах):

```powershell
cd "C:\Develop\Extreme Sudoku"

# 1. Новая партия: генерация -> рейтинг -> shortlist -> сертификация. Production не трогает.
python -m generator production-batch --seeds 9201,9202,9203,9204 --per-seed-count 12 --min-clues 22 --max-clues 30 --target-new 9 --runtime-budget 3600

# 2. Посмотреть итог (печатается в конце запуска, там же путь к отчёту):
#    "Run <run-id>: selected N certified candidates | report ...\batch_report.json | archive ..."
#    Список выбранных ID см. раздел 6.

# 3. Репетиция merge (в production ничего не пишет)
python -m generator production-merge --from-run data/research/phase9/runs/<run-id> --max-new 3 --dry-run

# 4. Настоящий merge -> проверка
python -m generator production-merge --from-run data/research/phase9/runs/<run-id> --max-new 3
python scripts/validate_production_database.py
```

Затем тесты, сборка, commit, push — разделы 15–17.

---

## 4. production-batch

```powershell
python -m generator production-batch [параметры]
```

Команда: генерирует кандидатов, отсеивает слабых, ранжирует оставшихся, сертифицирует shortlist и
записывает **всё** (включая отказы) в research archive. Production-базу она только читает (для проверки
дубликатов).

### Параметры (значения по умолчанию — из текущего кода)

| Параметр | По умолчанию | Назначение |
|---|---|---|
| `--seeds` | — (обязателен, если нет `--reuse-archive`) | Целые seed'ы, через запятую или пробел: `9201,9202` / `9201 9202`. Должны быть различными. |
| `--per-seed-count` (`--target-count`) | `12` | Сколько принятых задач просить у генератора на каждый seed. |
| `--difficulty` | `Extreme` | Целевой класс генератора: `Extreme` или `Ultra Extreme`. |
| `--min-clues` / `--max-clues` | `22` / `30` | Диапазон числа подсказок. |
| `--minimal` / `--no-minimal` | `--minimal` | Минимизировать задачу (нельзя убрать ни одну подсказку без потери уникальности). |
| `--generation-seconds` | `600` | Таймаут генерации **на каждый seed**. |
| `--max-attempts` | `100000` | Потолок попыток генератора на seed. |
| `--probe-seconds` | `15` | Короткий пробный бюджет сертификации перед обычным прогоном (`0` отключает). Пробный TIMEOUT остаётся INCONCLUSIVE, статус не повышается. |
| `--shortlist` | `20` | Сколько лучших (по suitability score) сертифицировать (`0` = всех). |
| `--target-new` | `10` | Остановиться, когда выбрано столько новых certified. |
| `--runtime-budget` | `3600` | Общий лимит времени запуска, секунды. |
| `--run-dir` | `data/research/phase9/runs/<run-id>` | Папка запуска (checkpoints и `batch_report.json`). `<run-id>` — время UTC вида `20261002T205655Z`. |
| `--archive` | `data/research/phase9_candidates.json` | Research archive (накопительный). |
| `--production` | `data/production/puzzles.json` | Только чтение — проверка дубликатов. |
| `--resume` | выкл. | Продолжить прерванный запуск: генерация берётся из checkpoints в `--run-dir`, окончательно обработанные ID пропускаются. |
| `--retry-timeouts` | выкл. | Заново сертифицировать архивные пробные TIMEOUT с обычным бюджетом. |
| `--include-high` | выкл. | Также сертифицировать Deep ≥ 36 (исследования; обычно вне зоны, раздел 8). |
| `--bands` | все доступные | Сертифицировать только эти Deep-рейтинги, например `35` или `32,35` (приоритизация; правила сертификации не меняются). |
| `--min-per-band` | `0` | Зарезервировать N лучших мест shortlist под каждую полосу рейтинга. |
| `--reuse-archive` | выкл. | Заново оценить уже ранжированных, но не завершённых кандидатов архива (например `NOT_SHORTLISTED`) без новой генерации; тогда `--seeds` необязателен. |
| `--no-archive-attempt-rejections` | выкл. | Не записывать в архив каждую отклонённую генератором попытку. |

Прочее: сертификация внутри batch использует `CertificationConfig()` по умолчанию (60 с на кандидата,
подробности — `docs/CERTIFICATION_SPEC.md`). Сертификат, на который ушло дольше 15 с (0,25 × 60 с), не
выбирается (`NOT_SELECTED_SLOW_CERTIFICATE`), чтобы повторная проверка в CI не упиралась в бюджет.

**Коды выхода:** `0` — выбран хотя бы один новый certified, `1` — ни одного, `2` — ошибка параметров/ввода-вывода
или архив занят другим процессом (см. lock ниже).

**Lock.** Рядом с архивом создаётся `<archive>.lock`. Второй запуск на том же архиве завершится кодом 2.
Если процесс был убит и lock остался, удалите файл вручную — **только убедившись**, что batch/merge не запущены.

**Продолжить прерванный запуск:**

```powershell
python -m generator production-batch --seeds 9201,9202,9203,9204 --per-seed-count 12 --min-clues 22 --max-clues 30 --run-dir data/research/phase9/runs/<run-id> --resume
```

Параметры генерации укажите те же, что при исходном запуске (они записаны в `batch_report.json` → `command`/`options`).

### Рекомендуемый пример (аналог Phase 9)

Phase 9 использовала 4 seed'а, около 500 попыток, и дала 13 certified. Для новой партии возьмите **другие**
seed'ы (раздел 5):

```powershell
python -m generator production-batch --seeds 9201,9202,9203,9204 --per-seed-count 12 --min-clues 22 --max-clues 30 --generation-seconds 600 --probe-seconds 15 --shortlist 20 --target-new 9 --runtime-budget 3600 --archive data/research/phase9_candidates.json
```

Что создаётся (запуск идёт десятки минут; на консоль идёт прогресс):

| Путь | Содержимое |
|---|---|
| `data/research/phase9/runs/<run-id>/batch_report.json` | Итоговый отчёт запуска: счётчики, команда, seeds/опции, список `selected` (ID, clues, seed, рейтинг, статус, время). |
| `data/research/phase9/runs/<run-id>/checkpoints/` | Checkpoints генерации для `--resume` (в git не попадает). |
| `data/research/phase9_candidates.json` | Накопительный архив **всех** кандидатов с причинами отказа. |

В конце печатается строка `Run <run-id>: selected N certified candidates | report ... | archive ...`.
`N = 0` (код выхода 1) — нормальный исход, см. [«0 certified»](#0-certified).

### Доработка существующего архива

Уже оценённых кандидатов можно сертифицировать повторно без новой генерации, например полосу 35:

```powershell
python -m generator production-batch --reuse-archive --bands 35 --shortlist 12 --target-new 4 --probe-seconds 15 --runtime-budget 1800
```

---

## 5. Seeds и воспроизводимость

* **Seed** — целое число, из которого детерминированно строится последовательность попыток генератора
  (полное решение → порядок удаления подсказок). Одинаковые seed + одинаковые параметры + одна версия
  кода дают ту же последовательность кандидатов.
* **Не гарантируется:** границы по времени (`--generation-seconds`, `--runtime-budget`, таймауты сертификации)
  зависят от скорости компьютера, поэтому запуск, оборванный по таймеру раньше/позже, может обработать
  другое число попыток. Тайминги и даты в гарантию не входят.
* **Где хранятся seed'ы:** в `batch_report.json` запуска (поля `command`, `options.seeds`, `perSeed`,
  `selected[].seed`) и у каждого кандидата в архиве (`source.seed`, `source.attemptSeed`, `source.attempt`,
  `source.runId`).
* **Как повторить запуск:** запустите ту же команду (она записана в `batch_report.json` → `command`) с теми же
  seed'ами и параметрами, лучше в новую `--run-dir`.
* **Какие seed'ы уже использованы:** посмотрите `options.seeds` в `batch_report.json` предыдущих запусков.
  Seed'ы Phase 9: 9101–9104. Для новой партии берите новые числа; повтор не вреден (дубликаты отсеются
  как `DUPLICATE`), но ничего нового не даст.
* Записывайте seed'ы в commit-сообщение вместе с ID добавленных задач.

---

## 6. Research archive и отчёты

`data/research/phase9_candidates.json` — **исследовательский архив, не production**. В нём лежат:

* certified (в том числе ещё не добавленные в production);
* `PROBE:CERTIFICATION_TIMEOUT` и другие inconclusive;
* отклонённые (`TOO_EASY`, `NOT_UNIQUE`, `HUMAN_UNSOLVED`, `DUPLICATE`, `OUT_OF_CONCLUSIVE_SCOPE`, …) и просто
  не отобранные в shortlist (`NOT_SHORTLISTED`) кандидаты.

**Никогда не копируйте записи архива в production вручную и не пытайтесь добавить «всё подряд».** Единственный
допустимый путь — `production-merge`, который заново сертифицирует каждую задачу. После успешного merge
команда сама помечает кандидата в архиве (`production.merged = true`).

### production-report

```powershell
python -m generator production-report --run-dir data/research/phase9/runs/<run-id> [--archive ФАЙЛ] [--output ФАЙЛ]
```

Пересчитывает счётчики запуска по checkpoints и архиву в **новый** файл
(по умолчанию `<run-dir>/batch_report.recomputed.json`); исходный `batch_report.json` не меняется. Печатает
`generated / unique / rated / shortlisted / certified / inconclusive (timeouts) / selected`. Она **не**
выводит таблицу кандидатов и не имеет фильтров/сортировки. Определения счётчиков: `docs/DATA_FORMAT.md` §57.1.

### Как посмотреть кандидатов (ID, clues, рейтинг, статус, seed)

Выбранные в запуске кандидаты записаны в `batch_report.json` → `selected`. Только чтение, ничего не меняет:

```powershell
@'
import json, sys
run = sys.argv[1]
report = json.load(open(run + "/batch_report.json", encoding="utf-8"))
print("Run", report["runId"], "| total:", report["total"])
for c in report["selected"]:
    print(c["id"], "clues", c["clues"], "rating", c["minimumRequiredRating"], c["status"], "seed", c["seed"], f'{c["elapsed"]}s')
'@ | python - data/research/phase9/runs/<run-id>
```

Все certified кандидаты архива, **ещё не добавленные** в production (включая прошлые запуски):

```powershell
@'
import json
archive = json.load(open("data/research/phase9_candidates.json", encoding="utf-8"))
for c in archive["candidates"]:
    cert = c.get("certification") or {}
    if cert.get("productionEligible") and not (c.get("production") or {}).get("merged"):
        print(c["id"], "clues", c["clues"], "rating", cert.get("minimumRequiredRating"),
              cert.get("status"), "bottlenecks", cert.get("certifiedBottlenecks"),
              "seed", (c.get("source") or {}).get("seed"))
'@ | python -
```

---

## 7. Как выбирать задачи

В production допускаются **только**:

```text
CERTIFIED_EXTREME
CERTIFIED_ULTRA_EXTREME
```

Не допускаются: `PRELIMINARY`, `SEARCH_INCONCLUSIVE`, `CERTIFICATION_TIMEOUT`, `REJECTED`, `UNRATED`,
`INVALID_PROOF`. (Это исполняется кодом: `production-merge` отбросит всё остальное, даже если вы укажете ID.)

Рекомендуемый порядок отбора:

1. Берите только кандидатов со статусом certified из `selected` отчёта или из списка непримердженных (раздел 6).
2. Чередуйте рейтинги: смесь 35 / 30 (и 32, если встретится) разнообразнее, чем одна полоса. `--min-per-band`
   в `production-batch` помогает набрать нужные полосы.
3. Предпочитайте больше `certifiedBottlenecks` (число действительно сложных обязательных мест).
4. Обращайте внимание на предупреждения diversity (`warnings`, `NEAR_DUPLICATE`): похожие задачи merge отсеет сам.
5. Берите небольшие порции (3–5 задач) и проверяйте каждую.

**Количество подсказок само по себе не делает задачу лучше или хуже.** Задача с 28 подсказками и подтверждённым
рейтингом 35 ценнее задачи с 22 подсказками и рейтингом 30. Главный критерий — подтверждённая логическая
сложность.

---

## 8. Границы сертификации (важно)

Состояние после Phase 7.1 / Phase 9:

* Рейтинг 30 (AIC / XY-Chain и др.) и **35 (Grouped AIC) сертифицируются успешно**. Полоса 32 (Nice Loop) в
  практике не встречалась.
* Область **рейтинга ≥ 36** (ALS-XZ и тяжелее; это порог Ultra Extreme) сейчас практически всегда даёт
  `SEARCH_INCONCLUSIVE` / `CERTIFICATION_TIMEOUT`: доказательство «нет более простого пути» для порога ≥ 36
  в рамках текущих бюджетов не завершается. Такие кандидаты `production-batch` по умолчанию пропускает как
  `OUT_OF_CONCLUSIVE_SCOPE` (включить для исследований можно `--include-high`).
* Следовательно, `CERTIFIED_ULTRA_EXTREME` в этой версии практически недостижим.
* **Отсутствие сертификата не означает, что задача простая** — только что система не смогла доказать уровень
  в рамках бюджета. И наоборот, `INCONCLUSIVE` нельзя считать Certified и нельзя добавлять в production.
* Бюджеты (`time_budget` и др.) и модель технико-логики в `CertificationConfig` ослаблять нельзя: production
  намеренно использует единую политику по умолчанию.
* Ultra Extreme требует нового проверенного метода негативного доказательства; это отдельная исследовательская
  фаза (см. «Recommendation» в `docs/PHASE9_CONTENT_EXPANSION_REPORT.md`).

Точные формулировки: `docs/CERTIFICATION_SPEC.md`.

---

## 9. Что проверяет certification

Для каждой задачи `certify_puzzle` (в `production-batch` и повторно в `production-merge`) выполняет:

1. **Fresh validation** — формат, цифры, соответствие `solution`; ничего не берётся из кэша или старых меток.
2. **Uniqueness** — решение единственное.
3. **Minimality metadata** — минимальность подсказок (при включённом `require_minimal`/метаданных).
4. **Human Solver replay** — детерминированное решение человеческими техниками, повторяемость пути.
5. **LogicStep proof validation** — каждый шаг независимо проверяется (вывод логически следует из состояния).
6. **Alternative-path search** — поиск более простых альтернативных путей; Stuck-State Superset Lemma даёт
   негативное доказательство «ниже этого уровня задача не решается».
7. **Final certification status** — `CERTIFIED_*`, либо inconclusive/timeout/rejected с причиной.

Human Solver **не использует** известное решение или Exact Solver как логический oracle: DFS применяется только
для проверки уникальности. Это проверяется тестами (ловушки Exact API, запрет импорта).

---

## 10. Ручная сертификация одной задачи (`certify`)

Режим есть: `certify --puzzle <81 цифр>` (опционально `--solution`, `--puzzle-id`) или
`certify --input <файл> --puzzle-id <ID>`. `--fresh` существует и явно включает fresh-режим (перед production-
экспортом он включён всегда).

> ⚠️ **Опасность.** По умолчанию `certify` пишет в `--output data/production/puzzles.json` (и в
> `--research-output data/candidates.json`, `--reports-dir reports/certification`) и **заменяет** выбранный
> output. Всегда задавайте `--output`, `--research-output` и `--reports-dir` явно в безопасное место.
> Для добавления задач в production используйте `production-merge`, а не `certify`.

Безопасный пример (строка задачи берётся из архива, scratch-папка вне проекта):

```powershell
$tmp = Join-Path $env:TEMP "es-certify"; New-Item -ItemType Directory -Force $tmp | Out-Null
python -m generator certify --puzzle <81-значная-строка> --puzzle-id <ID> --fresh --output "$tmp\prod.json" --research-output "$tmp\research.json" --reports-dir "$tmp\reports"
```

Коды выхода: `0` — есть certified, `1` — нет certified, `2` — ошибка параметров/ввода-вывода. Переопределения
бюджетов (`--time-budget`, `--node-budget`, …) годятся для *исследований*; их результат в production не
переносится, потому что `production-merge` всё равно сертифицирует заново с настройками по умолчанию.
Чтобы убедиться, что ID в production корректен, используйте validator (раздел 14).

---

## 11. production-merge

> **`production-merge` изменяет `data/production/puzzles.json`.** Это единственная команда, которая это делает
> (кроме `certify` с дефолтным `--output`, см. предупреждение выше).

```powershell
python -m generator production-merge [параметры]
```

| Параметр | По умолчанию | Назначение |
|---|---|---|
| `--production` | `data/production/puzzles.json` | Целевая база. |
| `--archive` | `data/research/phase9_candidates.json` (если нет `--from-run`) | Архив(ы) — источник кандидатов; можно повторять. |
| `--from-run` | — | Папка(ы) запуска: берутся `selected` из `batch_report.json`; можно повторять. |
| `--ids` | — | Только эти ID, **в указанном порядке** (пробелы между ID). Неизвестный ID — ошибка. |
| `--target-total N` | — | Остановиться, когда в базе станет N задач (N − текущее число = сколько добавить). |
| `--max-new N` | — | Добавить не более N новых (взаимоисключается с `--target-total`). |
| `--backup-dir` | `data/research/phase9/backups` | Куда класть backup (обязательно вне папки production). |
| `--report` | `data/research/phase9/merges/merge-<время>.json` | Отчёт merge. |
| `--dry-run` | выкл. | Сертифицировать и проверить дубликаты, **но не писать в production и не делать backup**. |

Без `--ids` порядок кандидатов выбирается автоматически (сначала финально certified `selected`, быстрые
сертификаты раньше, рейтинги чередуются).

Что делает команда:

1. **Проверяет всю существующую базу** (fresh re-certification). Если она невалидна — merge отменяется.
2. Существующие записи сохраняются **без изменений**.
3. Каждого нового кандидата **сертифицирует заново** с `CertificationConfig()` по умолчанию. Статусы из архива
   используются только для порядка. Допускаются только `CERTIFIED_EXTREME` / `CERTIFIED_ULTRA_EXTREME`.
4. **Duplicate checks**: точная строка, ID, то же решение, маска clues, symmetry fingerprint; ID должен совпадать
   с content-hash. Дубликаты и «похожие» пропускаются (`skipped` в отчёте с причиной).
5. Медленные сертификаты (> 15 с) пропускаются (`NOT_SELECTED_SLOW_CERTIFICATE`).
6. Делает backup, пишет через temp-файл и атомарную замену, перепроверяет результат (раздел 13).

**Коды выхода:** `0` — добавлено хотя бы одно; `1` — ничего не добавлено / нечего делать; `2` — ошибка
(база не изменена либо восстановлена из backup; также если архив занят lock'ом); `3` — production уже записана
и успешно перепроверена, но не удалось пометить кандидатов в архиве (`archiveUpdate: "failed: …"` в отчёте):
базу трогать не нужно, повторный merge отсеет эти ID как `DUPLICATE`.

`--dry-run` всё равно записывает отчёт `data/research/phase9/merges/merge-<время>.dry-run.json` (в git
игнорируется); production, backup и архив не меняются. Dry-run долгий, так как выполняет настоящую сертификацию.

---

## 12. Безопасный сценарий merge

```text
1. report            — посмотреть кандидатов (раздел 6)
2. выбрать IDs       — только certified, смесь рейтингов (раздел 7)
3. dry-run           — production-merge ... --dry-run
4. проверить результат — merged/skipped в выводе и в отчёте *.dry-run.json
5. real merge        — та же команда без --dry-run
6. validator         — python scripts/validate_production_database.py
7. git diff          — изменился только data/production/puzzles.json и ожидаемые файлы
```

Пример с явными ID (замените на свои):

```powershell
python -m generator production-merge --archive data/research/phase9_candidates.json --ids puzzle-AAAA puzzle-BBBB puzzle-CCCC --dry-run
python -m generator production-merge --archive data/research/phase9_candidates.json --ids puzzle-AAAA puzzle-BBBB puzzle-CCCC
python scripts/validate_production_database.py
```

В выводе `Merged N new | skipped M | total T | written True | backup ... | report ...`: убедитесь, что `N` равно
ожидаемому, `skipped` не содержит неожиданных причин, а `total` = старое число + N.

---

## 13. Backup и откат

Всё делается автоматически; **не редактируйте JSON вручную**.

* Перед записью создаётся побайтовая копия текущей базы в `data/research/phase9/backups/puzzles-<время>-<sha256[:12]>.json`
  (папка вне `data/production/`, в git игнорируется) и проверяется по SHA-256.
* Перед самой записью проверяется, что файл не изменился с момента чтения.
* Запись — во временный файл в той же папке, `fsync`, чтение обратно и атомарная замена (`os.replace`).
* Перед заменой проверяется схема, что новые данные = записи этого запуска, что **все** существующие записи не
  изменились и что `stats` согласована.
* После записи база валидируется ещё раз; если не прошла — backup восстанавливается и сверяется по хэшу
  (`Production merge failed (backup restored)`).
* Backup-файлы нужно хранить локально: это ваш ручной откат (скопировать файл поверх
  `data/production/puzzles.json`, затем запустить validator). Если база уже закоммичена, откатывать можно и
  через git.

---

## 14. Validator

```powershell
python scripts/validate_production_database.py
python scripts/validate_production_database.py путь\к\файлу.json   # другой файл
```

Скрипт **только читает**. Для каждой записи выполняется свежая повторная сертификация и сравниваются все
метаданные; проверяются схема (`schemaVersion`, `datasetKind`), ID, отсутствие дубликатов, строки
`puzzle`/`solution`, согласованность clues, уникальность/минимальность, статус `CERTIFIED_*` и
production-eligibility, а также `stats`. Пустая база считается валидной.

Выход: `0` — `OK production database …: N certified puzzle(s) re-validated in X s`; `1` — `INVALID …` (базу не
публиковать); `2` — файл нечитаем. Время растёт с числом задач (сертификация каждой записи).

Проверка количества задач после merge: число `N` в строке `OK …` валидатора; либо
`total` в выводе merge; либо:

```powershell
python -c "import json; d=json.load(open('data/production/puzzles.json',encoding='utf-8')); print(len(d['puzzles']), d['stats'])"
```

---

## 15. Тесты и сборка

Из корня проекта:

```powershell
# Python-тесты генератора/сертификации (несколько минут; число тестов меняется — смотрите на итог OK)
python -m unittest discover -s generator/tests

# Frontend unit-тесты
cd web; npm test; cd ..

# Browser, E2E и responsive (нужен Playwright, см. раздел 2). Артефакты — web/artifacts/
python web/tests/browser_regression.py
#   варианты: --browser chromium|webkit|all, --artifacts ПАПКА, --production-db ФАЙЛ

# Сборка Pages: web/ + data/production/puzzles.json -> dist/
node scripts/build_pages.mjs

# Просмотр собранного сайта как на Pages
python -m http.server 8000 --directory dist      # http://localhost:8000/

# Локальный dev-режим (без сборки)
python -m http.server 8000                       # http://localhost:8000/web/
```

Число тестов не фиксируется — важен итог `OK` без failures/errors.

`build_pages.mjs` — единственный способ получить опубликованные данные: из `dist/data/production/puzzles.json`
удаляются тяжёлые `certification.evidence/config`, к URL базы добавляется content-hash (`puzzles.json?v=…`),
чтобы кэш Pages не отдавал старый JSON. `dist/` в git не попадает.

---

## 16. Git и GitHub Pages

Не используйте `git add .` — можно захватить временные/служебные файлы.

```powershell
git status
git diff --stat
git diff data/production/puzzles.json
```

Обычно в commit попадают:

* `data/production/puzzles.json` — главная база;
* `data/research/phase9_candidates.json` — архив с пометками `production.merged`;
* `data/research/phase9/runs/<run-id>/batch_report.json` — отчёт запуска (с seed'ами);
* `data/research/phase9/merges/merge-<время>.json` — отчёт настоящего merge (не `*.dry-run.json`).

Не попадают (игнорируются или не нужны): `data/research/phase9/backups/`, `…/runs/*/checkpoints/`, `*.lock`,
`*.dry-run.json`, `dist/`, `web/artifacts/` (если не хотите обновлять скриншоты).

```powershell
git add data/production/puzzles.json data/research/phase9_candidates.json
git add data/research/phase9/runs/<run-id>/batch_report.json data/research/phase9/merges/merge-<время>.json
git status
git commit -m "Add 3 certified Extreme puzzles (seeds 9201-9204)"
git push origin main
```

### GitHub Pages

* Генерация и сертификация в Pages CI **не выполняются**. Workflow `.github/workflows/pages.yml` публикует
  уже готовую `data/production/puzzles.json`.
* Запускается на push в `main` или вручную: frontend tests → `validate_production_database.py` (при ошибке сборка
  падает) → `node scripts/build_pages.mjs` → deploy.
* После push проверьте workflow «Deploy to GitHub Pages» на
  https://github.com/shell322dll/extreme-sudoku/actions (должен завершиться success; обычно меньше минуты, но
  валидация растёт с размером базы).
* Если установлен GitHub CLI (`gh`; на машине разработки он может отсутствовать):
  ```powershell
  gh run list --workflow pages.yml --limit 3
  gh run view <run-id>
  gh run watch <run-id>
  ```
* Сайт: https://shell322dll.github.io/extreme-sudoku/

---

## 17. Smoke-тест публичного сайта

1. Сайт открывается, задача отображается.
2. Число задач в опубликованном JSON соответствует ожидаемому:
   ```powershell
   (Invoke-RestMethod "https://shell322dll.github.io/extreme-sudoku/data/production/puzzles.json").puzzles.Count
   ```
3. **New Game** переключает на другие задачи (не повторяет текущую, пока есть другие нерешённые).
4. **Puzzle Details** (ID, clues, рейтинг, сложность) соответствуют данным задачи.
5. Консоль браузера (F12) без ошибок; нет сообщения «Не удалось загрузить базу Sudoku».
6. При необходимости откройте сайт в окне инкогнито, чтобы исключить кэш.

---

## 18. Если что-то пошло не так

### `0 certified`
Код выхода 1, «selected 0». Generation batch **не гарантирует** получение Extreme: большинство кандидатов
отсеивается как `TOO_EASY`. Запустите с другими seed'ами, увеличьте `--per-seed-count`/`--runtime-budget`, либо
используйте `--reuse-archive`. Ослаблять сертификацию не нужно.

### `INCONCLUSIVE`
Не добавлять в production. Статус `SEARCH_INCONCLUSIVE` означает, что уровень не доказан. Задачи Deep ≥ 36 —
ожидаемый случай (раздел 8).

### `CERTIFICATION_TIMEOUT`
Не повышать статус вручную. Можно повторить с обычным бюджетом: `production-batch --reuse-archive --retry-timeouts`.
Если и тогда timeout — задача для production не годится.

### Duplicate ID / puzzle
`production-merge` пропустит кандидата с причиной `DUPLICATE`/`NEAR_DUPLICATE`. Не делайте merge «в обход»
и не правьте ID вручную (ID — hash от строки задачи). Если ID дублируется внутри уже существующей базы —
validator выдаст ошибку; публикацию остановите.

### Validator failed
`INVALID production database …` (код 1) — **production не публиковать**. Не пушьте. Восстановите базу из
`git restore data/production/puzzles.json` (если ещё не закоммичена) либо из backup
(`data/research/phase9/backups/`), затем снова запустите validator. Разберите причину по тексту ошибки.

### Pages показывает старый JSON
1. Проверьте, что workflow завершился success (раздел 16) и последний push именно ваш.
2. Сравните URL базы: в `dist` он содержит `puzzles.json?v=<hash>`; хэш меняется при изменении данных.
3. Обновите страницу без кэша (Ctrl+F5) или откройте в окне инкогнито.
4. Проверьте число задач в опубликованном JSON (раздел 17).

### Generation прервана
Повторите команду с `--run-dir data/research/phase9/runs/<run-id> --resume` и теми же параметрами генерации
(раздел 4). Если появилась ошибка lock — удалите `<archive>.lock` вручную, убедившись, что процесс не запущен.

### `Production merge failed … (backup restored)`
База восстановлена из backup (код 2). Перезапустите validator, убедитесь, что `git diff` пуст, разберите
причину (текст ошибки), затем повторите dry-run.

### Код выхода 3 у `production-merge`
Production записана и валидна, ошибка только в пометке архива. Базу не трогайте; см. `archiveUpdate` в отчёте.

---

## 19. Полный пример: новая партия и 3 задачи в production

Подставьте свои `<run-id>`, ID и время отчёта.

```powershell
# 0. Чистое состояние и текущая база
cd "C:\Develop\Extreme Sudoku"
git status
python scripts/validate_production_database.py

# 1. Generation + certification (production не трогается). Результат: <run-id> в последней строке вывода
python -m generator production-batch --seeds 9201,9202,9203,9204 --per-seed-count 12 --min-clues 22 --max-clues 30 --generation-seconds 600 --probe-seconds 15 --shortlist 20 --target-new 9 --runtime-budget 3600

# 2. Report: пересчёт счётчиков + список выбранных
python -m generator production-report --run-dir data/research/phase9/runs/<run-id>
@'
import json, sys
r = json.load(open(sys.argv[1] + "/batch_report.json", encoding="utf-8"))
for c in r["selected"]:
    print(c["id"], "clues", c["clues"], "rating", c["minimumRequiredRating"], c["status"], "seed", c["seed"])
'@ | python - data/research/phase9/runs/<run-id>

# 3. Selection: выбрать 3 ID (смесь рейтингов), записать их

# 4. Dry-run
python -m generator production-merge --from-run data/research/phase9/runs/<run-id> --ids puzzle-AAAA puzzle-BBBB puzzle-CCCC --dry-run

# 5. Настоящий merge (меняет data/production/puzzles.json, делает backup)
python -m generator production-merge --from-run data/research/phase9/runs/<run-id> --ids puzzle-AAAA puzzle-BBBB puzzle-CCCC

# 6. Validator (должно быть OK и +3 к прежнему числу)
python scripts/validate_production_database.py

# 7. Тесты и сборка
cd web; npm test; cd ..
python web/tests/browser_regression.py
node scripts/build_pages.mjs

# 8. git diff
git status
git diff --stat

# 9. Commit и push (только нужные файлы)
git add data/production/puzzles.json data/research/phase9_candidates.json
git add data/research/phase9/runs/<run-id>/batch_report.json data/research/phase9/merges/merge-<время>.json
git commit -m "Add 3 certified Extreme puzzles (seeds 9201-9204)"
git push origin main

# 10. Pages: проверить workflow (gh, если установлен) и сайт
gh run list --workflow pages.yml --limit 3
Start-Process "https://shell322dll.github.io/extreme-sudoku/"
```

После деплоя выполните smoke-тест из раздела 17.

## 20. Easy и Medium (Phase 10)

Используется тот же `PuzzleGenerator`: готовое решение → удаление clues → uniqueness → Human Solver
→ rating/filter. Затем выбранные кандидаты проходят свежий Deep-анализ, threshold solve,
независимую проверку logical proofs и детерминированный replay. Guessing и human backtracking запрещены.
Extreme alternative-path/minimax certification здесь не запускается, статус — `verification.status=VERIFIED`.

Классификация зависит от `hardest_required_rating`, а не clues или агрегированного `rating`:
Easy `[0, 2)` (техники до 1.2), Medium `[2, 7)` (до 5.2). Это lowest successful tested threshold
существующего bounded deterministic solver, а не доказательство минимальности по всем логическим путям.

Воспроизводимые команды Phase 10, из корня проекта (папки запуска должны быть новыми):

```powershell
python -m generator production-batch --difficulty Easy --seeds 10101,10102,10103 --per-seed-count 6 --target-new 9 --min-clues 20 --max-clues 45 --no-minimal --max-attempts 200 --generation-seconds 180 --runtime-budget 540 --run-dir data/research/phase10/easy-new
python -m generator production-batch --difficulty Medium --seeds 10201,10202,10203 --per-seed-count 6 --target-new 9 --min-clues 20 --max-clues 45 --no-minimal --max-attempts 250 --generation-seconds 240 --runtime-budget 720 --run-dir data/research/phase10/medium-new
```

Диапазон clues широкий и служит фильтром генератора. Он не присваивает сложность.
Для другой партии меняйте seeds и `--run-dir`. Путь по умолчанию — `data/research/phase10/runs/<run-id>`.
Результат: `batch_report.json` с `selected`, `verifiedUnselected`, `rejected`, seeds, attempts,
runtime, yield и diversity. Это research report, не production database. Standard batch не поддерживает
Extreme-опции resume/reuse/bands/retry-timeouts; существующий отчёт не перезаписывается.
Exit `0`: выбран полный `--target-new`; `1`: неполный набор; `2`: ошибка. Уже сохранённые ранние
Phase 10 отчёты могут не иметь поля `complete`: полноту проверяйте по длине `selected` и `targetNew`.

Проверьте все selected IDs, сложности, clues, rating, hardestTechnique, solutionSteps, seeds и verification.
`production-merge` принимает несколько `--from-run`, выполняет fresh verification каждой новой задачи,
отсекает дубликаты также относительно прежних Extreme и сохраняет прежние записи без изменений.

```powershell
python -m generator production-merge --from-run data/research/phase10/easy-new --from-run data/research/phase10/medium-new --max-new 18 --dry-run --report reports/phase10/new-dry-run.json
# После проверки dry-run и требуемого в вашей рабочей сессии подтверждения:
python -m generator production-merge --from-run data/research/phase10/easy-new --from-run data/research/phase10/medium-new --max-new 18
python scripts/validate_production_database.py
python -m unittest discover -s generator/tests
cd web; npm test; cd ..
python web/tests/browser_regression.py --artifacts reports/phase10/new-browser
node scripts/build_pages.mjs
```

Backup, атомарная запись, откат и защита от параллельных изменений — прежний merge-контракт (разделы 12–13).
Сам `--dry-run` никогда не меняет production. Существующие Extreme повторно валидируются прежним валидатором;
их сохранённые сертификаты, IDs, puzzle strings и ratings не пересоздаются и не изменяются.
Standard run report остаётся неизменяемым источником provenance; факт добавления отражён в merge report,
повторное добавление блокируется по ID/строке/solution/diversity. Не используйте derived `dist` как source DB.

Далее review → commit → push → Pages workflow → public smoke (разделы 16–17).
Дополнительно проверьте Easy → New Game → Easy, Medium → New Game → Medium, Extreme → New Game → Extreme,
корректные Puzzle Details и отсутствие ошибок консоли. Генерация Extreme остаётся в разделах 3–19.

## 21. Hard и Expert (Phase 11)

Оба уровня используют существующий генератор и стандартную проверку версии 1, как Easy/Medium.
Hard: `7 <= requiredRating < 12`, потолок применяемых техник 11. Expert: `requiredRating >= 12`,
потолок текущего registry 55 и обязательная свежая Deep-классификация именно Expert.
Expert не ограничивается рейтингом 29: сложный шаг сам по себе не выполняет остальные условия Extreme.
Уникальность, независимая проверка логического proof и два детерминированных replay обязательны.
Рейтинг, solver и Extreme certification не меняются; `VERIFIED` не означает minimax-сертификат.

Пример подготовки десяти задач каждого уровня (каждый новый запуск требует новый `--run-dir`):

```powershell
python -m generator production-batch --difficulty Hard --seeds 11101,11102,11103 --per-seed-count 5 --target-new 10 --min-clues 22 --max-clues 30 --minimal --max-attempts 100000 --generation-seconds 600 --runtime-budget 1800 --run-dir data/research/phase11/hard
python -m generator production-batch --difficulty Expert --seeds 11201,11202,11203 --per-seed-count 5 --target-new 10 --min-clues 22 --max-clues 30 --minimal --max-attempts 100000 --generation-seconds 600 --runtime-budget 1800 --run-dir data/research/phase11/expert
python -m generator production-merge --from-run data/research/phase11/hard --from-run data/research/phase11/expert --max-new 20 --dry-run --report reports/phase11/merge-dry-run.json
python -m generator production-merge --from-run data/research/phase11/hard --from-run data/research/phase11/expert --max-new 20 --backup-dir data/research/phase11/backups --report reports/phase11/merge.json
python scripts/validate_production_database.py
```

Сначала проверьте `complete`, количество `selected` и результаты dry-run. Бюджет/число попыток не гарантируют
квоту: при недостатке создайте следующую партию с новыми seeds, сохраняя критерии проверки. `--runtime-budget`
проверяется между seeds; отдельная Deep-проверка не прерывается жёстко по времени. Не выдавайте partial run
за завершённый выпуск. Existing production records и их IDs сохраняются; backup находится вне production.
Публикация выполняется отдельным release workflow после review, тестов и проверки итоговой базы.
