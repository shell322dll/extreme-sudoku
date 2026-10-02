# Phase 7 — Final Certification & Production Dataset Pipeline

Дата: 2026-10-01, Europe/Moscow. Рабочая папка: `C:\Develop\Extreme Sudoku`.

**Phase 7 реализована, regression и definitive experiment завершены.**
Из девяти реальных Phase 6 candidates ни один не получил сертификат в default
бюджете: все девять получили `CERTIFICATION_TIMEOUT`. Strict production dataset
валиден и пуст; контент для production frontend integration пока не готов.
Pilot и прерванный ранний запуск отделены от окончательного evidence.

## 1–3. Baseline и regression

Перед implementation зафиксированы fresh проверки:

| Проверка | Baseline | Final |
|---|---:|---:|
| Python unittest | 269 passed, 0 failures; 85.273 s, wall85.690 s | 350 passed, 0 failures; 99.244 s, wall99.619 s |
| Frontend Node tests | 15 passed, 947.532 ms | 16 passed, 131.291 ms |
| Browser scenario groups | 14 passed | 14 passed |
| Responsive cases | 56 passed | 56 passed |

Baseline environment: Python3.11.9, Node24.21.0, Chromium153.0.8010.12,
WebKit26.6, Windows. Зависимости не устанавливались. Полные команды, env и timings:
[PHASE7_BASELINE_SUMMARY.json](PHASE7_BASELINE_SUMMARY.json).
SHA-256 исходников `generator/web/data`, исключая pycache и старые browser artifacts:
[PHASE7_BASELINE_SOURCE_SHA256.json](PHASE7_BASELINE_SOURCE_SHA256.json).
Aggregate: `a62f701f7e089a4efecc7b4f1fa317b7eaf7a567854e283ad945df12a5747d4b`.
Git metadata отсутствуют; commits/tags не создавались и не выдумывались.

Все baseline regression checks сохранены; добавлены 81 Python certification
tests и один frontend metadata compatibility test. Итоговый запуск завершён
с exit code0 во всех трёх командах; исходники во время него не менялись.
Команды, timings и ссылки на полные logs:
[PHASE7_FINAL_SUMMARY.json](PHASE7_FINAL_SUMMARY.json).
Final source aggregate: `20644ec1a53851181cbd1de02877350ec51277c13a053785798e7a8a76a8831e`.
Browser wall40.938s; Chromium153.0.8010.12 и WebKit26.6.

## 4–5. Result, status и policy

`CertificationStatus`: `REJECTED`, `UNRATED`, `PRELIMINARY`,
`CERTIFIED_EXTREME`, `CERTIFIED_ULTRA_EXTREME`, `SEARCH_INCONCLUSIVE`,
`CERTIFICATION_TIMEOUT`, `INVALID_PROOF`. `FailureReason` отдельно хранит
format, solution mismatch, nonunique, nonminimal, unsolved, invalid proof,
nondeterministic replay, stored-path mismatch, limit и acceptance причины.
Timeout/inconclusive никогда не превращается в certified или в доказанный
downgrade исходного label.

`CertificationResult` сохраняет ID/puzzle/solution, clues, factual uniqueness и
minimality, human/proof/reproducibility flags, observed upper witness отдельно
от certified path, minimum required rating/tier, threshold results, bottlenecks,
states/caches/timings, причины, algorithm/config fingerprints и version1.

Immutable `CertificationConfig` объединяет все budgets и product gates.
Official thresholds/minimums нельзя ослабить ниже существующего DifficultyConfig.
Metric definitions используют существующую registry. Version/config/source
fingerprints позволяют отличать evidence от другой реализации. Persistent final
certificate cache отсутствует: production всегда выполняет fresh validation.

## 6–7. Fresh validation и независимые proofs

Математическая часть заново проверяет формат, givens/solution agreement,
`count_solutions(limit=2)==1`, clues и удаление каждого clue для factual minimality.
Known solution используется только здесь и для итогового сравнения решённого
grid. Два новых HumanSolver runs проверяют deterministic path; optional сохранённый
native path может быть сопоставлен через API `previous_path`.

Proof validator проверяет переданные premises, не вызывает тот же detector.
Каждый target — live legal candidate; givens не изменяются; итог locally
consistent. Independent validators покрывают singles, locked candidates,
subsets, fish, single-digit patterns и wings, а также:

| Advanced family | Проверяемое доказательство |
|---|---|
| X-Chain / XY-Chain | Candidate nodes, conjugacy/cell links, alternation, endpoints, visibility |
| AIC / Nice Loop | Strong/weak links, node повторения, endpoint и continuous/discontinuous loop semantics |
| Grouped AIC | Intersection groups, OR semantics, unit partition и pairwise conflict |
| ALS-XZ / ALS-XY-Wing / ALS Chain | N cells / N+1 candidates, disjoint sets, RCC visibility и endpoint theorem |
| Forcing Chain / Nishio | Starting assumption, exactly-one clause implications, parents/depth, shared conclusion или explicit contradiction |

Нет recursive secondary digit guesses, Exact calls или solution oracle в
proof derivation. Unsupported формы отклоняются. Это проверка реализованных
proof families, не формальная теорема о безошибочности любого Python-кода.

## 8–14. Alternative paths, бюджеты и minimum rating

Independently validated greedy path задаёт upper witness. Search запускается
на ближайшем меньшем registry threshold. Найденный более дешёвый witness
снижает upper bound, после чего процесс повторяется. Полный отрицательный
результат непосредственно ниже witness исключает также все меньшие thresholds,
поскольку transition sets вложены. Это отличается от простого greedy STUCK.

Transition — только independently valid LogicStep; arbitrary placement guesses
не добавляются. Frontier сохраняет альтернативные logical states. Приоритет
учитывает прогресс по candidates и deterministic secondary costs; эти
secondary costs не выдаются за отдельный доказанный optimum.

State signature содержит и values81, и candidate masks81. Transposition merges
только одинаковые signatures; shallower arrival доминирует deeper arrival,
поскольку оставляет больше depth budget. Canonical step key — placements,
eliminations, rating, retaining one deterministic proof для одинакового эффекта.
Это устраняет branching от разных представлений одного вывода.

| Limit | Default |
|---|---:|
| Общий time budget кандидата | 60 s |
| Node budget / state budget | 10000 / 10000 |
| Path depth / alternatives per state | 256 / 512 |
| Chain length / enumeration work | 19 / 100000 |
| ALS size / chain length / enumeration work | 4 / 5 / 30000 |
| Forcing depth / nodes / starting candidates | 12 / 2000 / 160 |

`SOLVED` означает witness; `PROVEN_UNSOLVABLE_WITHIN_MODEL` — empty frontier
после complete exploration без omitted work; `INCONCLUSIVE_BUDGET` сохраняет
конкретные limit reasons; `ERROR` сообщает invalid deduction/error.
Исчерпание длины цепи, ALS size, forcing propagation, time/node/state/depth
или alternative-step limit не является доказательством отсутствия пути.
Таймер cooperative: текущая операция может закончиться после deadline,
но просроченный run не становится production certificate.

## 15–16. Certified bottlenecks, Extreme и Ultra

На certified path заново проверяется отсутствие cheaper steps ниже configured
bottleneck floor12. Только complete negative enumeration при valid high witness
создаёт genuine event. Adjacent events и повторяющиеся proof identities
группируются в crises; сохраняются positions, late-game groups и gaps.
Счётчик относится к выбранному path, а не ко всем возможным путям одновременно.

Extreme: fresh unique, supported logical solve без guessing/backtracking,
independent proof/replay, conclusive minimum required rating>=30,
genuine crises>=2, advanced steps>=3. Ultra дополнительно: rating>=36,
crises>=3, advanced>=5, longest chain>=8, advanced work в >=2 из4 path bins,
chain/ALS/forcing evidence. Advanced threshold12, extreme-step threshold22.
Clues не повышают rating. 22+clue candidates допустимы, минимальность factual;
`require_minimal=False` default. Monster17–21 не является acceptance requirement.

## 17–23. Настоящие Phase 6 candidates и результаты

Definitive experiment завершён 2026-10-01 в13:09:06 UTC /16:09:06 Europe/Moscow.
Команда: `python docs/PHASE7_EXPERIMENT_RUN.py --final`; exit code0 harness
означает успешное измерение и сохранение evidence, а не наличие certificates.
Вход объединяет main export4, audit export5 и min22 Extreme из сохранённой final
population. Один exact overlap удалён явно при подготовке входа; получены
9 уникальных puzzles/IDs. Source paths и SHA-256 сохранены; исходные Phase6
артефакты не изменены. ID сохраняется, для population используется существующая
формула `puzzle-` + первые20 hex SHA-256 puzzle string.

Запуск последовательный, без параллельного regression/browser suite. Algorithm
fingerprint до/после совпадает с critical review:
`166aecc4915355c17af29d79b881acb1cd13fc0cd43576b8230f8102e5c96e76`.
Config fingerprint всех результатов:
`10cb06ffe34a9c65237d99a2918cffcfa0565e803cdff16ee823bc01f158899c`.
Все результаты `fresh=true`. Input, итог и raw progress:
[PHASE7_EXPERIMENT_INPUT.json](PHASE7_EXPERIMENT_INPUT.json),
[PHASE7_EXPERIMENT_SUMMARY.json](PHASE7_EXPERIMENT_SUMMARY.json),
[PHASE7_EXPERIMENT.log](PHASE7_EXPERIMENT.log).

| Preliminary label | Unique input | Certified | Rejected / unrated / invalid proof | Inconclusive without timeout | Timeout |
|---|---:|---:|---:|---:|---:|
| Extreme | 2 | 0 | 0 | 0 | 2 |
| Ultra Extreme | 7 | 0 | 0 | 0 | 7 |

Всего inconclusive с учётом timeouts: Extreme2/2, Ultra7/7, total9/9.
Доказанных downgrades или rejects нет. Minimum certified clues = `null`,
maximum certified required rating = `null`, maximum certified genuine
bottlenecks = `null`, hardest certified technique/tier = `null`.
Ни один preliminary rating не скопирован в certified minimum.

У всех9 fresh uniqueness, logical solve, независимая proof validation и
повторяемость replay прошли. Фактическая minimality:5 true,4 false; default
`require_minimal=false` не превращает nonminimal в автоматический reject.
Три22clue кандидата — `8e2b…` Extreme, `bcf460…` и `ca88…` Ultra — получили
timeout после успешных математических/proof проверок. Их Extreme/Ultra minimum
пока не подтверждён и не опровергнут.

Каждая строка ниже имеет status `CERTIFICATION_TIMEOUT`; upper — только
максимальный rating independently valid observed path, не доказанный minimum.

| ID | Preliminary | Clues | Upper | Seconds | States | Cache hits |
|---|---|---:|---:|---:|---:|---:|
| puzzle-8e2b144cecb50551d96b | Extreme | 22 | 35 | 60.009 | 945 | 7650 |
| puzzle-f197179f12c6533697b1 | Extreme | 23 | 35 | 60.050 | 522 | 3154 |
| puzzle-bcf460fc20aeeee740c2 | Ultra Extreme | 22 | 39 | 60.675 | 171 | 2120 |
| puzzle-ca88d658a18eafb27c24 | Ultra Extreme | 22 | 55 | 60.010 | 105 | 1493 |
| puzzle-03122df59ac468dbf09d | Ultra Extreme | 24 | 55 | 60.002 | 80 | 1276 |
| puzzle-55684dd4bac9cb6a200f | Ultra Extreme | 24 | 55 | 60.003 | 81 | 974 |
| puzzle-310fab8b8581c087bc8a | Ultra Extreme | 25 | 55 | 60.001 | 91 | 777 |
| puzzle-f23734d386d6cc1e2328 | Ultra Extreme | 25 | 55 | 60.002 | 118 | 562 |
| puzzle-b4d935b1bf18e438b282 | Ultra Extreme | 26 | 50 | 60.002 | 92 | 848 |

Отдельный pilot двух настоящих candidates завершён до source freeze:
`puzzle-f197179f12c6533697b1` (Extreme,23clues) и
`puzzle-ca88d658a18eafb27c24` (Ultra,22clues). Оба получили timeout при60s;
states595 и128. Pilot fingerprint изменился во время параллельных исправлений,
поэтому это только diagnostic experiment, не окончательное acceptance evidence.
Сохранён в [PHASE7_PILOT_SUMMARY.json](PHASE7_PILOT_SUMMARY.json).
Ранее прерванный definitive attempt сохранил лишь один результат; он также
не включён в статистику нового полного запуска. Его evidence сохранён отдельно:
`PHASE7_INTERRUPTED_EXPERIMENT.log` и `PHASE7_INTERRUPTED_EXPERIMENT_LATEST.json`.

## 24–27. Производительность и limits

Definitive wall541.431s (включая export/reports); average certification60.083924s,
worst60.675315s у `puzzle-bcf460fc20aeeee740c2`. Cooperative overrun максимума
составил0.675315s сверх60s; просроченный результат не был сертифицирован.
Исследовано2205states: среднее245, minimum80, maximum945.
Invocation-local transposition cache дал18854hits; per-ID counts приведены выше.
Общее число lookup attempts отдельно не измеряется, поэтому hit-rate процент
не заявляется. Persistent final/rating cache reuse =0: все9 запущены fresh.

| Stage | Total seconds | Average seconds/candidate |
|---|---:|---:|
| Format | 0.106804 | 0.011867 |
| Uniqueness | 0.041020 | 0.004558 |
| Minimality | 0.199061 | 0.022118 |
| Human solve + deterministic replay | 48.976785 | 5.441865 |
| Independent observed-path proof validation | 0.593414 | 0.065935 |
| Alternative-path search | 490.733575 | 54.525953 |
| Proof checks внутри alternative search | 16.439053 | 1.826561 |

Последняя строка уже включена в alternative search и не суммируется с ним
как независимая CPU доля. Основная стоимость — перебор альтернативных deductions.
Все9 lower-threshold attempts завершились `INCONCLUSIVE_BUDGET`; top-level
статус у всех — timeout, failure reason `SEARCH_TIMEOUT`. Таймаутов9/9 (100%),
отдельных non-timeout inconclusive0. Diagnostics также фиксируют chain length/
node limits, ALS size/chain/work limits и forcing starts/depth/node limits.
Их пересечения не являются дополнительными кандидатами и не доказывают отсутствие
пути. Измеренные thresholds соответственно32,32,36,50,50,50,50,50,42.
Defaults ограничивают затраты, но на этой выборке не обеспечили ни одного
завершённого сертификата; достаточная production throughput не продемонстрирована.

## 28–30. Production/research output и причины отказа

Strict output: `data/production/puzzles.json`; research: `data/candidates.json`;
per-candidate diagnostics: `reports/certification/*.json`.
Production size: **0**; production puzzle IDs: `[]`. Research содержит9 records,
диагностических per-candidate reports —9. Production JSON заново прочитан и
проверен public `validate_production_database`; schema1, datasetKind, stats и
пустой puzzle list валидны. Проверки каждого production puzzle здесь пусты по
определению; это не положительный roundtrip реального strong certificate.
Final rejects отсутствуют: все9 результатов имеют `SEARCH_TIMEOUT`, а не
доказанное несоответствие Extreme/Ultra criteria. Timeout не означает downgrade.

Exporter принимает raw inputs и всегда fresh-certifies. Он не доверяет saved
flags/results. Duplicate IDs/strings дают structured rejection до дорогих calls.
JSON schema1 сохраняет обязательные поля; optional certification содержит
config и полное evidence. Metadata сравнивается с fresh result по strict
canonical JSON, отличая Boolean от number. Atomic temporary write/fsync,
JSON readback validation и destination readback предохраняют от частичной записи.
Отдельный public validator заново сертифицирует records и сравнивает metadata.

Legacy `generate`/`evolve` остаются research/demo export, а current
`data/puzzles.json` не заменяется. Empty strict production dataset допустим
и честно означает отсутствие accepted candidates; frontend не переключается
на пустую коллекцию.

## 31–32. Ограничения и доказательная граница

Complete negative proof относится только к описанному transition model:
реализованные finite patterns, simple candidate chains, disjoint ALS chains,
single-assumption clause propagation. Полного каталога всех человеческих техник,
arbitrary groups, overlapping ALS и recursive dynamic forcing нет.
Search exhaustion и incomplete detector enumeration всегда inconclusive.

Математически проверяются exact uniqueness, factual minimality и structure
каждого supplied proof. Не заявляются глобальная сложность вне model,
необходимость конкретного technique name, minimum clue count, optimality всех
secondary metrics или одинаковое число crises во всех путях.
Fixed-seed/time-cutoff runs могут останавливаться на разных frontiers;
timing-dependent inconclusive результаты не являются certified claims.

Symmetry deduplication, новый Monster search, hitting-set enumeration,
frontend integration и deployment не реализовывались. Git history отсутствует,
поэтому provenance хранится hashes/config/version. Desktop WebKit не заменяет
физическую iOS Safari проверку.

## 33. Critical independent review

Независимое critical review завершено на frozen fingerprint
`166aecc4915355c17af29d79b881acb1cd13fc0cd43576b8230f8102e5c96e76`.
Известных блокирующих ошибок ложной сертификации не найдено.
Четыре findings P2 исправлены и повторно проверены: повреждённый Empty Rectangle
теперь возвращает invalid proof вместо исключения; trivial gap считает именно
непрерывные TRIVIAL steps; canonical proof tie-break не зависит от порядка
эквивалентных AIC proofs; strict JSON comparison различает Boolean и number.
Дополнительно проверена нормализация tuple/list при JSON readback.

Reviewer targeted suite: 81 passed, 13.119s. Independent audit проверил все
30 registry techniques и 30 proof-family fixtures при отключённых detectors,
отклонил 337 повреждений premises, проверил 19 logical modules и пять ловушек
Exact API. Настоящий puzzle решён и replay-проверен за71 шаг с Exact API traps;
threshold search и advanced enumeration также не обращались к Exact.
Отдельно проверены ALS size omissions, forcing depth/node omissions и timeout
после опустошения frontier: incomplete work не превращается в negative proof.
Полный разбор и ограничения:
[PHASE7_REVIEW.md](PHASE7_REVIEW.md),
[PHASE7_REVIEW_AUDIT.json](PHASE7_REVIEW_AUDIT.json).

После полного definitive batch выполнен независимый readback audit: PASS.
Проверены все9 входов, совпадение individual reports с research, итоговые
счётчики и timings, provenance, config/status metadata и неизменность frozen
source inventory с учётом двух новых выходных datasets. Отдельный MRV checker
независимо подтвердил единственное решение каждого из9 puzzles.
Evidence: [PHASE7_FINAL_EVIDENCE_REVIEW.json](PHASE7_FINAL_EVIDENCE_REVIEW.json).

Положительные Extreme/Ultra decision branches проверены на контролируемых
результатах; это не заменяет реальный accepted certificate. Полный production
roundtrip реального сильного certified puzzle остаётся эмпирическим ограничением:
definitive dataset пуст.

## 34. Готовность к production frontend integration

**NOT READY для production integration с frontend:** certified content0.
Pipeline/API/CLI, strict export и metadata compatibility реализованы и проверены;
готовая к игре production коллекция этим экспериментом не получена. Текущий demo
frontend продолжает использовать прежнюю demo-базу. Чтобы объявить готовность,
нужны реальные завершённые certificates и проверенный непустой production
roundtrip при сохранении строгих gates. Phase 7 implementation, regression,
измерения и отчёт завершены; Phase 8, frontend integration и deployment не начаты.

Нормативный контракт: [CERTIFICATION_SPEC.md](CERTIFICATION_SPEC.md).
