const BRIDGE_PORT = 38019;
const statusEl = document.getElementById("status");
const mediaListEl = document.getElementById("media-list");

fetch(`http://127.0.0.1:${BRIDGE_PORT}/ping`, { cache: "no-store" })
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
  .then(() => {
    statusEl.textContent = "Connected to X Downloader";
    statusEl.className = "status status-ok";
  })
  .catch(() => {
    statusEl.textContent = "X Downloader is not running";
    statusEl.className = "status status-error";
  });

const captureToggle = document.getElementById("capture-toggle");
chrome.storage.local.get("captureDownloads", ({ captureDownloads = true }) => {
  captureToggle.checked = captureDownloads;
});
captureToggle.addEventListener("change", () => {
  chrome.storage.local.set({ captureDownloads: captureToggle.checked });
});

function describeKind(kind) {
  switch (kind) {
    case "hls": return "HLS stream";
    case "dash": return "DASH stream";
    case "progressive-video": return "Video file";
    case "progressive-audio": return "Audio file";
    case "ytdlp": return "YouTube video";
    default: return "Media";
  }
}

function isYouTubeWatchPage(urlStr) {
  try {
    const u = new URL(urlStr);
    const host = u.hostname.replace(/^(www|m)\./, "");
    if (u.hostname === "youtu.be") return u.pathname.length > 1;
    if (host !== "youtube.com" && host !== "music.youtube.com") return false;
    return u.pathname === "/watch" || u.pathname.startsWith("/shorts/");
  } catch {
    return false;
  }
}

function formatSize(bytes) {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

function renderMedia(items, tab) {
  if (!items.length) {
    mediaListEl.innerHTML = `<div class="media-empty">No media detected yet. Try playing a video on the page.</div>`;
    return;
  }
  mediaListEl.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "media-item";
    row.innerHTML = `
      <div class="media-info">
        <div class="media-kind">${describeKind(item.kind)}</div>
        <div class="media-size">${formatSize(item.size)}</div>
      </div>
      <button class="media-download-btn">Download</button>
    `;
    row.querySelector("button").addEventListener("click", () => {
      chrome.runtime.sendMessage({
        type: "DOWNLOAD_MEDIA",
        url: item.url,
        kind: item.kind,
        pageUrl: tab?.url || "",
        filename: (tab?.title || "video").replace(/[\\/:*?"<>|]/g, "_").slice(0, 80),
      });
      row.querySelector("button").textContent = "Added";
    });
    mediaListEl.appendChild(row);
  }
}

chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  const tab = tabs[0];
  if (!tab) {
    mediaListEl.innerHTML = `<div class="media-empty">No active tab.</div>`;
    return;
  }
  chrome.runtime.sendMessage({ type: "GET_TAB_MEDIA", tabId: tab.id }, (resp) => {
    const items = (resp && resp.items) || [];
    if (isYouTubeWatchPage(tab.url || "")) {
      items.unshift({ url: tab.url, kind: "ytdlp", size: null });
    }
    renderMedia(items, tab);
  });
});
