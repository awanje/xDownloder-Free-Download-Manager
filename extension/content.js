(() => {
  const ANNOTATED = new WeakSet();
  let activePanel = null;
  let hideTimer = null;

  function isRealSrc(src) {
    return src && !src.startsWith("blob:") && !src.startsWith("data:");
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

  function makeButton() {
    const btn = document.createElement("div");
    btn.className = "xdl-overlay-btn";
    btn.title = "Download with X Downloader";
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 3v11m0 0l-4-4m4 4l4-4M5 19h14" stroke="white" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>Download</span>
    `;
    document.documentElement.appendChild(btn);
    return btn;
  }

  function positionOverlay(el, btn) {
    const rect = el.getBoundingClientRect();
    btn.style.top = `${Math.max(8, rect.top + 8)}px`;
    btn.style.left = `${Math.max(8, rect.right - btn.offsetWidth - 8)}px`;
  }

  function closePanel() {
    if (activePanel) {
      activePanel.remove();
      activePanel = null;
    }
  }

  function showPanel(anchorBtn, el) {
    closePanel();
    const panel = document.createElement("div");
    panel.className = "xdl-panel";

    const candidates = [];
    if (isYouTubeWatchPage(location.href)) {
      // YouTube serves media through a protocol network sniffing can't see,
      // so the reliable path is handing the page URL itself to yt-dlp.
      candidates.push({ url: location.href, kind: "ytdlp", label: "Download this YouTube video" });
    } else if (isRealSrc(el.currentSrc || el.src)) {
      candidates.push({ url: el.currentSrc || el.src, kind: null, label: "This video/audio file" });
    }

    panel.innerHTML = `<div class="xdl-panel-title">Loading detected media…</div>`;
    document.documentElement.appendChild(panel);
    const btnRect = anchorBtn.getBoundingClientRect();
    panel.style.top = `${btnRect.bottom + 6}px`;
    panel.style.left = `${Math.max(8, btnRect.right - panel.offsetWidth)}px`;
    activePanel = panel;

    chrome.runtime.sendMessage({ type: "GET_TAB_MEDIA" }, (resp) => {
      const items = (resp && resp.items) || [];
      for (const item of items) {
        if (!candidates.some((c) => c.url === item.url)) {
          candidates.push({
            url: item.url,
            kind: item.kind,
            label: describeKind(item.kind) + (item.size ? ` (${formatSize(item.size)})` : ""),
          });
        }
      }
      renderPanel(panel, candidates);
    });
  }

  function describeKind(kind) {
    switch (kind) {
      case "hls": return "HLS stream";
      case "dash": return "DASH stream";
      case "progressive-video": return "Video file";
      case "progressive-audio": return "Audio file";
      default: return "Media";
    }
  }

  function formatSize(bytes) {
    if (!bytes) return "";
    const units = ["B", "KB", "MB", "GB"];
    let v = bytes, i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(1)} ${units[i]}`;
  }

  function renderPanel(panel, candidates) {
    if (!candidates.length) {
      panel.innerHTML = `<div class="xdl-panel-title">No downloadable media detected yet.<br>Try playing the video first.</div>`;
      return;
    }
    panel.innerHTML = `<div class="xdl-panel-title">Download with X Downloader</div>`;
    for (const c of candidates) {
      const row = document.createElement("div");
      row.className = "xdl-panel-item";
      row.textContent = c.label;
      row.addEventListener("click", () => {
        chrome.runtime.sendMessage({
          type: "DOWNLOAD_MEDIA",
          url: c.url,
          kind: c.kind,
          pageUrl: location.href,
          filename: (document.title || "video").replace(/[\\/:*?"<>|]/g, "_").slice(0, 80),
        });
        closePanel();
      });
      panel.appendChild(row);
    }
  }

  function attach(el) {
    if (ANNOTATED.has(el)) return;
    ANNOTATED.add(el);

    const btn = makeButton();
    let visible = false;

    function show() {
      clearTimeout(hideTimer);
      positionOverlay(el, btn);
      if (!visible) {
        btn.classList.remove("xdl-visible");
        void btn.offsetWidth; // restart the pop-in animation on re-show
        btn.classList.add("xdl-visible");
      }
      visible = true;
    }
    function scheduleHide() {
      hideTimer = setTimeout(() => {
        btn.classList.remove("xdl-visible");
        visible = false;
      }, 350);
    }

    el.addEventListener("mouseenter", show);
    el.addEventListener("mouseleave", scheduleHide);
    btn.addEventListener("mouseenter", () => clearTimeout(hideTimer));
    btn.addEventListener("mouseleave", scheduleHide);
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      showPanel(btn, el);
    });

    window.addEventListener("scroll", () => visible && positionOverlay(el, btn), true);
    window.addEventListener("resize", () => visible && positionOverlay(el, btn));
  }

  function scan(root) {
    root.querySelectorAll?.("video, audio").forEach(attach);
  }

  scan(document);
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((node) => {
        if (node.nodeType !== 1) return;
        if (node.matches?.("video, audio")) attach(node);
        scan(node);
      });
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  document.addEventListener("click", (e) => {
    if (activePanel && !activePanel.contains(e.target) && !e.target.closest(".xdl-overlay-btn")) {
      closePanel();
    }
  });
})();
