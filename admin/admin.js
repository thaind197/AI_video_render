/* Veo Studio AI PRO - Admin Control Panel Logic */

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    checkAdminAuth();
    bindAdminLoginForm();
    bindCreateForm();
});

function checkAdminAuth() {
    const token = localStorage.getItem('admin_token');
    const overlay = document.getElementById('admin-auth-overlay');
    if (!token) {
        if (overlay) overlay.style.display = 'flex';
    } else {
        if (overlay) overlay.style.display = 'none';
        const userEmail = localStorage.getItem('admin_email') || 'admin@veostudio.ai';
        const emailEl = document.getElementById('admin-email-display');
        if (emailEl) emailEl.textContent = userEmail;
        loadDashboardData();
    }
}

function bindAdminLoginForm() {
    const form = document.getElementById('admin-login-form');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('admin-email-input').value.trim();
        const password = document.getElementById('admin-password-input').value.trim();
        const errorEl = document.getElementById('admin-login-error');

        try {
            const res = await fetch('/api/admin/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            const data = await res.json();
            if (res.ok && data.status === 'success') {
                localStorage.setItem('admin_token', data.token);
                localStorage.setItem('admin_email', data.user ? data.user.email : email);
                if (errorEl) errorEl.style.display = 'none';
                checkAdminAuth();
            } else {
                if (errorEl) {
                    errorEl.textContent = data.detail || data.message || "Đăng nhập thất bại!";
                    errorEl.style.display = 'block';
                }
            }
        } catch (err) {
            if (errorEl) {
                errorEl.textContent = "Lỗi kết nối tới server!";
                errorEl.style.display = 'block';
            }
        }
    });
}

function adminLogout() {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_email');
    checkAdminAuth();
}

function initTabs() {
    const links = document.querySelectorAll('.nav-link');
    links.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            links.forEach(l => l.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

            link.classList.add('active');
            const targetId = link.getAttribute('data-tab');
            const panel = document.getElementById(targetId);
            if (panel) panel.classList.add('active');
        });
    });
}

async function loadDashboardData() {
    await Promise.all([
        fetchStats(),
        fetchLicenses(),
        fetchPromptHistory()
    ]);
}

async function fetchStats() {
    try {
        const res = await fetch('/api/admin/stats');
        const data = await res.json();
        
        document.getElementById('stat-total-users').textContent = data.total_users || 0;
        document.getElementById('stat-active-licenses').textContent = data.active_licenses || 0;
        document.getElementById('stat-active-devices').textContent = data.activated_devices || 0;
        document.getElementById('stat-total-prompts').textContent = data.total_prompts_generated || 0;
    } catch (e) {
        console.error("Lỗi fetchStats:", e);
    }
}

async function fetchLicenses() {
    try {
        const res = await fetch('/api/admin/licenses');
        const data = await res.json();
        const tbody = document.getElementById('licenses-table-body');
        
        if (!data.licenses || data.licenses.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">Chưa có dữ liệu License.</td></tr>';
            return;
        }

        tbody.innerHTML = data.licenses.map(lic => {
            const isBlocked = lic.user_status === 'blocked';
            const boundCount = lic.bound_devices_count || 0;
            const maxDevs = lic.max_devices || 1;
            const validUntilStr = lic.valid_until ? String(lic.valid_until).substring(0, 10) : 'N/A';

            let modsList = [];
            try {
                modsList = typeof lic.allowed_modules === 'string' ? JSON.parse(lic.allowed_modules) : (lic.allowed_modules || []);
            } catch(e) {
                modsList = ["veo_generate", "tiktok_clone", "video_library", "social_autopost", "engine_settings"];
            }

            const modBadgesHtml = modsList.map(m => {
                let label = m;
                if (m === 'veo_generate') label = '⚡Veo';
                if (m === 'tiktok_clone') label = '📋TikTok';
                if (m === 'video_library') label = '🎬Library';
                if (m === 'social_autopost') label = '🚀Social';
                if (m === 'engine_settings') label = '⚙️Settings';
                return `<span class="badge badge-tier" style="margin-right:2px; font-size:10px;">${label}</span>`;
            }).join('');

            return `
                <tr>
                    <td><strong>${escapeHtml(lic.email || 'N/A')}</strong><br><small style="color:#64748b;">${escapeHtml(lic.full_name || '')}</small></td>
                    <td><code style="color:#38bdf8; font-weight:bold;">${escapeHtml(lic.license_key)}</code></td>
                    <td><span class="badge badge-tier">${escapeHtml(lic.tier)}</span></td>
                    <td style="max-width:180px;">${modBadgesHtml}</td>
                    <td><strong>${boundCount} / ${maxDevs} Máy</strong></td>
                    <td>${validUntilStr}</td>
                    <td><span class="badge ${isBlocked ? 'badge-blocked' : 'badge-active'}">${isBlocked ? 'Bị Khóa' : 'Hoạt Động'}</span></td>
                    <td style="display:flex; gap:6px; flex-wrap:wrap;">
                        <button class="btn btn-primary" style="padding:6px 10px; font-size:12px;" onclick="editModules('${lic.id}', '${encodeURIComponent(JSON.stringify(modsList))}')" title="Sửa phân quyền module">
                            <i class="fa-solid fa-pen-to-square"></i> Quyền
                        </button>
                        <button class="btn btn-warning" style="padding:6px 10px; font-size:12px;" onclick="resetMac('${lic.id}')" title="Reset MAC ID">
                            <i class="fa-solid fa-rotate-left"></i> Reset
                        </button>
                        <button class="btn btn-warning" style="padding:6px 10px; font-size:12px; background:#f59e0b; border-color:#d97706;" onclick="openResetPasswordModal('${lic.user_id}', '${escapeHtml(lic.email)}')" title="Đổi Mật Khẩu">
                            <i class="fa-solid fa-key"></i> Đổi MK
                        </button>
                        <button class="btn btn-danger" style="padding:6px 10px; font-size:12px;" onclick="toggleBlock('${lic.user_id}', ${!isBlocked})" title="${isBlocked ? 'Mở khóa' : 'Khóa'}">
                            <i class="fa-solid ${isBlocked ? 'fa-unlock' : 'fa-lock'}"></i> ${isBlocked ? 'Mở' : 'Khóa'}
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.error("Lỗi fetchLicenses:", e);
    }
}

async function fetchPromptHistory() {
    try {
        const res = await fetch('/api/admin/prompt-history?limit=50');
        const data = await res.json();
        const tbody = document.getElementById('prompts-table-body');

        if (!data.history || data.history.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">Chưa có lịch sử Prompt nào.</td></tr>';
            return;
        }

        tbody.innerHTML = data.history.map(item => {
            const dtStr = item.created_at ? String(item.created_at).replace('T', ' ').substring(0, 19) : '';
            return `
                <tr>
                    <td>#${item.id}</td>
                    <td><small style="color:#94a3b8;">${item.user_id ? item.user_id.substring(0, 8) + '...' : 'System'}</small></td>
                    <td><code style="color:#38bdf8;">${escapeHtml(item.mac_id || 'N/A')}</code></td>
                    <td>${item.aspect_ratio || '9:16'}</td>
                    <td><span class="badge badge-tier">${item.model || 'veo-2'}</span></td>
                    <td style="max-width: 300px; word-break: break-word;">${escapeHtml(item.veo_prompt || '')}</td>
                    <td><small>${dtStr}</small></td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.error("Lỗi fetchPromptHistory:", e);
    }
}

function showToast(message, type = 'info', title = '', duration = 4500) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const icons = {
        success: 'fa-solid fa-circle-check',
        error: 'fa-solid fa-circle-xmark',
        warning: 'fa-solid fa-triangle-exclamation',
        info: 'fa-solid fa-circle-info'
    };

    const defaultTitles = {
        success: 'Thành Công',
        error: 'Thất Bại',
        warning: 'Cảnh Báo',
        info: 'Thông Báo'
    };

    const toastTitle = title || defaultTitles[type] || 'Thông Báo';

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="${icons[type] || icons.info} toast-icon"></i>
        <div class="toast-body">
            <div class="toast-title">${escapeHtml(toastTitle)}</div>
            <div class="toast-message">${escapeHtml(message)}</div>
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()"><i class="fa-solid fa-xmark"></i></button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-out');
        setTimeout(() => {
            if (toast.parentElement) toast.remove();
        }, 300);
    }, duration);
}

function bindCreateForm() {
    const form = document.getElementById('create-license-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = document.getElementById('new-user-email').value.trim();
        const password = document.getElementById('new-user-password').value.trim();
        const full_name = document.getElementById('new-user-name').value.trim();
        const tier = document.getElementById('new-user-tier').value;
        const max_devices = parseInt(document.getElementById('new-user-max-devs').value, 10);
        const valid_days = parseInt(document.getElementById('new-user-days').value, 10);

        const allowed_modules = Array.from(document.querySelectorAll('.mod-chk:checked')).map(cb => cb.value);

        try {
            const res = await fetch('/api/admin/licenses', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, full_name, tier, max_devices, valid_days, allowed_modules })
            });

            const data = await res.json();
            if (res.ok) {
                showToast(`Mã License Key: ${data.license_key}\nEmail: ${data.email}\nHạn dùng: ${data.valid_until}`, 'success', 'Đã Cấp License Thành Công!');
                form.reset();
                loadDashboardData();
            } else {
                showToast(data.detail || data.message || "Tạo License thất bại!", 'error', 'Lỗi Tạo License Key');
            }
        } catch (err) {
            showToast("Lỗi kết nối tới server!", 'error', 'Lỗi Mạng / Server');
        }
    });
}

function editModules(licenseId, currentModsEncoded) {
    let currentMods = [];
    try {
        currentMods = JSON.parse(decodeURIComponent(currentModsEncoded));
    } catch(e) {
        currentMods = ["veo_generate", "tiktok_clone", "video_library", "social_autopost", "engine_settings"];
    }

    document.getElementById('edit-license-id').value = licenseId;
    document.getElementById('edit-mod-veo').checked = currentMods.includes('veo_generate');
    document.getElementById('edit-mod-tiktok').checked = currentMods.includes('tiktok_clone');
    document.getElementById('edit-mod-library').checked = currentMods.includes('video_library');
    document.getElementById('edit-mod-social').checked = currentMods.includes('social_autopost');
    document.getElementById('edit-mod-settings').checked = currentMods.includes('engine_settings');

    const modal = document.getElementById('edit-modules-modal');
    if (modal) modal.style.display = 'flex';
}

function closeEditModulesModal() {
    const modal = document.getElementById('edit-modules-modal');
    if (modal) modal.style.display = 'none';
}

async function saveEditModules() {
    const licenseId = document.getElementById('edit-license-id').value;
    const selectedMods = [];
    if (document.getElementById('edit-mod-veo').checked) selectedMods.push('veo_generate');
    if (document.getElementById('edit-mod-tiktok').checked) selectedMods.push('tiktok_clone');
    if (document.getElementById('edit-mod-library').checked) selectedMods.push('video_library');
    if (document.getElementById('edit-mod-social').checked) selectedMods.push('social_autopost');
    if (document.getElementById('edit-mod-settings').checked) selectedMods.push('engine_settings');

    try {
        const res = await fetch(`/api/admin/licenses/${licenseId}/modules`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ allowed_modules: selectedMods })
        });
        const data = await res.json();
        showToast(data.message || "Đã cập nhật phân quyền module thành công!", 'success', 'Cập Nhật Phân Quyền');
        closeEditModulesModal();
        fetchLicenses();
    } catch (e) {
        showToast("Lỗi cập nhật phân quyền!", 'error', 'Lỗi Hệ Thống');
    }
}

async function resetMac(licenseId) {
    if (!confirm("Bạn có chắc chắn muốn xóa toàn bộ MAC ID cũ đã binding cho License này? User sẽ có thể đăng nhập trên máy mới.")) return;
    try {
        const res = await fetch(`/api/admin/licenses/${licenseId}/reset-mac`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message || "Đã reset MAC ID thành công!", 'success', 'Reset MAC ID');
        fetchLicenses();
    } catch (e) {
        showToast("Lỗi reset MAC ID!", 'error', 'Lỗi Thao Tác');
    }
}

async function toggleBlock(userId, shouldBlock) {
    const actionName = shouldBlock ? "khóa" : "mở khóa";
    if (!confirm(`Bạn có chắc chắn muốn ${actionName} tài khoản này?`)) return;
    try {
        const res = await fetch(`/api/admin/users/${userId}/block?block=${shouldBlock}`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message || "Đã cập nhật trạng thái!", 'success', 'Trạng Thái Tài Khoản');
        fetchLicenses();
    } catch (e) {
        showToast("Lỗi cập nhật trạng thái user!", 'error', 'Lỗi Thao Tác');
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function openResetPasswordModal(userId, email) {
    document.getElementById('reset-pwd-user-id').value = userId;
    document.getElementById('reset-pwd-email-display').textContent = email;
    document.getElementById('reset-pwd-input').value = '';
    const modal = document.getElementById('reset-password-modal');
    if (modal) modal.style.display = 'flex';
}

function closeResetPasswordModal() {
    const modal = document.getElementById('reset-password-modal');
    if (modal) modal.style.display = 'none';
}

async function submitResetPassword() {
    const userId = document.getElementById('reset-pwd-user-id').value;
    const newPassword = document.getElementById('reset-pwd-input').value.trim();

    if (!newPassword) {
        showToast("Vui lòng nhập mật khẩu mới!", 'error', 'Cảnh Báo');
        return;
    }

    try {
        const res = await fetch(`/api/admin/users/${userId}/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_password: newPassword })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(data.message || "Đã đổi mật khẩu thành công!", 'success', 'Đổi Mật Khẩu');
            closeResetPasswordModal();
            fetchLicenses();
        } else {
            showToast(data.detail || data.message || "Đổi mật khẩu thất bại!", 'error', 'Lỗi Thao Tác');
        }
    } catch (e) {
        showToast("Lỗi kết nối tới Server!", 'error', 'Lỗi Thao Tác');
    }
}

// Expose global functions to window
window.editModules = editModules;
window.closeEditModulesModal = closeEditModulesModal;
window.saveEditModules = saveEditModules;
window.resetMac = resetMac;
window.toggleBlock = toggleBlock;
window.openResetPasswordModal = openResetPasswordModal;
window.closeResetPasswordModal = closeResetPasswordModal;
window.submitResetPassword = submitResetPassword;
window.adminLogout = adminLogout;
window.loadDashboardData = loadDashboardData;
window.showToast = showToast;


