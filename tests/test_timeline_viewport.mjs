import assert from "node:assert/strict";
import { test } from "node:test";
import {
  timelineGeometry, timelineTimeAtX, timelineXAtTime, zoomTimeline,
  timelineRuler, formatTimelineTime,
} from "../static/timeline-viewport.js";

test("time mapping includes scroll and remains invertible after zoom", () => {
  const view = timelineGeometry({ duration: 120, viewportWidth: 600, zoom: 4, scrollLeft: 900 });
  assert.equal(view.startTime, 45);
  assert.equal(view.endTime, 75);
  assert.equal(timelineTimeAtX(view, 300), 60);
  for (const time of [45, 48.125, 60, 75]) {
    assert.ok(Math.abs(timelineTimeAtX(view, timelineXAtTime(view, time)) - time) < 1e-9);
  }
  assert.equal(timelineTimeAtX(view, -10000), 0);
  assert.equal(timelineTimeAtX(view, 10000), 120);
});

test("zoom keeps the pointer time at the same screen position", () => {
  const initial = timelineGeometry({ duration: 120, viewportWidth: 600, zoom: 2, scrollLeft: 300 });
  const time = timelineTimeAtX(initial, 150);
  const zoomed = zoomTimeline(initial, 5, 150);
  assert.equal(timelineTimeAtX(zoomed, 150), time);
  const restored = zoomTimeline(zoomed, 2, 150);
  assert.equal(restored.scrollLeft, initial.scrollLeft);
});

test("zoom at an explicit playhead and fit never change the playhead time", () => {
  const initial = timelineGeometry({ duration: 80, viewportWidth: 800 });
  const playhead = 48.25;
  const anchor = timelineXAtTime(initial, playhead);
  const zoomed = zoomTimeline(initial, 8, anchor, playhead);
  assert.equal(timelineXAtTime(zoomed, playhead), anchor);
  const fit = zoomTimeline(zoomed, 1, anchor, playhead);
  assert.equal(fit.scrollLeft, 0);
  assert.equal(fit.contentWidth, 800);
  assert.equal(timelineTimeAtX(fit, timelineXAtTime(fit, playhead)), playhead);
});

test("edge zoom and invalid inputs keep geometry inside the recording", () => {
  const view = timelineGeometry({ duration: 10, viewportWidth: 500, zoom: 10000, scrollLeft: Infinity });
  assert.equal(view.maxZoom, 4);
  assert.equal(view.zoom, 4);
  assert.equal(view.scrollLeft, 0);
  const end = timelineGeometry({ ...view, scrollLeft: 10000 });
  assert.equal(end.endTime, 10);
  const out = zoomTimeline(end, 0.5, 500);
  assert.equal(out.zoom, 1);
  assert.equal(out.scrollLeft, 0);
  const empty = timelineGeometry({ duration: NaN, viewportWidth: 0, zoom: NaN });
  assert.equal(timelineTimeAtX(empty, 400), 0);
  assert.equal(empty.contentWidth, 1);
  assert.equal(empty.maxZoom, 1);
  assert.equal(timelineGeometry({ duration: 0.5, viewportWidth: 800, zoom: 4 }).zoom, 4);
});

test("ruler ticks remain readable at long and sub-second scales", () => {
  for (const duration of [2, 120, 7200, 86400]) {
    for (const zoom of [1, 4, 1024]) {
      const view = timelineGeometry({ duration, viewportWidth: 800, zoom, scrollLeft: 500 });
      const ruler = timelineRuler(view);
      assert.ok(ruler.step * view.pixelsPerSecond >= 80);
      assert.ok(ruler.ticks.length <= 13);
      for (const tick of ruler.ticks) {
        assert.ok(tick.time >= 0 && tick.time <= duration);
        assert.ok(Math.abs(tick.x - tick.time * view.pixelsPerSecond) < 1e-8);
      }
    }
  }
  assert.equal(formatTimelineTime(65), "1:05");
  assert.equal(formatTimelineTime(3665), "1:01:05");
  assert.equal(formatTimelineTime(0.5, true), "0:00.5");
  assert.equal(formatTimelineTime(59.99, true), "1:00.0");
});
