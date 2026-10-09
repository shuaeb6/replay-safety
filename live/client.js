const $ = (id) => document.getElementById(id);
const icons = {
  play: '<path d="m7 4 13 8-13 8z"/>',
  pause: '<path d="M8 4v16M16 4v16"/>',
  restart: '<path d="M3 10a9 9 0 1 1 1 8M3 4v6h6"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  evidence: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/>',
};
const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name]}</svg>`;
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[ch]));
const format = (seconds) => {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  return `${Math.floor(safe / 60)}:${String(Math.floor(safe % 60)).padStart(2, "0")}`;
};

const video = $("mainVideo");
let cameras = [];
let selectedId = "sdg_warehouse_cam-2";
let quietQuery = "empty scene with no people and no moving vehicles";
let reference = false;
let moments = [];
let active = -1;
let boxesOn = true;
let detection = null;
let searchGen = 0;
let noticeTimer;

function notify(message) {
  const node = $("notification");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { node.hidden = true; }, 3500);
}

function selectedCamera() {
  return cameras.find((camera) => camera.id === selectedId) || null;
}

function cameraLabel(id) {
  const camera = cameras.find((item) => item.id === id);
  return camera ? camera.name : (id || "Archive");
}

async function loadSites() {
  const response = await fetch("api/sites");
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "The archive did not respond.");
  cameras = payload.cameras || [];
  if (payload.quiet_query) quietQuery = payload.quiet_query;
  if (!cameras.some((camera) => camera.id === selectedId)) selectedId = cameras[0] ? cameras[0].id : "";
  $("cameraCount").textContent = String(cameras.length);
  $("archiveNote").textContent = payload.indexed_clips
    ? `${payload.indexed_clips} indexed segments`
    : "Indexed archive";
  renderCameras();
  renderViewer();
}

function renderCameras() {
  const all = {
    id: "",
    name: "All cameras",
    place: "Every indexed site",
    tone: "all",
    segments: cameras.reduce((sum, camera) => sum + (camera.segments || 0), 0),
  };
  const cards = [all, ...cameras];
  $("cameraGrid").innerHTML = cards.map((camera, index) => {
    const on = camera.id === selectedId;
    return `<button class="camera-card ${on ? "selected" : ""}" data-camera="${esc(camera.id)}" aria-pressed="${on}">
      <span class="cam-still ${esc(camera.tone || "street")}">${esc(camera.place)}</span>
      <span class="cam-tag">CAM ${String(index).padStart(2, "0")}</span>
      ${on ? '<span class="check">✓</span>' : ""}
      <strong>${esc(camera.name)}</strong>
      <small>${camera.segments || 0} segments</small>
    </button>`;
  }).join("");
  document.querySelectorAll("[data-camera]").forEach((button) => {
    button.onclick = () => selectCamera(button.dataset.camera);
  });
}

function selectCamera(id) {
  selectedId = id;
  reference = false;
  renderCameras();
  renderViewer();
  setModeButtons();
}

function renderViewer() {
  const camera = selectedCamera();
  $("viewerName").textContent = camera ? camera.name : "All cameras";
  $("viewerLocation").textContent = camera ? camera.place : "Search is not limited to one camera";
}

function setModeButtons() {
  $("scenarioButton").classList.toggle("selected", !reference);
  $("referenceButton").classList.toggle("selected", reference);
  $("scenarioButton").setAttribute("aria-pressed", String(!reference));
  $("referenceButton").setAttribute("aria-pressed", String(reference));
}

function activeQuery() {
  if (reference) return quietQuery;
  return $("requirement").value.trim();
}

async function runSearch() {
  const query = activeQuery();
  if (!query) {
    $("suggestion").innerHTML = '<div class="inline-error">Describe what you want to watch, or choose an example.</div>';
    return;
  }
  const gen = ++searchGen;
  $("searchButton").disabled = true;
  $("viewerStatus").textContent = reference ? "Searching for a quieter clip…" : "Searching the archive…";
  $("suggestion").innerHTML = '<div class="suggestion-card"><div class="eyebrow">INDEXED SEARCH</div><h3>Looking through indexed segments</h3><p>This usually takes a few seconds.</p></div>';
  try {
    const response = await fetch("api/search", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query, camera_id: selectedId}),
    });
    const payload = await response.json();
    if (gen !== searchGen) return;
    if (!response.ok) throw new Error(payload.error || "Search failed.");
    moments = payload.moments || [];
    active = -1;
    detection = null;
    video.removeAttribute("src");
    video.load();
    $("eventToast").hidden = true;
    $("analysisBadge").textContent = moments.length ? "MOMENTS READY" : "NO MATCH";
    const answer = payload.answer ? `<p class="answer">${esc(payload.answer)}</p>` : "";
    const heading = moments.length
      ? `${moments.length} matching ${moments.length === 1 ? "moment" : "moments"}`
      : "No matching moments";
    const note = moments.length
      ? "Open a row to replay that segment. The score is search similarity."
      : "Nothing in this camera filter matched. Try another camera, or search all cameras.";
    $("suggestion").innerHTML = `<div class="suggestion-card"><div class="eyebrow">${reference ? "QUIETER CLIP · ANOTHER SEARCH" : "INDEXED SEARCH"}</div><h3>${esc(heading)}</h3><p>${esc(note)}</p>${answer}</div>`;
    $("viewerStatus").textContent = moments.length
      ? "Select evidence to replay the indexed segment."
      : "No moments matched this search.";
    renderEvidence();
  } catch (error) {
    if (gen !== searchGen) return;
    $("suggestion").innerHTML = `<div class="inline-error">${esc(error.message || "Search failed.")}</div>`;
    $("viewerStatus").textContent = "Search did not finish.";
  } finally {
    if (gen === searchGen) $("searchButton").disabled = false;
  }
}

function renderEvidence() {
  $("eventCount").textContent = String(moments.length);
  $("evidenceList").innerHTML = moments.length ? moments.map((moment, index) => {
    const score = Number.isFinite(moment.score) ? `${Math.round(moment.score * 100)}% match` : "indexed";
    const when = Number.isFinite(moment.start_sec) ? format(moment.start_sec) : "0:00";
    return `<button class="evidence-row ${index === active ? "selected" : ""}" data-evidence="${index}">
      <span class="time-chip">${esc(when)}</span>
      <span><strong>${esc(moment.title)}</strong><small>${esc(cameraLabel(moment.camera_id))} · ${esc(moment.objects || "no listed class")} · ${esc(score)}</small></span>
      <span class="arrow">↗</span>
    </button>`;
  }).join("") : '<div class="empty-evidence">◇<strong>Your evidence will appear here</strong>Describe a requirement and search the archive.</div>';
  document.querySelectorAll("[data-evidence]").forEach((button) => {
    button.onclick = () => playMoment(Number(button.dataset.evidence));
  });
}

async function playMoment(index) {
  const moment = moments[index];
  if (!moment || !moment.source) return;
  active = index;
  renderEvidence();
  $("videoError").hidden = true;
  $("eventTitle").textContent = moment.title;
  $("eventMeta").textContent = `${cameraLabel(moment.camera_id)} · indexed caption`;
  $("eventToast").hidden = false;
  $("analysisBadge").textContent = "INDEXED SEGMENT";
  $("viewerStatus").textContent = "Playing the matching segment. Boxes appear when the detector has them.";
  detection = null;
  drawOverlay(0);
  video.src = `api/stream?source=${encodeURIComponent(moment.source)}`;
  video.load();
  try {
    await video.play();
  } catch {
    notify("Press play if the browser blocked autoplay.");
  }
  const gen = searchGen;
  try {
    const response = await fetch(`api/detections?source=${encodeURIComponent(moment.source)}`);
    const payload = await response.json();
    if (gen !== searchGen || active !== index) return;
    detection = response.ok ? payload : null;
    if (detection && detection.unavailable) {
      $("viewerStatus").textContent = "Playing the segment. This clip has no detector boxes.";
    }
    drawOverlay(video.currentTime || 0);
  } catch {
    detection = null;
  }
  $("mainVideo").scrollIntoView({behavior: "smooth", block: "center"});
}

function nearestFrame(time) {
  const frames = detection && detection.frames;
  if (!frames || !frames.length) return null;
  let best = frames[0];
  let gap = Infinity;
  for (const frame of frames) {
    const next = Math.abs((frame.time_sec || 0) - time);
    if (next < gap) {
      gap = next;
      best = frame;
    }
  }
  return best;
}

function drawOverlay(time) {
  const svg = $("overlay");
  const shape = (detection && detection.video_shape) || [1080, 1920];
  const height = shape[0] || 1080;
  const width = shape[1] || 1920;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!boxesOn || !detection) {
    svg.innerHTML = "";
    return;
  }
  const frame = nearestFrame(time);
  const boxes = (frame && frame.detections ? frame.detections : [])
    .filter((box) => Array.isArray(box.bbox) && box.bbox.length === 4)
    .sort((a, b) => (b.confidence || 0) - (a.confidence || 0))
    .slice(0, 8);
  svg.innerHTML = boxes.map((box) => {
    const [x1, y1, x2, y2] = box.bbox.map(Number);
    if (![x1, y1, x2, y2].every(Number.isFinite)) return "";
    const label = esc(box.label || "object");
    return `<rect x="${x1}" y="${y1}" width="${Math.max(0, x2 - x1)}" height="${Math.max(0, y2 - y1)}" fill="none" stroke="#d7f5df" stroke-width="3"></rect>
      <text x="${x1}" y="${Math.max(18, y1 - 8)}" fill="#e7f6ea" font-size="22" font-family="sans-serif">${label}</text>`;
  }).join("");
}

function tick() {
  const duration = Number.isFinite(video.duration) ? video.duration : 0;
  const time = video.currentTime || 0;
  $("timeLabel").textContent = `${format(time)} / ${format(duration)}`;
  $("seek").value = String(duration ? time / duration * 1000 : 0);
  if (active >= 0) drawOverlay(time);
}

async function play() {
  try {
    if (video.paused) {
      if (video.ended) video.currentTime = 0;
      await video.play();
    } else {
      video.pause();
    }
  } catch {
    notify("Playback failed. Try another moment.");
  }
}

$("ruleForm").onsubmit = (event) => {
  event.preventDefault();
  reference = false;
  setModeButtons();
  runSearch();
};
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.onclick = () => {
    $("requirement").value = button.dataset.prompt;
    reference = false;
    setModeButtons();
    selectedId = button.dataset.camera;
    renderCameras();
    renderViewer();
    runSearch();
  };
});
$("scenarioButton").onclick = () => {
  if (!reference) return;
  reference = false;
  setModeButtons();
  runSearch();
};
$("referenceButton").onclick = () => {
  if (reference) return;
  reference = true;
  setModeButtons();
  runSearch();
};
$("playButton").onclick = play;
video.onclick = play;
video.ontimeupdate = tick;
video.onloadedmetadata = tick;
video.onplay = () => {
  $("playButton").innerHTML = icon("pause");
  $("playButton").setAttribute("aria-label", "Pause footage");
};
video.onpause = () => {
  $("playButton").innerHTML = icon("play");
  $("playButton").setAttribute("aria-label", "Play footage");
};
video.onerror = () => {
  if (video.getAttribute("src")) $("videoError").hidden = false;
};
$("seek").oninput = (event) => {
  if (Number.isFinite(video.duration)) video.currentTime = Number(event.target.value) / 1000 * video.duration;
  tick();
};
$("restartButton").onclick = () => { video.currentTime = 0; tick(); };
$("speedButton").onclick = () => {
  const rates = [1, 1.5, 2, 0.5];
  video.playbackRate = rates[(rates.indexOf(video.playbackRate) + 1) % rates.length];
  $("speedButton").textContent = `${video.playbackRate}×`;
};
$("overlayToggle").onclick = () => {
  boxesOn = !boxesOn;
  $("overlayToggle").textContent = `Boxes ${boxesOn ? "on" : "off"}`;
  $("overlayToggle").setAttribute("aria-pressed", String(boxesOn));
  drawOverlay(video.currentTime || 0);
};
$("clearEvidence").onclick = () => {
  moments = [];
  active = -1;
  detection = null;
  $("eventToast").hidden = true;
  $("analysisBadge").textContent = "No moment selected";
  renderEvidence();
  drawOverlay(0);
  notify("Evidence cleared");
};
$("resetButton").onclick = () => {
  searchGen += 1;
  moments = [];
  active = -1;
  detection = null;
  reference = false;
  $("requirement").value = "";
  $("suggestion").innerHTML = "";
  $("eventToast").hidden = true;
  $("searchButton").disabled = false;
  selectedId = cameras.some((camera) => camera.id === "sdg_warehouse_cam-2") ? "sdg_warehouse_cam-2" : "";
  video.removeAttribute("src");
  video.load();
  setModeButtons();
  renderCameras();
  renderViewer();
  renderEvidence();
  $("viewerStatus").textContent = "Choose a camera and describe what to watch.";
  $("analysisBadge").textContent = "No moment selected";
  notify("Workspace reset");
};
$("aboutButton").onclick = () => $("aboutDialog").showModal();
$("closeAbout").onclick = () => $("aboutDialog").close();
$("evidenceNav").onclick = () => $("evidenceSection").scrollIntoView({behavior: "smooth"});
$("workspaceNav").onclick = () => window.scrollTo({top: 0, behavior: "smooth"});
$("workspaceNav").innerHTML = icon("grid");
$("evidenceNav").innerHTML = icon("evidence");
$("playButton").innerHTML = icon("play");
$("restartButton").innerHTML = icon("restart");
renderEvidence();
loadSites().catch((error) => {
  $("archiveNote").textContent = "Archive unavailable";
  $("cameraGrid").innerHTML = `<div class="inline-error">${esc(error.message || "Could not load cameras.")}</div>`;
});
