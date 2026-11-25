const BRIDGE_PORT = 38019;
const BRIDGE_ORIGIN = `http://127.0.0.1:${BRIDGE_PORT}`;
const APP_NAME = "X Downloader";

const LINK_MENU_ID = "xdl-download-link";
const MEDIA_MENU_ID = "xdl-download-media";

// tabId -> Map(url -> {url, kind, contentType, size, addedAt})
const tabMedia = new Map();

const MIN_PROGRESSIVE_BYTES = 200 * 1024; // filter out icons/beacons misnamed as media

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: LINK_MENU_ID,
    title: `Download with ${APP_NAME}`,
    contexts: ["link"],
  });
  chrome.contextMenus.create({
    id: MEDIA_MENU_ID,
    title: `Download with ${APP_NAME}`,
    contexts: ["image", "video", "audio"],
  });
  chrome.action.setBadgeBackgroundColor({ color: "#4F46E5" });
});

// ------------------------------------------------------------ media sniffing

function headerValue(headers, name) {
  const h = (headers || []).find((x) => x.name.toLowerCase() === name.toLowerCase());
  return h ? h.value : null;
}

function classify(url, contentType) {
  const path = url.split("?")[0].split("#")[0].toLowerCase();
  const ct = (contentType || "").toLowerCase();

  // Individual HLS/DASH segments/fragments aren't standalone downloadable
  // files on their own - the manifest (.m3u8/.mpd) capture below is what
  // lets ffmpeg pull the whole stream, so segment requests are just noise.
  if (/\.(ts|m4s|aac)$/.test(path) || ct === "video/mp2t" || ct.includes("iso.segment")) {
    return null;
  }

  if (ct.includes("mpegurl") || path.endsWith(".m3u8")) return "hls";
  if (ct.includes("dash+xml") || path.endsWith(".mpd")) return "dash";
  if (ct.startsWith("video/") || /\.(mp4|webm|mkv|mov|m4v)$/.test(path)) return "progressive-video";
  if (ct.startsWith("audio/") || /\.(mp3|m4a|wav|ogg|flac)$/.test(path)) return "progressive-audio";
  return null;
}

function rememberMedia(tabId, item) {
  if (tabId == null || tabId < 0) return;
  if (!tabMedia.has(tabId)) tabMedia.set(tabId, new Map());
  const bucket = tabMedia.get(tabId);
  const existing = bucket.get(item.url);
  bucket.set(item.url, { ...existing, ...item });
  updateBadge(tabId);
}

function updateBadge(tabId) {
  const count = tabMedia.get(tabId)?.size || 0;
  chrome.action.setBadgeText({ tabId, text: count > 0 ? String(count) : "" });
}

chrome.webRequest.onResponseStarted.addListener(
  (details) => {
    if (details.tabId < 0) return;
    const contentType = headerValue(details.responseHeaders, "content-type");
    const kind = classify(details.url, contentType);
    if (!kind) return;

    const lengthHeader = headerValue(details.responseHeaders, "content-length");
    const size = lengthHeader ? parseInt(lengthHeader, 10) : null;

    if (kind.startsWith("progressive") && size !== null && size < MIN_PROGRESSIVE_BYTES) {
      return; // too small to plausibly be real media content
    }

    rememberMedia(details.tabId, {
      url: details.url,
      kind,
      contentType,
      size,
      addedAt: Date.now(),
    });
  },
  { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other"] },
  ["responseHeaders"]
);

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading" && changeInfo.url) {
    tabMedia.delete(tabId);
    updateBadge(tabId);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  tabMedia.delete(tabId);
});

// --------------------------------------------------------------- messaging

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const tabId = msg.tabId ?? sender.tab?.id;

  if (msg.type === "GET_TAB_MEDIA") {
    const items = Array.from((tabMedia.get(tabId) || new Map()).values());
    sendResponse({ items });
    return false;
  }

  if (msg.type === "DOWNLOAD_MEDIA") {
    sendToApp(msg.url, msg.pageUrl, msg.kind, msg.filename);
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "PING_APP") {
    fetch(`${BRIDGE_ORIGIN}/ping`, { cache: "no-store" })
      .then((r) => sendResponse({ ok: r.ok }))
      .catch(() => sendResponse({ ok: false }));
    return true; // async response
  }

  return false;
});

// ------------------------------------------------------------- context menu

function filenameFromUrl(url) {
  try {
    const path = new URL(url).pathname;
    const last = path.substring(path.lastIndexOf("/") + 1);
    return decodeURIComponent(last) || "";
  } catch {
    return "";
  }
}

function notify(title, message, isError) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon128.png",
    title,
    message,
    priority: isError ? 2 : 0,
  });
}

async function sendToApp(url, pageUrl, kind, filename) {
  const name = filename || filenameFromUrl(url);
  try {
    const resp = await fetch(`${BRIDGE_ORIGIN}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, filename: name, referrer: pageUrl || "", kind: kind || "" }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    notify(APP_NAME, `Added: ${data.filename || name || url}`, false);
  } catch (err) {
    notify(
      `${APP_NAME} isn't running`,
      "Start the X Downloader app, then try the download again.",
      true
    );
  }
}

// ------------------------------------------------- browser download capture

async function appIsRunning() {
  try {
    const r = await fetch(`${BRIDGE_ORIGIN}/ping`, { cache: "no-store" });
    return r.ok;
  } catch {
    return false;
  }
}

async function captureEnabled() {
  const { captureDownloads = true } = await chrome.storage.local.get("captureDownloads");
  return captureDownloads;
}

// Hand Chrome's own downloads (link clicks, "Save as", etc.) to the app. Only
// takes over when the app is actually reachable, so downloads never get lost
// just because X Downloader is closed.
chrome.downloads.onCreated.addListener(async (item) => {
  try {
    if (item.byExtensionId) return;
    const url = item.finalUrl || item.url;
    if (!/^https?:\/\//i.test(url)) return; // blob:/data: can't be fetched by the app
    if (!(await captureEnabled())) return;
    if (!(await appIsRunning())) return;

    await chrome.downloads.cancel(item.id);
    await chrome.downloads.erase({ id: item.id });
    sendToApp(url, item.referrer || "", null, filenameFromUrl(url));
  } catch {
    // On any failure leave Chrome's download alone.
  }
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const url = info.linkUrl || info.srcUrl;
  if (!url) return;
  if (url.startsWith("blob:") || url.startsWith("data:")) {
    notify(
      APP_NAME,
      "This video's address isn't directly downloadable. Click the extension icon or the on-video Download button to pick the real stream instead.",
      true
    );
    return;
  }
  sendToApp(url, tab ? tab.url : "");
});
