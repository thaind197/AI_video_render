const API_BASE = ""; // Same origin / Relative path

let currentJobs = [];
let isEngineRunning = false;

// ── Global Fetch Interceptor: bắt 403 is_blocked từ middleware ──────────
// Khi version cũ, mọi POST/PUT/DELETE request sẽ bị middleware trả 403.
// Interceptor này tự động hiện modal "Yêu cầu cập nhật" thay vì lỗi generic.
const _originalFetch = window.fetch;
window.fetch = async function(...args) {
    const response = await _originalFetch.apply(this, args);
    if (response.status === 403) {
        try {
            const cloned = response.clone();
            const body = await cloned.json();
            if (body && body.is_blocked) {
                // Fetch version info để hiện modal đầy đủ
                try {
                    const vRes = await _originalFetch(`${API_BASE}/api/version`);
                    const vData = await vRes.json();
                    if (vData && vData.remote) {
                        showBlockedVersionModal(vData.remote);
                    }
                } catch(e) {
                    // Fallback: hiện thông báo từ detail
                    antd.message.error(body.detail || "Ứng dụng bị khóa. Vui lòng cập nhật phiên bản mới.");
                }
            }
        } catch(e) { /* ignore parse errors */ }
    }
    return response;
};

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatPromptText(text, maxLen = 50) {
    if (!text) return { shortText: "", fullText: "", isTruncated: false };
    const str = String(text).trim();
    if (str.length > maxLen) {
        return {
            shortText: str.substring(0, maxLen) + "...",
            fullText: str,
            isTruncated: true
        };
    }
    return {
        shortText: str,
        fullText: str,
        isTruncated: false
    };
}

// Ant Design Style Toast Notification Handler (Top-Right Corner)
function showToast(message, type = "info", duration = 4000) {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.className = "toast-container";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `ant-toast ant-toast-${type}`;

    let iconClass = "fa-circle-info";
    if (type === "success") iconClass = "fa-circle-check";
    if (type === "error") iconClass = "fa-circle-xmark";
    if (type === "warning") iconClass = "fa-triangle-exclamation";

    // Clean up leading emojis if duplicated
    const cleanMsg = String(message).replace(/^[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F1E6}-\u{1F1FF}\u{2705}\u{274C}\u{1F4BE}\u{1F6AA}\u{1F31F}\u{1F5D1}\u{2699}\u{1F31F}\u{26A0}\u{FE0F}]\s*/u, '');

    toast.innerHTML = `
        <i class="fa-solid ${iconClass} ant-toast-icon"></i>
        <div class="ant-toast-content">${cleanMsg}</div>
        <button class="ant-toast-close">&times;</button>
    `;

    const closeBtn = toast.querySelector(".ant-toast-close");
    const removeToast = () => {
        if (toast.classList.contains("toast-hiding")) return;
        toast.classList.add("toast-hiding");
        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 300);
    };

    closeBtn.addEventListener("click", removeToast);
    container.appendChild(toast);

    setTimeout(removeToast, duration);
}

// Custom Modal Confirm Popup (Promise-based replacement for native confirm)
function showConfirmModal(message, title = "Xác Nhận Thao Tác") {
    return new Promise((resolve) => {
        const modal = document.getElementById("confirm-modal");
        const titleEl = document.getElementById("confirm-modal-title");
        const msgEl = document.getElementById("confirm-modal-message");
        const btnOk = document.getElementById("confirm-modal-ok");
        const btnCancel = document.getElementById("confirm-modal-cancel");

        if (!modal || !btnOk || !btnCancel) {
            resolve(window.confirm(message));
            return;
        }

        titleEl.textContent = title;
        msgEl.textContent = message;

        modal.style.display = "flex";

        const cleanup = () => {
            modal.style.display = "none";
            btnOk.removeEventListener("click", onOk);
            btnCancel.removeEventListener("click", onCancel);
        };

        const onOk = () => {
            cleanup();
            resolve(true);
        };

        const onCancel = () => {
            cleanup();
            resolve(false);
        };

        btnOk.addEventListener("click", onOk);
        btnCancel.addEventListener("click", onCancel);
    });
}

// Custom Modal Prompt Popup (Promise-based replacement for native prompt)
function showPromptModal(message, defaultValue = "", title = "Nhập Thông Tin") {
    return new Promise((resolve) => {
        const modal = document.getElementById("prompt-modal");
        const titleEl = document.getElementById("prompt-modal-title");
        const msgEl = document.getElementById("prompt-modal-message");
        const inputEl = document.getElementById("prompt-modal-input");
        const btnOk = document.getElementById("prompt-modal-ok");
        const btnCancel = document.getElementById("prompt-modal-cancel");

        if (!modal || !inputEl || !btnOk || !btnCancel) {
            resolve(window.prompt(message, defaultValue));
            return;
        }

        titleEl.textContent = title;
        msgEl.textContent = message;
        inputEl.value = defaultValue;

        modal.style.display = "flex";
        setTimeout(() => inputEl.focus(), 100);

        const cleanup = () => {
            modal.style.display = "none";
            btnOk.removeEventListener("click", onOk);
            btnCancel.removeEventListener("click", onCancel);
            inputEl.removeEventListener("keyup", onKeyUp);
        };

        const onOk = () => {
            const val = inputEl.value;
            cleanup();
            resolve(val);
        };

        const onCancel = () => {
            cleanup();
            resolve(null);
        };

        const onKeyUp = (e) => {
            if (e.key === "Enter") onOk();
            if (e.key === "Escape") onCancel();
        };

        btnOk.addEventListener("click", onOk);
        btnCancel.addEventListener("click", onCancel);
        inputEl.addEventListener("keyup", onKeyUp);
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initForms();
    initModal();
    initEngineControl();
    initSettingsForm();
    initTableControls();

    // Initial Fetch & Start Real-time Polling every 2.5 seconds
    fetchJobsAndStats();
    fetchSocialStatus();
    fetchSettings();
    setInterval(fetchJobsAndStats, 2500);
    setInterval(fetchSocialStatus, 5000);
});

// Table Controls & Bulk Actions Bindings
function initTableControls() {
    const btnSelectAll = document.getElementById("btn-select-all-toggle");
    const selectAllCb = document.getElementById("select-all-jobs");

    const toggleSelectAll = (shouldSelect) => {
        const cbs = document.querySelectorAll(".job-checkbox");
        cbs.forEach(cb => {
            cb.checked = shouldSelect;
            const jid = parseInt(cb.getAttribute("data-id"));
            if (shouldSelect) {
                selectedConcatJobIds.add(jid);
            } else {
                selectedConcatJobIds.delete(jid);
            }
        });
        if (selectAllCb) selectAllCb.checked = shouldSelect;
        if (btnSelectAll) {
            btnSelectAll.innerHTML = shouldSelect
                ? `<i class="fa-solid fa-square-minus"></i> Bỏ Chọn Tất Cả`
                : `<i class="fa-regular fa-square-check"></i> Chọn Tất Cả`;
        }
        updateConcatToolbarUI();
    };

    if (btnSelectAll) {
        btnSelectAll.addEventListener("click", () => {
            const allCbs = document.querySelectorAll(".job-checkbox");
            const isAllSelected = allCbs.length > 0 && Array.from(allCbs).every(c => c.checked);
            toggleSelectAll(!isAllSelected);
        });
    }

    if (selectAllCb) {
        selectAllCb.addEventListener("change", (e) => {
            toggleSelectAll(e.target.checked);
        });
    }

    const btnBulkDelete = document.getElementById("btn-bulk-delete");
    if (btnBulkDelete) btnBulkDelete.addEventListener("click", bulkDeleteJobs);

    const btnBulkRetry = document.getElementById("btn-bulk-retry");
    if (btnBulkRetry) btnBulkRetry.addEventListener("click", bulkRetryJobs);

    const btnBulkPostFB = document.getElementById("btn-bulk-post-fb");
    if (btnBulkPostFB) btnBulkPostFB.addEventListener("click", bulkPostFBJobs);

    const btnRefresh = document.getElementById("btn-refresh-jobs");
    if (btnRefresh) btnRefresh.addEventListener("click", fetchJobsAndStats);

    const searchInput = document.getElementById("job-search-input");
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            const q = e.target.value.toLowerCase().trim();
            if (!q) {
                renderJobsTable(currentJobs);
            } else {
                const filtered = currentJobs.filter(j =>
                    (j.title && j.title.toLowerCase().includes(q)) ||
                    (j.veo_prompt && j.veo_prompt.toLowerCase().includes(q)) ||
                    (j.source_input && j.source_input.toLowerCase().includes(q)) ||
                    (j.status && j.status.toLowerCase().includes(q)) ||
                    (`job #${j.id}`.includes(q))
                );
                renderJobsTable(filtered);
            }
        });
    }
}

// Navigation & Tab Switching
function initNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanes = document.querySelectorAll(".tab-pane");
    const pageTitle = document.getElementById("page-title");
    const pageSubtitle = document.getElementById("page-subtitle");

    const titles = {
        dashboard: { title: "Tổng Quan System Automation", subtitle: "Hệ thống sản xuất 100 video 10s/ngày bằng Google Veo API & Auto Post" },
        generate: { title: "Sinh Kịch Bản & Veo Prompt", subtitle: "Tự động suy nghĩ kịch bản hàng loạt bằng Gemini 1.5 Flash" },
        clone: { title: "Clone Video TikTok / Reels", subtitle: "Tải video gốc, tách thoại Whisper & remake kịch bản 100% mới" },
        library: { title: "Thư Viện Video (9:16)", subtitle: "Quản lý và xem trước các video đã render thành công" },
        social: { title: "Cấu Hình Auto Post Social", subtitle: "Phiên đăng nhập trình duyệt bảo mật Facebook, TikTok, X" },
        settings: { title: "Cấu Hình Luồng & API", subtitle: "Quản lý API Key và số lượng Threads đa luồng" }
    };

    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const tabKey = item.getAttribute("data-tab");

            navItems.forEach(nav => nav.classList.remove("active"));
            tabPanes.forEach(pane => pane.classList.remove("active"));

            item.classList.add("active");
            const targetPane = document.getElementById(`tab-${tabKey}`);
            if (targetPane) targetPane.classList.add("active");

            if (titles[tabKey]) {
                pageTitle.textContent = titles[tabKey].title;
                pageSubtitle.textContent = titles[tabKey].subtitle;
            }
        });
    });
}

// Fetch Stats & Jobs from FastAPI Server
async function fetchJobsAndStats() {
    try {
        // Fetch Statistics
        const statsRes = await fetch(`${API_BASE}/api/stats`);
        if (statsRes.ok) {
            const statsData = await statsRes.json();
            updateStatisticsUI(statsData.data, statsData.is_engine_running, statsData.social);
        }

        // Fetch Jobs List
        const jobsRes = await fetch(`${API_BASE}/api/jobs`);
        if (jobsRes.ok) {
            const jobsData = await jobsRes.json();
            currentJobs = jobsData.data || [];
            renderJobsTable(currentJobs);
            renderLibraryGrid(currentJobs);
        }
    } catch (err) {
        console.warn("Không kết nối được API Backend:", err);
    }
}

// Update Statistics Cards & Indicators
function updateStatisticsUI(stats, running, social) {
    if (!stats) return;

    isEngineRunning = running;

    const total = Object.values(stats).reduce((a, b) => a + b, 0);
    const generating = (stats.GENERATING_VEO || 0) + (stats.SCRIPTED || 0) + (stats.QUOTA_WAIT || 0);
    const rendered = (stats.PROCESSING_FFMPEG || 0) + (stats.VEO_DONE || 0) + (stats.READY_TO_POST || 0) + (stats.PUBLISHED || 0);
    const published = stats.PUBLISHED || 0;
    const quotaWaiting = stats.QUOTA_WAIT || 0;

    const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setEl("stat-total", total);
    setEl("stat-generating", generating);
    setEl("stat-rendered", rendered);
    setEl("stat-published", published);

    // Update social sub-text
    if (social) {
        const subEl = document.getElementById("stat-social-sub");
        if (subEl) subEl.innerHTML = `<i class="fa-solid fa-circle-check"></i> FB: ${social.fb} | TikTok: ${social.tiktok} | X: ${social.x}`;
        const fbTag = document.getElementById("fb-posted-tag");
        if (fbTag) fbTag.textContent = `Đã Đăng: ${social.fb} Reels`;
        const ttTag = document.getElementById("tiktok-posted-tag");
        if (ttTag) ttTag.textContent = `Đã Đăng: ${social.tiktok} Videos`;
        const xTag = document.getElementById("x-posted-tag");
        if (xTag) xTag.textContent = `Đã Đăng: ${social.x} Videos`;
    }

    // Update progress bars
    const totalNz = total || 1;
    const updateBar = (barId, textId, count, label) => {
        const bar = document.getElementById(barId);
        const txt = document.getElementById(textId);
        const pct = Math.round((count / totalNz) * 100);
        if (bar) bar.style.width = pct + "%";
        if (txt) txt.textContent = `${pct}% (${count}/${total})`;
    };
    updateBar("progress-bar-script", "progress-text-script", (stats.SCRIPTED || 0), "Script");
    updateBar("progress-bar-veo", "progress-text-veo", (stats.GENERATING_VEO || 0) + (stats.VEO_DONE || 0), "Veo");
    updateBar("progress-bar-ffmpeg", "progress-text-ffmpeg", (stats.PROCESSING_FFMPEG || 0) + (stats.READY_TO_POST || 0), "FFmpeg");
    updateBar("progress-bar-social", "progress-text-social", published, "Social");

    // Show/hide quota warning banner
    let quotaBanner = document.getElementById("quota-wait-banner");
    if (quotaWaiting > 0) {
        if (!quotaBanner) {
            quotaBanner = document.createElement("div");
            quotaBanner.id = "quota-wait-banner";
            quotaBanner.style.cssText = "background:#fff7e6;border:1px solid #ffd591;border-radius:8px;padding:10px 16px;margin:10px 0;color:#d46b08;font-size:14px;display:flex;align-items:center;gap:8px;";
            // Append to stats-grid (the correct class in HTML)
            const statsGrid = document.querySelector(".stats-grid");
            if (statsGrid) statsGrid.parentNode.insertBefore(quotaBanner, statsGrid.nextSibling);
        }
        quotaBanner.innerHTML = `<i class="fa-solid fa-hourglass-half fa-spin"></i> <strong>${quotaWaiting} job</strong> đang chờ quota Veo API (429) — sẽ tự retry khi quota reset. <a href="https://ai.dev/rate-limit" target="_blank" style="color:#d46b08;text-decoration:underline;">Kiểm tra quota →</a>`;
        quotaBanner.style.display = "flex";
    } else if (quotaBanner) {
        quotaBanner.style.display = "none";
    }

    // Toggle Engine Button
    const btnEngine = document.getElementById("btn-run-all");
    if (btnEngine) {
        if (isEngineRunning) {
            btnEngine.className = "ant-btn ant-btn-primary ant-btn-lg";
            btnEngine.style.backgroundColor = "#ff4d4f";
            btnEngine.style.borderColor = "#ff4d4f";
            btnEngine.innerHTML = '<i class="fa-solid fa-stop"></i> Dừng Engine Đa Luồng';
        } else {
            btnEngine.className = "ant-btn ant-btn-primary ant-btn-lg";
            btnEngine.style.backgroundColor = "#1890ff";
            btnEngine.style.borderColor = "#1890ff";
            btnEngine.innerHTML = '<i class="fa-solid fa-play"></i> Khởi Chạy Engine Đa Luồng';
        }
    }
}

// Render Job Table Rows
function renderJobsTable(jobs) {
    const tbody = document.getElementById("job-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (jobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding: 20px;">Chưa có job nào trong database. Hãy bấm "Tạo Video Prompt" để bắt đầu!</td></tr>';
        return;
    }

    jobs.forEach(job => {
        const tr = document.createElement("tr");

        let statusTag = "";
        switch (job.status) {
            case "PUBLISHED":
                statusTag = '<span class="ant-tag ant-tag-success"><i class="fa-solid fa-check"></i> Đã Đăng Social</span>';
                break;
            case "PUBLISHING":
                statusTag = '<span class="ant-tag ant-tag-warning"><i class="fa-solid fa-paper-plane fa-spin"></i> Đang Đăng Bài...</span>';
                break;
            case "READY_TO_POST":
                statusTag = '<span class="ant-tag ant-tag-processing"><i class="fa-solid fa-circle-check"></i> Sẵn Sàng / Xong Video</span>';
                break;
            case "PROCESSING_FFMPEG":
                statusTag = '<span class="ant-tag ant-tag-warning"><i class="fa-solid fa-gear fa-spin"></i> FFmpeg Render Sub</span>';
                break;
            case "VEO_DONE":
                statusTag = '<span class="ant-tag ant-tag-warning"><i class="fa-solid fa-video"></i> Veo Raw Done</span>';
                break;
            case "GENERATING_VEO":
                statusTag = '<span class="ant-tag ant-tag-warning"><i class="fa-solid fa-spinner fa-spin"></i> Gen Veo API</span>';
                break;
            case "SCRIPTED":
                statusTag = '<span class="ant-tag ant-tag-processing">Đã Sinh Kịch Bản</span>';
                break;
            case "QUOTA_WAIT":
                statusTag = `<span class="ant-tag ant-tag-quota" title="${job.error_msg || 'Veo API quota exceeded — tự retry khi quota reset'}"><i class="fa-solid fa-hourglass-half fa-spin"></i> ⏳ Chờ Quota API</span>`;
                break;
            case "FAILED":
                statusTag = `<span class="ant-tag ant-tag-error" title="${job.error_msg || ''}"><i class="fa-solid fa-circle-xmark"></i> Thất Bại</span>`;
                break;
            default:
                statusTag = '<span class="ant-tag">Chờ Xử Lý (Pending)</span>';
        }

        const typeBadge = job.source_type === "PROMPT"
            ? '<span class="ant-tag ant-tag-processing">PROMPT</span>'
            : '<span class="ant-tag ant-tag-warning">CLONE</span>';

        // For PENDING status, show different label based on job type
        if (job.status === "PENDING") {
            statusTag = job.source_type === "CLONE"
                ? '<span class="ant-tag ant-tag-cyan"><i class="fa-solid fa-download fa-spin"></i> Đang Tải Video...</span>'
                : '<span class="ant-tag"><i class="fa-solid fa-clock"></i> Chờ Sinh Prompt...</span>';
        }

        const fbIcon = job.fb_posted ? '<i class="fa-brands fa-facebook text-blue" title="Facebook Reels"></i> ' : '';
        const tiktokIcon = job.tiktok_posted ? '<i class="fa-brands fa-tiktok" style="color:#ee1d52;" title="TikTok"></i> ' : '';
        const xIcon = job.x_posted ? '<i class="fa-brands fa-x-twitter" title="X"></i>' : '';
        const platformsStr = (fbIcon || tiktokIcon || xIcon) ? `${fbIcon}${tiktokIcon}${xIcon}` : '-';

        // Prompt column: CLONE jobs don't have prompts, show source URL excerpt instead
        let promptExcerpt;
        if (job.source_type === "CLONE") {
            const srcShort = (job.source_input || '').replace(/https?:\/\/(www\.)?/, '');
            const formatted = formatPromptText(srcShort, 50);
            promptExcerpt = `<span style="color:var(--text-secondary);font-size:11px;" title="${escapeHtml(formatted.fullText)}"><i class="fa-brands fa-tiktok"></i> ${escapeHtml(formatted.shortText) || 'Clone video gốc'}</span>`;
        } else {
            const fullP = job.veo_prompt || job.source_input || "Chờ sinh prompt...";
            const formatted = formatPromptText(fullP, 50);
            promptExcerpt = `<span style="color:var(--text-secondary);font-size:11px;cursor:pointer;" title="${escapeHtml(formatted.fullText)}">${escapeHtml(formatted.shortText)}</span>`;
        }
        const titleFormatted = formatPromptText(job.title || job.source_input || `Job #${job.id}`, 50);
        const durationLabel = job.duration_sec != null ? `${job.duration_sec}s` : "-";

        const isChecked = selectedConcatJobIds.has(job.id) ? "checked" : "";
        tr.innerHTML = `
            <td style="text-align: center;">
                <input type="checkbox" class="job-checkbox" data-id="${job.id}" ${isChecked} style="cursor: pointer; transform: scale(1.2);">
            </td>
            <td><strong>#${job.id}</strong></td>
            <td>${typeBadge}</td>
            <td><strong title="${escapeHtml(titleFormatted.fullText)}" style="cursor:pointer;">${escapeHtml(titleFormatted.shortText)}</strong></td>
            <td style="max-width: 250px; font-size: 11px; color: var(--text-secondary);">${promptExcerpt}</td>
            <td>${durationLabel}</td>
            <td>${statusTag}</td>
            <td style="font-size: 16px;">${platformsStr}</td>
            <td>
                <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                    <button class="ant-btn ant-btn-default btn-preview" onclick="openPreviewModal(${job.id})">
                        <i class="fa-solid fa-eye"></i> Xem
                    </button>
                    ${(job.status === 'READY_TO_POST' || job.status === 'PUBLISHED' || job.status === 'VEO_DONE') ? `
                    <button class="ant-btn" style="background:#1877f2;color:#fff;border-color:#1877f2;" onclick="postVideoToFB(${job.id})" title="Đăng lên Facebook Reels">
                        <i class="fa-brands fa-facebook"></i> Đăng FB
                    </button>
                    <button class="ant-btn" style="background:#fe2c55;color:#fff;border-color:#fe2c55;" onclick="postVideoToTikTok(${job.id})" title="Đăng lên TikTok Channels">
                        <i class="fa-brands fa-tiktok"></i> Đăng TikTok
                    </button>` : ''}
                    <button class="ant-btn ant-btn-danger btn-delete-job" onclick="deleteJob(${job.id})" title="Xóa Job #${job.id}">
                        <i class="fa-solid fa-trash"></i> Xóa
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });

    // Attach checkbox toggle listeners
    tbody.querySelectorAll(".job-checkbox").forEach(cb => {
        cb.addEventListener("change", (e) => {
            const jid = parseInt(e.target.getAttribute("data-id"));
            if (e.target.checked) {
                selectedConcatJobIds.add(jid);
            } else {
                selectedConcatJobIds.delete(jid);
            }
            updateConcatToolbarUI();
        });
    });

    // Sync select-all checkbox & button state
    const selectAllCb = document.getElementById("select-all-jobs");
    const btnSelectAll = document.getElementById("btn-select-all-toggle");
    const allCbs = tbody.querySelectorAll(".job-checkbox");
    const isAllChecked = allCbs.length > 0 && Array.from(allCbs).every(c => c.checked);

    if (selectAllCb) selectAllCb.checked = isAllChecked;
    if (btnSelectAll) {
        btnSelectAll.innerHTML = isAllChecked
            ? `<i class="fa-solid fa-square-minus"></i> Bỏ Chọn Tất Cả`
            : `<i class="fa-regular fa-square-check"></i> Chọn Tất Cả`;
    }
}

// Single Job Deletion Handler
async function deleteJob(jobId) {
    const confirmed = await showConfirmModal(`Bạn có chắc chắn muốn xóa Job #${jobId}? Hành động này sẽ xóa cả file video/audio liên quan.`, "Xác Nhận Xóa Job");
    if (!confirmed) return;
    try {
        const res = await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, "success");
            fetchJobsAndStats();
        } else {
            showToast(data.detail, "error");
        }
    } catch (err) {
        showToast(`Lỗi kết nối xóa Job: ${err.message}`, "error");
    }
}

// Manual Test Post to Social Platform
async function testPostJob(jobId, platform = 'facebook') {
    const platformName = platform === 'facebook' ? 'Facebook Reels' : platform === 'tiktok' ? 'TikTok' : 'X (Twitter)';
    const confirmed = await showConfirmModal(
        `Đăng Job #${jobId} lên ${platformName} ngay bây giờ? (Chạy trong nền, có thể mất vài phút)`,
        `Xác Nhận Đăng Bài`
    );
    if (!confirmed) return;
    try {
        showToast(`Đang gửi lệnh đăng Job #${jobId} lên ${platformName}...`, 'info');
        const res = await fetch(`${API_BASE}/api/social/test-post`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: jobId, platform })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
        } else {
            showToast(data.detail || 'Lỗi đăng bài', 'error');
        }
    } catch (err) {
        showToast(`Lỗi kết nối: ${err.message}`, 'error');
    }
}

let selectedConcatJobIds = new Set();

function updateConcatToolbarUI() {
    // Update ALL elements with selected-count-badge id (there are 2: in dashboard toolbar & library toolbar)
    const badges = document.querySelectorAll("#selected-count-badge");
    const toolbar = document.getElementById("bulk-actions-toolbar");
    const btnConcat = document.getElementById("btn-concat-selected");
    const btnDelete = document.getElementById("btn-bulk-delete");
    const btnDeleteSelected = document.getElementById("btn-delete-selected");
    const count = selectedConcatJobIds.size;

    badges.forEach(badge => {
        if (count > 0) {
            badge.style.display = "inline-block";
            badge.textContent = `Đã chọn: ${count} video`;
        } else {
            badge.style.display = "none";
        }
    });

    if (toolbar) {
        toolbar.style.display = count > 0 ? "flex" : "none";
    }

    if (btnDelete) {
        btnDelete.disabled = (count === 0);
        btnDelete.innerHTML = `<i class="fa-solid fa-trash"></i> Xóa (${count}) Video Đã Chọn`;
    }

    // Also enable/disable the library delete button
    if (btnDeleteSelected) {
        btnDeleteSelected.disabled = (count === 0);
    }

    if (btnConcat) {
        if (count >= 2) {
            btnConcat.disabled = false;
            btnConcat.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Ghép ${count} Video Thành 1 Video Dài`;
        } else {
            btnConcat.disabled = true;
            btnConcat.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Ghép Video Đã Chọn`;
        }
    }
}

// Bulk Actions Handlers
async function bulkDeleteJobs() {
    const ids = Array.from(selectedConcatJobIds);
    if (ids.length === 0) return;
    const confirmed = await showConfirmModal(`Bạn có chắc chắn muốn xóa ${ids.length} Job đã chọn? Hành động này không thể hoàn tác.`, `Xóa ${ids.length} Jobs`);
    if (!confirmed) return;

    try {
        showToast(`Đang xóa ${ids.length} Jobs...`, "info");
        const res = await fetch(`${API_BASE}/api/jobs/delete-batch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ job_ids: ids })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, "success");
            selectedConcatJobIds.clear();
            updateConcatToolbarUI();
            fetchJobsAndStats();
        } else {
            showToast(data.detail || "Lỗi xóa hàng loạt", "error");
        }
    } catch (err) {
        showToast(`Lỗi kết nối: ${err.message}`, "error");
    }
}

async function bulkRetryJobs() {
    const ids = Array.from(selectedConcatJobIds);
    if (ids.length === 0) return;
    const confirmed = await showConfirmModal(`Đặt lại (Retry) ${ids.length} Job đã chọn để chạy lại tự động?`, `Retry ${ids.length} Jobs`);
    if (!confirmed) return;

    try {
        showToast(`Đang đặt lại ${ids.length} Jobs...`, "info");
        const res = await fetch(`${API_BASE}/api/jobs/retry-batch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ job_ids: ids })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, "success");
            selectedConcatJobIds.clear();
            updateConcatToolbarUI();
            fetchJobsAndStats();
        } else {
            showToast(data.detail || "Lỗi retry hàng loạt", "error");
        }
    } catch (err) {
        showToast(`Lỗi kết nối: ${err.message}`, "error");
    }
}

async function bulkPostFBJobs() {
    const ids = Array.from(selectedConcatJobIds);
    if (ids.length === 0) return;
    const confirmed = await showConfirmModal(`Đăng ${ids.length} Job đã chọn lên Facebook Reels ngay bây giờ?`, `Đăng ${ids.length} Jobs Lên FB`);
    if (!confirmed) return;

    showToast(`Đang xếp hàng đăng ${ids.length} video lên Facebook Reels...`, "info");
    for (const id of ids) {
        testPostJob(id, 'facebook');
    }
}


// Render Video Library 9:16 Grid (Gom nhóm theo Prompt / Topic)
let expandedGroupKeys = new Set();
let lastLibrarySignature = "";

function renderLibraryGrid(jobs) {
    const grid = document.getElementById("library-video-grid");
    if (!grid) return;

    const readyJobs = jobs.filter(j => j.status === "PUBLISHED" || j.status === "READY_TO_POST" || j.status === "VEO_DONE");

    // So sánh signature để tránh giật/xóa DOM khi không có thay đổi
    const currentSignature = JSON.stringify(readyJobs.map(j => [j.id, j.status, j.fb_posted, j.tiktok_posted, Array.from(selectedConcatJobIds).includes(j.id)]));
    if (currentSignature === lastLibrarySignature && grid.children.length > 0) {
        return; // Không cần render lại nếu dữ liệu hoàn toàn giống hệt
    }
    lastLibrarySignature = currentSignature;

    grid.innerHTML = "";

    if (readyJobs.length === 0) {
        grid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-secondary);">Chưa có video 9:16 nào được render thành công.</div>';
        return;
    }

    // Gom nhóm theo Prompt / Topic (source_input hoặc title gốc)
    const grouped = {};
    readyJobs.forEach(job => {
        const key = (job.source_input || job.title || "Khác").trim();
        if (!grouped[key]) grouped[key] = [];
        grouped[key].push(job);
    });

    Object.keys(grouped).forEach(promptKey => {
        const groupJobs = grouped[promptKey];
        const { shortText, fullText } = formatPromptText(promptKey, 50);

        const isExpanded = expandedGroupKeys.has(promptKey);
        const groupCard = document.createElement("div");
        groupCard.className = `prompt-collapse-item ${isExpanded ? 'expanded' : 'collapsed'}`;

        const allGroupSelected = groupJobs.every(j => selectedConcatJobIds.has(j.id));

        groupCard.innerHTML = `
            <div class="prompt-collapse-header">
                <div class="prompt-collapse-title-area">
                    <span class="prompt-collapse-chevron"><i class="fa-solid fa-chevron-down"></i></span>
                    <input type="checkbox" class="group-select-all-cb" ${allGroupSelected ? 'checked' : ''} style="transform: scale(1.25); cursor: pointer;" title="Tích chọn tất cả video trong nhóm prompt này">
                    <h3 style="margin: 0; font-size: 14px; font-weight: 600; color: var(--text-primary);" title="${escapeHtml(fullText)}">
                        <i class="fa-solid fa-folder-open" style="color: #1890ff; margin-right: 6px;"></i>
                        <span class="prompt-title-text">${escapeHtml(shortText)}</span>
                    </h3>
                    <span class="ant-tag ant-tag-processing" style="font-size: 11px; margin-left: 4px; border-radius: 10px;">${groupJobs.length} video</span>
                </div>
                <div style="display: flex; gap: 8px; align-items: center;" onclick="event.stopPropagation()">
                    <button class="ant-btn ant-btn-default btn-concat-group-fast" style="font-size: 12px; padding: 3px 12px; height: 30px; border-radius: 6px;">
                        <i class="fa-solid fa-wand-magic-sparkles" style="color: #faad14;"></i> Ghép Nhóm Này (${groupJobs.length})
                    </button>
                </div>
            </div>
            <div class="prompt-collapse-body">
                <div class="group-video-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px;">
                </div>
            </div>
        `;

        const groupVideoGrid = groupCard.querySelector(".group-video-grid");
        const groupCb = groupCard.querySelector(".group-select-all-cb");
        const headerEl = groupCard.querySelector(".prompt-collapse-header");

        // Toggle Expand/Collapse khi click vào Header (ngoại trừ checkbox và nút bấm)
        headerEl.addEventListener("click", (e) => {
            if (e.target.closest(".group-select-all-cb") || e.target.closest("button")) return;
            groupCard.classList.toggle("collapsed");
            groupCard.classList.toggle("expanded");
            if (groupCard.classList.contains("expanded")) {
                expandedGroupKeys.add(promptKey);
            } else {
                expandedGroupKeys.delete(promptKey);
            }
        });


        // Click checkbox nhóm chọn tất cả video trong nhóm (không trigger toggle collapse)
        groupCb.addEventListener("click", (e) => {
            e.stopPropagation();
        });
        groupCb.addEventListener("change", (e) => {
            const isChecked = e.target.checked;
            groupJobs.forEach(j => {
                if (isChecked) {
                    selectedConcatJobIds.add(j.id);
                } else {
                    selectedConcatJobIds.delete(j.id);
                }
            });
            groupCard.querySelectorAll(".video-card-checkbox").forEach(cb => {
                cb.checked = isChecked;
                const card = cb.closest(".video-card-916");
                if (card) {
                    if (isChecked) card.classList.add("selected");
                    else card.classList.remove("selected");
                }
            });
            updateConcatToolbarUI();
        });

        // Nút ghép nhanh tất cả video trong nhóm prompt này
        const btnGroupConcat = groupCard.querySelector(".btn-concat-group-fast");
        btnGroupConcat.addEventListener("click", (e) => {
            e.stopPropagation();
            selectedConcatJobIds.clear();
            groupJobs.forEach(j => selectedConcatJobIds.add(j.id));
            updateConcatToolbarUI();
            const btnConcat = document.getElementById("btn-concat-selected");
            if (btnConcat) btnConcat.click();
        });

        // Render từng card video thuộc nhóm này
        groupJobs.forEach(job => {
            const isSelected = selectedConcatJobIds.has(job.id);
            const card = document.createElement("div");
            card.className = `video-card-916 ${isSelected ? 'selected' : ''}`;

            const fbBtn = job.fb_posted
                ? `<span style="font-size:11px;color:#52c41a;"><i class="fa-solid fa-circle-check"></i> FB</span>`
                : `<button class="ant-btn" style="font-size:11px;padding:3px 8px;height:auto;background:#1877f2;color:#fff;border-color:#1877f2;"
                    onclick="event.stopPropagation(); postVideoToFB(${job.id})">
                    <i class="fa-brands fa-facebook"></i> Đăng FB
                   </button>`;

            const tiktokBtn = job.tiktok_posted
                ? `<span style="font-size:11px;color:#52c41a;"><i class="fa-solid fa-circle-check"></i> TikTok</span>`
                : `<button class="ant-btn" style="font-size:11px;padding:3px 8px;height:auto;background:#fe2c55;color:#fff;border-color:#fe2c55;"
                    onclick="event.stopPropagation(); postVideoToTikTok(${job.id})">
                    <i class="fa-brands fa-tiktok"></i> Đăng TikTok
                   </button>`;

            const titleObj = formatPromptText(job.title || `Video #${job.id}`, 50);

            card.innerHTML = `
                <input type="checkbox" class="video-card-checkbox" data-job-id="${job.id}" ${isSelected ? 'checked' : ''}>
                <div class="video-thumbnail-916">
                    <i class="fa-solid fa-circle-play play-icon"></i>
                </div>
                <div class="video-card-info">
                    <h4 title="${escapeHtml(titleObj.fullText)}" style="cursor:pointer;">${escapeHtml(titleObj.shortText)}</h4>
                    <small style="color: var(--text-secondary);">${job.duration_sec != null ? job.duration_sec + 's' : ''} • 9:16 HD</small>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center;">
                        ${fbBtn}
                        ${tiktokBtn}
                    </div>
                </div>
            `;

            const cb = card.querySelector(".video-card-checkbox");
            cb.addEventListener("click", (e) => {
                e.stopPropagation();
                if (cb.checked) {
                    selectedConcatJobIds.add(job.id);
                    card.classList.add("selected");
                } else {
                    selectedConcatJobIds.delete(job.id);
                    card.classList.remove("selected");
                }
                groupCb.checked = groupJobs.every(j => selectedConcatJobIds.has(j.id));
                updateConcatToolbarUI();
            });

            card.addEventListener("click", (e) => {
                if (e.target === cb) return;
                openPreviewModal(job.id);
            });

            groupVideoGrid.appendChild(card);
        });

        grid.appendChild(groupCard);
    });

    updateConcatToolbarUI();
}

// Quick FB post from library card (no confirm dialog, direct post)
async function postVideoToFB(jobId) {
    const btnEls = document.querySelectorAll(`button[onclick*="postVideoToFB(${jobId})"]`);
    btnEls.forEach(b => { b.disabled = true; b.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang đăng...'; });

    try {
        showToast(`Đang gửi lệnh đăng Job #${jobId} lên Facebook Reels...`, 'info');
        const res = await fetch(`${API_BASE}/api/social/test-post`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: jobId, platform: 'facebook' })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`✅ ${data.message}`, 'success');
            // Update button to show "đang xử lý"
            btnEls.forEach(b => { b.style.background = '#faad14'; b.style.borderColor = '#faad14'; b.innerHTML = '<i class="fa-solid fa-clock"></i> Đang xử lý...'; });
            // Auto refresh after 30s
            setTimeout(() => fetchJobsAndStats(), 30000);
        } else {
            showToast(data.detail || 'Lỗi đăng bài', 'error');
            btnEls.forEach(b => { b.disabled = false; b.innerHTML = '<i class="fa-brands fa-facebook"></i> Đăng FB'; });
        }
    } catch (err) {
        showToast(`Lỗi kết nối: ${err.message}`, 'error');
        btnEls.forEach(b => { b.disabled = false; b.innerHTML = '<i class="fa-brands fa-facebook"></i> Đăng FB'; });
    }
}

// Form Handlers (Call REST API)
function initForms() {
    // Interactive Checkbox Card Active state handler
    document.querySelectorAll(".ant-checkbox-card input[type='checkbox']").forEach(input => {
        input.addEventListener("change", () => {
            const card = input.closest(".ant-checkbox-card");
            if (card) {
                if (input.checked) {
                    card.classList.add("active");
                } else {
                    card.classList.remove("active");
                }
            }
        });
    });

    const promptForm = document.getElementById("form-generate-prompt");
    if (promptForm) {
        promptForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const topic = document.getElementById("prompt-topic").value;
            const count = parseInt(document.getElementById("prompt-count").value) || 10;

            const selectedStyles = Array.from(document.querySelectorAll("input[name='prompt-style']:checked")).map(el => el.value);
            const selectedVoices = Array.from(document.querySelectorAll("input[name='prompt-voice']:checked")).map(el => el.value);

            // Optional checkboxes: Fallback to defaults if none checked
            const finalStyles = selectedStyles.length > 0 ? selectedStyles : ["cinematic"];
            const finalVoices = selectedVoices.length > 0 ? selectedVoices : ["vi-VN-HoaiMyNeural"];

            const keepContextEl = document.getElementById("prompt-keep-context");
            const customContextEl = document.getElementById("prompt-custom-context");
            const keepContext = keepContextEl ? keepContextEl.checked : true;
            const customContext = customContextEl ? customContextEl.value.trim() : "";

            const aspectRatio = document.getElementById("prompt-aspect-ratio") ? document.getElementById("prompt-aspect-ratio").value : "9:16";
            const duration = document.getElementById("prompt-duration") ? parseInt(document.getElementById("prompt-duration").value) : 8;
            const variants = document.getElementById("prompt-variants") ? parseInt(document.getElementById("prompt-variants").value) : 1;
            const veoModel = document.getElementById("prompt-veo-model") ? document.getElementById("prompt-veo-model").value : "veo-3.1-lite-generate-preview";
            const quality = document.getElementById("labs-quality-select") ? document.getElementById("labs-quality-select").value : "1080p";

            try {
                const res = await fetch(`${API_BASE}/api/generate-prompt`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        topic,
                        count,
                        styles: finalStyles,
                        voices: finalVoices,
                        keep_context: keepContext,
                        custom_context: customContext,
                        aspect_ratio: aspectRatio,
                        duration: duration,
                        variants: variants,
                        veo_model: veoModel,
                        quality: quality
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message, "success");
                    fetchJobsAndStats();
                } else {
                    showToast(data.detail, "error");
                }
            } catch (err) {
                showToast(`Lỗi kết nối API: ${err.message}`, "error");
            }
        });
    }

    // Interactive Toggle Helper for Clone Feature Boxes
    ['toggle-voiceover', 'toggle-subtitle'].forEach(id => {
        const label = document.getElementById(id);
        if (!label) return;
        const cb = label.querySelector('input[type="checkbox"]');
        const indicator = label.querySelector('.feature-toggle-indicator');

        const updateUI = () => {
            if (cb.checked) {
                label.classList.add('active');
                label.classList.remove('inactive');
                if (indicator) indicator.textContent = '✓ Bật';
            } else {
                label.classList.add('inactive');
                label.classList.remove('active');
                if (indicator) indicator.textContent = '✕ Tắt';
            }
        };
        if (cb) {
            cb.addEventListener('change', updateUI);
            updateUI();
        }
    });

    const cloneForm = document.getElementById("form-clone-video");
    if (cloneForm) {
        cloneForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const url = document.getElementById("clone-url").value;
            const voiceoverCb = document.getElementById("clone-voiceover");
            const subtitleCb = document.getElementById("clone-subtitle");

            const add_voiceover = voiceoverCb ? voiceoverCb.checked : false;
            const add_subtitle = subtitleCb ? subtitleCb.checked : false;

            try {
                const res = await fetch(`${API_BASE}/api/clone-video`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        url,
                        add_voiceover,
                        add_subtitle
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message, "success");
                    fetchJobsAndStats();
                } else {
                    showToast(data.detail, "error");
                }
            } catch (err) {
                showToast(`Lỗi kết nối API: ${err.message}`, "error");
            }
        });
    }

    // Video Concatenation Button Handler
    const btnConcat = document.getElementById("btn-concat-selected");
    if (btnConcat) {
        btnConcat.addEventListener("click", async () => {
            const ids = Array.from(selectedConcatJobIds);
            if (ids.length < 2) {
                showToast("Vui lòng chọn ít nhất 2 video để ghép nối!", "warning");
                return;
            }

            const title = await showPromptModal("Nhập tiêu đề cho video tổng hợp (tùy chọn):", `Video Tổng Hợp (${ids.length} đoạn)`, "Ghép Video Đã Chọn");
            if (title === null) return;

            btnConcat.disabled = true;
            btnConcat.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang ghép video...';

            try {
                const res = await fetch(`${API_BASE}/api/concat-videos`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        job_ids: ids,
                        title: title.trim()
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message, "success");
                    selectedConcatJobIds.clear();
                    await fetchJobsAndStats();
                    if (data.job_id) {
                        openPreviewModal(data.job_id);
                    }
                } else {
                    showToast(data.detail, "error");
                }
            } catch (err) {
                showToast(`Lỗi kết nối ghép video: ${err.message}`, "error");
            } finally {
                updateConcatToolbarUI();
            }
        });
    }

    // Batch Video Deletion Button Handler
    const btnDeleteBatch = document.getElementById("btn-delete-selected");
    if (btnDeleteBatch) {
        btnDeleteBatch.addEventListener("click", async () => {
            const ids = Array.from(selectedConcatJobIds);
            if (ids.length === 0) {
                showToast("Vui lòng chọn ít nhất 1 video để xóa!", "warning");
                return;
            }

            const confirmed = await showConfirmModal(`Bạn có chắc chắn muốn xóa ${ids.length} video đã chọn? Các file video/audio tương ứng sẽ bị xóa vĩnh viễn.`, "Xác Nhận Xóa Hàng Loạt");
            if (!confirmed) return;

            btnDeleteBatch.disabled = true;
            btnDeleteBatch.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang xóa...';

            try {
                const res = await fetch(`${API_BASE}/api/jobs/delete-batch`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ job_ids: ids })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message, "success");
                    selectedConcatJobIds.clear();
                    await fetchJobsAndStats();
                } else {
                    showToast(data.detail, "error");
                }
            } catch (err) {
                showToast(`Lỗi kết nối xóa video: ${err.message}`, "error");
            } finally {
                updateConcatToolbarUI();
            }
        });
    }

    // Social Login Buttons
    document.querySelectorAll(".btn-login-social").forEach(btn => {
        btn.addEventListener("click", async () => {
            const platform = btn.getAttribute("data-platform");
            try {
                const res = await fetch(`${API_BASE}/api/social/login`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ platform })
                });
                const data = await res.json();
                showToast(data.message, "info");
                fetchSocialStatus();
            } catch (err) {
                showToast(`Lỗi mở trình duyệt đăng nhập: ${err.message}`, "error");
            }
        });
    });

    // Social Logout Buttons
    document.querySelectorAll(".btn-logout-social").forEach(btn => {
        btn.addEventListener("click", async () => {
            const platform = btn.getAttribute("data-platform");
            const confirmed = await showConfirmModal(`Bạn có chắc chắn muốn đăng xuất tài khoản ${platform}?`, "Xác Nhận Đăng Xuất");
            if (!confirmed) return;
            try {
                const res = await fetch(`${API_BASE}/api/social/logout`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ platform })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message, "success");
                    fetchSocialStatus();
                } else {
                    showToast(data.detail, "error");
                }
            } catch (err) {
                showToast(`Lỗi kết nối API: ${err.message}`, "error");
            }
        });
    });
}

// Fetch Real-time Social Session Status
async function fetchSocialStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/social/status`);
        if (!res.ok) return;
        const result = await res.json();
        const data = result.data;
        if (!data) return;

        updatePlatformStatusTag("fb-status-tag", data.facebook);
        updatePlatformStatusTag("tiktok-status-tag", data.tiktok);
        updatePlatformStatusTag("x-status-tag", data.x);
        updatePlatformStatusTag("labs-google-status-tag", data.labs_google);
    } catch (err) {
        console.warn("Lỗi kiểm tra trạng thái social:", err);
    }
}

function updatePlatformStatusTag(tagId, isLoggedIn) {
    const el = document.getElementById(tagId);
    if (!el) return;
    if (isLoggedIn) {
        el.className = "ant-tag ant-tag-success";
        el.innerHTML = '<i class="fa-solid fa-check"></i> Đã Đăng Nhập';
    } else {
        el.className = "ant-tag ant-tag-default";
        el.innerHTML = '<i class="fa-solid fa-circle-xmark"></i> Chưa Đăng Nhập';
    }
}

// Engine Control Toggle
function initEngineControl() {
    const btnEngine = document.getElementById("btn-run-all");
    if (btnEngine) {
        btnEngine.addEventListener("click", async () => {
            try {
                const res = await fetch(`${API_BASE}/api/engine/toggle`, { method: "POST" });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message, "info");
                    fetchJobsAndStats();
                }
            } catch (err) {
                showToast(`Lỗi khởi chạy Engine: ${err.message}`, "error");
            }
        });
    }
}

// Modal Preview Handler
function initModal() {
    const modal = document.getElementById("video-modal");
    const closeBtn = document.getElementById("modal-close-btn");

    const closeVideoModal = () => {
        if (!modal) return;
        modal.style.display = "none";
        const videoEl = modal.querySelector("video");
        if (videoEl) { videoEl.pause(); videoEl.src = ""; }
    };

    if (closeBtn && modal) {
        closeBtn.onclick = closeVideoModal;
    }

    // Click outside modal container to close
    if (modal) {
        modal.addEventListener("click", (e) => {
            if (e.target === modal) closeVideoModal();
        });
    }

    // ESC key closes all modals
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeVideoModal();
            const confirmModal = document.getElementById("confirm-modal");
            if (confirmModal && confirmModal.style.display !== "none") {
                const cancelBtn = document.getElementById("confirm-modal-cancel");
                if (cancelBtn) cancelBtn.click();
            }
            const promptModal = document.getElementById("prompt-modal");
            if (promptModal && promptModal.style.display !== "none") {
                const cancelBtn = document.getElementById("prompt-modal-cancel");
                if (cancelBtn) cancelBtn.click();
            }
            closeFbProfileModal();
        }
    });
}

function openPreviewModal(jobId) {
    const job = currentJobs.find(j => j.id === jobId);
    if (!job) return;

    document.getElementById("modal-video-title").textContent = job.title || `Job #${job.id}`;
    document.getElementById("modal-video-desc").textContent = job.voiceover_text || job.veo_prompt || "Không có mô tả";

    // Tags may be a JSON string from SQLite — parse it
    let tagsArr = [];
    if (Array.isArray(job.tags)) {
        tagsArr = job.tags;
    } else if (typeof job.tags === 'string' && job.tags.trim()) {
        try { tagsArr = JSON.parse(job.tags); } catch(e) { tagsArr = []; }
    }
    let tagsHtml = tagsArr.length > 0
        ? tagsArr.map(t => `<span class="ant-tag ant-tag-processing">${t}</span>`).join(" ")
        : '<span class="ant-tag ant-tag-processing">#AI2026</span> <span class="ant-tag ant-tag-processing">#Shorts</span>';
    document.getElementById("modal-video-tags").innerHTML = tagsHtml;

    const container = document.getElementById("modal-video-container");
    const downloadBtn = document.getElementById("modal-download-btn");
    const fbBtn = document.querySelector("#video-modal .fb-btn");
    const tiktokBtn = document.querySelector("#video-modal .tiktok-btn");
    const xBtn = document.querySelector("#video-modal .x-btn");

    const hasVideo = job.video_final_path || job.video_raw_path;

    if (container) {
        if (hasVideo) {
            // Use absolute URL to avoid relative path issues when page is served from /ui/
            const streamUrl = `${window.location.origin}/api/video-stream/${job.id}`;
            container.innerHTML = `
                <video
                    id="modal-player"
                    controls
                    autoplay
                    playsinline
                    preload="metadata"
                    style="width:100%;height:100%;object-fit:contain;border-radius:12px;background:#000;"
                    src="${streamUrl}"
                >
                    Trình duyệt không hỗ trợ phát video.
                </video>
                <div id="modal-player-err" style="display:none;color:#ff6b6b;text-align:center;padding:20px;font-size:13px;">
                    ⚠️ Không tải được video. <a href="${streamUrl}" target="_blank" style="color:#60a5fa;">Mở trực tiếp →</a>
                </div>
            `;
            // Force load & play
            const vid = document.getElementById('modal-player');
            if (vid) {
                vid.onerror = () => {
                    const errEl = document.getElementById('modal-player-err');
                    if (errEl) errEl.style.display = 'block';
                };
                vid.load();
                vid.play().catch(() => {});
            }
            if (downloadBtn) {
                downloadBtn.style.display = "inline-flex";
                downloadBtn.href = `${window.location.origin}/api/video-stream/${job.id}`;
            }
        } else {
            container.innerHTML = `
                <div class="video-mock-frame">
                    <div class="video-overlay-sub">"${job.voiceover_text || 'Đang tạo kịch bản & render video 9:16...'}"</div>
                    <div class="video-watermark">Veo 2.0 AI</div>
                </div>
            `;
            if (downloadBtn) {
                downloadBtn.style.display = "none";
            }
        }
    }

    // Bind social post click handlers
    if (fbBtn) {
        fbBtn.disabled = !hasVideo;
        fbBtn.onclick = (e) => {
            e.stopPropagation();
            document.getElementById("video-modal").style.display = "none";
            postVideoToFB(job.id);
        };
    }
    if (tiktokBtn) {
        tiktokBtn.disabled = !hasVideo;
        tiktokBtn.onclick = (e) => {
            e.stopPropagation();
            document.getElementById("video-modal").style.display = "none";
            postVideoToTikTok(job.id);
        };
    }
    if (xBtn) {
        xBtn.disabled = !hasVideo;
        xBtn.onclick = (e) => {
            e.stopPropagation();
            document.getElementById("video-modal").style.display = "none";
            testPostJob(job.id, 'x');
        };
    }

    document.getElementById("video-modal").style.display = "flex";
}

// Fetch & Update System Settings
async function fetchSettings() {
    try {
        const res = await fetch(`${API_BASE}/api/settings`);
        if (!res.ok) return;
        const result = await res.json();
        const data = result.data;
        if (!data) return;

        const apiKeyEl = document.getElementById("settings-api-key");
        const maxWorkersEl = document.getElementById("settings-max-workers");
        const maxLabsWorkersEl = document.getElementById("settings-max-labs-workers");
        const storageDirEl = document.getElementById("settings-storage-dir");

        if (apiKeyEl && data.gemini_api_key !== undefined) apiKeyEl.value = data.gemini_api_key;
        if (maxWorkersEl && data.max_workers !== undefined) maxWorkersEl.value = data.max_workers;
        if (maxLabsWorkersEl && data.max_labs_workers !== undefined) maxLabsWorkersEl.value = data.max_labs_workers;
        if (storageDirEl && data.storage_dir !== undefined) storageDirEl.value = data.storage_dir;

        const veoModelEl = document.getElementById("settings-veo-model");
        const imageModelEl = document.getElementById("settings-image-model");
        if (veoModelEl && data.veo_model) veoModelEl.value = data.veo_model;
        if (imageModelEl && data.image_model) imageModelEl.value = data.image_model;

        if (data.require_confirmation !== undefined) {
            const confAlways = document.getElementById("conf-always");
            const confNever = document.getElementById("conf-never");
            if (data.require_confirmation && confAlways) confAlways.checked = true;
            else if (confNever) confNever.checked = true;
        }

        if (data.aspect_ratio) {
            const radio = document.querySelector(`input[name="video_aspect_ratio"][value="${data.aspect_ratio}"]`);
            if (radio) radio.checked = true;
        }

        if (data.gen_engine) {
            const engineRadio = document.querySelector(`input[name="settings_gen_engine"][value="${data.gen_engine}"]`);
            if (engineRadio) engineRadio.checked = true;
        }

        // Veo duration (4/6/8s)
        if (data.veo_duration) {
            const durRadio = document.querySelector(`input[name="veo_duration"][value="${data.veo_duration}"]`);
            if (durRadio) durRadio.checked = true;
        }
        // Veo variants (x1/x2/x3/x4)
        if (data.veo_variants) {
            const varRadio = document.querySelector(`input[name="veo_variants"][value="${data.veo_variants}"]`);
            if (varRadio) varRadio.checked = true;
        }
        // Veo strict model
        const strictEl = document.getElementById("settings-veo-strict");
        if (strictEl && data.veo_strict_model !== undefined) strictEl.checked = !!data.veo_strict_model;
    } catch (err) {
        console.warn("Lỗi fetch cài đặt:", err);
    }
}

function initSettingsForm() {
    const btnToggleKey = document.getElementById("btn-toggle-key");
    const apiKeyInput = document.getElementById("settings-api-key");
    if (btnToggleKey && apiKeyInput) {
        btnToggleKey.addEventListener("click", () => {
            if (apiKeyInput.type === "password") {
                apiKeyInput.type = "text";
                btnToggleKey.innerHTML = '<i class="fa-solid fa-eye-slash"></i>';
            } else {
                apiKeyInput.type = "password";
                btnToggleKey.innerHTML = '<i class="fa-solid fa-eye"></i>';
            }
        });
    }

    const btnBrowse = document.getElementById("btn-browse-folder");
    const folderPicker = document.getElementById("file-folder-picker");
    const storageDirInput = document.getElementById("settings-storage-dir");

    if (btnBrowse && folderPicker) {
        btnBrowse.addEventListener("click", () => {
            folderPicker.click();
        });

        folderPicker.addEventListener("change", (e) => {
            if (e.target.files && e.target.files.length > 0) {
                const firstFile = e.target.files[0];
                if (firstFile.path) {
                    const parts = firstFile.path.split(/[/\\]/);
                    parts.pop();
                    storageDirInput.value = parts.join("/");
                } else if (firstFile.webkitRelativePath) {
                    const folderName = firstFile.webkitRelativePath.split("/")[0];
                    storageDirInput.value = `/storage/${folderName}`;
                }
            }
        });
    }

    const settingsForm = document.getElementById("form-settings");
    if (settingsForm) {
        settingsForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const apiKey = document.getElementById("settings-api-key").value;
            const maxWorkers = parseInt(document.getElementById("settings-max-workers").value) || 5;
            const maxLabsWorkers = parseInt(document.getElementById("settings-max-labs-workers")?.value || "3");
            const storageDir = document.getElementById("settings-storage-dir").value;

            const engineRadio = document.querySelector('input[name="settings_gen_engine"]:checked');
            const genEngine = engineRadio ? engineRadio.value : "labs";

            const veoModel = document.getElementById("settings-veo-model").value;
            const imageModel = document.getElementById("settings-image-model").value;

            const confRadio = document.querySelector('input[name="require_confirmation"]:checked');
            const requireConfirmation = confRadio ? (confRadio.value === "true") : false;

            const videoAspectRadio = document.querySelector('input[name="video_aspect_ratio"]:checked');
            const aspectRatio = videoAspectRadio ? videoAspectRadio.value : "9:16";

            const durRadio = document.querySelector('input[name="veo_duration"]:checked');
            const veoDuration = durRadio ? parseInt(durRadio.value) : 8;

            const varRadio = document.querySelector('input[name="veo_variants"]:checked');
            const veoVariants = varRadio ? parseInt(varRadio.value) : 1;

            const strictEl = document.getElementById("settings-veo-strict");
            const veoStrictModel = strictEl ? strictEl.checked : true;

            try {
                const res = await fetch(`${API_BASE}/api/settings`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        gemini_api_key: apiKey,
                        max_workers: maxWorkers,
                        max_labs_workers: maxLabsWorkers,
                        gen_engine: genEngine,
                        storage_dir: storageDir,
                        veo_model: veoModel,
                        image_model: imageModel,
                        aspect_ratio: aspectRatio,
                        require_confirmation: requireConfirmation,
                        veo_duration: veoDuration,
                        veo_variants: veoVariants,
                        veo_strict_model: veoStrictModel
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message, "success");
                    fetchSettings();
                } else {
                    showToast(data.detail, "error");
                }
            } catch (err) {
                showToast(`Lỗi lưu cài đặt: ${err.message}`, "error");
            }
        });
    }
}



// ═══════════════════════════════════════════════════════════════
// FB MULTI-PROFILE MANAGEMENT
// ═══════════════════════════════════════════════════════════════

let _fbProfiles = [];  // Cache danh sách profiles

// ── Load & Render Profiles (Social Tab) ──────────────────────
async function loadFbProfiles() {
    const container = document.getElementById("fb-profiles-list");
    if (!container) return;
    try {
        const res = await fetch(`${API_BASE}/api/fb-profiles`);
        const data = await res.json();
        _fbProfiles = data.profiles || [];
        renderFbProfiles(_fbProfiles);
    } catch (err) {
        if (container) container.innerHTML = `<div style="color:var(--color-error);padding:12px;">Lỗi tải profiles: ${err.message}</div>`;
    }
}

function renderFbProfiles(profiles) {
    const container = document.getElementById("fb-profiles-list");
    if (!container) return;

    if (profiles.length === 0) {
        container.innerHTML = `
            <div style="text-align:center;padding:24px;color:var(--text-secondary);">
                <i class="fa-solid fa-user-plus" style="font-size:28px;margin-bottom:8px;display:block;opacity:0.4;"></i>
                Chưa có profile nào. Nhập tên và click "Thêm Profile" để bắt đầu.
            </div>`;
        return;
    }

    container.innerHTML = profiles.map(p => {
        const isDefault = p.id === 'default';
        const loggedIn = p.logged_in;
        const statusBadge = loggedIn
            ? `<span class="ant-tag" style="background:rgba(82,196,26,0.12);color:#52c41a;border-color:rgba(82,196,26,0.3);">
                <i class="fa-solid fa-circle-check"></i> Đã đăng nhập</span>`
            : `<span class="ant-tag" style="background:rgba(250,173,20,0.12);color:#faad14;border-color:rgba(250,173,20,0.3);">
                <i class="fa-solid fa-triangle-exclamation"></i> Chưa đăng nhập</span>`;

        return `
        <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;border:1px solid var(--border-color);background:var(--bg-secondary);">
            <i class="fa-brands fa-facebook" style="font-size:20px;color:#1877f2;flex-shrink:0;"></i>
            <div style="flex:1;min-width:0;">
                <div style="font-weight:600;font-size:14px;">${p.name}${isDefault ? ' <span style="font-size:11px;color:var(--text-secondary);">(mặc định)</span>' : ''}</div>
                <div style="margin-top:4px;">${statusBadge}</div>
            </div>
            <div style="display:flex;gap:6px;flex-shrink:0;">
                ${loggedIn
                    ? `<button class="ant-btn" style="font-size:12px;padding:4px 10px;height:auto;color:#faad14;border-color:rgba(250,173,20,0.4);"
                        onclick="logoutFbProfile('${p.id}')">
                        <i class="fa-solid fa-right-from-bracket"></i> Logout
                       </button>`
                    : `<button class="ant-btn ant-btn-primary" style="font-size:12px;padding:4px 10px;height:auto;"
                        onclick="loginFbProfile('${p.id}')">
                        <i class="fa-solid fa-arrow-right-to-bracket"></i> Login
                       </button>`
                }
                ${!isDefault ? `
                <button class="ant-btn ant-btn-danger" style="font-size:12px;padding:4px 10px;height:auto;"
                    onclick="deleteFbProfile('${p.id}', '${p.name}')">
                    <i class="fa-solid fa-trash"></i>
                </button>` : ''}
            </div>
        </div>`;
    }).join('');
}

async function createFbProfile() {
    const input = document.getElementById("fb-new-profile-name");
    const name = (input?.value || "").trim();
    if (!name) { showToast("Nhập tên profile trước!", "error"); return; }

    try {
        const res = await fetch(`${API_BASE}/api/fb-profiles`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`✅ Đã tạo profile "${data.profile.name}"`, "success");
            if (input) input.value = "";
            loadFbProfiles();
        } else {
            showToast(data.detail || "Lỗi tạo profile", "error");
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    }
}

async function deleteFbProfile(profileId, name) {
    const ok = await showConfirmModal(`Xóa profile "${name}"? Toàn bộ session đăng nhập sẽ bị xóa!`, "Xác Nhận Xóa Profile");
    if (!ok) return;
    try {
        const res = await fetch(`${API_BASE}/api/fb-profiles/${profileId}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok) {
            showToast(`Đã xóa profile "${name}"`, "success");
            loadFbProfiles();
        } else {
            showToast(data.detail || "Lỗi xóa profile", "error");
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    }
}

async function loginFbProfile(profileId) {
    showToast("Đang mở browser đăng nhập...", "info");
    try {
        const res = await fetch(`${API_BASE}/api/fb-profiles/${profileId}/login`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            showToast("Browser đăng nhập đã mở! Sau khi đăng nhập xong, click Refresh.", "info");
            setTimeout(() => loadFbProfiles(), 5000);
        } else {
            showToast(data.detail || "Lỗi mở browser", "error");
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    }
}

async function logoutFbProfile(profileId) {
    const profiles = _fbProfiles;
    const p = profiles.find(x => x.id === profileId);
    const name = p ? p.name : profileId;
    const ok = await showConfirmModal(`Đăng xuất profile "${name}"? Cần đăng nhập lại sau.`, "Xác Nhận Logout");
    if (!ok) return;
    try {
        const res = await fetch(`${API_BASE}/api/fb-profiles/${profileId}/logout`, { method: "POST" });
        const data = await res.json();
        showToast(data.message, res.ok ? "success" : "error");
        loadFbProfiles();
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    }
}

// ── Profile Selector Modal (Library → Đăng FB) ───────────────
let _fbModalJobId = null;
let _fbModalJobTitle = null;

async function postVideoToFB(jobId) {
    // Thay vì đăng thẳng, mở modal chọn profiles
    openFbProfileModal(jobId);
}

async function openFbProfileModal(jobId) {
    _fbModalJobId = jobId;

    // Set video name in modal header
    const modal = document.getElementById("fb-profile-modal");
    const nameEl = document.getElementById("fb-modal-video-name");
    const captionEl = document.getElementById("fb-modal-caption");
    const job = currentJobs.find(j => j.id === jobId);

    if (nameEl) {
        nameEl.textContent = `Video: ${job ? (job.title || `#${jobId}`) : `Job #${jobId}`}`;
    }
    if (captionEl) {
        captionEl.value = job ? ((job.title ? job.title + "\n\n" : "") + (job.voiceover_text || "")).trim() : "";
    }

    // Show modal
    if (modal) modal.style.display = "flex";

    // Load profiles vào modal
    await renderFbModalProfiles();
}

function closeFbProfileModal() {
    const modal = document.getElementById("fb-profile-modal");
    if (modal) modal.style.display = "none";
    _fbModalJobId = null;
}

async function renderFbModalProfiles() {
    const container = document.getElementById("fb-modal-profiles");
    if (!container) return;

    try {
        const res = await fetch(`${API_BASE}/api/fb-profiles`);
        const data = await res.json();
        const profiles = data.profiles || [];
        _fbProfiles = profiles;

        if (profiles.length === 0) {
            container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text-secondary);">
                Chưa có profile nào. Vào <b>Cấu Hình Auto Post</b> để tạo profile.</div>`;
            return;
        }

        container.innerHTML = profiles.map(p => {
            const loggedIn = p.logged_in;
            return `
            <label style="display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;border:1px solid var(--border-color);cursor:${loggedIn ? 'pointer' : 'default'};background:var(--bg-secondary);${!loggedIn ? 'opacity:0.55;' : ''}">
                <input type="checkbox" class="fb-profile-checkbox" value="${p.id}" ${!loggedIn ? 'disabled' : ''} checked style="width:16px;height:16px;">
                <i class="fa-brands fa-facebook" style="font-size:18px;color:#1877f2;"></i>
                <div style="flex:1;">
                    <div style="font-weight:600;">${p.name}</div>
                    <div style="font-size:11px;color:${loggedIn ? '#52c41a' : '#faad14'};">
                        ${loggedIn ? '✅ Đã đăng nhập — sẵn sàng đăng' : '⚠️ Chưa đăng nhập'}
                    </div>
                </div>
            </label>`;
        }).join('');

        // Update button label
        updateFbModalPostBtn();
        document.querySelectorAll(".fb-profile-checkbox").forEach(cb => {
            cb.addEventListener("change", updateFbModalPostBtn);
        });

    } catch (err) {
        container.innerHTML = `<div style="color:var(--color-error);padding:12px;">Lỗi tải profiles: ${err.message}</div>`;
    }
}

function updateFbModalPostBtn() {
    const checked = document.querySelectorAll(".fb-profile-checkbox:checked:not(:disabled)");
    const label = document.getElementById("fb-modal-post-label");
    const btn = document.getElementById("fb-modal-post-btn");
    const count = checked.length;
    if (label) label.textContent = count > 0
        ? `Đăng Lên ${count} Profile${count > 1 ? 's' : ''}`
        : "Chọn ít nhất 1 profile";
    if (btn) btn.disabled = count === 0;
}

async function executePostToProfiles() {
    if (!_fbModalJobId) return;
    const checked = document.querySelectorAll(".fb-profile-checkbox:checked:not(:disabled)");
    const profileIds = Array.from(checked).map(cb => cb.value);
    if (profileIds.length === 0) { showToast("Chọn ít nhất 1 profile!", "error"); return; }

    const maxWorkers = parseInt(document.getElementById("fb-modal-max-workers")?.value || "3");
    const customCaption = (document.getElementById("fb-modal-caption")?.value || "").trim();
    const postBtn = document.getElementById("fb-modal-post-btn");
    if (postBtn) { postBtn.disabled = true; postBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang gửi...'; }

    try {
        const res = await fetch(`${API_BASE}/api/social/post-to-profiles`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                job_id: _fbModalJobId,
                profile_ids: profileIds,
                max_workers: maxWorkers,
                custom_caption: customCaption
            })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`✅ ${data.message}`, "success");
            closeFbProfileModal();
            // Refresh sau 30s
            setTimeout(() => fetchJobsAndStats(), 30000);
        } else {
            showToast(data.detail || "Lỗi đăng bài", "error");
            if (postBtn) { postBtn.disabled = false; postBtn.innerHTML = '<i class="fa-brands fa-facebook"></i> <span id="fb-modal-post-label">Đăng Lên Profiles</span>'; }
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
        if (postBtn) { postBtn.disabled = false; postBtn.innerHTML = '<i class="fa-brands fa-facebook"></i> <span id="fb-modal-post-label">Đăng Lên Profiles</span>'; }
    }
}

// ═══════════════════════════════════════════════════════════════
// TIKTOK MULTI-PROFILE MANAGEMENT
// ═══════════════════════════════════════════════════════════════

let _tiktokProfiles = [];

async function loadTikTokProfiles() {
    const container = document.getElementById("tiktok-profiles-list");
    if (!container) return;
    try {
        const res = await fetch(`${API_BASE}/api/tiktok-profiles`);
        const data = await res.json();
        _tiktokProfiles = data.profiles || [];
        renderTikTokProfiles(_tiktokProfiles);
    } catch (err) {
        if (container) container.innerHTML = `<div style="color:var(--color-error);padding:12px;">Lỗi tải profiles: ${err.message}</div>`;
    }
}

function renderTikTokProfiles(profiles) {
    const container = document.getElementById("tiktok-profiles-list");
    if (!container) return;

    if (profiles.length === 0) {
        container.innerHTML = `
            <div style="text-align:center;padding:24px;color:var(--text-secondary);">
                <i class="fa-solid fa-user-plus" style="font-size:28px;margin-bottom:8px;display:block;opacity:0.4;"></i>
                Chưa có profile nào. Nhập tên và click "Thêm Profile" để bắt đầu.
            </div>`;
        return;
    }

    container.innerHTML = profiles.map(p => {
        const isDefault = p.id === 'default';
        const loggedIn = p.logged_in;
        const statusBadge = loggedIn
            ? `<span class="ant-tag" style="background:rgba(82,196,26,0.12);color:#52c41a;border-color:rgba(82,196,26,0.3);">
                <i class="fa-solid fa-circle-check"></i> Đã đăng nhập</span>`
            : `<span class="ant-tag" style="background:rgba(250,173,20,0.12);color:#faad14;border-color:rgba(250,173,20,0.3);">
                <i class="fa-solid fa-triangle-exclamation"></i> Chưa đăng nhập</span>`;

        return `
        <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;border:1px solid var(--border-color);background:var(--bg-secondary);">
            <i class="fa-brands fa-tiktok" style="font-size:20px;color:#fe2c55;flex-shrink:0;"></i>
            <div style="flex:1;min-width:0;">
                <div style="font-weight:600;font-size:14px;">${p.name}${isDefault ? ' <span style="font-size:11px;color:var(--text-secondary);">(mặc định)</span>' : ''}</div>
                <div style="margin-top:4px;">${statusBadge}</div>
            </div>
            <div style="display:flex;gap:6px;flex-shrink:0;">
                ${loggedIn
                    ? `<button class="ant-btn" style="font-size:12px;padding:4px 10px;height:auto;color:#faad14;border-color:rgba(250,173,20,0.4);"
                        onclick="logoutTikTokProfile('${p.id}')">
                        <i class="fa-solid fa-right-from-bracket"></i> Logout
                       </button>`
                    : `<button class="ant-btn ant-btn-primary" style="font-size:12px;padding:4px 10px;height:auto;background:#fe2c55;border-color:#fe2c55;"
                        onclick="loginTikTokProfile('${p.id}')">
                        <i class="fa-solid fa-arrow-right-to-bracket"></i> Login
                       </button>`
                }
                ${!isDefault ? `
                <button class="ant-btn ant-btn-danger" style="font-size:12px;padding:4px 10px;height:auto;"
                    onclick="deleteTikTokProfile('${p.id}', '${p.name}')">
                    <i class="fa-solid fa-trash"></i>
                </button>` : ''}
            </div>
        </div>`;
    }).join('');
}

async function createTikTokProfile() {
    const input = document.getElementById("tiktok-new-profile-name");
    const name = (input?.value || "").trim();
    if (!name) { showToast("Nhập tên profile TikTok trước!", "error"); return; }

    try {
        const res = await fetch(`${API_BASE}/api/tiktok-profiles`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`✅ Đã tạo profile TikTok "${data.profile.name}"`, "success");
            if (input) input.value = "";
            loadTikTokProfiles();
        } else {
            showToast(data.detail || "Lỗi tạo profile TikTok", "error");
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    }
}

async function deleteTikTokProfile(profileId, name) {
    const ok = await showConfirmModal(`Xóa profile TikTok "${name}"? Toàn bộ session đăng nhập sẽ bị xóa!`, "Xác Nhận Xóa Profile TikTok");
    if (!ok) return;
    try {
        const res = await fetch(`${API_BASE}/api/tiktok-profiles/${profileId}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok) {
            showToast(`Đã xóa profile TikTok "${name}"`, "success");
            loadTikTokProfiles();
        } else {
            showToast(data.detail || "Lỗi xóa profile TikTok", "error");
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    }
}

async function loginTikTokProfile(profileId) {
    showToast("Đang mở browser đăng nhập TikTok...", "info");
    try {
        const res = await fetch(`${API_BASE}/api/tiktok-profiles/${profileId}/login`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            showToast("Browser đăng nhập TikTok đã mở! Sau khi đăng nhập xong, click Refresh.", "info");
            setTimeout(() => loadTikTokProfiles(), 5000);
        } else {
            showToast(data.detail || "Lỗi mở browser TikTok", "error");
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    }
}

async function logoutTikTokProfile(profileId) {
    const profiles = _tiktokProfiles;
    const p = profiles.find(x => x.id === profileId);
    const name = p ? p.name : profileId;
    const ok = await showConfirmModal(`Đăng xuất profile TikTok "${name}"? Cần đăng nhập lại sau.`, "Xác Nhận Logout TikTok");
    if (!ok) return;
    try {
        const res = await fetch(`${API_BASE}/api/tiktok-profiles/${profileId}/logout`, { method: "POST" });
        const data = await res.json();
        showToast(data.message, res.ok ? "success" : "error");
        loadTikTokProfiles();
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    }
}

// ── TikTok Profile Selector Modal (Library → Đăng TikTok) ────
let _tiktokModalJobId = null;

async function postVideoToTikTok(jobId) {
    openTikTokProfileModal(jobId);
}

async function openTikTokProfileModal(jobId) {
    _tiktokModalJobId = jobId;

    const modal = document.getElementById("tiktok-profile-modal");
    const nameEl = document.getElementById("tiktok-modal-video-name");
    const captionEl = document.getElementById("tiktok-modal-caption");
    const job = currentJobs.find(j => j.id === jobId);

    if (nameEl) {
        nameEl.textContent = `Video: ${job ? (job.title || `#${jobId}`) : `Job #${jobId}`}`;
    }
    if (captionEl) {
        captionEl.value = job ? ((job.title ? job.title + "\n\n" : "") + (job.voiceover_text || "")).trim() : "";
    }

    if (modal) modal.style.display = "flex";
    await renderTikTokModalProfiles();
}

function closeTikTokProfileModal() {
    const modal = document.getElementById("tiktok-profile-modal");
    if (modal) modal.style.display = "none";
    _tiktokModalJobId = null;
}

async function renderTikTokModalProfiles() {
    const container = document.getElementById("tiktok-modal-profiles");
    if (!container) return;

    try {
        const res = await fetch(`${API_BASE}/api/tiktok-profiles`);
        const data = await res.json();
        const profiles = data.profiles || [];
        _tiktokProfiles = profiles;

        if (profiles.length === 0) {
            container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text-secondary);">
                Chưa có profile TikTok nào. Vào <b>Cấu Hình Auto Post</b> để tạo profile.</div>`;
            return;
        }

        container.innerHTML = profiles.map(p => {
            const loggedIn = p.logged_in;
            return `
            <label style="display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;border:1px solid var(--border-color);cursor:${loggedIn ? 'pointer' : 'default'};background:var(--bg-secondary);${!loggedIn ? 'opacity:0.55;' : ''}">
                <input type="checkbox" class="tiktok-profile-checkbox" value="${p.id}" ${!loggedIn ? 'disabled' : ''} checked style="width:16px;height:16px;">
                <i class="fa-brands fa-tiktok" style="font-size:18px;color:#fe2c55;"></i>
                <div style="flex:1;">
                    <div style="font-weight:600;">${p.name}</div>
                    <div style="font-size:11px;color:${loggedIn ? '#52c41a' : '#faad14'};">
                        ${loggedIn ? '✅ Đã đăng nhập — sẵn sàng đăng' : '⚠️ Chưa đăng nhập'}
                    </div>
                </div>
            </label>`;
        }).join('');

        updateTikTokModalPostBtn();
        document.querySelectorAll(".tiktok-profile-checkbox").forEach(cb => {
            cb.addEventListener("change", updateTikTokModalPostBtn);
        });

    } catch (err) {
        container.innerHTML = `<div style="color:var(--color-error);padding:12px;">Lỗi tải profiles: ${err.message}</div>`;
    }
}

function updateTikTokModalPostBtn() {
    const checked = document.querySelectorAll(".tiktok-profile-checkbox:checked:not(:disabled)");
    const label = document.getElementById("tiktok-modal-post-label");
    const btn = document.getElementById("tiktok-modal-post-btn");
    const count = checked.length;
    if (label) label.textContent = count > 0
        ? `Đăng Lên ${count} Profile TikTok`
        : "Chọn ít nhất 1 profile";
    if (btn) btn.disabled = count === 0;
}

async function executePostToTikTokProfiles() {
    if (!_tiktokModalJobId) return;
    const checked = document.querySelectorAll(".tiktok-profile-checkbox:checked:not(:disabled)");
    const profileIds = Array.from(checked).map(cb => cb.value);
    if (profileIds.length === 0) { showToast("Chọn ít nhất 1 profile TikTok!", "error"); return; }

    const maxWorkers = parseInt(document.getElementById("tiktok-modal-max-workers")?.value || "3");
    const customCaption = (document.getElementById("tiktok-modal-caption")?.value || "").trim();
    const postBtn = document.getElementById("tiktok-modal-post-btn");
    if (postBtn) { postBtn.disabled = true; postBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang gửi...'; }

    try {
        const res = await fetch(`${API_BASE}/api/social/post-to-tiktok-profiles`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                job_id: _tiktokModalJobId,
                profile_ids: profileIds,
                max_workers: maxWorkers,
                custom_caption: customCaption
            })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`✅ ${data.message}`, "success");
            closeTikTokProfileModal();
            setTimeout(() => fetchJobsAndStats(), 30000);
        } else {
            showToast(data.detail || "Lỗi đăng bài TikTok", "error");
            if (postBtn) { postBtn.disabled = false; postBtn.innerHTML = '<i class="fa-brands fa-tiktok"></i> <span id="tiktok-modal-post-label">Đăng Lên Profiles</span>'; }
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
        if (postBtn) { postBtn.disabled = false; postBtn.innerHTML = '<i class="fa-brands fa-tiktok"></i> <span id="tiktok-modal-post-label">Đăng Lên Profiles</span>'; }
    }
}

// ── Switch Social Horizontal Sub-Tabs ────────────────────────
function switchSocialSubtab(platform) {
    document.querySelectorAll(".social-subtab-btn").forEach(btn => {
        const p = btn.getAttribute("data-subtab");
        if (p === platform) {
            btn.classList.add("active");
            btn.style.background = p === 'fb' ? '#1877f2' : p === 'tiktok' ? '#fe2c55' : p === 'labs' ? '#4285f4' : '#14171a';
            btn.style.color = '#fff';
            btn.style.borderColor = 'transparent';
        } else {
            btn.classList.remove("active");
            btn.style.background = 'var(--bg-secondary)';
            btn.style.color = 'var(--text-color)';
            btn.style.borderColor = 'var(--border-color)';
        }
    });

    document.querySelectorAll(".social-subtab-content").forEach(content => {
        const targetId = `social-subtab-${platform}`;
        content.style.display = content.id === targetId ? 'block' : 'none';
    });

    if (platform === 'fb') loadFbProfiles();
    if (platform === 'tiktok') loadTikTokProfiles();
    if (platform === 'labs') checkLabsGoogleStatus();
}

async function checkLabsGoogleStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/labs-google/status`);
        const data = await res.json();
        updatePlatformStatusTag("labs-google-status-tag", data.logged_in);
    } catch (err) {
        console.warn("Lỗi kiểm tra Labs Google status:", err);
    }
}

async function loginLabsGoogle() {
    const btn = document.querySelector("#social-subtab-labs button.ant-btn-primary");
    if (btn && btn.disabled) return;
    const oldHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang mở...';
    }
    showToast("Đang mở trình duyệt đăng nhập Google Labs...", "info");
    try {
        const res = await fetch(`${API_BASE}/api/labs-google/login`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            if (data.status === "warning") {
                showToast(data.message, "warning");
            } else {
                showToast("Trình duyệt đăng nhập đã mở! Vui lòng đăng nhập tài khoản Google trên labs.google.", "info");
            }
            setTimeout(checkLabsGoogleStatus, 5000);
        } else {
            showToast(data.detail || "Lỗi mở trình duyệt", "error");
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    } finally {
        setTimeout(() => {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = oldHtml || '<i class="fa-solid fa-arrow-right-to-bracket"></i> Mở Trình Duyệt Đăng Nhập Google Labs';
            }
        }, 3000);
    }
}

async function generateViaLabsGoogle(promptText, quality) {
    if (!promptText || !promptText.trim()) {
        showToast("Vui lòng nhập prompt trước khi tạo!", "error");
        return;
    }
    const qualityVal = quality || (document.getElementById("labs-quality-select") ? document.getElementById("labs-quality-select").value : "1080p");
    const subCb = document.getElementById("labs-subtitle-checkbox");
    const addSub = subCb ? subCb.checked : true;
    const voiceCb = document.getElementById("labs-voiceover-checkbox");
    const addVoice = voiceCb ? voiceCb.checked : true;

    const aspectRatio = document.getElementById("prompt-aspect-ratio") ? document.getElementById("prompt-aspect-ratio").value : "9:16";
    const duration = document.getElementById("prompt-duration") ? parseInt(document.getElementById("prompt-duration").value) : 8;
    const variants = document.getElementById("prompt-variants") ? parseInt(document.getElementById("prompt-variants").value) : 1;
    const veoModel = document.getElementById("prompt-veo-model") ? document.getElementById("prompt-veo-model").value : "veo-3.1-lite-generate-preview";

    const countEl = document.getElementById("prompt-count");
    const count = countEl ? (parseInt(countEl.value) || 1) : 1;

    const keepCb = document.getElementById("prompt-keep-context");
    const keepContext = keepCb ? keepCb.checked : false;

    const customContextInput = document.getElementById("prompt-custom-context");
    const customContext = customContextInput ? customContextInput.value : "";

    showToast(`Đang gửi yêu cầu sinh ${count} video qua Labs.google (${aspectRatio} | ${duration}s | ${variants}x | ${qualityVal})...`, "info");
    try {
        if (count > 1) {
            const res = await fetch(`${API_BASE}/api/generate-prompt`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    topic: promptText.trim(),
                    count: count,
                    keep_context: keepContext,
                    custom_context: customContext,
                    aspect_ratio: aspectRatio,
                    duration: duration,
                    variants: variants,
                    veo_model: veoModel,
                    quality: qualityVal
                })
            });
            const data = await res.json();
            if (res.ok) {
                showToast(`✅ ${data.message}`, "success");
                fetchJobsAndStats();
            } else {
                showToast(data.detail || "Lỗi sinh batch video", "error");
            }
        } else {
            const res = await fetch(`${API_BASE}/api/labs-google/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    prompt: promptText.trim(),
                    quality: qualityVal,
                    aspect_ratio: aspectRatio,
                    duration: duration,
                    variants: variants,
                    veo_model: veoModel,
                    add_subtitle: addSub,
                    add_voiceover: addVoice
                })
            });
            const data = await res.json();
            if (res.ok) {
                showToast(`✅ ${data.message}`, "success");
                fetchJobsAndStats();
            } else {
                showToast(data.detail || "Lỗi tạo video", "error");
            }
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    }
}

// Expose on window scope for inline HTML onclick attributes
window.switchSocialSubtab = switchSocialSubtab;
window.createFbProfile = createFbProfile;
window.createTikTokProfile = createTikTokProfile;
window.loadFbProfiles = loadFbProfiles;
window.loadTikTokProfiles = loadTikTokProfiles;
window.loginFbProfile = loginFbProfile;
window.logoutFbProfile = logoutFbProfile;
window.deleteFbProfile = deleteFbProfile;
window.loginTikTokProfile = loginTikTokProfile;
window.logoutTikTokProfile = logoutTikTokProfile;
window.deleteTikTokProfile = deleteTikTokProfile;
window.postVideoToFB = postVideoToFB;
window.postVideoToTikTok = postVideoToTikTok;
window.closeFbProfileModal = closeFbProfileModal;
window.closeTikTokProfileModal = closeTikTokProfileModal;
window.executePostToProfiles = executePostToProfiles;
window.executePostToTikTokProfiles = executePostToTikTokProfiles;
window.checkLabsGoogleStatus = checkLabsGoogleStatus;
window.loginLabsGoogle = loginLabsGoogle;
window.generateViaLabsGoogle = generateViaLabsGoogle;

async function fetchAppVersion() {
    try {
        const res = await _originalFetch(`${API_BASE}/api/version`);
        const data = await res.json();
        if (data && data.version) {
            const badge = document.getElementById("app-version-badge");
            if (badge && !document.getElementById("blocked-version-modal")) {
                badge.innerText = `PRO v${data.version}`;
            }
        }
        if (data && data.remote) {
            if (data.remote.is_blocked) {
                showBlockedVersionModal(data.remote);
                return true; // blocked
            } else {
                // Nếu trước đó bị block nhưng giờ OK → xóa modal
                const oldModal = document.getElementById("blocked-version-modal");
                if (oldModal) oldModal.remove();
                if (data.remote.is_update_available) {
                    showUpdateAvailableBadge(data.remote);
                }
            }
        }
    } catch (e) {
        console.warn("Could not fetch app version:", e);
    }
    return false;
}

function showBlockedVersionModal(remote) {
    // Nếu modal đã hiện rồi thì không tạo lại
    if (document.getElementById("blocked-version-modal")) return;

    const modal = document.createElement("div");
    modal.id = "blocked-version-modal";
    modal.style.cssText = "position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.95);z-index:999999;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(12px);font-family:Inter,sans-serif;";

    // Chặn mọi thao tác: click, keyboard, scroll
    modal.addEventListener("click", e => e.stopPropagation());
    modal.addEventListener("keydown", e => { e.preventDefault(); e.stopPropagation(); });

    const msg = remote.update_message || "Phiên bản bạn đang dùng đã hết hạn. Vui lòng cập nhật phiên bản mới nhất để tiếp tục sử dụng.";
    const downloadUrl = remote.download_url || "#";
    const remoteVer = remote.remote_version || remote.min_version || "?";

    modal.innerHTML = `
        <div style="background:#1f1f1f;border:2px solid #ff4d4f;border-radius:16px;padding:40px;max-width:540px;width:90%;text-align:center;box-shadow:0 20px 60px rgba(255,77,79,0.4);color:#fff;animation:fadeInUp 0.4s ease-out;">
            <div style="width:70px;height:70px;background:rgba(255,77,79,0.15);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;color:#ff4d4f;font-size:32px;">
                <i class="fa-solid fa-triangle-exclamation"></i>
            </div>
            <h2 style="color:#ff4d4f;margin:0 0 12px;font-size:22px;font-weight:700;">ỨNG DỤNG ĐÃ BỊ VÔ HIỆU HÓA</h2>
            <p style="color:#d9d9d9;font-size:14px;line-height:1.6;margin-bottom:20px;">${escapeHtml(msg)}</p>
            <div style="background:rgba(255,255,255,0.05);padding:14px;border-radius:8px;margin-bottom:24px;font-size:13px;color:#aaa;display:flex;justify-content:space-around;">
                <span>Phiên bản hiện tại: <strong style="color:#fff;">v${remote.current_version}</strong></span>
                <span>Yêu cầu tối thiểu: <strong style="color:#ff4d4f;">v${remoteVer}</strong></span>
            </div>
            <a href="${downloadUrl}" target="_blank" class="ant-btn ant-btn-primary ant-btn-lg" style="background:#ff4d4f;border-color:#ff4d4f;font-weight:600;width:100%;height:46px;display:flex;align-items:center;justify-content:center;gap:8px;text-decoration:none;font-size:15px;border-radius:8px;">
                <i class="fa-solid fa-download"></i> TẢI BẢN CẬP NHẬT MỚI NGAY
            </a>
            <p style="color:#666;font-size:11px;margin-top:16px;">Bạn không thể sử dụng ứng dụng cho đến khi cập nhật phiên bản mới.</p>
        </div>
    `;

    document.body.appendChild(modal);

    // Chặn keyboard toàn cục
    document.addEventListener("keydown", _blockAllKeys, true);
}

function _blockAllKeys(e) {
    if (document.getElementById("blocked-version-modal")) {
        e.preventDefault();
        e.stopPropagation();
    }
}

function showUpdateAvailableBadge(remote) {
    const badge = document.getElementById("app-version-badge");
    if (badge) {
        badge.innerHTML = `PRO v${remote.current_version} <a href="${remote.download_url}" target="_blank" style="color:#52c41a;margin-left:6px;font-weight:bold;text-decoration:none;" title="Có bản v${remote.latest_version} mới!"><i class="fa-solid fa-circle-up"></i> New v${remote.latest_version}</a>`;
    }
}


// ── Auto-load profiles & version khi trang web load ───────────────────
document.addEventListener("DOMContentLoaded", () => {
    fetchAppVersion();

    // ── Periodic Version Check: kiểm tra Firebase mỗi 30 giây ─────────
    // Khi admin sửa Remote Config → user bị block trong vòng 30s
    setInterval(async () => {
        try {
            // Force server refresh cache trước
            await _originalFetch(`${API_BASE}/api/remote-config/refresh`, { method: "POST" });
        } catch(e) {}
        await fetchAppVersion();
    }, 30000);

    const socialNav = document.querySelector('[data-tab="social"]');
    if (socialNav) {
        socialNav.addEventListener("click", () => {
            setTimeout(() => {
                loadFbProfiles();
                loadTikTokProfiles();
                checkLabsGoogleStatus();
            }, 100);
        });
    }
    if (document.querySelector('#tab-social.active')) {
        loadFbProfiles();
        loadTikTokProfiles();
        checkLabsGoogleStatus();
    }
});

