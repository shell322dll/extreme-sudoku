# Extreme Sudoku — Phase 1–6 Technical Report

Дата независимого анализа: **2026-09-30**, Europe/Moscow. Рабочая папка: `C:\Develop\Extreme Sudoku`.

- Current commit hash: **недоступен** — в переданной папке Git repository не обнаружен.
- Current branch: **недоступна** по той же причине.
- Найденные phase tags: **проверить невозможно**; это не утверждение, что теги никогда не существовали.
- Python: **3.11.9**, Windows.
- Основная проверка: `python -m unittest discover -s generator/tests -v` из корня проекта.
- Дополнительные проверки frontend: `node --test web/tests/game.test.js` и browser regression согласно [web/VALIDATION.md](../web/VALIDATION.md).
- Область изменений этого аудита: только настоящий отчёт. Phase 7 и исправление production-кода не выполнялись.

## Executive Summary

Phase 1–6 образуют работоспособную исследовательскую систему: Exact Solver, 30 human detectors, bounded Quick/Deep rating, обычный генератор и evolutionary/memetic поиск. Текущий полный Python suite проходит: **269 passed, 0 failed, 0 skipped**, unittest **89.567 s**, wall **90.093 s**, warnings не обнаружены. Git chronology независимо восстановить нельзя; фактическая архитектура подтверждена кодом, границы фаз — сохранёнными отчётами и fixtures.

Preliminary Extreme и preliminary Ultra Extreme candidates существуют; initial и final best сохранённого Phase6 эксперимента заново воспроизведены текущим Deep Rating. Полноценного **Monster target match с 17–21 clues нет**; ближайший minimal Ultra candidate имеет 22 clues. Это не Production Certified Sudoku: required rating и genuine bottlenecks подтверждаются только внутри bounded deterministic repertoire. Главный незавершённый аспект — финальная независимая certification с явной политикой alternative logical paths и detector exhaustion. Доказанных CRITICAL ошибок корректности или anti-cheating нарушений не найдено. Инфраструктура пригодна для начала Phase7, но production release до выполнения certification gates заблокирован.

## Repository State

Проверены обязательные [AGENTS.md](../AGENTS.md), [README.md](../README.md), [PRODUCT_SPEC.md](PRODUCT_SPEC.md), [GENERATOR_SPEC.md](GENERATOR_SPEC.md), [UI_SPEC.md](UI_SPEC.md), [DATA_FORMAT.md](DATA_FORMAT.md), сохранённые phase reports/reviews/profiles/logs и frontend validation documents. Старые отчёты использованы как историческое свидетельство; текущие алгоритмы и defaults проверены непосредственно по коду.

Команды `git status`, `git log --oneline --decorate --graph`, `git tag` возвращают `fatal: not a git repository`. `.git` в дереве проекта не найден. Поэтому нельзя подтвердить current hash/branch, clean/dirty состояние, commits или создание phase tags. Сравнения **phase1-complete → phase2-complete**, **phase2-complete → phase3-complete**, **phase3-complete → phase4-complete**, **phase4-complete → phase5-complete**, **phase5-complete → phase6-complete** недоступны. Отсутствующая история не реконструируется вымышленными commits.

Сохранены [PHASE2_REVIEW.md](PHASE2_REVIEW.md), [PHASE3_REPORT.md](PHASE3_REPORT.md), [PHASE4_REPORT.md](PHASE4_REPORT.md), [PHASE5_REPORT.md](PHASE5_REPORT.md), [PHASE6_REPORT.md](PHASE6_REPORT.md), [PHASE6_REVIEW.md](PHASE6_REVIEW.md); profiles Phase3–6, Phase6 baseline/final logs, snapshots и candidates. Отдельный Phase1 report в папке не обнаружен. Исторические числа tests ниже — из документов, а не запуск отсутствующих Git snapshots.

Нумерация этапов [PRODUCT_SPEC.md](PRODUCT_SPEC.md), примерного плана GENERATOR_SPEC §57 и фактических Phase1–6 reports различается. В этом отчёте Phase1–6 означают этапы, подтверждённые сохранёнными phase documents/current compatibility repertoires; старый план не подменяет фактическую историю.

Read-only scope дополнительно проверен SHA256 inventory, снятым в начале аудита: существовавшие файлы `generator/`, `web/`, `data/`, `docs/` не изменились. Исключения инвентаризации — `__pycache__` и новый настоящий отчёт. Root README/AGENTS в этот hash inventory не входили; это не заявление о побайтовой проверке всего workspace. Диагностические логи и browser artifacts размещены в OS TEMP.

## Architecture Overview

```text
Extreme Sudoku/
├── generator/                    Python, offline generation
│   ├── sudoku/                   grid.py, candidates.py
│   ├── solver/                   exact_solver.py, human_solver.py, models.py
│   │   └── techniques/           singles, subsets, locked, fish, wings,
│   │                             single_digit_patterns, chains, als, forcing
│   ├── rating/                   registry/config/profiles, difficulty,
│   │                             state_analysis/mandatory/bottlenecks,
│   │                             classification/precertification/report
│   ├── solution_generator.py     complete valid solutions
│   ├── chromosome.py             immutable solution + clue mask
│   ├── clue_generator.py         original clue/minimal helpers
│   ├── construction.py           bounded removal/minimality
│   ├── config.py / models.py      ordinary generation contract
│   ├── pipeline.py / export.py    generation/filtering/JSON validation
│   ├── evolution/                config/models/engine/fitness,
│   │                             operators/repair/selection/io
│   ├── __main__.py               CLI
│   └── tests/                    unittest, fixtures, profiling commands
├── data/puzzles.json             sample exchange database
├── web/                          independent static HTML/CSS/JS application
│   ├── app.js / lib/             UI, game, storage, loading
│   └── tests/                    Node and browser regression
└── docs/                         specs, phase evidence, audit report
```

Generator и frontend взаимодействуют через schemaVersion=1 JSON; browser не выполняет тяжёлую генерацию или human rating. Exact Solver отделён от Human Solver; проверка уникальности не участвует в выводе logical eliminations.

`generator/sudoku/grid.py`: grid — независимый `list[int]`, ровно 81 элемент, строго целые 0..9 (bool отвергается), row-major; row=i//9, col=i%9, box=i//27*3+i%9//3. ROWS/COLS/BOXES, ALL_UNITS (27), UNITS (3 на клетку), PEERS (20 на клетку) вычисляются один раз, immutable tuples. `validate_grid` проверяет формат, `is_consistent` — повтор givens, `is_complete` — заполненность и consistency.

`generator/sudoku/candidates.py`: `ALL=511`, digit d соответствует `1<<(d-1)`. `SudokuState.grid` + `candidates` — mutable lists; filled cells имеют mask=0. Явные masks могут сохранять прошлые логические eliminations. Проверяются несовместимость givens, пустые/запрещённые masks, отсутствие поддержки цифры в unit. Это локальная consistency, не доказательство существования решения. `copy` независим; signature=(tuple(grid),tuple(candidates)), поэтому одинаковые givens с различными eliminations — разные состояния. place/eliminate применяются атомарно через trial copy и validate, place обновляет peers. Полный copy/validate — заметная стоимость; incremental human state/undo отсутствуют, корректность здесь приоритетнее.

## Phase 1 Summary

**Цель:** Sudoku engine и базовая человеческая логика. Текущий код и frozen `phase1_techniques()` подтверждают Grid/units/peers, bitmasks/SudokuState, MRV Exact Solver/uniqueness, full solution generation, clue-mask chromosome, clue removal/minimal puzzle и 8 detectors: Full House, Naked/Hidden Single, Locked Candidates, Naked/Hidden Pair/Triple.

Архитектурные решения: flat 81 cells, immutable topology, exact/human boundary, deterministic easiest-first human path, отдельные solution/clue generators. **46 исторических tests** упомянуты только ретроспективно в Phase2 review; отдельного Phase1 snapshot/tag/report нет. Нельзя независимо утверждать точный состав всех файлов/коммитов на конец Phase1.

## Phase 2 Summary

**Цель:** расширить базовую логику fish/wings/single-digit patterns. [Phase2 review](PHASE2_REVIEW.md) и текущий `phase2_techniques()` подтверждают 12 добавленных detectors: Naked/Hidden Quad, X-Wing/Swordfish/Jellyfish, Skyscraper, 2-String Kite, Turbot Fish, Empty Rectangle, XY/XYZ/W-Wing; всего 20. Coloring из старого плана не реализован.

**Документальный итог:** 100 tests, 3.365 s, OK; сохранены 46 прежних. Три реальные unique fixtures: Phase1 STUCK, Phase2 SOLVED. В review также сохранены independent soundness checks: 300 candidate states/8995 deductions и 200 one-digit states/285 deductions с exhaustive single-digit templates. Эти дополнительные исторические проверки не выдаются за повторно выполненный аудитом run.

Решения: frozen comparison repertoires, общий источник weights, no general chains на этом этапе, deterministic replay и tests exact/human boundary. Git diff Phase1→2 отсутствует.

## Phase 3 Summary

**Цель:** advanced human proof machinery. [Phase3 report](PHASE3_REPORT.md) и текущий код подтверждают X-Chain, XY-Chain, AIC, continuous Nice Loop, Grouped AIC, ALS-XZ, ALS-XY-Wing, ALS Chain, Forcing Chain, Nishio — всего 30 canonical techniques. ALS/forcing фактически появились здесь, хотя GENERATOR_SPEC §57 относил их к более поздним этапам.

**Документальный итог:** 149 tests, 36.816 s, OK. Fixtures: 7 сценариев на 4 unique Sudoku (seeds 4/29/193/48), including restricted repertoires; наличие техники в fixture path не доказательство её глобальной необходимости. Архитектура: inference graph и bounded BFS, ALS/RCC endpoint theorem, single-assumption propagation, immutable proof metadata, budget limits, independent oracle tests и guarded imports. Evolution/minimax/certification не относятся к этой фазе. Git diff Phase2→3 отсутствует.

## Phase 4 Summary

**Цель:** отдельный Difficulty Engine. [Phase4 report](PHASE4_REPORT.md) подтверждает immutable registry/config, четыре profiles, Quick/Deep, ascending required thresholds, state minima/cache, genuine crisis grouping, preliminary classification и regression corpus. Текущая реализация этих компонентов подробно разобрана ниже.

**Документальный итог:** 184 tests, 57.790 s, OK. Архитектурное решение: честно отделить observed greedy path от required level внутри bounded deterministic repertoire; uniqueness — отдельный gate, production/minimax не заявлены. Историческое review исправление transitive bottleneck grouping подтверждается текущим regression test `A, cheap, B, A`. Git diff Phase3→4 отсутствует.

## Phase 5 Summary

**Цель:** ordinary generator как полный pipeline, CLI и validated export. [Phase5 report](PHASE5_REPORT.md) подтверждает config/models/construction/pipeline/export, batch/attempt seeds, target filtering, minimality и partial failure reporting. Evolution в Phase5 ещё не относится к реализованному scope.

**Документальный итог:** 230 tests, 57.417 s, OK. Зафиксирован sample batch seed42: 8 minimal unique puzzles, 23–26 clues; классы Easy/Medium/Expert. Данные не объявлялись production Extreme. Архитектура сохраняет Exact/Human/Difficulty separation и DATA_FORMAT contract; текущие значения defaults проверяются по коду ниже, version из старого отчёта не применяется автоматически. Git diff Phase4→5 отсутствует.

## Phase 6 Summary

**Цель:** evolutionary/memetic поиск на clue masks. [Phase6 report](PHASE6_REPORT.md) и [review](PHASE6_REVIEW.md) подтверждают population, mutations/crossover, alternative-solution repair, staged Quick/Deep, fitness, tournament/elitism/diversity/injection, bounded local search, Pareto archive, caches и диагностический snapshot. Возобновляемый checkpoint и multiprocessing **NOT IMPLEMENTED**.

**Документальный итог:** 269 tests, 85.488 s (wall85.9672994), OK; отдельный evolution блок 39 tests. На входе в сохранённый Phase6 диалог уже было 260 tests; документ сообщает 9 новых regression tests. Без Git нельзя восстановить отдельные commits этого промежуточного состояния. Принципиально: только Deep verified кандидаты становятся reported best/archive; final certification Phase7 отсутствует. Реальный bounded эксперимент и audit caveats представлены ниже. Git diff Phase5→6 отсутствует.

## Exact Solver

`generator/solver/exact_solver.py`: `_search` — MRV bitmask DFS. На каждом depth выбирается незаполненная клетка с минимальным bit_count допустимых digits; zero candidates => branch fails. In-place board и row/col/box masks, перестановка списка empty и undo через XOR, без deepcopy. Digit order ascending, deterministic. Конфликт givens => 0 solutions. API `solve_one`, `count_solutions(limit=2)`, `has_unique_solution`, дополнительно `collect_solutions(limit=2)` для generator repair. Count/collect прекращаются сразу на limit. Malformed input/invalid limit => ValueError. Нет отдельного propagation queue или поддерживаемого массива incremental candidates: MRV пересчитывает masks из occupancy на каждом посещении. Singleton MRV работает как немедленное принуждение в DFS. Exact стоимость нигде не становится human difficulty.

Core READY для текущего scope, Exact READY. Не обнаружено доказанного неправильного решения/счёта при code review. Tests: test_grid.py, test_candidates.py, test_exact_solver.py (unique, complete, no solution с/без duplicate givens, multiple, early limit, malformed), collect witnesses дополнительно evolution tests.

## Human Solver

`generator/solver/human_solver.py:30` сортирует detectors по `(difficulty,name)`. В каждом состоянии берётся первая техника с deductions, внутри неё минимальный `step_key`; после применения перезапуск с простейшей. Вход/шаги не мутируются; `apply_step` атомарно проверяет наличие targets/progress и применяет к копии. Результаты solved/stuck/invalid различаются, malformed grid — API error. Exact fallback отсутствует.

`LogicStep` immutable: technique, rating, placements, eliminations, premises, explanation, search_complexity, chain, grouped_nodes, als, assumptions, contradiction. CandidateNode — OR кандидатов одной цифры, ChainLink — strong/weak edge + reason. Chain.length — количество inference links, для ALS — RCC links; forcing chain_length — максимальная глубина dependency proof (не количество facts). `HumanSolveResult` хранит path, solved/stuck/invalid/grid, hardest technique/max_rating, total_score, technique counts, intermediate/advanced/chain/ALS/forcing counts, longest chain; guesses=0, used_backtracking=False. Flags отражают архитектурный контракт, сами по себе не инструментированное доказательство отсутствия поиска.

Важная совместимость: `HumanSolveResult.advanced_steps` — исторически только 10 Phase-3 techniques (X-Chain и выше); `DifficultyResult.advanced_steps` — все шаги с rating>=12, включая Swordfish/Wings/Jellyfish. Аналогично `HumanSolveResult.total_score=Σ step.rating²`, а DifficultyResult добавляет структурные бонусы. Для fitness/report следует читать DifficultyResult, не смешивать два смысла.

### Anti-cheating audit

Runtime imports/calls в human_solver.py, sudoku/, techniques/ не обращаются к known solution, exact solver, count_solutions или unrestricted DFS/backtracking. `chains.py` ищет пути в логическом inference graph, `als.py` — цепочки theorem-valid RCC; это не перебор заполнений Sudoku. `forcing.py` допускает ровно одно предположение, из него exactly-one clause exclusions/last-support; нет recursive secondary guess. Исчерпание budget устанавливает limited/возвращает найденное, не трактуется как contradiction.

Единственный exact call внутри rating — `rating/precertification.py:8`, отдельный uniqueness gate после human анализа; возвращаемый solution не передаётся solver. `DifficultyAnalyzer.deep` по умолчанию check_unique=False; публичный `analyze_difficulty` по умолчанию mode=deep/check_unique=True. Quick ignore uniqueness и не сертифицирует Extreme.

Доказательства tests: `test_phase3_integration.test_runtime_exact_api_traps_for_all_advanced_detectors` подменяет solve_one/count_solutions/has_unique_solution на exceptions, проверяет все advanced detectors и реальное solve; static AST forbidden imports/calls + clean subprocess guarded import; test_phase4_integration дополнительно отделяет optional gate от Quick/Deep. Independent solution oracle используется только tests, где все placements/eliminations сверяются с ним. `test_advanced_soundness` создаёт 18 varied candidate states и требует >1000 deductions, покрывая каждую advanced technique; oracle не передаётся detector. Также есть proof replay для graph и forcing rules, ALS локальная независимая enumeration.

CRITICAL anti-cheating violation не обнаружено. Это code/test audit текущего repertoire, а не формальное доказательство отсутствия всех возможных ошибок. Test oracle по одному solution не доказывает preservation всех solutions для каждого мыслимого multi-solution state.

## Implemented Techniques

Источник чисел: `generator/rating/registry.py`; это внутренняя legacy шкала (AIC=30), НЕ Sudoku Explainer/SE 8.x/9.x. Всего 30 canonical detector names. По умолчанию base_rating=weight для каждого:

| Tier | Техника → base_rating = weight | Реализация и tests |
|---|---|---|
| TRIVIAL (0) | Full House .5; Naked Single 1; Hidden Single 1.2 | singles.py; test_techniques.py |
| BASIC (1) | Locked Candidates 2; Naked Pair 3; Hidden Pair 3.2; Naked Triple 5; Hidden Triple 5.2 | locked_candidates.py (Pointing + Claiming), subsets.py; test_techniques.py |
| INTERMEDIATE (2) | Naked Quad 7; Hidden Quad 7.2; X-Wing 8; Skyscraper 9; 2-String Kite 9.2; Turbot Fish 10; Empty Rectangle 11 | subsets/fish/single_digit_patterns.py; test_quads, test_fish, test_single_digit_patterns |
| ADVANCED (3) | Swordfish 12; XY-Wing 14; XYZ-Wing 16; W-Wing 17; Jellyfish 18 | fish/wings.py; test_fish, test_wings |
| EXTREME (4) | X-Chain 22; XY-Chain 25; AIC 30; Nice Loop 32; Grouped AIC 35; ALS-XZ 36; ALS-XY-Wing 39; ALS Chain 42; Forcing Chain 50; Nishio 55 | chains/als/forcing.py; test_chains, test_als, test_forcing, test_advanced_soundness, test_phase3_integration |

Все перечисленные detectors IMPLEMENTED в указанном ниже scope. Названия `INTERMEDIATE_TECHNIQUE_TYPES`/`ADVANCED_TECHNIQUE_TYPES` в solver/techniques/__init__.py — исторические Phase2/3 repertoires, НЕ текущие tiers. Phase1 repertoire=8, Phase2=20, default=30. Текущие Basic/Intermediate/Advanced/Extreme profiles через registry включают максимум 5.2/11/18/55 соответственно.

| Advanced logic | Статус | Точная поддержка и границы |
|---|---|---|
| X-Chain | IMPLEMENTED | Одноцифровый strong/weak inference graph, strong endpoints и исключение видящих оба endpoints кандидатов; bounded BFS. test_chains.test_x_chain и negatives |
| XY-Chain | IMPLEMENTED | Только bivalue cells, strong within cell, weak между видящими одноцифровыми nodes, одинаковая цифра endpoints; explicit 19-link cutoff test |
| AIC | IMPLEMENTED | Multi-digit inference graph, strong/weak endpoint conclusions; discontinuous strong/strong loop => placement, weak/weak => elimination; отдельные positive/negative tests |
| Nice Loops | PARTIAL | `Nice Loop` detector реализует continuous alternating loops; discontinuous loops реализованы как AIC. Полная неограниченная теория loops не заявляется; test_nice_loop/negative |
| Grouped AIC | PARTIAL | OR nodes только из box/row/column intersections, strong partition всех supports unit digit, weak требует conflict каждой пары members; arbitrary grouping отсутствует. Grouped detection обязан реально включать grouped node. test_grouped_aic/invalid_partition_and_visibility |
| ALS enumeration | IMPLEMENTED | N cells одной unit, N+1 candidate digits; canonical dedupe по cells, default size<=4; test_canonical_als, invalid, limits |
| ALS-XZ | PARTIAL | Два disjoint ALS, RCC all-to-all visibility, endpoint eliminations; overlapping ALS и дополнительные double-linked eliminations отсутствуют. Есть multicell exact-local-assignment oracle test |
| ALS-XY-Wing | IMPLEMENTED | Три disjoint ALS с различными последовательными RCC, endpoint theorem; positive и broken-RCC tests |
| ALS Chain | PARTIAL | 4..5 disjoint ALS по умолчанию; RCC adjacent digits должны различаться, проверяются endpoints; overlapping/general chain variants отсутствуют |
| Forcing Chain | PARTIAL | Два ветвления A / not A, в каждом only exactly-one clauses propagation; общие доказанные consequences. Нет nested assumptions/dynamic arbitrary technique propagation |
| Nishio | PARTIAL | Refutation одного true либо false candidate assumption по explicit opposite/two-true/empty-clause contradiction, не unrestricted contradiction search |
| Finned X-Wing/Finned Swordfish/Sashimi Fish | NOT IMPLEMENTED | Нет detectors/registry entries/tests |
| Simple Coloring/Multi Coloring/3D Medusa | NOT IMPLEMENTED | Нет отдельных detectors; некоторые выводы могут перекрываться AIC, но это не реализация именованных techniques |
| Unique Rectangle/BUG+1 | NOT IMPLEMENTED | Нет uniqueness-assumption techniques; allow_uniqueness_techniques toggle не нужен текущему repertoire и не реализован |
| Sue de Coq; Franken/Mutant/Kraken Fish | NOT IMPLEMENTED | Нет detectors |
| Cell/Region/Dynamic Forcing Chain | NOT IMPLEMENTED | Нет отдельных алгоритмов; binary candidate Forcing Chain не равнозначен полной поддержке этих families |

В таблице PARTIAL означает реализован строго ограниченный вариант family, а не заглушку. В частности ALS-XZ/Grouped AIC/forcing реально создают проверяемые deductions.

Точные `AdvancedConfig` defaults (`generator/solver/advanced_config.py:7`): max_x_chain_length=15; max_xy_chain_length=19; max_aic_length=19; max_grouped_aic_length=19; max_chain_search_nodes=100000; max_als_size=4; max_als_chain_length=5; max_als_search_nodes=30000; max_forcing_depth=12; max_forcing_nodes=2000; max_forcing_starts=160. NiceLoop использует max_aic_length. Все значения positive int, max_als_size<=8. ALS max_als_chain_length здесь число ALS sets, хотя LogicStep.chain_length считает links: default 5 sets => максимум 4 RCC links. 30000 отдельно ограничивает pair graph construction и traversal. Chain budget общий на detector call по всем стартовым nodes; BFS сохраняет representative shortest path per (start,node,next-link-kind), не все proofs. Forcing 160 — первые candidates в canonical cell/digit order, nodes/depth — на propagation branch.

## Difficulty Rating System

`TechniqueRegistry` immutable, entries сортируются по (base_rating,name), имена уникальны; ratings/weights finite nonnegative, tier order monotone. `base_rating` управляет solver order/profile/threshold, `weight` — стоимость шага. Overrides действительно передаются default_techniques(weights=...) => Technique.__init__ => LogicStep.rating=self.difficulty; ошибки разрыва registry/detector ratings не найдено. Config round-trips через JSON.

Quick (`difficulty.py:69`): один greedy solve полным bounded repertoire, собирает path metrics; не вычисляет required level/bottlenecks/uniqueness; high classes невозможны. Deep (`difficulty.py:75`): независимо перебирает все ascending thresholds из {0}∪registry ratings, каждый раз solve исходной puzzle c max_rating<=threshold; останавливается на первом SOLVED. Далее независимо запускает четыре profiles. Для метрик берёт solution именно lowest successful tested threshold, при неуспехе — Extreme profile path. Повторно replay path, на high states вычисляет minima и bottlenecks. Optional uniqueness gate выполняется отдельно.

`required_level.verified=True` означает, что все проверенные lower thresholds дали STUCK, а не INVALID. Это не minimax over all logical paths. Binary search намеренно не применяется: bounded detector behaviour не обязан быть монотонным при изменении раннего пути. `technique_necessity` отдельно сравнивает baseline и solve с technique disabled; hardest_required_technique — название hardest шага выбранного минимального threshold path, НЕ доказательство неизбежности именно этого имени. Test показывает AIC-floor=30 puzzle решается более тяжёлым repertoire после отключения AIC.

Точные формулы (defaults):

```text
branch_count(step) = Σ_proofs Σ_inferences max(0, len(parents)-1)
complexity(step) = 1.5*chain_length + 2.0*len(grouped_nodes)
                 + 1.0*(branch_count + max(0,len(assumptions)-1))
score(step) = registry.weight(technique)^2
            + complexity(step)
            + 4.0*bool(als)
            + 8.0*bool(assumptions)
            + 0.01*log1p(max(0,search_complexity))
total_score = Σ score(step)
quick.rating = hardest_observed_rating + 0.1*log1p(total_score)
deep.rating = hardest_required_rating + 0.1*log1p(total_score)
              + 0.05*bottleneck_severity + 0.1*distributed_advanced_steps
# deep.rating = 0 если required rating отсутствует
```

Прочие DifficultyConfig defaults полностью: advanced_threshold=12; extreme_step_threshold=22; bottleneck_threshold=12; extreme_threshold=30; ultra_threshold=36; minimum_advanced_steps=3; minimum_bottlenecks=2; ultra_minimum_advanced_steps=5; ultra_minimum_bottlenecks=3; ultra_minimum_chain=8; ultra_minimum_distributed_bins=2; late_fraction=.65; distribution_bins=4; cache_size=512. score_exponent=2, chain_length_factor=1.5, grouped_node_factor=2, branching_factor=1, als_bonus=4, forcing_bonus=8, search_complexity_factor=.01, total_rating_factor=.1, bottleneck_rating_factor=.05, distribution_rating_factor=.1. classification_thresholds=(Easy,0),(Medium,2),(Hard,7),(Expert,12). config.search=AdvancedConfig выше; config.registry=DEFAULT_REGISTRY.

Difficulty profile — list base_rating на каждом применённом шаге; advanced_steps count>=12, extreme_steps count>=22. High peak — первый advanced step или advanced step после <12; непрерывная серия advanced steps даёт один peak. peak_positions zero-based; late>=step_count*.65; advanced_distribution — 4 bins по индексу шага floor(i*4/N); distributed_advanced_steps — количество непустых bins, не количество ходов. chain_steps count bool(chain or assumptions), als_steps bool(als), forcing_steps bool(assumptions). longest_chain — max proof link/dependency depth по path, peak_rating — hardest observed.

Полная структура `DifficultyResult` (`rating/models.py:18`) по группам:

- status: solved, mode, difficulty_class, invalid, unique (None/True/False), minimal (None/True/False), used_backtracking, guesses, preliminary=True, scope;
- ratings: rating, hardest_technique, hardest_rating, hardest_required_technique, hardest_required_rating, minimum_tier, required_level_verified;
- path totals: total_score, step_count, advanced_steps, extreme_steps, chain_steps, longest_chain, chain_complexity, als_steps, forcing_steps, clue_count;
- bottlenecks: bottlenecks, true_bottleneck_count, max_bottleneck_rating, bottleneck_severity, late_bottleneck_count;
- profile: difficulty_profile, peak_rating, high_peak_count, peak_positions, late_peak_count, distributed_advanced_steps, advanced_distribution, state_signatures;
- analysis evidence: profile_statuses, threshold_results;
- eligibility: is_extreme_candidate, is_ultra_extreme_candidate.

Default scope literal: `deterministic bounded human solver; no exhaustive alternative-path proof`. `minimal` заполняет generator, DifficultyAnalyzer минимальность не проверяет. DifficultyResult сам не хранит LogicSteps/technique_counts, только summaries/signatures; HumanSolveResult хранит полную трассу. Для экспорта traces получают отдельно.

Classification использует hardest_observed в Quick, hardest_required в Deep, не составной result.rating. Unsolved/invalid => Unrated; Deep unverified => Unrated. Easy: floor<2, Medium 2<=floor<7, Hard 7<=floor<12, Expert floor>=12 если high class gates не пройдены. Preliminary Extreme требует одновременно Deep, solved, valid, unique is True, required_level_verified, used_backtracking=False, guesses=0, Basic STUCK, Intermediate STUCK, Extreme SOLVED, floor>=30, advanced>=3, genuine crises>=2. Preliminary Ultra дополнительно floor>=36, advanced>=5, crises>=3, longest_chain>=8, непустых bins>=2, хотя бы chain/ALS/forcing step. Clue count и minimality сами по себе НЕ gates rating classification (их задаёт generator acceptance). Один случайный X-Wing или высокий observed peak Extreme не дают. Class Expert допустим даже при observed/required AIC, если недостаточно crises/advanced steps.

## Bottleneck Detection

`StateAnalyzer.minimum_available_rating` последовательно посещает все lower rating layers и ВСЕ tied detectors первого доступного слоя; потом останавливается. `analyze_state` посещает все detectors. Каждый возвращённый deduction проходит `apply_step`; плохой detector не маскируется как STUCK. Summary: state_signature, techniques, minimum_rating, maximum_rating, minimum_technique, minimum_steps, steps, number_of_alternatives, enumeration_complete, scope. Minimum-only summary counts относятся только к minimum layer. LRU cache key=(grid+candidates signature, SolverProfile, полный immutable DifficultyConfig, minimum_only), default capacity=512, config/profile changes инвалидируют ключ; можно disabled cache=0/clear.

`bottlenecks.py`: valid применённый low step сам свидетель против high minimum, поэтому подробный анализ только перед applied rating>=12. Event существует, если обнаруженный minimum>=12. Bottleneck fields: step_index, state_signature, required_rating, required_technique, minimum_step_count, easier_steps_available=0, genuine=True, group_id, scope='bounded implemented techniques'. genuine относителен реализованным bounded detectors. Соседние high events группируются в одну crisis; повтор proof identity (technique,premises,chain,ALS,assumptions без effects/prose) в другом месте объединяется, включая transitive bridging. true_bottleneck_count = число групп; severity = сумма максимальных required_rating каждой группы; max_bottleneck_rating=max событий; late_bottleneck_count = группы с хотя бы event после .65 пути. Количество отдельных eliminations не выдаётся за число independent crises.

Ограничение: representative path/detector cutoff может пропустить cheaper deduction. ALSGraph.truncated существует, Propagation.limited существует в proof, но не передаются как общий exhaustion status в StateAnalysis/DifficultyResult; `enumeration_complete=True` при analyze_state означает проход всех detectors, а не exhaustive proof enumeration. `chains.py:180` возвращает найденное при exhausted global budget, `als.py:184` аналогично; отсутствие шагов из-за budget неотличимо наверху от исчерпания repertoire. Поэтому verified required level не гарантирует глобальную математическую необходимость и не должен стать final certification без дополнительного gate.

## Basic Generator

`GeneratorConfig` defaults: seed=None; min_clues=17; max_clues=23; target_difficulty=None; require_minimal=True; require_unique=True; max_attempts=100; rating_mode="quick_then_deep"; symmetry="none"; timeout_seconds=None; difficulty_config=DifficultyConfig(). Validated 17≤min≤max≤81; uniqueness нельзя отключить; symmetry только None/none; allowed rating modes quick/deep/quick_then_deep. Quick + explicit Extreme/Ultra target запрещены. Все тайм-ауты finite positive, budgets integer, bool-as-int rejected.

Pipeline (`pipeline.PuzzleGenerator`): для каждой попытки отдельный 64-bit attempt_seed из локального RNG run seed → `generate_solution(attempt_seed)` → immutable full `Individual` → случайный target clues в заданном inclusive диапазоне → shuffled sequential `remove_clues` с uniqueness каждого удаления → при require_minimal `minimalize(...target=0)` → строгий итоговый clue-range filter → fresh `validate_candidate` вне cache → exact string duplicate check → Quick/Deep rating → solved/invalid/no guessing/no backtracking filter → точное совпадение target class → проверка minimality → повторная реконструкция human path → `GeneratedPuzzle` → отдельный export.

`remove_clues` пробует каждую присутствующую clue один раз. Удаление принимается только если count_solutions(limit=2)==1. Цель может оказаться недостижимой. Один полный проход для minimality достаточен: два решения после неуспешного удаления сохранятся после последующих удалений других clues. `minimalize` target=0; `check_minimal` отдельно пробует удалить каждую оставшуюся clue. Minimal != minimum. Minimalization может пересечь min_clues вниз; затем кандидат честно rejected по диапазону. Финальная математическая проверка uniqueness свежая; промежуточная minimality может переиспользовать correctness-preserving cache; exporter повторяет claimed minimality независимо.

`solution_generator.generate_solution`: фиксированный Latin pattern `digits[(r*3+r//3+c)%9]`, row/column permutations within bands/stacks, band/stack permutations, digit permutation, optional transpose. Поэтому не просто неравномерная выборка: все генерируемые complete grids принадлежат одному классу эквивалентности этого базового grid. Разные seeds/solutions дают разные строки, но не новые структурные классы решений.

Quick/deep staging (`_rate_validated`): deep режим напрямую Deep; quick режим обычно Quick, но observed hardest≥extreme_threshold тоже отправляет в Deep. Default quick_then_deep выполняет Deep, если Quick не решился, observed hardest≥classification_thresholds[Expert], либо observed rating выше floor заданного класса и Quick class не совпал с target. Явно слабые кандидаты не тратят Deep. Нельзя интерпретировать quick режим как абсолютный запрет Deep.

Если target class не совпал, обычный кандидат rejected; прошедший остальные проверки Extreme/Ultra кандидат сохраняется отдельно в `BatchResult.preliminary_candidates`, а не незаметно засчитывается в accepted. Без target принимается любой solved rated class. Required difficulty не вычисляется по clues.

Batch `max_attempts=100` — общий бюджет всего batch, а не на каждую puzzle. `generate_many` возвращает partial `BatchResult(puzzles, requested, seed, stats, preliminary_candidates)`; complete определяется len(puzzles)==requested. `generate_puzzle` при неполном результате бросает `GenerationError` со structured batch. Reasons: NOT_UNIQUE, OUTSIDE_CLUE_RANGE, HUMAN_UNSOLVED, WRONG_DIFFICULTY, DUPLICATE. Invalid/Unrated/backtracking/guesses рейтинги агрегируются в HUMAN_UNSOLVED. Timeout отражается отдельно timed_out, не искусственным rejection reason. Stats: attempts, generated_complete_grids, accepted, причины, stage_seconds/stage_calls, elapsed/timed_out.

ID=`puzzle-` + first 20 hex SHA256(puzzle ASCII). Duplicates проверяются по полной 81-digit строке в данном batch и отдельно exporter. Не canonical symmetry hash; нет сравнения с ранее существовавшей базой при новом запуске.

Reproducibility: private random.Random; seed=None становится secrets.randbits(64), записывается в result; каждый batch restarting seed, caches очищаются, human state cache очищается. Seed/config/code одинаковы → puzzles/IDs/ratings одинаковы; wall clock stopping, timings, generatedAt исключены. Rating cache key включает solution+mask+mode+DifficultyConfig, records deep-copied, смена policy обновляет analyzer и invalidates старый cache.

CLI:

```text
python -m generator --seed 42
python -m generator generate --seed 42 --count 1 --min-clues 35 --max-clues 40 --no-minimal --rating quick --max-attempts 2 --output <TEMP>/sample.json
```

Legacy demo сохранён. generate defaults count=1, clues17–23, minimal=True, attempts100, output=data/puzzles.json; --difficulty, --rating, --timeout поддерживаются. Exit0 complete; exit1 partial/empty; exit2 ValueError/OSError. Partial batch экспортирует реальные accepted; empty не заменяет существующий файл. Preliminary сохраняются в `<stem>_preliminary<suffix>`. CLI меняет output только при явном запуске; аудит не запускает default writing command.

Export (`export.py`): schemaVersion=1; generatedAt UTC; generatorVersion="0.5.0" (также evolution); puzzles; stats.total/byDifficulty. Puzzle обязательные id/puzzle/solution/clues/difficulty/unique; далее rating/minimal/difficultyData/techniques/techniquesUsed/generatorSeed/ratingMetadata/generationMetadata. `hardestTechnique` и `difficultyData.hardestRating` записываются только для verified Deep required level; Quick observed metrics явно помещены в ratingMetadata. Allowed classes Easy/Medium/Hard/Expert/Extreme/Ultra Extreme. Формат совместим с DATA_FORMAT compact export; solutionPath optional в contract и НЕ экспортируется текущим compact exporter. Полные human steps существуют в in-memory GeneratedPuzzle; отдельного extended path export нет.

`validate_puzzle` проверяет ASCII length/alphabet, корректность полного решения, givens agreement, clue count, unique=True, class, numeric metadata, positive technique counts, fresh exact uniqueness и claimed minimality. `validate_database` проверяет root version/date/semver, duplicate IDs/strings, serializability без NaN. Unknown fields permitted. Нельзя считать эту structural/exact validation доказательством difficulty: она не делает fresh full Deep и не проверяет логический provenance числовых метаданных. Standard pipeline строит human path отдельно, evolution exporter реконструирует required-threshold path. Полная повторная независимая certification — будущий шаг.

Запись UTF-8 без BOM, indent2, tempfile в destination directory, flush/fsync, os.replace; validation/write failures сохраняют старый файл. Sort по class index, descending rating, clues, id. При заданном generated_at порядок input не влияет на bytes.

## Evolutionary Generator

Модули: config (политика), models (records), operators (mask mutations/crossover), repair (alternative-solution evidence), fitness (scalar/vector), selection (tournament/survivors/Pareto), engine (run/caches/budgets/telemetry), io (target_match/export/snapshot).

`Individual` — frozen dataclass: clue_mask int 0≤mask<2^81; solution — immutable validated complete tuple81; clue_count=mask.bit_count; puzzle[i]=solution[i], если соответствующий bit установлен. `EvolutionIndividual` — frozen wrapper: candidate, unique/minimal optional booleans, собственные deepcopied quick_rating/deep_rating, fitness=-inf, fitness_vector=(), status=UNRATED, generation=0, operator=seed, parent_keys=(). Identity `(solution, clue_mask)`; mutable rating objects копируются, но сами по себе не immutable. Known solution используется только для construction/uniqueness/validation, не logical eliminations.

### Все EvolutionConfig defaults

| Parameter | Default |
|---|---:|
| seed | None |
| population_size / elite_size / offspring_count | 32 / 3 / 32 |
| random_injection_count / injection_interval | 3 / 5 |
| max_generations / solution_count | 30 / 4 |
| min_clues / max_clues / search_max_clues | 17 / 21 / 32 |
| tournament_size / crossover_rate | 5 / 0.1 |
| multi_swap_sizes | (2,3) |
| mutation weights remove/add/swap/multi_swap/region/guided | .15/.10/.35/.20/.10/.10 |
| repair_limit / repair_strategy | 5 / coverage |
| deep_fraction / deep_candidates_per_generation | .05 / 2 |
| local_search_candidates / local_search_budget | 1 / 3 |
| stagnation_generations / stagnation_strength | 8 / 2 |
| near_duplicate_distance / near_duplicate_penalty | 4 / .02 |
| cache_size / archive_size | 4096 / 100 |
| initialization_attempt_factor / offspring_attempt_factor | 20 / 10 |
| reduce_after_repair | False |
| max_seconds | None |
| mode | balanced |
| difficulty_config | DifficultyConfig() |
| fitness_config / target | mode-derived unless supplied |

Validation: 17≤min≤max≤search_max≤81; elites<population; injections≤population−elites; budgets проверяются на nonnegative/positive по назначению, probabilities/config — на допустимые значения. Параметров workers, annealing temperature и resume нет.

Initial population: private RNG seeds создают min(solution_count,population_size) полных solutions; попытки обходят их round-robin. Каждая начинается с81 clues и shuffled removal до min_clues либо неприводимого состояния. Кандидаты вне min_clues..search_max_clues, nonunique или с invalid human state отбрасываются; identity deduplicated. Максимум initialization attempts=population×factor=640. Неполная population приводит к остановке initialization_budget. Каждый прошедший кандидат получает Quick; затем не более min(deep_candidates_per_generation,max(1,ceil(pool_size×deep_fraction))) лучших по scalar ещё не Deep-rated candidates проходят Deep; default initial32 →2. Initial best — лучший проверенный среди выбранных Deep seeds, НЕ fresh Deep максимум всех initial32.

`_evaluate`: строгий exploration clue range → exact uniqueness cache → Quick → reuse cached Deep, если есть → fitness. HUMAN_UNSOLVED сохраняется как exploratory candidate со status и -inf, но не может стать verified best/archive. `_deep` проверяет bounded required level и minimality; `_remember` обновляет historical scalar champion и отдельный Pareto archive.

Каждое поколение сохраняет scalar elites; создаёт tournament children с optional same-solution crossover, затем mutation, repair и reduction после crossover. До offspring_count×attempt_factor=320 попыток дают до32 distinct children. Далее выполняются local search для1 лучшего child, injections по расписанию/stagnation, один общий Deep budget для old population+children+injections, резервирование elite/injection slots, greedy diversity-adjusted survivors, stats и stagnation update. Best/archive сохраняются, даже если champion больше не входит в current population.

### Search modes и точные target thresholds

Все modes по умолчанию имеют target clues17–21 и exploratory max32. Targets — условия соответствия выходного кандидата, а не жёсткие ограничения exploration.

| mode | required rating≥ | bottlenecks≥ | advanced_steps≥ | longest_chain≥ | Intermediate STUCK required | minimal required |
|---|---:|---:|---:|---:|---|---|
| balanced | 0 | 0 | 0 | 0 | no | no |
| extreme | 30 | 2 | 3 | 0 | yes | no |
| monster | 36 | 3 | 5 | 8 | yes | yes |
| min_clues | 0 | 0 | 0 | 0 | no | no |

Все modes требуют status DEEP_RATED, unique=True, solved, verified required level и непустой required rating. `prefer_minimal=True` сохраняется у каждого profile, но не читается engine/fitness/target_match; реальный небольшой бонус независимо задаёт FitnessConfig. Target `monster` НЕ синоним rating class Ultra Extreme: classify и target_match накладывают разные gates. Mode с именем Ultra Extreme или GENERATE_MONSTER нет; фактические имена lowercase, как выше.

## Fitness Function

Обозначения: T=verified minimum_tier ordinal TRIVIAL0/BASIC1/INTERMEDIATE2/ADVANCED3/EXTREME4, R=hardest_required_rating, B=true_bottleneck_count, A=advanced_steps, E=extreme_steps, S=total_score, C=chain_complexity, L=longest_chain, U=als_steps, F=forcing_steps, N=clues, M=1 только при minimal is True. Логарифм натуральный.

```text
fitness = 10000*T + 1000*R
        + wB*ln(1+B) + wA*ln(1+A) + 10*ln(1+E)
        + 1*ln(1+S) + wC*ln(1+C) + wL*ln(1+L)
        + wU*ln(1+U) + wF*ln(1+F)
        + wN*max(0,82-N) + 0.1*M
```

| Mode | wB | wA | wC | wL | wU | wF | wN |
|---|---:|---:|---:|---:|---:|---:|
| balanced | 100 | 20 | 5 | 1 | 2 | 3 | .1 |
| extreme | 200 | 30 | 5 | 1 | 2 | 3 | .1 |
| monster | 300 | 40 | 20 | 5 | 10 | 15 | .1 |
| min_clues | 100 | 20 | 5 | 1 | 2 | 3 | 200000 |

Все12 coefficients переопределяются конечными неотрицательными полями FitnessConfig. Внутри формулы нет отдельных complexity/clue penalties, резкого порога21 clues, бонуса за одну class label, false-lead/novelty/distributed-bottleneck/late-peak слагаемых. Required level/rating практически преобладает над вторичными features обычных modes; sparse Easy не должен превосходить hard candidate из-за .1 на clue. min_clues намеренно меняет приоритет огромным clue bonus; это не отдельный математический lexicographic algorithm. Minimality default добавляет только .1, но monster target жёстко требует minimal=True.

Quick substitutes R=observed hardest_rating, provisional T=max registry tier among entries base_rating≤R, B=0; cannot claim mandatory level or enter archive. Deep with unverified required level becomes UNRATED; verified Deep requires R non-None. Scalar Quick/Deep units comparable, but provisional rank still may be wrong and selected Deep lowers it legitimately.

Hard rejection/status (`evaluate_fitness`): N<17 or unique=False → REJECTED/-inf; result.invalid/backtracking/guesses → REJECTED/-inf; result not solved → HUMAN_UNSOLVED/-inf; missing rating/unique not True → UNRATED/-inf; unverified Deep or missing required rating → UNRATED/-inf. Engine additionally rejects outside config.min_clues..search_max_clues and failed uniqueness/repair before scoring. Validated chromosome structurally prevents contradictory givens; zero-solution child not expected but exact repair handles failure. Target clue max21 does NOT reject exploratory22–32, and no scalar penalty beyond marginal clue bonus. Duplicate children discarded by identity.

Fitness vector (max all): `(R, B, A+E, C, S, -N)`. `advanced_steps` includes extreme steps, so A+E intentionally counts an extra contribution from extremes. Vector omits minimum_tier, L, ALS, forcing, minimality independently; a Pareto dominator can have lower scalar fitness. Code preserves scalar champion separately for this reason. Search ranking is scalar tournament; Pareto is an auxiliary archive, not NSGA-II selection.

Selection penalty, separate from stored fitness: adjusted=f−abs(f)×near_duplicate_penalty×neighbor_count for finite fitness; neighbors same target solution, other identity, Hamming(maskA,maskB)<4 default. Tournament counts neighbors in full population; survivor selection counts in already-selected prefix. Potential >100% penalties with custom dense populations are allowed. No claim this is a fitness bonus.

## Mutation / Crossover / Repair

| Operator | Реализация |
|---|---|
| REMOVE | remove up to strength random present bits |
| ADD | add up to strength random absent bits |
| SWAP | independently sample strength present and absent positions; equal number |
| MULTI_SWAP | choose2 or3 then multiply by strength; bounded by present/absent counts |
| REGION | choose uniformly one of27 row/column/box units; swap within unit |
| GUIDED | strongest genuine bottleneck by descending required_rating, step-index tie; choose up to4 unresolved cells with smallest candidate counts, union peers; swap within resulting region; fallback global if none |

No-op on impossible boundary is safe; fresh uniqueness/rating required. Only mask changes, same valid complete solution. GUIDED is structural heuristic, not an AIC/ALS pattern predictor.

Crossover: ONLY parents with exactly equal target solution. common=A&B, optional=A^B; each optional bit independently included p=.5. Default probability .1; mutation ALSO applied after crossover. Repair → clue reduction to min floor → evaluate. No crosses between unrelated solutions. `_child` second parent uses tournament size from config, but inadvertently uses default near_distance=4/penalty=.02 rather than forwarding configurable values; first parent does forward them. This is a low-severity custom-policy inconsistency, not invalid puzzle generation.

Uniqueness repair: `collect_solutions(puzzle,limit=2)`. Each valid alternative different from target produces exact 81-bit difference mask `D={cells where alt!=target}`. It need not use the difference between the two collected alternatives: target-relative witnesses directly guarantee selected target clue excludes witnessed alternative. ConflictStore caches witnessed masks per immutable target, max128 target solutions ×1024 sets each; validation via complete Individual prevents poisoned incomplete witness grids. Unresolved set means `(D & current_mask)==0`; known clues all coincide with that alternative.

Repair adds ≤repair_limit(5) target clues. random picks from union unhit witnesses; coverage picks maximal number of hit unresolved sets with RNG ties; guided additionally breaks coverage ties to prefer cells outside bottleneck influence. Witness stored for every addition (`addition_conflicts`); discovered/conflict_sets/check count returned. When no known unresolved sets remain, collect solutions again; at limit also perform final exact check. Hitting cached sets never itself certifies uniqueness. Failure after budget returns False, child discarded. `reduce_after_repair=False` default; crossover always has separate reduction. This is greedy reusable witnessed hitting information, NOT exhaustive unavoidable-set/hitting-set optimization for globally minimum17 clues.

## Selection / Diversity / Archive

Tournament: sample min(size5,population length) with RNG, maximize (adjusted fitness, raw fitness, identity). Elites top3/32=9.375% unchanged chromosome; if subsequently Deep-evaluated, evidence may update. Survivors dedup identity, choose Deep evidence over Quick duplicate, then fitness; preserve elites and successful injections before greedily filling.

Diversity: exact identity dedup + near clone penalty; reported mean pairwise Hamming raw0–81 over all masks, including unlike solutions. Same mask on unrelated solution isn't exact duplicate; near penalty applies only same solution. No normalized distance, minimum separation guarantee, Sudoku canonicalization or technique-histogram novelty score.

Random injections: default3 fresh complete solution seeds each5 generations, plus when stagnated. They are unrelated strings but still same Latin equivalence family. Slots reserved against immediate fitness culling. Initialization attempts factor20 also bounds injection attempts.

Stagnation: default8 consecutive completed generations without strict increase of verified historical champion scalar; NEXT generation uses strength2 and additional injection trigger. Counter resets after response; archive/champion kept. Not an adaptively learned operator schedule. Mutation success telemetry means valid evaluated offspring, NOT fitness improvement.

Memetic/local search IMPLEMENTED bounded: best local_search_candidates=1 children;3 random single swaps each, no repair (delta must describe proposed swap). Evaluate uniqueness/Quick; if either endpoint has Deep (including cached neighbor), deepen both before comparison. Accept delta>0 only; current updated iteratively. Records finite critical_clue deltas, removed/added positions, generation, evidence mode; telemetry bounded cache_size. No exhaustive all-swap neighborhood; no systematic individual-clue removal/addition delta matrix.

Simulated annealing: NOT IMPLEMENTED. Multiprocessing/parallel evaluation: NOT IMPLEMENTED. Novelty search beyond masks: NOT IMPLEMENTED. Full logical multi-path/minimax rating: NOT IMPLEMENTED (existing bounded Deep reused). Resume checkpoint: NOT IMPLEMENTED.

Pareto archive: require unique True, ≥17 clues, Deep non-None solved valid no guessing/backtracking, required_level_verified, finite fitness/vector. Dominated entries removed; non-dominated tradeoffs retained; dedup identity. Default100 bounded capacity: sort scalar, preserve scalar frontier leader and objective endpoints, fill remaining scalar leaders. Thus not all historical nondominated candidates guaranteed retained. Separate best_seen scalar champion survives loss from Pareto and population; export union archive+champion exact-deduped. Archive does not itself demand target clues17–21 or monster profile.

Caches: bounded4096 per run uniqueness `(solution,mask)`; rating shared OrderedDict `(solution,mask,quick/deep,DifficultyConfig)`; fitness `(identity,FitnessConfig,DifficultyConfig,minimal,hasDeep)`; separate conflict store128×1024; analyzer internal state cache. Mutable rating results copied in/out; counters lookup/hits for every cache. Engine rerun resets all. No disk/persistent result cache.

Snapshot `snapshotVersion=1, phase=6, resumable=False`: seed, full config, completed generation, stop reason/timed_out/elapsed, initial_best/best/archive summaries, stats and counters/stage timings. Atomic tempfile/fsync/replace. Not RNG state, full population or full proof serialization; cannot restart from this file.

Reproducibility: private seeded RNG, deterministic tie-breaks, caches run-owned/reset. Tests assert same population keys/champion fitness/counters/stats except timing when no wall-clock cutoff. seed=None explicit effective64bit seed. max_seconds cooperative between solver calls; current expensive call may overrun. Export and independent revalidation outside search budget. Partial generation may have updated best/archive but last completed generation/stat lower. Do not claim bit-identical timed runs.

Evolution CLI: `python -m generator evolve`, args seed/population32/generations30/mode balanced|min_clues|extreme|monster/clues17–21/search-max32/max-seconds/output default data/evolution_candidates.json/snapshot/export-limit10/targets-only. CLI derives elite and injection sizes max(1,population//10), offspring=population. Snapshot and output cannot resolve same file. No --resume/--workers/--anneal. Snapshot always saved after run; archive+champion candidate selection; targets-only applies stricter profile. Zero matching verified candidates leaves puzzle output unchanged, returns1; exceptions2; successful selected export0 even timed-out run may have candidate. Exports remain preliminary.

Evolution export `to_generated_puzzle`: fresh exact validate, reconstruct Human solve with same required threshold and DifficultyConfig (not known solution passed to human), compare solved grid to target, fresh check_minimal, set preliminary=True, reuse schema1 exporter. This does NOT rerun full independent Deep/minimax/bottleneck certification. The reported required level is inherited from Deep search result.

## Testing

`python -m unittest discover -s generator/tests -v`: **269 passed, 0 failed/errors, 0 skipped**, 89.567 s по unittest, **90.0930217 s wall**. Warnings в логе отсутствуют. Полный лог: `%TEMP%/extreme_sudoku_audit_unittest_20260930.log`. Без coverage-инструмента: percentages code coverage не измерялись.

Непересекающаяся группировка всех 269 unittest:

| Область | Modules | Tests |
|---|---|---:|
| Core grid/candidates | test_grid=4, test_candidates=8 | 12 |
| Exact Solver | test_exact_solver | 6 |
| Human Solver orchestration | test_human_solver | 11 |
| Individual techniques | test_techniques=12, test_quads=5, test_fish=10, test_single_digit_patterns=17, test_wings=16, test_chains=18, test_als=13, test_forcing=10 | 101 |
| Advanced soundness | test_advanced_soundness | 1 |
| Difficulty/rating/profiles | test_classification=3, test_deep_rating=2, test_difficulty=5, test_mandatory_rating=4, test_rating_profiles=3, test_rating_registry=3, test_state_rating=7 | 27 |
| Bottlenecks | test_bottleneck_rating | 4 |
| Generator | test_generator=5, test_generation_pipeline=26 | 31 |
| Export/CLI | test_export_cli | 20 |
| Evolution core | test_evolution_core | 23 |
| Evolution engine/integration | test_evolution_engine | 16 |
| Phase integration | test_phase2_integration=6, test_phase3_integration=7, test_phase4_integration=4 | 17 |
| Total | | 269 |

Тематически внутри evolution core: config/individual (4); mutation/crossover (6); uniqueness repair (4); fitness/selection/Pareto (9). Есть проверки всех операторов, boundary masks, deterministic RNG, region locality, guided bottleneck structure; exact alternative witnesses, всех трёх repair strategies и difference sets; conflict isolation по target solution; hard rejection/HUMAN_UNSOLVED; Quick/Deep tier scale; tier/rating/complexity/minimality coefficients; tournament bias/repeatability; elites, duplicates, diversity, Pareto trade-offs. Engine integration (16) проверяет pipeline, seed reproducibility без timings, reserved injections, telemetry, cache policy и detach, historical champion, staged Deep старых/injected кандидатов, Monster minimality, local-search Deep evidence, timeout, snapshot и CLI/export contracts. Это покрытие требований тестами, не процент строк кода.

Дополнительно реально выполнены frontend checks: **15/15 Node unit tests**, 0 failed/skipped, duration 951.593 ms; **14/14 browser scenario groups**, включающие **56 responsive cases** (14 viewports × 2 themes × 2 engines), 42.9694006 s wall, exit 0. Chromium 153.0.8010.12, WebKit 26.6. Ранее установленный isolated tooling в TEMP использован без установки пакетов. Node/npm отсутствуют в PATH, поэтому выполнен эквивалент npm test: `& "$env:TEMP\extreme-sudoku-qa\packages\playwright\driver\node.exe" --test web/tests/game.test.js`. Build-команды нет: frontend static ES modules.

Browser source имеет фиксированный ARTIFACTS внутри проекта. Для соблюдения read-only audit загружен существующий module через `importlib.util.spec_from_file_location`, перед `m.main()` только runtime-переменная `m.ARTIFACTS` перенаправлена в `%TEMP%/extreme_sudoku_audit_browser_20260930`. ROOT оставлен исходным, проверялась реальная текущая web/data. Команда:

```powershell
$env:PYTHONPATH = Join-Path $env:TEMP 'extreme-sudoku-qa\packages'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $env:TEMP 'extreme-sudoku-qa\browsers'
python -c "import importlib.util,pathlib,tempfile,time,json; p=pathlib.Path('web/tests/browser_regression.py'); s=importlib.util.spec_from_file_location('audit_browser',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.ARTIFACTS=pathlib.Path(tempfile.gettempdir())/'extreme_sudoku_audit_browser_20260930'; t=time.perf_counter(); m.main(); print(json.dumps({'wall_seconds':time.perf_counter()-t,'artifacts':str(m.ARTIFACTS)}))"
```

Browser groups и responsive cases не суммируются с unittest как одинаковые единицы. Совокупно 284 Python/JS unit tests plus browser matrix. Физическое iOS Safari не проверялось; это desktop WebKit. Необязательный fixture-builder не запускался: он перезаписывает сохранённые fixtures. profile_phase3/4/5/6 scripts — диагностические benchmarks, не дополнительные test suites; их исторические артефакты прочитаны, повторно с default output не запускались.

## Evolution Experiment

Сохранённых результатов достаточно для диагностического сравнения, поэтому новый evolution run в этом аудите не запускался. Основной завершённый сохранённый run: `docs/PHASE6_PROFILE.json`, соответствующие `PHASE6_SNAPSHOT.json`, `PHASE6_CANDIDATES.json` и log. Timestamp 2026-09-29T18:59:21Z. Команда:

```text
python -m generator.tests.profile_phase6 --seed 42 --population 32 --offspring 32 --generations 10 --max-seconds 240 --mode extreme --output docs/PHASE6_PROFILE.json --database docs/PHASE6_CANDIDATES.json --snapshot docs/PHASE6_SNAPSHOT.json
```

seed=42; mode=extreme; population=32; offspring=32; generations=10; elapsed=234.4052326 s; stop_reason=max_generations; timed_out=false. Архив содержит 4 records, population=32. Initial best — только лучший из initial selective-Deep, не доказанный максимум всей начальной популяции. Final leader создан REMOVE в generation 10, следовательно улучшение не объясняется только отложенным Deep initial seed.

| Метрика | Initial verified best | Final verified best |
|---|---:|---:|
| ID | puzzle-f197179f12c6533697b1 | puzzle-310fab8b8581c087bc8a |
| Fitness | 75609.97826805139 | 95635.06103194806 |
| Clues | 23 | 25 |
| Minimal | true | false |
| Class | preliminary Extreme | preliminary Ultra Extreme |
| Required rating | 35 | 55 |
| Hardest required technique | Grouped AIC | Nishio |
| Genuine bottlenecks | 9 | 8 |
| Advanced steps | 13 | 30 |
| Extreme steps | 12 | 30 |
| Longest chain | 19 | 12 |
| Chain complexity | 190 | 349.5 |
| ALS steps | 0 | 7 |
| Forcing steps | 0 | 6 |
| Total score | 11882.861423024402 | 44277.82634012756 |

Initial puzzle: `050000700000028000090600000670000009000300006900010250200040010030000005700050030`.

Final puzzle: `050030000000028000090600000671000009000304006003010250200000010030007005700050030`.

Audit заново вызвал fresh `DifficultyAnalyzer(config).deep(grid, check_unique=True)` для обоих endpoints. Сохранённая DifficultyConfig побитно по to_dict совпала с current default; все 25 полей rating_summary обоих endpoints совпали с историческим JSON, включая unique logical resolution, required rating, score, bottlenecks, profile statuses, отсутствие guesses/backtracking. Это текущая независимая воспроизводимость bounded evidence, а не Phase7 certification. Повторные значения fitness не вычислялись отдельно: приведены из сохранённого run; rating evidence перепроверено.

В финальном run среди distinct Deep records 15 extreme candidates, включая 11 ultra candidates; эти категории пересекаются. **0 Extreme target matches и 0 Monster target matches с clues17–21**. Есть Ultra Extreme и minimal low-clue exploratory candidates, но нет полноценного target-Monster в установленном диапазоне. Производственный сертификат ни одному puzzle не присваивается.

## Best Candidates Found

Сравнение сделано по independent objectives, без искусственного общего рейтинга. Всего обнаружено 34 distinct verified-Deep puzzle strings в сохранённых Phase6 profiles (AUDIT, final, smoke). Old AUDIT отражает другую историческую версию весов; его scalar fitness нельзя напрямую сопоставлять с final. Fixtures не считаются продуктом evolution. Рекурсивный просмотр всех `docs/*.json` подтверждает минимальную сохранённую puzzle string с 22 clues; в Phase5 profiling есть metadata о минимизации до21, но без соответствующего сохранённого puzzle/ID — не candidate record.

Обозначения в таблице: R — required rating, B — genuine bottleneck groups, A — advanced steps, E — extreme steps, L — longest chain. Значения record относятся к соответствующему сохранённому profile; fresh Deep текущим кодом повторён для initial/final champions, а не для всех34 records.

| Критерий | Подтверждённый record | Значение / контекст |
|---|---|---|
| Minimum clues, final archive | puzzle-ca88d658a18eafb27c24 | 22, minimal=true, preliminary Ultra Extreme, R55/B8/A19/E19/L17, score32350.214507962733 |
| Minimum clues, final population | puzzle-8e2b144cecb50551d96b | 22, minimal=true, preliminary Extreme, R35/B3/A17/E15/L13; сохранён в PHASE6_PROFILE, отсутствует в final Pareto export |
| Minimum clues, historical AUDIT | puzzle-bcf460fc20aeeee740c2 | 22, minimal=true, preliminary Ultra Extreme, R39/B5/A10/E7/L9 |
| Maximum required rating | puzzle-310fab8b8581c087bc8a; puzzle-ca88d658a18eafb27c24; и другие ties | 55 (Nishio); нет уникального победителя этой цели |
| Maximum genuine bottlenecks, final archive | puzzle-55684dd4bac9cb6a200f; puzzle-f197179f12c6533697b1 | 9; respectively R55/24clues and R35/23clues |
| Maximum advanced/extreme steps | puzzle-310fab8b8581c087bc8a | 30 advanced and 30 extreme; advanced включает extreme, поэтому это не60 различных шагов |
| Maximum longest chain | puzzle-f197179f12c6533697b1 и historical ties | 19; Grouped AIC initial seed, final Pareto archive |
| Maximum total score across historical saved results | puzzle-f23734d386d6cc1e2328 | 46602.53212202193, только PHASE6_AUDIT_PROFILE/CANDIDATES, preliminary Ultra Extreme, 25clues/minimal=false, R55/B8/A29/E27/L19 |
| Strong representative preliminary Extreme | puzzle-f197179f12c6533697b1 | 23clues/minimal=true, R35/B9/A13/L19; fresh Deep reproduced |
| Strong representative preliminary Ultra, scalar final champion | puzzle-310fab8b8581c087bc8a | 25clues/minimal=false; fresh Deep reproduced; не MONSTER_SEARCH match |
| Closest low-clue preliminary Monster-like candidate | puzzle-ca88d658a18eafb27c24 | 22clues/minimal=true/R55/B8/A19/L17; остальные перечисленные Monster logic thresholds выполнены, clue target17–21 не выполнен; не называть полноценным Monster target |

Идентификаторы record, отсутствующих в database, выведены по той же стабильной формуле `puzzle-` + первые20 hex SHA256(puzzle). Они явно ссылаются на profile puzzle string, а не выдуманный export.

`puzzle-ca88d658a18eafb27c24`:
`050000000000028000090600000601000009000004006003010200200940010000007005700050030`.

`puzzle-8e2b144cecb50551d96b`:
`009000001000050008010000640028004000000190000000002030002403000100000206000070003`.

`puzzle-bcf460fc20aeeee740c2`:
`050000000000028000090600000670000009008300006900010250000040010030000005700050030`.

`puzzle-55684dd4bac9cb6a200f`:
`050000000000028000090600000671000009000300006903010250200040010000007005700050030`.

`puzzle-f23734d386d6cc1e2328`:
`050000700100028000090600000070000009000300076900010250205040010030000005700050030`.

## Performance

Текущие короткие измерения (выполнены последовательно после test suites, без одновременно запущенного browser/evolution; exact — median20 repetitions, Quick/Deep — fresh analyzer один вызов):

| Operation | Initial Extreme | Final Ultra |
|---|---:|---:|
| count_solutions(limit=2) | 0.001522350 s | 0.001508300 s |
| Quick Rating | 0.538410300 s | 4.914241300 s |
| Deep Rating with uniqueness | 2.745117200 s | 19.484743900 s |

Текущий один обычный generation attempt: seed42, clues35–40, require_minimal=false, rating_mode=quick, max_attempts1 — accepted1, wall0.114283300 s; rating0.066084800 s, Human path0.037877900 s, clue removal0.006461200 s, uniqueness validation0.000106400 s. Output не экспортировался. Это easy smoke, не оценка стоимости поиска Extreme.

Исторические authoritative timings final Phase6 run: mean generation22.48207795 s; median15.10199935; min7.30728560; max48.19917280. Quick:83.84010720 s/362 calls (~0.2316 s/call); Deep143.72245560 s/22 (~6.5328 s/call); uniqueness2.25739239 s/4906 calls; seed construction0.94691450 s; repair0.63705300 s/302; crossover reduction0.75700680 s; mutation0.02721020 s/351; local search8.84342760 s/10; minimality0.18358570 s/20. Quick~35.77% и Deep~61.31% search wall. Stages inclusive и перекрываются (local search включает rating, construction/minimality включают uniqueness), доли не следует суммировать как независимые CPU shares. Основная стоимость — human rating/Deep, не mask mutation или exact uniqueness.

Cache hit rates saved final run: uniqueness237/(237+4669)=4.83%; Quick21/(21+362)=5.48%; Deep0/(0+22)=0%; fitness18/(18+407)=4.24%. Это результаты данного run, не общие гарантии эффективности.

Исторический PHASE3_PROFILE, four unique fixture puzzles: default solves2.246459 s; detector totals ALS Chain0.451556, Nishio0.364222, Forcing Chain0.352032, Grouped AIC0.271657, ALS-XY-Wing0.265296, ALS-XZ0.208012, AIC0.066209, Nice Loop0.021972, X-Chain0.009994, XY-Chain0.003303 s. На этой выборке ALS Chain дороже AIC; это не микропрофиль текущего чемпиона. ALS enumeration, forcing propagation и многократные Deep threshold passes — ключевые bounded hotspots. Отдельного текущего profiler CPU attribution по enumeration не запускали; нельзя объявить эти времена exclusive enumeration costs.

Исторический Phase5 smoke0.119494 s; batch8 accepted/8 attempts2.948841 s, среднее attempt0.368537 s; Deep только для1 кандидата1.320791 s. Phase4 saved medians: basic Quick0.076823/Deep0.287768; seed21 Quick0.116764/Deep0.901316; seed3 Quick0.124578/Deep1.117095 s. Эти значения исторические, не результаты текущего audit run.

## Specification Compliance

Статусы относятся к фактическому текущему scope. `PARTIAL` может означать осознанную границу Phase1–6, а не дефект существующего алгоритма. Числа из иллюстративных SE-подобных шкал спецификации не заменяют current registry.

| Requirement | Specification | Implementation | Status | Notes |
|---|---|---|---|---|
| Независимые generator/frontend | PRODUCT §3.1, UI §35/37, DATA_FORMAT §53 | Python offline + static web через JSON | DONE | Генерация и рейтинг не выполняются в browser |
| Grid, masks, units, peers | GENERATOR §1 | 81 integers, 9-bit candidates, immutable topology | DONE | Explicit eliminations входят в state signature |
| Exact solving/count/uniqueness | GENERATOR §2 | MRV bitmask DFS, early limit, alternative witnesses | DONE | Runtime exact отделён от human deduction |
| Случайное полное решение | GENERATOR §3 допускает shuffled base pattern | Latin pattern с допустимыми transformations | DONE | Разные seeds остаются одним solution orbit; охват ограничен |
| Human logic без known solution/backtracking | GENERATOR §7/59, AGENTS | 30 detectors, proof metadata, guarded tests | DONE | В пределах реализованного repertoire; не полная теория Sudoku |
| Весь перечисленный каталог techniques | GENERATOR §9 | Fish/wings/chains/ALS/binary forcing subset | PARTIAL | Нет finned/sashimi, coloring/Medusa, UR/BUG, dynamic forcing; см. таблицу |
| Сначала простейший доступный ход | GENERATOR §8 | Deterministic rating/name + step_key | DONE | Найденный минимум зависит от detector budgets |
| Rating registry и tiers | GENERATOR §11–13/18, PRODUCT §12 | Configurable legacy .5–55, структурный score | DIFFERS FROM SPEC | Совместимость текущих Phase1–6; это не SE calibration |
| Minimum required level и alternative paths | GENERATOR §15–17/49 | Ascending threshold reruns одного greedy solver | PARTIAL | Полный minimax/branching logical paths отсутствует |
| Genuine bottlenecks | GENERATOR §14/46/48 | State minimum, cheap-step exclusion, proof grouping | PARTIAL | Genuine только относительно bounded detectors; exhaustion наверх не передаётся |
| Quick/Deep многоэтапная оценка | GENERATOR §42 | Cheap uniqueness/Quick, selective Deep | DONE | Deep limited по числу выбранных candidates, не всей популяции |
| Extreme/Ultra acceptance | GENERATOR §24/25/43/64 | Current explicit rating gates и отдельные search targets | DIFFERS FROM SPEC | Ultra class не равен monster target; точные пороги выше |
| Clue removal/minimality | GENERATOR §6/53 | Exact checked removal, fresh final checks | DONE | Minimal не minimum; нельзя обещать 17 clues |
| Clue-mask chromosome | GENERATOR §4/26 | Frozen full solution + 81-bit mask | DONE | Cross-target crossover запрещён |
| Mutations и crossover | GENERATOR §28/30 | Шесть операторов, region объединяет row/col/box; mask crossover | DONE | Guided — structural heuristic по bottleneck |
| Difference-set repair | GENERATOR §31–33 | Target-relative alternative witnesses, greedy coverage | DONE | Это не exhaustive hitting-set optimization |
| Tournament/elitism/injection | GENERATOR §34–36/38 | Scalar tournament, elites, reserved injections, stagnation response | DONE | Точные budgets/defaults выше |
| Diversity/canonicalization | GENERATOR §36/37 | Identity dedup + Hamming neighbor penalty | PARTIAL | Symmetry canonicalization отсутствует |
| Memetic/critical clues | GENERATOR §29/39 | Три случайных swap trials и finite deltas | PARTIAL | Нет exhaustive neighborhood или полной clue influence matrix |
| Simulated annealing | GENERATOR §40 | Нет temperature/acceptance schedule | NOT IMPLEMENTED | Отсутствие опциональной эвристики само по себе не blocker |
| Technique-profile novelty | GENERATOR §41 | Mask diversity only | NOT IMPLEMENTED | Telemetry operator success не novelty score |
| Fitness и multi-objective search | GENERATOR §21/61–63 | Current scalar formula + auxiliary bounded Pareto archive | PARTIAL | NSGA-II population selection отсутствует; Pareto objectives не все scalar features |
| Parallel evaluation | GENERATOR §55 | Последовательный engine | NOT IMPLEMENTED | Нет workers/multiprocessing API |
| Воспроизводимость/config/cache | PRODUCT §57/59, GENERATOR §54 | Local RNG, serialization, bounded policy-aware caches | DONE | Тайминги/wall-clock cutoffs/generatedAt исключены |
| Snapshot/checkpoint | Текущий README/Phase6 scope | Atomic snapshotVersion1, resumable=False | PARTIAL | Диагностика реализована, продолжить RNG/population нельзя |
| Compact JSON validation/export | DATA_FORMAT §2/39–49/53 | Schema1, stable ID, exact/minimal checks, atomic write | DONE | Unknown fields допустимы, Quick observed metadata отделены |
| Explainability/extended export | GENERATOR §50/51, DATA_FORMAT §24/49 | In-memory LogicSteps, compact metadata | PARTIAL | Полный checkable solutionPath в экспортируемой базе отсутствует |
| Независимая final certification | GENERATOR §52, PRODUCT §45/54 | Exact/claimed minimality свежие; bounded Deep evidence переиспользуется | PARTIAL | Нет финального независимого logical multi-path gate или production certificate |
| Практический low-clue Extreme/Monster результат | GENERATOR §44/64–66 | Extreme/Ultra candidates22–25, целевые17–21 matches=0 | PARTIAL | Высокий scalar fitness не закрывает целевой clue contract |
| Frontend contract/smoke | UI_SPEC, DATA_FORMAT | Static UI, 15 Node tests, 14 browser groups/56 responsive cases | DONE | Проверенный smoke scope; production dataset integration отдельно |

Документация не должна трактовать старые phase numbers как текущую Git chronology. Полный proof export, alternative-path certification и low-clue dataset остаются работой после этого аудита; отсутствие этих функций не скрывается за названием «Phase6 complete».

## Technical Debt

### Critical

**Подтверждённых CRITICAL дефектов не обнаружено.** Не найдены конкретный неправильный Sudoku, unsafe logical elimination или использование Exact Solver/known solution для human deductions. Прошедшие tests и witness checks не являются полным математическим доказательством soundness всех возможных состояний.

### High

1. **Неполная доказательная граница difficulty.** `chains.py`/`als.py` могут исчерпать search budget; `StateAnalysis`/`DifficultyResult` не сообщают общий detector-exhaustion статус. Threshold STUCK и genuine bottleneck нельзя трактовать как доказательство отсутствия более простого хода. Current scope явно preliminary, но без отдельного certification gate эти поля способны породить ложное утверждение о финальной difficulty.
2. **Нет независимой end-to-end production certification и сохраняемого полного proof artifact.** Export повторяет exact/minimality и human path, но наследует Deep required/bottleneck metadata. Отсутствует policy для alternative logical paths и отдельный окончательный проверяющий этап. Это blocker выпуска Production Certified базы, а не blocker начала Phase7.
3. **Поиск ограничен одним structural solution orbit.** `generate_solution` даёт transformations одного Latin pattern; chromosome mutations сохраняют solution, injections не расширяют множество классов эквивалентности. Ограничение существенно сужает search reach. Оно не доказывает невозможность получить 17–21 clues и не установлено как единственная причина отсутствия target matches.

### Medium

- **Low-clue цель практически не подтверждена:** сохранённый final run не дал Extreme/Monster matches17–21. Это незакрытый acceptance outcome; scalar gain сам по себе не доказывает качество целевой базы.
- **Нет symmetry canonicalization:** equivalent puzzles могут занимать cache/archive/search budget и увеличивать видимое разнообразие.
- **Snapshots не возобновляют поиск:** отсутствуют RNG state и полная population; прерванный длительный experiment нельзя продолжить из snapshot. Это потеря продолжения, не повреждение сохранённых candidates.
- **Deep дорого повторяет human work:** сейчас evaluation последовательно, bounded local search и множество threshold passes концентрируют стоимость в ALS/forcing/chain search. Параллелизация и оптимизация требуют benchmark evidence, не нужны для корректности текущего run.
- **Provenance текущей поставки неполон:** Git metadata отсутствуют, поэтому snapshot reports нельзя привязать к independently verified commits/tags. Это ограничение полученной папки, а не доказательство, что история никогда не велась.

### Low

- `TargetProfile.prefer_minimal` записывается в config, но не влияет на selection/fitness/target_match. Реальные механизмы — .1 fitness bonus и monster `require_minimal=True`; публичное поле вводит в заблуждение.
- В crossover `_child` второй parent tournament не получает пользовательские near-duplicate distance/penalty и применяет defaults4/.02. Изолированный read-only reproduction с config9/.7 показал фактические kwargs `{'size': 5}`. Default policy не затронута; корректность Sudoku не нарушается.
- Export `generatorVersion="0.5.0"` сохраняется и в Phase6. Одного этого semver недостаточно для точного provenance алгоритма; нужны revision/config identifiers в evidence bundle.
- HumanSolveResult и DifficultyResult используют разные определения advanced_steps/total_score. README это объясняет, но downstream consumers должны выбирать правильную модель.

Отсутствие SA, NSGA-II и exhaustive local search не объявляется искусственным correctness defect: это возможные последующие расширения, оправданные только измеримым улучшением поиска.

## Known Limitations

`HUMAN_UNSOLVED` означает, что данный bounded deterministic solver не закончил puzzle. Это **не обязательно mathematically harder puzzle**, не доказательство необходимости угадывания и не показатель Extreme. Solver может не поддерживать нужную технику, пропустить proof из-за representative-path selection или исчерпать бюджет.

- Нет полного каталога advanced families; конкретные отсутствующие и ограниченные варианты перечислены в Implemented Techniques. Binary forcing не равен unrestricted DFS, Cell/Region/Dynamic Forcing не реализованы.
- Required level — минимум среди испытанных threshold runs одного deterministic policy. Другой допустимый logical path может иметь более низкий maximum rating. Hardest required technique label не доказывает обязательность именно этого technique name.
- Genuine crises и minimum available rating относительны реализованному repertoire и budgets. `enumeration_complete` не означает exhaustive graph-proof enumeration. Нельзя сертифицировать отсутствие simpler alternatives по одному Boolean.
- Chain length сравнивает candidate/RCC links и forcing dependency depth; это разные proof structures. Текущие scalar/vector используют их как эвристические признаки, а не универсальную шкалу математической трудности.
- Minimal puzzle нельзя уменьшить удалением одной clue с сохранением unique; это не minimum-clue Sudoku и не доказательство недостижимости меньшего числа clues после изменения pattern.
- Выборочный Deep может изменить ранжирование Quick. Initial verified best — только Deep-reviewed подмножество initial population, не exhaustive best. HUMAN_UNSOLVED остаётся exploratory, но не archive-certified.
- Все complete grids обычного генератора/evolution принадлежат одному Latin orbit. Diversity telemetry по raw masks не измеряет разнообразие Sudoku equivalence classes.
- Timeout cooperative; долгий текущий solver call может закончиться после deadline. Исторический AUDIT run занял186.579s при180s budget. Seed reproducibility без cutoff не даёт bit-identical timed runs.
- Pareto archive bounded и не обязан сохранить все nondominated candidates истории. Scalar champion отдельно сохраняется, но не заменяет независимые цели.
- Compact export не включает полный solutionPath; exact/JSON validation не доказывает difficulty metadata. Preliminary Ultra label не означает Monster target match или Production Certified.
- Текущие проверки browser — desktop Chromium/WebKit; физический iOS Safari не тестировался. Evolution candidates в docs не публикуются автоматически в текущую frontend database.
- Git history/tags недоступны в полученной папке. Исторические tests/phase boundaries подтверждаются сохранёнными документами и compatibility repertoires, а не независимо проверенными tags.

## Current Readiness

| Компонент | Оценка | Причина |
|---|---|---|
| Core Solver | **READY** | Flat grid/units/masks и exact MRV/count корректно разделены, текущие unit/integration проверки проходят; доказанных ошибок не найдено |
| Human Solver | **READY FOR CURRENT SCOPE** | 30 bounded detectors с proof metadata, soundness/replay/API-trap tests; неполный каталог и budget limits явно описаны |
| Difficulty Rating | **READY FOR PHASE 7** | Воспроизводимая preliminary оценка, registry/profiles/thresholds/bottlenecks пригодны как вход certification; final necessity proof ещё не готов |
| Basic Generator | **READY** | Seeded removal, uniqueness/minimality, partial failures, CLI и atomic validated schema1 export работают; finite attempts не гарантируют desired class/clues |
| Evolutionary Generator | **READY FOR PHASE 7** | Реальный bounded experiment улучшил verified candidate; mutation/repair/Deep/archive/export проверены. Поиск даёт исследовательские candidates, а не production certificate |
| Production Dataset | **NOT CERTIFIED YET** | Нет final logical gates/proof bundle и нет target17–21 Extreme/Monster matches в сохранённом final run |
| Frontend Integration | **SEPARATE** | Smoke/contract tests проходят; web/data остаются самостоятельным продуктовым слоем, публикация сертифицированной evolution базы не оценивалась |

`READY FOR PHASE 7` здесь означает, что следующий этап можно начать на имеющихся исследовательских результатах. Это не снимает обязательных gates перед завершением certification и release. Отсутствие Git history ограничивает аудит provenance, но не мешает проверить текущую копию кода и candidates.

## Phase 7 Prerequisites

### BLOCKERS

**Для начала Phase7 подтверждённых технических blockers нет.** Для завершения final certification и production release остаются blockers:

1. Определить проверяемое значение «required» и «genuine» в final certificate: какие techniques, budgets, alternative paths и состояния считаются исследованными; exhaustion не должен молча становиться доказательством необходимости.
2. Выполнить независимую final проверку выбранных candidates, включая полную логическую трассу и повторную оценку claims; текущий compact export и inherited Deep summaries этого не заменяют.
3. Если acceptance contract требует Extreme/Monster17–21 clues, предъявить реальные прошедшие candidates либо явно пересмотреть контракт. Имеющиеся22–25-clue candidates не закрывают эту цель.

### REQUIRED

- Зафиксировать исходный код/revision доступной копии, Python, полный DifficultyConfig/EvolutionConfig и effective seed; восстановить Git history из достоверного источника, если он доступен. Не создавать фиктивные phase tags.
- У каждого выбранного record заново проверить full solution/givens agreement, exact uniqueness и claimed minimality. Сохранить puzzle ID/string, original source result и отдельное certificate evidence.
- Сохранять replayable human proof, explicit bounded scope, detector-limit evidence и traceability required-level/bottleneck выводов. Чётко отделять observed hardest, threshold floor и necessity конкретной техники.
- Проверить cheaper logical alternatives по принятой certification policy; воспроизводимость одного greedy path сама по себе недостаточна для global claim. Не обязательно обещать exhaustive minimax, если продукт честно выбирает иной ограниченный контракт.
- Зафиксировать различие rating class Ultra Extreme, search mode monster и target_match; публиковать preliminary labels до прохождения final gates.
- Повторить текущий suite и новые адресные проверки будущих certification gates после реализации Phase7. Не подменять этим аудитом будущую validation.

### RECOMMENDED

- Расширить sampling complete solutions за пределы одного Latin orbit и проверить эффект на low-clue target yield.
- Добавить canonical dedup и более содержательную diversity telemetry; оценить, насколько текущее raw-mask разнообразие переоценивает охват.
- Профилировать реальные трудные candidates отдельно по AIC/ALS enumeration/forcing/Deep threshold passes. Оптимизировать measured hotspots с сохранением soundness.
- Уточнить provenance version/config hashes; устранить inert prefer_minimal и custom crossover policy inconsistency адресными изменениями и regression tests.
- Для будущих длительных экспериментов спроектировать возобновляемый checkpoint и сохраняемые logs, а также контролируемые budget/exhaustion diagnostics.

### OPTIONAL

- Simulated annealing, NSGA-II population selection, technique novelty и более полный local-search neighborhood — после измерения полезности для целевой базы.
- Multiprocessing с детерминированным порядком merge results и контролем памяти, если последовательный throughput реально ограничивает следующий эксперимент.
- Новые human techniques, extended UI hints/replay и production frontend integration — отдельными согласованными scope, без автоматического включения в настоящий аудит.

## Recommended Next Step

Зафиксировать этот отчёт и текущие предварительные candidates как исходные evidence для отдельной постановки Phase7. Первой задачей следующего этапа сделать контракт final certification и правила обработки detector exhaustion/alternative logical paths; затем выбирать кандидатов по независимым Pareto-целям и проверять их по этому контракту. Scalar champion, минимальный22-clue Ultra и longest-chain Extreme решают разные исследовательские задачи и не должны заменять друг друга.

В рамках данного диалога выполнены только аудит, диагностические проверки и этот отчёт. Phase7 не начата; найденные ограничения и дефекты production-кода не исправлялись.

