/** Standalone illustrated lessons. This module has no game, storage or solver access. */
import { STRATEGIES, STRATEGY_INTRO } from './strategy-content.js';

const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
const position = index => ({ row: Math.floor(index / 9), column: index % 9 });
const coordinate = index => { const { row, column } = position(index); return `строка ${row + 1}, столбец ${column + 1}`; };
const CELL = 40, MARGIN = 24, BOARD = CELL * 9;
const origin = index => { const { row, column } = position(index); return { x: MARGIN + column * CELL, y: MARGIN + row * CELL }; };
const center = index => { const { x, y } = origin(index); return { x: x + CELL / 2, y: y + CELL / 2 }; };
const candidatePoint = (index, digit) => {
  const { x, y } = origin(index);
  return { x: x + (2 * ((digit - 1) % 3) + 1) * CELL / 6, y: y + (2 * Math.floor((digit - 1) / 3) + 1) * CELL / 6 };
};
const textParagraphs = value => (Array.isArray(value) ? value : [value]).filter(Boolean).map(text => `<p>${escape(text)}</p>`).join('');

export function diagramDescription(diagram) {
  const descriptions = (diagram.cells ?? []).map(cell => {
    let content = cell.value ? `цифра ${cell.value}` : cell.candidates?.length ? `кандидаты ${cell.candidates.join(', ')}` : diagram.candidateMode === 'digit' ? `кандидата ${diagram.digit} нет` : 'рассматриваемая клетка';
    const removed = (diagram.eliminations ?? []).filter(item => item.cell === cell.index).map(item => item.digit);
    const placed = (diagram.placements ?? []).find(item => item.cell === cell.index);
    if (removed.length) content += `; исключаем ${removed.join(', ')}`;
    if (placed) content += `; найденная цифра ${placed.digit}`;
    return `${coordinate(cell.index)}: ${content}`;
  });
  for (const arrow of diagram.arrows ?? []) descriptions.push(`Стрелка: ${coordinate(arrow.from)} → ${coordinate(arrow.to)}${arrow.label ? ` (${arrow.label})` : ''}`);
  return `${diagram.candidateMode === 'digit' ? `Показаны только кандидаты ${diagram.digit}; остальные цифры скрыты. ` : ''}${descriptions.join('. ')}.`;
}

export function renderStrategyDiagram(diagram, id = 'strategy-diagram') {
  const safeId = String(id).replace(/[^a-zA-Z0-9_-]/g, '-');
  const givenCells = new Map((diagram.cells ?? []).map(cell => [cell.index, cell]));
  let backgrounds = '', numbers = '';
  for (let index = 0; index < 81; index++) {
    const cell = givenCells.get(index);
    const { x, y } = origin(index);
    const highlight = ['focus', 'support', 'target', 'result'].includes(cell?.highlight) ? cell.highlight : '';
    backgrounds += `<rect x="${x}" y="${y}" width="${CELL}" height="${CELL}" class="strategy-cell ${cell ? 'shown' : 'omitted'} ${highlight}"/>`;
    if (!cell) continue;
    if (cell.value) numbers += `<text x="${x + CELL / 2}" y="${y + CELL / 2}" class="strategy-value">${escape(cell.value)}</text>`;
    else for (const digit of cell.candidates ?? []) {
      const point = candidatePoint(index, digit);
      const eliminated = (diagram.eliminations ?? []).some(item => item.cell === index && item.digit === digit);
      numbers += `<text x="${point.x}" y="${point.y}" class="strategy-candidate${eliminated ? ' eliminated' : ''}">${escape(digit)}</text>`;
      if (eliminated) numbers += `<path d="M${point.x - 5},${point.y - 5}l10,10m-10,0l10,-10" class="strategy-elimination"/>`;
    }
    if ((diagram.placements ?? []).some(item => item.cell === index)) numbers += `<circle cx="${x + CELL / 2}" cy="${y + CELL / 2}" r="16" class="strategy-placement"/>`;
  }
  const units = (diagram.units ?? []).map(unit => {
    const x = MARGIN + (unit.type === 'column' ? unit.index * CELL : unit.type === 'box' ? unit.index % 3 * CELL * 3 : 0);
    const y = MARGIN + (unit.type === 'row' ? unit.index * CELL : unit.type === 'box' ? Math.floor(unit.index / 3) * CELL * 3 : 0);
    const width = unit.type === 'row' ? BOARD : unit.type === 'box' ? 3 * CELL : CELL;
    const height = unit.type === 'column' ? BOARD : unit.type === 'box' ? 3 * CELL : CELL;
    return `<rect x="${x + 2}" y="${y + 2}" width="${width - 4}" height="${height - 4}" class="strategy-unit"/>`;
  }).join('');
  const lines = Array.from({ length: 10 }, (_, line) => {
    const offset = MARGIN + line * CELL;
    return `<path d="M${MARGIN},${offset}H${MARGIN + BOARD}M${offset},${MARGIN}V${MARGIN + BOARD}" class="strategy-grid-line${line % 3 === 0 ? ' major' : ''}"/>`;
  }).join('');
  const arrows = (diagram.arrows ?? []).map(arrow => {
    if (arrow.from === arrow.to) return '';
    const from = center(arrow.from), to = center(arrow.to);
    const distance = Math.hypot(to.x - from.x, to.y - from.y);
    const dx = (to.x - from.x) / distance, dy = (to.y - from.y) / distance;
    const mid = { x: (from.x + to.x) / 2 - dy * 12, y: (from.y + to.y) / 2 + dx * 12 };
    return `<path d="M${from.x + dx * 13},${from.y + dy * 13}Q${mid.x},${mid.y} ${to.x - dx * 14},${to.y - dy * 14}" class="strategy-arrow" marker-end="url(#${safeId}-arrow)"/>${arrow.label ? `<text x="${mid.x}" y="${mid.y - 7}" class="strategy-arrow-label">${escape(arrow.label)}</text>` : ''}`;
  }).join('');
  const axes = Array.from({ length: 9 }, (_, index) => `<text x="${MARGIN + (index + .5) * CELL}" y="12" class="strategy-axis">${index + 1}</text><text x="12" y="${MARGIN + (index + .5) * CELL}" class="strategy-axis">${index + 1}</text>`).join('');
  return `<svg class="strategy-diagram" viewBox="0 0 ${BOARD + MARGIN * 2} ${BOARD + MARGIN * 2}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="${safeId}-title ${safeId}-description"><title id="${safeId}-title">Учебная схема</title><desc id="${safeId}-description">${escape(diagram.caption)} ${escape(diagramDescription(diagram))} Серые клетки не показаны; это не пустые клетки текущей партии.</desc><defs><marker id="${safeId}-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" class="strategy-arrowhead"/></marker></defs><g aria-hidden="true">${backgrounds}${lines}${units}${arrows}${numbers}${axes}</g></svg>`;
}

export function renderStrategyCatalog() {
  return `<div class="strategy-help" lang="ru"><p class="strategy-introduction">Разбирайтесь в логике шаг за шагом. Это учебные примеры: справка не анализирует вашу партию, не раскрывает её цифры и не добавляет подсказок.</p><p class="strategy-pause-note">Открытая партия на паузе. Когда закончите читать, закройте окно и нажмите «Resume game» на игровом поле.</p><section class="strategy-intro"><h3>${escape(STRATEGY_INTRO.title)}</h3>${textParagraphs(STRATEGY_INTRO.text)}<p>Если вы только начинаете, выберите Easy («Лёгкий»). Кнопка Notes («Заметки») помогает записывать возможные цифры в клетке.</p>${STRATEGY_INTRO.legend?.length ? `<ul>${STRATEGY_INTRO.legend.map(text => `<li>${escape(text)}</li>`).join('')}</ul>` : ''}</section><h3 id="strategy-catalog-heading" tabindex="-1">Способы решения</h3><p class="small-print">Начните сверху: сначала простые шаги, затем комбинации кандидатов.</p><ol class="strategy-catalog">${STRATEGIES.map((lesson, index) => `<li><button class="strategy-choice" data-strategy-id="${escape(lesson.id)}"><span class="strategy-order" aria-hidden="true">${index + 1}</span><span><strong>${escape(lesson.title)}</strong><small>${escape(lesson.level)}${lesson.term ? ` · ${escape(lesson.term)}` : ''}</small></span><span aria-hidden="true">→</span></button></li>`).join('')}</ol><button id="strategy-keyboard" class="secondary">Управление и клавиатура</button></div>`;
}

export function renderStrategyLesson(lesson, stepIndex = 0) {
  const step = lesson.steps[stepIndex];
  if (!step) throw new RangeError('Unknown strategy step');
  const last = stepIndex === lesson.steps.length - 1;
  const sourceLinks = (lesson.sources ?? []).filter(source => /^https:\/\//.test(source.url)).map(source => `<a href="${escape(source.url)}" target="_blank" rel="noopener noreferrer">${escape(source.title)}</a>`).join(' · ');
  return `<article class="strategy-help strategy-lesson" lang="ru"><button id="strategy-back" class="secondary">← К списку способов</button><p class="strategy-level">${escape(lesson.level)}${lesson.term ? ` · ${escape(lesson.term)}` : ''}</p><section class="strategy-when"><h3>Когда применять</h3>${textParagraphs(lesson.when)}</section><div class="strategy-stage"><p id="strategy-step-count" class="eyebrow">Шаг ${stepIndex + 1} из ${lesson.steps.length}</p><h3 id="strategy-step-heading" tabindex="-1">${escape(step.title)}</h3>${textParagraphs(step.text)}<figure class="strategy-figure"><div class="strategy-figure-tools"><span>Учебный пример</span><button id="strategy-zoom" class="text-button" aria-pressed="false" aria-controls="strategy-diagram-scroll">Увеличить схему</button></div><div id="strategy-diagram-scroll" class="strategy-diagram-scroll" role="region" aria-label="Схема шага" tabindex="0">${renderStrategyDiagram(step.diagram, `strategy-${lesson.id}-${stepIndex}`)}</div><figcaption>${escape(step.diagram.caption)}</figcaption></figure><p class="strategy-legend small-print">Серые клетки — не показаны. Рамки выделяют клетки и группы; стрелки показывают связь. Крестик исключает кандидата, круг отмечает найденную цифру.</p><details class="strategy-text-description"><summary>Текстовое описание схемы</summary><p>${escape(diagramDescription(step.diagram))}</p></details><div class="strategy-step-buttons"><button id="strategy-previous" class="secondary" ${stepIndex === 0 ? 'disabled' : ''}>← Предыдущий шаг</button><button id="strategy-next" class="primary">${last ? 'Готово · к списку' : 'Следующий шаг →'}</button></div></div><section class="strategy-reason"><h3>Почему это работает</h3>${textParagraphs(lesson.why)}</section>${lesson.mistake ? `<section class="strategy-mistake"><h3>Частая ошибка</h3>${textParagraphs(lesson.mistake)}</section>` : ''}${sourceLinks ? `<p class="strategy-sources small-print">Подробнее о методе: ${sourceLinks}</p>` : ''}<p class="small-print">Партия остаётся на паузе. Закройте справку и продолжите игру, когда будете готовы.</p></article>`;
}

/** Bind navigation inside the existing modal; never owns or mutates Sudoku state. */
export function openStrategyLibrary({ root, show, onKeyboard }) {
  const catalog = (focusId = null) => {
    show('Помощь: как решать судоку', renderStrategyCatalog());
    for (const button of root.querySelectorAll('[data-strategy-id]')) button.addEventListener('click', () => {
      const lesson = STRATEGIES.find(item => item.id === button.dataset.strategyId);
      if (lesson) lessonPage(lesson, 0);
    });
    root.querySelector('#strategy-keyboard').addEventListener('click', () => onKeyboard(() => catalog()));
    if (focusId) [...root.querySelectorAll('[data-strategy-id]')].find(button => button.dataset.strategyId === focusId)?.focus({ preventScroll: true });
  };
  const lessonPage = (lesson, index) => {
    show(lesson.title, renderStrategyLesson(lesson, index));
    root.querySelector('#strategy-back').addEventListener('click', () => catalog(lesson.id));
    root.querySelector('#strategy-previous').addEventListener('click', () => { if (index > 0) lessonPage(lesson, index - 1); });
    root.querySelector('#strategy-next').addEventListener('click', () => index + 1 < lesson.steps.length ? lessonPage(lesson, index + 1) : catalog(lesson.id));
    root.querySelector('#strategy-zoom').addEventListener('click', event => {
      const zoomed = event.currentTarget.getAttribute('aria-pressed') !== 'true';
      event.currentTarget.setAttribute('aria-pressed', String(zoomed));
      event.currentTarget.textContent = zoomed ? 'Уменьшить схему' : 'Увеличить схему';
      root.querySelector('#strategy-diagram-scroll').classList.toggle('zoomed', zoomed);
    });
    root.querySelector('#strategy-step-heading').focus({ preventScroll: true });
  };
  catalog();
}
