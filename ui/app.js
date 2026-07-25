// Real-time API Client connected to FastAPI Backend & SQLite DB
const API_BASE = ""; // Same origin / Relative path

let currentJobs = [];
let isEngineRunning = false;

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
            updateStatisticsUI(statsData.data, statsData.is_engine_running);
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
function updateStatisticsUI(stats, running) {
    if (!stats) return;

    isEngineRunning = running;

    const total = Object.values(stats).reduce((a, b) => a + b, 0);
    const generating = (stats.GENERATING_VEO || 0) + (stats.SCRIPTED || 0) + (stats.QUOTA_WAIT || 0);
    const rendered = (stats.PROCESSING_FFMPEG || 0) + (stats.VEO_DONE || 0) + (stats.READY_TO_POST || 0) + (stats.PUBLISHED || 0);
    const published = stats.PUBLISHED || 0;
    const quotaWaiting = stats.QUOTA_WAIT || 0;

    document.getElementById("stat-total").textContent = total;
    document.getElementById("stat-generating").textContent = generating;
    document.getElementById("stat-rendered").textContent = rendered;
    document.getElementById("stat-published").textContent = published;

    // Show/hide quota warning banner
    let quotaBanner = document.getElementById("quota-wait-banner");
    if (quotaWaiting > 0) {
        if (!quotaBanner) {
            quotaBanner = document.createElement("div");
            quotaBanner.id = "quota-wait-banner";
            quotaBanner.style.cssText = "background:#fff7e6;border:1px solid #ffd591;border-radius:8px;padding:10px 16px;margin:10px 0;color:#d46b08;font-size:14px;display:flex;align-items:center;gap:8px;";
            quotaBanner.innerHTML = `<i class="fa-solid fa-hourglass-half fa-spin"></i> <strong>${quotaWaiting} job</strong> đang chờ quota Veo API (429) — sẽ tự retry khi quota reset. <a href="https://ai.dev/rate-limit" target="_blank" style="color:#d46b08;text-decoration:underline;">Kiểm tra quota →</a>`;
            const statsRow = document.querySelector(".stats-row");
            if (statsRow) statsRow.parentNode.insertBefore(quotaBanner, statsRow.nextSibling);
        } else {
            quotaBanner.innerHTML = `<i class="fa-solid fa-hourglass-half fa-spin"></i> <strong>${quotaWaiting} job</strong> đang chờ quota Veo API (429) — sẽ tự retry khi quota reset. <a href="https://ai.dev/rate-limit" target="_blank" style="color:#d46b08;text-decoration:underline;">Kiểm tra quota →</a>`;
            quotaBanner.style.display = "flex";
        }
    } else if (quotaBanner) {
        quotaBanner.style.display = "none";
    }

    // Toggle Engine Button
    const btnEngine = document.getElementById("btn-run-all");
    if (btnEngine) {
        if (isEngineRunning) {
            btnEngine.className = "ant-btn ant-btn-primary ant-btn-lg";
            btnEngine.style.backgroundColor = "#ff4d4f";
            btnEngine.innerHTML = '<i class="fa-solid fa-stop"></i> Dừng Engine Đa Luồng';
        } else {
            btnEngine.className = "ant-btn ant-btn-primary ant-btn-lg";
            btnEngine.style.backgroundColor = "#1890ff";
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
            const srcShort = (job.source_input || '').replace(/https?:\/\/(www\.)?/, '').substring(0, 45);
            promptExcerpt = `<span style="color:var(--text-secondary);font-size:11px;"><i class="fa-brands fa-tiktok"></i> ${srcShort || 'Clone video gốc'}</span>`;
        } else {
            promptExcerpt = job.veo_prompt ? (job.veo_prompt.substring(0, 50) + "...") : "Chờ sinh prompt...";
        }
        const titleStr = job.title || job.source_input || `Job #${job.id}`;
        const durationLabel = job.duration_sec != null ? `${job.duration_sec}s` : "-";

        const isChecked = selectedConcatJobIds.has(job.id) ? "checked" : "";
        tr.innerHTML = `
            <td style="text-align: center;">
                <input type="checkbox" class="job-checkbox" data-id="${job.id}" ${isChecked} style="cursor: pointer; transform: scale(1.2);">
            </td>
            <td><strong>#${job.id}</strong></td>
            <td>${typeBadge}</td>
            <td><strong>${titleStr}</strong></td>
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
                    <button class="ant-btn" style="background:#1877f2;color:#fff;border-color:#1877f2;" onclick="testPostJob(${job.id},'facebook')" title="Đăng ngay lên Facebook Reels">
                        <i class="fa-brands fa-facebook"></i> Đăng FB
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
    const badge = document.getElementById("selected-count-badge");
    const toolbar = document.getElementById("bulk-actions-toolbar");
    const btnConcat = document.getElementById("btn-concat-selected");
    const btnDelete = document.getElementById("btn-bulk-delete");
    const count = selectedConcatJobIds.size;

    if (badge) {
        if (count > 0) {
            badge.style.display = "inline-block";
            badge.textContent = `Đã chọn: ${count} video`;
        } else {
            badge.style.display = "none";
        }
    }

    if (toolbar) {
        toolbar.style.display = count > 0 ? "flex" : "none";
    }

    if (btnDelete) {
        btnDelete.disabled = (count === 0);
        btnDelete.innerHTML = `<i class="fa-solid fa-trash"></i> Xóa (${count}) Video Đã Chọn`;
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

// Render Video Library 9:16 Grid
function renderLibraryGrid(jobs) {
    const grid = document.getElementById("library-video-grid");
    if (!grid) return;
    grid.innerHTML = "";

    const readyJobs = jobs.filter(j => j.status === "PUBLISHED" || j.status === "READY_TO_POST" || j.status === "VEO_DONE");

    if (readyJobs.length === 0) {
        grid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-secondary);">Chưa có video 9:16 nào được render thành công.</div>';
        return;
    }

    readyJobs.forEach(job => {
        const isSelected = selectedConcatJobIds.has(job.id);
        const card = document.createElement("div");
        card.className = `video-card-916 ${isSelected ? 'selected' : ''}`;

        // Social post buttons
        const fbBtn = job.fb_posted
            ? `<span style="font-size:11px;color:#52c41a;"><i class="fa-solid fa-circle-check"></i> FB</span>`
            : `<button class="ant-btn" style="font-size:11px;padding:3px 8px;height:auto;background:#1877f2;color:#fff;border-color:#1877f2;"
                onclick="event.stopPropagation(); postVideoToFB(${job.id})">
                <i class="fa-brands fa-facebook"></i> Đăng FB
               </button>`;

        const tiktokBtn = job.tiktok_posted
            ? `<span style="font-size:11px;color:#52c41a;"><i class="fa-solid fa-circle-check"></i> TikTok</span>`
            : `<button class="ant-btn" style="font-size:11px;padding:3px 8px;height:auto;background:#ee1d52;color:#fff;border-color:#ee1d52;"
                onclick="event.stopPropagation(); testPostJob(${job.id},'tiktok')">
                <i class="fa-brands fa-tiktok"></i> TikTok
               </button>`;

        card.innerHTML = `
            <input type="checkbox" class="video-card-checkbox" data-job-id="${job.id}" ${isSelected ? 'checked' : ''}>
            <div class="video-thumbnail-916">
                <i class="fa-solid fa-circle-play play-icon"></i>
            </div>
            <div class="video-card-info">
                <h4>${job.title || `Video #${job.id}`}</h4>
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
            updateConcatToolbarUI();
        });

        card.addEventListener("click", (e) => {
            if (e.target === cb) return;
            openPreviewModal(job.id);
        });

        grid.appendChild(card);
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
                        custom_context: customContext
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

            const add_voiceover = voiceoverCb ? voiceoverCb.checked : true;
            const add_subtitle = subtitleCb ? subtitleCb.checked : true;

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
    if (closeBtn && modal) {
        closeBtn.onclick = () => {
            modal.style.display = "none";
            const videoEl = modal.querySelector("video");
            if (videoEl) videoEl.pause();
        };
    }
}

function openPreviewModal(jobId) {
    const job = currentJobs.find(j => j.id === jobId);
    if (!job) return;

    document.getElementById("modal-video-title").textContent = job.title || `Job #${job.id}`;
    document.getElementById("modal-video-desc").textContent = job.voiceover_text || job.veo_prompt || "Không có mô tả";

    let tagsHtml = "";
    if (job.tags && Array.isArray(job.tags)) {
        tagsHtml = job.tags.map(t => `<span class="ant-tag ant-tag-processing">${t}</span>`).join(" ");
    } else {
        tagsHtml = '<span class="ant-tag ant-tag-processing">#AI2026</span> <span class="ant-tag ant-tag-processing">#Shorts</span>';
    }
    document.getElementById("modal-video-tags").innerHTML = tagsHtml;

    const container = document.getElementById("modal-video-container");
    const downloadBtn = document.getElementById("modal-download-btn");
    const fbBtn = document.querySelector("#video-modal .fb-btn");
    const tiktokBtn = document.querySelector("#video-modal .tiktok-btn");
    const xBtn = document.querySelector("#video-modal .x-btn");

    const hasVideo = job.video_final_path || job.video_raw_path;

    if (container) {
        if (hasVideo) {
            // Use the smart stream API — works for clone (downloads/) AND generated (final/) videos
            const streamUrl = `${API_BASE}/api/video-stream/${job.id}`;
            container.innerHTML = `
                <video
                    id="modal-player"
                    src="${streamUrl}"
                    controls
                    autoplay
                    loop
                    playsinline
                    style="width:100%;height:100%;object-fit:cover;border-radius:12px;background:#000;"
                    onerror="document.getElementById('modal-player-err').style.display='block'"
                >
                    Trình duyệt không hỗ trợ phát video.
                </video>
                <div id="modal-player-err" style="display:none;color:#ff6b6b;text-align:center;padding:20px;">
                    ⚠️ Không tải được video. Thử <a href="${streamUrl}" target="_blank" style="color:#60a5fa;">mở trực tiếp</a>
                </div>
            `;
            if (downloadBtn) {
                downloadBtn.style.display = "inline-flex";
                downloadBtn.href = streamUrl;
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
            testPostJob(job.id, 'tiktok');
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
        const storageDirEl = document.getElementById("settings-storage-dir");

        if (apiKeyEl && data.gemini_api_key !== undefined) apiKeyEl.value = data.gemini_api_key;
        if (maxWorkersEl && data.max_workers !== undefined) maxWorkersEl.value = data.max_workers;
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
            const storageDir = document.getElementById("settings-storage-dir").value;

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

// ─── Facebook Graph API: Page Scanner ──────────────────────────────────────

let _fbScanPoller = null;

async function scanFbPages() {
    const tokenInput = document.getElementById("fb-token-input");
    const btn = document.getElementById("btn-fb-scan-pages");
    const statusEl = document.getElementById("fb-scan-status");
    const selectorWrap = document.getElementById("fb-page-selector-wrap");
    const saveBtn = document.getElementById("btn-fb-save-page");
    if (!btn || !statusEl) return;

    const token = tokenInput ? tokenInput.value.trim() : "";
    if (!token) {
        statusEl.style.display = "block";
        statusEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color:#faad14;"></i> Vui lòng paste User Access Token vào ô trên trước.`;
        return;
    }

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang lấy Pages...`;
    statusEl.style.display = "block";
    statusEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin" style="color:#1890ff;"></i> Đang gọi Facebook Graph API...`;
    selectorWrap.style.display = "none";
    if (saveBtn) saveBtn.style.display = "none";

    try {
        // Call Graph API directly with the user-provided token
        const apiUrl = `https://graph.facebook.com/v20.0/me/accounts?fields=id,name,category,access_token,fan_count&access_token=${encodeURIComponent(token)}`;
        const res = await fetch(apiUrl);
        const data = await res.json();

        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-magnifying-glass"></i> Lấy Danh Sách Pages`;

        if (data.error) {
            statusEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color:#ff4d4f;"></i> <strong>Lỗi Facebook:</strong> ${data.error.message} (code ${data.error.code})`;
            return;
        }

        const pages = data.data || [];
        if (pages.length === 0) {
            statusEl.innerHTML = `<i class="fa-solid fa-circle-exclamation" style="color:#faad14;"></i> Không tìm thấy Pages nào. Bạn cần có ít nhất 1 Facebook Page với quyền admin.`;
            return;
        }

        statusEl.innerHTML = `<i class="fa-solid fa-circle-check" style="color:#52c41a;"></i> Tìm thấy <strong>${pages.length}</strong> Pages!`;
        populateFbPageDropdown(pages);
        selectorWrap.style.display = "block";

    } catch (err) {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-magnifying-glass"></i> Lấy Danh Sách Pages`;
        statusEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color:#ff4d4f;"></i> Lỗi: ${err.message}`;
    }
}

function populateFbPageDropdown(pages) {
    const select = document.getElementById("fb-page-select");
    const saveBtn = document.getElementById("btn-fb-save-page");
    if (!select || !saveBtn) return;

    select.innerHTML = `<option value="">-- Chọn Page muốn đăng --</option>`;
    pages.forEach(page => {
        const opt = document.createElement("option");
        opt.value = page.id;
        opt.textContent = `${page.name} (${page.category || "Page"})`;
        opt.dataset.token = page.access_token || "";
        opt.dataset.name = page.name;
        select.appendChild(opt);
    });
    select.onchange = () => {
        saveBtn.style.display = select.value ? "inline-flex" : "none";
    };
}

async function saveFbPage() {
    const select = document.getElementById("fb-page-select");
    const saveBtn = document.getElementById("btn-fb-save-page");
    const statusEl = document.getElementById("fb-scan-status");
    if (!select || !select.value) return;

    const selectedOpt = select.options[select.selectedIndex];
    const pageId = selectedOpt.value;
    const pageName = selectedOpt.dataset.name;
    const pageToken = selectedOpt.dataset.token;

    saveBtn.disabled = true;
    saveBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang lưu...`;

    try {
        const res = await fetch(`${API_BASE}/api/social/fb-select-page`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ page_id: pageId, page_name: pageName, page_access_token: pageToken }),
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, "success");
            statusEl.innerHTML = `<i class="fa-solid fa-circle-check" style="color:#52c41a;"></i> ${data.message}`;
            _updateFbActivePage(pageName, pageId);
            const modeTag = document.getElementById("fb-mode-tag");
            if (modeTag) {
                modeTag.innerHTML = `<i class="fa-solid fa-bolt"></i> Graph API ✅`;
                Object.assign(modeTag.style, { background: "rgba(82,196,26,0.12)", color: "#52c41a", border: "1px solid rgba(82,196,26,0.3)" });
            }
        } else {
            showToast(data.detail || "Lỗi lưu Page", "error");
        }
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, "error");
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> Lưu & Dùng Page Này`;
    }
}

function _updateFbActivePage(name, id) {
    const wrap = document.getElementById("fb-active-page-wrap");
    const nameEl = document.getElementById("fb-active-page-name");
    const idEl = document.getElementById("fb-active-page-id");
    if (wrap && nameEl && idEl) {
        nameEl.textContent = name;
        idEl.textContent = `(ID: ${id})`;
        wrap.style.display = "block";
    }
}

function initFbPageScanner() {
    const scanBtn = document.getElementById("btn-fb-scan-pages");
    if (scanBtn) scanBtn.addEventListener("click", scanFbPages);

    const saveBtn = document.getElementById("btn-fb-save-page");
    if (saveBtn) saveBtn.addEventListener("click", saveFbPage);

    // Open Facebook Graph API Explorer in browser (user is already logged in)
    const explorerBtn = document.getElementById("btn-fb-open-explorer");
    if (explorerBtn) {
        explorerBtn.addEventListener("click", async () => {
            explorerBtn.disabled = true;
            explorerBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang mở...`;
            try {
                // Open via our server (which launches browser with FB session)
                await fetch(`${API_BASE}/api/social/fb-open-explorer`, { method: "POST" });
                showToast("Đã mở Facebook Graph API Explorer. Tạo token, copy và paste vào ô bên dưới.", "info");
            } catch (e) {
                // Fallback: open in user's default browser
                window.open("https://developers.facebook.com/tools/explorer/", "_blank");
                showToast("Đã mở trong trình duyệt. Đăng nhập và lấy token.", "info");
            }
            setTimeout(() => {
                explorerBtn.disabled = false;
                explorerBtn.innerHTML = `<i class="fa-brands fa-facebook"></i> Mở Facebook Token Generator`;
            }, 2000);
        });
    }

    // Press Enter in token input to trigger scan
    const tokenInput = document.getElementById("fb-token-input");
    if (tokenInput) {
        tokenInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") scanFbPages();
        });
        // Toggle show/hide password
        tokenInput.addEventListener("dblclick", () => {
            tokenInput.type = tokenInput.type === "password" ? "text" : "password";
        });
    }
}

// Auto-init when DOM is ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initFbPageScanner);
} else {
    initFbPageScanner();
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
    if (nameEl) {
        // Lấy title từ job list đang cache
        const job = currentJobs.find(j => j.id === jobId);
        nameEl.textContent = `Video: ${job ? (job.title || `#${jobId}`) : `Job #${jobId}`}`;
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
    const postBtn = document.getElementById("fb-modal-post-btn");
    if (postBtn) { postBtn.disabled = true; postBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang gửi...'; }

    try {
        const res = await fetch(`${API_BASE}/api/social/post-to-profiles`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ job_id: _fbModalJobId, profile_ids: profileIds, max_workers: maxWorkers })
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

// ── Auto-load profiles khi vào Social tab ───────────────────
document.addEventListener("DOMContentLoaded", () => {
    // Load FB profiles khi click vào tab social
    const socialNav = document.querySelector('[data-tab="social"]');
    if (socialNav) {
        socialNav.addEventListener("click", () => {
            setTimeout(loadFbProfiles, 100);
        });
    }
    // Cũng load ngay nếu đang ở tab social
    if (document.querySelector('#tab-social.active')) {
        loadFbProfiles();
    }
});
