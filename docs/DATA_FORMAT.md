# Data Format Specification — Extreme Sudoku

## 1. Назначение

Этот документ описывает формат обмена данными между:

```text
Python Sudoku Generator
        ↓
data/puzzles.json
        ↓
Web Frontend
```

Генератор и frontend должны зависеть от этого контракта, а не друг от друга.

Изменения формата должны быть обратно совместимыми либо сопровождаться изменением `schemaVersion`.

---

# 2. Основной файл

Главный файл базы:

```text
data/puzzles.json
```

Формат:

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-09-26T18:00:00Z",
  "generatorVersion": "0.1.0",
  "puzzles": []
}
```

---

# 3. schemaVersion

Обязательное поле:

```json
"schemaVersion": 1
```

Используется для версионирования структуры данных.

Если структура существенно меняется:

```text
1 → 2
```

Frontend должен проверять поддерживаемую версию.

---

# 4. generatedAt

Дата создания базы.

Формат:

```text
ISO 8601 UTC
```

Пример:

```json
"generatedAt": "2026-09-26T18:34:12Z"
```

Поле информационное.

---

# 5. generatorVersion

Версия Python-генератора:

```json
"generatorVersion": "0.4.0"
```

Использовать Semantic Versioning:

```text
MAJOR.MINOR.PATCH
```

---

# 6. Puzzle object

Минимальная задача:

```json
{
  "id": "extreme-000001",
  "puzzle": "000000000000000000000000000000000000000000000000000000000000000000000000000000000",
  "solution": "123456789456789123789123456214365897365897214897214365531642978642978531978531642",
  "clues": 18,
  "difficulty": "Extreme"
}
```

---

# 7. id

Обязательный уникальный идентификатор.

Тип:

```text
string
```

Пример:

```json
"id": "ultra-000042"
```

ID не должен изменяться после публикации задачи.

Не использовать индекс массива как постоянный ID.

---

# 8. puzzle

Строка длиной:

```text
81 символ
```

Каждый символ соответствует одной клетке:

```text
row-major order
```

Допустимые значения:

```text
0 = пустая клетка
1–9 = clue
```

Пример:

```json
"puzzle": "003000700..."
```

Индексация:

```text
0–8     row 1
9–17    row 2
...
72–80   row 9
```

Формула:

```text
index = row * 9 + column
```

---

# 9. solution

Полное корректное решение.

Строка длиной:

```text
81
```

Допустимы только:

```text
1–9
```

Нулей быть не должно.

Пример:

```json
"solution": "583241769..."
```

Каждая clue из `puzzle` должна совпадать с соответствующим символом `solution`.

---

# 10. clues

Количество исходных цифр.

Тип:

```text
integer
```

Пример:

```json
"clues": 18
```

Значение должно соответствовать количеству ненулевых символов в `puzzle`.

Для основной Extreme-базы ожидаемый диапазон:

```text
17–23
```

но формат не должен жёстко ограничивать другие значения.

---

# 11. difficulty

Допустимые значения:

```text
Easy
Medium
Hard
Expert
Extreme
Ultra Extreme
```

Пример:

```json
"difficulty": "Ultra Extreme"
```

Frontend не должен пытаться самостоятельно пересчитывать difficulty.

Источник истины:

```text
Python rating system
```

---

# 12. rating

Числовая оценка сложности.

```json
"rating": 9.4
```

Тип:

```text
number
```

Рейтинг определяется генератором.

Frontend использует его только для отображения и фильтрации.

---

# 13. minimal

Указывает, является ли puzzle minimal.

```json
"minimal": true
```

`true` означает:

> удаление любой оставшейся clue уничтожает уникальность решения.

Не путать с minimum-clue Sudoku.

---

# 14. unique

```json
"unique": true
```

Все публикуемые задачи должны иметь:

```text
unique = true
```

Поле оставляется в JSON для:

- диагностики;
- тестирования;
- верификации базы.

---

# 15. difficultyData

Расширенные данные рейтинга:

```json
"difficultyData": {
  "hardestRating": 9.4,
  "totalScore": 18422.8,
  "advancedSteps": 7,
  "trueBottlenecks": 4,
  "longestChain": 17
}
```

---

# 16. hardestRating

Рейтинг наиболее сложной обязательной техники.

```json
"hardestRating": 9.4
```

Это не обязательно совпадает с общим `rating`.

---

# 17. totalScore

Совокупная оценка полного logical solution path.

```json
"totalScore": 18422.8
```

Может использоваться генератором для сравнения задач одного уровня.

---

# 18. advancedSteps

Количество продвинутых логических шагов:

```json
"advancedSteps": 7
```

---

# 19. trueBottlenecks

Количество подтверждённых сложных bottleneck-состояний:

```json
"trueBottlenecks": 4
```

---

# 20. longestChain

Максимальная длина логической цепочки:

```json
"longestChain": 17
```

Если задача не использует цепочки:

```json
"longestChain": 0
```

---

# 21. hardestTechnique

Название самой сложной обязательной техники:

```json
"hardestTechnique": "Forcing Chain"
```

---

# 22. techniques

Статистика техник.

Рекомендуемый формат:

```json
"techniques": {
  "Naked Single": 14,
  "Hidden Single": 8,
  "Locked Candidates": 3,
  "X-Wing": 1,
  "XY-Wing": 2,
  "AIC": 3,
  "ALS-XZ": 1,
  "Forcing Chain": 1
}
```

Значение:

```text
technique name → количество использований
```

Не добавлять техники с нулевым количеством.

---

# 23. techniquesUsed

Для простого frontend-фильтра дополнительно допускается массив:

```json
"techniquesUsed": [
  "X-Wing",
  "XY-Wing",
  "AIC",
  "ALS-XZ",
  "Forcing Chain"
]
```

Он может быть автоматически сформирован из `techniques`.

---

# 24. solutionPath

Опционально.

Содержит последовательность логических шагов Human Solver.

Пример:

```json
"solutionPath": [
  {
    "step": 1,
    "technique": "Hidden Single",
    "rating": 1.0,
    "placements": [
      {
        "cell": "r4c7",
        "digit": 3
      }
    ],
    "eliminations": [],
    "explanation": "Digit 3 can only appear in r4c7 in row 4."
  }
]
```

---

# 25. step

Порядковый номер:

```json
"step": 17
```

Начинается с:

```text
1
```

---

# 26. technique

Название применённой техники:

```json
"technique": "AIC"
```

Названия должны совпадать с canonical names генератора.

---

# 27. rating внутри solutionPath

Рейтинг конкретного шага:

```json
"rating": 8.2
```

---

# 28. Cell notation

Для человекочитаемых ссылок использовать:

```text
r1c1
...
r9c9
```

Например:

```json
"cell": "r7c3"
```

Допускается дополнительно хранить индекс:

```json
"index": 56
```

но `index` не является обязательным.

---

# 29. placements

Массив установленных значений.

```json
"placements": [
  {
    "cell": "r7c3",
    "digit": 8
  }
]
```

---

# 30. eliminations

Удаления кандидатов:

```json
"eliminations": [
  {
    "cell": "r5c3",
    "digit": 7
  },
  {
    "cell": "r6c3",
    "digit": 7
  }
]
```

---

# 31. premises

Для сложных техник допускается:

```json
"premises": [
  {
    "cell": "r2c3",
    "digit": 4,
    "state": "strong"
  },
  {
    "cell": "r8c3",
    "digit": 4,
    "state": "weak"
  }
]
```

Это позволит в будущем визуализировать цепочки.

---

# 32. explanation

Краткое человекочитаемое объяснение:

```json
"explanation": "An AIC proves that candidate 4 can be eliminated from r7c3."
```

Не хранить здесь огромные тексты.

---

# 33. chain

Для chain-based техник допускается отдельная структура:

```json
"chain": {
  "length": 11,
  "nodes": [
    {
      "cell": "r2c3",
      "digit": 4,
      "link": "strong"
    },
    {
      "cell": "r2c8",
      "digit": 4,
      "link": "weak"
    }
  ]
}
```

Поле опционально.

---

# 34. tags

Дополнительные категории:

```json
"tags": [
  "minimal",
  "low-clue",
  "long-chain",
  "multiple-bottlenecks"
]
```

Используются только для:

- фильтрации;
- статистики;
- разработки.

Не являются частью рейтинга.

---

# 35. createdAt

Дата генерации конкретной задачи:

```json
"createdAt": "2026-09-26T17:54:11Z"
```

---

# 36. generatorSeed

Для воспроизводимости допускается:

```json
"generatorSeed": 762951301
```

Опционально.

---

# 37. sourceSolutionId

Если несколько puzzles создаются из одного complete solution:

```json
"sourceSolutionId": "solution-00128"
```

Используется для внутреннего анализа.

Frontend игнорирует это поле.

---

# 38. Полный рекомендуемый объект

```json
{
  "id": "ultra-000128",

  "puzzle": "000000000000000000000000000000000000000000000000000000000000000000000000000000000",
  "solution": "583241769241769583769583241825314697314697825697825314156438972438972156972156438",

  "clues": 18,

  "difficulty": "Ultra Extreme",
  "rating": 9.4,

  "unique": true,
  "minimal": true,

  "hardestTechnique": "Forcing Chain",

  "difficultyData": {
    "hardestRating": 9.4,
    "totalScore": 18422.8,
    "advancedSteps": 7,
    "trueBottlenecks": 4,
    "longestChain": 17
  },

  "techniques": {
    "Naked Single": 14,
    "Hidden Single": 8,
    "Locked Candidates": 3,
    "X-Wing": 1,
    "XY-Wing": 2,
    "AIC": 3,
    "ALS-XZ": 1,
    "Forcing Chain": 1
  },

  "techniquesUsed": [
    "X-Wing",
    "XY-Wing",
    "AIC",
    "ALS-XZ",
    "Forcing Chain"
  ],

  "tags": [
    "minimal",
    "low-clue",
    "long-chain",
    "multiple-bottlenecks"
  ],

  "createdAt": "2026-09-26T17:54:11Z",

  "generatorSeed": 762951301,

  "solutionPath": []
}
```

---

# 39. Обязательные поля

Минимально обязательны:

```text
id
puzzle
solution
clues
difficulty
unique
```

Рекомендуемые:

```text
rating
minimal
hardestTechnique
difficultyData
techniques
```

Опциональные:

```text
techniquesUsed
solutionPath
tags
generatorSeed
sourceSolutionId
createdAt
```

---

# 40. Валидация puzzle

При экспорте generator обязан проверить:

```text
len(puzzle) == 81
```

и:

```text
all(char in "0123456789")
```

---

# 41. Валидация solution

```text
len(solution) == 81
```

и:

```text
all(char in "123456789")
```

---

# 42. Проверка clues

```text
clues ==
count(character != "0" for character in puzzle)
```

---

# 43. Проверка соответствия solution

Для каждого индекса:

```text
если puzzle[i] != 0

то:

puzzle[i] == solution[i]
```

---

# 44. Проверка ID

Все:

```text
puzzle.id
```

должны быть уникальны в рамках файла.

---

# 45. Сортировка

Не полагаться на физический порядок элементов в `puzzles`.

Frontend должен фильтровать по полям.

Однако для удобства экспорт может сортировать:

```text
difficulty
rating descending
clues ascending
id
```

---

# 46. Числовая точность

Рейтинги хранить как обычные JSON numbers.

При отображении frontend может округлять:

```text
9.428193
→
9.4
```

Исходное значение желательно не терять.

---

# 47. Backward compatibility

Frontend должен игнорировать неизвестные дополнительные поля.

Например новая версия generator может добавить:

```json
"searchComplexity": 124.9
```

Старый frontend не должен из-за этого ломаться.

---

# 48. Не удалять поля без новой schemaVersion

Если поле использовалось frontend и удаляется или меняет смысл:

```text
schemaVersion
```

должна быть увеличена.

---

# 49. Большие solutionPath

`solutionPath` может существенно увеличить размер файла.

Поэтому допускаются два режима экспорта.

## Compact

```text
data/puzzles.json
```

без solution paths.

## Extended

```text
data/puzzles_extended.json
```

с полным logical solution.

---

# 50. Рекомендуемая структура в будущем

Если база станет большой:

```text
data/
    index.json

    easy/
        easy-000001.json

    extreme/
        extreme-000001.json

    ultra/
        ultra-000001.json
```

Но первая версия должна использовать простой:

```text
data/puzzles.json
```

---

# 51. Статистика базы

В корневом объекте допускается:

```json
"stats": {
  "total": 250,
  "byDifficulty": {
    "Easy": 20,
    "Medium": 20,
    "Hard": 30,
    "Expert": 50,
    "Extreme": 80,
    "Ultra Extreme": 50
  }
}
```

Это поле опционально и может рассчитываться при экспорте.

---

# 52. Пример полного файла

```json
{
  "schemaVersion": 1,

  "generatedAt": "2026-09-26T18:00:00Z",

  "generatorVersion": "0.1.0",

  "stats": {
    "total": 1,
    "byDifficulty": {
      "Ultra Extreme": 1
    }
  },

  "puzzles": [
    {
      "id": "ultra-000001",

      "puzzle": "000000000000000000000000000000000000000000000000000000000000000000000000000000000",

      "solution": "583241769241769583769583241825314697314697825697825314156438972438972156972156438",

      "clues": 18,

      "difficulty": "Ultra Extreme",

      "rating": 9.4,

      "unique": true,

      "minimal": true,

      "hardestTechnique": "Forcing Chain",

      "difficultyData": {
        "hardestRating": 9.4,
        "totalScore": 18422.8,
        "advancedSteps": 7,
        "trueBottlenecks": 4,
        "longestChain": 17
      },

      "techniques": {
        "Naked Single": 14,
        "Hidden Single": 8,
        "X-Wing": 1,
        "XY-Wing": 2,
        "AIC": 3,
        "ALS-XZ": 1,
        "Forcing Chain": 1
      }
    }
  ]
}
```

---

# 53. Источник истины

Правила:

```text
Generator
    отвечает за корректность Sudoku
    уникальность
    difficulty
    rating
    techniques

Frontend
    отвечает за отображение
    игровой прогресс
    ввод пользователя
    localStorage
```

Frontend не должен изменять или переоценивать результаты анализа generator.

---

# 54. Главный принцип формата

Формат должен позволять сделать простой frontend сегодня:

```text
puzzle + solution + difficulty
```

но не блокировать будущие возможности:

```text
логические подсказки
визуализация AIC
solution replay
анализ техники
статистика
сравнение сложности
```

Поэтому расширенные поля являются опциональными, а базовый контракт остаётся компактным и стабильным.

# 55. Phase 7 certified production dataset

Обратная совместимость сохраняется: `schemaVersion=1`, обязательные puzzle поля
не изменены. Текущий `data/puzzles.json` — demo/research collection Phase 5;
strict certification output располагается в `data/production/puzzles.json`.
Frontend автоматически на него не переключается.

Корень strict dataset добавляет `datasetKind: "production-certified"`.
Допустим пустой `puzzles: []`: это честный результат без прошедших кандидатов,
а не playable collection. На уровне каждого production puzzle обязательно
optional-for-legacy поле `certification`:

```json
{
  "status": "CERTIFIED_EXTREME",
  "version": "1",
  "requiredRating": 30,
  "requiredTier": "EXTREME",
  "searchConclusive": true,
  "proofValidated": true,
  "humanSolved": true,
  "reproducible": true,
  "genuineBottlenecks": 2,
  "configFingerprint": "<SHA-256>",
  "config": {},
  "evidence": {}
}
```

Это пример структуры, не действующий сертификат: реальные `config` и `evidence`
не пусты. `evidence` содержит полный CertificationResult: proof path,
threshold results с explicit statuses и limit reasons, bottleneck positions,
algorithm/config fingerprints, timings и причины отказа. LogicStep proof path
сериализуется dataclass-структурой в `certification.evidence.certified_path`;
его numeric cell indices не подменяют иллюстративный human-readable `solutionPath`
§24. Frontend игнорирует новое поле и не валидирует математический сертификат.

В production разрешены только `CERTIFIED_EXTREME` и
`CERTIFIED_ULTRA_EXTREME`. `rating` здесь равен certified minimum maximum step
rating, а не legacy composite fitness. `requiredRating` совпадает с ним.
`hardestTechnique` не экспортируется: доказательство уровня не означает
неизбежности конкретного названия техники. `techniques` описывает выбранный
сертифицированный путь. ID существующего кандидата сохраняется.

Strict exporter всегда запускает fresh certification, затем проверяет всю
сформированную запись, IDs, exact duplicates, solution consistency, uniqueness,
schema и metadata. Он повторно читает и проверяет JSON перед atomic replace;
после replace проверяет bytes назначения. Публичный
`validate_production_database` заново сертифицирует каждый record и сравнивает
evidence за исключением измеренных runtime полей. Обычный legacy
`validate_database` не подтверждает истинность certification metadata.

Research output имеет отдельный формат `researchVersion=1`: `config`,
`candidates: [{source, certification}]`, `stats`. Исходные preliminary labels,
failed и inconclusive results остаются здесь, без превращения в production.
Подробный нормативный контракт: [CERTIFICATION_SPEC.md](CERTIFICATION_SPEC.md).


# 56. Published (derived) database for GitHub Pages

`scripts/build_pages.mjs` writes `dist/data/production/puzzles.json` from `data/production/puzzles.json`. This file
is a **publish-only derivative**, never an input or output of the generator:

- root gets `derived: true` (the frontend ignores it; the schema is otherwise unchanged, `schemaVersion=1`);
- `certification.evidence` and `certification.config` are removed (the bulk of each record);
- `certification.hardestStep` `{technique, rating}` is added: the highest-rated step of
  `evidence.certified_path`. It describes the recorded path only, not a mandatory technique;
- all other fields (puzzle, solution, clues, rating, techniques, remaining certification fields) are unchanged.

Because the proof evidence is gone, a derived file **cannot** be checked by `validate_production_database` (it would
fail by design). Validate the source file `data/production/puzzles.json` (`python scripts/validate_production_database.py`);
the Pages workflow does that before building. Never commit `dist/` or copy the derived file back into `data/production/`.
