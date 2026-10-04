# Phase 10 — Difficulty Expansion: Easy & Medium

Обновлено: 2026-10-04 (Europe/Moscow). **Phase 10 завершена: production содержит 9 Easy, 9 Medium
и все прежние 10 Extreme; финальные проверки, push, Pages deployment и public smoke успешны.**
Production merge и публикация выполнены после явного подтверждения пользователя. Следующая фаза не начата.

## Production и неизменность Extreme

- Фактическая исходная база: **10 Extreme**, а не 9. Все они сохранены в production.
- В production добавлено **9 Easy + 9 Medium**; итог **28** задач. Все записи совпадают с проверенной репетиционной базой.
- SHA-256 исходного `data/production/puzzles.json` и backup:
  `859e581c3f7c03e285acd87880f3aeceb42bbb55d59157916237e7a9a2ff28c1`.
- SHA-256 после merge:
  `d5ce2f329526d117a5bf1f7b20f62fc07241e34d1ee37da13515d5501b576046`.
- Все 10 полных Extreme records равны исходным, включая IDs, строки, ratings и certification metadata.
  Независимый review подтвердил также неизменность каждого прежнего форматированного блока в raw bytes нового JSON.
- `generator/certification`, `generator/solver`, `generator/sudoku`, `generator/rating` не изменялись;
  fingerprints прежних сертификатов не затронуты. Новый код находится в `generator/production`.
- Ultra/Monster research и расширение Stuck-State Lemma не выполнялись.

## Фактические пороги

Source of truth — `generator/rating/config.py`, `registry.py`, `classification.py`, без изменения значений.
Классификация использует **hardest_required_rating**, найденный Deep среди проверенных порогов.
Это не `clues` и не агрегированное поле `rating`.

| Категория | Правило действующего классификатора |
| --- | --- |
| Easy | `0 <= requiredRating < 2`; фактический максимум техники 1.2 |
| Medium | `2 <= requiredRating < 7`; фактический максимум техники 5.2 |
| Hard | `7 <= requiredRating < 12` |
| Expert | `requiredRating >= 12`, если не выполнены дополнительные Extreme/Ultra gates |
| Extreme | `requiredRating >= 30`, unique Deep human solve, Basic и Intermediate STUCK, Extreme SOLVED, >=3 advanced steps и >=2 true bottlenecks |
| Ultra Extreme | Extreme gates плюс `requiredRating >=36`, >=5 advanced steps, >=3 bottlenecks, chain length >=8, >=2 distributed bins и chain/ALS/forcing steps |

Для Extreme/Ultra это preliminary Difficulty Engine classification, после которой production по-прежнему
требует отдельную неизменную certification. Порог Expert не ограничен сверху числом 30: без дополнительных
gates высокая техника сама по себе не даёт Extreme.

Easy registry: Full House **0.5**, Naked Single **1**, Hidden Single **1.2**.
Medium допускает Easy techniques плюс Locked Candidates **2**, Naked Pair **3**, Hidden Pair **3.2**,
Naked Triple **5**, Hidden Triple **5.2**. Quad (7) и выше исключены.

Агрегированный standard `rating` остаётся результатом существующего Deep:
required rating + `0.1*log1p(total_score)` + `0.05*bottleneck_severity` + `0.1*distributed_advanced_steps`.
У Extreme существующее поле rating остаётся certified minimum maximum step rating.

## Verification model

Минимальное расширение schema v1: сохранён корневой `datasetKind: production-certified`, а у Easy/Medium
добавлено отдельное `verification` со статусом **VERIFIED**, version 1 и методом
**DETERMINISTIC_THRESHOLD_REPLAY**. Поле `certification` у них отсутствует.

Fresh verification проверяет ASCII-формат, корректное solution, givens/clues, ровно одно решение,
stable content ID, наличие незаполненных клеток, human solve в потолке категории, Deep classification,
minimum successful threshold, отсутствие guessing/backtracking, совпадение двух детерминированных путей
с solution и независимый `certification.proofs.validate_path`. В source JSON сохраняются threshold attempts
и полный LogicStep path. Mixed validator пересчитывает известные metadata/evidence и stats, отклоняет
неверную сложность, неподтверждённые статусы, дубликаты и ложные Extreme claims.

False-Easy/Medium protection использует уже существующий ascending threshold solver и Deep, а не только
greedy Quick path. Найденный capped logical solve гарантирует наличие полного пути без более сложных техник.
Никакого утверждения о минимальности среди всех альтернативных человеческих путей не делается:
это **lowest successful tested threshold в bounded deterministic модели**.

Extreme minimax здесь не нужен: standard admission заявляет уникальное решение, корректный логический путь
и классификацию существующего engine, а не Extreme negative alternative-path proof.
При mixed validation Extreme subset передаётся прежнему валидатору. Повторная проверка существующих Extreme
во время merge/validator следует сохранённому контракту; их записи не пересоздаются и не изменяются.

## Генерация

Новый генератор не создавался: `production-batch --difficulty Easy|Medium` использует `PuzzleGenerator`,
полное решение, удаление clues с uniqueness, Quick/Deep rating/filter, затем standard verification.
Evolutionary search не используется. Все кандидаты сначала сохраняются в research.

Точные команды подготовленной партии:

```powershell
python -m generator production-batch --difficulty Easy --seeds 10101,10102,10103 --per-seed-count 6 --target-new 9 --min-clues 20 --max-clues 45 --no-minimal --max-attempts 200 --generation-seconds 180 --runtime-budget 540 --run-dir data/research/phase10/easy
python -m generator production-batch --difficulty Medium --seeds 10201,10202,10203 --per-seed-count 6 --target-new 9 --min-clues 20 --max-clues 45 --no-minimal --max-attempts 250 --generation-seconds 240 --runtime-budget 720 --run-dir data/research/phase10/medium
```

Повторный запуск должен использовать новые `--run-dir`: существующие отчёты не перезаписываются.
Для обычного использования см. [GENERATION_GUIDE §20](GENERATION_GUIDE.md#20-easy-и-medium-phase-10).

| Категория | Seeds: attempts / accepted | Attempts | Verified pool | Selected | Runtime | Pool yield | Selected / attempts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Easy | 10101: 6/6; 10102: 8/6; 10103: 6/6 | 20 | 18 | 9 | 14.690 s | 90.00% | 45.00% |
| Medium | 10201: 52/6; 10202: 104/6; 10203: 214/6 | 370 | 18 | 9 | 146.313 s | 4.86% | 2.43% |

Ни один seed не достиг timeout. Из 18 verified candidates каждой категории выбраны 9, остальные остаются
в `verifiedUnselected`. Отбор предпочитает разные required ratings, clue counts и technique profiles,
после чего применяет прежний DiversityIndex относительно production и уже выбранных задач.
Верификация всех выбранных записей повторена во время dry-run и rehearsal merge.

Локальные source reports (не включены в commit): `data/research/phase10/easy/batch_report.json`,
`data/research/phase10/medium/batch_report.json`. Таблица ниже сохраняет выбранные IDs, seeds и параметры
воспроизведения; production JSON содержит полный verification evidence выбранных записей.
Они созданы до добавления поля `complete` в формат; каждый содержит ровно `targetNew=9` selected records.
Generation runtime — время реально завершённых batch reports. Предложенная в ходе работы оптимизация
генератора threshold-prefilter не внедрялась: исходный существующий pipeline успел завершить оба запуска.

## Выбранные 18 задач

Все ниже — **VERIFIED**, с полным source evidence. Rating округлён до 6 знаков только в таблице.
Seed относится к generator run; attemptSeed и attempt сохранены в research records.

| ID | Difficulty | Clues | Rating | Hardest Technique | Solution Steps | Seed | Verification |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| `puzzle-013d14af3a0bd6b8744e` | Easy | 25 | 1.576143 | Hidden Single | 56 | 10102 | VERIFIED |
| `puzzle-b4a264beb7d058271b54` | Easy | 45 | 1.309104 | Naked Single | 36 | 10101 | VERIFIED |
| `puzzle-8135b404d3b503332e9c` | Easy | 24 | 1.589508 | Hidden Single | 57 | 10101 | VERIFIED |
| `puzzle-2f18d1cda53e2dc2d09d` | Easy | 31 | 1.563469 | Hidden Single | 50 | 10103 | VERIFIED |
| `puzzle-5c3d2f40b8f501ed33a4` | Easy | 34 | 1.347352 | Naked Single | 47 | 10103 | VERIFIED |
| `puzzle-a09a352dcc84dcdb8891` | Easy | 28 | 1.575303 | Hidden Single | 53 | 10102 | VERIFIED |
| `puzzle-379996a393d2487a825e` | Easy | 39 | 1.330505 | Naked Single | 42 | 10103 | VERIFIED |
| `puzzle-169e3cf1fd788f925816` | Easy | 36 | 1.545221 | Hidden Single | 45 | 10102 | VERIFIED |
| `puzzle-4d25537c3c9ee28b73d4` | Easy | 43 | 1.317805 | Naked Single | 38 | 10101 | VERIFIED |
| `puzzle-0747fb4d247f7c3c1942` | Medium | 25 | 2.392257 | Locked Candidates | 57 | 10201 | VERIFIED |
| `puzzle-ac4f3069cca33fecc1bc` | Medium | 26 | 3.436182 | Naked Pair | 62 | 10202 | VERIFIED |
| `puzzle-7eb7bcdadbbd09c7d6a4` | Medium | 25 | 3.639161 | Hidden Pair | 63 | 10202 | VERIFIED |
| `puzzle-492043b68948c157a848` | Medium | 24 | 2.408075 | Locked Candidates | 58 | 10203 | VERIFIED |
| `puzzle-58f395e2398d149f65ec` | Medium | 23 | 2.414931 | Locked Candidates | 62 | 10202 | VERIFIED |
| `puzzle-ad6965ee0571feafeff2` | Medium | 27 | 2.405022 | Locked Candidates | 57 | 10202 | VERIFIED |
| `puzzle-62555358b0ace5eefe6f` | Medium | 25 | 3.464833 | Naked Pair | 69 | 10201 | VERIFIED |
| `puzzle-ae6206c866d41535f753` | Medium | 25 | 3.422931 | Naked Pair | 58 | 10203 | VERIFIED |
| `puzzle-dacdd2456a0034918d24` | Medium | 25 | 2.421020 | Locked Candidates | 60 | 10203 | VERIFIED |

## Diversity и реальные ranges

В mixed rehearsal: **28 различных IDs, puzzle strings, solution strings и clue masks**; точных и near-duplicates
относительно существующих Extreme и между новыми задачами нет. Минимальная clue-mask distance по всему
набору **24**, внутри Easy **30**, внутри Medium **24**. Проверяется также symmetry fingerprint.

| Категория | Clues | Aggregate rating | Required ratings | Solution steps | Различные count profiles |
| --- | --- | --- | --- | --- | ---: |
| Easy | 24–45 | 1.309104–1.589508 | 1, 1.2 | 36–57 | 9 |
| Medium | 23–27 | 2.392257–3.639161 | 2, 3, 3.2 | 57–69 | 9 |

Technique cosine similarity может быть высокой: Easy max 0.998618, Medium max 0.995256.
У Medium есть **3 информационных предупреждения** о сходных профилях при одинаковом clue count;
это ожидаемо для низких категорий с множеством singles, не дубликаты полей. Эти warnings не скрыты,
сохранены в batch report. У Easy таких warnings нет. Clues не использовались для классификации.

## Проверки до/после

| Проверка | Baseline | После изменений, до production merge |
| --- | --- | --- |
| Python unittest suite | 448 OK, 187.823 s | **463 OK**, 200.044 s |
| Frontend unit | 43/43 | **48/48**, также на реальной rehearsal DB |
| Browser check groups | 28/28 | **30/30**, Chromium 153 + WebKit 26.6 |
| Existing responsive matrix | 56/56 | **56/56** |
| Mixed New Game / Details / storage / replay | отсутствовало | оба engine, **390×844, 844×390, 810×1080, 1080×810** |
| Production validator | 10 Extreme OK, 13.0 s | **28-record rehearsal OK**, 23.1 s |
| Pages build | прежняя база | **28 playable records**, derived JSON **28,481 bytes** |
| git diff --check | — | pass |

Baseline выполнялся на immutable snapshot; первый пробный Python-запуск встретил отсутствующую в snapshot
`data/puzzles.json`. После восстановления fixture полный baseline повторён и прошёл 448/448.
Это проблема подготовки тестового snapshot, не дефект исходного проекта.

Новые Python regressions включают реальные Easy/Medium classification/admission, Medium-as-Easy,
Easy-as-Medium, Hard-as-Medium, bad status/flags/rating/proof, full-grid/nonunique rejection, отсутствие
Extreme-certification вызова для standard, mixed database, duplicate/stats, fresh merge, dry-run,
backup/atomic failure preservation и seeded research-only batch. Frontend tests проверяют строгий admission,
future fields, выбранную категорию включая replay и изоляцию values/notes/history/mistakes/hints по ID.

Browser suite выполнен на **отдельном snapshot с реальной mixed DB**, поэтому и `dist` собирался с 28 задачами,
а основной production-файл не менялся. Проверены Easy → another Easy, Medium → another Medium,
Extreme → existing certified Extreme, корректные Details, отсутствие console/page errors, storage после
reload и отмена replay. Скриншоты телефона portrait/landscape дополнительно просмотрены.

Логи и summaries: `reports/phase10/` (baseline, python-tests, frontend-mixed-tests, browser/browser-results,
mixed-validation, content-qc, merge-dry-run, rehearsal-merge). Скриншоты, backup и rehearsal DB — локальные
артефакты, исключённые из git; полные логи и research dumps также не входят в релизный commit.
Репетиционный slim build имел DB content hash `6d878403d15184df`.

### Остановка на post-merge regression

Первый полный Python-запуск на фактической mixed production базе завершился **463 tests, 1 error,
201.302 s**. Релиз был остановлен до commit/push. Причина — устаревшее предположение теста
`RealCertificationMergeTests.test_live_production_keeps_original_record_and_fingerprint`
в `generator/tests/test_production_phase9.py`: цикл обращался к `record['certification']` для каждой записи,
включая Easy/Medium, и получал `KeyError: 'certification'`.

После команды пользователя продолжить тест обновлён по явным категориям: Easy/Medium требуют fresh
`verify_standard`, точного совпадения известных metadata и отсутствия certification; Extreme/Ultra
сохраняют прежние status/default-config assertions. Неизвестная категория отклоняется. Проверки frozen
baseline block и fingerprints не изменены. Дополнительно добавлен negative mixed regression:
отсутствие `verification` отдельно у Easy и Medium либо `certification` у Extreme приводит к отказу.
Production records и certification engine при исправлении теста не менялись. Финальный полный повтор
после исправления завершился успешно: **463 tests, OK, 220.396 s**.

### Финальные проверки фактической production базы

Все проверки ниже выполнены после исправления post-merge regression, на production **28 = 9 Easy +
9 Medium + 10 Extreme**; ошибок нет.

| Проверка | Финальный результат |
| --- | --- |
| Python unittest suite | **463/463 OK**, 220.396 s |
| Frontend unit | **48/48 OK** |
| Browser check groups | **30/30 OK**, Chromium 153 + WebKit 26.6 |
| Existing responsive matrix | **56/56 OK** |
| Mixed categories / New Game / Details / storage / replay | оба engine, **390×844, 844×390, 810×1080, 1080×810**, PASS |
| Production validator | **28 OK**, 24.3 s |
| Pages build | **28 playable records**, derived JSON **28,481 bytes** |

Локальные финальные логи: `reports/phase10/final-python-tests.log`, `final-frontend-tests.log`,
`final-validation.log`, `final-browser.log`; browser summary —
`reports/phase10/final-browser/browser-results.json`. Production SHA-256 остался
`d5ce2f329526d117a5bf1f7b20f62fc07241e34d1ee37da13515d5501b576046`.
Актуальный локальный build: database `?v=3fa96923daea0a39`, application `?v=7282131a32219dcc`.
Изменение database hash относительно rehearsal связано с новым `generatedAt` при реальном merge.
Это локальные build hashes; совпадение опубликованной базы подтверждено public smoke ниже.

## Frontend и документация

- Отдельный strict standard admission, прежний Extreme gate сохранён.
- New Game показывает только имеющиеся категории, сохраняет текущую выбранной и не повторяет текущую
  задачу, если есть другая в этой категории. Полностью сыгранные категории доступны через подтверждение replay.
- Easy/Medium badge показывает реальную сложность, Details — verification, clues, rating, hardest technique,
  solution steps и technique summary. Extreme claims показываются только у Extreme.
- Формат localStorage и layout/CSS не изменены; прогресс сохраняется по puzzle ID.
- Pages build удаляет standard `verification.evidence`, сохраняя summary для frontend.
- README, web README, DATA_FORMAT и GENERATION_GUIDE обновлены. Исходные пользовательские добавления
  README и ранее незакоммиченный GENERATION_GUIDE сохранены и дополнены.

## Review, production merge и публикация

Независимый reviewer проверил partial backend/frontend и обнаружил расхождение для fully filled grid;
исправлено отказом в production admission и покрыто тестом. Затем все субагенты остановились из-за
runtime usage limit. Доработка, проверки репетиционной базы и документация выполнены основным агентом
по предусмотренному workspace fallback. После возобновления отдельный reviewer повторно проверил
окончательный source diff и фактическую production базу: **PASS, существенных дефектов не найдено**.
Review включает verification, mixed validator, batch/merge, frontend admission/selection и тесты;
46 файлов в certification/rating/solver/sudoku не изменены. Финальные запусковые проверки выполнены
отдельным Launch agent; результаты приведены выше.

Dry-run: `reports/phase10/merge-dry-run.json` — **18 new, 0 skipped, total 28, written false**.
Реальная репетиция на `data/research/phase10/rehearsal.json` — **18 new, 0 skipped**, atomic write, backup
и повторная проверка прошли; существующие Extreme records полностью неизменны.

После явного подтверждения пользователя выполнены production merge и повторная валидация:

```powershell
python -m generator production-merge --from-run data/research/phase10/easy --from-run data/research/phase10/medium --target-total 28 --report reports/phase10/production-merge.json
python scripts/validate_production_database.py
```

Merge завершён **2026-10-03 18:11:13 Europe/Moscow**: `reports/phase10/production-merge.json` —
**18 new, 0 skipped, total 28, written true, existingFormatCanonical true**.
Backup: `data/research/phase9/backups/puzzles-20261003T151048Z-859e581c3f7c.json` (локальный gitignored путь
существующего merge-инструмента). Повторный production validator: **28 OK, 23.1 s**.
`reports/phase10/post-merge-content-qc.json` подтверждает exact selected IDs, равенство rehearsal records,
28 unique IDs/puzzles/solutions и неизменность всех прежних Extreme blocks.

### GitHub Pages deployment

Implementation commit [`aa0c7eec2f1abcebb6e2dd9b19ec01573eda3efc`](https://github.com/shell322dll/extreme-sudoku/commit/aa0c7eec2f1abcebb6e2dd9b19ec01573eda3efc)
(`Phase 10: add verified Easy and Medium Sudoku`) успешно отправлен в существующий `origin/main`.
[Workflow «Deploy to GitHub Pages», run 37176301757](https://github.com/shell322dll/extreme-sudoku/actions/runs/37176301757)
для этого commit завершился **success**: **2026-10-04 07:11:57–07:12:58 Europe/Moscow**, 61 s.
Локальная копия ответа GitHub: `reports/phase10/pages-release-run.json`.

### Public smoke

Публичная проверка выполнена **2026-10-04 07:13:44–07:14:02 Europe/Moscow**.
[GitHub Pages URL](https://shell322dll.github.io/extreme-sudoku/) перенаправил на
[http://extreme.onedesire.ru/](http://extreme.onedesire.ru/). Проверен фактически загруженный сайт:
**4/4 PASS** — Chromium 153 и WebKit 26.6, каждый при **390×844** и **1440×900**.

- Публичный JSON целиком, побайтно совпадает с локальным `dist`: **28 задач = 9 Easy + 9 Medium +
  10 Extreme**, все 28 IDs совпадают.
- Database URL содержит `?v=3fa96923daea0a39`; SHA-256 опубликованного JSON:
  `3fa96923daea0a397c74685a1a207637fe25f70410c1e80bb7f532b4c1a6db65`.
- Easy, Medium и Extreme доступны. Для каждой категории New Game выбирает другую задачу той же
  сложности; повторное открытие chooser сохраняет выбранной текущую категорию.
- Details показывают стандартную verification для Easy/Medium и certification для Extreme без ложных claims.
- Прогресс разных задач сохраняется отдельно после переключений и reload.
- Console errors, page errors, failed requests и HTTP errors: **0** во всех четырёх запусках.

Локальная сводка: `reports/phase10/public-smoke/summary.json`; скриншоты лежат рядом и исключены из git.
Эта финализация отчёта публикуется отдельным docs-only commit; приложение и production data при ней не меняются.

## Ограничения

Bounded Deep не является глобальным minimax proof. Generator по-прежнему строит solution grids из Latin
pattern с перестановками, поэтому разные строки решений могут быть математически изоморфными.
Выбранная Medium партия не содержит triples: в registry они допустимы, но выбранные реальные уровни —
2/3/3.2. Standard batch не реализует Extreme resume/reuse/bands options. Timeout существующего pipeline
проверяется между solver calls и может превышаться внутри дорогого вызова. Browser WebKit emulation
не заменяет физический iOS Safari. Public smoke проверил фактический HTTP endpoint custom domain;
доступность HTTPS custom domain в эту проверку не входила.
