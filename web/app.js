/* Social Content Studio Frontend */

const FOLD_LIMIT = 210;
const STATUS_ORDER = ["draft", "ready", "scheduled", "published", "archived"];
const STATUS_LABELS = {
  draft: "Draft",
  ready: "Ready",
  scheduled: "Scheduled",
  published: "Published",
  archived: "Archived",
};
const PLATFORM_META = {
  linkedin: { label: "LinkedIn", short: "in", max: 3000 },
  x: { label: "X", short: "𝕏", max: 280 },
  threads: { label: "Threads", short: "@", max: 500 },
};

const state = {
  drafts: [],
  notes: [],
  discoverItems: [],
  config: null,
  aiState: null,
  aiDraftProvider: "local_templates",
  promptTemplates: [],
  voiceProfiles: [],
  activeVoiceId: "",
  presetsTab: "templates",
  editingPresetId: null,
  undoStacks: {},
  theme: localStorage.getItem("studio_theme") || "dark",
  liDark: false,
  activeView: "studio",
  selectedId: null,
  schedulingDraftId: null,
  filterStatus: "all",
  boardPlatformFilter: "all",
  searchQuery: "",
  discoverSearch: "",
  dismissedDueKey: "",
  previewDevice: "desktop",
  previewExpanded: false,
  dirty: false,
  draftEdit: null,
};

const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const CALENDAR_SVG =
  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="18" height="18" x="3" y="4" rx="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>';
const TRASH_SVG =
  '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>';

const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatSocialHtml(rawText) {
  return escapeHtml(rawText || "")
    .replace(/(https?:\/\/[^\s<]+)/g, '<span class="li-link">$1</span>')
    .replace(/(^|[\s(>])(#[A-Za-z][A-Za-z0-9_]*|@[A-Za-z0-9_.-]+)/g, '$1<span class="li-hashtag">$2</span>');
}

function showToast(message, type = "info", action = null) {
  const container = $("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const msgSpan = document.createElement("span");
  msgSpan.textContent = message;
  toast.appendChild(msgSpan);

  if (action && action.label && typeof action.onClick === "function") {
    const actBtn = document.createElement("button");
    actBtn.type = "button";
    actBtn.className = "toast-action-btn";
    actBtn.textContent = action.label;
    actBtn.addEventListener("click", () => {
      toast.remove();
      action.onClick();
    });
    toast.appendChild(actBtn);
  }

  container.appendChild(toast);
  setTimeout(() => toast.remove(), action ? 6000 : 3400);
}

function openConfirmModal({
  title = "Confirm Action",
  message = "Are you sure?",
  confirmLabel = "Confirm",
  danger = true,
} = {}) {
  return new Promise((resolve) => {
    const modal = $("confirm-modal");
    const okBtn = $("btn-confirm-ok");
    const cancelBtn = $("btn-confirm-cancel");
    const closeBtn = $("btn-close-confirm-modal");

    $("confirm-modal-title").textContent = title;
    $("confirm-modal-message").textContent = message;
    okBtn.textContent = confirmLabel;
    okBtn.className = danger ? "btn btn-danger" : "btn btn-primary";
    modal.classList.remove("hidden");

    const cleanup = (result) => {
      modal.classList.add("hidden");
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      closeBtn.removeEventListener("click", onCancel);
      modal.removeEventListener("click", onBackdrop);
      window.removeEventListener("keydown", onKey);
      resolve(result);
    };

    const onOk = () => cleanup(true);
    const onCancel = () => cleanup(false);
    const onBackdrop = (e) => { if (e.target === modal) cleanup(false); };
    const onKey = (e) => { if (e.key === "Escape") cleanup(false); };

    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    closeBtn.addEventListener("click", onCancel);
    modal.addEventListener("click", onBackdrop);
    window.addEventListener("keydown", onKey);
  });
}

async function confirmDiscard(message = "Discard your unsaved changes in Studio?", confirmLabel = "Discard") {
  if (!state.dirty) return true;
  return openConfirmModal({
    title: "Discard Unsaved Changes?",
    message,
    confirmLabel,
    danger: false,
  });
}

async function withBusy(btn, busyText, fn) {
  const labelEl = btn?.querySelector("span") || btn;
  const origText = labelEl ? labelEl.textContent : "";
  if (btn) btn.disabled = true;
  if (labelEl && busyText) labelEl.textContent = busyText;
  try {
    return await fn();
  } catch (err) {
    showToast(err.message, "error");
    return null;
  } finally {
    if (btn) btn.disabled = false;
    if (labelEl && busyText) labelEl.textContent = origText;
  }
}

function bindModal(modalId, closeBtnIds, onClose = null) {
  const modal = $(modalId);
  const close = () => (onClose ? onClose() : modal.classList.add("hidden"));
  closeBtnIds.forEach((id) => $(id)?.addEventListener("click", close));
  modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
}

function bindPillGroup(containerEl, selector, onSelect) {
  containerEl.addEventListener("click", (e) => {
    const btn = e.target.closest(selector);
    if (!btn) return;
    containerEl.querySelectorAll(selector).forEach((el) => el.classList.toggle("active", el === btn));
    onSelect(btn);
  });
}

function applyTheme(theme) {
  const normalized = theme === "light" ? "light" : "dark";
  state.theme = normalized;
  document.documentElement.dataset.theme = normalized;
  localStorage.setItem("studio_theme", normalized);

  const isDark = normalized === "dark";
  $("theme-icon-sun").classList.toggle("hidden", !isDark);
  $("theme-icon-moon").classList.toggle("hidden", isDark);
  $("theme-label").textContent = isDark ? "Light" : "Dark";
}

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

async function copyText(text, label, buttonEl = null) {
  if (!text) {
    showToast(`Nothing to copy for ${label}.`, "error");
    return;
  }
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    if (buttonEl) {
      const labelSpan = buttonEl.querySelector("span") || buttonEl;
      const orig = labelSpan.textContent;
      labelSpan.textContent = "Copied!";
      setTimeout(() => { labelSpan.textContent = orig; }, 1500);
    }
    showToast(`${label} copied to clipboard.`, "success");
  } catch {
    showToast("Copy failed—please copy manually.", "error");
  }
}

async function copyAndPublish(draft) {
  if (!draft) return;
  await copyText(draft.post_copy, "Post copy");
  await updateDraftStatus(draft, "published");
}

function getInitials(name) {
  const parts = String(name || "YN").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "YN";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const pad2 = (n) => String(n).padStart(2, "0");

function parseLocalSchedule(str) {
  if (!str || typeof str !== "string") return null;
  const m = str.trim().match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})$/);
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]), 0, 0);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatScheduleInfo(str) {
  const dtObj = parseLocalSchedule(str);
  if (!dtObj) return null;

  const shortLabel = `${MONTHS_SHORT[dtObj.getMonth()]} ${dtObj.getDate()} · ${pad2(dtObj.getHours())}:${pad2(dtObj.getMinutes())}`;
  const diffMs = dtObj.getTime() - Date.now();
  const isDue = diffMs <= 0;

  let relativeLabel = "Due now";
  if (!isDue) {
    const totalMins = Math.round(diffMs / 60000);
    relativeLabel =
      totalMins < 60
        ? `in ${Math.max(1, totalMins)}m`
        : totalMins < 48 * 60
        ? `in ${Math.round(totalMins / 60)}h`
        : `in ${Math.round(totalMins / 1440)}d`;
  }
  return { shortLabel, relativeLabel, isDue, dateObj: dtObj };
}

function getPresetDateTime(presetKey) {
  const now = new Date();
  const target = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 9, 0, 0, 0);

  if (presetKey === "tomorrow-9") {
    target.setDate(target.getDate() + 1);
  } else if (presetKey === "plus2-10") {
    target.setDate(target.getDate() + 2);
    target.setHours(10, 0, 0, 0);
  } else if (presetKey === "next-mon-9") {
    const day = target.getDay();
    target.setDate(target.getDate() + (day === 1 ? 7 : (8 - day) % 7 || 7));
  } else if (presetKey === "today-18") {
    target.setHours(18, 0, 0, 0);
    if (target.getTime() <= now.getTime()) target.setDate(target.getDate() + 1);
  }

  return {
    date: `${target.getFullYear()}-${pad2(target.getMonth() + 1)}-${pad2(target.getDate())}`,
    time: `${pad2(target.getHours())}:${pad2(target.getMinutes())}`,
  };
}

function downloadScheduleIcs(draft, dateStr, timeStr) {
  const dtObj = parseLocalSchedule(`${dateStr}T${timeStr}`);
  if (!dtObj) {
    showToast("Pick a valid publish date and time first.", "error");
    return;
  }
  const toUtcStamp = (d) =>
    `${d.getUTCFullYear()}${pad2(d.getUTCMonth() + 1)}${pad2(d.getUTCDate())}T${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}00Z`;
  const endObj = new Date(dtObj.getTime() + 15 * 60000);
  const esc = (s) =>
    String(s || "")
      .replaceAll("\\", "\\\\")
      .replaceAll(";", "\\;")
      .replaceAll(",", "\\,")
      .replaceAll("\r\n", "\\n")
      .replaceAll("\n", "\\n");

  const plat = PLATFORM_META[draft.platform || "linkedin"]?.label || "Social";
  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Content Studio//EN",
    "BEGIN:VEVENT",
    `UID:content-studio-${Date.now()}@local`,
    `DTSTAMP:${toUtcStamp(new Date())}`,
    `DTSTART:${toUtcStamp(dtObj)}`,
    `DTEND:${toUtcStamp(endObj)}`,
    `SUMMARY:${esc(`Publish ${plat} Post: ${draft.title || "Untitled Draft"}`)}`,
    `DESCRIPTION:${esc((draft.post_copy || "").slice(0, 600))}`,
    "END:VEVENT",
    "END:VCALENDAR",
    "",
  ].join("\r\n");

  const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${(draft.filename || "social-post").replace(/\.md$/i, "")}.ics`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast("Calendar reminder (.ics) downloaded.", "success");
}

function updateNavCounts() {
  $("nav-discover-count").textContent = String(state.discoverItems.length);
  $("nav-board-count").textContent = String(state.drafts.length);
  $("nav-notes-count").textContent = String(state.notes.length);
  if ($("board-summary")) $("board-summary").textContent = `${state.drafts.length} total drafts`;
}

function syncDraftViews() {
  renderQueue();
  renderEditor();
  renderBoard();
  renderNotifications();
}

/* ---------------- IN-APP NOTIFICATIONS ---------------- */

function renderNotifications() {
  const scheduled = state.drafts
    .filter((d) => d.status === "scheduled" && d.scheduled_for)
    .sort((a, b) => a.scheduled_for.localeCompare(b.scheduled_for));

  const dueDrafts = [];
  const upcomingDrafts = [];
  for (const d of scheduled) {
    const info = formatScheduleInfo(d.scheduled_for);
    if (!info) continue;
    (info.isDue ? dueDrafts : upcomingDrafts).push({ draft: d, info });
  }

  const badge = $("notif-badge");
  badge.textContent = String(dueDrafts.length);
  badge.classList.toggle("hidden", dueDrafts.length === 0);

  const dueKey = dueDrafts.map((x) => x.draft.id).join("|");
  const banner = $("due-banner");
  if (dueDrafts.length > 0 && state.dismissedDueKey !== dueKey) {
    const first = dueDrafts[0].draft;
    const plat = PLATFORM_META[first.platform || "linkedin"]?.label || "Post";
    $("due-banner-text").textContent =
      dueDrafts.length === 1
        ? `Due now (${plat}): "${first.title}"`
        : `${dueDrafts.length} scheduled posts are due now — next: "${first.title}"`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }

  const listEl = $("notif-pop-list");
  listEl.innerHTML = "";
  if (dueDrafts.length === 0 && upcomingDrafts.length === 0) {
    listEl.innerHTML = '<p class="muted small" style="padding:8px">No scheduled posts yet.</p>';
    return;
  }

  for (const { draft, info } of dueDrafts) {
    const item = document.createElement("div");
    item.className = "notif-item due";
    const plat = PLATFORM_META[draft.platform || "linkedin"]?.label || "Post";
    item.innerHTML = `
      <div class="notif-item-title">${escapeHtml(draft.title)}</div>
      <div class="muted small">${escapeHtml(plat)} · Due now (${escapeHtml(info.shortLabel)})</div>
      <div class="notif-item-actions">
        <button type="button" class="btn btn-xs btn-primary notif-publish-btn">Copy &amp; Publish</button>
        <button type="button" class="btn btn-xs btn-secondary notif-open-btn">Open</button>
      </div>
    `;
    item.querySelector(".notif-publish-btn").addEventListener("click", () => copyAndPublish(draft));
    item.querySelector(".notif-open-btn").addEventListener("click", () => {
      $("notif-popover").classList.add("hidden");
      openDraftInStudio(draft.id);
    });
    listEl.appendChild(item);
  }

  for (const { draft, info } of upcomingDrafts.slice(0, 5)) {
    const item = document.createElement("div");
    item.className = "notif-item";
    const plat = PLATFORM_META[draft.platform || "linkedin"]?.label || "Post";
    item.innerHTML = `
      <div class="notif-item-title">${escapeHtml(draft.title)}</div>
      <div class="muted small">${escapeHtml(plat)} · ${escapeHtml(info.shortLabel)} (${escapeHtml(info.relativeLabel)})</div>
    `;
    listEl.appendChild(item);
  }
}

/* ---------------- DISCOVER INBOX ---------------- */

function renderDiscoverList() {
  $("discover-total-count").textContent = String(state.discoverItems.length);
  updateNavCounts();

  const q = state.discoverSearch.trim().toLowerCase();
  const filtered = state.discoverItems.filter((it) =>
    !q ||
    (it.title || "").toLowerCase().includes(q) ||
    (it.source_name || "").toLowerCase().includes(q) ||
    (it.summary || "").toLowerCase().includes(q)
  );

  const listEl = $("discover-list");
  listEl.innerHTML = "";

  if (filtered.length === 0) {
    const msg = document.createElement("div");
    msg.className = "muted small";
    msg.style.padding = "16px";
    msg.textContent =
      state.discoverItems.length === 0
        ? 'Inbox is empty. Click "Fetch Feeds" above to pull recent articles.'
        : "No fetched posts match your filter.";
    listEl.appendChild(msg);
    return;
  }

  for (const it of filtered) {
    const row = document.createElement("div");
    row.className = "discover-feed-row";
    row.setAttribute("role", "listitem");

    const excerpt = (it.summary || "").trim();
    row.innerHTML = `
      <div class="discover-feed-main">
        <div class="discover-feed-title-row">
          <span class="discover-feed-title">${escapeHtml(it.title)}</span>
          ${it.already_sent ? '<span class="tag">Sent</span>' : ""}
        </div>
        ${excerpt ? `<div class="discover-feed-excerpt">${escapeHtml(excerpt)}</div>` : ""}
        <div class="discover-feed-meta">
          <span>${escapeHtml(it.source_name || "Feed")}</span>
          ${it.published ? `<span>·</span><span>${escapeHtml(it.published.slice(0, 16))}</span>` : ""}
        </div>
      </div>
      <div class="discover-feed-actions">
        ${it.link ? `<a href="${escapeHtml(it.link)}" target="_blank" rel="noopener noreferrer" class="btn btn-xs btn-secondary discover-open-link">Open Original ↗</a>` : ""}
        <button type="button" class="btn btn-xs btn-primary discover-send-btn">Send to Studio →</button>
        <button type="button" class="btn btn-xs btn-danger-ghost discover-delete-btn" title="Delete from inbox" aria-label="Delete from inbox">${TRASH_SVG} <span>Delete</span></button>
      </div>
    `;

    const sendBtn = row.querySelector(".discover-send-btn");
    sendBtn.addEventListener("click", () => sendFeedItemToStudio(it, sendBtn));
    row.querySelector(".discover-delete-btn").addEventListener("click", () => dismissDiscoverItem(it.id));
    listEl.appendChild(row);
  }
}

async function fetchDiscoverFeeds(reset = false) {
  await withBusy($("btn-discover-fetch"), "Fetching...", async () => {
    const res = await api(reset ? "/api/discover/reset" : "/api/discover/fetch", {
      method: "POST",
      body: "{}",
    });
    state.discoverItems = res.items || [];
    renderDiscoverList();
    showToast(`Fetched ${state.discoverItems.length} article(s).`, "success");
  });
}

async function dismissDiscoverItem(id) {
  if (!id) return;
  try {
    await api("/api/discover/dismiss", { method: "POST", body: JSON.stringify({ id }) });
    state.discoverItems = state.discoverItems.filter((it) => it.id !== id);
    renderDiscoverList();
    showToast("Removed from inbox.", "info");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function sendFeedItemToStudio(item, btn) {
  if (!item) return;
  if (!(await confirmDiscard("You have unsaved edits in Studio. Discard them and open this article?", "Discard & Open"))) {
    return;
  }
  await withBusy(btn, "Sending...", async () => {
    const res = await api("/api/discover/send", {
      method: "POST",
      body: JSON.stringify({
        id: item.id || "",
        title: item.title,
        summary: item.summary || "",
        url: item.link || "",
        source_name: item.source_name || "Discover Inbox",
        platform: $("discover-platform")?.value || "linkedin",
        fetch_full: true,
      }),
    });
    state.drafts.unshift(res.draft);
    if (item.id) {
      const target = state.discoverItems.find((it) => it.id === item.id);
      if (target) target.already_sent = true;
    }
    state.selectedId = res.draft.id;
    renderDiscoverList();
    syncDraftViews();
    switchView("studio");
    showToast("Sent raw post to Studio for editing.", "success");
  });
}

/* ---------------- MULTI-PLATFORM PREVIEW ---------------- */

function computeTruncatedPreview(text) {
  if (!text || state.previewExpanded) return { text: text || "", truncated: false };

  const lines = text.split("\n");
  let candidate = lines.length > 4 ? lines.slice(0, 4).join("\n") : text;
  if (candidate.length > FOLD_LIMIT) {
    let slice = candidate.slice(0, FOLD_LIMIT);
    const lastSpace = slice.lastIndexOf(" ");
    if (lastSpace > 140) slice = slice.slice(0, lastSpace);
    candidate = slice.trimEnd();
  }
  return { text: candidate, truncated: candidate.length < text.length };
}

function renderPreview() {
  const profile = state.config?.profile || {
    name: "Your Name",
    handle: "yourhandle",
    headline: "Software Engineer · AI Builder",
  };
  const name = profile.name || "Your Name";
  const handle = (profile.handle || "yourhandle").replace(/^@/, "");
  const headline = profile.headline || "";
  const initials = getInitials(name);

  if ($("cfg-avatar-preview")) {
    $("cfg-avatar-preview").textContent = initials;
    $("cfg-name-preview").textContent = name;
    $("cfg-handle-preview").textContent = `@${handle}`;
    $("cfg-headline-preview").textContent = headline;
  }

  const platform = state.draftEdit?.platform || "linkedin";
  const meta = PLATFORM_META[platform] || PLATFORM_META.linkedin;
  $("preview-platform-title").textContent = `${meta.label} Preview`;

  const frame = $("linkedin-frame");
  frame.classList.toggle("desktop", state.previewDevice === "desktop");
  frame.classList.toggle("mobile", state.previewDevice === "mobile");
  frame.classList.toggle("li-dark", state.liDark);

  $("btn-li-theme").textContent = state.liDark ? "Card: Dark" : "Card: Light";
  const expandBtn = $("btn-toggle-expand");
  expandBtn.classList.toggle("hidden", platform !== "linkedin");
  expandBtn.textContent = state.previewExpanded ? "Expanded" : "Folded (...see more)";

  const postCopy = state.draftEdit ? state.draftEdit.post_copy : "";
  const root = $("preview-card-root");

  if (platform === "x" || platform === "threads") {
    const isX = platform === "x";
    const parts = !postCopy.trim()
      ? []
      : isX && postCopy.length > 280 && postCopy.includes("\n\n")
      ? postCopy.split(/\n\n+/).filter(Boolean)
      : [postCopy];

    const bodyHtml =
      parts.length === 0
        ? `<span class="muted">Start typing your ${isX ? "X post or thread" : "Threads post"}...</span>`
        : isX
        ? parts
            .map(
              (chunk, idx) => `
          <div class="thread-block">
            ${parts.length > 1 ? `<div class="thread-count">${idx + 1}/${parts.length} · ${chunk.length}/280</div>` : ""}
            <div class="social-body">${formatSocialHtml(chunk)}</div>
          </div>`
            )
            .join("")
        : `<div class="social-body">${formatSocialHtml(postCopy)}</div>`;

    root.innerHTML = `
      <article class="social-card">
        <header class="social-card-head">
          <div class="li-avatar li-avatar-md">${escapeHtml(initials)}</div>
          <div class="social-meta">
            <span class="social-name">${escapeHtml(isX ? name : `@${handle}`)}</span>
            <span class="social-handle">${escapeHtml(isX ? `@${handle}` : name)} · now</span>
          </div>
        </header>
        ${bodyHtml}
        <footer class="social-foot">
          ${isX ? "<span>💬 3</span><span>🔁 6</span><span>♡ 29</span><span>📊 412</span>" : "<span>♡ 18</span><span>💬 4</span><span>🔁 2</span><span>📤</span>"}
        </footer>
      </article>
    `;
    return;
  }

  let bodyHtml = '<span style="color:var(--li-muted)">Start typing your LinkedIn post to preview...</span>';
  if (postCopy.trim()) {
    const { text, truncated } = computeTruncatedPreview(postCopy);
    const formatted = formatSocialHtml(text);
    bodyHtml = truncated
      ? `${formatted}<button type="button" class="li-see-more" id="li-see-more-btn">...see more</button>`
      : formatted;
  }

  root.innerHTML = `
    <article class="li-card">
      <header class="li-author">
        <div class="li-avatar">${escapeHtml(initials)}</div>
        <div class="li-author-meta">
          <div class="li-name-row">
            <span class="li-name">${escapeHtml(name)}</span>
            <span class="li-conn">· 1st</span>
          </div>
          <div class="li-headline">${escapeHtml(headline)}</div>
          <div class="li-sub">
            <span>Just now</span>
            <span>·</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
          </div>
        </div>
      </header>
      <div id="li-body" class="li-body">${bodyHtml}</div>
      <div class="li-stats-row">
        <div class="li-reactions">
          <span class="rx rx-like" aria-hidden="true"></span>
          <span class="rx rx-celebrate" aria-hidden="true"></span>
          <span class="rx rx-love" aria-hidden="true"></span>
          <span class="rx-count">24</span>
        </div>
        <span>4 comments · 2 reposts</span>
      </div>
      <footer class="li-actions-bar">
        <span>Like</span><span>Comment</span><span>Repost</span><span>Send</span>
      </footer>
    </article>
  `;

  $("li-see-more-btn")?.addEventListener("click", () => {
    state.previewExpanded = true;
    renderPreview();
  });
}

function updateMeters() {
  const text = $("edit-post-copy").value || "";
  const platform = $("edit-platform").value || "linkedin";
  const totalLen = text.length;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const seconds = Math.round((words / 200) * 60);

  $("read-time").textContent = seconds >= 60 ? `~${Math.round(seconds / 60)}m read` : `~${seconds}s read`;

  const fillEl = $("hook-progress-fill");
  const hookMeter = $("hook-meter");
  const totalMeter = $("total-meter");

  if (platform === "x") {
    fillEl.style.width = `${Math.min(100, Math.round((totalLen / 280) * 100))}%`;
    const ok = totalLen <= 280;
    const blocks = text.split(/\n\n+/).filter(Boolean).length || 1;
    fillEl.className = `hook-progress-fill ${ok ? "ok" : "warn"}`;
    hookMeter.textContent = ok
      ? `X Post: ${totalLen} / 280 · Fits single post`
      : `Thread mode (${blocks} blocks) · Single post > 280`;
    hookMeter.className = `meter ${ok ? "meter-ok" : "meter-warn"}`;
    totalMeter.textContent = `${totalLen} chars`;
    totalMeter.className = "meter-subtle mono";
    return;
  }

  if (platform === "threads") {
    fillEl.style.width = `${Math.min(100, Math.round((totalLen / 500) * 100))}%`;
    const ok = totalLen <= 500;
    fillEl.className = `hook-progress-fill ${ok ? "ok" : "warn"}`;
    hookMeter.textContent = `${ok ? "Threads" : "Over limit"}: ${totalLen} / 500 chars`;
    hookMeter.className = `meter ${ok ? "meter-ok" : "meter-danger"}`;
    totalMeter.textContent = `${totalLen} / 500`;
    totalMeter.className = ok ? "meter-subtle mono" : "meter meter-danger mono";
    return;
  }

  const hookLen = (text.split("\n\n")[0] || "").length;
  const hookOk = hookLen <= FOLD_LIMIT;
  fillEl.style.width = `${Math.min(100, Math.round((hookLen / FOLD_LIMIT) * 100))}%`;
  fillEl.className = `hook-progress-fill ${hookOk ? "ok" : "warn"}`;
  hookMeter.textContent = `Hook: ${hookLen} / ${FOLD_LIMIT} · ${hookOk ? "Fits above fold" : 'May clip before "...see more"'}`;
  hookMeter.className = `meter ${hookOk ? "meter-ok" : "meter-warn"}`;
  totalMeter.textContent = `${totalLen} / 3000`;
  totalMeter.className = totalLen > 3000 ? "meter meter-danger mono" : "meter-subtle mono";
}

function setDirty(dirty) {
  state.dirty = dirty;
  $("unsaved-indicator").classList.toggle("hidden", !dirty);
}

const getSelectedDraft = () => state.drafts.find((d) => d.id === state.selectedId) || null;

function updateUndoButton() {
  $("btn-ai-undo").disabled = (state.undoStacks[state.selectedId] || []).length === 0;
}

function renderEditorSchedulePill(draft) {
  const pill = $("btn-editor-schedule");
  if (!pill || !draft) return;
  const info = formatScheduleInfo(draft.scheduled_for);
  if (info) {
    const dueTag = draft.status === "scheduled" && info.isDue;
    pill.className = `schedule-pill${dueTag ? " due" : ""}`;
    pill.innerHTML = `${CALENDAR_SVG} <span>${escapeHtml(dueTag ? `Due · ${info.shortLabel}` : info.shortLabel)}</span>`;
  } else {
    pill.className = "schedule-pill empty";
    pill.innerHTML = `${CALENDAR_SVG} <span>Schedule</span>`;
  }
}

function renderEditor() {
  const draft = getSelectedDraft();
  const empty = $("editor-empty");
  const workspace = $("editor-workspace");

  if (!draft) {
    empty.classList.remove("hidden");
    workspace.classList.add("hidden");
    state.draftEdit = null;
    renderPreview();
    return;
  }

  empty.classList.add("hidden");
  workspace.classList.remove("hidden");

  state.draftEdit = { ...draft };
  $("edit-title").value = draft.title || "";
  $("edit-platform").value = PLATFORM_META[draft.platform] ? draft.platform : "linkedin";
  $("edit-status").value = draft.status || "draft";
  $("edit-post-copy").value = draft.post_copy || "";

  const srcEl = $("edit-source-display");
  srcEl.innerHTML = draft.source_link
    ? `Source: <a href="${escapeHtml(draft.source_link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(draft.source_name)}</a> · ${escapeHtml(draft.date)}`
    : `Source: ${escapeHtml(draft.source_name || "Studio")} · ${escapeHtml(draft.date)}`;

  renderEditorSchedulePill(draft);
  setDirty(false);
  updateUndoButton();
  updateMeters();
  renderPreview();
}

async function openDraftInStudio(draftId) {
  if (draftId !== state.selectedId && !(await confirmDiscard("Discard your unsaved edits in Studio and switch drafts?"))) {
    return;
  }
  state.selectedId = draftId;
  state.previewExpanded = false;
  switchView("studio");
  renderQueue();
  renderEditor();
}

/* ---------------- QUEUE & DRAFT MUTATIONS ---------------- */

function renderQueue() {
  const counts = { all: state.drafts.length, draft: 0, ready: 0, scheduled: 0, published: 0, archived: 0 };
  for (const d of state.drafts) {
    if (counts[d.status] !== undefined) counts[d.status] += 1;
  }
  $("queue-total-count").textContent = String(state.drafts.length);
  for (const [k, v] of Object.entries(counts)) {
    const span = document.querySelector(`[data-count="${k}"]`);
    if (span) span.textContent = String(v);
  }
  updateNavCounts();

  const q = state.searchQuery.trim().toLowerCase();
  const filtered = state.drafts.filter((d) => {
    if (state.filterStatus !== "all" && d.status !== state.filterStatus) return false;
    return (
      !q ||
      (d.title || "").toLowerCase().includes(q) ||
      (d.source_name || "").toLowerCase().includes(q) ||
      (d.post_copy || "").toLowerCase().includes(q)
    );
  });

  const listEl = $("queue-list");
  listEl.innerHTML = "";

  if (filtered.length === 0) {
    listEl.innerHTML = '<div class="muted small" style="padding:16px">No drafts match your filter.</div>';
    return;
  }

  for (const d of filtered) {
    const row = document.createElement("div");
    row.className = `queue-item${d.id === state.selectedId ? " selected" : ""}`;
    row.setAttribute("role", "listitem");
    row.tabIndex = 0;

    const plat = PLATFORM_META[d.platform] ? d.platform : "linkedin";
    const info = formatScheduleInfo(d.scheduled_for);
    const schedBadge = info
      ? `<span class="schedule-pill${d.status === "scheduled" && info.isDue ? " due" : ""}">${CALENDAR_SVG} ${escapeHtml(info.shortLabel)}</span>`
      : "";

    row.innerHTML = `
      <div class="queue-item-top">
        <span class="queue-item-title">${escapeHtml(d.title)}</span>
        <div class="discover-card-actions">
          <span class="status-dot ${escapeHtml(d.status)}" title="${escapeHtml(STATUS_LABELS[d.status] || d.status)}"></span>
          <button type="button" class="queue-icon-btn queue-delete-btn" title="Delete draft" aria-label="Delete draft">${TRASH_SVG}</button>
        </div>
      </div>
      <div class="queue-item-meta">
        <span class="plat-badge plat-${escapeHtml(plat)}">${escapeHtml(PLATFORM_META[plat].label)}</span>
        <span>${escapeHtml(d.date)}</span>
        <span>·</span>
        <span>${escapeHtml(d.source_name)}</span>
        ${schedBadge}
      </div>
    `;

    row.addEventListener("click", () => selectDraft(d.id));
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectDraft(d.id);
      }
    });
    row.querySelector(".queue-delete-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteDraftById(d.id, d.title, { skipConfirm: true });
    });
    listEl.appendChild(row);
  }
}

async function selectDraft(id) {
  if (id === state.selectedId) return;
  if (!(await confirmDiscard("Discard your unsaved changes to this draft?"))) return;
  state.selectedId = id;
  state.previewExpanded = false;
  renderQueue();
  renderEditor();
}

async function patchDraft(id, patch, toastMessage, FullEditorSync = false) {
  try {
    const data = await api("/api/drafts", {
      method: "PUT",
      body: JSON.stringify({ id, ...patch }),
    });
    const idx = state.drafts.findIndex((d) => d.id === id);
    if (idx !== -1) state.drafts[idx] = data.draft;

    if (state.selectedId === id) {
      if (FullEditorSync) {
        state.draftEdit = { ...data.draft };
        setDirty(false);
      } else if (state.draftEdit) {
        state.draftEdit.status = data.draft.status;
        state.draftEdit.scheduled_for = data.draft.scheduled_for;
      }
      $("edit-status").value = data.draft.status;
      renderEditorSchedulePill(data.draft);
    }
    renderQueue();
    renderBoard();
    renderNotifications();
    if (toastMessage) {
      showToast(typeof toastMessage === "function" ? toastMessage(data.draft) : toastMessage, "success");
    }
    return data.draft;
  } catch (err) {
    showToast(err.message, "error");
    return null;
  }
}

async function saveCurrentDraft() {
  if (!state.selectedId || !state.draftEdit) return;
  await patchDraft(
    state.selectedId,
    {
      title: $("edit-title").value.trim() || "Untitled Draft",
      platform: $("edit-platform").value,
      status: $("edit-status").value,
      post_copy: $("edit-post-copy").value,
    },
    "Draft saved.",
    true
  );
}

async function updateDraftStatus(draft, newStatus) {
  await patchDraft(draft.id, { status: newStatus }, `Moved to ${STATUS_LABELS[newStatus]}.`);
}

async function createBlankDraft() {
  if (!(await confirmDiscard("Discard your unsaved edits and create a blank draft?"))) return;
  try {
    const data = await api("/api/drafts/new", {
      method: "POST",
      body: JSON.stringify({ title: "New Social Post", platform: "linkedin", post_copy: "" }),
    });
    state.drafts.unshift(data.draft);
    state.selectedId = data.draft.id;
    switchView("studio");
    syncDraftViews();
    $("edit-title").focus();
    $("edit-title").select();
    showToast("Created new draft.", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function restoreDeletedDraft(draft) {
  try {
    const data = await api("/api/drafts/new", {
      method: "POST",
      body: JSON.stringify({
        title: draft.title,
        post_copy: draft.post_copy,
        platform: draft.platform || "linkedin",
        status: draft.status || "draft",
        scheduled_for: draft.scheduled_for || "",
        source_name: draft.source_name || "Studio Draft",
        source_link: draft.source_link || "",
        generator: draft.generator || "studio",
        style: draft.style || "custom",
      }),
    });
    state.drafts.unshift(data.draft);
    state.selectedId = data.draft.id;
    syncDraftViews();
    showToast("Draft restored.", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function deleteDraftById(id, title, { skipConfirm = false } = {}) {
  if (!id) return;
  const deletedSnapshot = state.drafts.find((d) => d.id === id) || null;
  if (!skipConfirm) {
    const confirmed = await openConfirmModal({
      title: "Delete Draft",
      message: `Delete "${title || "this draft"}"? This removes the file from disk.`,
      confirmLabel: "Delete",
      danger: true,
    });
    if (!confirmed) return;
  }
  try {
    await api("/api/drafts/delete", { method: "POST", body: JSON.stringify({ id }) });
    state.drafts = state.drafts.filter((d) => d.id !== id);
    delete state.undoStacks[id];
    if (state.selectedId === id) {
      state.selectedId = state.drafts[0]?.id || null;
      setDirty(false);
    }
    syncDraftViews();
    showToast(
      "Draft deleted.",
      "success",
      deletedSnapshot ? { label: "Undo", onClick: () => restoreDeletedDraft(deletedSnapshot) } : null
    );
  } catch (err) {
    showToast(err.message, "error");
  }
}

/* ---------------- STUDIO AI PROMPTS, TEMPLATES & VOICES ---------------- */

function renderStudioPresets() {
  const voiceSelect = $("studio-voice-select");
  voiceSelect.innerHTML = "";
  for (const v of state.voiceProfiles) {
    const opt = document.createElement("option");
    opt.value = v.id;
    opt.textContent = v.name;
    voiceSelect.appendChild(opt);
  }
  if (state.activeVoiceId) voiceSelect.value = state.activeVoiceId;

  const chips = $("studio-template-chips");
  chips.innerHTML = "";
  for (const t of state.promptTemplates) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip-btn";
    btn.textContent = t.name;
    btn.title = t.prompt;
    btn.addEventListener("click", () => {
      $("studio-ai-prompt").value = t.prompt;
      $("studio-ai-prompt").focus();
    });
    chips.appendChild(btn);
  }
}

async function persistStudioPresets(payload) {
  const res = await api("/api/studio/presets", { method: "PUT", body: JSON.stringify(payload) });
  state.promptTemplates = res.prompt_templates || [];
  state.voiceProfiles = res.voice_profiles || [];
  state.activeVoiceId = res.active_voice_id || "";
  renderStudioPresets();
}

async function runStudioPrompt(adaptOnly = false) {
  if (!state.selectedId || !state.draftEdit) return;
  if (!state.aiState || state.aiState.ai?.provider === "local_templates") {
    showToast("Connect an AI model in the top bar first.", "info");
    openAiModal();
    return;
  }
  const customPrompt = $("studio-ai-prompt").value.trim();
  if (!adaptOnly && !customPrompt) {
    showToast("Type a prompt or click a saved template first.", "error");
    $("studio-ai-prompt").focus();
    return;
  }

  const btn = adaptOnly ? $("btn-adapt-platform") : $("btn-run-prompt");
  const currentText = $("edit-post-copy").value;

  await withBusy(btn, adaptOnly ? "Adapting..." : "Running...", async () => {
    const res = await api("/api/ai/rewrite", {
      method: "POST",
      body: JSON.stringify({
        title: $("edit-title").value,
        post_copy: currentText,
        platform: $("edit-platform").value,
        voice_id: $("studio-voice-select").value,
        custom_prompt: adaptOnly ? "" : customPrompt,
        adapt_to_platform: adaptOnly,
      }),
    });

    if (!state.undoStacks[state.selectedId]) state.undoStacks[state.selectedId] = [];
    state.undoStacks[state.selectedId].push(currentText);
    updateUndoButton();

    const ta = $("edit-post-copy");
    ta.value = res.post_copy || currentText;
    ta.dispatchEvent(new Event("input"));
    showToast(`Updated with ${res.model_used}. Use Undo anytime or Save.`, "success");
  });
}

function undoStudioAiEdit() {
  if (!state.selectedId) return;
  const stack = state.undoStacks[state.selectedId] || [];
  if (stack.length === 0) return;
  const prev = stack.pop();
  updateUndoButton();
  const ta = $("edit-post-copy");
  ta.value = prev;
  ta.dispatchEvent(new Event("input"));
  showToast("Restored previous draft text.", "info");
}

function openPresetsModal(tab = "templates") {
  state.presetsTab = tab;
  state.editingPresetId = null;
  renderPresetsModal();
  $("presets-modal").classList.remove("hidden");
}

function closePresetsModal() {
  state.editingPresetId = null;
  $("presets-modal").classList.add("hidden");
}

function renderPresetsModal() {
  const isTpl = state.presetsTab === "templates";
  $("presets-tab-templates").classList.toggle("active", isTpl);
  $("presets-tab-voices").classList.toggle("active", !isTpl);

  const items = isTpl ? state.promptTemplates : state.voiceProfiles;
  const listEl = $("presets-list");
  listEl.innerHTML = items.length === 0 ? '<p class="muted small">None saved yet. Add one below!</p>' : "";

  for (const item of items) {
    const bodyText = isTpl ? item.prompt : item.instructions;
    const row = document.createElement("div");
    row.className = "preset-item";
    row.innerHTML = `
      <div class="preset-item-info">
        <div class="preset-item-name">${escapeHtml(item.name)}</div>
        <div class="preset-item-body">${escapeHtml(bodyText)}</div>
      </div>
      <div class="preset-item-actions">
        <button type="button" class="btn btn-xs btn-secondary preset-edit-btn">Edit</button>
        <button type="button" class="btn btn-xs btn-danger-ghost preset-del-btn">Delete</button>
      </div>
    `;
    row.querySelector(".preset-edit-btn").addEventListener("click", () => {
      state.editingPresetId = item.id;
      $("preset-name-input").value = item.name;
      $("preset-body-input").value = bodyText;
      $("preset-form-heading").textContent = isTpl ? "Edit Template" : "Edit Voice & Tone";
      $("btn-preset-save").textContent = "Update";
      $("btn-preset-cancel-edit").classList.remove("hidden");
    });
    row.querySelector(".preset-del-btn").addEventListener("click", async () => {
      if (!isTpl && state.voiceProfiles.length <= 1) {
        showToast("Keep at least one voice profile.", "error");
        return;
      }
      const nextList = items.filter((x) => x.id !== item.id);
      try {
        await persistStudioPresets(isTpl ? { prompt_templates: nextList } : { voice_profiles: nextList });
        if (state.editingPresetId === item.id) state.editingPresetId = null;
        renderPresetsModal();
        showToast("Removed.", "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
    listEl.appendChild(row);
  }

  if (!state.editingPresetId) {
    $("preset-name-input").value = "";
    $("preset-body-input").value = "";
    $("preset-form-heading").textContent = isTpl ? "Add New Template" : "Add New Voice & Tone";
    $("preset-body-label").textContent = isTpl ? "Prompt Instructions" : "Voice & Tone Instructions";
    $("btn-preset-save").textContent = isTpl ? "Add Template" : "Add Voice";
    $("btn-preset-cancel-edit").classList.add("hidden");
  }
}

/* ---------------- SCHEDULE MODAL & KANBAN BOARD ---------------- */

function updateScheduleHint() {
  const dateVal = $("sched-date").value;
  const timeVal = $("sched-time").value;
  const hint = $("sched-relative-hint");
  const info = formatScheduleInfo(dateVal && timeVal ? `${dateVal}T${timeVal}` : "");
  if (!info) {
    hint.textContent = "Select a publish date and time.";
    hint.className = "meter meter-warn";
  } else if (info.isDue) {
    hint.textContent = `${info.shortLabel} — Time is in the past (will mark Due now)`;
    hint.className = "meter meter-warn";
  } else {
    hint.textContent = `Scheduled for ${info.shortLabel} (${info.relativeLabel})`;
    hint.className = "meter meter-ok";
  }
}

function openScheduleModal(draftId) {
  const draft = state.drafts.find((d) => d.id === draftId);
  if (!draft) return;
  state.schedulingDraftId = draftId;
  $("sched-draft-title").textContent = draft.title || "Untitled Draft";

  const existing = parseLocalSchedule(draft.scheduled_for);
  if (existing) {
    $("sched-date").value = `${existing.getFullYear()}-${pad2(existing.getMonth() + 1)}-${pad2(existing.getDate())}`;
    $("sched-time").value = `${pad2(existing.getHours())}:${pad2(existing.getMinutes())}`;
  } else {
    const def = getPresetDateTime("tomorrow-9");
    $("sched-date").value = def.date;
    $("sched-time").value = def.time;
  }

  $("btn-clear-schedule").classList.toggle("hidden", !draft.scheduled_for);
  updateScheduleHint();
  $("schedule-modal").classList.remove("hidden");
}

function closeScheduleModal() {
  state.schedulingDraftId = null;
  $("schedule-modal").classList.add("hidden");
}

async function saveScheduleModal() {
  const draft = state.drafts.find((d) => d.id === state.schedulingDraftId);
  if (!draft) return;
  const dateVal = $("sched-date").value;
  const timeVal = $("sched-time").value;
  if (!dateVal || !timeVal) {
    showToast("Please select both a date and time.", "error");
    return;
  }
  const scheduledFor = `${dateVal}T${timeVal}`;
  const targetStatus = draft.status === "published" ? "published" : "scheduled";
  const updated = await patchDraft(
    draft.id,
    { scheduled_for: scheduledFor, status: targetStatus },
    (d) => `Scheduled for ${formatScheduleInfo(d.scheduled_for)?.shortLabel || scheduledFor}.`
  );
  if (updated) closeScheduleModal();
}

async function clearScheduleModal() {
  const draft = state.drafts.find((d) => d.id === state.schedulingDraftId);
  if (!draft) return;
  const nextStatus = draft.status === "scheduled" ? "ready" : draft.status;
  const updated = await patchDraft(draft.id, { scheduled_for: "", status: nextStatus }, "Schedule cleared.");
  if (updated) closeScheduleModal();
}

function moveOrSchedule(draft, targetStatus) {
  if (targetStatus === "scheduled" && !draft.scheduled_for) {
    openScheduleModal(draft.id);
    return;
  }
  updateDraftStatus(draft, targetStatus);
}

function renderBoard() {
  updateNavCounts();

  const visibleDrafts = state.drafts.filter(
    (d) => state.boardPlatformFilter === "all" || (d.platform || "linkedin") === state.boardPlatformFilter
  );

  const scheduledDrafts = visibleDrafts.filter((d) => d.status === "scheduled");
  const dueCount = scheduledDrafts.filter((d) => formatScheduleInfo(d.scheduled_for)?.isDue).length;

  $("board-scheduled-pill").textContent = `${scheduledDrafts.length} scheduled`;
  const duePill = $("board-due-pill");
  duePill.textContent = `${dueCount} due now`;
  duePill.classList.toggle("hidden", dueCount === 0);

  const board = $("kanban-board");
  board.innerHTML = "";

  for (let colIdx = 0; colIdx < STATUS_ORDER.length; colIdx++) {
    const status = STATUS_ORDER[colIdx];
    const items = visibleDrafts.filter((d) => d.status === status);
    if (status === "scheduled") {
      items.sort((a, b) => (a.scheduled_for || "9999").localeCompare(b.scheduled_for || "9999"));
    }

    const col = document.createElement("div");
    col.className = "kanban-col";
    col.dataset.status = status;

    col.addEventListener("dragover", (e) => {
      e.preventDefault();
      col.classList.add("drag-over");
    });
    col.addEventListener("dragleave", () => col.classList.remove("drag-over"));
    col.addEventListener("drop", (e) => {
      e.preventDefault();
      col.classList.remove("drag-over");
      const draft = state.drafts.find((d) => d.id === e.dataTransfer.getData("text/plain"));
      if (draft && draft.status !== status) moveOrSchedule(draft, status);
    });

    col.innerHTML = `
      <div class="kanban-col-header">
        <span class="kanban-col-title">
          <span class="status-dot ${escapeHtml(status)}" style="margin-top:0"></span>
          <span>${STATUS_LABELS[status]}</span>
        </span>
        <span class="count-pill">${items.length}</span>
      </div>
      <div class="kanban-cards"></div>
    `;

    const cardsEl = col.querySelector(".kanban-cards");
    for (const d of items) {
      const card = document.createElement("div");
      card.className = "kanban-card";
      card.draggable = true;
      card.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", d.id));

      const prevStatus = colIdx > 0 ? STATUS_ORDER[colIdx - 1] : null;
      const nextStatus = colIdx < STATUS_ORDER.length - 1 ? STATUS_ORDER[colIdx + 1] : null;
      const plat = PLATFORM_META[d.platform] ? d.platform : "linkedin";
      const snippet = (d.post_copy || "").replace(/\s+/g, " ").trim();
      const schedInfo = formatScheduleInfo(d.scheduled_for);
      const isDue = Boolean(schedInfo && d.status === "scheduled" && schedInfo.isDue);

      card.innerHTML = `
        <div class="kanban-card-head">
          <div class="kanban-card-title">${escapeHtml(d.title)}</div>
          <button type="button" class="queue-icon-btn board-delete-btn" draggable="false" title="Delete draft" aria-label="Delete draft">${TRASH_SVG}</button>
        </div>
        ${schedInfo ? `<button type="button" class="schedule-pill${isDue ? " due" : ""} card-sched-pill" title="Edit publish schedule">${CALENDAR_SVG} <span>${escapeHtml(isDue ? `Due now · ${schedInfo.shortLabel}` : `${schedInfo.shortLabel} (${schedInfo.relativeLabel})`)}</span></button>` : ""}
        ${snippet ? `<div class="kanban-card-snippet">${escapeHtml(snippet)}</div>` : ""}
        <div class="kanban-card-meta">
          <span class="plat-badge plat-${escapeHtml(plat)}">${escapeHtml(PLATFORM_META[plat].label)}</span>
          <span class="mono">${d.total_length || 0} chars</span>
        </div>
        ${isDue ? '<button type="button" class="due-action-btn">Copy &amp; Publish</button>' : ""}
        <div class="kanban-card-actions">
          <div class="move-btns">
            <button type="button" class="btn btn-xs btn-secondary open-studio-btn">Open</button>
            <button type="button" class="btn btn-xs btn-secondary schedule-card-btn" title="Schedule publish date & time">${CALENDAR_SVG} <span>Schedule</span></button>
          </div>
          <div class="move-btns">
            ${prevStatus ? `<button type="button" class="btn btn-xs btn-secondary move-prev-btn" title="Move to ${STATUS_LABELS[prevStatus]}">←</button>` : ""}
            ${nextStatus ? `<button type="button" class="btn btn-xs btn-secondary move-next-btn" title="Move to ${STATUS_LABELS[nextStatus]}">→</button>` : ""}
          </div>
        </div>
      `;

      card.querySelector(".kanban-card-title").addEventListener("click", () => openDraftInStudio(d.id));
      card.querySelector(".board-delete-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        deleteDraftById(d.id, d.title, { skipConfirm: true });
      });
      card.querySelector(".open-studio-btn").addEventListener("click", () => openDraftInStudio(d.id));
      card.querySelector(".schedule-card-btn").addEventListener("click", () => openScheduleModal(d.id));
      card.querySelector(".card-sched-pill")?.addEventListener("click", () => openScheduleModal(d.id));
      card.querySelector(".due-action-btn")?.addEventListener("click", () => copyAndPublish(d));
      card.querySelector(".move-prev-btn")?.addEventListener("click", () => moveOrSchedule(d, prevStatus));
      card.querySelector(".move-next-btn")?.addEventListener("click", () => moveOrSchedule(d, nextStatus));

      cardsEl.appendChild(card);
    }

    board.appendChild(col);
  }
}

/* ---------------- NOTES & SETTINGS ---------------- */

function renderNotes() {
  $("notes-count").textContent = String(state.notes.length);
  updateNavCounts();
  const list = $("notes-list");
  list.innerHTML = "";

  if (state.notes.length === 0) {
    list.innerHTML = '<p class="muted small">No saved notes yet. Capture an idea on the left!</p>';
    return;
  }

  for (const n of state.notes) {
    const item = document.createElement("div");
    item.className = "note-item";
    item.innerHTML = `
      <div class="note-item-head">
        <div>
          <div class="note-item-title">${escapeHtml(n.title)}</div>
          <div class="note-item-meta">${escapeHtml(n.filename)} · ${escapeHtml(n.modified)}</div>
        </div>
        <button type="button" class="btn btn-xs btn-danger-ghost delete-note-btn">Delete</button>
      </div>
      <div class="note-item-body">${escapeHtml(n.content)}</div>
    `;
    item.querySelector(".delete-note-btn").addEventListener("click", async () => {
      const confirmed = await openConfirmModal({
        title: "Delete Note",
        message: `Delete note "${n.filename}"?`,
        confirmLabel: "Delete",
        danger: true,
      });
      if (!confirmed) return;
      try {
        await api("/api/notes/delete", { method: "POST", body: JSON.stringify({ filename: n.filename }) });
        state.notes = state.notes.filter((x) => x.filename !== n.filename);
        renderNotes();
        showToast("Note deleted.", "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
    list.appendChild(item);
  }
}

async function submitNote(draftNow) {
  const title = $("note-title").value.trim();
  const content = $("note-content").value.trim();
  if (!title && !content) {
    showToast("Enter a title or rough notes first.", "error");
    return;
  }
  const btnSave = $("btn-save-note");
  const btnDraft = $("btn-save-draft-note");
  btnSave.disabled = true;
  btnDraft.disabled = true;
  try {
    const data = await api("/api/notes", {
      method: "POST",
      body: JSON.stringify({ title, content, draft_now: draftNow }),
    });
    $("note-title").value = "";
    $("note-content").value = "";
    await refreshNotes();
    if (draftNow && Array.isArray(data.drafts)) {
      state.drafts = data.drafts;
      if (state.drafts.length > 0 && !state.dirty) state.selectedId = state.drafts[0].id;
      syncDraftViews();
      switchView("studio");
      showToast("Note saved & drafted into Queue!", "success");
    } else {
      showToast("Note saved.", "success");
    }
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btnSave.disabled = false;
    btnDraft.disabled = false;
  }
}

function renderSettings() {
  if (!state.config) return;
  const prof = state.config.profile || {};
  $("cfg-profile-name").value = prof.name || "Your Name";
  $("cfg-profile-handle").value = (prof.handle || "yourhandle").replace(/^@/, "");
  $("cfg-profile-headline").value = prof.headline || "";
  renderPreview();
  renderFeedsList();
}

function renderFeedsList() {
  const container = $("feeds-list");
  container.innerHTML = "";
  const feeds = state.config?.feeds || [];
  if (feeds.length === 0) {
    container.innerHTML = '<p class="muted small">No feeds configured.</p>';
    return;
  }
  feeds.forEach((feed, idx) => {
    const row = document.createElement("div");
    row.className = "feed-row";
    row.innerHTML = `
      <span class="feed-name">${escapeHtml(feed.name)}</span>
      <span class="feed-url" title="${escapeHtml(feed.url)}">${escapeHtml(feed.url)}</span>
      <button type="button" class="btn btn-xs btn-danger-ghost">Remove</button>
    `;
    row.querySelector("button").addEventListener("click", () => {
      state.config.feeds.splice(idx, 1);
      renderFeedsList();
    });
    container.appendChild(row);
  });
}

async function saveSettings() {
  try {
    const data = await api("/api/config", {
      method: "PUT",
      body: JSON.stringify({
        profile: {
          name: $("cfg-profile-name").value.trim() || "Your Name",
          handle: $("cfg-profile-handle").value.trim().replace(/^@/, "") || "yourhandle",
          headline: $("cfg-profile-headline").value.trim(),
        },
        feeds: state.config.feeds || [],
      }),
    });
    state.config = data.config;
    renderPreview();
    showToast("Settings saved.", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

/* ---------------- AI CONNECT MODAL ---------------- */

function renderAiButton() {
  const btn = $("btn-ai-connect");
  const label = $("ai-connect-label");
  if (!btn || !label) return;
  const aiState = state.aiState;
  if (!aiState || aiState.ai?.provider === "local_templates") {
    btn.className = "ai-connect-btn";
    label.textContent = "AI: Local Templates";
  } else if (aiState.active_ready) {
    btn.className = "ai-connect-btn connected";
    label.textContent = `AI: ${aiState.active_label}`;
  } else {
    btn.className = "ai-connect-btn needs-key";
    label.textContent = `AI: ${aiState.active_label} (Key needed)`;
  }
}

function renderModelChips(models) {
  const container = $("ai-model-chips");
  container.innerHTML = "";
  for (const m of Array.from(new Set(models || [])).slice(0, 16)) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip-btn mono";
    chip.textContent = m;
    chip.addEventListener("click", () => { $("ai-model-input").value = m; });
    container.appendChild(chip);
  }
}

function selectAiProvider(pid) {
  const presets = state.aiState?.presets || {};
  const preset = presets[pid];
  if (!preset) return;
  state.aiDraftProvider = pid;

  const grid = $("ai-provider-grid");
  grid.innerHTML = "";
  for (const [id, p] of Object.entries(presets)) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `provider-card${id === pid ? " active" : ""}`;
    card.dataset.provider = id;
    const savedMasked = state.aiState?.saved_keys?.[id] || "";
    const statusChip =
      id === "local_templates"
        ? '<span class="tag">Offline</span>'
        : savedMasked
        ? '<span class="tag">Key saved</span>'
        : !p.requires_key
        ? '<span class="tag">No key</span>'
        : "";
    card.innerHTML = `
      <div class="provider-card-head"><span>${escapeHtml(p.label)}</span>${statusChip}</div>
      <span class="provider-card-desc">${escapeHtml(p.description)}</span>
    `;
    card.addEventListener("click", () => selectAiProvider(id));
    grid.appendChild(card);
  }

  const isLocal = pid === "local_templates";
  $("ai-config-fields").classList.toggle("hidden", isLocal);
  $("ai-test-result").classList.add("hidden");

  if (!isLocal) {
    const savedAi = state.aiState?.ai || {};
    const useSaved = savedAi.provider === pid;
    $("ai-model-input").value = (useSaved && savedAi.model) || preset.default_model || "";
    $("ai-base-url").value = (useSaved && savedAi.base_url) || preset.default_base_url || "";
    const temp = useSaved && savedAi.temperature !== undefined ? savedAi.temperature : 0.7;
    $("ai-temperature").value = String(temp);
    $("ai-temp-value").textContent = String(temp);

    const masked = state.aiState?.saved_keys?.[pid] || "";
    const badge = $("ai-saved-key-badge");
    const clearBtn = $("btn-clear-ai-key");
    badge.textContent = masked ? `Saved: ${masked}` : "";
    badge.classList.toggle("hidden", !masked);
    clearBtn.classList.toggle("hidden", !masked);
    $("ai-api-key").placeholder = masked
      ? "Leave blank to keep saved key, or paste new key"
      : preset.requires_key
      ? "Paste API key (stored locally in .ai_secrets.json)"
      : "Optional API key (leave blank for local servers)";
    $("ai-api-key").value = "";
    renderModelChips(preset.suggested_models || []);
  }
}

function openAiModal() {
  if (!state.aiState) return;
  $("ai-api-key").type = "password";
  $("btn-toggle-key-vis").textContent = "Show";
  $("ai-test-result").classList.add("hidden");
  selectAiProvider(state.aiState.ai?.provider || "local_templates");
  $("ai-modal").classList.remove("hidden");
}

const closeAiModal = () => $("ai-modal").classList.add("hidden");

function collectAiModalPayload() {
  return {
    provider: state.aiDraftProvider,
    model: $("ai-model-input").value.trim(),
    base_url: $("ai-base-url").value.trim(),
    api_key: $("ai-api-key").value.trim(),
    temperature: Number($("ai-temperature").value) || 0.7,
  };
}

/* ---------------- NAVIGATION & BOOTSTRAP ---------------- */

function switchView(viewName) {
  state.activeView = viewName;
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === viewName);
  });
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `view-${viewName}`);
  });
}

function insertAtCursor(textarea, text) {
  const start = textarea.selectionStart ?? textarea.value.length;
  const end = textarea.selectionEnd ?? textarea.value.length;
  textarea.value = textarea.value.slice(0, start) + text + textarea.value.slice(end);
  const pos = start + text.length;
  textarea.focus();
  textarea.setSelectionRange(pos, pos);
  textarea.dispatchEvent(new Event("input"));
}

async function refreshNotes() {
  const data = await api("/api/notes");
  state.notes = data.notes || [];
  renderNotes();
}

async function loadInitialData() {
  try {
    const [draftsData, notesData, cfgData, discoverData] = await Promise.all([
      api("/api/drafts"),
      api("/api/notes"),
      api("/api/config"),
      api("/api/discover"),
    ]);
    state.drafts = draftsData.drafts || [];
    state.notes = notesData.notes || [];
    state.discoverItems = discoverData.items || [];
    state.config = cfgData.config;
    state.aiState = cfgData.ai_state || null;
    state.promptTemplates = cfgData.prompt_templates || [];
    state.voiceProfiles = cfgData.voice_profiles || [];
    state.activeVoiceId = cfgData.active_voice_id || "";

    renderAiButton();
    renderStudioPresets();
    if (state.drafts.length > 0) state.selectedId = state.drafts[0].id;

    renderDiscoverList();
    syncDraftViews();
    renderNotes();
    renderSettings();
  } catch (err) {
    showToast(`Failed to load studio data: ${err.message}`, "error");
  }
}

function setupEventListeners() {
  $("btn-theme-toggle").addEventListener("click", () => {
    applyTheme(state.theme === "dark" ? "light" : "dark");
  });

  // Topbar notifications
  $("btn-notifications").addEventListener("click", (e) => {
    e.stopPropagation();
    $("notif-popover").classList.toggle("hidden");
  });
  document.addEventListener("click", (e) => {
    const pop = $("notif-popover");
    if (!pop.classList.contains("hidden") && !e.target.closest(".notif-wrap")) {
      pop.classList.add("hidden");
    }
  });
  $("btn-due-copy-publish").addEventListener("click", () => {
    const due = state.drafts.find((d) => d.status === "scheduled" && formatScheduleInfo(d.scheduled_for)?.isDue);
    copyAndPublish(due);
  });
  $("btn-due-open-board").addEventListener("click", () => switchView("board"));
  $("btn-due-dismiss").addEventListener("click", () => {
    state.dismissedDueKey = state.drafts
      .filter((d) => d.status === "scheduled" && formatScheduleInfo(d.scheduled_for)?.isDue)
      .map((d) => d.id)
      .join("|");
    $("due-banner").classList.add("hidden");
  });

  // AI Connect modal
  $("btn-ai-connect").addEventListener("click", openAiModal);
  bindModal("ai-modal", ["btn-close-ai-modal", "btn-cancel-ai"], closeAiModal);
  $("ai-temperature").addEventListener("input", (e) => { $("ai-temp-value").textContent = e.target.value; });
  $("btn-toggle-key-vis").addEventListener("click", () => {
    const input = $("ai-api-key");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    $("btn-toggle-key-vis").textContent = show ? "Hide" : "Show";
  });
  $("btn-ai-fetch-models").addEventListener("click", () =>
    withBusy($("btn-ai-fetch-models"), "Fetching...", async () => {
      const res = await api("/api/ai/models", { method: "POST", body: JSON.stringify(collectAiModalPayload()) });
      renderModelChips(res.models || []);
      if (!$("ai-model-input").value.trim() && res.models?.length) $("ai-model-input").value = res.models[0];
      showToast(`Loaded ${(res.models || []).length} model(s).`, "success");
    })
  );
  $("btn-ai-test").addEventListener("click", async () => {
    const btn = $("btn-ai-test");
    const box = $("ai-test-result");
    btn.disabled = true;
    btn.textContent = "Testing...";
    box.classList.add("hidden");
    try {
      const res = await api("/api/ai/test", { method: "POST", body: JSON.stringify(collectAiModalPayload()) });
      box.className = `ai-test-result ${res.ok ? "ok" : "err"}`;
      box.textContent = res.ok ? res.message || "Connection succeeded." : res.error || "Connection failed.";
    } catch (err) {
      box.className = "ai-test-result err";
      box.textContent = err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "Test Connection";
    }
  });
  $("btn-ai-save").addEventListener("click", () =>
    withBusy($("btn-ai-save"), null, async () => {
      const res = await api("/api/ai", { method: "PUT", body: JSON.stringify(collectAiModalPayload()) });
      state.aiState = res;
      renderAiButton();
      closeAiModal();
      showToast(`AI set to ${res.active_label}.`, "success");
    })
  );
  $("btn-clear-ai-key").addEventListener("click", async () => {
    try {
      const res = await api("/api/ai", {
        method: "PUT",
        body: JSON.stringify({ ...collectAiModalPayload(), api_key: "", clear_api_key: true }),
      });
      state.aiState = res;
      renderAiButton();
      selectAiProvider(state.aiDraftProvider);
      showToast("Saved API key cleared.", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Navigation & filters
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });
  $("btn-discover-fetch").addEventListener("click", () => fetchDiscoverFeeds(false));
  $("btn-discover-reset").addEventListener("click", () => fetchDiscoverFeeds(true));
  $("discover-search").addEventListener("input", (e) => {
    state.discoverSearch = e.target.value;
    renderDiscoverList();
  });
  $("queue-search").addEventListener("input", (e) => {
    state.searchQuery = e.target.value;
    renderQueue();
  });
  bindPillGroup($("status-filters"), ".filter-pill", (btn) => {
    state.filterStatus = btn.dataset.status;
    renderQueue();
  });
  bindPillGroup($("board-platform-filters"), "[data-board-platform]", (btn) => {
    state.boardPlatformFilter = btn.dataset.boardPlatform;
    renderBoard();
  });

  // Editor inputs & quick-insert
  const onEditorInput = () => {
    if (!state.draftEdit) return;
    state.draftEdit.title = $("edit-title").value;
    state.draftEdit.platform = $("edit-platform").value;
    state.draftEdit.status = $("edit-status").value;
    state.draftEdit.post_copy = $("edit-post-copy").value;
    setDirty(true);
    updateMeters();
    renderPreview();
  };
  ["edit-title", "edit-post-copy"].forEach((id) => $(id).addEventListener("input", onEditorInput));
  ["edit-platform", "edit-status"].forEach((id) => $(id).addEventListener("change", onEditorInput));

  document.querySelectorAll("[data-insert]").forEach((btn) => {
    btn.addEventListener("click", () => insertAtCursor($("edit-post-copy"), btn.dataset.insert));
  });
  document.querySelectorAll("[data-insert-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ta = $("edit-post-copy");
      if (btn.dataset.insertAction === "divider") {
        insertAtCursor(ta, `${ta.value && !ta.value.endsWith("\n") ? "\n\n" : ""}———\n\n`);
      }
    });
  });

  // Studio AI prompt, templates & voice
  $("studio-voice-select").addEventListener("change", async (e) => {
    try {
      await persistStudioPresets({ active_voice_id: e.target.value });
      showToast("Voice & Tone selected.", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  });
  $("btn-run-prompt").addEventListener("click", () => runStudioPrompt(false));
  $("btn-adapt-platform").addEventListener("click", () => runStudioPrompt(true));
  $("btn-ai-undo").addEventListener("click", undoStudioAiEdit);
  $("btn-quick-save-template").addEventListener("click", () => {
    const promptText = $("studio-ai-prompt").value.trim();
    if (!promptText) {
      showToast("Write a prompt first to save it as a template.", "error");
      return;
    }
    openPresetsModal("templates");
    $("preset-name-input").value = promptText.slice(0, 32);
    $("preset-body-input").value = promptText;
    $("preset-name-input").focus();
    $("preset-name-input").select();
  });

  // Presets Manager modal
  ["btn-manage-templates", "btn-settings-templates"].forEach((id) =>
    $(id).addEventListener("click", () => openPresetsModal("templates"))
  );
  ["btn-manage-voices", "btn-settings-voices"].forEach((id) =>
    $(id).addEventListener("click", () => openPresetsModal("voices"))
  );
  bindModal("presets-modal", ["btn-close-presets-modal", "btn-done-presets"], closePresetsModal);
  $("presets-tab-templates").addEventListener("click", () => {
    state.presetsTab = "templates";
    state.editingPresetId = null;
    renderPresetsModal();
  });
  $("presets-tab-voices").addEventListener("click", () => {
    state.presetsTab = "voices";
    state.editingPresetId = null;
    renderPresetsModal();
  });
  $("btn-preset-cancel-edit").addEventListener("click", () => {
    state.editingPresetId = null;
    renderPresetsModal();
  });
  $("btn-preset-save").addEventListener("click", async () => {
    const name = $("preset-name-input").value.trim();
    const bodyText = $("preset-body-input").value.trim();
    if (!name || !bodyText) {
      showToast("Enter both a name and instructions.", "error");
      return;
    }
    const isTpl = state.presetsTab === "templates";
    const list = isTpl ? [...state.promptTemplates] : [...state.voiceProfiles];
    const entry = isTpl
      ? { id: state.editingPresetId || `tpl-${Date.now()}`, name, prompt: bodyText }
      : { id: state.editingPresetId || `voice-${Date.now()}`, name, instructions: bodyText };

    if (state.editingPresetId) {
      const idx = list.findIndex((x) => x.id === state.editingPresetId);
      if (idx !== -1) list[idx] = entry;
    } else {
      list.push(entry);
    }
    try {
      await persistStudioPresets(isTpl ? { prompt_templates: list } : { voice_profiles: list });
      state.editingPresetId = null;
      renderPresetsModal();
      showToast("Saved!", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Editor main buttons & preview controls
  $("btn-save-draft").addEventListener("click", saveCurrentDraft);
  $("btn-editor-schedule").addEventListener("click", () => {
    if (state.selectedId) openScheduleModal(state.selectedId);
  });
  $("btn-copy-post").addEventListener("click", () =>
    copyText($("edit-post-copy").value, "Post copy", $("btn-copy-post"))
  );
  $("btn-delete-draft").addEventListener("click", () => {
    const draft = getSelectedDraft();
    if (draft) deleteDraftById(draft.id, draft.title);
  });
  $("btn-new-draft").addEventListener("click", createBlankDraft);
  $("btn-empty-new").addEventListener("click", createBlankDraft);

  bindPillGroup(document.querySelector(".preview-toggles"), "[data-device]", (btn) => {
    state.previewDevice = btn.dataset.device;
    renderPreview();
  });
  $("btn-li-theme").addEventListener("click", () => {
    state.liDark = !state.liDark;
    renderPreview();
  });
  $("btn-toggle-expand").addEventListener("click", () => {
    state.previewExpanded = !state.previewExpanded;
    renderPreview();
  });

  // Notes & Settings
  $("btn-save-note").addEventListener("click", () => submitNote(false));
  $("btn-save-draft-note").addEventListener("click", () => submitNote(true));

  const syncProfilePreview = () => {
    if (!state.config) return;
    state.config.profile = {
      name: $("cfg-profile-name").value || "Your Name",
      handle: $("cfg-profile-handle").value.replace(/^@/, "") || "yourhandle",
      headline: $("cfg-profile-headline").value || "",
    };
    renderPreview();
  };
  ["cfg-profile-name", "cfg-profile-handle", "cfg-profile-headline"].forEach((id) =>
    $(id).addEventListener("input", syncProfilePreview)
  );

  $("btn-add-feed").addEventListener("click", () => {
    const name = $("new-feed-name").value.trim();
    const url = $("new-feed-url").value.trim();
    if (!name || !url) {
      showToast("Enter both a feed name and URL.", "error");
      return;
    }
    state.config.feeds = state.config.feeds || [];
    state.config.feeds.push({ name, url });
    $("new-feed-name").value = "";
    $("new-feed-url").value = "";
    renderFeedsList();
  });
  $("btn-save-settings").addEventListener("click", saveSettings);

  // Schedule Modal
  bindModal("schedule-modal", ["btn-close-schedule-modal", "btn-cancel-schedule"], closeScheduleModal);
  ["sched-date", "sched-time"].forEach((id) => $(id).addEventListener("input", updateScheduleHint));
  document.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = getPresetDateTime(btn.dataset.preset);
      $("sched-date").value = preset.date;
      $("sched-time").value = preset.time;
      updateScheduleHint();
    });
  });
  $("btn-save-schedule").addEventListener("click", saveScheduleModal);
  $("btn-clear-schedule").addEventListener("click", clearScheduleModal);
  $("btn-export-ics").addEventListener("click", () => {
    const draft = state.drafts.find((d) => d.id === state.schedulingDraftId);
    if (draft) downloadScheduleIcs(draft, $("sched-date").value, $("sched-time").value);
  });

  // Periodic in-app due-status refresh (every 30s) & Ctrl/Cmd+S
  setInterval(() => {
    renderNotifications();
    if (state.activeView === "board") renderBoard();
  }, 30000);

  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && state.activeView === "studio" && state.selectedId) {
      e.preventDefault();
      saveCurrentDraft();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(state.theme);
  setupEventListeners();
  loadInitialData();
});
