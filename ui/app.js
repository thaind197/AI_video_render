// Real-time API Client connected to FastAPI Backend & SQLite DB
const API_BASE = ""; // Same origin / Relative path

let currentJobs = [];
let isEngineRunning = false;

document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initForms();
    initModal();
    initEngineControl();

    // Initial Fetch & Start Real-time Polling every 2.5 seconds
    fetchJobsAndStats();
    setInterval(fetchJobsAndStats, 2500);
});

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
    const generating = (stats.GENERATING_VEO || 0) + (stats.SCRIPTED || 0);
    const rendered = (stats.PROCESSING_FFMPEG || 0) + (stats.VEO_DONE || 0) + (stats.READY_TO_POST || 0) + (stats.PUBLISHED || 0);
    const published = stats.PUBLISHED || 0;

    document.getElementById("stat-total").textContent = total;
    document.getElementById("stat-generating").textContent = generating;
    document.getElementById("stat-rendered").textContent = rendered;
    document.getElementById("stat-published").textContent = published;

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
            case "READY_TO_POST":
                statusTag = '<span class="ant-tag ant-tag-processing"><i class="fa-solid fa-cloud-arrow-up"></i> Sẵn Sàng Đăng</span>';
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
            case "FAILED":
                statusTag = `<span class="ant-tag ant-tag-error" title="${job.error_msg || ''}"><i class="fa-solid fa-circle-xmark"></i> Thất Bại</span>`;
                break;
            default:
                statusTag = '<span class="ant-tag">Chờ Xử Lý (Pending)</span>';
        }

        const typeBadge = job.source_type === "PROMPT"
            ? '<span class="ant-tag ant-tag-processing">PROMPT</span>'
            : '<span class="ant-tag ant-tag-warning">CLONE</span>';

        const fbIcon = job.fb_posted ? '<i class="fa-brands fa-facebook text-blue" title="Facebook Reels"></i> ' : '';
        const tiktokIcon = job.tiktok_posted ? '<i class="fa-brands fa-tiktok" style="color:#ee1d52;" title="TikTok"></i> ' : '';
        const xIcon = job.x_posted ? '<i class="fa-brands fa-x-twitter" title="X"></i>' : '';
        const platformsStr = (fbIcon || tiktokIcon || xIcon) ? `${fbIcon}${tiktokIcon}${xIcon}` : '-';

        const promptExcerpt = job.veo_prompt ? (job.veo_prompt.substring(0, 50) + "...") : "Chờ sinh prompt...";
        const titleStr = job.title || job.source_input || `Job #${job.id}`;

        tr.innerHTML = `
            <td><strong>#${job.id}</strong></td>
            <td>${typeBadge}</td>
            <td><strong>${titleStr}</strong></td>
            <td style="max-width: 250px; font-size: 11px; color: var(--text-secondary);">${promptExcerpt}</td>
            <td>10s</td>
            <td>${statusTag}</td>
            <td style="font-size: 16px;">${platformsStr}</td>
            <td>
                <button class="ant-btn ant-btn-default btn-preview" onclick="openPreviewModal(${job.id})">
                    <i class="fa-solid fa-eye"></i> Xem Chi Tiết
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Render Video Library 9:16 Grid
function renderLibraryGrid(jobs) {
    const grid = document.getElementById("library-video-grid");
    if (!grid) return;
    grid.innerHTML = "";

    const readyJobs = jobs.filter(j => j.status === "PUBLISHED" || j.status === "READY_TO_POST" || j.status === "VEO_DONE");
    readyJobs.forEach(job => {
        const card = document.createElement("div");
        card.className = "video-card-916";
        card.onclick = () => openPreviewModal(job.id);
        card.innerHTML = `
            <div class="video-thumbnail-916">
                <i class="fa-solid fa-circle-play play-icon"></i>
            </div>
            <div class="video-card-info">
                <h4>${job.title || `Video #${job.id}`}</h4>
                <small style="color: var(--text-secondary);">10s • 9:16 HD</small>
            </div>
        `;
        grid.appendChild(card);
    });
}

// Form Handlers (Call REST API)
function initForms() {
    const promptForm = document.getElementById("form-generate-prompt");
    if (promptForm) {
        promptForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const topic = document.getElementById("prompt-topic").value;
            const count = parseInt(document.getElementById("prompt-count").value) || 10;

            try {
                const res = await fetch(`${API_BASE}/api/generate-prompt`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ topic, count })
                });
                const data = await res.json();
                if (res.ok) {
                    alert(`✅ ${data.message}`);
                    fetchJobsAndStats();
                } else {
                    alert(`❌ Lỗi: ${data.detail}`);
                }
            } catch (err) {
                alert(`❌ Lỗi kết nối API: ${err.message}`);
            }
        });
    }

    const cloneForm = document.getElementById("form-clone-video");
    if (cloneForm) {
        cloneForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const url = document.getElementById("clone-url").value;

            try {
                const res = await fetch(`${API_BASE}/api/clone-video`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ url })
                });
                const data = await res.json();
                if (res.ok) {
                    alert(`✅ ${data.message}`);
                    fetchJobsAndStats();
                } else {
                    alert(`❌ Lỗi: ${data.detail}`);
                }
            } catch (err) {
                alert(`❌ Lỗi kết nối API: ${err.message}`);
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
                alert(`🌐 ${data.message}`);
            } catch (err) {
                alert(`❌ Lỗi mở trình duyệt đăng nhập: ${err.message}`);
            }
        });
    });
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
                    alert(`⚙️ ${data.message}`);
                    fetchJobsAndStats();
                }
            } catch (err) {
                alert(`❌ Lỗi khởi chạy Engine: ${err.message}`);
            }
        });
    }
}

// Modal Preview Handler
function initModal() {
    const modal = document.getElementById("video-modal");
    const closeBtn = document.getElementById("modal-close-btn");
    if (closeBtn && modal) {
        closeBtn.onclick = () => { modal.style.display = "none"; };
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

    document.getElementById("video-modal").style.display = "flex";
}
