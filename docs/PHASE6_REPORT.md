# Phase 6 — Evolutionary / Memetic Generator

Phase 6 завершена в пределах описанных ниже bounded-search требований.
Phase 7 не начата. Реализация, которая уже находилась в папке при начале этого
диалога, проверена и доработана; исходный незавершённый отчёт заменён этим.

## 1–3. Baseline и полный regression suite

- Исторический baseline до Phase 6: **230 tests, OK, 56.059 s**;
  wall **56.6102206 s**, [исходный лог](PHASE6_BASELINE_TESTS.txt).
- На входе в текущий диалог уже существовало 260 тестов:
  230 Phase 1–5 + 30 evolution. Все прошли за **85.199 s**,
  wall **85.7493192 s**, [текущий baseline](phase6_baseline_current.txt).
- Итог: **269 tests, OK, 85.488 s**, wall **85.9672994 s**,
  [полный лог](PHASE6_FINAL_TESTS.txt). Все исторические 230 тестов сохранены.
- Отдельная Phase 6 проверка: **39 tests, OK, 29.714 s**.
  В этом диалоге добавлено девять регрессионных тестов.

Команда: `python -m unittest discover -s generator/tests -v`.
Среда: Python 3.11.9, Windows; внешние пакеты не устанавливались.
Репозиторий Git в папке не обнаружен, поэтому commit/diff не создавался.

## 4. Individual

Существующий immutable `Individual` остаётся chromosome:
complete solution tuple + 81-bit clue mask. `EvolutionIndividual` хранит ссылку
на него, unique/minimal, Quick/Deep DifficultyResult, scalar fitness,
fitness vector, status, generation, operator и parent_keys. Clue count вычисляется
из маски. Mutable legacy ratings копируются, чтобы не делить состояние
кэша/родителей. Отдельной несовместимой модели puzzle нет.

## 5. EvolutionConfig

Централизованы seed, population/elite/offspring/tournament sizes, crossover rate,
mutation weights, multi-swap sizes, random injection count/interval, generations,
clue limits, Quick/Deep budgets, local-search budgets, stagnation threshold/strength,
runtime, caches/archive limits, repair policy, mode, FitnessConfig и DifficultyConfig.
Конфигурация immutable, валидируется и сериализуется в JSON.

Defaults: population=32, elites=3, offspring=32, tournament=5, crossover=0.1,
четыре complete solutions, injection=3 каждые 5 поколений, max_generations=30,
target clues=17–21, exploratory ceiling=32, Deep fraction=0.05 и максимум 2
новых staged Deep кандидата за поколение; local search — 1 child × 3 соседей;
stagnation=8, strength=2, repair limit=5, cache=4096, archive=100.
В CLI elites/injections адаптируются к размеру популяции.

BALANCED использует базовые веса. EXTREME повышает веса bottlenecks/advanced.
MONSTER дополнительно повышает chain/ALS/forcing веса. MIN_CLUES — отдельный
экспериментальный пресет; он не меняет другие режимы.
Прямой `EvolutionConfig(mode=...)` согласован с `for_mode`.

Начальная population использует несколько complete solutions и независимые
порядки удаления clues с приватным seeded RNG. Random injections получают новые
solutions. Seeds минимальны или near-minimal; не используются готовые сложные fixtures.

## 6. Mutations и crossover

REMOVE, ADD, SWAP, MULTI-SWAP 2↔2/3↔3, REGION (row/column/box), GUIDED.
Все операции изменяют только маску, сохраняют solution и проверяют границы.
На пустой/полной границе невозможная операция безопасно становится no-op.
При stagnation сила mutation повышается.

GUIDED использует genuine bottleneck с наибольшим required rating, клетки с малым
числом кандидатов в его state signature и peers. Это локальная эвристика
влияния; отдельного предсказателя ALS/AIC-структур нет. После изменения рейтинг
и uniqueness пересчитываются.

Crossover допускается только для одинакового complete solution:
common = A & B, optional = A ^ B; optional включаются случайно.
Затем выполняются repair, clue reduction и validation. Mutation остаётся основным
механизмом; crossover имеет default probability 0.1.

## 7. Uniqueness repair

Exact solver получает до двух решений; из каждого отличного от target строится
difference mask. Добавляемая target-clue обязательно принадлежит одному из
непересечённых witnessed difference sets. Стратегии: random, maximum coverage,
guided coverage с предпочтением не затрагивать bottleneck region.
Для каждой добавленной clue сохраняется witness.

ConflictStore ограничен и разделён по complete solution. Известные sets могут
переиспользоваться, но их пересечение не заменяет заключительный exact check.
При исчерпании repair budget неуникальный child отклоняется.
Invalid/corrupted, zero-solution, nonunique и clues<17 не компенсируются fitness.

## 8–9. Точная fitness formula и clue bonus

Обозначения: T — required tier (TRIVIAL=0, BASIC=1, INTERMEDIATE=2,
ADVANCED=3, EXTREME=4), R — hardest required rating, B — genuine bottlenecks,
A/E — advanced/extreme steps, S — total logical score, C — chain complexity,
L — longest chain, U/F — ALS/forcing steps, N — clues, M — confirmed minimality.

```text
fitness =
  10000*T + 1000*R
  + wB*ln(1+B) + wA*ln(1+A) + 10*ln(1+E)
  + ln(1+S) + wC*ln(1+C) + wL*ln(1+L)
  + wU*ln(1+U) + wF*ln(1+F)
  + wN*max(0,82-N) + 0.1*M
```

| Mode | wB | wA | wC | wL | wU | wF | wN |
|---|---:|---:|---:|---:|---:|---:|---:|
| balanced | 100 | 20 | 5 | 1 | 2 | 3 | 0.1 |
| extreme | 200 | 30 | 5 | 1 | 2 | 3 | 0.1 |
| monster | 300 | 40 | 20 | 5 | 10 | 15 | 0.1 |
| min_clues | 100 | 20 | 5 | 1 | 2 | 3 | 200000 |

Все коэффициенты переопределяются через FitnessConfig.
В основных режимах удаление clue даёт всего 0.1, единица required rating — 1000.
Поэтому 17-clue Easy не обгоняет 19-clue Extreme из-за clues.
Нет отдельной резкой премии за границу 21; диапазон применяется к target matching.
MIN_CLUES намеренно отдаёт приоритет clues и остаётся изолированным экспериментом.

Quick подставляет provisional observed rating и соответствующий provisional tier,
но B=0. Это сопоставимая численная шкала для поиска, не verified required level.
Quick не может стать reported best или записью verified Deep archive.
HUMAN_UNSOLVED имеет fitness=-infinity; статус не означает Extreme.

Fitness vector: (R, B, A+E, C, S, -N). Он хранится отдельно от scalar.
Поскольку advanced_steps уже включает extreme-level steps в Phase 4, A+E
намеренно дополнительно выделяет extreme steps.

## 10. Quick vs Deep

Каждый новый допустимый кандидат проходит exact uniqueness, затем Quick.
Staged Deep выбирает перспективных ещё не проверенных кандидатов из общего
pool: прежняя population, children и injections. Budget применяется к этому pool
один раз за поколение. Local search может дополнительно Deep-проверить соседей
в пределах собственного ограниченного бюджета.

Только solved verified Deep без guessing/backtracking попадает в archive/best.
Initial/final endpoints эксперимента повторно оценены свежими Deep analyzers
с одинаковой конфигурацией. Initial best — лучший среди первоначально Deep-rated
кандидатов, не результат Deep-проверки всех 32 seeds.

## 11–12. Selection и elitism

Tournament выбирает лучшее adjusted fitness из случайного подмножества
до tournament_size=5. Near-neighbor penalty уменьшает давление к клонам.
Elites сохраняют chromosome без mutation; полученное Deep evidence может
обновить их оценку. Default — около 10% популяции.

## 13. Diversity

Identity = (solution, clue_mask); exact duplicates исключаются.
Hamming distance = (maskA ^ maskB).bit_count(). Near-duplicate penalty применяется
внутри одного target solution; default distance<4, penalty=0.02 на соседа.
Среднее попарное Hamming distance записывается в диапазоне 0–81, без нормализации.
Для unrelated random injections резервируются survivor slots.

Полной Sudoku symmetry canonicalization нет. Near-duplicates штрафуются,
а не безусловно запрещаются — это не обещание заданной нижней границы diversity.

## 14. Stagnation

После 8 поколений без роста verified scalar champion сила mutation возрастает
до 2, включая multi-swap, и запускаются дополнительные random injections.
Archive не сбрасывается. Исторический scalar champion хранится отдельно от
Pareto frontier и не может исчезнуть из-за другого objective ordering.

## 15. Memetic local search

Для лучших children исследуется ограниченное число single-swap соседей.
Принимается только положительная delta фактического рейтинга.
Если хотя бы один endpoint имеет Deep, оба сравниваются через Deep.
Critical-clue deltas, attempts/improvements и inclusive runtime сохраняются.
Exhaustive neighborhood и simulated annealing не реализованы.

## 16. Pareto archive

Принимает только unique human-solved verified Deep records.
Dominated кандидаты исключаются, nondominated trade-offs сохраняются.
При превышении capacity сохраняются scalar leader и endpoints по objectives,
затем остальные leaders. Archive bounded, поэтому не хранит весь исторический
недоминируемый фронт. Отдельный scalar champion не зависит от этой обрезки.
Экспорт объединяет champion и archive, устраняя duplicates.

## 17. Caches

Uniqueness, Quick и Deep ключи включают complete solution + mask.
Rating дополнительно учитывает mode и полную DifficultyConfig.
Fitness учитывает fitness/rating config, minimality и наличие Deep.
Кэши принадлежат одному run, при новом run создаются заново; между версиями
процесса не переносятся. Cached mutable ratings копируются.
Измеряются lookup/hit counts; hit rate имеет явный знаменатель.

## 18. CLI, export и checkpoint

```console
python -m generator evolve --mode extreme --seed 42 --population 32 --generations 10 --min-clues 17 --max-clues 21 --max-seconds 240 --output data/evolution_candidates.json
python -m generator evolve --mode monster --seed 42 --population 32 --generations 30 --targets-only --snapshot data/monster_snapshot.json
python -m generator.tests.profile_phase6 --seed 42 --population 32 --offspring 32 --generations 10 --max-seconds 240 --mode extreme --output docs/PHASE6_PROFILE.json --database docs/PHASE6_CANDIDATES.json --snapshot docs/PHASE6_SNAPSHOT.json
```

Компактный CLI показывает generation, clues, required rating, bottlenecks,
advanced steps, chain, target match и diversity. Diagnostic harness пишет
развёрнутые JSON records в log.

Используется Phase 5 exporter, schemaVersion=1: независимые uniqueness/minimality
проверки, реконструкция Human path, atomic write. Preliminary metadata сохранено.
`--targets-only` применяет target clue range и profile; обычный export также
сохраняет exploratory candidates с >21 clues. Пустой export не затирает файл.

Snapshot содержит seed/config/generation/archive/best/stats и timings.
Это минимальный checkpoint, **не resume**: RNG/full population continuation
и флаг --resume не реализованы. `data/puzzles.json` не перезаписывался.

## 19–29. Performance и реальный эксперимент

Числовые результаты финального прогона приведены в приложении ниже, первичные данные:
[profile](PHASE6_PROFILE.json), [log](PHASE6_PROFILE.log),
[candidates](PHASE6_CANDIDATES.json), [snapshot](PHASE6_SNAPSHOT.json).

Дополнительный контрольный прогон исходного engine:
32 individuals, seed42, 8 завершённых поколений за 186.579 s при мягком budget180 s.
Fresh Deep: required35→55, bottlenecks9→8, score11882.861→46602.532,
advanced13→29, clues23→25, longest chain19→19.
Финальный лидер — новый remove child generation7, не переоценённый initial seed.
Minimum clues22; required max55; bottleneck max9; longest max19.
Target17–21 matches=0. Это контроль исходной реализации, а не итог новых весов.
Артефакты: [audit profile](PHASE6_AUDIT_PROFILE.json).

## 30. Известные ограничения

- 17–21 clues остаётся трудной вторичной целью; exploratory seeds разрешены до32.
- Complete grids происходят из существующего Latin-pattern family; распределение
  не равномерно по всем Sudoku. Нет symmetry canonicalization.
- Deep подтверждает уровень только в рамках deterministic bounded Human Solver;
  не перебираются все логические пути. Длина forcing proof и chain links —
  разные структуры, не единая физическая мера.
- Initial best выбран по selective Deep; сравнение не доказывает превосходство
  над неизвестным Deep maximum всех первоначальных seeds.
- Таймер кооперативный: текущий solver call может закончиться позже deadline.
  Export и независимые повторные Deep проверки выполняются вне search budget.
- Timings inclusive: local search включает rating/uniqueness, seed construction
  и minimality включают uniqueness. Проценты этапов нельзя суммировать как
  независимые CPU shares. Основная стоимость — Human Rating, особенно Deep.
- Нет multiprocessing, annealing и resumable checkpoint; для первой версии
  они не обязательны. Fixed-seed determinism проверен без wall-clock cutoff.

## 31. Что требуется в Phase 7

Отдельно определить final certification policy и production dataset criteria;
проверять альтернативные logical paths и минимально необходимую сложность в
явно ограниченном/исчерпывающем certification workflow; проводить независимую
финальную проверку и отбор production puzzles. Не принимать evolution fitness
или HUMAN_UNSOLVED за сертификат Extreme. Phase 7 здесь не реализована.
Frontend integration и deployment не выполнялись.

## 32. Финальный critical review

[Полный review](PHASE6_REVIEW.md) фиксирует найденные дефекты и их исправления:
несопоставимые Quick/Deep scales, Deep starvation, декоративные modes,
потеря scalar champion через Pareto, stale minimality evidence, CLI export gate,
разные уровни evidence в local search и недостающая telemetry.

Независимый reviewer проверил основные изменения. Его последняя итерация была
прервана лимитом сервиса; оставшиеся edge cases исправлены и перепроверены
основным агентом. Все 269 тестов проходят; блокирующих замечаний в выполненном
review не осталось. Это critical code review, не Phase 7 certification.

## Числовое приложение: итоговый эксперимент

Seed=42, population=32, offspring=32, mode=extreme, 10 generations,
max_seconds=240. Завершены все **10 поколений**;
stop_reason=`max_generations`, search wall=234.405 s.
Проверка экспорта и fresh Deep endpoints успешно завершились после поиска.

| Метрика | Initial verified best | Final verified best |
|---|---:|---:|
| Required rating | 35 | 55 |
| Required technique | Grouped AIC | Nishio |
| Genuine bottlenecks | 9 | 8 |
| Total logical score | 11882.861 | 44277.826 |
| Advanced steps | 13 | 30 |
| Extreme steps | 12 | 30 |
| Clues | 23 | 25 |
| Longest chain | 19 | 12 |
| Chain complexity | 190 | 349.5 |
| ALS steps | 0 | 7 |
| Forcing steps | 0 | 6 |
| Scalar fitness | 75609.978 | 95635.061 |
| Bounded candidate class | Extreme | Ultra Extreme |

Final leader — **новый REMOVE child поколения 10**, не delayed Deep начального seed.
Ранее LOCAL_SWAP поколения 3 тоже улучшил лидера; всего local improvements=2
при 30 local attempts (6 допустимых rating deltas). Это подтверждает работу mutation
и memetic search, а не только переименование Quick в Deep. Улучшение частичное:
required rating, total score, advanced/ALS/forcing выросли, но bottlenecks,
clues и longest chain ухудшились. Приоритет difficulty над clues сохранён.

Initial puzzle:
```text
050000700000028000090600000670000009000300006900010250200040010030000005700050030
```

Final puzzle:
```text
050030000000028000090600000671000009000304006003010250200000010030007005700050030
```

Общие экстремумы по deduplicated final population/archive/champion:

- Minimum clues: **22**, в том числе среди Deep-rated.
- Maximum required rating: **55**; strongest required technique — **Nishio**.
- Maximum genuine bottlenecks: **9**.
- Maximum longest chain: **19**.
- DifficultyAnalyzer Extreme candidates: **15**, из них **11 Ultra candidates**
  (счётчики пересекаются; это bounded preliminary labels).
- Полный target Extreme с 17–21 clues: **0**.
- Полный target Monster с 17–21 clues и minimality: **0**.
- Pareto archive: **4**; экспортировано **4** задачи. Все прошли fresh exact
  uniqueness и проверку minimality; две minimal, две non-minimal.

Таким образом, preliminary Extreme/Ultra Extreme найдены вне целевого clue range;
целевой low-clue Extreme/Monster за этот ограниченный run не найден.
Сертифицированных production задач Phase 6 не заявляет.

### Производительность

Generation mean **22.482 s**, median **15.102 s**, min **7.307 s**,
max **48.199 s**. Инициализация не включена в mean generation time.
Fresh initial Deep: **2.715 s**; fresh final Deep: **19.321 s**.

| Этап | Seconds | % search wall |
|---|---:|---:|
| Uniqueness cache/exact calls | 2.257 | 0.96% |
| Quick Rating | 83.840 | 35.77% |
| Deep Rating | 143.722 | 61.31% |
| Repair (включая alternative exact calls) | 0.637 | 0.27% |
| Local search (inclusive) | 8.843 | 3.77% |
| Seed construction (inclusive) | 0.947 | 0.40% |
| Crossover reduction (inclusive) | 0.757 | 0.32% |
| Minimality (inclusive) | 0.184 | 0.08% |
| Mutation | 0.027 | 0.01% |

Этапы вложены, поэтому их проценты **нельзя суммировать**.
Основной bottleneck: Quick+Deep human rating — около 97.08% search wall.
Deep выполнялся 22 раза против 362 некэшированных Quick calls.

| Cache | Hits / lookups | Hit rate |
|---|---:|---:|
| Uniqueness | 237 / 4906 | 4.83% |
| Quick | 21 / 383 | 5.48% |
| Deep | 0 / 22 | 0.00% |
| Fitness | 18 / 425 | 4.24% |

Низкий hit rate соответствует большому числу новых masks, а не отключённым caches.
Repair: **290 / 302 = 96.03%** успешных, добавлено 666 clues суммарно за run.
Mutation calls: 351, crossover attempts: 32, duplicate rejections: 19.
В statistics success означает valid evaluated child, не обязательный рост fitness.
Per-generation rates и raw stage counters сохранены в profile/snapshot.
Stagnation response покрыт deterministic integration test; в этом run
8-поколенный порог не был достигнут.

Финальные артефакты используют тот же schema-v1 экспорт и остаются под `docs/`;
публичная база не заменялась.
