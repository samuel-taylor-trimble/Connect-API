/** Pure helpers for the Trimble Connect video extension. */

export const VIDEO_EXTENSIONS = new Set(["mp4", "m4v", "webm", "ogg", "ogv", "mov"]);

const FALLBACK_TC_API = {
  northamerica: "https://app.connect.trimble.com/tc/api/2.0",
  us: "https://app.connect.trimble.com/tc/api/2.0",
  europe: "https://app21.connect.trimble.com/tc/api/2.0",
  eu: "https://app21.connect.trimble.com/tc/api/2.0",
  uk: "https://app22.connect.trimble.com/tc/api/2.0",
  "eu-gb": "https://app22.connect.trimble.com/tc/api/2.0",
  asia: "https://app31.connect.trimble.com/tc/api/2.0",
  ap: "https://app31.connect.trimble.com/tc/api/2.0",
  "ap-au": "https://app32.connect.trimble.com/tc/api/2.0",
};

export function isVideoName(name) {
  const extension = String(name || "").split(".").pop()?.toLowerCase() || "";
  return VIDEO_EXTENSIONS.has(extension) && String(name).includes(".");
}

export function videoMimeType(name) {
  const extension = String(name || "").split(".").pop()?.toLowerCase();
  if (extension === "webm") return "video/webm";
  if (extension === "ogg" || extension === "ogv") return "video/ogg";
  if (extension === "mov") return "video/quicktime";
  return "video/mp4";
}

export function normalizeTcApi(raw) {
  const url = String(raw || "").trim().replace(/\/$/, "");
  if (!url) {
    throw new Error("Trimble Connect region did not include a tc-api URL.");
  }
  if (url.endsWith("/tc/api/2.0")) return url;
  if (url.endsWith("/tc/api")) return `${url}/2.0`;
  return `${url}/tc/api/2.0`;
}

export function resolveTcApiBase(regions, location) {
  const wanted = String(location || "").trim().toLowerCase();
  const list = Array.isArray(regions) ? regions : [];
  const match = list.find((region) => regionKey(region) === wanted);
  if (match?.["tc-api"]) return normalizeTcApi(match["tc-api"]);
  if (FALLBACK_TC_API[wanted]) return FALLBACK_TC_API[wanted];
  const master = list.find((region) => region?.isMaster && region["tc-api"]);
  if (!wanted && master) return normalizeTcApi(master["tc-api"]);
  throw new Error(`No Trimble Connect file API is published for project location "${location || ""}".`);
}

export function parseContentRange(header) {
  const match = /^items\s+(\d+)-(\d+)\/(\d+|\*)$/i.exec(String(header || "").trim());
  if (!match) return null;
  return {
    start: Number(match[1]),
    end: Number(match[2]),
    total: match[3] === "*" ? null : Number(match[3]),
  };
}

export function nextPageStart(contentRange, batchLength, requestedStart, pageSize) {
  if (!batchLength) return null;
  if (contentRange?.total != null) {
    const next = contentRange.end + 1;
    return next >= contentRange.total ? null : next;
  }
  if (batchLength < pageSize) return null;
  return requestedStart + batchLength;
}

export async function collectVideos(rootId, listItems) {
  const videos = [];
  const seen = new Set();

  async function walk(folderId, prefix) {
    if (!folderId || seen.has(folderId)) return;
    seen.add(folderId);
    const items = await listItems(folderId);
    for (const item of items) {
      if (item?.type === "FOLDER") {
        await walk(item.id, `${prefix}${item.name}/`);
      } else if (item?.type === "FILE" && isVideoName(item.name)) {
        videos.push({
          id: item.id,
          name: item.name,
          path: `${prefix}${item.name}`,
          size: item.size,
          versionId: item.versionId,
        });
      }
    }
  }

  await walk(rootId, "");
  videos.sort((left, right) => left.path.localeCompare(right.path));
  return videos;
}

function regionKey(region) {
  return String(region?.location || region?.region || region?.trnRegion || "").trim().toLowerCase();
}
