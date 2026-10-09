/**
 * Allowlisted preset modules and demo camera/clip mappings.
 * New capabilities must be added here before the compiler can emit them.
 */

export const modules = Object.freeze({
  zone: Object.freeze({
    name: 'Walkway watch',
    icon: 'route',
    description: 'Flag time spent outside the designated pedestrian route.',
    camera: 'corridor',
    unit: 'seconds',
    defaultThreshold: 2,
    keywords: Object.freeze(['walk', 'zone', 'restricted', 'pedestrian', 'lane', 'perimeter']),
    examples: Object.freeze(['Keep people on the walkway', 'Alert outside the walkway for 3 seconds']),
  }),
  load: Object.freeze({
    name: 'Load visibility',
    icon: 'layers',
    description: 'Review a tall stack that may obstruct the operator’s view.',
    camera: 'loading',
    unit: 'seconds',
    defaultThreshold: 1,
    keywords: Object.freeze(['forklift', 'load', 'stack', 'operator', 'visibility']),
    examples: Object.freeze(['Flag tall forklift loads', 'Watch operator visibility for 1 second']),
  }),
  panel: Object.freeze({
    name: 'Panel watch',
    icon: 'shield',
    description: 'Flag a panel left visibly open.',
    camera: 'machine',
    unit: 'seconds',
    defaultThreshold: 2,
    keywords: Object.freeze(['panel', 'cabinet', 'cover']),
    examples: Object.freeze(['Watch for an open panel', 'Flag open panels for 2 seconds']),
  }),
});

export const cameras = Object.freeze([
  Object.freeze({
    id: 'corridor',
    name: 'Production walkway',
    location: 'Factory · Camera 01',
    file: '0_te21',
    reference: '4_te5',
    module: 'zone',
    duration: 10.477582,
    event: Object.freeze({
      start: 1,
      end: 8,
      title: 'Outside pedestrian route',
      detail:
        'Illustrative interval for the source walkway example. Review the video to verify the event.',
    }),
  }),
  Object.freeze({
    id: 'loading',
    name: 'Material handling',
    location: 'Factory · Camera 02',
    file: '3_te7',
    reference: '7_te3',
    module: 'load',
    duration: 4,
    event: Object.freeze({
      start: 0.2,
      end: 3.7,
      title: 'Tall load · review visibility',
      detail:
        'Source example contains a tall stack. This does not establish load weight or a collision risk.',
    }),
  }),
  Object.freeze({
    id: 'machine',
    name: 'Machine floor',
    location: 'Factory · Camera 03',
    file: '2_te12',
    reference: '6_te12',
    module: 'panel',
    duration: 10.4,
    event: Object.freeze({
      start: 0.5,
      end: 9,
      title: 'Panel state · review required',
      detail:
        'Illustrative interval based on the publisher’s open-panel category. Confirm the specific panel in the footage.',
    }),
  }),
]);

export function listModules() {
  return Object.keys(modules).map((id) => ({ id, ...modules[id] }));
}

export function getModule(id) {
  return modules[id] || null;
}

export function getCamera(id) {
  return cameras.find((c) => c.id === id) || null;
}

export function cameraForModule(moduleId) {
  return cameras.find((c) => c.module === moduleId) || null;
}

export function compatible(camera, rule) {
  return Boolean(camera && rule && camera.module === rule.module);
}

export function supportedCapabilitySummary() {
  return 'This demo supports walkway rules, tall-load review, and panel state.';
}
