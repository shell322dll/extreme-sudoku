# Extreme Sudoku

Python-движок генератора по `docs/GENERATOR_SPEC.md`. Генерация Phase 1–6 и
отдельный слой сертификации Phase 7 реализованы;
frontend и база опубликованных задач независимы от генератора. Phase 7 добавляет
отдельный консервативный certification pipeline; его контракт описан в
[CERTIFICATION_SPEC](docs/CERTIFICATION_SPEC.md).

Требуется Python 3.10+; внешних зависимостей нет. Команды из корня проекта:

```console
python -m unittest discover -s generator/tests -v
python -m generator --seed 42
```

В Windows вместо `python` можно использовать `py -3`, если так настроен Python.

Phase 1 включает плоское поле из 81 числа, заранее вычисленные peers/units,
кандидатов в 9-битных масках, exact solver (MRV + bitmask DFS), проверку уникальности,
воспроизводимое полное решение, 81-битную маску подсказок и минимизацию с сохранением
единственного решения. `Individual` хранит неизменяемые solution и clue mask.
Human Solver применяет Singles, Locked Candidates и Naked/Hidden Pairs/Triples,
начиная с самой простой доступной техники и сохраняя объяснения шагов.

Phase 2 расширяет этот набор: Naked/Hidden Quad, X-Wing, Skyscraper,
2-String Kite, Turbot Fish, Empty Rectangle, Swordfish, XY-Wing, XYZ-Wing,
W-Wing и Jellyfish. Каждая техника возвращает все найденные полезные шаги через
`find_steps(state)` без изменения state. После каждого применения поиск начинается
с самой простой техники; выбор шага детерминирован. Turbot Fish ограничен двумя
conjugate pairs и одной соединяющей weak link. Phase 3 добавляет общий inference graph,
X-Chain, XY-Chain, AIC, continuous Nice Loop, Grouped AIC, ALS-XZ, ALS-XY-Wing,
ALS Chain, Forcing Chain и Nishio. Подробности и проверки: [отчёт Phase 3](docs/PHASE3_REPORT.md).

```python
from generator.solution_generator import generate_solution
from generator.clue_generator import generate_clue_mask, is_minimal
from generator.chromosome import Individual
from generator.solver.exact_solver import has_unique_solution
from generator.solver.human_solver import solve

solution = generate_solution(seed=42)
individual = Individual(generate_clue_mask(solution, seed=42), tuple(solution))
puzzle = individual.to_puzzle()
assert has_unique_solution(puzzle)
assert is_minimal(puzzle)
result = solve(puzzle)
print(result.solved, result.stuck)
```

Настройки и отчёт Human Solver:

```python
from generator.solver.human_solver import HumanSolver
from generator.solver.techniques import phase1_techniques, phase2_techniques
from generator.solver.advanced_config import AdvancedConfig

basic = HumanSolver(phase1_techniques()).solve(puzzle)
intermediate = HumanSolver(phase2_techniques()).solve(puzzle)
result = HumanSolver(weights={"X-Wing": 8.0}, config=AdvancedConfig()).solve(puzzle)
print(result.technique_counts, result.hardest_technique, result.max_rating)
print(result.total_score, result.intermediate_steps, result.advanced_steps)
print(result.chain_step_count, result.longest_chain, result.als_step_count, result.forcing_step_count)
```

Значения по умолчанию централизованы в
`generator/rating/registry.py` (`generator/solver/techniques/weights.py` — compatibility export).
`HumanSolveResult.total_score` — сумма квадратов рейтингов
шагов. `intermediate_steps` считает применения техник Phase 2, включая quads и
Jellyfish, независимо от пользовательских весов. `advanced_steps` считает техники
Phase 3. `longest_chain` использует число связей candidate chain/ALS RCC либо
глубину зависимости forcing proof; эти значения не являются единой шкалой сложности.
Метрики описывают выбранный логический путь,
а не доказанную минимальную сложность среди всех возможных путей.

`AdvancedConfig` ограничивает длины, число исследованных связей, размеры ALS и
глубину/объём forcing propagation. `HumanSolver.all_available_steps(state)` возвращает
выводы с дедупликацией внутри каждой техники в этих пределах;
`minimum_available_rating(state)` — рейтинг
первой доступной техники. Поиск сохраняет представительные доказательства, а не все
возможные цепочки. Достижение лимита не доказывает отсутствие логического хода.

`generator/tests/fixtures/phase2_puzzles.json` содержит три воспроизводимые задачи:
Phase 1 останавливается, Phase 2 решает их с X-Wing (seed 21), Swordfish (seed 227)
или XY-Wing (seed 3) в стандартном solution path. Они получены существующей
минимизацией `minimize_puzzle(generate_solution(seed=n), seed=n)`; происхождение
сохранено рядом с каждой строкой puzzle. Интеграционные тесты проверяют уникальность
исходной задачи, наличие техники, повторяемость, приоритет простейшего шага и полный
replay. Присутствие техники в этом пути не утверждает её необходимость во всех
альтернативных путях. Исторический regression с ожиданием `STUCK` использует
явный набор `phase1_techniques()`, сохраняя первоначальные проверки.

Поле — `list[int]` длины 81, пустые клетки — `0`. Некорректная форма/тип данных
вызывает `ValueError`. Exact solver возвращает `None`/`0`/`False` для противоречивых
исходных цифр; `count_solutions(grid, limit=2)` прекращает поиск по достижении лимита.
Входные поля не изменяются. `SudokuState` допускает явные логические исключения в
кандидатах, проверяет локальные противоречия и атомарно применяет изменения.

Минимальность означает, что нельзя удалить ни одну оставшуюся подсказку без потери
уникальности. Количество 17–20 подсказок не гарантируется. Полные поля получаются
из Latin pattern допустимыми перестановками; это не равномерная выборка всех Sudoku.

`generator/tests/fixtures/phase3_puzzles.json` содержит 7 сценариев для 4 уникальных
задач: Phase 1/2 останавливаются, полный Phase 3 решает все четыре. Отдельные
репертуары Phase 2 + одна техника проверяют X-Chain, XY-Chain, AIC, ALS-XZ,
Forcing Chain и Nishio; default seed 48 также использует Grouped AIC и ALS chains.
Воспроизводимость fixtures и ориентировочный профиль:

```console
python -m generator.tests.build_phase3_fixtures
python -m generator.tests.profile_phase3
```

Phase 3 не сертифицирует задачи как Extreme. Остановка Human Solver означает лишь,
что реализованных техник недостаточно. DFS используется только exact solver,
а человеческие техники не обращаются к нему или известному решению. Это проверяется
статически, ловушками Exact API и отдельным процессом с запретом импорта.
Phase 6 добавляет эволюцию и fitness. Они дают предварительных кандидатов;
Phase 7 отдельно проверяет логические proofs и альтернативные пути перед
production acceptance. Cell/Region/Dynamic Forcing остаются вне реализованного
набора техник. Phase 5 добавляет проверенный JSON export. Демонстрационная команда выводит seed puzzle
в консоль, без оценки Extreme.

## Phase 4: Difficulty Rating

Отдельный слой оценивает логическую сложность и предварительных кандидатов Extreme.
Полная архитектура, пороги, ограничения и результаты проверок:
[отчёт Phase 4](docs/PHASE4_REPORT.md).

```python
from generator.rating.difficulty import analyze_difficulty, DifficultyAnalyzer
from generator.rating.report import diagnostic_report
from generator.rating.profiles import BASIC_PROFILE, solve_with_profile, solve_with_max_rating

quick = analyze_difficulty(puzzle, mode="quick")
deep = analyze_difficulty(puzzle)  # Deep + отдельная проверка уникальности
print(diagnostic_report(deep, puzzle))
print(deep.is_extreme_candidate, deep.difficulty_profile)
basic = solve_with_profile(puzzle, BASIC_PROFILE)
limited = solve_with_max_rating(puzzle, 18)

# Только human analysis: exact solver не вызывается.
human_only = DifficultyAnalyzer().deep(puzzle)
```

Quick использует один путь и не подтверждает обязательность уровня или Extreme.
Deep перебирает разрешённые рейтинги по возрастанию до первого логического решения,
оценивает этот путь, проверяет minimum available rating в сложных состояниях и
объединяет повторные bottlenecks. Это свидетельство в рамках детерминированного
Human Solver с конечными лимитами, а не minimax-доказательство по всем путям.
Deep без проверки уникальности не присваивает Extreme/Ultra Extreme.

Числа совместимы с Phase 1–3: X-Wing=8, AIC=30, ALS-XZ=36.
Профили BASIC/INTERMEDIATE/ADVANCED/EXTREME ограничены tiers и по умолчанию дают
потолки 5.2/11/18/55. Исторический `phase2_techniques()` включает также ADVANCED
техники; номер фазы не равен tier. Новое `DifficultyResult.advanced_steps` считает
шаги с рейтингом ≥12, `extreme_steps` — ≥22. Старые HumanSolveResult-метрики не менялись.

`DifficultyConfig` задаёт registry, веса, формулу score, thresholds, detector budgets
и bounded cache. JSON: `DifficultyConfig.from_dict(config.to_dict())`.
`generator.rating.state_analysis.analyze_state(state)` возвращает все
представительные шаги в пределах detector budgets; `minimum_available_rating(state)`
возвращает только минимальный слой и явно помечает неполное перечисление альтернатив.
Числа clues и minimality остаются метаданными и не увеличивают rating.

```console
python -m generator.tests.profile_phase4
```

Fixtures: `generator/tests/fixtures/difficulty/regression.json`.
Эволюционный поиск, полный minimax и окончательная production certification не входят в Phase 4.

## Phase 5: обычный генератор и JSON export

Генератор создаёт полное solution, удаляет подсказки с проверкой уникальности,
при необходимости минимизирует, независимо перепроверяет uniqueness и передаёт
кандидат существующему DifficultyAnalyzer. Затем применяет фильтры clues/difficulty
и сохраняет принятые задачи. Эволюционный поиск описан ниже в разделе Phase 6.

Команды запускаются из корня проекта. Одна минимальная задача с широким диапазоном:

```console
python -m generator generate --seed 42 --count 1 --min-clues 17 --max-clues 30 --minimal --output data/single.json
```

Небольшая база и фильтрация по сложности:

```console
python -m generator generate --seed 42 --count 8 --max-clues 30 --output data/puzzles.json
python -m generator generate --seed 42 --count 5 --difficulty Easy --min-clues 35 --max-clues 40 --no-minimal --rating quick --output data/easy.json
python -m generator generate --seed 42 --count 2 --difficulty Expert --max-clues 30 --max-attempts 100 --rating quick_then_deep --timeout 120 --output data/expert.json
```

Последняя команда может закончиться неполной выборкой: случайное удаление подсказок
не гарантирует нужный уровень. По умолчанию диапазон равен 17–23, включена
минимизация, лимит — 100 попыток на весь batch. В режиме `--minimal` сначала
удаляются все избыточные clues, затем проверяется диапазон. Если минимальная задача
получилась ниже `--min-clues`, она отклоняется. Для более заполненных полей используйте
`--no-minimal`. Минимальность означает невозможность удалить любую одну подсказку,
а не минимально возможное количество подсказок.

`--rating quick` оценивает один логический путь. `deep` проверяет обязательный уровень
и bottlenecks в пределах реализованного bounded Human Solver. `quick_then_deep`
сначала выполняет Quick и запускает Deep для перспективных или не решённых Quick
кандидатов. Явно слабые кандидаты не требуют Deep. Если даже в режиме `quick`
случайно обнаружен кандидат с Extreme-level техникой, он проходит Deep перед
возможным сохранением. Quick с целевым Extreme/Ultra Extreme запрещён: эти классы
требуют Deep. Все оценки остаются preliminary; исчерпывающего minimax-доказательства нет.

Случайный Extreme/Ultra Extreme, не прошедший только целевой фильтр сложности,
сохраняется отдельно в `<output-stem>_preliminary.json` и не увеличивает число принятых
задач. Прогресс показывает attempts/accepted/best candidate, финальная статистика —
причины отказов и время этапов. Коды выхода: `0` — batch заполнен, `1` — найдено меньше
запрошенного, `2` — неверные параметры или ошибка экспорта. Неполный batch сохраняет
только принятые puzzles. При нуле принятых основной output остаётся прежним.
Timeout проверяется между этапами и попытками удаления clues: текущий вызов solver
не прерывается, поэтому фактическое время может превысить `--timeout`.

Python API:

```python
from generator import GeneratorConfig, generate_puzzle, generate_many
from generator.export import export_puzzles, validate_database

config = GeneratorConfig(seed=42, min_clues=17, max_clues=30,
                         require_minimal=True, rating_mode="quick_then_deep",
                         max_attempts=100)
puzzle = generate_puzzle(config)  # GenerationError.result содержит статистику при неудаче
batch = generate_many(8, config)  # BatchResult: puzzles, requested, seed, stats, complete
if batch.puzzles:
    database = export_puzzles(batch.puzzles, "data/puzzles.json")
    validate_database(database)
print(batch.complete, batch.stats.to_dict())
```

`GeneratedPuzzle` содержит ID, строки puzzle/solution, clue mask, clues, unique,
minimal, difficulty, rating, DifficultyResult, HumanSolveResult, seed и attempt seed.
Для Phase 6 доступны независимые `Individual(solution=solution, clue_mask=clue_mask)`
(используйте именованные аргументы), `remove_clues`, `minimalize`, `check_minimal`,
`validate_candidate` и `PuzzleGenerator.rate_candidate`. Они не зависят от CLI.
Поддерживается только `symmetry="none"`; unique обязательно.

Локальный RNG обеспечивает одинаковую последовательность попыток для одинаковых
seed/config/version. При `seed=None` фактический seed записывается в результат и JSON.
Время этапов, текущая дата экспорта и остановка по wall-clock timeout не входят в
гарантию воспроизводимости. Uniqueness cache использует solution вместе с clue mask,
rating cache — также режим и конфигурацию рейтинга. Exact duplicate puzzle strings
исключаются; эквивалентность под Sudoku transformations пока не проверяется.
ID — стабильный `puzzle-` плюс 20 hex символов SHA-256 строки puzzle, независимый от
позиции в batch и последующего изменения рейтинга.

JSON соответствует [DATA_FORMAT](docs/DATA_FORMAT.md), `schemaVersion=1`:
`schemaVersion`, `generatedAt` (UTC), `generatorVersion`, `puzzles`, `stats`.
В puzzles экспортируются обязательные поля, rating/minimal, difficultyData,
techniques/techniquesUsed, generatorSeed и дополнительные ratingMetadata/generationMetadata.
`hardestTechnique` и `difficultyData.hardestRating` означают подтверждённый обязательный
уровень и присутствуют только при verified Deep. Наблюдавшаяся самая сложная техника
всегда находится отдельно в `ratingMetadata.observedHardestTechnique/observedHardestRating`;
mode/scope/preliminary явно ограничивают смысл оценки. Это использование optional полей
существующей schema 1, без изменения обязательного frontend-контракта.

Перед записью export проверяет ID, отсутствие дубликатов, строки и корректность solution,
соответствие clues, фактическую уникальность и заявленную минимальность. Ошибка любой
задачи отклоняет всю запись; старый файл сохраняется. Запись UTF-8 с `indent=2` выполняется
через временный файл и атомарный replace. Порядок задач стабилен: difficulty, rating по
убыванию, clues, ID. Для побайтово одинакового JSON передайте фиксированный UTC
`generated_at` в `export_puzzles`; по умолчанию ставится текущая дата.

Причины отклонения: `NOT_UNIQUE`, `OUTSIDE_CLUE_RANGE`, `HUMAN_UNSOLVED`,
`WRONG_DIFFICULTY`, `DUPLICATE`. Статистика содержит число полных grids, attempts,
accepted, rejection counts и длительности этапов. Полный suite и диагностический профиль:

```console
python -m unittest discover -s generator/tests -v
python -m generator.tests.profile_phase5
```

Результаты smoke, реального batch и измерений: [отчёт Phase 5](docs/PHASE5_REPORT.md).

## Phase 6: Evolutionary / Memetic Search

```console
python -m generator evolve --seed 42 --population 32 --generations 30 --mode extreme --max-seconds 300 --output data/evolution_candidates.json
python -m generator evolve --seed 42 --population 200 --generations 100 --mode monster --min-clues 17 --max-clues 21 --max-seconds 600
```

Поиск однопроцессный. По умолчанию population=32, elites=3, offspring=32, четыре
complete grids и независимые порядки удаления clues. Несколько масок строятся на
каждом target solution. Большие популяции 200–1000 задаются явно: Deep Rating
может быть существенно дороже Quick. Полные решения пока принадлежат семейству
Latin-pattern transformations; это ограничивает разнообразие математических grids.

`--min-clues` / `--max-clues` задают целевой диапазон (17–21), а
`--search-max-clues` (32) разрешает промежуточные minimal seeds и ADD, иначе старт
с редких 17–21-clue задач был бы слишком дорогим. Summary показывает отдельно
лучшего Deep-кандидата и соответствие целевому профилю. Обычный экспорт сохраняет
лучшие предварительные кандидаты, в том числе вне целевого диапазона;
`--targets-only` ограничивает экспорт диапазоном и порогами профиля.

```python
from generator.evolution import EvolutionConfig, evolve, export_evolution, save_snapshot

config = EvolutionConfig.for_mode("extreme", seed=42, population_size=32,
    offspring_count=32, max_generations=30, max_seconds=300)
result = evolve(config)
print(result.seed, result.generations, result.stop_reason)
print(result.initial_best, result.best)
if result.archive:
    export_evolution(result, "data/evolution_candidates.json")
save_snapshot(result, "data/evolution_snapshot.json")
```

`EvolutionIndividual` ссылается на существующий неизменяемый `Individual`
(complete solution + 81-bit mask), добавляя unique/minimal, Quick/Deep results,
scalar fitness, objective vector, generation/operator/parents. После mutation
проверяются uniqueness и новый рейтинг. REMOVE, ADD, SWAP, MULTI-SWAP, region
(row/column/box) и bottleneck-guided mutation работают только с маской; веса
операторов, размеры multi-swap и budgets находятся в `EvolutionConfig`.
Редкий crossover допускает только одинаковый target solution, затем repair и
удаление лишних clues. Repair получает альтернативные Exact solutions и добавляет
target clue из реального difference set. Conflict sets переиспользуются только
для того же solution; random/coverage/guided стратегии задаются конфигурацией.

Quick оценивает все новые допустимые маски; Deep получает верхняя доля ещё не
проверенных кандидатов из общей популяции, offspring и injections с отдельным
лимитом на поколение. В archive и `result.best` попадают
только решённые кандидаты с проверенным Deep required level. Quick maximum
используется для выбора перспективных родителей и не считается обязательным
уровнем. Предварительный Quick tier использует ту же численную шкалу, что и Deep;
сама покупка Deep-проверки не даёт бонус tier. Human-unsolved имеет отдельный
статус и не получает высокий fitness.

`FitnessConfig` задаёт коэффициенты required tier/rating, genuine bottlenecks,
advanced/extreme steps, total score, chain complexity/length, ALS, forcing,
clues и minimality. Secondary metrics входят через `log1p`; clue bonus по
умолчанию `0.1 * (82 - clues)`, minimality bonus=0.1. Основной required-rating
weight=1000, поэтому сокращение clues не заменяет сложную логику. Objective vector
сохраняется независимо от scalar; ограниченный Pareto archive удерживает
non-dominated решения и крайние значения objectives. Исторический scalar champion
хранится отдельно: Pareto dominance не может его потерять. Экспорт включает и
champion, и архив с устранением дубликатов.

Tournament selection, неизменяемые elites, exact duplicate rejection,
near-duplicate penalty и зарезервированные random injections сохраняют diversity.
Stagnation усиливает mutation и вызывает injections. Ограниченный local swap
search оценивает реальные critical-clue deltas и принимает только улучшения;
если исходный кандидат Deep-rated, сосед тоже проходит Deep. Exhaustive 81×81
search и simulated annealing не используются.

Caches ограничены и включают solution+mask; rating cache учитывает полную rating
policy, fitness cache — также coefficients и minimality. Одинаковые seed/config
дают одинаковые решения и ordering. Wall-clock timeout и timings в гарантию
детерминизма не входят. Deadline проверяется между solver calls: текущий вызов
заканчивается до остановки. При раннем timeout `best` может быть `None`, population
частичной; уже проверенный archive сохраняется. Экспорт и независимые проверки
после поиска выполняются вне `--max-seconds`.

CLI сохраняет snapshot рядом с output (`*_snapshot.json`) либо по `--snapshot`.
Snapshot содержит archive, config, seed, generation, stats и timings; это
диагностический снимок, **без возобновления RNG/population**. Он использует отдельный
формат; puzzle JSON создаётся существующим Phase 5 exporter с повторной uniqueness,
minimality и human-path проверкой. `data/puzzles.json` команда evolve по умолчанию
не затрагивает. Неудачный или пустой экспорт сохраняет прежний puzzle-файл.

`EXTREME_SEARCH` требует rating≥30, bottlenecks≥2, advanced steps≥3,
Intermediate STUCK. `MONSTER_SEARCH`: rating≥36, bottlenecks≥3, advanced≥5,
chain length≥8 и подтверждённую минимальность. Числа соответствуют текущей registry
(AIC=30, ALS-XZ=36). `balanced` не требует этих порогов. `extreme` увеличивает веса
bottlenecks/advanced steps; `monster` также усиливает chains/ALS/forcing.
Экспериментальный `min_clues` использует clue weight=200000 и не изменяет политику
других режимов. Эти режимы ищут **кандидатов**: bounded Deep evidence не
является Phase 7 minimax или независимой production certification.

По поколениям сохраняются best/median fitness, required rating, bottlenecks,
advanced steps, clues, размер уникальной популяции и число уникальных масок,
число Deep-rated, diversity, mutation/repair success rates, archive size,
acceptance, injections и время. `stage_seconds` включает
Quick/Deep/uniqueness/mutation/repair/local_search;
seed construction, minimality и reduction включают вложенные uniqueness вызовы,
поэтому суммы этапов нельзя трактовать как независимые доли CPU.

Проверки и воспроизводимый эксперимент:

```console
python -m unittest discover -s generator/tests -v
python -m generator.tests.profile_phase6 --population 200 --generations 20 --max-seconds 600
```

Измерения, ограничения поиска и critical review: [отчёт Phase 6](docs/PHASE6_REPORT.md).

## Phase 7: независимая сертификация

```console
python -m generator certify --input docs/PHASE6_CANDIDATES.json --fresh --output data/production/puzzles.json --research-output data/candidates.json --reports-dir reports/certification
python -m generator certify --input docs/PHASE6_CANDIDATES.json --puzzle-id puzzle-ca88d658a18eafb27c24 --fresh
```

Прямая строка задаётся через `--puzzle`, необязательное решение — `--solution`.
`--config` читает CertificationConfig JSON; доступны overrides `--time-budget`,
`--node-budget`, `--state-budget`, `--max-path-depth`,
`--max-alternative-steps-per-state`, `--max-chain-length`, `--max-als-size`,
`--require-minimal`. По умолчанию кандидат получает 60 секунд.

Каждый кандидат проходит fresh uniqueness/minimality, повторное логическое
решение, независимую проверку proof и поиск альтернативных логических путей.
Исчерпание любого лимита означает inconclusive, если доказательство необходимого
уровня не завершено. Evolution/Deep labels не копируются в certified rating.
Числовая шкала прежняя: AIC=30, ALS-XZ=36. Сертифицируется уровень внутри
явно описанной модели техник; обязательность конкретного имени техники и
глобальная полнота всей человеческой Sudoku-логики не заявляются.

`data/production/puzzles.json` принимает только `CERTIFIED_EXTREME` и
`CERTIFIED_ULTRA_EXTREME`; `data/candidates.json` сохраняет research failures и
inconclusive вместе с исходными records. Полные proof/config/search diagnostics
записываются в `reports/certification`. IDs остаются прежними. Повторяющиеся IDs
или точные puzzle strings отклоняются до дорогой проверки.

Пустая production база допустима и означает отсутствие прошедших кандидатов.
CLI возвращает 0 при наличии certified, 1 при нуле, 2 при ошибке параметров/I/O.
Команда заменяет выбранный output, поэтому для отдельного диагностического
прогона задайте отдельные выходные пути. Входные файлы сохраняются.
Текущая demo-база `data/puzzles.json` и frontend loader остаются прежними;
`generate`/`evolve` экспортируют preliminary/research данные, без production
сертификата. Изменение frontend integration или deployment — отдельная работа.

Подробные gates, границы полноты и формат evidence:
[Certification Spec](docs/CERTIFICATION_SPEC.md).

## Phase 8 / Release 0.1: frontend и GitHub Pages

Frontend (`web/`, статический, без сборки и зависимостей) играет **только**
сертифицированные задачи из `data/production/puzzles.json` (`schemaVersion 1`,
`datasetKind: production-certified`). `data/puzzles.json` (demo Phase 5) во
frontend не загружается; он остаётся только фикстурой unit-тестов. Версия приложения
(0.1.0) хранится единственный раз — `web/package.json`; UI читает её оттуда.

Принимаются только записи со статусом `CERTIFIED_EXTREME` или
`CERTIFIED_ULTRA_EXTREME` (с совпадающей сложностью), валидными 81-символьными
`puzzle`/`solution`, согласованными givens и числом clues. Остальное пропускается с
`console.warn`. Ошибка загрузки показывает «Не удалось загрузить базу Sudoku.
Попробуйте обновить страницу.» (без fallback на mock), пустая база — «Сейчас нет
доступных сертифицированных Sudoku.»

Команды (из корня проекта; Node 20+ и Python 3.10+):

```console
# локальный запуск: открыть http://localhost:8000/web/
python -m http.server 8000

# тесты frontend (unit)
cd web && npm test

# повторная проверка production-базы (re-certification каждой записи; ничего не пишет)
python scripts/validate_production_database.py

# сборка для Pages: web/ + data/production/puzzles.json -> dist/ (относительные пути)
node scripts/build_pages.mjs
# проверка dist как на Pages: python -m http.server 8000 --directory dist

# browser/E2E/responsive (нужен: pip install playwright; python -m playwright install chromium webkit)
python web/tests/browser_regression.py
```

`scripts/build_pages.mjs` — единственный способ получить опубликованные данные:
из `dist/data/production/puzzles.json` удаляются `certification.evidence` и
`certification.config` (≈99% размера), добавляется компактный `hardestStep`.
Ручных копий нет; `dist/` в `.gitignore`.

Деплой: `.github/workflows/pages.yml` (push в `main` или ручной запуск): frontend
tests → `validate_production_database.py` (при ошибке сборка падает) → `build_pages.mjs`
→ `upload-pages-artifact` → `deploy-pages`. Генератор и сертификация в workflow не
запускаются. Один раз в репозитории на GitHub: Settings → Pages → Source:
**GitHub Actions**. Сайт будет доступен по адресу вида `https://<owner>.github.io/<repo>/`
(корень — `dist/index.html`); URL репозитория в проекте не задан. Новые задачи
добавляются только через `python -m generator certify ...` (Phase 7) и коммит
`data/production/puzzles.json`.

Подробности, измерения и ограничения: [docs/PHASE8_RELEASE_0_1_REPORT.md](docs/PHASE8_RELEASE_0_1_REPORT.md).

Фактический деплой Release 0.1.0: репозиторий https://github.com/shell322dll/extreme-sudoku, ветка main, Pages (источник - GitHub Actions) публикуется workflow `pages.yml`: https://shell322dll.github.io/extreme-sudoku/. Источник данных - `data/production/puzzles.json` (1 задача, CERTIFIED_EXTREME). Файлы `*.py` хранятся без нормализации окончаний строк (`.gitattributes`): fingerprint сертификации хэширует их байты.

