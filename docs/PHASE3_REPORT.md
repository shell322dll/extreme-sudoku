# Phase 3 — Advanced Human Solver

Реализованы X-Chain, XY-Chain, AIC, continuous Nice Loop, Grouped AIC,
ALS-XZ, ALS-XY-Wing, ALS Chain, Forcing Chain и Nishio. Изменения ограничены
Python Human Solver, тестами и документацией. UI, evolution, minimax и production
Extreme certification не добавлялись. Существующие Phase 1/2 техники сохранены.

## Доказательства и ограничения

`CandidateNode(cells, digit)` означает дизъюнкцию кандидатов одной цифры;
одна клетка образует обычный узел. `ChainLink` сохраняет начало, конец, вид связи
и причину. Strong означает `not A -> B`; weak означает `A -> not B`.
Одна пара может иметь обе связи, но ни одна семантика не выводится из другой.
Внутриклеточная strong допустима только при двух кандидатах; strong в unit —
при двух оставшихся позициях цифры. Weak требует конфликтующих кандидатов.

X-Chain, XY-Chain, AIC и Grouped AIC используют общий ограниченный BFS графа
инференций. X-Chain ограничен одной цифрой; XY-Chain — bivalue cells и одинаковой
цифрой концов. AIC допускает клеточные и unit-связи, открытые цепочки, strong/weak
discontinuity. Continuous Nice Loop выводит исключения через weak-связи замкнутой
чередующейся цепи. Это поиск логических доказательств, без перебора Sudoku assignments.
Повторение узла запрещено, кроме явного замыкания. Grouped nodes лежат в пересечении
box/line: strong partition покрывает все позиции цифры в unit, weak требует
конфликта каждой пары участников групп.

ALS содержит N клеток общего unit и ровно N+1 цифр. Неизменяемое представление
сохраняет клетки и их исходные маски, canonicalization убирает дубликаты.
RCC требует видимости всех соответствующих occurrences двух непересекающихся ALS.
ALS-XZ, ALS-XY-Wing и ALS Chain используют общий ALS graph и один endpoint theorem:
соседние RCC различны, конечная цифра отличается от первого/последнего RCC,
удаляемый кандидат видит все её occurrences обоих концов. Пересекающиеся ALS
и дополнительные double-linked ALS выводы пока не поддерживаются.

Forcing Chain сравнивает ограниченную propagation из `A` и `not A` и сохраняет
общий вывод. Nishio сохраняет опровергнутое предположение и явное противоречие.
Propagation использует exactly-one clauses клетки и позиции цифры в unit:
истинный кандидат исключает остальных, единственный оставшийся становится истинным.
Каждая инференция содержит родителей, правило и глубину; сертификат обрезается до
предков конкретного вывода. Вложенных предположений и recursive Sudoku solving нет.
Исчерпание лимита означает unknown, а не contradiction.

Cell Forcing, Region Forcing и Dynamic Forcing отложены: обязательный механизм
двух альтернатив уже реализован; расширение групп альтернатив и динамического
добавления более сложных правил требует отдельного доказательства корректности.
Это optional техники пользовательского задания, а не пропущенные обязательные пункты.

В `AdvancedConfig` defaults: X 15, XY/AIC/Grouped 19 связей; 100000 examined edges
на detector call; ALS size 4, chain до 5 ALS, 30000 pair checks и отдельно до
30000 chain expansions; forcing depth 12, 2000 inferences на предположение,
160 стартовых кандидатов. BFS сохраняет короткий представительный путь на состояние
графа, детерминированно перечисляет выводы и дедуплицирует одинаковые эффекты.
Он не перечисляет все возможные доказательства; bounded empty result не является
сертификатом отсутствия хода. `all_available_steps` и `minimum_available_rating`
подготовлены для будущего bottleneck анализа в пределах этого репертуара.

`LogicStep` расширен совместимыми optional `chain`, `grouped_nodes`, `als`,
`assumptions`, `contradiction`; сохранены старые поля. Результат содержит hardest
technique/rating, total score, advanced/chain/ALS/forcing counts и longest chain.
Длина candidate chain — число связей, ALS — число RCC, forcing — максимальная
глубина зависимости сертификата. Это разные величины, не универсальная мера сложности.

## Проверки и fixtures

До Phase 3: **100 тестов, 3.306 s, OK**. Промежуточные полные прогоны:
114 / 4.745 s; 130 / 7.970 s до registry; 130 / 9.365 s после registry.
Интеграционный блок: 7 / 22.040 s. Предфинальный checkpoint: 137 / 31.595 s, OK.
**Финальный полный regression: 149 тестов за 36.816 s, OK** — после всех
исправлений и дополнительных тестов независимого ревью. Все прежние 100 тестов
продолжают проходить. Команда: `python -m unittest discover -s generator/tests -v`.

Тесты проверяют positive/negative patterns, strong/weak семантику, неправильные
endpoints/visibility/alternation, повторения узлов, отсутствие полезного вывода,
immutability, determinism, deduplication и safety limits. Проверки зависимости
сканируют AST production-модулей, ставят runtime ловушки на Exact API и запускают
Human Solver в отдельном процессе, где импорт Exact Solver запрещён. Production
техники не импортируют exact solver и не имеют доступа к известному solution.
Exact Solver используется только тестами для независимой валидации fixtures.

В корпусе 7 сценариев для 4 разных Sudoku. Все четыре имеют уникальное решение,
Basic/Intermediate STUCK и Advanced SOLVED. Источник — существующий Phase 1
`minimize_puzzle(generate_solution(seed=n), seed=n)`; это фиксированные test recipes,
не evolutionary search. `build_phase3_fixtures` воспроизводит все 7 записей, включая
последнюю смешанную задачу, и обновляет измеренные метаданные.

| Seed | Puzzle | Проверяемые техники |
|---|---|---|
| 4 | `009000830001340020040050000030900006024100000000007090080000050002700049000000600` | AIC, ALS-XZ, Forcing Chain, Nishio |
| 29 | `008050000126300000000100007070000120504000008000008009000094010001000045050060800` | XY-Chain |
| 193 | `000800000008041030010020807020000049004203000500400000003007004001630008000000002` | X-Chain |
| 48 | `090000005001040060060200700700080000002070040000300900000800500015004082000090006` | default: Grouped AIC, ALS-XZ, ALS-XY-Wing, ALS Chain |

Для первых шести сценариев используется Phase 2 + указанная техника. Их наличие
не означает обязательность этой техники среди всех альтернативных путей. Например,
default решает seed 4 через X-Chain/AIC; forcing/Nishio проверяются отдельными
репертуарами. После обрезки forcing proof target seed 4 имеет dependency depth 9,
Nishio — 11. На default solution paths максимальная candidate chain — 17 связей.
При перечислении доступных шагов на Phase2-stuck состояниях профилирование наблюдает
19 candidate links, 4 ALS RCC и forcing depth 12.
Отдельный synthetic regression также воспроизводит XY-Chain из 19 связей.

CLI `python -m generator --seed 42` прошёл: 24 clues, Unique=True, Minimal=True.
Команда по-прежнему выводит Phase 1 seed puzzle без присвоения Extreme.

## Производительность

Воспроизводимый скрипт: `python -m generator.tests.profile_phase3`.
Полные параметры, окружение, graph sizes, число выводов и времена хранятся в
[PHASE3_PROFILE.json](PHASE3_PROFILE.json). Это одиночные wall-clock samples,
без хрупких timing assertions; измерения следует выполнять без соседней CPU нагрузки.

Четыре default solve заняли суммарно **2.246 s**: seed 4 — 0.171 s,
29 — 0.101 s, 193 — 0.104 s, 48 — 1.870 s.
На начальных Phase2-stuck состояниях суммарное время по технике:
ALS Chain 0.452 s, Nishio 0.364 s, Forcing Chain 0.352 s, Grouped AIC 0.272 s.
Основное измеренное узкое место — ALS Chain; повторная ALS enumeration/graph build
между тремя ALS detectors и обход RCC paths дают заметную цену. Forcing повторяет
bounded propagation для стартов; grouped graph увеличивает число пар связей.
Это зафиксированный baseline; оптимизация логики в этой фазе не выполнялась.

Максимум на этих состояниях: 299 inference nodes, 155 ALS, 11935 ALS pair checks,
96 emitted steps одним detector. ALS graph cutoff здесь не достигнут.
Экспоненциальное перечисление ALS paths ограничено явным бюджетом; большие случаи
могут исчерпать его и пропустить доступный ход. Корректность выводов от этого не меняется.

## Независимое ревью

Отдельный reviewer проверил граф, ALS theorem, endpoint semantics, loop closure,
forcing limits/proof replay, dependency boundary и determinism. На 18 валидных
кандидатных состояниях проверены **2773 вывода всех десяти техник** относительно
независимо сохранённого полного решения: ложных выводов не найдено (4.947 s).
Состояния строились с `random.Random(9824)`, solution seeds 0..17, probability
clue 0.25 и кандидата 0.7 с обязательным сохранением правильного кандидата;
audit limits: graph 10000, ALS 3000, forcing starts 40, прочее defaults.

Отдельно reviewer воспроизвёл 99 обрезанных forcing proofs seed 4, включая правила,
индексы родителей, глубину, contradiction roots и фактические conclusions.
Производственных блокирующих дефектов не обнаружено. Замечания ревью закрыты:
добавлены отдельные discontinuity regression tests, уточнено объяснение continuous
Nice Loop, сохранён независимый soundness audit как regression и добавлены проверки
обрезанных forcing proofs. Все рейтинги advanced classes читаются из общей таблицы
`TECHNIQUE_WEIGHTS`. Независимое логическое ревью завершено без открытых замечаний.
Reviewer отдельно проверил все десять импортов весов (22..55), отсутствие цикла
импортов и registry test (1 / 0.257 s, OK). Последующая полная проверка — 149 / 36.816 s.
Наиболее рискованные области — grouped all-members visibility, ALS RCC endpoints,
замыкание AIC и корректное различение cutoff/contradiction; они покрыты отдельными
проверками, но конечный корпус не доказывает полноту техники на всех Sudoku.

Phase 4 не начата. Минимальная обязательная сложность, genuine bottlenecks и
производственная сертификация Extreme остаются будущей работой.
