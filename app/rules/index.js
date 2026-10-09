/**
 * Track B — Rules component public API.
 * Catalog + schema + keyword compiler + demo evaluator.
 */

export {
  THRESHOLD_MIN,
  THRESHOLD_MAX,
  SOURCE_MODES,
  normalizeThreshold,
  thresholdInRange,
  validateRule,
  createRule,
  createEvidenceEvent,
} from './schema.js';

export {
  modules,
  cameras,
  listModules,
  getModule,
  getCamera,
  cameraForModule,
  compatible,
  supportedCapabilitySummary,
} from './catalog.js';

export {
  compileRequirement,
  compileRequirementAsync,
  interpret,
  applyThreshold,
} from './compiler.js';

export {
  compileRemote,
  normalizeWorkshopCompile,
  WORKSHOP_TO_DEMO,
} from './remote.js';

export { evaluate, evidenceKey } from './evaluator.js';
