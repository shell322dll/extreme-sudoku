# Phase 5: ordinary Sudoku Generator

Этот отчёт относится к обычной генерации, проверке и экспорту Sudoku. Evolution,
fitness, mutations, population, crossover и minimax не реализованы в этой фазе.
Нумерация ниже соответствует 22 пунктам итогового отчёта из задания Phase 5.

## 1. Baseline

До изменений: Python 3.11.9 (Windows, 64 bit), `py -3 -B -m unittest discover
-s generator/tests -v`: **184 tests, OK**, 54.853 s; wall time процесса 55.184 s.
После первого блока config/models/construction: 184 tests, OK, 53.675 s.

## 2–3. Итоговое количество тестов и полный suite

Итоговый `py -3 -B -m unittest discover -s generator/tests -v`:
**230 tests, OK, 57.417 s** (2026-09-28, Python 3.11.9). Добавлено 46 tests
относительно baseline; Phase 1–4 regression, включая clean-process dependency
boundary, пройден. Focused verification перед финальным прогоном: 47 tests,
OK, 2.538 s. После полного suite изменялась только документация.

## 4. Generation pipeline

`GeneratorConfig` задаёт ограничения. `PuzzleGenerator.generate_many()` выполняет
Solution Generation → Clue Removal → optional Minimalization → Clue Range →
fresh Exact Uniqueness → Quick/Deep Rating → Acceptance → Human Path → Export.
`GeneratedPuzzle` содержит puzzle/solution strings, clue mask, seed и attempt seed,
идентификатор, clues/unique/minimal, `DifficultyResult` и воспроизводимый Human path.

## 5. Clue removal

`remove_clues(Individual, target_clues, rng=...)` перемешивает существующие clues
локальным RNG и оставляет удаление только после exact uniqueness check. Остановка
происходит на выбранном target либо после исчерпания removable clues. Некорректная
неуникальная задача не создаётся для достижения числовой цели.

## 6. Minimalization

`minimalize()` использует тот же алгоритм с target=0. Достаточно одного полного
прохода: если после удаления clue было два решения, они сохранятся после удаления
других clues. Затем pipeline проверяет каждую оставшуюся clue. Minimal означает
невозможность удалить одну clue; это не minimum и не обещание 17 clues.

## 7. DifficultyAnalyzer

Используется существующий `DifficultyAnalyzer` Phase 4. Exact solver применяется
для математической валидации, Human Solver получает только puzzle. Difficulty
классифицируется по логическому пути и текущим правилам Phase 4; clues служат
отдельным фильтром. Рейтинги и solver correctness Phase 1–4 не переписывались.

## 8. Quick и Deep

`quick` — обычный быстрый анализ; случайно найденный сложный кандидат дополнительно
проверяется Deep. `deep` — прямой Deep. Default `quick_then_deep` запускает Quick
для прошедших дешёвые фильтры задач, затем Deep для перспективных Expert+,
Quick-stuck и подходящих случаев возможного снижения класса при target filtering.
Для явно слабых задач Deep не запускается. Deep наследует bounded deterministic
доказательства Phase 4 и не является полным minimax по всем логическим путям.

## 9. Difficulty filtering

При `target_difficulty` принимается только совпадающий класс. Несовпадение
расходует одну попытку и регистрируется. Quick-only для Extreme/Ultra Extreme
target недопустим. Уровень не повышается из-за малого числа clues.

## 10. Reproducibility

Один batch использует локальный `random.Random(seed)` и сохраняет отдельный seed
каждой попытки. При seed=None выбранный seed возвращается в результате. Повторный
запуск с одинаковыми seed/config/version воспроизводит puzzles, IDs и анализ.
Время, UTC даты и остановка по wall-clock timeout в эту гарантию не входят.

## 11. Batch

`generate_many(count, config)` возвращает `BatchResult`: requested, puzzles,
complete, seed, stats и отдельно preliminary candidates. `max_attempts` — общий
budget batch. Частичный результат честно содержит найденное число задач. Exact
duplicate определяется по полной puzzle string. ID строится из SHA-256 puzzle.

## 12. Rejection reasons

`NOT_UNIQUE`, `OUTSIDE_CLUE_RANGE`, `HUMAN_UNSOLVED`, `WRONG_DIFFICULTY`, `DUPLICATE`.
Stats содержат attempts, generatedCompleteGrids, accepted, counters rejection,
время и количество вызовов стадий, elapsed и timedOut. Timeout проверяется между
стадиями и удалениями clues; уже начавшийся solver call не прерывается.

## 13. JSON export

Root: `schemaVersion: 1`, `generatedAt` (UTC), `generatorVersion: "0.5.0"`,
`puzzles`, `stats`. Puzzle использует контракт `DATA_FORMAT.md`: id, puzzle,
solution, clues, difficulty, rating, unique, minimal, difficultyData, techniques
и опциональные metadata. `hardestTechnique` и `difficultyData.hardestRating`
экспортируются только для подтверждённого Deep required level. Quick сохраняет
наблюдаемую технику в `ratingMetadata.observedHardestTechnique`, не объявляя её
обязательной. Формат спецификации не изменён. Запись UTF-8 с indent=2,
стабильными полями/порядком; изменяемые timestamps явно отделены от seed results.
Перед записью экспорт выполняет самостоятельные проверки содержимого.

## 14. CLI

```console
py -3 -m generator generate --seed 42 --count 1 --min-clues 35 --max-clues 40 --no-minimal --rating quick --output data/easy-sample.json
py -3 -m generator generate --seed 42 --count 8 --min-clues 17 --max-clues 30 --minimal --rating quick_then_deep --output data/puzzles.json
py -3 -m generator generate --seed 42 --count 1 --difficulty Expert --max-attempts 20 --min-clues 17 --max-clues 30 --output data/expert-sample.json
```

Фильтр может не найти нужный класс в указанном budget; это штатный partial failure.

## 15. Smoke generation

Запуск `py -3 -m generator.tests.profile_phase5` воспроизводит fixed-seed smoke,
повтор seed/config, экспорт во временный JSON и independent fresh checks.
Результат сохранён в `PHASE5_PROFILE.json` от 2026-09-28: seed=42, 35–40 clues,
без minimalization, Quick. Получена одна Easy с 36 clues,
ID `puzzle-e4c65a691a4fdf026061`, rating=1.340950, unique=true, minimal=false;
наблюдаемая техника Naked Single. Время 0.119494 s, 1/1 попытка принята.
Повтор seed/config дал равный результат (0.140771 s). Экспорт повторно прочитан;
independent validation подтвердила solution units, givens, uniqueness и minimality.

После финального regression выполнены два реальных CLI subprocess без mocks:

```console
py -3 -B -m generator generate --seed 42 --count 1 --min-clues 35 --max-clues 40 --no-minimal --rating quick --output <temp>/success.json
py -3 -B -m generator generate --seed 42 --count 1 --min-clues 35 --max-clues 40 --no-minimal --difficulty "Ultra Extreme" --max-attempts 1 --output <temp>/failure.json
```

Первый вернул exit=0 за 0.303646 s, записал одну ту же Easy; повторный JSON parse,
`validate_database` и fresh independent checks пройдены. Второй использовал default
`quick_then_deep`, вернул exit=1 за 0.242214 s, Found=0/1, attempts=1,
`WRONG_DIFFICULTY=1`; выходной файл отсутствует. Deep для явно слабой задачи
не запускался, fake records не создавались. Временный каталог очищен.

## 16. Реальный sample batch

Профиль генерирует 8 minimal puzzles с seed=42, диапазоном 17–30 clues, без target
difficulty; пишет `data/puzzles.json`, повторно парсит и валидирует его. Для всех
задач независимо проверяются полные Sudoku units, givens, uniqueness, minimality
и отсутствие duplicate IDs/puzzles. Реальный запуск принял 8/8 за 2.948841 s;
все восемь задач unique=true и minimal=true, rejection отсутствуют.

| ID | Clues | Difficulty | Rating | Minimal | Hardest technique |
| --- | ---: | --- | ---: | --- | --- |
| puzzle-1618f2c5ac56583ae13f | 23 | Easy | 1.598304 | true | Hidden Single (observed) |
| puzzle-eedf24b9b7d2dabbc873 | 25 | Easy | 1.594507 | true | Hidden Single (observed) |
| puzzle-69645ab9048cf559f77e | 25 | Easy | 1.579863 | true | Hidden Single (observed) |
| puzzle-00e8aac7882fac026985 | 26 | Easy | 1.578601 | true | Hidden Single (observed) |
| puzzle-4ba451b3675f7983b4c1 | 23 | Medium | 3.427722 | true | Naked Pair (observed) |
| puzzle-7a9540473df3ba834e85 | 23 | Medium | 3.420767 | true | Naked Pair (observed) |
| puzzle-ed252da19f0f2a0ba981 | 25 | Medium | 2.406440 | true | Locked Candidates (observed) |
| puzzle-f2a1e331cba6509d1546 | 24 | Expert | 19.424711 | true | W-Wing (Deep verified) |

Observed — техника выбранного Quick path из ratingMetadata; соответствующее
поле `hardestTechnique` в JSON отсутствует. У Expert Deep подтвердил required
rating=17.0 и два bottlenecks в пределах реализованного Human Solver.

## 17–18. Performance и дорогие стадии

Диагностические measurements находятся в `PHASE5_PROFILE.json`. Они включают
mean attempt, calls/total/mean для каждой стадии, export/fresh validation и
отдельные cold Quick/Deep/minimalization samples. Сериализованные измерения не
используют конкурентные тестовые процессы; время не является pass/fail threshold.
Для batch 17–30 средняя generation attempt равна **0.368537 s**.

| Стадия batch | Вызовов | Всего, s | Среднее на вызов, s |
| --- | ---: | ---: | ---: |
| Solution generation | 8 | 0.000733 | 0.000092 |
| Clue removal | 8 | 0.121992 | 0.015249 |
| Minimalization | 8 | 0.126512 | 0.015814 |
| Fresh uniqueness | 8 | 0.008956 | 0.001120 |
| Quick rating | 8 | 0.813177 | 0.101647 |
| Deep rating | 1 | 1.320791 | 1.320791 |
| Minimality check | 8 | 0.028274 | 0.003534 |
| Human path | 8 | 0.491635 | 0.061454 |

Самая дорогая стадия — Deep (один вызов для Expert); затем Quick и повторное
построение Human path. Для семи слабых кандидатов Deep не выполнялся. Export с
валидацией занял 0.167269 s, отдельные independent fresh checks — 0.155406 s.
Cold diagnostics (Easy / Expert): Quick 0.065781 / 0.148963 s,
Deep 0.245078 / 1.322233 s, minimalization 0.015382 / 0.009838 s
(отдельные кандидаты с 35 clues уменьшились до 21 / 25).

Default 17–23, seed=42, budget=8: принято 2/8 (25%), шесть `OUTSIDE_CLUE_RANGE`,
complete=false, wall 0.606773 s, mean attempt 0.075789 s. Quick вызван дважды,
Deep ни разу. Время меньше за счёт ранних отказов, поэтому его нельзя напрямую
сравнивать со временем принятой задачи широкого диапазона. Измерения сделаны
на Python 3.11.9, Windows 10 build 17763, AMD64 Family 25 Model 80;
окружение и полная точность сохранены в JSON. Это диагностика, не benchmark.

## 19. Ограничения обычного generator

Исходные solutions основаны на прежнем Latin pattern с допустимыми перестановками;
это не равномерная выборка всех Sudoku. Случайное удаление не гарантирует 17–23
clues либо трудный класс. Minimalization может выйти из запрошенного диапазона —
кандидат отклоняется. Symmetry сейчас только none. Дедупликация exact, без полного
Sudoku canonical equivalence. Решаемость/необходимость сложных техник ограничены
существующим репертуаром, лимитами и детерминированными путями Human Solver.

## 20. Частота Expert/Extreme

В принятом batch 17–30: Easy 4/8 (50%), Medium 3/8 (37.5%), Expert 1/8 (12.5%),
Hard/Extreme/Ultra Extreme — 0/8. Default 17–23 дал одну Easy и одну Medium;
Expert/Extreme/Ultra Extreme не найдены. Preliminary candidates: 0.
Оба прогона используют один seed и не считаются независимыми выборками.
Такие данные не оценивают общую вероятность Expert/Extreme/Ultra Extreme для
произвольных Sudoku. Extreme, не совпавшие с target difficulty, API сохраняет
отдельно как preliminary candidates после Deep; совпавшие и результаты без
target входят в принятые puzzles. Final certification этим не объявляется.

## 21. Подготовка Phase 6

Доступны reusable `Individual(solution=solution, clue_mask=clue_mask)`, `remove_clues`, `minimalize`,
`validate_candidate`, `PuzzleGenerator.rate_candidate` и независимый export API.
Для Phase 6 потребуются отдельно спроектированные search/operators, budgets,
более широкая выборка и строгая сертификация. Phase 6 в этом изменении не начата.

## 22. Отдельное code review

Независимый reviewer проверил config/models, construction, pipeline, export,
CLI, public imports и README: **GREEN, блокирующих замечаний нет**.
В ходе финализации исправлены eager public imports (lazy `__getattr__` сохраняет
API и исключает транзитивный exact dependency при human-only import), подпись
CLI `Best candidate` для предварительных кандидатов и порядок аргументов
`Individual` в документации посредством явных keywords.

Review охватил сохранение uniqueness/minimality, диапазон clues, локальные RNG,
immutable solution, cache boundaries, независимость difficulty от clue count,
JSON validation/atomic write, duplicates, rejected/preliminary export,
условный Deep и reuse API. Последующая verification: полный suite 230/230,
успешный и отклонённый реальные CLI subprocess. Ограничения bounded Human Solver
и малой выборки остаются явно задокументированными; Phase 6 не начата.
