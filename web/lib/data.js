export const DIFFICULTIES = Object.freeze(['Easy', 'Medium', 'Hard', 'Expert', 'Extreme', 'Ultra Extreme']);

/** Validate the exchange format and completed grid; never solve or re-rate a puzzle. */
export function isValidPuzzle(puzzle) {
  if (!puzzle || typeof puzzle.id !== 'string' || !puzzle.id.trim() ||
    typeof puzzle.puzzle !== 'string' || !/^[0-9]{81}$/.test(puzzle.puzzle) ||
    typeof puzzle.solution !== 'string' || !/^[1-9]{81}$/.test(puzzle.solution) ||
    !DIFFICULTIES.includes(puzzle.difficulty) || puzzle.unique !== true ||
    puzzle.clues !== [...puzzle.puzzle].filter(value => value !== '0').length ||
    [...puzzle.puzzle].some((value, index) => value !== '0' && value !== puzzle.solution[index])) return false;
  for (let unit = 0; unit < 9; unit++) {
    const row = [], column = [], box = [];
    for (let offset = 0; offset < 9; offset++) {
      row.push(puzzle.solution[unit * 9 + offset]);
      column.push(puzzle.solution[offset * 9 + unit]);
      box.push(puzzle.solution[(Math.floor(unit / 3) * 3 + Math.floor(offset / 3)) * 9 + (unit % 3) * 3 + offset % 3]);
    }
    if ([row, column, box].some(values => new Set(values).size !== 9)) return false;
  }
  return true;
}

export function parseDatabase(database, warn = console.warn) {
  if (!database || database.schemaVersion !== 1) throw new Error('Unsupported puzzle database version.');
  if (!Array.isArray(database.puzzles)) throw new Error('Invalid puzzle database.');
  const ids = new Set(), valid = [];
  for (const puzzle of database.puzzles) {
    if (!isValidPuzzle(puzzle) || ids.has(puzzle.id)) {
      warn('Skipping invalid or duplicate puzzle:', puzzle?.id ?? '(missing ID)');
      continue;
    }
    ids.add(puzzle.id);
    valid.push(puzzle);
  }
  if (valid.length === 0) throw new Error('The database has no playable puzzles.');
  return valid;
}

export const PRODUCTION_DATASET_KIND = 'production-certified';
/** Extreme certification statuses. Standard verification never grants one of these labels. */
export const CERTIFIED_STATUSES = Object.freeze({
  CERTIFIED_EXTREME: { difficulty: 'Extreme', label: 'Certified Extreme' },
  CERTIFIED_ULTRA_EXTREME: { difficulty: 'Ultra Extreme', label: 'Certified Ultra Extreme' },
});

const isRecord = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);

/** Label for a certified puzzle's badge, or null when the record is not certified. */
export const certificationLabel = (puzzle) => CERTIFIED_STATUSES[puzzle?.certification?.status]?.label ?? null;

/**
 * Hardest step of the certified solution path. The exporter does not publish a "hardest technique"
 * because a level proof does not make one named technique mandatory, so this describes the recorded path only.
 * Uses the compact `hardestStep` written by the Pages build, else the full proof path when present.
 */
export function hardestStep(certification) {
  const compact = certification?.hardestStep;
  if (isRecord(compact) && typeof compact.technique === 'string' && Number.isFinite(compact.rating)) {
    return { technique: compact.technique, rating: compact.rating };
  }
  const path = certification?.evidence?.certified_path;
  if (!Array.isArray(path)) return null;
  let best = null;
  for (const step of path) {
    if (isRecord(step) && typeof step.technique === 'string' && Number.isFinite(step.rating) && (!best || step.rating > best.rating)) {
      best = { technique: step.technique, rating: step.rating };
    }
  }
  return best;
}

/** A production puzzle must be structurally valid AND carry a consistent, certified status. */
export function isCertifiedPuzzle(puzzle) {
  if (!isValidPuzzle(puzzle) || !isRecord(puzzle.certification)) return false;
  const status = CERTIFIED_STATUSES[puzzle.certification.status];
  return Boolean(status) && status.difficulty === puzzle.difficulty;
}

/** Cheap structural admission only; Python independently verifies the logical evidence before publication. */
export function isVerifiedStandardPuzzle(puzzle) {
  if (!isValidPuzzle(puzzle) || puzzle.clues === 81 || puzzle.certification != null || !isRecord(puzzle.verification)) return false;
  const v = puzzle.verification;
  // Expert has no category ceiling below Extreme: Python confirms its fresh
  // classification, including Extreme's additional path requirements.
  const band = { Easy: [0, 2, 1.2], Medium: [2, 7, 5.2], Hard: [7, 12, 11], Expert: [12, Infinity, 55] }[puzzle.difficulty];
  return Boolean(band) && v.status === 'VERIFIED' && v.version === 1 &&
    v.method === 'DETERMINISTIC_THRESHOLD_REPLAY' && v.difficulty === puzzle.difficulty &&
    Number.isFinite(v.requiredRating) && v.requiredRating >= band[0] && v.requiredRating < band[1] &&
    v.techniqueCeiling === band[2] && v.requiredRating <= v.techniqueCeiling &&
    v.humanSolved === true && v.proofValidated === true && v.reproducible === true && v.unique === true &&
    v.guesses === 0 && v.usedBacktracking === false &&
    Number.isFinite(puzzle.rating) && puzzle.rating >= 0 &&
    puzzle.difficultyData?.hardestRating === v.requiredRating &&
    typeof puzzle.hardestTechnique === 'string' && puzzle.hardestTechnique.length > 0 &&
    Number.isInteger(puzzle.solutionSteps) && puzzle.solutionSteps > 0;
}

export const isProductionPuzzle = (puzzle) => isCertifiedPuzzle(puzzle) || isVerifiedStandardPuzzle(puzzle);

/**
 * Parse a production database. Unlike parseDatabase it never throws for an empty/all-invalid list:
 * the caller shows "no verified puzzles". It throws only for an unusable file (wrong schema or kind).
 */
export function parseProductionDatabase(database, warn = console.warn) {
  if (!isRecord(database)) throw new Error('Invalid puzzle database.');
  if (database.schemaVersion !== 1) throw new Error(`Unsupported puzzle database schemaVersion: ${String(database.schemaVersion)}.`);
  if (database.datasetKind !== PRODUCTION_DATASET_KIND) throw new Error(`Not a production database (datasetKind: ${String(database.datasetKind)}).`);
  if (!Array.isArray(database.puzzles)) throw new Error('Invalid puzzle database.');
  const ids = new Set(), valid = [];
  for (const puzzle of database.puzzles) {
    if (!isProductionPuzzle(puzzle) || ids.has(puzzle.id)) {
      warn('Skipping invalid, unverified or duplicate puzzle:', puzzle?.id ?? '(missing ID)', puzzle?.certification?.status ?? puzzle?.verification?.status ?? '(no verification)');
      continue;
    }
    ids.add(puzzle.id);
    valid.push(puzzle);
  }
  return valid;
}

/**
 * Drop proof evidence/config (the bulk of each record) for publishing; keep everything the UI shows.
 * Used by scripts/build_pages.mjs, so the published file is derived, never hand-maintained.
 */
export function slimDatabase(database) {
  return {
    ...database,
    // Marks a publish-only derivative: NOT valid input for validate_production_database (proof evidence is gone).
    derived: true,
    puzzles: database.puzzles.map((puzzle) => {
      if (isRecord(puzzle.verification)) {
        const { evidence, ...verification } = puzzle.verification;
        return { ...puzzle, verification };
      }
      if (!isRecord(puzzle.certification)) return puzzle;
      const { evidence, config, ...rest } = puzzle.certification;
      const step = hardestStep(puzzle.certification);
      return { ...puzzle, certification: step ? { ...rest, hardestStep: step } : rest };
    }),
  };
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Unable to load puzzle database (${response.status}).`);
  return response.json();
}

/** Generic loader (collections used by tests/fixtures). The app uses loadProductionPuzzles. */
export async function loadPuzzles(url = new URL('../data/puzzles.json', document.baseURI)) {
  return parseDatabase(await fetchJson(url));
}

/** Load the verified production database from an explicit URL; there is no default and no fallback. */
export async function loadProductionPuzzles(url, warn = console.warn) {
  return parseProductionDatabase(await fetchJson(url), warn);
}
