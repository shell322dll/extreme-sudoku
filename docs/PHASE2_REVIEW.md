# Независимое ревью Phase 2

Дата: 2026-09-27. Reviewer не участвовал в реализации production-кода.
Проверены текущие файлы проекта, AGENTS.md, PRODUCT_SPEC.md, GENERATOR_SPEC.md
и пользовательское задание Phase 2. В рабочей папке отсутствует `.git`, поэтому
сравнение с историческим коммитом недоступно.

Блокирующих дефектов не обнаружено. Все девять пунктов Definition of Done
выполнены в проверенном состоянии. Единственное промежуточное замечание —
дублирование числовых весов — устранено: классы используют `TECHNIQUE_WEIGHTS`.

| Проверка | Результат |
| --- | --- |
| Обязательные техники | Naked/Hidden Quad, X-Wing, Swordfish, Skyscraper, 2-String Kite, Turbot Fish, Empty Rectangle, XY/XYZ/W-Wing реализованы; также Jellyfish |
| Unit tests | Для каждой техники есть positive, точные effects, near-miss negative, применение без локального противоречия и проверка неизменности state |
| Regression | `python -m unittest discover -s generator/tests -v`: 100 tests, OK, 3.365 s; сохранены 46 исторических тестов |
| Интеграция | Три уникальных clue puzzles: Phase 1 STUCK, Phase 2 SOLVED; X-Wing seed 21, Swordfish seed 227, XY-Wing seed 3 присутствуют в путях |
| Human logic | В детекторах и HumanSolver нет exact solver, solution oracle, guessing или DFS/backtracking |
| Воспроизводимость | Стабильные сортировки и выбор шага; повторное решение, полный replay и минимальный доступный rating проверены тестами |
| Reporting | Проверены technique_counts, hardest_technique, max_rating, total_score, intermediate_steps; последний не зависит от custom weights |
| Scope | Phase 3, общий поиск цепочек, эволюция, minimax и Extreme certification не добавлены |

Исторический тест, ожидающий STUCK, теперь явно использует `phase1_techniques()`:
его прежние проверки сохранены. `LogicStep` не изменён, новое поле результата
добавлено в конец dataclass. Возврат к простейшей технике после каждого шага
проверяется существующим plugin-тестом и replay новых реальных puzzles.

Проверенные математические условия:

- Quads используют ограничение четырёх цифр четырьмя клетками одной unit.
- Обычные fish используют N независимых base houses и ровно N cover houses.
- Skyscraper/Kite/Turbot требуют два conjugate pairs, соединение внутренних
  endpoints и видимость обоих внешних endpoints у исключаемой клетки.
- Empty Rectangle проверяет обе непустые arms, отсутствие кандидатов вне них,
  внешний conjugate pair и правильную клетку пересечения для elimination.
  Кандидат на пересечении arms допустим; его исключают те же две линии.
- XY-Wing требует разные связи с pivot; XYZ-Wing дополнительно требует
  видимость pivot у target; W-Wing требует одинаковые bivalue wings и настоящий
  conjugate bridge, исключая overlap bridge/wing.

Особенно чувствительные границы покрыты negative fixtures: лишняя cover line,
третий кандидат в conjugate pair, disconnected endpoints, кандидат вне ER arms,
одинаковые связи XY, отсутствие видимости pivot XYZ и разорванный W bridge.
Перечисление ограничено заявленными паттернами: обычные fish без fins,
Turbot из двух disjoint conjugate pairs, стандартные wings. Эквивалентные
доказательства с одинаковым effect объединяются; разные полезные effects
сохраняются. Полнота произвольных логических выводов не заявляется.

Дополнительные независимые проверки выполнены вне production-кода:

1. Seed `93725`, 300 satisfiable candidate states, все 12 новых техник:
   8995 шагов сохранили известное допустимое решение; входной state не менялся.
2. Seed `6013`, 200 candidate states для одной цифры: вычислены все совместимые
   положения цифры среди 46656 row/column/box templates. Все 285 найденных шагов
   fish и single-digit patterns исключали только позиции, невозможные в любом
   совместимом template.

Первая проверка обнаруживает потерю одного известного решения, но сама по себе
не доказывает сохранение всех решений. Вторая исчерпывает положения одной цифры
для выбранных states, а не все candidate states Sudoku. Обе дополняют чтение
логических доказательств и unit tests, а не заменяют их. Проверка solution oracle
внешняя; он не используется детекторами или для оценки сложности.

Fixtures доказывают улучшение реализованного solver и наличие техники в
детерминированном пути. Не доказано, что именно эта техника неизбежна во всех
альтернативных путях; greedy metrics не являются mandatory/minimax difficulty.

## Воспроизведение дополнительных проверок

Следующий Python-код запускается из корня проекта. Он предназначен только для
review validation; переносить template enumeration или solution oracle в human
solver нельзя.

```python
import random
from collections import Counter
from itertools import permutations
from generator.sudoku.candidates import SudokuState, ALL, digit_mask
from generator.solver.techniques.subsets import NakedQuad, HiddenQuad
from generator.solver.techniques.fish import XWing, Swordfish, Jellyfish
from generator.solver.techniques.wings import XYWing, XYZWing, WWing
from generator.solver.techniques.single_digit_patterns import (
    Skyscraper, TwoStringKite, TurbotFish, EmptyRectangle,
)

classes = (NakedQuad, HiddenQuad, XWing, Swordfish, Jellyfish, XYWing,
           XYZWing, WWing, Skyscraper, TwoStringKite, TurbotFish, EmptyRectangle)
techniques = [cls() for cls in classes]
solution = [(r * 3 + r // 3 + c) % 9 + 1 for r in range(9) for c in range(9)]
rng = random.Random(93725)
counts = Counter()
for trial in range(300):
    density = rng.uniform(0.12, 0.65)
    masks = [digit_mask(value) | sum(digit_mask(d) for d in range(1, 10)
             if d != value and rng.random() < density) for value in solution]
    state = SudokuState([0] * 81, masks)
    before = (state.grid.copy(), state.candidates.copy())
    for technique in techniques:
        steps = technique.find_steps(state)
        counts[technique.name] += len(steps)
        for step in steps:
            assert all(solution[c] != d for c, d in step.eliminations)
            assert all(solution[c] == d for c, d in step.placements)
        assert before == (state.grid, state.candidates)
assert sum(counts.values()) == 8995
print(dict(counts))

patterns = []
for cols in permutations(range(9)):
    if all(len({cols[r] // 3 for r in range(b, b + 3)}) == 3 for b in (0, 3, 6)):
        patterns.append(sum(1 << (9 * r + c) for r, c in enumerate(cols)))
assert len(patterns) == 46656
techniques = [cls() for cls in (XWing, Swordfish, Jellyfish, Skyscraper,
                               TwoStringKite, TurbotFish, EmptyRectangle)]
rng = random.Random(6013)
counts = Counter()
for case in range(200):
    support = rng.choice(patterns)
    density = rng.uniform(0.1, 0.6)
    for c in range(81):
        if rng.random() < density:
            support |= 1 << c
    state = SudokuState([0] * 81,
                        [ALL if support & (1 << c) else ALL ^ 1 for c in range(81)])
    possible = 0
    for pattern in patterns:
        if pattern & ~support == 0:
            possible |= pattern
    assert possible
    for technique in techniques:
        steps = technique.find_steps(state)
        counts[technique.name] += len(steps)
        for step in steps:
            for cell, digit in step.eliminations:
                assert digit == 1 and possible & (1 << cell) == 0
assert sum(counts.values()) == 285
print(dict(counts))
```
