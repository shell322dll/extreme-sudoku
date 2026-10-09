import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { STRATEGIES } from '../lib/strategy-content.js';
import { diagramDescription, renderStrategyDiagram, renderStrategyCatalog, renderStrategyLesson } from '../lib/strategy-help.js';

test('catalog offers every lesson and separates general learning from the current puzzle', () => {
  const html = renderStrategyCatalog();
  for (const lesson of STRATEGIES) assert.ok(html.includes(`data-strategy-id="${lesson.id}"`));
  assert.match(html, /не анализирует вашу партию/);
  assert.match(html, /не добавляет подсказок/);
  assert.match(html, /Easy.*Лёгкий/);
  assert.match(html, /Notes.*Заметки/);
  assert.match(html, /lang="ru"/);
  assert.match(html, /id="strategy-keyboard"/);
});

test('all lesson stages have real diagrams, readable captions and working navigation bounds', () => {
  const before = JSON.stringify(STRATEGIES);
  for (const lesson of STRATEGIES) {
    for (let index = 0; index < lesson.steps.length; index++) {
      const html = renderStrategyLesson(lesson, index);
      assert.match(html, /<svg[^>]+role="img"[^>]+aria-labelledby=/);
      assert.match(html, /<figcaption>[^<]+<\/figcaption>/);
      assert.match(html, /id="strategy-step-heading" tabindex="-1"/);
      assert.match(html, /Текстовое описание схемы/);
      assert.match(html, /aria-controls="strategy-diagram-scroll"/);
      assert.equal(/id="strategy-previous"[^>]+disabled/.test(html), index === 0);
      assert.equal(html.includes('Готово · к списку'), index === lesson.steps.length - 1);
      if (lesson.steps[index].diagram.arrows?.some(arrow => arrow.from !== arrow.to)) assert.match(html, /class="strategy-arrow" marker-end="url\(#strategy-/);
    }
    assert.throws(() => renderStrategyLesson(lesson, lesson.steps.length), RangeError);
  }
  assert.equal(JSON.stringify(STRATEGIES), before, 'rendering must not mutate lesson snapshots');
});

test('diagram explains sparse digit-only views and encodes eliminations/placements without relying on color', () => {
  const diagram = { candidateMode: 'digit', digit: 7, caption: 'Показан только кандидат 7.',
    cells: [{ index: 0, candidates: [7], highlight: 'target' }, { index: 1, candidates: [] }, { index: 10, value: 7, highlight: 'result' }],
    arrows: [{ from: 0, to: 10, label: '7' }], eliminations: [{ cell: 0, digit: 7 }], placements: [{ cell: 10, digit: 7 }] };
  const text = diagramDescription(diagram);
  assert.match(text, /Показаны только кандидаты 7; остальные цифры скрыты/);
  assert.match(text, /строка 1, столбец 1: кандидаты 7; исключаем 7/);
  assert.match(text, /строка 1, столбец 2: кандидата 7 нет/);
  assert.match(text, /строка 2, столбец 2: цифра 7; найденная цифра 7/);
  const html = renderStrategyDiagram(diagram, 'demo');
  assert.match(html, /class="strategy-elimination"/);
  assert.match(html, /class="strategy-placement"/);
  assert.match(html, /Серые клетки не показаны/);
  assert.match(html, /id="demo-arrow"/);
  assert.match(html, /marker-end="url\(#demo-arrow\)"/);
});

test('lesson text is escaped and help module has no game or storage dependencies', async () => {
  const diagram = { caption: '<script>alert(1)</script>', cells: [], arrows: [] };
  const html = renderStrategyDiagram(diagram, 'test');
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('&lt;script&gt;'));
  const code = await readFile(new URL('../lib/strategy-help.js', import.meta.url), 'utf8');
  assert.doesNotMatch(code, /(?:localStorage|saveGame|loadSave|SudokuGame|\.\/game\.js|\.\/storage\.js)/);
});
