import {
  collectVideos,
  isVideoName,
  nextPageStart,
  parseContentRange,
  resolveTcApiBase,
  videoMimeType,
} from "./video_library.js";

const REGIONS_URL = "https://app.connect.trimble.com/tc/api/2.0/regions";
const PAGE_SIZE = 100;

const statusNode = document.querySelector("#status");
const projectNode = document.querySelector("#project-name");
const listNode = document.querySelector("#video-list");
const playerNode = document.querySelector("#player");
const nowPlaying = document.querySelector("#now-playing");
const refreshButton = document.querySelector("#refresh");
const setupNode = document.querySelector("#setup");

let api = null;
let accessToken = "";
let project = null;
let serviceBase = "";
let videos = [];

refreshButton.addEventListener("click", () => {
  loadVideos().catch((error) => setStatus(error.message));
});

playerNode.addEventListener("error", () => {
  setStatus("This browser could not play that video. The file is still stored in the project.");
});

if (hostedByTrimble()) {
  refreshButton.hidden = false;
  connectExtension().catch((error) => setStatus(error.message));
} else {
  showSetup();
}

function hostedByTrimble() {
  if (window.parent === window) return false;
  try {
    // A same-origin parent is this server, or a test browser framing the page.
    // Trimble Connect embeds the extension from another origin.
    void window.parent.location.origin;
    return false;
  } catch {
    return true;
  }
}

function showSetup() {
  setupNode.hidden = false;
  refreshButton.hidden = true;
  const manifest = new URL("manifest.json", window.location.href);
  setupNode.querySelector("[data-manifest]").textContent = manifest.href;
  setStatus("Add the extension to a project to play its videos.");
}

async function connectExtension() {
  setStatus("Connecting to Trimble Connect…");
  const workspace = window.TrimbleConnectWorkspace;
  if (!workspace?.connect) {
    throw new Error("The Trimble Connect Workspace API script did not load.");
  }
  api = await workspace.connect(window.parent, onWorkspaceEvent, 30000);
  try {
    await api.ui.setMenu({
      title: "Videos",
      icon: new URL("icon.svg", window.location.href).href,
      command: "videos",
    });
  } catch {
    // The project page can still host the panel if the menu call is rejected.
  }
  const permission = await api.extension.requestPermission("accesstoken");
  if (permission === "denied") {
    setStatus("Allow the Video viewer access token in the extension settings, then refresh.");
    return;
  }
  if (isAccessToken(permission)) {
    accessToken = permission;
    await loadVideos();
    return;
  }
  setStatus("Allow this extension to use your Trimble Connect session.");
}

function onWorkspaceEvent(eventName, args) {
  if (eventName === "extension.accessToken" || eventName === "extension.sessionInvalid") {
    const token = readToken(args);
    if (isAccessToken(token)) {
      accessToken = token;
      if (!videos.length) loadVideos().catch((error) => setStatus(error.message));
    }
    return;
  }
  if (eventName === "extension.fileSelected" || eventName === "extension.fileViewClicked") {
    const file = args?.data?.file;
    if (file && isVideoName(file.name)) {
      play({
        id: file.id,
        name: file.name,
        path: file.name,
        versionId: file.versionId,
      }).catch((error) => setStatus(error.message));
    }
  }
}

async function loadVideos() {
  if (!isAccessToken(accessToken)) {
    setStatus("Waiting for a Trimble Connect access token.");
    return;
  }
  setStatus("Reading project videos…");
  project = await api.project.getProject();
  projectNode.textContent = project?.name || "Project";
  serviceBase = await discoverServiceBase(project?.location);
  const details = await connectJson(`/projects/${encodeURIComponent(project.id)}`);
  if (!details.rootId) {
    throw new Error("The project response did not include a root folder.");
  }
  videos = await collectVideos(details.rootId, (folderId) => listFolder(folderId));
  renderList();
  setStatus(videos.length ? `${videos.length} video${videos.length === 1 ? "" : "s"}` : "No videos in this project.");
}

async function discoverServiceBase(location) {
  const response = await fetch(REGIONS_URL, { headers: authHeaders() });
  const regions = response.ok ? await response.json() : [];
  return resolveTcApiBase(regions, location);
}

async function listFolder(folderId) {
    const items = [];
    let start = 0;
    let refreshed = false;
    while (start < 10000) {
      const end = start + PAGE_SIZE - 1;
      const response = await fetch(
        `${serviceBase}/folders/${encodeURIComponent(folderId)}/items`,
        { headers: { ...authHeaders(), Range: `items=${start}-${end}` } },
      );
      if (response.status === 401) {
        if (refreshed) throw new Error("The Trimble Connect session expired. Allow the access token again.");
        refreshed = true;
        await refreshToken();
        continue;
      }
      refreshed = false;
    if (!response.ok && response.status !== 206) {
      throw new Error(await errorMessage(response));
    }
    const batch = await response.json();
    if (!Array.isArray(batch)) {
      throw new Error("Folder items response was not a list.");
    }
    items.push(...batch);
    const next = nextPageStart(parseContentRange(response.headers.get("Content-Range")), batch.length, start, PAGE_SIZE);
    if (next == null) break;
    start = next;
  }
  return items;
}

async function play(video) {
  setStatus(`Opening ${video.name}…`);
  const query = video.versionId ? `?versionId=${encodeURIComponent(video.versionId)}` : "";
  const payload = await connectJson(`/files/fs/${encodeURIComponent(video.id)}/downloadurl${query}`);
  if (!payload.url) throw new Error("Trimble Connect did not return a video URL.");
  playerNode.setAttribute("type", videoMimeType(video.name));
  playerNode.src = payload.url;
  playerNode.load();
  nowPlaying.textContent = video.path || video.name;
  try {
    await playerNode.play();
  } catch {
    setStatus("Press play if the browser blocked automatic playback.");
    return;
  }
  setStatus(video.name);
}

function renderList() {
  listNode.replaceChildren();
  if (!videos.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "Add an .mp4, .webm, .ogg, or .mov file in the project, then refresh.";
    listNode.append(empty);
    return;
  }
  for (const video of videos) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "video-row";
    const title = document.createElement("span");
    title.className = "video-name";
    title.textContent = video.name;
    const path = document.createElement("span");
    path.className = "video-path";
    path.textContent = video.path;
    button.append(title, path);
    button.addEventListener("click", () => {
      play(video).catch((error) => setStatus(error.message));
    });
    listNode.append(button);
  }
}

async function connectJson(path) {
  const response = await fetch(`${serviceBase}${path}`, { headers: authHeaders() });
  if (response.status === 401) {
    await refreshToken();
    const retry = await fetch(`${serviceBase}${path}`, { headers: authHeaders() });
    if (!retry.ok) throw new Error(await errorMessage(retry));
    return retry.json();
  }
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

async function refreshToken() {
  const permission = await api.extension.requestPermission("accesstoken");
  if (!isAccessToken(permission)) {
    throw new Error("The Trimble Connect session expired. Allow the access token again.");
  }
  accessToken = permission;
}

function authHeaders() {
  return {
    Authorization: `Bearer ${accessToken}`,
    Accept: "application/json",
  };
}

async function errorMessage(response) {
  let detail = "";
  try {
    const payload = await response.json();
    detail = payload.message || payload.error_description || payload.error || "";
  } catch {
    detail = "";
  }
  return detail ? `Connect returned ${response.status}: ${detail}` : `Connect returned ${response.status}.`;
}

function readToken(args) {
  if (typeof args === "string") return args;
  return args?.data;
}

function isAccessToken(value) {
  return typeof value === "string" && value.length > 20 && value !== "pending" && value !== "denied";
}

function setStatus(message) {
  statusNode.textContent = message;
}
