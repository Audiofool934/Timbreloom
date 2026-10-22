const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;

// Keep the time scale separate from the DOM so every timeline interaction uses
// the same bounds, including clicks after scrolling and pointer-anchored zoom.
export function timelineGeometry({ duration = 0, viewportWidth = 1, zoom = 1, scrollLeft = 0 } = {}) {
  duration = Math.max(0, finite(duration));
  viewportWidth = Math.max(1, finite(viewportWidth, 1));
  const maxZoom = duration > 0 ? Math.max(4, Math.min(1024, duration * 160 / viewportWidth)) : 1;
  zoom = clamp(finite(zoom, 1), 1, maxZoom);
  const contentWidth = viewportWidth * zoom;
  const maxScrollLeft = Math.max(0, contentWidth - viewportWidth);
  scrollLeft = clamp(finite(scrollLeft), 0, maxScrollLeft);
  const pixelsPerSecond = duration > 0 ? contentWidth / duration : 0;
  return {
    duration, viewportWidth, zoom, maxZoom, contentWidth, maxScrollLeft,
    scrollLeft, pixelsPerSecond,
    startTime: pixelsPerSecond ? scrollLeft / pixelsPerSecond : 0,
    endTime: pixelsPerSecond ? (scrollLeft + viewportWidth) / pixelsPerSecond : 0,
  };
}

export function timelineTimeAtX(geometry, viewportX) {
  if (!geometry.pixelsPerSecond) return 0;
  return clamp((geometry.scrollLeft + finite(viewportX)) / geometry.pixelsPerSecond, 0, geometry.duration);
}

export function timelineXAtTime(geometry, seconds) {
  return clamp(finite(seconds), 0, geometry.duration) * geometry.pixelsPerSecond - geometry.scrollLeft;
}

export function zoomTimeline(geometry, zoom, anchorX = geometry.viewportWidth / 2, anchorTime = null) {
  anchorX = clamp(finite(anchorX), 0, geometry.viewportWidth);
  const seconds = anchorTime === null
    ? timelineTimeAtX(geometry, anchorX)
    : clamp(finite(anchorTime), 0, geometry.duration);
  const next = timelineGeometry({ ...geometry, zoom });
  return timelineGeometry({ ...next, scrollLeft: seconds * next.pixelsPerSecond - anchorX });
}

export function timelineRuler(geometry, minimumSpacing = 80) {
  if (!geometry.pixelsPerSecond) return { step: 1, ticks: [{ time: 0, x: 0 }] };
  const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
  let step = steps.find((value) => value * geometry.pixelsPerSecond >= minimumSpacing);
  if (!step) step = Math.ceil(minimumSpacing / geometry.pixelsPerSecond / 3600) * 3600;
  const firstIndex = Math.max(0, Math.floor(geometry.startTime / step));
  const lastIndex = Math.min(Math.floor(geometry.duration / step), Math.ceil(geometry.endTime / step));
  const ticks = [];
  for (let index = firstIndex; index <= lastIndex; index += 1) {
    const time = Number((index * step).toFixed(3));
    ticks.push({ time, x: time * geometry.pixelsPerSecond });
  }
  return { step, ticks };
}

export function formatTimelineTime(seconds, fractional = false) {
  const tenths = Math.max(0, Math.round(finite(seconds) * 10));
  const totalSeconds = Math.floor(tenths / 10);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const second = String(totalSeconds % 60).padStart(2, "0");
  const main = hours ? `${hours}:${String(minutes).padStart(2, "0")}:${second}` : `${minutes}:${second}`;
  return fractional ? `${main}.${tenths % 10}` : main;
}
