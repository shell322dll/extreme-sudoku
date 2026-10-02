# Phase 7: независимое критическое ревью

Дата: 2026-10-01. Область: `generator/certification`, соответствующие тесты,
CLI, граница production export и используемые логические detectors.
Reviewer не изменял продуктовый код; исправления передавались ответственным
разработчикам и проверялись повторно. Phase 8 не рассматривалась.

На проверенной версии известных блокирующих ошибок, допускающих ложную
сертификацию или превращение исчерпанного бюджета в доказательство, не найдено.
Это результат code review и воспроизводимых проверок, а не формальная
верификация всей программы. Разрешена фиксация исходников для общего regression
suite и окончательного candidate experiment.

Проверенный fingerprint:
`166aecc4915355c17af29d79b881acb1cd13fc0cd43576b8230f8102e5c96e76`.
Fingerprint в [PHASE7_REVIEW_AUDIT.json](PHASE7_REVIEW_AUDIT.json) подтверждён
до и после запуска независимого audit; исходники за этот запуск не изменились.

## Найденные и исправленные проблемы

| Приоритет | Ошибка и воспроизведение | Исправление и повторная проверка |
| --- | --- | --- |
| P2 | Повреждённый Empty Rectangle: заменить bridge `(x,y)` на `(x,x)` в валидном fixture. `validate_step` выбрасывал `StopIteration`, вместо результата invalid proof. Это сбой обработки внешнего proof, не принятие неправильного вывода. | Проверка двух различных bridge cells перед `next`; отдельный regression проходит. |
| P2 | `max_trivial_gap` считал расстояние между genuine bottlenecks. В него попадали BASIC/ADVANCED шаги, что не соответствует максимальной последовательности trivial steps. | Метрика считает непрерывные серии registry tier `TRIVIAL`; любой другой tier сбрасывает счётчик. Проверено чтением конечного алгоритма. |
| P2 | `canonical_steps` выбирал объяснение по неполному `step_key`. Две валидные обратные ориентации одинакового AIC loop имели одинаковый ключ, и результат зависел от порядка входа. Эффект и rating одинаковы, но сохранённый proof и его identity различались. | Полный структурный JSON proof добавлен как последний tie-break. Воспроизведение на настоящем AIC fixture и regression с обращением порядка проходят. Исторический greedy Human Solver не изменён. |
| P2 | Сравнение metadata через Python dictionary equality не различало `true` и `1`, `false` и `0`. Это слабость проверки JSON-контракта; fresh re-certification всё равно не позволяла принять неверную задачу. | Каноническое JSON-сравнение сохраняет типы; тест использует реальные fresh evidence лёгкой задачи, а не поддельный accepted certificate. Добавлены проверки типов пустой production statistics и input schema. |

Дополнительно проверено исправление IO-разработчика: tuple-поля dataclass proof
нормализуются в JSON-массивы до readback-сравнения. Иначе сериализация непустого
research proof могла ошибочно считаться повреждённой записью.

## Проверки reviewer

Команды из корня проекта:

```console
python docs/PHASE7_REVIEW_AUDIT.py
python -m unittest generator.tests.test_certification_engine generator.tests.test_certification_io generator.tests.test_certification_proofs -q
```

Второй запуск: **81 tests passed**, **13.119 s**, без failures/errors.
Это targeted certification suite. Итоговый общий regression suite и frontend
результаты должны браться из окончательных run artifacts и PHASE7_REPORT.

[PHASE7_REVIEW_AUDIT.py](PHASE7_REVIEW_AUDIT.py) — отдельные воспроизводимые
пробы reviewer. Они подтвердили:

- Все 30 registry names и ratings совпадают с действующим набором техник.
- 30 положительных семейных proof fixtures проходят, когда методы поиска
  detectors заменены ловушками. Checker действительно проверяет переданные
  premises, а не вызывает detector для нового объяснения.
- 337 независимых замен целочисленных premise atoms на `999` отклонены;
  неперехваченных исключений в этой серии нет. Это дополняет специализированные
  тесты повреждённых links, endpoints, RCC и forcing branches.
- Статически просмотрены 19 логических модулей: прямых Exact Solver imports
  в Human Solver, techniques, search, enumerators и proof checker нет.
- При ловушках всех пяти загруженных Exact API aliases настоящий Phase 3
  puzzle решён за 71 логический шаг и независимо replay-проверен. В этих же
  условиях выполнены threshold search и advanced enumeration; шесть полученных
  proofs валидны. Поиск получил puzzle/candidates, без known solution.
- Независимый перебор комбинаций клеток и множеств цифр нашёл те же 251 ALS,
  что production helper: размеры 1/2/3/8 — соответственно 4/3/1/243.
  При `max_als_size=1` пропущенные большие множества явно дают `ALS_SIZE_LIMIT`.
- Обе forcing-family enumerations с полным списком starts и минимальными
  node/depth budgets дают `FORCING_DEPTH_OR_NODE_LIMIT`, `complete=false`.
- Смоделировано истечение времени внутри enumerator после внешней проверки
  часов. Даже пустой итоговый frontier возвращает `INCONCLUSIVE_BUDGET` с
  `TIME_LIMIT`, а не доказанную невозможность.

## Completeness, minimax и dominance

Для одного fixed threshold переходы не используют произвольные guesses.
Proof каждого используемого перехода проверяется до применения. Ключ состояния
содержит значения всех клеток и candidate masks. Дедупликация шагов сохраняет
эффект и rating; два разных ratings одного эффекта не сливаются.

Поиск не обязан оптимизировать secondary cost: при одинаковом состоянии
доминирует путь меньшей глубины, потому что он оставляет не меньший depth budget.
Цена secondary используется для детерминированного порядка. Отдельный тест
проверяет повторное открытие состояния, сначала достигнутого глубоким, затем
более коротким путём. Этот тест изолирует алгоритм очереди на управляемом графе;
он не считается доказательством Sudoku theorem. Реальные proof-переходы
проверяются отдельными тестами.

Сертификация использует проверенный upper witness и поиск на ближайшем меньшем
registry rating. Если найден более дешёвый путь, проверяется следующий нижний
уровень. Исчерпывающее отсутствие пути непосредственно ниже upper witness
исключает все меньшие уровни благодаря вложенности каталога переходов.
Нижний `INCONCLUSIVE` не становится точным required rating.

Для первых 20 правил используются их конечные pattern detectors. Их область —
реализованные pattern rules, а не все возможные человеческие интерпретации
названия техники. В частности, naked subsets используют предусмотренный
detector набор клеток, а один transition содержит весь возвращённый эффект.
Full House перебирает units, а дедупликация одинаковых placement effects не
удаляет различных последующих состояний.

Пять chain families используют полный перебор простых путей по своему inference
graph; прежнее representative-node pruning не используется. Превышение длины
или числа просмотренных рёбер оставляет явный limit. Группы ограничены
реализованными box/line intersections; это часть модели, а не все мыслимые
grouped deductions.

Три ALS families используют disjoint ALS и RCC с полной попарной видимостью.
Всевозможные ALS sizes 1–8 проверяются перед operational size filtering, поэтому
исключённые большим размером множества не исчезают молча. Ограничения на размер,
graph work и длину chain дают incomplete. Overlapping/double-linked ALS вне
реализованной модели.

Forcing/Nishio используют одну исходную assumption и exactly-one clause
propagation. Дополнительные вложенные assumptions validator запрещает. Checker
проверяет каждый parent, глубину зависимости, clause membership и contradiction.
Структура ветвей и общие выводы проверяются независимо. Exact API в этом
выводе отсутствует. Пропущенные starts либо propagation nodes/depth дают limits.

Node/state/depth/alternative-step/time limits не дают отрицательного
доказательства. Верхний положительный witness может быть найден при неполном
перечислении остальных ветвей; это корректное доказательство существования
пути, но не его минимальности. Final classification требует завершённого
отрицательного lower search. Общий node budget делится между threshold passes.

## Граница production и сохранённые данные

`export_production` принимает исходные candidate records, заново сертифицирует
их и не принимает сохранённый label как разрешение на export. Дубликаты ID и
exact puzzle strings отклоняются до дорогой обработки. Uniqueness проверяется
заново; minimality проверяет удаление каждого оставшегося clue. Known solution
используется в математической проверке согласованности, а не inference.

Промежуточные статусы, timeout и invalid proof не проходят
`production_eligible`. Конфигурация не позволяет снизить существующие Extreme
и Ultra product thresholds. Clue count не входит в rating criteria. Genuine
bottlenecks проверяют отсутствие дешёвого шага ниже исторического bottleneck
floor 12; этот floor не следует путать с Extreme required-rating floor 30.

Перед записью и после JSON readback сверяется полный результат текущего fresh
запуска; схема, решение, uniqueness, ID и дубликаты проверяются дополнительно.
Файл заменяется атомарно. Независимый validator готовой production database
ещё раз выполняет fresh certification и сравнивает сертификаты с сохранёнными.
Игнорируются только конкретные поля времени; counters, algorithm/config
fingerprints и proof evidence остаются частью сравнения. NaN/Infinity запрещены.

Persisted rating/certification cache не переиспользуется, включая `fresh=False`.
Fingerprint охватывает certification, solver, Sudoku и rating sources.
Это исключает обычное принятие stale certificate после смены registry/proofs.

## Реальные данные и оставшиеся ограничения

На момент source freeze доступен только предварительный pilot двух настоящих
Phase 6 candidates: по одному Preliminary Extreme и Ultra Extreme,
оба получили timeout около 60 секунд, production count 0.
Источник: [PHASE7_PILOT_SUMMARY.json](PHASE7_PILOT_SUMMARY.json).
Его fingerprints до и после запуска различаются: pilot выполнялся во время
разработки. Поэтому он **не является финальным экспериментом проверенной
версии** и не подтверждает воспроизводимость финальных сертификатов.
Окончательные статистика и перечень IDs должны быть взяты из frozen-source
experiment и PHASE7_REPORT, без переноса pilot labels в certified fields.

Положительные Extreme/Ultra decision branches проверены на контролируемой
модели результата. Ни эти unit-тесты, ни успешный replay сложного puzzle не
заменяют реальный положительный сертификат с исчерпывающим lower search.
На момент ревью нет подтверждённого реального accepted-production roundtrip
для Extreme/Ultra. Если финальный эксперимент также даст пустую production
базу, это допустимый строгий результат, но положительный сценарий остаётся
эмпирически неподтверждённым на реальном сильном puzzle. Нельзя заявлять наличие
сертифицированного контента для frontend.

Время контролируется между операциями, отдельный Exact или detector вызов не
прерывается посреди выполнения. Возможен небольшой overrun; завершающая проверка
не допускает late result к certification. Результаты остановки по wall clock
и timing counters не обязаны совпадать между запусками с разной нагрузкой.

Exhaustive search дорог: многие высокие thresholds закончатся лимитом,
особенно из-за простых chain paths и больших ALS. Это снижает практическую
пропускную способность, но не даёт оснований ослаблять gates. Минимальный rating
доказан только внутри явно реализованной модели. Все возможные человеческие
решения Sudoku, конкретная обязательная техника и глобальный минимум clues
этой работой не доказываются.

## Окончательная проверка regression и definitive evidence

После source freeze независимо сверены завершённые артефакты:
[PHASE7_FINAL_SUMMARY.json](PHASE7_FINAL_SUMMARY.json), исходные test logs,
[PHASE7_EXPERIMENT_SUMMARY.json](PHASE7_EXPERIMENT_SUMMARY.json), input,
research JSON, все девять индивидуальных reports и strict production JSON.
Результат проверки сохранён в
[PHASE7_FINAL_EVIDENCE_REVIEW.json](PHASE7_FINAL_EVIDENCE_REVIEW.json).

Final regression: **350 Python tests**, **16 frontend tests**, **14 browser
groups**, **56 responsive checks** прошли. Число frontend tests подтверждено
непосредственно логом: его Unicode reporter не заполнил поле `tests` в summary.
Исходники regression совпадают с текущими: aggregate SHA-256
`20644ec1a53851181cbd1de02877350ec51277c13a053785798e7a8a76a8831e`.
При повторном расчёте исключены только два новых experiment outputs:
`data/candidates.json` и `data/production/puzzles.json`, которых до batch не было.
Algorithm fingerprint до/после batch и во всех девяти results совпадает с
проверенным выше `166aecc4915355c17af29d79b881acb1cd13fc0cd43576b8230f8102e5c96e76`.

Все девять входов имеют различные IDs и puzzle strings; сохранённые source
archives и их SHA-256 не изменены. Provenance каждого record сопоставлен с
исходными Phase 6 exports/population. Отдельный небольшой MRV exact checker,
не использующий production Exact Solver, повторно подтвердил ровно одно
решение каждого из девяти puzzles. Полнота/валидность сохранённых solution,
согласованность givens и clues проверены отдельно. Индивидуальные reports
совпадают с research entries; JSON разобран с отказом при повторяющихся keys
или nonfinite numbers. Counts, группировка по preliminary labels, timings,
states и cache counters пересчитаны из per-candidate evidence.

Definitive batch: **2 Preliminary Extreme + 7 Preliminary Ultra Extreme**;
все девять получили **CERTIFICATION_TIMEOUT**, certified/rejected/прочих
inconclusive — **0/0/0**. Включены три кандидата с 22 clues. Batch wall time
541.431 s, среднее 60.084 s, максимум 60.675 s; 2205 explored states и
18854 transposition cache hits. У всех девяти fresh evidence сообщает успешные
human solve/proof checks, но minimum required rating/tier остаются `null`,
а certified paths пусты. Timeout не стал ни certificate, ни доказанным
понижением прежней preliminary difficulty.

Strict production содержит **0 puzzles**; IDs пусты, certified extrema —
`null`. Повторный public `validate_production_database` прошёл для этой пустой
базы. Это проверка пустого dataset contract, а не испытание положительного
accepted-record roundtrip. Реального положительного Extreme/Ultra certificate
при default policy по-прежнему нет; наличие production-контента и готовность
к снабжению frontend сертифицированными задачами **не подтверждены**.
Новых дефектов целостности окончательных evidence не обнаружено. Повторный
дорогой threshold search при этом review не запускался; ограничение
практической производительности и граница реализованной модели остаются.
