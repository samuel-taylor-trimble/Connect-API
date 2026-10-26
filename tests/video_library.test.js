import assert from "node:assert/strict";
import test from "node:test";

import {
  collectVideos,
  isVideoName,
  nextPageStart,
  normalizeTcApi,
  parseContentRange,
  resolveTcApiBase,
  videoMimeType,
} from "../extension/video_library.js";

test("recognizes browser video names and ignores other files", () => {
  assert.equal(isVideoName("Site Walk.MP4"), true);
  assert.equal(isVideoName("clip.webm"), true);
  assert.equal(isVideoName("notes.pdf"), false);
  assert.equal(isVideoName("mp4"), false);
  assert.equal(videoMimeType("clip.webm"), "video/webm");
  assert.equal(videoMimeType("take.mov"), "video/quicktime");
});

test("uses the regional tc-api and falls back to the published hosts", () => {
  assert.equal(normalizeTcApi("https://app.connect.trimble.com"), "https://app.connect.trimble.com/tc/api/2.0");
  assert.equal(
    resolveTcApiBase(
      [{ location: "europe", "tc-api": "https://app21.connect.trimble.com/tc/api/2.0" }],
      "Europe",
    ),
    "https://app21.connect.trimble.com/tc/api/2.0",
  );
  assert.equal(
    resolveTcApiBase([], "northAmerica"),
    "https://app.connect.trimble.com/tc/api/2.0",
  );
  assert.throws(() => resolveTcApiBase([], "unknown-region"), /unknown-region/);
});

test("pages folder items with Content-Range", () => {
  assert.deepEqual(parseContentRange("items 0-99/240"), { start: 0, end: 99, total: 240 });
  assert.equal(nextPageStart({ start: 0, end: 99, total: 240 }, 100, 0, 100), 100);
  assert.equal(nextPageStart({ start: 200, end: 239, total: 240 }, 40, 200, 100), null);
  assert.equal(nextPageStart(null, 20, 0, 100), null);
});

test("collects nested videos and skips folders already seen", async () => {
  const tree = {
    root: [
      { id: "folder-a", name: "Field", type: "FOLDER" },
      { id: "doc", name: "spec.pdf", type: "FILE" },
    ],
    "folder-a": [
      { id: "vid", name: "walk.mp4", type: "FILE", size: 10, versionId: "v1" },
      { id: "root", name: "loop", type: "FOLDER" },
    ],
  };
  const videos = await collectVideos("root", async (folderId) => tree[folderId] || []);
  assert.deepEqual(videos, [
    { id: "vid", name: "walk.mp4", path: "Field/walk.mp4", size: 10, versionId: "v1" },
  ]);
});
