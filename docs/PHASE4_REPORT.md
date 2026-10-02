# Phase 4 — Difficulty Rating

Реализован отдельный Python-слой `generator/rating`, без изменений correctness
детекторов Phase 1–3 и без начала evolutionary generator. Название Phase 4 в этом
отчёте относится к текущему заданию; историческая нумерация в GENERATOR_SPEC шире.

## Проверки

Baseline: **149 tests, OK**, unittest **37.703 s**, полное время команды **38.075 s**,
Python **3.11.9** на Windows. Команда:

```console
python -m unittest discover -s generator/tests -q
```

После каждого блока выполнялся полный suite:

| Блок | Что проверено | Tests | unittest, s | Результат |
|---|---|---:|---:|---|
| A | registry/config, legacy compatibility | 152 | 36.324 | OK |
| B | Quick, result, profile metrics, signatures | 156 | 37.340 | OK |
| C | tiers/profiles, threshold/disabled solving | 159 | 37.530 | OK |
| D | available/minimum steps, cache isolation | 164 | 37.916 | OK |
| E | genuine bottlenecks and grouping | 167 | 37.987 | OK |
| F | required level and specific necessity | 171 | 39.568 | OK |
| G | Deep and transitive dedup regression | 174 | 41.194 | OK |
| H | classification, uniqueness, diagnostic report | 177 | 43.049 | OK |
| I | regression fixtures, cache/determinism, validation | 183 | 55.195 | OK |
| J | независимый final regression, ALS/forcing metadata | 184 | 57.790 | OK |

Итого **149 →184 tests (+35), весь regression suite OK**, exit code0.
Независимый финальный запуск: unittest **57.790 s**, command wall **58.119 s**,
Python3.11.9 x64. Финальная длительность могла включать конкуренцию с другим
завершающимся suite, поэтому не используется как performance benchmark.
Отдельный profiling ниже выполнялся без конкурирующих CPU-heavy процессов.
Время checkpoint — wall-clock внутри unittest, не performance assertion.

## Registry и конфигурация

`registry.py`: immutable `TechniqueRating(name, tier, base_rating, weight)` и
`TechniqueRegistry(entries)`, API `rating_of`, `tier_of`, `weight_of`. Неизвестные
имена и дубли вызывают `ValueError`; порядок стабилен по `(rating, name)`, numeric
ratings и weights проверяются на finite/nonnegative. `weights.py` теперь только
compatibility export этого источника, поэтому существующие detectors и custom
`HumanSolver(weights=...)` сохраняют прежний контракт.

Сохраняется шкала **0.5–55**, не Sudoku Explainer scale:

| Tier | Техники | Default ratings |
|---|---|---|
| TRIVIAL | Full House, Naked/Hidden Single | 0.5, 1, 1.2 |
| BASIC | Locked Candidates, Naked/Hidden Pair, Naked/Hidden Triple | 2, 3, 3.2, 5, 5.2 |
| INTERMEDIATE | Quads, X-Wing, Skyscraper, Kite, Turbot, Empty Rectangle | 7–11 |
| ADVANCED | Swordfish, XY/XYZ/W-Wing, Jellyfish | 12, 14, 16, 17, 18 |
| EXTREME | X/XY-Chain, AIC, Nice Loop, Grouped AIC, ALS, forcing | 22–55 |

`DifficultyConfig` immutable и JSON-serializable (`to_dict`/`from_dict`). Содержит
registry с отдельными scoring weights, `AdvancedConfig` budgets, exponent и bonuses,
пороги шагов/классов/candidates, temporal bins, cache bound. Конфигурация не меняет
логическую корректность detectors. Политика thresholds должна перекалибровываться
при существенном изменении registry; числа не являются универсальной шкалой человека.

## Quick и score

Quick запускает один детерминированный HumanSolver path. Не запускает threshold
solves, альтернативные detectors или uniqueness. Сохраняет hardest observed,
weighted total, step counts, цепочки/ALS/forcing, signature перед каждым шагом,
фактический difficulty profile и расположение сложных участков.

Default формула отдельного `DifficultyResult.total_score`:

```text
step_score = weight**2 + chain_complexity
           + 4*has_ALS + 8*has_forcing + 0.01*log1p(search_complexity)
chain_complexity = 1.5*chain_length + 2*grouped_nodes
                 + 1*(extra_assumption_branches + extra_inference_parents)
total_score = sum(step_score)
quick_rating = hardest_observed + 0.1*log1p(total_score)
```

Все коэффициенты configurable. Search work получает лишь небольшой логарифмический
вклад. Старый `HumanSolveResult.total_score=sum(step.rating**2)` не изменён.
AIC длиной 4 и 18 получают разный score; base technique остаётся главным фактором.
Candidate links, ALS RCC links и forcing proof depth сохранены как существующие
единицы `chain_length`; это приближение, не единая психологическая единица.

`advanced_steps` в новом result означает rating ≥12, `extreme_steps` ≥22.
Исторический HumanSolveResult.advanced_steps по-прежнему означает техники Phase 3.
`high_peak_count` считает начала непрерывных advanced episodes, `peak_positions`
сохраняет индексы, `advanced_distribution` — число advanced steps в четырёх
равных интервалах пути. Late начинается с 65% пути. Один высокий пик не создаёт
несколько peaks, а одна длинная цепь не превращается в несколько steps.

## Deep, required level и альтернативы

`required_level` пробует **все distinct ratings по возрастанию**, начиная с 0,
до первого SOLVED. Каждая попытка начинает puzzle заново и разрешает только
техники ≤threshold. Binary search не используется: bounded detectors и порядок
переходов могут делать успех немонотонным. Сохраняются statuses всех попыток;
INVALID ниже порога не считается доказательством недостаточности простого уровня.
Для unsolved puzzles required rating отсутствует. Unverified successful threshold
может сохраняться как наблюдение, но verified=False и класс Unrated.
Полностью заполненное валидное поле имеет required=0, пустой path, Easy.

Deep оценивает путь **первого успешного threshold run**, дополнительно выполняет
четыре named profiles и проверяет сложные состояния. Поэтому gratuitously harder
path другого запуска не повышает required floor. `technique_necessity` отдельно
сравнивает полный repertoire с отключённой одной техникой; это иной вопрос.
Для seed 4 required level AIC=30, но AIC можно заменить ALS/forcing логикой.

```text
deep_rating = required_rating + 0.1*log1p(total_score)
            + 0.05*sum(maximum minimum-rating per crisis group)
            + 0.1*number_of_occupied_advanced_bins
```

Класс определяется floor и explicit candidate gates, не добавочными малыми bonuses.
Количество clues/minimality не участвует в формуле.

`StateAnalyzer.analyze_state` возвращает все available representative deductions,
minimum/maximum, techniques и число alternatives в заданных detector budgets.
`minimum_available_rating` проверяет все более низкие уровни и все tied detectors
первого доступного уровня. Более высокие уровни не могут уменьшить минимум и
пропускаются: `enumeration_complete=False`, counts относятся **только к minimum
layer**, не ко всем возможным ходам. Даже complete означает bounded implemented
enumeration, не неограниченное множество цепочек. Invalid emitted deduction
вызывает ошибку, а не превращается в отсутствие хода.

## Bottlenecks и fake-extreme

Bottleneck — состояние, где minimum available rating ≥12. Перед каждым дорогим
шагом вычисляется именно minimum, а не rating выбранного шага. Для дешёвого
применённого шага сам валидный шаг уже является свидетельством против высокого
bottleneck. Никаких отсутствий easy moves по одному greedy выбору не предполагается.

Unit cases: Hidden Single+AIC → не AIC bottleneck; только AIC →30;
AIC+ALS-XZ →30. Для каждой записи сохраняются step index, immutable state signature,
required rating/technique, число минимальных шагов, genuine, group id и bounded scope.

Смежные высокие шаги объединяются в один кризис. Повтор той же структуры proof
также объединяется; если повтор связывает две группы, выполняется transitive merge.
Proof identity исключает target eliminations и поясняющий текст. Метод намеренно
консервативен: может объединить независимые смежные patterns, но не завышает count
из-за нескольких технических eliminations. Raw states остаются доступны отдельно.
`true_bottleneck_count`, severity и late count считаются по группам.

Fake-extreme защита: требуется несколько групп и advanced steps; для Ultra также
длинная цепь и распределение сложных шагов. Один forcing peak и последующие singles
не получает автоматически максимальную категорию.

## Классы, профили, предварительные кандидаты

Профили централизованы в `profiles.py`: BASIC≤5.2, INTERMEDIATE≤11,
ADVANCED≤18, EXTREME≤55 при default registry. Они задаются tier, поэтому custom
registry учитывается автоматически. Phase 2 включает также ADVANCED и не равен
INTERMEDIATE profile.

| Класс | Начальный floor / дополнительные условия |
|---|---|
| Easy | 0 |
| Medium | 2 |
| Hard | 7 |
| Expert | 12; также high-floor без полного pre-certification evidence |
| Extreme | required≥30, ≥3 advanced steps, ≥2 crisis groups |
| Ultra Extreme | required≥36, ≥5 advanced steps, ≥3 groups, longest chain≥8, ≥2 occupied advanced bins |

Оба high classes требуют Deep, verified required floor, unique=True, solved,
Basic/Intermediate STUCK, Extreme profile SOLVED, no guesses/backtracking.
Ultra дополнительно требует chain/ALS/forcing usage. Quick максимум Expert;
его классы описывают observed path, а не подтверждённую обязательность.
Все thresholds/минимумы вынесены в config.

`analyze_difficulty(puzzle)` по умолчанию выполняет Deep и отдельную uniqueness
проверку. `DifficultyAnalyzer.deep(puzzle)` и `analyze_difficulty(...,
check_unique=False)` выполняют только human analysis. Exact импорт разрешён лишь
в `precertification.py`; он считает solutions с limit=2 и не передаёт solution
или поисковые метрики human слою. Quick никогда не вызывает exact.

`is_extreme_candidate`/`is_ultra_extreme_candidate` — **preliminary**, production
certification не реализована. `diagnostic_report` явно печатает scope,
профили, required/observed, counts, total, класс и статус preliminary.

## Реальные regression fixtures

Файл: `generator/tests/fixtures/difficulty/regression.json`. Значения подтверждены
ascending threshold solves, а не выведены из названий старых fixtures.

| Fixture | Минимальный успешный rating | Tier / класс |
|---|---:|---|
| basic-classic | 1 | TRIVIAL, решается BASIC / Easy |
| intermediate-seed-21 | 10 | INTERMEDIATE / Hard |
| advanced-seed-3 | 14 | ADVANCED / Expert |
| extreme-seed-4 | 30 | EXTREME / Extreme candidate |

```text
Basic:
530070000600195000098000060800060003400803001700020006060000280000419005000080079
Intermediate:
728000000000000500000409000640070020900000000000645009201000870090380000000000040
Advanced:
710000004800000020090000830004700000050040200007800000040002500000094702001380090
Extreme candidate:
009000830001340020040050000030900006024100000000007090080000050002700049000000600
```

Seed 21 исторически назывался X-Wing fixture, но минимальный успешный threshold
равен **Turbot Fish=10**, не8. Seed4: required AIC30, 5 advanced steps,
2 grouped bottlenecks и longest chain7; поэтому Extreme candidate, не Ultra.
Ultra-положительный real fixture на этом этапе не объявляется без подтверждения;
criteria проверяются controlled unit scenarios.

## Cache, determinism, performance

`SudokuState.signature()` — `(tuple(grid), tuple(candidate_masks))`; учитывает
логические eliminations и не содержит runtime IDs. Copyable state и representative
all-steps API готовы для будущего bounded minimax, который здесь не реализован.

Bounded LRU хранит immutable summaries. Ключ включает state signature, profile,
всю immutable config и вид запроса minimum/full. State mutation, другая конфигурация
или repertoire не используют stale cache. `cache_size=0` отключает хранение;
есть clear_cache и counters вне DifficultyResult. Results не содержат timing или
cache stats. Тестируются cache hit, mutation, profile/config separation, eviction,
disabled cache и детерминизм fresh/reused/cache-disabled анализов и subprocess hash seeds.

Измерения воспроизводятся `python -m generator.tests.profile_phase4`;
подробный environment/config/normal/Quick/Deep/state/detector профиль хранится в
`docs/PHASE4_PROFILE.json`. Независимый run: `python -m
generator.tests.profile_phase4 --repeats 3`, без одновременно работающего suite;
медианы трёх samples, Deep включает отдельный uniqueness gate:

| Puzzle | Human Solve, s | Quick, s | Deep cold, s | Deep warm, s | Deep / Human |
|---|---:|---:|---:|---:|---:|
| Basic | 0.044017 | 0.076823 | 0.287768 | 0.287195 | 6.538 |
| seed21 | 0.073307 | 0.116764 | 0.901316 | 0.903105 | 12.295 |
| seed3 | 0.076720 | 0.124578 | 1.117095 | 1.112318 | 14.561 |
| seed4 | 0.171406 | 0.223517 | 1.327723 | 1.230420 | 7.746 |

Quick дороже обычного solve из-за instrumentation/replay и scoring, но не запускает
дорогие threshold/alternative runs. Warm Deep повторяет threshold/profile solves,
поэтому ускорение умеренное: cache относится к state analysis, не всему result.

На seed4 state перед первым AIC (index19): minimum-only **0.030609 s**, полный
validated state analysis **0.641749 s**, raw `HumanSolver.all_available_steps`
**0.530199 s**, cache hit **0.000203 s**. Дополнительная validation emitted steps
также стоит времени. Проверка только минимального слоя сокращает большую часть
расходов, не ослабляя minimum claim в заданном repertoire.

На этом состоянии самые дорогие detectors: ALS Chain **0.126706 s**, Nishio
**0.098875 s**, Forcing Chain **0.094079 s**, ALS-XY-Wing **0.070734 s**,
Grouped AIC **0.062972 s**, ALS-XZ **0.050222 s**, AIC **0.015459 s**.
Главные bottlenecks — многократные threshold/profile solves, ALS graph enumeration,
forcing propagation и полное перечисление высоких техник. Это измерение одной
сложной позиции, не универсальный ranking. `--include-expensive` позволяет отдельно
добавить существующий seed48; он не включён в сохранённый run, новые fixtures не
генерировались. Все internal correctness/determinism/cache assertions profiling
прошли; historical PHASE3_PROFILE не изменялся.

## Независимое review и ограничения

Отдельный reviewer проверил registry/import cycle, legacy weights, state/cache,
mandatory evidence, Deep и candidate gates. Найден medium defect: повтор pattern
мог связывать две смежные группы без transitive объединения. Исправлен с regression
`A, cheap, B, A`; повторное review подтвердило исправление. Также усилена validation
Boolean tier и численных classification thresholds.

**Final independent review: APPROVED, открытых blocking findings нет.** Reviewer
изучил финальные regression fixtures, cache/determinism tests и ALS/forcing metadata
test. Дополнительно отдельный clean subprocess запрещал импорт `exact_solver`,
`solution_generator` и `clue_generator` при полном Deep seed4 с `check_unique=False`:
SOLVED, verified required30, 2 bottlenecks, unique=None, candidate=False; exact module
не загружался. Отдельный verification agent подтвердил final **184 tests OK**.

Ограничения: observed минимум в **bounded deterministic repertoire**, не глобально
минимальная человеческая сложность; detector budget exhaustion не доказывает
отсутствие произвольной логики. Нет полного future branching/minimax, поэтому
STUCK проще уровня — лишь свидетельство внутри реализованного solver. Возможны
недооценка числа кризисов из-за conservative grouping и зависимость результата
от явно заданных budgets. Scoring weights и классы нуждаются в калибровке на более
широкой независимо оценённой базе. Search complexity — технический proxy.

Перед evolutionary generator понадобятся: расширенный проверенный dataset и
калибровка, измерение throughput на candidate pools, обработка budget exhaustion
с более явным telemetry, bounded alternative-path/minimax для лучших кандидатов,
fresh independent uniqueness/minimality/path validation перед production export.
Эти шаги не начаты автоматически: Phase 4 останавливается на preliminary analysis.
