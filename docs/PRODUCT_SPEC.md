# Product Specification — Extreme Sudoku

## 1. Назначение проекта

Extreme Sudoku — веб-приложение для решения классических Sudoku 9×9 с особым упором на задачи экстремального уровня сложности.

Ключевая особенность проекта — использование собственного Python-генератора, который должен создавать Sudoku с:

- единственным решением;
- малым количеством исходных цифр;
- преимущественно 17–21 clue;
- высокой логической сложностью;
- обязательным использованием продвинутых методов решения;
- проверяемым логическим solution path;
- отсутствием перебора при оценке человеческой сложности.

Проект состоит из двух независимых частей:

```text
Python Generator
      ↓
data/puzzles.json
      ↓
Web Application
```

Python-генератор создаёт и проверяет задачи.

Frontend загружает уже готовые задачи и предоставляет интерфейс для их решения.

---

# 2. Главная цель

Создать публичное веб-приложение, в котором пользователь может решать действительно сложные Sudoku, созданные собственным генератором.

Основная продуктовая цель:

> Пользователь должен получать Sudoku, сложность которых определяется не только малым количеством исходных цифр, а необходимостью применения продвинутых логических методов.

Приоритет проекта:

```text
качество задачи
>
логическая сложность
>
единственность решения
>
малое количество clues
>
количество сгенерированных задач
```

---

# 3. Основные принципы

Проект должен соблюдать следующие принципы.

## 3.1 Генератор и frontend независимы

Frontend не должен:

- генерировать Extreme Sudoku;
- проверять уникальность;
- вычислять рейтинг;
- выполнять тяжёлый Human Solver;
- запускать эволюционный алгоритм.

Python generator не должен:

- зависеть от UI;
- содержать frontend-логику;
- работать внутри браузера.

Связь осуществляется через:

```text
data/puzzles.json
```

---

## 3.2 Корректность важнее производительности

Неправильно оценённое Sudoku хуже медленного генератора.

Особенно это касается:

- uniqueness;
- candidate elimination;
- advanced techniques;
- difficulty rating;
- bottleneck detection.

---

## 3.3 Backtracking не является мерой сложности

Backtracking разрешён только для:

- создания полного solution grid;
- проверки существования решения;
- проверки уникальности.

Backtracking не должен использоваться Human Solver для определения сложности.

---

## 3.4 Количество clues не определяет сложность

17 clues является желательным результатом, но не основной целью.

Например:

```text
17 clues + простое решение
```

хуже, чем:

```text
19 clues + несколько обязательных AIC/ALS/forcing bottlenecks
```

Основной критерий — логическая сложность.

---

# 4. Целевая аудитория

Основная аудитория:

- опытные любители Sudoku;
- пользователи, которым обычные Easy/Medium/Hard задачи кажутся слишком простыми;
- пользователи, интересующиеся advanced Sudoku techniques;
- программисты и энтузиасты логических головоломок;
- пользователи, желающие решать задачи уровня Extreme / Ultra Extreme.

В дальнейшем проект может быть расширен для обычной аудитории уровня:

```text
Easy
Medium
Hard
Expert
```

Но первоначальный фокус:

```text
Extreme
Ultra Extreme
```

---

# 5. Основной пользовательский сценарий

Пользователь открывает сайт.

Приложение:

1. загружает базу Sudoku;
2. предлагает начать новую игру;
3. показывает уровень сложности;
4. показывает количество clues;
5. отображает Sudoku grid;
6. позволяет вводить значения и notes;
7. сохраняет прогресс;
8. показывает время;
9. позволяет пользоваться Undo, Hint и Restart;
10. определяет успешное завершение задачи.

Основной сценарий должен работать без регистрации.

---

# 6. Основные компоненты проекта

Проект состоит из следующих компонентов.

```text
Extreme Sudoku
│
├── Generator
│
│   ├── Exact Solver
│   ├── Human Solver
│   ├── Difficulty Rating
│   ├── Evolution Engine
│   ├── Puzzle Validator
│   └── Export
│
├── Data
│   └── puzzles.json
│
└── Web
    ├── Sudoku UI
    ├── Game State
    ├── Input
    ├── Notes
    ├── Timer
    ├── Hints
    ├── Local Storage
    └── Puzzle Loader
```

---

# 7. Generator

Подробное техническое описание находится в:

```text
docs/GENERATOR_SPEC.md
```

Generator отвечает за:

- создание полного solution grid;
- создание puzzle;
- проверку единственности;
- Human Solver;
- оценку сложности;
- evolutionary search;
- поиск минимальных puzzles;
- поиск Extreme puzzles;
- экспорт базы.

---

# 8. Exact Solver

Exact Solver используется исключительно как математический инструмент.

Он должен:

- находить решение;
- считать количество решений;
- прекращать поиск после второго решения;
- подтверждать uniqueness.

Допустимы:

- DFS;
- backtracking;
- MRV;
- constraint propagation;
- bitmasks.

Exact Solver не определяет человеческую сложность.

---

# 9. Human Solver

Human Solver является центральным компонентом рейтинга.

Он должен решать Sudoku используя только формализованные логические техники.

Пример уровней:

```text
Singles
Subsets
Locked Candidates
Fish
Wings
Coloring
Chains
AIC
ALS
Forcing Chains
```

Human Solver должен сохранять:

- каждое применение техники;
- placements;
- eliminations;
- рейтинг шага;
- explanation;
- chain information;
- bottlenecks.

---

# 10. Extreme Sudoku

Задача не считается Extreme только из-за количества clues.

Минимальные требования для Extreme:

```text
unique solution
Basic Solver -> STUCK
Intermediate Solver -> STUCK
Advanced Solver -> SOLVED
no guessing
no Human Solver backtracking
advanced techniques required
```

Желательно:

```text
17–21 clues
minimal puzzle
>= 3 advanced logical steps
>= 2 genuine bottlenecks
```

---

# 11. Ultra Extreme Sudoku

Ultra Extreme является более строгой категорией.

Примерные критерии:

```text
17–21 clues

unique
minimal

Basic -> STUCK
Intermediate -> STUCK

Advanced -> SOLVED

>= 5 advanced steps

>= 3 true bottlenecks

AIC / ALS / forcing level required

long logical chains

no guessing
```

Фактические пороги определяются rating system.

---

# 12. Difficulty rating

Сложность должна учитывать:

- hardest required technique;
- количество advanced steps;
- количество bottlenecks;
- chain complexity;
- chain length;
- total logical score;
- search complexity;
- наличие альтернативных логических путей.

Не использовать только:

```text
hardestTechnique
```

как единственный рейтинг.

---

# 13. Логическая неизбежность

Для наиболее сложных puzzles система должна пытаться определить:

> Можно ли решить задачу более простым логическим путём?

Если найден сложный AIC, но существует простой X-Wing, позволяющий его избежать, AIC не должен автоматически считаться обязательным.

В перспективе используется:

```text
minimax logical difficulty
```

то есть сложность самого простого возможного логического solution path.

---

# 14. Эволюционный поиск

Generator должен использовать evolutionary / memetic search для поиска сложных задач.

Оптимизация должна учитывать одновременно:

```text
maximize logical difficulty
maximize bottlenecks
maximize advanced techniques
maximize chain complexity
minimize clue count
```

Желательно использовать multi-objective подход.

---

# 15. Frontend

Подробное описание:

```text
docs/UI_SPEC.md
```

Frontend должен работать как статическое веб-приложение.

Целевая платформа:

```text
GitHub Pages
```

---

# 16. Поддерживаемые устройства

Интерфейс должен корректно работать на:

- desktop;
- laptop;
- tablet;
- smartphone.

Основные браузеры:

- Chrome;
- Edge;
- Firefox;
- Safari.

---

# 17. Основные функции frontend

Минимально:

- Sudoku grid 9×9;
- ввод цифр;
- Notes Mode;
- Undo;
- Erase;
- Restart;
- New Game;
- Timer;
- Difficulty;
- Clue count;
- responsive UI;
- localStorage;
- загрузка `puzzles.json`.

---

# 18. Дополнительные функции

После MVP:

- hints;
- advanced technique hints;
- puzzle details;
- logical solution replay;
- statistics;
- themes;
- history;
- completed puzzles;
- daily puzzle.

---

# 19. Формат данных

Контракт между generator и frontend описан в:

```text
docs/DATA_FORMAT.md
```

Основной поток:

```text
Generator
    ↓
data/puzzles.json
    ↓
Frontend
```

---

# 20. MVP

Minimum Viable Product должен содержать:

## Generator

```text
Exact Solver
Unique Solution Check
Full Grid Generator
Basic Human Solver
Difficulty classification
Puzzle export
```

## Frontend

```text
Sudoku Grid
Number Input
Notes
Erase
Undo
Timer
Restart
New Game
Difficulty
Persistence
```

## Data

```text
puzzles.json
```

с минимум несколькими корректными Sudoku.

На стадии MVP задачи могут быть тестовыми и не обязательно Ultra Extreme.

---

# 21. Граница MVP

MVP считается завершённым, когда можно:

```text
запустить генератор
        ↓
получить puzzles.json
        ↓
открыть GitHub Pages
        ↓
выбрать Sudoku
        ↓
полностью решить его в браузере
```

без ручного изменения данных.

---

# 22. Что НЕ входит в первую версию

Первая версия не должна включать:

- аккаунты пользователей;
- серверную базу данных;
- backend API;
- multiplayer;
- realtime multiplayer;
- cloud saves;
- monetization;
- advertisements;
- mobile application;
- App Store / Google Play;
- social network;
- tournaments;
- global leaderboards.

Не добавлять эти возможности до завершения основного продукта.

---

# 23. Регистрация

Регистрация пользователей не требуется.

Прогресс хранится локально.

Использовать:

```text
localStorage
```

---

# 24. Backend

Для первой версии backend отсутствует.

Архитектура:

```text
GitHub Pages
+
static JSON
```

Это сознательное решение.

---

# 25. Серверная генерация

Generator не запускается при открытии сайта.

Sudoku генерируются заранее.

Pipeline:

```text
Python generator
        ↓
validation
        ↓
puzzles.json
        ↓
Git commit
        ↓
GitHub Pages
```

---

# 26. Производительность frontend

Открытие игры не должно запускать тяжёлые Sudoku-алгоритмы.

Frontend должен оставаться отзывчивым даже на мобильном устройстве.

---

# 27. Производительность generator

Generator может быть вычислительно тяжёлым.

Допустимы:

- multiprocessing;
- caching;
- long-running searches;
- evolutionary populations;
- expensive final validation.

Главное — корректность результата.

---

# 28. Репозиторий

Рекомендуемая структура:

```text
extreme-sudoku/
│
├── AGENTS.md
├── README.md
│
├── docs/
│   ├── PRODUCT_SPEC.md
│   ├── GENERATOR_SPEC.md
│   ├── UI_SPEC.md
│   └── DATA_FORMAT.md
│
├── generator/
│   ├── sudoku/
│   ├── solver/
│   ├── evolution/
│   ├── rating/
│   └── tests/
│
├── web/
│
└── data/
    └── puzzles.json
```

---

# 29. Источник истины

Для разных частей проекта используются разные документы.

```text
PRODUCT_SPEC.md
→ что создаётся и зачем

GENERATOR_SPEC.md
→ алгоритмы generator

UI_SPEC.md
→ frontend

DATA_FORMAT.md
→ контракт данных
```

При конфликте технической реализации с product requirements сначала необходимо определить, какой документ требует изменения.

Не изменять требования молча.

---

# 30. Этап разработки 1 — Project Foundation

Цель:

создать каркас проекта.

Необходимо:

- создать структуру директорий;
- добавить документацию;
- определить data contract;
- создать базовые тесты;
- подготовить tooling.

Результат:

```text
репозиторий готов для независимой разработки
frontend и generator.
```

---

# 31. Этап разработки 2 — Frontend Prototype

Цель:

создать полностью работающий интерфейс на mock Sudoku.

Не реализовывать сложный generator.

Функции:

- grid;
- selection;
- number input;
- notes;
- undo;
- erase;
- timer;
- restart;
- responsive design;
- mock puzzle.

Критерий:

```text
тестовую Sudoku можно полностью решить через UI.
```

---

# 32. Этап разработки 3 — Exact Sudoku Engine

Реализовать:

- Grid;
- peers;
- units;
- bitmasks;
- candidate calculation;
- Exact Solver;
- count solutions;
- uniqueness;
- full-grid generator.

Критерии:

```text
корректно решает тестовые Sudoku
находит multiple solutions
подтверждает uniqueness
```

---

# 33. Этап разработки 4 — Basic Human Solver

Реализовать сначала:

```text
Naked Single
Hidden Single
Locked Candidates
Pairs
Triples
```

Human Solver не использует backtracking.

Критерий:

```text
известные тестовые puzzles решаются
ожидаемыми техниками.
```

---

# 34. Этап разработки 5 — Intermediate Solver

Добавить:

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

Каждая техника должна иметь отдельные tests.

---

# 35. Этап разработки 6 — Advanced Solver

Добавить:

```text
X-Chain
XY-Chain
AIC
Grouped AIC
ALS-XZ
ALS Chains
Forcing Chains
```

Это критический этап Extreme Generator.

---

# 36. Этап разработки 7 — Difficulty Rating

Добавить:

- technique weights;
- total score;
- hardest required technique;
- advanced steps;
- bottlenecks;
- chain complexity;
- difficulty profile.

Первые категории:

```text
Easy
Medium
Hard
Expert
Extreme
Ultra Extreme
```

---

# 37. Этап разработки 8 — Basic Generator

Создавать puzzles через:

```text
full grid
↓
clue removal
↓
uniqueness checking
↓
minimalization
```

На этом этапе evolutionary search ещё необязателен.

---

# 38. Этап разработки 9 — Evolutionary Generator

Добавить:

- population;
- mutation;
- swap;
- multi-swap;
- crossover;
- uniqueness repair;
- fitness;
- elitism;
- diversity;
- local search.

Цель:

```text
автоматически повышать logical difficulty.
```

---

# 39. Этап разработки 10 — Extreme Search

Generator начинает целенаправленно искать задачи:

```text
17–21 clues

Basic -> STUCK

Intermediate -> STUCK

Advanced -> SOLVED
```

с несколькими advanced bottlenecks.

---

# 40. Этап разработки 11 — Deep Rating

Для лучших кандидатов реализовать:

- alternative path analysis;
- mandatory technique verification;
- minimax logical rating;
- deep bottleneck validation.

Это позволяет уменьшить количество fake-extreme puzzles.

---

# 41. Этап разработки 12 — Data Export

Generator экспортирует задачи в формат:

```text
docs/DATA_FORMAT.md
```

Результат:

```text
data/puzzles.json
```

---

# 42. Этап разработки 13 — Integration

Frontend перестаёт использовать mock Sudoku.

Он загружает:

```text
data/puzzles.json
```

и использует реальные задачи generator.

Критерий:

```text
generator и frontend работают вместе
без ручной конвертации данных.
```

---

# 43. Этап разработки 14 — GitHub Pages

Настроить публикацию frontend.

Сайт должен:

- открываться по GitHub Pages URL;
- загружать puzzle database;
- работать после refresh;
- работать без backend.

---

# 44. Этап разработки 15 — Advanced Hints

Использовать `solutionPath` для:

- названия техники;
- подсветки relevant cells;
- candidate eliminations;
- краткого объяснения.

---

# 45. Этап разработки 16 — Final Extreme Certification

Для публикуемых Extreme puzzles выполнять:

```text
fresh uniqueness check
minimality check
Human Solver check
difficulty check
bottleneck check
solution-path validation
```

Только после этого puzzle попадает в production database.

---

# 46. Критерии готовности Exact Solver

Exact Solver готов, если:

- проходит unit tests;
- корректно решает Sudoku;
- корректно определяет invalid puzzle;
- корректно определяет multiple solutions;
- count solutions останавливается после установленного limit;
- результаты воспроизводимы.

---

# 47. Критерии готовности Human Solver

Human Solver готов, если:

- не использует solution grid для доказательства eliminations;
- не использует DFS;
- каждая техника имеет tests;
- каждый шаг объясним;
- state после каждого шага остаётся валидным;
- полный solution path воспроизводим.

---

# 48. Критерии готовности Extreme Generator

Extreme Generator считается готовым, если способен автоматически получать задачи, удовлетворяющие:

```text
unique = true

17 <= clues <= 21
или обоснованно немного больше

Basic Solver = STUCK

Intermediate Solver = STUCK

Advanced Solver = SOLVED

Human backtracking = 0

advancedSteps >= configured minimum

trueBottlenecks >= configured minimum
```

---

# 49. Критерии готовности frontend

Frontend готов, если:

- корректно отображает 9×9;
- нельзя менять clues;
- работает keyboard input;
- работает touch input;
- Notes работают;
- Undo работает;
- Restart работает;
- timer работает;
- refresh не уничтожает progress;
- mobile layout не имеет horizontal scroll;
- puzzle можно полностью решить.

---

# 50. Критерии готовности data integration

Интеграция готова, если:

- Generator создаёт `puzzles.json`;
- Frontend читает его напрямую;
- структура соответствует `DATA_FORMAT.md`;
- malformed puzzle не ломает приложение;
- difficulty отображается корректно;
- clue count совпадает;
- puzzle и solution согласованы.

---

# 51. Критерии готовности GitHub Pages

Production deployment готов, если:

- сайт открывается через HTTPS;
- assets загружаются;
- JSON загружается;
- navigation работает;
- refresh работает;
- desktop работает;
- mobile работает;
- нет критических console errors.

---

# 52. Definition of Done — MVP

MVP завершён, если выполняется полный pipeline:

```text
1. Запускается Python generator.

2. Создаётся валидная задача.

3. Уникальность подтверждена.

4. Задача экспортируется.

5. Frontend загружает её.

6. Пользователь может решить её.

7. Progress сохраняется.

8. Completion определяется корректно.

9. Сайт работает на GitHub Pages.
```

---

# 53. Definition of Done — Extreme Release

Первая полноценная версия Extreme Sudoku готова, когда:

- существует стабильный Exact Solver;
- существует Advanced Human Solver;
- реализован difficulty rating;
- реализован evolutionary generator;
- существуют Extreme puzzles;
- существуют Ultra Extreme puzzles;
- каждая production puzzle уникальна;
- задачи проходят final certification;
- frontend работает с production database;
- есть responsive UI;
- работает local persistence;
- проект опубликован на GitHub Pages.

---

# 54. Quality Gate для production puzzles

Перед публикацией каждая задача должна пройти:

```text
VALID GRID
      ↓
UNIQUE
      ↓
MINIMALITY CHECK
      ↓
HUMAN SOLVE
      ↓
DIFFICULTY ANALYSIS
      ↓
BOTTLENECK VALIDATION
      ↓
EXPORT VALIDATION
      ↓
PRODUCTION
```

При провале любого обязательного этапа задача не публикуется.

---

# 55. Тестирование

Проект должен содержать:

## Unit tests

для:

- grid;
- candidates;
- Exact Solver;
- individual techniques;
- mutations;
- rating components;
- data validation.

## Integration tests

для:

```text
generator → JSON
JSON → frontend
```

## Regression tests

Сохранять набор известных puzzles, чтобы изменения solver не меняли результаты неожиданно.

---

# 56. Regression dataset

Создать отдельный набор:

```text
tests/fixtures/
```

с задачами, для которых заранее известны:

- solution;
- uniqueness;
- ожидаемые techniques;
- expected eliminations;
- difficulty class.

---

# 57. Требование воспроизводимости

Генератор должен поддерживать:

```text
random seed
```

Для ошибок должно быть возможно повторить конкретный generation run.

Логировать:

```text
seed
configuration
generator version
```

---

# 58. Логирование generator

Generator должен записывать:

- generation number;
- population size;
- best fitness;
- clue count;
- hardest technique;
- bottleneck count;
- discovered Extreme candidates.

Не выводить чрезмерно подробные данные для каждого слабого individual.

---

# 59. Конфигурация

Основные параметры не должны быть разбросаны по коду.

Хранить конфигурацию отдельно.

Пример:

```text
population size
mutation rate
crossover rate
clue targets
technique weights
Extreme thresholds
Ultra thresholds
worker count
```

---

# 60. Безопасность данных

Frontend не работает с чувствительными пользовательскими данными.

Не требуется:

- аккаунт;
- email;
- пароль;
- платежи;
- личная информация.

localStorage используется только для игрового состояния и настроек.

---

# 61. Ограничения GitHub Pages

При разработке учитывать:

- нет server-side Python;
- нет постоянного backend process;
- static hosting;
- данные должны быть доступны как static assets.

Поэтому generator запускается отдельно от production frontend.

---

# 62. Будущие направления

После первой стабильной версии могут быть добавлены:

```text
Daily Extreme
Puzzle of the Day
Logical Hint System
Solution Replay
Statistics
Achievement system
Import Sudoku
Custom Sudoku analysis
Difficulty analyzer
Technique trainer
Share links
PWA
Offline mode
```

---

# 63. Возможный Sudoku Analyzer

В будущем generator engine может использоваться отдельно:

```text
пользователь вводит Sudoku
        ↓
Human Solver
        ↓
rating
        ↓
technique report
```

Это не является обязательным для первой версии.

---

# 64. Возможный Technique Trainer

Можно использовать базу с solution paths для обучения:

```text
X-Wing trainer
AIC trainer
ALS trainer
Forcing Chain trainer
```

Но это отдельный будущий продуктовый модуль.

---

# 65. Не допускать scope creep

До достижения Extreme Release не тратить значительное время на:

- animations;
- achievements;
- user accounts;
- leaderboards;
- social features;
- visual effects;
- complicated settings.

Приоритет:

```text
Sudoku correctness
↓
Human Solver correctness
↓
Extreme generation
↓
good gameplay
↓
everything else
```

---

# 66. Главный технический риск

Наибольший риск проекта — не frontend.

Главный риск:

> Human Solver неправильно классифицирует сложность задачи.

Поэтому advanced solving techniques и rating system должны иметь особенно хорошее тестовое покрытие.

---

# 67. Второй главный риск

Генератор может находить задачи, которые кажутся сложными только из-за ограничений самого Human Solver.

Поэтому необходимо постепенно добавлять:

- alternative solution path analysis;
- more techniques;
- minimax rating;
- independent verification.

---

# 68. Главный продуктовый критерий

Пользователь, выбрав:

```text
Extreme
```

не должен регулярно получать Sudoku, которое решается почти полностью Singles.

Пользователь, выбрав:

```text
Ultra Extreme
```

должен ожидать действительно тяжёлый логический challenge.

---

# 69. Основная метрика качества Extreme базы

Предпочтительная метрика:

```text
minimum logical difficulty
required to solve a puzzle
```

а не:

```text
maximum complexity
ever observed by one solver path
```

---

# 70. Финальная цель проекта

Итоговый продукт должен представлять собой:

```text
качественный Sudoku frontend
+
собственный математически корректный generator
+
собственный Human Solver
+
собственный difficulty rating
+
базу проверенных Extreme Sudoku
```

и работать как единый публичный проект на GitHub.

Главная отличительная особенность:

> Extreme Sudoku создаёт сложные задачи не случайным удалением цифр, а целенаправленным поиском Sudoku, для решения которых необходима продвинутая логика.