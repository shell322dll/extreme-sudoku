# Phase 7.1 — Certification Search Performance & Negative Certificates

Дата: 2026-10-02, Europe/Moscow. Рабочая папка: `C:\Develop\Extreme Sudoku`.

**Phase 7.1 реализована, проверена review/re-review, regression и official export
завершены.** Из девяти Phase 6 candidates, которые в Phase 7 все получили
`CERTIFICATION_TIMEOUT`, один (`puzzle-8e2b144cecb50551d96b`, 22 clues) теперь
`CERTIFIED_EXTREME` с minimum required rating 35. Остальные восемь остаются
`CERTIFICATION_TIMEOUT`. Strict production dataset валиден и содержит **1** puzzle.

Статус изменили не оптимизации поиска как таковые: они дали примерно 2.2× больше
states в секунду на T=32, но ни одного статуса не поменяли. Статус изменил
формально доказанный negative certificate — Stuck-State Superset Lemma (SSL-v1).

Источники evidence (все ссылки относительные):

| Тема | Файлы |
|---|---|
| Baseline / final regression | [PHASE7_1_BASELINE_SUMMARY.json](PHASE7_1_BASELINE_SUMMARY.json), [PHASE7_1_FINAL_SUMMARY.json](PHASE7_1_FINAL_SUMMARY.json) |
| Profiling до изменений | [PHASE7_1_PROFILE_BASELINE.md](PHASE7_1_PROFILE_BASELINE.md), [PHASE7_1_PROFILE_BASELINE.json](PHASE7_1_PROFILE_BASELINE.json) |
| SSL: доказательства и независимое review | [PHASE7_1_STUCK_STATE_PROOFS.md](PHASE7_1_STUCK_STATE_PROOFS.md), [PHASE7_1_SSL_REVIEW.md](PHASE7_1_SSL_REVIEW.md) |
| Code review + re-review | [PHASE7_1_REVIEW.md](PHASE7_1_REVIEW.md) |
| Before/after benchmark | [PHASE7_1_BENCHMARK.md](PHASE7_1_BENCHMARK.md), [PHASE7_1_BENCHMARK.json](PHASE7_1_BENCHMARK.json) |
| Re-certification (analysis) | [PHASE7_1_RECERT.md](PHASE7_1_RECERT.md), [PHASE7_1_RECERT_SUMMARY.json](PHASE7_1_RECERT_SUMMARY.json) |
| Official export | [PHASE7_1_EXPORT_SUMMARY.json](PHASE7_1_EXPORT_SUMMARY.json), [PHASE7_1_EXPORT.log](PHASE7_1_EXPORT.log), [../data/production/puzzles.json](../data/production/puzzles.json) |
| Нормативный контракт | [CERTIFICATION_SPEC.md](CERTIFICATION_SPEC.md) |
| Предыдущие результаты | [PHASE7_REPORT.md](PHASE7_REPORT.md), [PHASE7_EXPERIMENT_SUMMARY.json](PHASE7_EXPERIMENT_SUMMARY.json) |

Git metadata отсутствуют; commits/tags не создавались. Provenance хранится
через SHA-256 aggregates и algorithm/config fingerprints.

## 1. Baseline test count

Fresh baseline 2026-10-02 10:12–10:14 UTC, Python 3.11.9, Windows 10.0.17763,
Chromium 153.0.8010.12, WebKit 26.6
([PHASE7_1_BASELINE_SUMMARY.json](PHASE7_1_BASELINE_SUMMARY.json)):

| Проверка | Baseline |
|---|---:|
| Python unittest | **350 passed**, OK; 99.17 s (wall 99.50 s) |
| Frontend Node tests | **16 passed**, 0 fail/skip/cancel |
| Browser scenario groups | **14/14 passed** |
| Responsive checks | **56** |

Первая попытка без `PYTHONPATH`/`PLAYWRIGHT_BROWSERS_PATH` упала на browser
(`ModuleNotFoundError playwright`). Повторный запуск был сделан с тем же окружением,
что и в Phase 7. Во время baseline параллельно мог идти CPU-heavy profiling, поэтому wall times
указаны как измерено.

## 2. Final test count

Final regression 2026-10-02 13:27–13:30 UTC
([PHASE7_1_FINAL_SUMMARY.json](PHASE7_1_FINAL_SUMMARY.json), логи
[PHASE7_1_FINAL_PYTHON.log](PHASE7_1_FINAL_PYTHON.log),
[PHASE7_1_FINAL_FRONTEND.log](PHASE7_1_FINAL_FRONTEND.log),
[PHASE7_1_FINAL_BROWSER.log](PHASE7_1_FINAL_BROWSER.log)):

| Проверка | Baseline | Final |
|---|---:|---:|
| Python unittest | 350 | **413 passed**, OK; 155.33 s (wall 155.76 s) |
| Frontend Node tests | 16 | **16 passed** |
| Browser scenario groups | 14 | **14/14 passed** |
| Responsive checks | 56 | **56** |

Добавлено 63 Python tests (новые модули `test_certification_search_opt.py` и
`test_certification_ssl.py`, см. [PHASE7_1_REVIEW.md](PHASE7_1_REVIEW.md)). Все три
команды завершились с exit code 0. Source aggregate `generator/`, `web/`, `data/`
(188 файлов) до и после прогона одинаковый:
`d3e4423c9b1e3ad6dba3307e76b77684e5f4c49854dc7c4b15cea558ce5f2bd4`, `source_unchanged=true`.
Regression выполнена **до** official export. Export затем перезаписал
`data/production/puzzles.json`, `data/candidates.json` и `reports/certification/*.json`
([PHASE7_1_EXPORT_SUMMARY.json](PHASE7_1_EXPORT_SUMMARY.json), notes).

## 3. Baseline candidate profiling

Только диагностика: instrumentation через in-process monkeypatching в
`docs/PHASE7_1_PROFILE_RUN.py`, по одному fresh subprocess на job, default
`CertificationConfig`, harness overhead 0.06 s на 60 s run
([PHASE7_1_PROFILE_BASELINE.md](PHASE7_1_PROFILE_BASELINE.md)). Детально
профилировались `threshold_search` для 8e2b@T=32 и ca88@T=50. Lattice- и
walk-probes делались для всех 9 candidates.

| Metric | 8e2b T=32, 60 s | 8e2b T=32, 300 s | ca88 T=50, 60 s | ca88 T=50, 300 s |
|---|---:|---:|---:|---:|
| Status | INCONCLUSIVE (TIME) | INCONCLUSIVE (TIME) | INCONCLUSIVE (TIME + limits) | INCONCLUSIVE (TIME + limits) |
| States explored | 958 | 4 689 | 122 | 659 |
| Unique states | 1 430 | 5 134 | 933 | 1 459 |
| Children | 9 169 | 56 103 | 2 622 | 9 416 |
| Child transposition hits | 84.4 % | 90.9 % | 64.4 % | 84.5 % |
| ms / expanded state | 62.6 | 64.0 | 492 | 455 |
| Enumerations с limit reason | 1/958 | 1/4 689 | **122/122** | **659/659** |
| RSS peak | 36 MB | 58 MB | 54 MB | 54 MB |

Доля времени: `StepEnumerator.enumerate` занимает 72–77 % (8e2b) и 92–94 % (ca88).
Stale pops, re-expansions и depth-improved re-push равны 0. Heap и signature занимают
меньше 0.02 % времени.

Walk-probes по всем 9: у 8e2b@32 141 случайная walk пришла в один и тот же terminal
G (125 candidates), enumeration там complete. У f197, ca88, 03122 и b4d9 найдено
несколько terminals (система не confluent при limit-dependent detectors). У bcf460 и
всех T=50/42 candidates limits встречаются в 100 % enumerations. Одна из 24 walks
для ca88 нашла валидный witness с max rating 50 < 55 (`validate_path` = valid). Ни
у одного candidate не нашлось witness ниже `extreme_threshold` = 30.

## 4. Основной источник timeout

Источник **структурный**. Это не константа на state.

1. **Экспоненциальная reachable state lattice.** Для 8e2b@32 на root есть 20
   попарно независимых persistent effects, отсюда доказанная нижняя граница
   **≥ 2^20 ≈ 1.05·10^6** reachable states. Для ca88@50 эта граница **≥ 2^83**.
   85–91 % сгенерированных children являются transpositions уже известных states.
   Unique states растут **линейно** с числом expansions (~1.09 и ~1.2 новых на
   expansion) без признаков насыщения за 300 s. При 63 ms/state полный обход 8e2b
   занял бы ≥ 18 h; уложиться в 60 s можно было бы только при < 60 µs/state.
2. **При T ≥ 36 PROVEN невозможен by construction.** ALS (`ALS_SIZE_LIMIT`
   срабатывает, пока в unit больше 5 empty cells), Forcing (depth/node/start) и
   Grouped AIC (chain length/node) дают limit reason в 100 % enumerations. Поэтому
   любая полностью завершённая exploration всё равно вернула бы INCONCLUSIVE.
   Для f197@32 limits встречаются в 63 % enumerations.
3. **Вторичный constant factor** — стоимость одной enumeration: при T=32 доминирует
   AIC (≈ 50 % wall), при T=50 — ALS 37–42 %, Forcing 23–30 % и Grouped AIC 17–18 %.
   Ещё 2–3× давали повторная работа над эквивалентными шагами (44–62 % children
   совпадают с sibling по successor) и JSON-сериализация proofs для tie-break
   (6–14 % времени).

Ordering не влияет на negative proofs. Memory, heap и signature узким местом
не являются.

## 5. Оптимизации

Все изменения ниже sound без дополнительных допущений. Ни одно из них не меняет
семантику статусов.

| # | Изменение | Где | Смысл |
|---|---|---|---|
| 1 | **Effect dedup** с сохранением lowest rating | `search.select_transitions` | Steps группируются по **signature successor state** (а не только по effect), из группы берётся min по (rating, `step_key`, full JSON). Разные states никогда не сливаются. Выбор не зависит от порядка входа |
| 2 | **Transposition / visited semantics** с depth rule | `search.threshold_search` | Каждая signature раскрывается не более одного раза. Re-open только при строго более мелком arrival и только если depth limit может сработать (`depth_bound(root) ≥ max_path_depth`) |
| 3 | Transposition lookup **до** validate/apply | `threshold_search` | Валидируется каждый step, создающий или переоткрывающий frontier entry, а значит каждое witness edge |
| 4 | **Per-invocation caches** | `enumeration.EnumerationCache`, `transitions.LRU` | Enumeration cache: key = (config fingerprint, full signature = values81 + masks81, technique), LRU на 12 000 записей, результаты с `TIME_LIMIT` не кэшируются. Validation cache: key = (signature, frozen `LogicStep`), 4 096 записей. Оба cache создаются заново на каждый `certify_puzzle` |
| 5 | **Fast apply** | `transitions.apply_step` | Те же preconditions, что у `human_solver.apply_step`, но одна финальная validation (обоснование через monotonicity). Witnesses replay-ятся reference-реализацией |
| 6 | Дешёвый canonical tie-break | `enumeration.representative` | JSON proof сериализуется только при полном tie по (rating, `step_key`). Representative тот же, что в Phase 7 |
| 7 | Shared `InferenceGraph` | `StepEnumerator._run` | AIC и Nice Loop используют один immutable graph на state |
| 8 | **Refactor в `minimax_descent`** с abstract provider | `search.py`, `transitions.py` | Descent отделён от Sudoku: provider interface (`initial`, `signature`, `enumerate`, `child`, `validate`, `negative_certificate`, …). Это позволило проверить алгоритм fuzz-тестами на random DAG |
| 9 | **Early REJECTED** | `pipeline.py` | Если validated witness имеет upper < `extreme_threshold`, результат `REJECTED` (`RATING_BELOW_EXTREME`). `minimum_required_rating` остаётся `None` |
| 10 | **Telemetry** и `negative_proof_possible` | `ThresholdResult.telemetry` | Lookups/hits, duplicates by family, branching, peak frontier, family seconds, первая expansion с каждым limit reason. Любой limit reason сбрасывает `negative_proof_possible` |
| 11 | **SSL-v1** negative certificate | `stuck_state.py` | См. §14–§16. Это единственное изменение, повлиявшее на статус |

Итог pure-оптимизаций ([PHASE7_1_BENCHMARK.md](PHASE7_1_BENCHMARK.md)):
**2.23×** states/60 s на 8e2b@32 и **1.39×** (instrumented 1.57×) на ca88@50.
Ни один статус не изменился: при SSL off все 9 candidates остаются
`CERTIFICATION_TIMEOUT` (`byStatus_ssl_off` в
[PHASE7_1_RECERT_SUMMARY.json](PHASE7_1_RECERT_SUMMARY.json)).

## 6. Old states

Phase 7 definitive experiment ([PHASE7_EXPERIMENT_SUMMARY.json](PHASE7_EXPERIMENT_SUMMARY.json)):
всего 2 205 states, среднее 245, min 80, max 945. По candidates: 8e2b 945,
f197 522, bcf460 171, ca88 105, 03122 80, 55684 81, 310fab 91, f23734 118, b4d9 92.
Plain benchmark baseline, 60 s: 8e2b@32 — 990 explored / 1 458 unique;
ca88@50 — 123 / 934.

## 7. New states

Official export ([PHASE7_1_EXPORT_SUMMARY.json](PHASE7_1_EXPORT_SUMMARY.json)):
8e2b 0 (SSL certificate, поиск не нужен), f197 1 126, bcf460 464, ca88 151,
03122 119, 55684 117, 310fab 121, f23734 143, b4d9 119. Сумма 2 360.
Plain benchmark, 60 s: 8e2b@32 при SSL off — **2 203** explored / 2 675 unique;
при SSL on — 0 explored, 0.29 s. ca88@50 при SSL off — **171** / 971.
Масштабный probe f197 на 300 s ([PHASE7_1_RECERT.md](PHASE7_1_RECERT.md) §3):
5 581 explored / 5 910 unique, рост линейный, насыщения нет.

## 8. Old/new branching

Instrumented benchmark ([PHASE7_1_BENCHMARK.md](PHASE7_1_BENCHMARK.md) §2):

| Metric | 8e2b old | 8e2b new | ca88 old | ca88 new |
|---|---:|---:|---:|---:|
| Raw steps / state | 9.59 | 10.46 | 22.77 | 17.73 |
| Distinct children / state (effective branching) | 5.36 | 5.69 | 10.27 | 7.84 |
| Duplicates, убранные до apply | 0 | 10 079 (45.6 % raw) | 0 | 1 690 (55.8 %) |

Effective branching **по сути не изменился**. Выигрыш получен за счёт стоимости
одного state, а не за счёт сокращения state space. Профиль baseline: max 62
(8e2b) и 154 (ca88) steps на state. f197: mean branching 5.20 (60 s) и 6.33 (300 s).

## 9. Old/new cache hit rate (и смена знаменателя)

| Run | Old hit rate | New hit rate |
|---|---:|---:|
| 8e2b T=32 (instrumented) | 7 624 / 9 035 = **84.4 %** | 9 454 / 12 038 = **78.5 %** |
| ca88 T=50 (instrumented) | 1 564 / 2 474 = **63.2 %** | 369 / 1 339 = **27.6 %** |

**Смена знаменателя.** Old: lookup делался для каждого applied child, включая
siblings с одинаковым successor. New: equal-successor siblings удаляются раньше,
в `select_transitions`, и lookup не проходят. Поэтому падение hit rate — артефакт
знаменателя, а не ухудшение. Сопоставимая метрика — доля steps, разрешённых без
нового state, (dup + hits) / raw: 8e2b 84.4 % → **88.3 %**, ca88 63.2 % → **67.9 %**.

В Phase 7 известны только абсолютные hits (18 854 суммарно). Lookups там не
измерялись, поэтому hit rate Phase 7 не заявлялся. Re-cert TT hit rate по
candidates: от 18.6 % (03122) до 74.3 % (f197).

Enumeration/validation caches внутри одного exhaustive `threshold_search` дали
**0 hits** (каждый expanded state новый). Они окупаются только между стадиями:
8e2b SSL on — 1 858/2 082 (89 %), ca88 SSL on — 3 769/8 841 (43 %, closure,
переиспользованный fallback search). В 300 s probe f197 enumeration LRU
(старый размер 120 000) заполнился, RSS был 158 MB. После re-review LRU уменьшен
до 12 000 / 4 096.

## 10. Old/new runtime

| | Phase 7 | Phase 7.1 |
|---|---:|---:|
| Wall всего batch (вкл. export) | 541.43 s | 482.86 s |
| 8e2b | 60.009 s (TIMEOUT) | **1.72 s** (export) / 2.0 s (re-cert), CERTIFIED |
| Остальные 8 | 60.0–60.675 s, TIMEOUT | 60.001–60.003 s, TIMEOUT |
| ms / expanded state, 8e2b@32 (plain) | 60.6 | 27.2 |
| ms / expanded state, ca88@50 (plain) | 487.8 | 350.9 |
| SSL check, 8e2b@32 | — | 0.29–0.32 s, PROVEN |
| SSL closure перед fallback, T ≥ 36 | — | 1.4–3.8 s |

Human replay съедает 5–13 s из 60 s budget у T=50 candidates.
RSS: 8e2b SSL off 75 MB (было 29 MB, рост из-за caches), SSL on 25 MB.

## 11. AIC timing before/after

ms на expanded state, product `family_enumeration_seconds` (new) против
instrumented baseline. Цифры new включают общую постройку inference graph:

| Family | 8e2b old → new | ca88 old → new |
|---|---:|---:|
| AIC | 31.5 → **15.0** | 27.6 → **12.0** |
| Grouped AIC | — | 92.9 → **47.7** |
| X-Chain, XY-Chain, Nice Loop (сумма) | 11.2 → **5.5** | 11.4 → **5.6** |

Ускорение примерно 2× за счёт shared graph, link objects только при emit и
дешёвого canonical tie-break. Enumeration output при этом не изменился: 204/204
идентичных результатов против pre-7.1 baseline (step JSON hashes, limit reasons,
`complete`, `work`; [PHASE7_1_REVIEW.md](PHASE7_1_REVIEW.md)).

## 12. ALS before/after

ALS-XZ + ALS-XY-Wing + ALS Chain, ca88@50: **188.4 → 181.4 ms/state, без
изменений**. ALS не ускорялся. Теперь это доминирующая стоимость при T=50
(≈ 52 % wall). Поэтому T=42/50 searches получили лишь ±15 % (в пределах шума).

## 13. Forcing before/after

Forcing Chain / Nishio, ca88@50: **176.2 → 93.0 ms/state** (≈ 1.9×). Limit reasons
`FORCING_DEPTH_OR_NODE_LIMIT` / `FORCING_START_LIMIT` остаются во всех
T=50 enumerations.

## 14. Search algorithm before/after

**Before (Phase 7):** greedy Human Solver path задаёт upper witness. Затем
best-first `threshold_search` на ближайшем меньшем registry threshold
(priority = число candidates). Equal signatures сливаются, shallower arrival
доминирует. Каждый enumerated step валидируется и применяется. Проверка
`PROVEN_UNSOLVABLE_WITHIN_MODEL` возможна только после полного обхода без
omitted work.

**After (Phase 7.1):**

- `minimax_descent(root, ratings, config, provider)` работает поверх abstract
  provider. Thresholds — registry ratings ∪ {0} строго ниже текущего upper.
  Node budget общий на весь descent. SOLVED даёт более дешёвый validated witness
  (дополнительно fresh `validate_path`) и descent продолжается. PROVEN ниже
  witness делает результат conclusive. Всё остальное — inconclusive stop.
- В начале каждого `threshold_search` при `use_stuck_state_lemma=True` (default)
  пробуется SSL. Сначала строится deterministic cheapest-first closure G. Затем
  `check_certificate` с guards G0–G8 на fresh objects.
  - Принятый certificate ⇒ `PROVEN_UNSOLVABLE_WITHIN_MODEL`,
    `negative_proof_kind = STUCK_STATE_SUPERSET_LEMMA`.
  - Решённая closure ⇒ witness при тех же depth/node ограничениях и с replay.
  - `ERROR` (провал G8 replay) ⇒ `ERROR`.
  - Любой другой исход (guard FAIL, timeout) ⇒ **неизменный exhaustive fallback**.
- Exhaustive search: visited semantics, dedup по successor, transposition до
  validation, fast apply, caches. Proven результат помечается
  `negative_proof_kind = EXHAUSTIVE_SEARCH`.
- После descent работает **confluence alarm** (`confluence_violation`).
  Срабатывание: SOLVED при T' ≤ certified T, witness с rating ≤ T, prefix state
  не ⊒ G или prefix step нарушает SSL относительно G. Результат ⇒ `ERROR` ⇒
  `INVALID_PROOF`. Исключение внутри проверки тоже считается alarm (fail closed).
- **Exact solver в logical search не используется**: ни `exact_solver`, ни
  solution grid нет в search, transitions, enumeration и stuck_state. `proofs.py`,
  `human_solver.py`, solver techniques и `exact_solver` побайтно совпадают с
  baseline ([PHASE7_1_REVIEW.md](PHASE7_1_REVIEW.md)).
- **Parallelization не реализована.** Приоритетом была эффективность одного
  candidate: root cause структурный, и параллельный exhaustive search не изменил
  бы статусы. Candidate-level parallelism (независимые candidates в отдельных
  процессах) остаётся возможной будущей работой. Все замеры Phase 7.1
  последовательные.

## 15. Canonical step strategy

- **Enumerator** (`canonical_steps`, семантика Phase 7): одна canonical proof на
  (effects, **rating**). Equal effects разных техник с разными ratings выживают,
  потому что от этого зависят bottleneck evidence и `ALTERNATIVE_STEP_LIMIT`.
  Representative — min по (rating, `step_key`, full JSON proof). JSON считается
  только для настоящих ties, итог совпадает с Phase 7 (review check 2).
- **Search** (`select_transitions`): steps группируются по signature successor
  через ratings. Из группы берётся cheapest proof. Порядок transitions:
  placements, затем больше eliminations, затем ниже rating, затем `step_key`. Он
  влияет только на scheduling.
- **SSL closure** (`compute_closure`): rating levels ≤ T перебираются по
  возрастанию, применяется первый step первого непустого level в canonical порядке
  (rating, `step_key`). Каждый step проходит `proofs.validate_step` и
  reference `apply_step`. Путь к G для теоремы логически безразличен (важно
  только root ⊒ G).

## 16. Dominance rules

1. **Successor dominance:** steps с одинаковым successor взаимозаменяемы, кроме
   собственного rating. Cheaper representative не повышает max rating, число
   extreme steps и score.
2. **Transposition:** сливаются только равные полные signatures (values81 +
   masks81). Разные states не сливаются никогда.
3. **Depth rule:** при binding depth limit более мелкий arrival доминирует более
   глубокий (re-open). Иначе работает plain visited semantics. Max-rating reopen,
   найденный в review как P2-1, удалён.
4. **SSL order ⊒** (`X ⊒ G`: `L_G(c) ⊆ L_X(c)` для каждой клетки, empty в G ⇒
   empty в X) проверяется bitwise напрямую (G2), а не выводится из пути. Это
   dominance-отношение используется только в составе доказанной теоремы.
5. **Forced-move / trivial closure.** Plain closure («применить все singles или
   forced moves и считать результат эквивалентным») **не принята как допущение**.
   Profiling показал, что такие shortcuts unsound для текущей реализации при
   limit-dependent detectors (несколько terminals у f197, ca88, 03122, b4d9).
   Closure используется **только внутри SSL**, где soundness доказана леммой и
   проверена guards. Partial-order / stubborn-set reduction и eager singles не
   реализованы по той же причине.
6. Subset-dominance между effects (в профиле 18 из 39 root effects 8e2b — строгие
   подмножества других) для pruning **не используется**.

## 17. Threshold strategy

- **Upper bound:** max rating independently validated Human Solver path
  (observed upper). Каждый SOLVED threshold даёт более дешёвый witness и строго
  понижает upper. Thresholds берутся только **строго ниже** известного witness.
- **Порядок:** сверху вниз, ближайший меньший registry rating (`lower[-1]`).
  Transition sets вложены по T, поэтому PROVEN непосредственно ниже witness
  исключает все меньшие thresholds. SSL certificate при T также покрывает все T' ≤ T.
- **Lower-bound heuristic:** deep-rating lower bound **для pruning не
  использовался**. Поле `minimum_rating_lower_bound` в bottleneck events —
  описательная evidence (`bottleneck_threshold`), не pruning.
- **Early REJECTED** использует только upper bound: validated witness ниже 30
  доказывает, что minimum < Extreme floor.
- Фактически в Phase 7.1 каждый descent остановился на **первом** threshold:
  8e2b T=32 (PROVEN через SSL ⇒ minimum = 35), f197 T=32, bcf460 T=36,
  ca88/03122/55684/310fab/f23734 T=50, b4d9 T=42. Cheaper witness нигде найден
  не был. Witness ≤ 50 для ca88 из profiling random walk в production не
  используется (witness portfolio не реализован), поэтому ca88 по-прежнему
  ищется при T=50 с upper 55.

## 18. Budget semantics

Defaults не менялись: 60 s, node/state 10 000/10 000, path depth 256,
alternatives 512, chain 19/100 000, ALS 4/5/30 000, forcing 12/2 000/160. Добавлен
только флаг `use_stuck_state_lemma=true`, он входит в config fingerprint
`bdf36558…` ([CERTIFICATION_SPEC.md](CERTIFICATION_SPEC.md), Centralized budgets).

- **TIME / NODE / STATE / MEMORY / PATH_DEPTH** и любой enumerator limit ⇒
  `INCONCLUSIVE_BUDGET`, никогда PROVEN. PROVEN возвращается только при пустом
  множестве `reasons`.
- Top-level: timeout ⇒ `CERTIFICATION_TIMEOUT` / `SEARCH_TIMEOUT`, иначе
  `SEARCH_INCONCLUSIVE`. Timeout никогда не означает downgrade или reject.
- Node budget общий на descent. Solved SSL closure учитывается в
  `states_explored` и должна укладываться в `max_path_depth` и оставшийся
  node budget.
- Timeout внутри SSL closure или guard check ⇒ certificate не выдаётся
  (G0/G4 deadline). Поздний certificate невозможен.
- Таймер cooperative. Результаты с `TIME_LIMIT` не кэшируются.
- `negative_proof_possible = false` ровно тогда, когда встречен хотя бы один
  limit reason. Значение информационное, статус решается по `reasons`.

## 19. Результаты всех 9 candidates

Official export 2026-10-02 13:39 UTC, команда
`python -m generator certify --input docs/PHASE7_EXPERIMENT_INPUT.json --fresh …`,
exit 0, algorithm fingerprint `3ccb7aa0…`, config fingerprint `bdf36558…`
([PHASE7_1_EXPORT_SUMMARY.json](PHASE7_1_EXPORT_SUMMARY.json),
[PHASE7_1_EXPORT.log](PHASE7_1_EXPORT.log)). Elapsed и states взяты из export.
Previous — Phase 7 ([PHASE7_EXPERIMENT_SUMMARY.json](PHASE7_EXPERIMENT_SUMMARY.json)).

| ID | Clues | Previous result (states) | New result | Elapsed, s | States | Upper | Threshold | Min. required rating | Status |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| puzzle-8e2b144cecb50551d96b | 22 | TIMEOUT (945) | T=32 PROVEN (SSL) | 1.72 | 0 | 35 | 32 | **35** | **CERTIFIED_EXTREME** |
| puzzle-f197179f12c6533697b1 | 23 | TIMEOUT (522) | INCONCLUSIVE_BUDGET | 60.00 | 1 126 | 35 | 32 | null | CERTIFICATION_TIMEOUT |
| puzzle-bcf460fc20aeeee740c2 | 22 | TIMEOUT (171) | INCONCLUSIVE_BUDGET | 60.00 | 464 | 39 | 36 | null | CERTIFICATION_TIMEOUT |
| puzzle-ca88d658a18eafb27c24 | 22 | TIMEOUT (105) | INCONCLUSIVE_BUDGET | 60.00 | 151 | 55 | 50 | null | CERTIFICATION_TIMEOUT |
| puzzle-03122df59ac468dbf09d | 24 | TIMEOUT (80) | INCONCLUSIVE_BUDGET | 60.00 | 119 | 55 | 50 | null | CERTIFICATION_TIMEOUT |
| puzzle-55684dd4bac9cb6a200f | 24 | TIMEOUT (81) | INCONCLUSIVE_BUDGET | 60.00 | 117 | 55 | 50 | null | CERTIFICATION_TIMEOUT |
| puzzle-310fab8b8581c087bc8a | 25 | TIMEOUT (91) | INCONCLUSIVE_BUDGET | 60.00 | 121 | 55 | 50 | null | CERTIFICATION_TIMEOUT |
| puzzle-f23734d386d6cc1e2328 | 25 | TIMEOUT (118) | INCONCLUSIVE_BUDGET | 60.00 | 143 | 55 | 50 | null | CERTIFICATION_TIMEOUT |
| puzzle-b4d935b1bf18e438b282 | 26 | TIMEOUT (92) | INCONCLUSIVE_BUDGET | 60.00 | 119 | 50 | 42 | null | CERTIFICATION_TIMEOUT |

Upper и threshold взяты из export (`observed_upper_rating`) и
[PHASE7_1_RECERT.md](PHASE7_1_RECERT.md) (threshold result).

У всех 9 candidates uniqueness, human solve, proof validation и replay прошли.
Minimal = true у 8e2b, f197, bcf460, ca88, 03122 и false у остальных четырёх
(`require_minimal=false`). Failure reason у 8 timeouts — `SEARCH_TIMEOUT`.

Certificate 8e2b ([PHASE7_1_RECERT.md](PHASE7_1_RECERT.md),
[../data/production/puzzles.json](../data/production/puzzles.json)):

- SSL-v1 при T=32: closure length 28, closure candidates 125 (это тот же G, что в
  baseline lattice study), все guards PASS.
- Certified path 84 steps, tier EXTREME, certified bottlenecks 3, late-game 0,
  advanced steps 17, longest chain 13, distributed bins 2, max trivial gap 35.
- Не Ultra: 35 < `ultra_threshold` 36.
- При SSL off тот же candidate остаётся TIMEOUT (1 684 states): certificate получен
  только благодаря лемме.

Re-certification run ([PHASE7_1_RECERT.md](PHASE7_1_RECERT.md), fingerprint
`85753039…`) дал те же статусы. Числа states в нём немного другие (1 018, 402, 144, …),
потому что после него был remediation кода, а параллельно шёл test suite.
Решающим является export на текущем коде.

## 20. Counts по статусам

| Status | Phase 7 | Phase 7.1 |
|---|---:|---:|
| CERTIFIED_EXTREME | 0 | **1** |
| CERTIFIED_ULTRA_EXTREME | 0 | **0** |
| REJECTED | 0 | **0** |
| INCONCLUSIVE (`CERTIFICATION_TIMEOUT`; отдельных `SEARCH_INCONCLUSIVE` нет) | 9 | **8** |

## 21. Минимум clues среди certified

**22** (`minCluesAmongCertified`, единственный certified puzzle 8e2b).

## 22. Лучший certified required rating

**35.0** (`bestCertifiedRating`, tier EXTREME, evidence ниже minimum —
`STUCK_STATE_SUPERSET_LEMMA` при T=32). Certified Ultra нет.

## 23. Размер production dataset

**1 puzzle** — `data/production/puzzles.json`: schemaVersion 1,
`datasetKind = production-certified`, generatorVersion 0.5.0,
stats `{"total": 1, "byDifficulty": {"Extreme": 1}}`. Запись содержит
`certification.negativeProofKind = STUCK_STATE_SUPERSET_LEMMA`,
`requiredRating 35.0`, `searchConclusive true`, `genuineBottlenecks 3`.

Readback через public `validate_production_database`: **ok**, 1.79 s. Validator
заново сертифицирует record и сравнивает metadata. Это первый реальный
production roundtrip непустого certified record. Research `data/candidates.json`
содержит 9 records, reports — 9 штук (старые Phase 7 reports с теми же именами
перезаписаны, stale reports не осталось).

## 24. Known limitations

1. **8 из 9 inconclusive** (все `CERTIFICATION_TIMEOUT`):
   - **f197@32:** SSL FALLBACK по **G4**. Closure G пустой, но enumeration не
     complete (`AIC/Nice Loop: CHAIN_LENGTH_LIMIT, CHAIN_NODE_LIMIT`). Те же
     chain limits появляются в search уже на expansions 2–6, так что даже
     завершённый search при T=32 не дал бы PROVEN. Rating range 30–35 не
     опровергнут и не подтверждён.
   - **bcf460@36, b4d9@42, ca88 / 03122 / 55684 / 310fab / f23734 @50:** SSL
     неприменим (G5.scope: T ≥ 36; G5.proven: ALS-XZ и выше не доказаны). В
     100 % enumerations есть ALS / Forcing / Grouped AIC limits, поэтому PROVEN
     невозможен by construction. Больше времени может дать только cheaper
     witness, но не certificate минимума.
2. **ALS не ускорен** (188.4 → 181.4 ms/state). При T=50 ALS — ≈ 52 % wall.
3. **SSL scope только T < 36.** ALS (≥ 36) не анализировался. Для Forcing Chain
   найден правдоподобный механизм контрпримера (emission condition не монотонна).
   Nishio не анализировался.
4. **Grouped AIC: эмпирическое покрытие слабое.** Доказательство принято после
   закрытия gap C1. Но на реальных puzzles G при T=35 ни разу не был complete;
   Grouped AIC покрыт только synthetic states (тест D′: 30 complete G, 2 371
   Grouped AIC steps, 0 violations). Практическая польза SSL при T=35 пока мала,
   при T=32 — реальна.
5. **Monkeypatch scope.** Identity pins (72 объекта) ловят подмену entry points.
   Monkeypatching более глубоких helpers (например
   `solver.techniques.chains.conflicts`, `step_key`, `PEERS`, методы
   `SudokuState`) в том же процессе может дать ложный SSL certificate.
   Production code ничего не патчит в runtime. Принято как документированное
   ограничение (P2-2 residual).
6. **Unvalidated duplicate / transposition edges.** Steps, ведущие в уже
   известный state, и non-representative дубликаты не валидируются ни в
   exhaustive, ни в SSL режиме. Model от этого не ослаблен, witness edges
   валидируются всегда. Но защитный alarm «detector выдал invalid proof» слабее,
   чем в pre-7.1 search, который валидировал каждый step. Задокументировано в spec.
7. **Pre-7.1 production records нужно перегенерировать.** `CERTIFICATION_VERSION`
   остался "1", но config получил `use_stuck_state_lemma`, а record —
   `negativeProofKind`. Поэтому старые records не проходят
   `validate_production_database` (fail closed). Текущий dataset уже
   перегенерирован.
8. **Caches дают 0 hits внутри одного search.** Enumeration и validation caches
   окупаются только между стадиями (SSL closure → fallback → bottlenecks) и
   повышают RSS.
9. Cache poisoning внутри процесса обманывает exhaustive search (SSL отвергает
   его через G4 fresh enumerator). Вне in-process вмешательства это недостижимо (N2).
10. Witness portfolio и randomized restarts не реализованы. Валидный witness ≤ 50
    для ca88 из profiling в production descent не используется.
11. Model по-прежнему ограничен реализованными finite patterns, simple chains,
    disjoint ALS и single-assumption forcing, как в Phase 7. Desktop WebKit не
    заменяет физическую проверку iOS Safari.

## 25. Готовность к frontend integration

**Честная оценка: технически pipeline готов, по контенту — NOT READY для
полноценной production integration.**

- Strict production dataset впервые непустой: **1** certified Extreme puzzle,
  прошедший fresh re-certification readback. Контракт metadata и roundtrip
  реального сильного certificate подтверждены.
- Одного puzzle недостаточно для игровой коллекции. Ultra Extreme отсутствует,
  8 из 9 candidates не сертифицированы.
- Frontend в этой фазе **не менялся**: по code review изменены только
  `generator/certification/*` и тесты. Frontend Node tests (16) и browser
  regression (14 groups / 56 responsive) остались на baseline-уровне. Demo frontend
  продолжает использовать прежнюю demo-базу. Переключение на production dataset
  не выполнялось и не проверялось.
- Чтобы объявить готовность, нужны: больше certified puzzles (новые candidates в
  scope SSL T < 36 или новые доказанные negative certificates для ALS/Forcing) и
  отдельная фаза интеграции с UI-проверкой.

## 26. Final critical review

**SSL review** ([PHASE7_1_SSL_REVIEW.md](PHASE7_1_SSL_REVIEW.md)):

- Theorem §2 и все families ≤ 32: **ACCEPT**. Grouped AIC: ACCEPT-WITH-CONDITIONS
  из-за gap в walk lemma (open chain сжимается до одного strong link). Gap закрыт
  через bivalue-cell и Locked Candidates, условие C1 внесено в
  [PHASE7_1_STUCK_STATE_PROOFS.md](PHASE7_1_STUCK_STATE_PROOFS.md) Revision 2.
- Итог: **T=32 ACCEPT; T=35 ACCEPT после C1; T ≥ 36 неприменимо.**
- Adversarial проверки без единого нарушения:
  - 275 037 states / 3 642 263 steps на random walks; все terminals равны G;
  - 409 528 states на random supersets;
  - degenerate G′, synthetic states, targeted Grouped AIC;
  - 22 полностью исчерпанных lattice segments, в каждом ровно один terminal = G.
- Рекомендации R1–R6 реализованы: pins `certification/models.py` и
  `solver/techniques/__init__.py`, confluence alarm, G8 ⇒ ERROR, regression tests.

**Code review + Re-review** ([PHASE7_1_REVIEW.md](PHASE7_1_REVIEW.md)):

- **P0/P1 нет.** Ложный certificate или ложный PROVEN через production paths
  получить не удалось.
- Проверки:
  - enumeration equivalence 204/204 с pre-7.1 baseline;
  - 102 search cases без конфликтов статусов (15 PROVEN = PROVEN с идентичным
    числом expansions; 6 новых SOLVED там, где baseline исчерпал budget; 21/21
    conclusive verdicts exhaustive и SSL совпадают);
  - fuzz 3000 + 1000 descents + 3000 visited-mode с 0 ошибок;
  - SSL attacks (poisoned cache, T ≥ 36, tampered pins/ratings, timeout) все
    отвергнуты.
- Восемь P2 исправлены и перепроверены:
  - P2-1: max-rating reopen удалён, node accounting равен baseline (300 = 300);
  - P2-2: identity pins на 72 объекта;
  - P2-3: validation scope описан в spec;
  - P2-4: `solver/models.py` добавлен в pins, теперь 17 файлов;
  - P2-5: solved closure подчиняется depth/node budget;
  - P2-6: confluence check fail-closed;
  - P2-7: исправлен docs drift;
  - P2-8: config fingerprint вошёл в cache key.
- Остаточная заметка: monkeypatch deeper helpers (§24.5), не blocker.
- Re-review: **413 tests OK**. **Verdict: код Phase 7.1 безопасен для
  производства production dataset.** Pre-7.1 records нужно перегенерировать (N1);
  это сделано official export.

## Definition of Done

| # | Пункт (из задания) | Статус и evidence |
|---:|---|---|
| 1 | Baseline profiling выполнен | Выполнено: §3, [PHASE7_1_PROFILE_BASELINE.md](PHASE7_1_PROFILE_BASELINE.md) |
| 2 | Определён основной источник timeout | Выполнено: структурный (lattice ≥ 2^20, 85–91 % transpositions; при T ≥ 36 limits в 100 % enumerations), §4 |
| 3 | Canonical LogicStep effect реализован или подтверждён | Выполнено: `canonical_steps` по (effects, rating) подтверждён (204/204 с baseline); в search добавлен dedup по successor signature, §5, §15 |
| 4 | Equivalent-step branching существенно уменьшен | Частично: 45.6–55.8 % duplicate steps убираются до apply/validate, но effective branching (distinct children/state) почти не изменился (5.36→5.69, 10.27→7.84); выигрыш в стоимости одного state, §8 |
| 5 | Transposition table корректна | Выполнено: только равные полные signatures; fuzz 3000+3000, 102 search cases без конфликтов, §16, §26 |
| 6 | Dominance pruning корректен | Выполнено: visited semantics + depth rule; secondary-metric (max-rating) re-open удалён по P2-1, node accounting = baseline, §16, §26 |
| 7 | State cache работает | Выполнено с оговоркой: внутри одного search 0 hits (каждый state новый); польза между стадиями (8e2b 89 %, ca88 43 %), §9, §24.8 |
| 8 | Expensive technique cache работает там, где безопасно | Выполнено: per-technique cache, key = config fingerprint + full signature + technique, без `TIME_LIMIT`; `InferenceGraph` общий для AIC/Nice Loop на state, §5, §11 |
| 9 | Threshold search оптимизирован | Выполнено: 2.23× (T=32) и 1.39× (T=50) states за 60 s; статусы от этого не меняются, §5, §10 |
| 10 | Existing solution upper bound используется | Выполнено: validated Human Solver path задаёт upper, thresholds строго ниже, §17 |
| 11 | Search semantics остаются minimax-correct | Выполнено: fuzz 1000 `minimax_descent` против brute-force minimax, mock graph test, §14, §26 |
| 12 | Timeout/node exhaustion остаются INCONCLUSIVE | Выполнено: §18; TIME/NODE/STATE/MEMORY/PATH_DEPTH tests, review contract checklist |
| 13 | Proof Validators не ослаблены | Выполнено: `proofs.py` побайтно как в baseline; witness edges и closure steps валидируются; не валидируются только transposition/duplicate edges (§24.6), §14 |
| 14 | Human Solver anti-cheating rules сохранены | Выполнено: `human_solver.py` и techniques без изменений; нет `exact_solver`/solution в search, §14 |
| 15 | Все Phase 1–7 tests проходят | Выполнено: 413 Python OK (включая прежние 350), 16 frontend, 14/56 browser, §2 |
| 16 | Новые optimization tests проходят | Выполнено: 63 новых теста (`test_certification_search_opt.py`, `test_certification_ssl.py`) в составе 413 OK, §2 |
| 17 | Выполнено before/after profiling | Выполнено: [PHASE7_1_BENCHMARK.md](PHASE7_1_BENCHMARK.md), §8–§13 |
| 18 | Все 9 real candidates повторно проверены | Выполнено: re-cert и official export, §19 |
| 19 | Хотя бы один candidate завершён CONCLUSIVE | Выполнено: 8e2b, T=32 PROVEN (SSL), minimum 35, §19 |
| 20 | Если candidate сертифицирован — production export проходит | Выполнено: size 1, `validate_production_database` ok, §23 |
| 21 | Если candidate rejected — причина documented | N/A: rejected нет; причины 8 inconclusive описаны в §24.1 |
| 22 | Выполнен critical review | Выполнено: SSL review + code review + re-review, P0/P1 нет, §26 |
| 23 | Phase 8 не начата | Выполнено: Phase 8 и frontend integration не начаты, §25 |

Не выполнено и не заявляется: parallelization (§14), ускорение ALS (§12),
negative certificate для T ≥ 36 (§24), frontend integration (§25).

---

**Phase 7.1 complete. Phase 8 и frontend integration не начаты.**
