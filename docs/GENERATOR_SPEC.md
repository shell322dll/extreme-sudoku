# Цель проекта

> Текущий контракт Phase 7: [CERTIFICATION_SPEC.md](CERTIFICATION_SPEC.md).
> Он уточняет final acceptance и supersedes иллюстративные пороги ниже:
> применяется существующая registry (AIC=30), 22+ clues допустимы;
> исчерпание search/detector budget никогда не доказывает отсутствие простого пути.

Реализовать на Python генератор классических Sudoku 9×9 экстремального уровня сложности.

Генератор должен искать задачи, обладающие одновременно следующими свойствами:

1. Размер поля — 9×9.
2. Единственное решение.
3. Желательно 17–20 исходных цифр.
4. Приоритет:
   - 17 clues — идеальный результат;
   - 18 clues — отличный;
   - 19–20 — допустимый;
   - 21–23 — допускаются только если сложность существенно выше.
5. Судоку не должно решаться только Singles / Pairs / Triples и другими простыми техниками.
6. Решение должно обязательно проходить через один или несколько продвинутых логических bottleneck-состояний.
7. Желательно наличие:
   - AIC;
   - X-Chain;
   - XY-Chain;
   - ALS-XZ;
   - ALS Chain;
   - forcing chain;
   - contradiction chain / Nishio;
   - сложных fish;
   - других продвинутых техник.
8. Полный backtracking разрешается использовать внутри генератора ТОЛЬКО:
   - для проверки существования решения;
   - для проверки единственности;
   - для построения полного solution grid.
9. Backtracking запрещено использовать при оценке человеческой сложности судоку.
10. Финальная задача должна иметь воспроизводимый логический solution path.

Главная идея:

> Генетический алгоритм оптимизирует не заполненную таблицу Sudoku, а набор исходных подсказок, причём fitness определяется прежде всего сложностью логического решения.

---

# Важное замечание о «переборе»

Технически любое Sudoku можно решить полным перебором.

Поэтому критерий:

"Sudoku невозможно решить перебором"

математически некорректен.

В проекте под этим следует понимать:

- uniqueness solver имеет право использовать DFS/backtracking;
- human solver не имеет права использовать DFS/backtracking;
- puzzle должен быть НЕрешаем ограниченным набором простых human-techniques;
- puzzle должен становиться решаемым после подключения продвинутых логических техник.

То есть нужно доказать примерно следующее:

```text
BasicSolver(puzzle)      -> STUCK
IntermediateSolver       -> STUCK
AdvancedLogicSolver      -> SOLVED
BacktrackingUsed         -> False
```

Это центральный критерий Extreme.

---

# Архитектура проекта

Разделить программу минимум на следующие компоненты:

```text
sudoku/
    grid.py
    candidates.py

solver/
    exact_solver.py
    human_solver.py
    techniques/
        singles.py
        subsets.py
        locked_candidates.py
        fish.py
        wings.py
        coloring.py
        chains.py
        als.py
        forcing.py

generator/
    solution_generator.py
    chromosome.py
    mutation.py
    crossover.py
    repair.py
    evolution.py

rating/
    difficulty.py
    fitness.py
    metrics.py

tests/
    ...
```

Не смешивать exact solver и human solver.

---

# 1. Представление Sudoku

Использовать:

```python
grid: list[int]  # 81 элементов
```

Значения:

```text
0 = пустая клетка
1..9 = заданная цифра
```

Индекс:

```python
index = row * 9 + col
```

Для производительности кандидатов желательно использовать bitmask.

Например:

```text
bit 0 -> digit 1
bit 1 -> digit 2
...
bit 8 -> digit 9
```

Полный набор:

```python
ALL = 0b111111111
```

Функции:

```python
row_of(cell)
col_of(cell)
box_of(cell)

peers[cell]
units[cell]
```

Все peers и units предварительно вычислить один раз.

---

# 2. Exact Solver

Создать отдельный максимально быстрый решатель.

Его задачи:

```python
solve_one(grid)
count_solutions(grid, limit=2)
has_unique_solution(grid)
```

Он МОЖЕТ использовать:

- constraint propagation;
- bitmasks;
- MRV;
- DFS;
- backtracking.

Для проверки уникальности всегда достаточно:

```python
count_solutions(grid, limit=2)
```

Если:

```text
0 -> INVALID
1 -> UNIQUE
>=2 -> MULTIPLE
```

После нахождения второго решения поиск немедленно прекращать.

Использовать MRV:

```text
выбирать незаполненную клетку
с минимальным количеством кандидатов
```

Желательно также:

- cached peers;
- incremental candidate updates;
- undo stack вместо полного deepcopy.

Этот solver должен быть очень быстрым, потому что эволюционный алгоритм вызовет его миллионы раз.

---

# 3. Полное решение

Сначала генерируется корректный complete solution:

```text
8 1 2 7 5 3 6 4 9
9 4 3 6 8 2 1 7 5
...
```

Можно использовать:

- randomized DFS;
- Latin pattern + permutations;
- случайные допустимые transformations.

После этого chromosome должен определять, какие клетки из данного solution остаются clues.

---

# 4. Chromosome

Не хранить сами значения.

Хранить 81-битную маску:

```text
1 = значение solution показывается пользователю
0 = клетка пустая
```

Пример:

```python
class Individual:
    clue_mask: int
    solution: tuple[int, ...]
```

Количество clues:

```python
clue_count = clue_mask.bit_count()
```

Получение puzzle:

```python
puzzle[i] = solution[i] if mask & (1 << i) else 0
```

Это гарантирует, что каждая mutation не создаёт противоречивых clues.

---

# 5. Почему нельзя просто удалить 64 цифры

Наивный алгоритм:

```text
создать complete grid
случайно удалить цифры до 17
```

почти всегда приведёт к:

```text
несколько решений
```

или к неинтересной задаче.

Поэтому удаление clues должно сопровождаться:

```python
has_unique_solution(candidate)
```

---

# 6. Получение начальной минимальной задачи

Сделать функцию:

```python
def minimize_puzzle(solution):
```

Начать:

```text
81 clues
```

Создать случайный порядок:

```python
positions = shuffled(range(81))
```

Последовательно пробовать удалить clue:

```python
for cell in positions:
    remove(cell)

    if not unique:
        restore(cell)
```

После одного прохода повторить с новым случайным порядком.

Остановиться, когда ни одну оставшуюся clue невозможно удалить без потери uniqueness.

Это даёт minimal puzzle.

ВАЖНО:

```text
minimal != minimum
```

Minimal означает:

> ни одну подсказку отдельно удалить нельзя.

Это НЕ означает 17 clues.

---

# 7. Human Solver

Это важнейшая часть проекта.

Он должен имитировать человеческое решение и никогда автоматически не применять DFS.

Интерфейс:

```python
result = human_solver.solve(puzzle)
```

Результат:

```python
@dataclass
class HumanSolveResult:
    solved: bool
    stuck: bool

    steps: list[LogicStep]

    hardest_technique: Technique
    max_rating: float
    total_score: float

    technique_counts: dict
    advanced_steps: int

    bottlenecks: list
```

Каждый LogicStep:

```python
@dataclass
class LogicStep:
    technique: Technique
    rating: float

    placements: list
    eliminations: list

    premises: list
    explanation: str

    search_complexity: float
```

---

# 8. Очень важное правило выбора шагов

Human solver должен ВСЕГДА сначала искать наиболее простую доступную технику.

Алгоритм:

```python
while not solved:

    for technique in techniques_sorted_by_difficulty:

        steps = technique.find_all(state)

        if steps:
            step = choose_step(steps)
            apply(step)
            restart from easiest technique
            break

    else:
        return STUCK
```

То есть сложную технику нельзя применять, пока существует простой логический ход.

Иначе генератор будет искусственно завышать рейтинг задачи.

---

# 9. Уровни техник

Предлагаемая иерархия.

## Tier 0 — trivial

```text
Full House
Naked Single
Hidden Single
```

## Tier 1 — basic

```text
Locked Candidates
Pointing
Claiming

Naked Pair
Hidden Pair

Naked Triple
Hidden Triple
```

## Tier 2 — intermediate

```text
Naked Quad
Hidden Quad

X-Wing
Skyscraper
2-String Kite
Turbot Fish
Empty Rectangle
```

## Tier 3 — advanced

```text
Swordfish
Jellyfish

Finned X-Wing
Finned Swordfish
Sashimi Fish

XY-Wing
XYZ-Wing
W-Wing

Simple Coloring
Multi Coloring
3D Medusa

Unique Rectangle
BUG+1
```

## Tier 4 — extreme

```text
X-Chain
XY-Chain

AIC
Nice Loop

Grouped AIC

ALS-XZ
ALS-XY-Wing
ALS Chain

Sue de Coq

Franken Fish
Mutant Fish

Kraken Fish

Forcing Chain
Nishio Chain
Cell Forcing Chain
Region Forcing Chain
Dynamic Forcing Chain
```

Конкретные числовые веса сделать конфигурируемыми.

---

# 10. Не считать puzzle Extreme только из-за одного случайного X-Wing

Очень важно.

Сложность должна зависеть не только от:

```text
hardest technique
```

но и от структуры solution path.

Например:

Puzzle A:

```text
50 singles
1 XY-Wing
20 singles
```

не должен иметь такой же fitness, как:

```text
AIC
5 singles
ALS-XZ
X-Chain
3 singles
Grouped AIC
Forcing Chain
```

Поэтому считать несколько метрик.

---

# 11. Difficulty metrics

Для каждой задачи вычислять:

```python
D_max
D_total
D_advanced
D_bottleneck
D_chain
D_search
D_dependency
```

### D_max

Сложность самого тяжёлого обязательного шага.

Например:

```text
Single        1
Pair          2
X-Wing        4
XY-Wing       5
AIC           8
ALS Chain     9
Forcing Chain 10
```

---

# 12. Weighted total difficulty

Например:

```python
D_total = sum(step.rating ** 2 for step in steps)
```

Возведение в квадрат нужно, чтобы несколько сложных шагов сильно повышали результат.

Можно использовать:

```python
D_total = Σ weight[technique]
```

Пример начальных весов:

```text
Naked Single            1
Hidden Single           1

Locked Candidate        2

Pair                    3
Triple                  5
Quad                    7

X-Wing                  8
Skyscraper              9
2-String Kite           9

Swordfish              12

XY-Wing                14
XYZ-Wing               16
W-Wing                 16

Jellyfish              18
Coloring               18

X-Chain                22
XY-Chain               25

AIC                    30
Grouped AIC            35

ALS-XZ                 36
ALS Chain              42

Franken Fish           40
Mutant Fish            45

Forcing Chain          50
Nishio                 55
Dynamic Forcing       65
```

Эти значения не считать абсолютной истиной — вынести в конфиг.

---

# 13. Advanced step count

```python
advanced_steps =
    count(step.rating >= ADVANCED_THRESHOLD)
```

Желательно Extreme puzzle требовать:

```text
advanced_steps >= 3
```

а Ultra Extreme:

```text
advanced_steps >= 5
```

---

# 14. Bottleneck

Нужно обнаруживать состояния, в которых:

```text
простая логика полностью исчерпана
```

и единственный прогресс возможен сложной техникой.

Например:

```python
basic_solver.solve_until_stuck(state)
```

После остановки определить:

```python
available_advanced_steps(state)
```

Если minimum available technique имеет rating 8:

```text
это настоящий difficulty bottleneck.
```

Считать:

```python
bottleneck_score += minimum_required_rating
```

---

# 15. Самое важное: обязательность сложной техники

Недостаточно обнаружить AIC.

Нужно определить:

> можно ли избежать AIC другим более простым логическим путём?

Если можно — AIC не должен считаться обязательным.

Для особенно перспективных кандидатов выполнить более дорогую проверку.

Пусть:

```text
R = rating проверяемого шага
```

Создать solver с техниками:

```text
rating < R
```

Если он не способен продолжить:

```text
STUCK
```

а после разрешения техники R puzzle продолжает решаться:

```text
R является настоящим bottleneck.
```

---

# 16. Альтернативные solution paths

Это принципиально важно.

Greedy human solver может случайно выбрать путь:

```text
AIC
```

хотя где-то существует:

```text
простая XY-Wing
```

Поэтому для кандидатов высокого качества выполнять:

```python
find_all_steps(state)
```

а не только первый шаг.

Определить:

```python
minimum_available_rating(state)
```

Difficulty bottleneck определяется минимальной сложностью любого возможного шага.

То есть:

```text
min(all possible valid steps)
```

а не первым найденным solver'ом.

---

# 17. Logical branching search

Для финальных кандидатов можно реализовать ещё более строгую оценку.

Исследовать граф различных логических solution paths.

Состояние:

```text
candidate grid
```

Переход:

```text
применение допустимого логического шага
```

Цель:

```text
найти логический путь до решения,
минимизирующий максимальную сложность шага.
```

Это minimax-задача.

Определить:

```text
difficulty(puzzle)
=
minimum over all logical solutions
    maximum technique rating in that solution
```

Это намного лучше обычного:

```text
difficulty =
hardest step chosen by one greedy solver
```

Именно эту метрику использовать для финальной сертификации лучших Sudoku.

Полный exhaustive поиск всех логических путей может быть дорогим, поэтому:

```text
обычные individuals -> greedy rating
top 1%              -> multi-path rating
top 0.1%            -> exhaustive/minimax rating
```

---

# 18. Chain complexity

Для цепочных техник учитывать длину.

Например:

```python
chain_score =
    base_weight +
    1.5 * chain_links +
    2.0 * grouped_nodes
```

Пример:

```text
AIC длиной 4
```

не должен оцениваться так же высоко, как:

```text
AIC длиной 18
```

Особенно ценны:

```text
long AIC
ALS chains
forcing chains
```

---

# 19. Pattern search difficulty

Два одинаковых AIC могут сильно отличаться по человеческой сложности.

Добавить приблизительную стоимость обнаружения:

```python
search_complexity =
    candidate_count *
    possible_start_nodes *
    branching_factor *
    chain_length_factor
```

Не обязательно идеально моделировать человека.

Главное:

```text
чем больше потенциальных похожих паттернов нужно проверить,
тем выше search difficulty.
```

---

# 20. False leads

Очень интересная метрика для Extreme.

В сложном Sudoku может существовать множество:

```text
почти X-Wing
почти AIC
ALS без elimination
цепочек без полезного вывода
```

Это усложняет поиск человеку.

Можно считать:

```python
false_pattern_count
```

и немного увеличивать fitness.

Но вес должен быть небольшим, чтобы генератор не оптимизировал бессмысленный шум.

---

# 21. Fitness function

Главная функция.

Предлагаемая схема:

```python
fitness =
      1000 * extreme_required
    + 150  * hardest_rating
    + 30   * advanced_steps
    + 10   * bottleneck_score
    + 5    * chain_complexity
    + 2    * search_complexity
    + 1    * total_logic_score
    + clue_bonus
    + minimality_bonus
    - penalties
```

Где:

```python
extreme_required = 1
```

только если:

```text
Basic solver       -> STUCK
Intermediate       -> STUCK
Advanced solver    -> SOLVED
Backtracking       -> 0
required Extreme technique exists
```

Иначе:

```python
extreme_required = 0
```

---

# 22. Clue bonus

Количество clues должно иметь значительно меньший вес, чем difficulty.

Например:

```python
CLUE_BONUS = {
    17: 600,
    18: 450,
    19: 300,
    20: 200,
    21: 100,
    22: 50,
    23: 0,
}
```

Но:

```text
17-clue Medium Sudoku
```

всегда должен проигрывать:

```text
20-clue Extreme Sudoku
```

если основной целью является сложность.

---

# 23. Hard constraints

Некоторые условия не включать в fitness, а сразу отбрасывать.

```python
if solutions != 1:
    fitness = -INF

if clues < 17:
    fitness = -INF

if clues > MAX_CLUES:
    penalty

if human_solver.invalid:
    fitness = -INF
```

---

# 24. Extreme constraint

Для режима:

```text
MODE_EXTREME
```

задача проходит только если:

```python
basic_solved == False
advanced_solved == True
max_required_rating >= EXTREME_THRESHOLD
advanced_steps >= 2
```

Лучше:

```python
true_bottlenecks >= 2
```

---

# 25. Ultra Extreme

Дополнительный режим:

```text
MODE_ULTRA_EXTREME
```

Условия:

```text
clues <= 21

hardest >= AIC/ALS level

true bottlenecks >= 3

advanced steps >= 5

chain technique required

max chain length >= 8

no backtracking in human solver

unique solution
```

Дополнительно желательно:

```text
один forcing chain
или
ALS Chain
или
Grouped AIC
или
Kraken / Mutant Fish
```

---

# 26. Population

Например:

```python
POPULATION = 500
```

Лучше 500–2000 при достаточной производительности.

Начальная популяция создаётся из нескольких разных complete grids.

Не использовать один solution grid для всей эволюции навсегда.

Например:

```text
20 complete solutions
×
25 clue masks
=
500 individuals
```

---

# 27. Инициализация population

Для каждого полного solution:

1. начать с ~28–35 clues;
2. постепенно удалять;
3. сохранять uniqueness;
4. получить minimal или near-minimal puzzle;
5. создать вокруг него несколько вариантов.

Почему не начинать сразу с 17:

```text
17-clue уникальные Sudoku очень редки.
```

---

# 28. Mutation operators

Не использовать только:

```text
remove random clue
```

Нужен набор операторов.

## Mutation A — REMOVE

```text
удалить 1 clue
```

После:

```text
check uniqueness
```

---

## Mutation B — ADD

Добавить ранее удалённую clue.

Это кажется движением назад, но крайне важно.

Иногда:

```text
19-clue puzzle
```

имеет плохой landscape.

Чтобы перейти в другой набор 19 clues, нужно:

```text
19 -> 20 -> 19
```

---

## Mutation C — SWAP

```text
remove clue A
add clue B
```

Количество clues сохраняется.

Это должен быть один из основных операторов.

---

## Mutation D — MULTI SWAP

```text
remove 2 clues
add 2 clues
```

или:

```text
3 ↔ 3
```

Позволяет выйти из local optimum.

---

## Mutation E — BOX mutation

Изменить clues внутри одного box.

---

## Mutation F — ROW/COLUMN mutation

Менять структуру подсказок локально.

---

## Mutation G — difficulty-guided mutation

Самая интересная.

Получить human solution path.

Определить область около:

```text
сложного bottleneck
```

Затем преимущественно мутировать clues, влияющие на кандидатов этой области.

Цель:

```text
усложнить существующий bottleneck
```

или создать новый.

---

# 29. Critical clue analysis

Для каждой clue можно вычислить:

```python
difficulty_delta
```

Пример:

```python
remove clue X
```

если uniqueness остаётся:

```text
rating before = 6.0
rating after  = 8.2
```

тогда clue X — сильный кандидат на удаление.

Аналогично:

```text
добавление clue Y
```

может неожиданно сделать другой участок сложнее из-за изменения solution path.

Поэтому mutations нужно оценивать экспериментально.

---

# 30. Crossover

Обычный генетический crossover здесь применять осторожно.

Родители:

```text
mask_A
mask_B
```

Можно создать:

```python
child = mask_A & mask_B
```

Но слишком вероятна потеря uniqueness.

Или:

```python
child = mask_A | mask_B
```

Но clues станет слишком много.

Лучший crossover:

```text
1. взять intersection
2. добавить случайные clues из symmetric difference
3. repair uniqueness
4. minimize
```

Псевдокод:

```python
common = A & B
optional = A ^ B

child = common

for clue in shuffled(optional):
    if random():
        child |= clue

child = repair_uniqueness(child)
child = minimize(child)
```

Использовать crossover относительно редко:

```text
10–20%
```

Основной движок поиска — mutations.

---

# 31. Uniqueness repair

Если после mutation:

```text
multiple solutions
```

не обязательно сразу выбрасывать child.

Можно repair.

Exact solver должен вернуть:

```text
solution1
solution2
```

Найти клетки, где решения различаются:

```python
diff = [
    i for i in range(81)
    if solution1[i] != solution2[i]
]
```

Добавить clue из исходного target solution в одной из этих клеток.

Повторить:

```text
count solutions
```

пока:

```text
solutions == 1
```

Это очень полезный оператор.

---

# 32. Почему repair работает

Если существуют два решения, новая clue должна устранять хотя бы одно альтернативное решение.

Поэтому добавлять случайную clue неэффективно.

Нужно добавлять clue именно в:

```text
difference set между альтернативными solutions.
```

---

# 33. Hitting-set идея

Для режима поиска 17 clues желательно дополнительно реализовать идею unavoidable sets / hitting sets.

Каждое альтернативное решение определяет набор клеток:

```text
где оно отличается от target solution.
```

Чтобы target solution был единственным, набор clues должен пересекать каждый такой set.

Получаем hitting-set problem.

Именно таким подходом намного разумнее искать очень малое количество clues, чем бесконечно случайно удалять значения.

Рекомендуемая архитектура:

```text
Evolutionary search
        +
uniqueness repair
        +
hitting-set information
```

---

# 34. Selection

Использовать tournament selection.

Например:

```python
TOURNAMENT_SIZE = 5
```

Выбрать случайно пять individuals и взять лучшего.

Избегать исключительно:

```text
top N reproduce
```

иначе population быстро потеряет diversity.

---

# 35. Elitism

Сохранять лучшие:

```text
5–10%
```

без mutation.

Например:

```python
ELITE = 25
```

при population 500.

---

# 36. Diversity

Две puzzle могут отличаться одной clue.

Нужно бороться с клонами.

Расстояние:

```python
distance(A, B) =
    (A.clue_mask ^ B.clue_mask).bit_count()
```

Если:

```text
distance < 3
```

можно считать их почти одинаковыми.

Добавить diversity bonus или удалять дубликаты.

---

# 37. Canonicalization

Sudoku, полученное:

```text
перестановкой digits
перестановкой rows внутри band
перестановкой columns внутри stack
перестановкой bands
перестановкой stacks
transpose
```

может быть математически эквивалентным.

Для большой базы желательно реализовать canonical hash либо хотя бы простой normalized fingerprint, чтобы не сохранять тысячи эквивалентных задач.

---

# 38. Generational loop

Псевдокод:

```python
population = initialize_population()

for generation in range(MAX_GENERATIONS):

    evaluated = []

    for individual in population:

        if not unique(individual):
            continue

        quick = quick_rate(individual)

        evaluated.append((individual, quick))

    evaluated.sort(key=fitness)

    elites = top(evaluated)

    # Дорогой анализ только лучших
    for ind in top_percent(evaluated, 0.05):
        ind.deep_rating = advanced_human_analysis(ind)
        ind.fitness = full_fitness(ind)

    next_population = elites

    while len(next_population) < POP_SIZE:

        parent = tournament_select(evaluated)

        if random() < CROSSOVER_RATE:
            parent2 = tournament_select(evaluated)
            child = crossover(parent, parent2)
        else:
            child = clone(parent)

        child = mutate(child)

        if not unique(child):
            child = repair(child)

        if unique(child):
            next_population.append(child)

    population = diversity_filter(next_population)

    periodically:
        inject_random_individuals()
```

---

# 39. Memetic improvement

После genetic mutation добавить локальный поиск.

То есть алгоритм становится:

```text
Genetic Algorithm
+
Local Search
```

Для хорошего child:

```text
проверить все возможные single swaps
```

Например:

```text
remove one current clue
add one absent clue
```

Посмотреть, какой swap сильнее всего увеличивает difficulty.

Применить лучший.

Это называется memetic algorithm и для данной задачи подходит лучше чистого GA.

---

# 40. Simulated annealing

Чтобы не застревать, иногда принимать ухудшения.

```python
if new_fitness > old_fitness:
    accept
else:
    probability = exp((new-old)/temperature)
```

Temperature постепенно уменьшать.

Это особенно полезно, потому что landscape Sudoku очень неровный:

```text
удаление одной clue
```

может внезапно:

```text
уничтожить uniqueness

или

снизить сложность с Extreme до Easy.
```

---

# 41. Novelty search

Не оптимизировать исключительно fitness.

Добавить небольшой novelty score.

Характеристики:

```text
clue pattern
technique histogram
hardest technique
bottleneck positions
chain structures
```

Это заставляет population исследовать новые структуры Sudoku.

---

# 42. Multi-stage evaluation

Чтобы программа была быстрой, fitness вычислять уровнями.

## Stage 1

Очень дёшево:

```text
valid?
17 <= clues <= 25?
unique?
```

Большинство кандидатов отбрасывать здесь.

---

## Stage 2

Basic Human Solver:

```text
Singles
Locked
Pairs
Triples
```

Если puzzle полностью решилось:

```text
не Extreme
```

Низкий fitness.

---

## Stage 3

Intermediate solver.

```text
Fish
Wings
Coloring
```

Если решилось:

```text
Expert, но не Extreme
```

---

## Stage 4

Advanced solver:

```text
Chains
AIC
ALS
Complex fish
```

---

## Stage 5

Очень дорого:

```text
forcing chains
multi-path analysis
minimax logical rating
```

Только top candidates.

---

# 43. Puzzle acceptance

Финальный Extreme puzzle принимать только если:

```python
assert clue_count <= 21
assert clue_count >= 17

assert exact_solver.count_solutions(puzzle, 2) == 1

assert basic_solver.solve(puzzle).solved is False

assert intermediate_solver.solve(puzzle).solved is False

advanced = advanced_solver.solve(puzzle)

assert advanced.solved
assert not advanced.used_backtracking

assert advanced.true_bottleneck_count >= 2

assert advanced.advanced_steps >= 3
```

Для Ultra:

```python
assert hardest_rating >= 8
assert true_bottleneck_count >= 3
assert advanced_steps >= 5
assert longest_chain >= 8
```

---

# 44. Не требовать строго 17 clues

Крайне важно.

Основной optimization objective должен быть:

```text
1. Extreme difficulty
2. uniqueness
3. logical solvability
4. low clue count
```

а не:

```text
1. 17 clues
2. всё остальное
```

Лучше получить:

```text
19 clues
SE-like difficulty 9+
несколько AIC/ALS/forcing bottlenecks
```

чем:

```text
17 clues
решаемые hidden singles + pairs.
```

Поэтому сделать режимы:

```python
TARGET_CLUES_MIN = 17
TARGET_CLUES_IDEAL = 17
TARGET_CLUES_MAX = 21
```

---

# 45. Специализированный режим 17 clues

Отдельно:

```python
mode="minimum_clues"
```

Здесь objective меняется:

```text
PRIMARY: clue count
SECONDARY: uniqueness
THIRD: difficulty
```

После нахождения уникальных 17-clue Sudoku уже среди них искать максимально сложные.

Не смешивать этот режим с обычным Extreme search.

---

# 46. Difficulty bottleneck map

Для каждого состояния solution path сохранять:

```text
cell candidates
available techniques
minimum technique rating
```

Можно получить график:

```text
start
 |
1.0
1.0
2.0
4.2
8.0 <- bottleneck
1.0
3.4
8.5 <- bottleneck
1.0
9.0 <- bottleneck
...
solved
```

Именно задачи с несколькими высокими пиками особенно интересны.

---

# 47. Difficulty profile

Сохранять:

```python
difficulty_profile = [
    1,1,1,2,3,8,
    1,1,4,
    9,
    1,2,
    8,
    ...
]
```

Дополнительная fitness:

```python
peak_count
peak_height
area_under_curve
late_game_peak
```

Особенно ценить сложные bottlenecks:

```text
в середине
и
ближе к концу решения.
```

---

# 48. Не допускать fake-extreme

Плохой пример:

```text
первая позиция требует безумного forcing chain,
после чего всё решается singles.
```

Это сложная задача, но менее интересная.

Давать бонус за:

```text
несколько разнесённых bottlenecks.
```

Например:

```python
distributed_extreme_score
```

---

# 49. Hardness floor

Задать:

```python
EXTREME_FLOOR
```

Например:

```text
минимальный обязательный technique level = AIC
```

Или:

```text
ALS-XZ / long chain.
```

Если задача ни разу не достигает этого уровня:

```text
не сохранять её как Extreme
```

независимо от количества clues.

---

# 50. Сохранение результата

Формат JSON:

```json
{
  "puzzle": "...81 chars...",
  "solution": "...81 chars...",

  "clues": 18,

  "unique": true,
  "minimal": true,

  "difficulty": {
    "class": "ULTRA_EXTREME",
    "fitness": 18422.8,
    "hardest_rating": 9.1,
    "total_logic_score": 834.2,
    "advanced_steps": 7,
    "true_bottlenecks": 4,
    "longest_chain": 15
  },

  "techniques": {
    "Naked Single": 14,
    "Hidden Single": 8,
    "X-Wing": 1,
    "XY-Wing": 2,
    "AIC": 3,
    "ALS-XZ": 1,
    "Forcing Chain": 1
  },

  "solution_path": [...]
}
```

---

# 51. Обязательно сохранять объяснимость

Для каждой задачи генератор должен уметь вывести:

```text
Step 1:
Hidden Single r3c6 = 7

Step 2:
Locked Candidates ...

Step 17:
AIC:
(r2c3=4) - ...
=> eliminate 4 from r7c3

Step 18:
...

Step 34:
ALS-XZ ...

Solved.
```

Иначе невозможно проверить, является ли puzzle действительно логически интересным.

---

# 52. Повторная независимая валидация

После генерации финального кандидата снова:

1. очистить все caches;
2. заново загрузить puzzle;
3. exact count_solutions;
4. human solve;
5. multi-path difficulty analysis;
6. minimality check.

Только после этого сохранять.

---

# 53. Minimality verification

Для каждого clue:

```python
candidate = puzzle_without(clue)

if unique(candidate):
    puzzle_is_not_minimal
```

Финальный 17–20 clue Extreme желательно делать minimal:

```text
удаление любой исходной цифры уничтожает uniqueness.
```

---

# 54. Кэширование

Это чрезвычайно важно.

Ключ:

```python
clue_mask
```

Caches:

```python
uniqueness_cache
human_rating_cache
candidate_state_cache
fitness_cache
```

Например:

```python
@cache
def count_solutions(mask):
    ...
```

Эволюция будет многократно посещать близкие masks.

---

# 55. Parallelization

Fitness отдельных individuals практически независим.

Использовать multiprocessing.

Например:

```text
main process:
selection/evolution

workers:
uniqueness
human rating
deep analysis
```

Не использовать threading для CPU-bound Python, если большая часть solver написана на чистом Python.

---

# 56. Performance priority

Наиболее часто выполняемые части оптимизировать:

1. uniqueness solver;
2. candidate generation;
3. singles;
4. basic techniques;
5. hashing/cache.

Редкие ALS/forcing algorithms могут первоначально быть менее оптимизированы.

---

# 57. Development order

НЕ пытаться реализовать всё сразу.

## Phase 1

Реализовать:

```text
Grid
Candidate masks
Exact solver
Unique test
Full-grid generator
Clue-mask generator
Singles
Locked Candidates
Pairs/Triples
```

Добиться корректности.

## Phase 2

```text
X-Wing
Swordfish
Skyscraper
2-String Kite
XY-Wing
XYZ-Wing
W-Wing
Coloring
```

## Phase 3

```text
X-Chain
XY-Chain
AIC
```

## Phase 4

```text
ALS
ALS-XZ
ALS Chains
```

## Phase 5

```text
Forcing Chains
Grouped AIC
Complex Fish
```

## Phase 6

```text
Evolution
fitness
multi-path rating
optimization
parallelization
```

---

# 58. Главное правило тестирования техник

Для каждой technique создать unit tests:

```text
positive case:
техника существует

negative case:
техники нет

expected eliminations:
точно совпадают
```

Human solver является основой fitness.

Ошибка здесь приведёт к генерации Sudoku с ложным рейтингом.

---

# 59. Не использовать solution при human solving

Критически важно.

Human Solver не должен смотреть на известный solution.

Нельзя делать:

```python
if candidate == solution[cell]:
```

чтобы понять правильность elimination.

Technique должна доказывать elimination только из текущего candidate state.

Solution разрешён:

```text
exact solver
generator
validation
```

но не human techniques.

---

# 60. Борьба с ошибочными uniqueness-based techniques

Такие техники, как Unique Rectangle, иногда опираются на предположение уникальности.

Разделить:

```text
pure logic
uniqueness techniques
```

И дать режим:

```python
allow_uniqueness_techniques = True/False
```

Для наиболее чистых Extreme puzzles желательно иметь возможность искать задачи, решаемые без uniqueness assumptions.

---

# 61. Основной fitness, рекомендуемая версия

Реализовать сначала такую:

```python
def fitness(puzzle):

    clues = count_clues(puzzle)

    if clues < 17:
        return -INF

    if clues > 24:
        return -10000

    if count_solutions(puzzle, limit=2) != 1:
        return -INF

    basic = solve_with_max_level(puzzle, BASIC)

    if basic.solved:
        return (
            -5000
            + clue_bonus(clues)
        )

    intermediate = solve_with_max_level(
        puzzle,
        INTERMEDIATE
    )

    if intermediate.solved:
        return (
            -1000
            + intermediate.score
            + clue_bonus(clues)
        )

    advanced = solve_advanced(puzzle)

    if not advanced.solved:
        # Пока неизвестно:
        # возможно puzzle выше возможностей solver.
        return -2000

    score = 0

    score += advanced.hardest_rating * 500

    score += advanced.total_weighted_score

    score += advanced.advanced_steps * 100

    score += advanced.true_bottlenecks * 500

    score += advanced.longest_chain * 20

    score += advanced.chain_step_count * 100

    score += advanced.als_step_count * 150

    score += advanced.forcing_step_count * 250

    score += clue_bonus(clues)

    if is_minimal(puzzle):
        score += 300

    return score
```

Позже заменить линейную формулу на multi-objective.

---

# 62. Лучше перейти на multi-objective optimization

Финальная версия желательно NSGA-II либо похожий подход.

Objectives:

```text
maximize hardest_required_technique

maximize advanced_bottlenecks

maximize total_logic_complexity

maximize chain_complexity

minimize clue_count
```

То есть individual имеет vector:

```python
fitness = (
    hardest_required,
    bottlenecks,
    advanced_score,
    chain_score,
    -clue_count,
)
```

Потом использовать Pareto frontier.

Это лучше, чем вручную угадывать один универсальный коэффициент.

---

# 63. Pareto frontier

Могут существовать:

```text
Puzzle A
17 clues
difficulty 8.0

Puzzle B
19 clues
difficulty 9.4

Puzzle C
21 clues
difficulty 10.0
```

Нет причины автоматически уничтожать B/C только потому, что A имеет меньше clues.

Все три могут находиться на Pareto frontier.

Пользователь уже сам выбирает:

```text
минимум clues
или
максимум difficulty.
```

---

# 64. Режим GENERATE_MONSTER

Добавить профиль:

```python
GENERATE_MONSTER = {
    "clues_min": 17,
    "clues_max": 21,

    "require_unique": True,
    "require_minimal": True,

    "reject_basic_solution": True,
    "reject_intermediate_solution": True,

    "minimum_hardest_level": "AIC",

    "minimum_advanced_steps": 4,
    "minimum_bottlenecks": 3,

    "prefer_long_chains": True,
    "prefer_als": True,
    "prefer_forcing": True
}
```

---

# 65. Конечный алгоритм GENERATE_MONSTER

Высокоуровневый псевдокод:

```python
def generate_monster():

    global_archive = []

    solutions = generate_random_solutions(N)

    population = []

    for solution in solutions:

        seeds = create_unique_minimal_seeds(solution)

        population.extend(seeds)

    for generation in range(MAX_GENERATIONS):

        # 1
        cheap_validate(population)

        # 2
        population = [
            p for p in population
            if p.unique
        ]

        # 3
        quick_rate(population)

        # 4
        promising = select_promising(population)

        # 5
        deep_logic_rate(promising)

        # 6
        monsters = [
            p for p in promising
            if passes_extreme_constraints(p)
        ]

        # 7
        global_archive = pareto_merge(
            global_archive,
            monsters
        )

        # 8
        elites = select_elites(population)

        children = []

        while len(children) < CHILD_COUNT:

            parent = tournament_select(population)

            op = choose_mutation_operator()

            child = op(parent)

            if not child.unique:
                child = uniqueness_repair(child)

            child = local_improvement(child)

            children.append(child)

        # 9
        random_injections = create_random_seeds()

        # 10
        population = diversity_select(
            elites
            + children
            + random_injections
        )

    # Финальная сертификация
    certified = []

    for puzzle in global_archive:

        if not uniqueness_check_from_scratch(puzzle):
            continue

        if not minimality_check(puzzle):
            continue

        result = exhaustive_logic_rating(puzzle)

        if not result.solved_without_guessing:
            continue

        if result.true_bottlenecks < REQUIRED:
            continue

        certified.append(
            build_report(puzzle, result)
        )

    return sort_pareto(certified)
```

---

# 66. Что считать идеальным результатом

Желательный пример результата генератора:

```text
Clues: 18
Unique: yes
Minimal: yes

Basic solver:
STUCK

Intermediate solver:
STUCK

Advanced logical solver:
SOLVED

Guessing:
NO

Backtracking during human solve:
NO

Solution path:
Singles             17
Locked Candidates    3
X-Wing               1
XY-Wing              2
X-Chain              1
AIC                  3
ALS-XZ               2
Forcing Chain        1

True bottlenecks:
4

Longest chain:
17 links

Hardest required:
Forcing Chain

Difficulty:
ULTRA EXTREME
```

Такой Sudoku намного ближе к поставленной задаче, чем просто случайный grid с 17 clues.

---

# 67. Основной принцип проекта

Не оптимизировать:

```text
"как мало цифр оставить?"
```

Оптимизировать:

```text
"какой минимальный уровень логики неизбежно потребуется
даже при оптимальном человеческом пути решения?"
```

И лишь вторым критерием:

```text
"можно ли одновременно приблизиться к 17 clues?"
```

Именно это должно быть главным критерием эволюционного алгоритма.

---

# 68. Рекомендуемая стратегия для первой рабочей версии

Первая реально полезная версия генератора должна искать не строго 17, а:

```text
17–21 clues
```

и обязательно требовать:

```text
UNIQUE

Basic -> STUCK

Intermediate -> STUCK

Advanced -> SOLVED

AIC или выше требуется хотя бы один раз

>= 3 advanced steps

>= 2 genuine bottlenecks

NO guessing

NO DFS in human solver
```

После того как такой генератор стабильно создаёт Extreme задачи, добавить:

```text
ALS
forcing chains
multi-path minimax difficulty
17-clue hitting-set optimization
```

---

# 69. Дополнительное требование для Codex

Код должен проектироваться так, чтобы новые solving techniques подключались как плагины:

```python
class Technique(ABC):

    name: str
    difficulty: float

    @abstractmethod
    def find_steps(
        self,
        state: SudokuState
    ) -> list[LogicStep]:
        ...
```

Тогда можно постепенно увеличивать интеллект solver без переписывания генератора.

---

# 70. Главная проверка качества всей системы

После реализации создать тест:

```python
for puzzle in generated_extreme_puzzles:

    assert exact_solver.solutions(puzzle) == 1

    assert not BASIC_SOLVER.solve(puzzle).solved

    assert not INTERMEDIATE_SOLVER.solve(puzzle).solved

    result = EXTREME_SOLVER.solve(puzzle)

    assert result.solved
    assert result.guesses == 0
    assert result.backtracking == 0

    assert result.true_bottlenecks >= 2
```

А для лучших кандидатов:

```python
rating = minimax_logical_rating(puzzle)

assert rating >= EXTREME_THRESHOLD
```

Это и должно быть определением настоящего Extreme Sudoku внутри программы.

## Phase 7 implementation boundary

`generator/certification/` содержит отдельные config/result/status модели,
fresh mathematical validation, независимые proof validators, alternative-path
threshold search и strict production exporter. Legacy Phase 4 Deep и Phase 6
fitness остаются предварительными методами отбора кандидатов.

Production допускает только conclusive `CERTIFIED_EXTREME` /
`CERTIFIED_ULTRA_EXTREME`. Fresh exact uniqueness и factual minimality
отделены от human deductions; proof validator и logical search не используют
Exact Solver или known solution для вывода placements/eliminations.

Поиск минимизирует maximum rating path через последовательно понижаемые
thresholds от независимо проверенного upper witness и исследует
различные последовательности допустимых LogicSteps. Signature включает values
и candidate masks. Negative proof допустим лишь при исчерпании полного
reachable graph выбранной модели без limit reasons. Node/time/state/depth,
alternative-step и advanced enumeration limits дают `INCONCLUSIVE_BUDGET`.
Complete scope относится к реализованным finite pattern families, simple
candidate chains, disjoint ALS chains и single-assumption clause propagation;
это не исчерпывающая теория человеческих Sudoku-техник.

Критерии Extreme/Ultra сохраняют текущие DifficultyConfig floors и distribution
requirements; количество clues отдельно. Monster/17-clue hitting-set search,
новая эволюция, frontend integration и deployment не входят в этот этап.
Strict output: `data/production/puzzles.json`; research: `data/candidates.json`.
CLI, budgets, proof scope и acceptance gates полностью определены в
[CERTIFICATION_SPEC.md](CERTIFICATION_SPEC.md).

## Phase 9 implementation boundary

Content expansion reuses the unchanged generator (`generate_many`, random minimal puzzles, Deep rating) and the
unchanged certifier; it lives in `generator/production/` outside the fingerprinted folders. `production-batch`
orchestrates generate → prefilter (invalid, NOT_UNIQUE, HUMAN_UNSOLVED, TOO_EASY, exact/ID duplicates, same-solution
clue-mask distance ≤ 8, one puzzle per solution, symmetry-invariant fingerprint; technique-profile similarity is a
warning only) → certification-suitability ordering (Deep 30 > 32 > 35; ≥ 36 outside the conclusive SSL scope and
skipped from the quota) → probe certification (short budget, research only) → fresh default certification →
research archive and batch report. `production-merge` is the only path into `data/production/puzzles.json` for new
records: fresh default certification, verbatim existing records, verified backup, atomic write, post-validation with
restore. The suitability score is prioritization, not proof. No Monster 17–21 search, no extension of the Stuck-State
Lemma, no relaxation of certification gates or budgets. Formats: [DATA_FORMAT.md §57](DATA_FORMAT.md).
