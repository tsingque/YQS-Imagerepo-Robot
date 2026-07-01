const metricsGrid = document.querySelector("#metricsGrid");
const directoryGrid = document.querySelector("#directoryGrid");
const previewGrid = document.querySelector("#previewGrid");
const statusDot = document.querySelector("#statusDot");
const statusText = document.querySelector("#statusText");
const updatedAt = document.querySelector("#updatedAt");
const refreshButton = document.querySelector("#refreshButton");
const loadButton = document.querySelector("#loadButton");
const compressButton = document.querySelector("#compressButton");
const clearButton = document.querySelector("#clearButton");
const recognizeButton = document.querySelector("#recognizeButton");
const similarityButton = document.querySelector("#similarityButton");
const agentButton = document.querySelector("#agentButton");
const feishuTestButton = document.querySelector("#feishuTestButton");
const feishuConfigured = document.querySelector("#feishuConfigured");
const feishuReceiveType = document.querySelector("#feishuReceiveType");
const feishuAutoNotify = document.querySelector("#feishuAutoNotify");
const recognitionProgress = document.querySelector("#recognitionProgress");
const recognitionFailed = document.querySelector("#recognitionFailed");
const recognitionPending = document.querySelector("#recognitionPending");
const recognitionBar = document.querySelector("#recognitionBar");
const recognitionMessage = document.querySelector("#recognitionMessage");
const similarityImageCount = document.querySelector("#similarityImageCount");
const similarityPairCount = document.querySelector("#similarityPairCount");
const similarityHighCount = document.querySelector("#similarityHighCount");
const similarityMessage = document.querySelector("#similarityMessage");
const similarityList = document.querySelector("#similarityList");
const agentRunning = document.querySelector("#agentRunning");
const agentMode = document.querySelector("#agentMode");
const agentFinishedAt = document.querySelector("#agentFinishedAt");
const agentMessage = document.querySelector("#agentMessage");
const tabs = Array.from(document.querySelectorAll(".tab"));

let currentStatus = null;
let activePreviewKey = "raw";
let recognitionPollTimer = null;
let agentPollTimer = null;
let currentAgentRunning = false;
let recognitionStartPending = false;
let dashboardToken = window.sessionStorage.getItem("yqsDashboardToken") || "";

const metricLabels = [
  ["allImages", "当前图片总数", "四个目录合计"],
  ["raw", "images_raw", "等待压缩或识别"],
  ["recognized", "AI 识图完成", "images_recognized"],
  ["compressed", "压缩输出", "images_compressed"],
  ["finished", "Codex 成品图", "case_materials"],
];

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  })[char]);
}

function setStatus(message, type = "ok") {
  statusText.textContent = message;
  statusDot.className = `status-dot ${type}`;
}

function setBusy(isBusy) {
  refreshButton.disabled = isBusy;
  loadButton.disabled = isBusy;
  compressButton.disabled = isBusy;
  clearButton.disabled = isBusy;
  recognizeButton.disabled = isBusy || recognitionStartPending;
  feishuTestButton.disabled = isBusy;
  similarityButton.disabled = isBusy;
  agentButton.disabled = isBusy || currentAgentRunning;
}

function renderAgent(agent) {
  currentAgentRunning = Boolean(agent.running);
  agentRunning.textContent = agent.running ? "运行中" : "空闲";
  agentMode.textContent = agent.mode || "-";
  agentFinishedAt.textContent = agent.finished_at || "-";
  const message = agent.message || "尚未启动 DeerFlow 托管处理。";
  agentMessage.textContent = agent.fallback_reason
    ? `${message}（${agent.fallback_reason}）`
    : message;
  agentButton.disabled = currentAgentRunning;

  if (agent.running && agentPollTimer === null) {
    agentPollTimer = window.setInterval(fetchAgentStatus, 2000);
  }
  if (!agent.running && agentPollTimer !== null) {
    window.clearInterval(agentPollTimer);
    agentPollTimer = null;
    fetchStatus();
    fetchRecognitionStatus();
  }
}

function renderRecognition(recognition) {
  const total = Number(recognition.total || 0);
  const completed = Number(recognition.completed || 0);
  const failed = Number(recognition.failed || 0);
  const pendingCompressed = Number(recognition.pendingCompressed || 0);
  const percent = total > 0 ? Math.min(100, Math.round(((completed + failed) / total) * 100)) : 0;

  recognitionProgress.textContent = `${completed} / ${total}`;
  recognitionFailed.textContent = String(failed);
  recognitionPending.textContent = String(pendingCompressed);
  recognitionBar.style.width = `${percent}%`;
  recognitionMessage.textContent = recognition.currentFile
    ? `${recognition.message}（${recognition.currentFile}）`
    : recognition.message;
  const finished = total > 0 && (completed + failed) >= total;
  if (recognition.running || finished || !recognitionStartPending) {
    recognitionStartPending = false;
  }
  recognizeButton.disabled = recognition.running || recognitionStartPending;
  recognizeButton.title = recognition.running || recognitionStartPending
    ? "AI 识图任务正在运行"
    : "开始 AI 识图";

  if (recognition.running && recognitionPollTimer === null) {
    recognitionPollTimer = window.setInterval(fetchRecognitionStatus, 2000);
  }
  if (!recognition.running && recognitionPollTimer !== null) {
    window.clearInterval(recognitionPollTimer);
    recognitionPollTimer = null;
    fetchStatus();
  }
}

function renderFeishu(feishu) {
  feishuConfigured.textContent = feishu.configured ? "已配置" : "未配置";
  feishuReceiveType.textContent = feishu.receiveIdType || "chat_id";
  feishuAutoNotify.textContent = feishu.notifyOnRecognition ? "开启" : "关闭";
}

function renderSimilarity(similarity) {
  const counts = similarity.counts || {};
  const highCount = Number(counts.exact || 0) + Number(counts.same || 0) + Number(counts.high || 0);
  const pairs = similarity.pairs || [];

  similarityImageCount.textContent = String(similarity.imageCount || 0);
  similarityPairCount.textContent = String(similarity.pairCount || 0);
  similarityHighCount.textContent = String(highCount);
  similarityMessage.textContent = similarity.updatedAt
    ? `最近检查：${similarity.updatedAt}，范围：${similarity.directory || "image_compressor/images_compressed"}，报告：${similarity.csvPath}`
    : (similarity.message || "尚未检查相似图片。");

  if (pairs.length === 0) {
    similarityList.innerHTML = `<div class="empty-state">暂无疑似相似图片</div>`;
    return;
  }

  similarityList.innerHTML = pairs.map((pair) => `
    <article class="similarity-card">
      <div class="similarity-images">
        <div>
          <img class="thumb" src="${escapeHtml(pair.leftUrl)}" alt="${escapeHtml(pair.leftName)}" loading="lazy">
          <p class="file-name" title="${escapeHtml(pair.left)}">${escapeHtml(pair.leftName)}</p>
          <button class="mini-danger-button" type="button" data-delete-image="${escapeHtml(pair.left)}">删除这张</button>
        </div>
        <div>
          <img class="thumb" src="${escapeHtml(pair.rightUrl)}" alt="${escapeHtml(pair.rightName)}" loading="lazy">
          <p class="file-name" title="${escapeHtml(pair.right)}">${escapeHtml(pair.rightName)}</p>
          <button class="mini-danger-button" type="button" data-delete-image="${escapeHtml(pair.right)}">删除这张</button>
        </div>
      </div>
      <div class="similarity-info">
        <strong>${escapeHtml(pair.level)}</strong>
        <span>距离 ${escapeHtml(pair.distance)}</span>
        <p>${escapeHtml(pair.suggestion)}</p>
      </div>
    </article>
  `).join("");
}

function renderMetrics(status) {
  metricsGrid.innerHTML = metricLabels.map(([key, label, note]) => `
    <article class="metric-card">
      <p class="eyebrow">${label}</p>
      <div class="metric-value">${status.totals[key]}</div>
      <p class="metric-note">${note}</p>
    </article>
  `).join("");
}

function renderDirectories(status) {
  directoryGrid.innerHTML = status.directories.map((directory) => `
    <article class="directory-card">
      <h3>${escapeHtml(directory.label)}</h3>
      <p class="directory-path" title="${escapeHtml(directory.path)}">${escapeHtml(directory.path)}</p>
      <div class="directory-row">
        <div>
          <p class="eyebrow">图片</p>
          <div class="directory-count">${directory.count}</div>
        </div>
        <div>
          <p class="eyebrow">大小</p>
          <div class="directory-count">${directory.sizeLabel}</div>
        </div>
      </div>
    </article>
  `).join("");
}

function renderPreview(status) {
  const directory = status.directories.find((item) => item.key === activePreviewKey);
  if (!directory || directory.preview.length === 0) {
    previewGrid.innerHTML = `<div class="empty-state">这个目录暂时没有可预览图片</div>`;
    return;
  }

  previewGrid.innerHTML = directory.preview.map((image) => `
    <article class="preview-card">
      <img class="thumb" src="${escapeHtml(image.url)}" alt="${escapeHtml(image.name)}" loading="lazy">
      <p class="file-name" title="${escapeHtml(image.path)}">${escapeHtml(image.name)}</p>
    </article>
  `).join("");
}

function render(status) {
  currentStatus = status;
  updatedAt.textContent = `更新于 ${status.updatedAt}`;
  renderMetrics(status);
  renderDirectories(status);
  renderPreview(status);
}

async function fetchStatus() {
  setBusy(true);
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("读取状态失败");
    const status = await response.json();
    render(status);
    setStatus("素材状态已同步", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function fetchRecognitionStatus() {
  try {
    const response = await fetch("/api/recognition-status");
    if (!response.ok) throw new Error("读取识图状态失败");
    const recognition = await response.json();
    renderRecognition(recognition);
  } catch (error) {
    recognitionMessage.textContent = error.message;
  }
}

async function fetchFeishuStatus() {
  try {
    const response = await fetch("/api/feishu-status");
    if (!response.ok) throw new Error("读取飞书状态失败");
    const feishu = await response.json();
    renderFeishu(feishu);
  } catch (error) {
    feishuConfigured.textContent = "读取失败";
  }
}

async function fetchAgentStatus() {
  try {
    const response = await fetch("/api/agent-status");
    if (!response.ok) throw new Error("读取 DeerFlow 状态失败");
    const agent = await response.json();
    renderAgent(agent);
  } catch (error) {
    agentMessage.textContent = error.message;
  }
}

async function fetchSimilarityStatus() {
  try {
    const response = await fetch("/api/similarity-status");
    if (!response.ok) throw new Error("读取相似图片结果失败");
    const similarity = await response.json();
    renderSimilarity(similarity);
  } catch (error) {
    similarityMessage.textContent = error.message;
  }
}

async function postAction(url) {
  if (!ensureDashboardToken()) return;
  setBusy(true);
  try {
    const response = await fetch(url, postOptions());
    const payload = await response.json();
    if (response.status === 401) {
      const token = window.prompt(payload.message || "请输入 Dashboard 访问口令");
      if (token) {
        dashboardToken = token;
        window.sessionStorage.setItem("yqsDashboardToken", token);
        return postAction(url);
      }
    }
    if (!response.ok || !payload.ok) throw new Error(payload.message || "操作失败");
    render(payload.status);
    setStatus(payload.message, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

function postOptions() {
  const headers = {};
  if (dashboardToken) headers["X-YQS-Dashboard-Token"] = dashboardToken;
  return { method: "POST", headers };
}

function ensureDashboardToken() {
  if (dashboardToken) return true;
  const token = window.prompt("请输入 Dashboard 访问口令");
  if (!token) {
    setStatus("已取消：需要访问口令才能执行操作", "error");
    return false;
  }
  dashboardToken = token;
  window.sessionStorage.setItem("yqsDashboardToken", token);
  return true;
}

function jsonPostOptions(payload) {
  const options = postOptions();
  options.headers = {
    ...options.headers,
    "Content-Type": "application/json",
  };
  options.body = JSON.stringify(payload);
  return options;
}

refreshButton.addEventListener("click", fetchStatus);
loadButton.addEventListener("click", () => postAction("/api/load-images"));
compressButton.addEventListener("click", () => postAction("/api/compress-images"));
recognizeButton.addEventListener("click", async () => {
  if (recognitionStartPending || recognizeButton.disabled) return;
  if (!ensureDashboardToken()) return;
  recognitionStartPending = true;
  recognizeButton.disabled = true;
  recognizeButton.title = "AI 识图任务正在启动";
  recognitionMessage.textContent = "AI 识图任务正在启动...";
  setBusy(true);
  try {
    const response = await fetch("/api/start-recognition", postOptions());
    const payload = await response.json();
    if (response.status === 401) {
      const token = window.prompt(payload.message || "请输入 Dashboard 访问口令");
      if (token) {
        dashboardToken = token;
        window.sessionStorage.setItem("yqsDashboardToken", token);
        recognizeButton.click();
        return;
      }
    }
    if (!response.ok || !payload.ok) throw new Error(payload.message || "启动识图失败");
    render(payload.status);
    setStatus(payload.message, "ok");
    recognitionMessage.textContent = "AI 识图任务已启动，正在等待进度...";
    if (recognitionPollTimer === null) {
      recognitionPollTimer = window.setInterval(fetchRecognitionStatus, 2000);
    }
    window.setTimeout(fetchRecognitionStatus, 400);
  } catch (error) {
    recognitionStartPending = false;
    setStatus(error.message, "error");
    recognitionMessage.textContent = error.message;
  } finally {
    setBusy(false);
    recognizeButton.disabled = recognitionStartPending;
  }
});
agentButton.addEventListener("click", async () => {
  if (!ensureDashboardToken()) return;
  setBusy(true);
  try {
    const response = await fetch("/api/start-agent-workflow", postOptions());
    const payload = await response.json();
    if (response.status === 401) {
      const token = window.prompt(payload.message || "请输入 Dashboard 访问口令");
      if (token) {
        dashboardToken = token;
        window.sessionStorage.setItem("yqsDashboardToken", token);
        agentButton.click();
        return;
      }
    }
    if (!response.ok || !payload.ok) throw new Error(payload.message || "启动 DeerFlow 托管失败");
    render(payload.status);
    renderAgent(payload.agent);
    setStatus(payload.message, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
});
feishuTestButton.addEventListener("click", async () => {
  if (!ensureDashboardToken()) return;
  setBusy(true);
  try {
    const response = await fetch("/api/test-feishu", postOptions());
    const payload = await response.json();
    if (response.status === 401) {
      const token = window.prompt(payload.message || "请输入 Dashboard 访问口令");
      if (token) {
        dashboardToken = token;
        window.sessionStorage.setItem("yqsDashboardToken", token);
        feishuTestButton.click();
        return;
      }
    }
    if (!response.ok || !payload.ok) throw new Error(payload.message || "飞书测试失败");
    render(payload.status);
    renderFeishu(payload.feishu);
    setStatus(payload.message, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
});
similarityButton.addEventListener("click", async () => {
  if (!ensureDashboardToken()) return;
  setBusy(true);
  similarityMessage.textContent = "正在检查压缩图片相似度...";
  try {
    const response = await fetch("/api/check-similarity", postOptions());
    const payload = await response.json();
    if (response.status === 401) {
      const token = window.prompt(payload.message || "请输入 Dashboard 访问口令");
      if (token) {
        dashboardToken = token;
        window.sessionStorage.setItem("yqsDashboardToken", token);
        similarityButton.click();
        return;
      }
    }
    if (!response.ok || !payload.ok) throw new Error(payload.message || "相似图片检查失败");
    render(payload.status);
    renderSimilarity(payload.similarity);
    setStatus(payload.message, "ok");
  } catch (error) {
    setStatus(error.message, "error");
    similarityMessage.textContent = error.message;
  } finally {
    setBusy(false);
  }
});
similarityList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-image]");
  if (!button) return;

  const imagePath = button.dataset.deleteImage;
  const confirmed = window.confirm(`确认删除这张压缩图？\n${imagePath}`);
  if (!confirmed) return;
  if (!ensureDashboardToken()) return;

  setBusy(true);
  try {
    const response = await fetch("/api/delete-similar-image", jsonPostOptions({ path: imagePath }));
    const payload = await response.json();
    if (response.status === 401) {
      const token = window.prompt(payload.message || "请输入 Dashboard 访问口令");
      if (token) {
        dashboardToken = token;
        window.sessionStorage.setItem("yqsDashboardToken", token);
        button.click();
        return;
      }
    }
    if (!response.ok || !payload.ok) throw new Error(payload.message || "删除失败");
    render(payload.status);
    renderSimilarity(payload.similarity);
    setStatus(payload.message, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
});
clearButton.addEventListener("click", () => {
  const confirmed = window.confirm("确认清空 image_compressor/images_raw 中的所有文件？");
  if (confirmed) postAction("/api/clear-images-raw");
});

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    activePreviewKey = tab.dataset.previewKey;
    tabs.forEach((item) => item.classList.toggle("is-active", item === tab));
    if (currentStatus) renderPreview(currentStatus);
  });
});

fetchStatus();
fetchRecognitionStatus();
fetchFeishuStatus();
fetchAgentStatus();
fetchSimilarityStatus();
