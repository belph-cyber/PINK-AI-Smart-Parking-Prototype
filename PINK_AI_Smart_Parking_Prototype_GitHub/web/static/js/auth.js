// -*- coding: utf-8 -*-
/* ==============================================================================
   PINK AI: Smart Parking Management System
   Authentication, Session Management & RBAC Navigation Controller
============================================================================== */

let currentUser = null;

function initAuth() {
  currentUser = API.getUser();
  if (!currentUser || !API.getToken()) {
    showLoginModal();
  } else {
    applyUserSession(currentUser);
  }

  window.addEventListener('auth:required', () => {
    showLoginModal('กรุณาเข้าสู่ระบบก่อนใช้งาน');
  });

  // Start live clock in header
  updateLiveClock();
  setInterval(updateLiveClock, 1000);
}

function updateLiveClock() {
  const clockEl = document.getElementById('header-live-clock');
  const greetingEl = document.getElementById('header-greeting-title');
  const dateEl = document.getElementById('header-date-text');

  const now = new Date();
  const timeStr = now.toLocaleTimeString('th-TH');
  const dateStr = now.toLocaleDateString('th-TH', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  if (clockEl) clockEl.innerText = timeStr;
  if (dateEl) dateEl.innerText = dateStr;

  const hour = now.getHours();
  let greet = "Good Evening";
  if (hour < 12) greet = "Good Morning";
  else if (hour < 17) greet = "Good Afternoon";

  if (greetingEl && currentUser) {
    greetingEl.innerText = `${greet}, ${currentUser.name || currentUser.username}`;
  }
}

function showLoginModal(msg = '') {
  const modal = document.getElementById('login-modal');
  if (modal) {
    modal.style.display = 'flex';
    const errBox = document.getElementById('login-error-msg');
    if (errBox) {
      errBox.innerText = msg;
      errBox.style.display = msg ? 'block' : 'none';
    }
  }
}

function hideLoginModal() {
  const modal = document.getElementById('login-modal');
  if (modal) modal.style.display = 'none';
}

async function handleLoginSubmit(event) {
  if (event) event.preventDefault();
  const uInput = document.getElementById('login-username');
  const pInput = document.getElementById('login-password');
  const errBox = document.getElementById('login-error-msg');
  const submitBtn = document.getElementById('login-submit-btn');

  const username = uInput ? uInput.value.trim() : '';
  const password = pInput ? pInput.value.trim() : '';

  if (!username || !password) {
    if (errBox) {
      errBox.innerText = 'กรุณากรอกชื่อผู้ใช้และรหัสผ่าน';
      errBox.style.display = 'block';
    }
    return;
  }

  try {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> กำลังตรวจสอบสิทธิ์...';
    }
    if (errBox) errBox.style.display = 'none';

    const res = await API.login(username, password);
    currentUser = res.user;
    hideLoginModal();
    applyUserSession(currentUser);
  } catch (err) {
    if (errBox) {
      errBox.innerText = err.message || 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง';
      errBox.style.display = 'block';
    }
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = '<i class="fa-solid fa-right-to-bracket"></i> เข้าสู่ระบบ (Sign In)';
    }
  }
}

function quickFillLogin(username, password) {
  const uInput = document.getElementById('login-username');
  const pInput = document.getElementById('login-password');
  if (uInput) uInput.value = username;
  if (pInput) pInput.value = password;
  handleLoginSubmit();
}

function logout() {
  API.clearAuth();
  currentUser = null;
  showLoginModal('ออกจากระบบเรียบร้อยแล้ว');
}

function applyUserSession(user) {
  if (!user) return;

  // Update Sidebar User Card
  const avatarEl = document.getElementById('sidebar-user-avatar');
  const nameEl = document.getElementById('sidebar-user-name');
  const roleEl = document.getElementById('sidebar-user-role');
  const greetingSub = document.getElementById('header-greeting-sub');

  if (avatarEl) avatarEl.src = user.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150';
  if (nameEl) nameEl.innerText = user.name || user.username;
  if (roleEl) roleEl.innerText = user.role_name || user.role_code;
  if (greetingSub) greetingSub.innerText = `ยินดีต้อนรับสู่ระบบ PINK AI Smart Parking (${user.faculty || user.department || user.role_name})`;

  // Render Navigation items strictly matching role
  renderSidebarNav(user.role_code);

  // Load Dashboard corresponding to role
  if (user.role_code === 'ADMIN') {
    switchView('admin-overview');
  } else if (user.role_code === 'SECURITY') {
    switchView('security-dashboard');
  } else {
    // STUDENT or TEACHER
    switchView('user-portal');
  }
}

function renderSidebarNav(role) {
  const navList = document.getElementById('sidebar-nav-list');
  if (!navList) return;

  let html = '';

  if (role === 'STUDENT' || role === 'TEACHER') {
    html = `
      <div class="nav-group-title">พอร์ทัลส่วนตัว (${role})</div>
      <div class="nav-item active" id="nav-user-portal" onclick="switchView('user-portal')">
        <i class="fa-solid fa-id-card"></i>
        <span>บัตรจอดรถ & พิกัดรถ</span>
      </div>
      <div class="nav-item" id="nav-user-vehicles" onclick="switchView('user-vehicles')">
        <i class="fa-solid fa-car"></i>
        <span>ยานพาหนะของฉัน</span>
      </div>
      <div class="nav-item" id="nav-user-history" onclick="switchView('user-history')">
        <i class="fa-solid fa-clock-rotate-left"></i>
        <span>ประวัติการเข้า-ออก</span>
      </div>
      <div class="nav-item" id="nav-user-messages" onclick="switchView('user-messages')">
        <i class="fa-solid fa-comments"></i>
        <span>ข้อความ & แจ้งเตือน</span>
        <span class="nav-badge" id="user-unread-badge" style="display:none;">0</span>
      </div>
    `;
  } else if (role === 'SECURITY') {
    html = `
      <div class="nav-group-title">ศูนย์ควบคุม รปภ. (Security)</div>
      <div class="nav-item active" id="nav-security-dashboard" onclick="switchView('security-dashboard')">
        <i class="fa-solid fa-shield-halved"></i>
        <span>แดชบอร์ดรักษาการ</span>
      </div>
      <div class="nav-item" id="nav-security-slotmap" onclick="switchView('security-slotmap')">
        <i class="fa-solid fa-map-location-dot"></i>
        <span>แผนผังช่องจอด (Slot Map)</span>
      </div>
      <div class="nav-item" id="nav-security-cctv" onclick="switchView('security-cctv')">
        <i class="fa-solid fa-video"></i>
        <span>กล้องวงจรปิด LPR (5 ตัว)</span>
        <span class="nav-badge">LIVE</span>
      </div>
      <div class="nav-item" id="nav-security-gate" onclick="switchView('security-gate')">
        <i class="fa-solid fa-torii-gate"></i>
        <span>ควบคุมไม้กั้น (Gate Control)</span>
      </div>
      <div class="nav-item" id="nav-security-ai" onclick="switchView('security-ai')">
        <i class="fa-solid fa-microchip"></i>
        <span>ตรวจสอบเหตุการณ์ AI</span>
        <span class="nav-badge" id="sec-ai-pending-badge" style="background:var(--color-warning);">0</span>
      </div>
      <div class="nav-item" id="nav-security-search" onclick="switchView('security-search')">
        <i class="fa-solid fa-magnifying-glass"></i>
        <span>ค้นหาข้อมูลรถ & ทะเบียน</span>
      </div>
      <div class="nav-item" id="nav-security-messages" onclick="switchView('security-messages')">
        <i class="fa-solid fa-headset"></i>
        <span>สนทนากับเจ้าของรถ</span>
      </div>
    `;
  } else if (role === 'ADMIN') {
    html = `
      <div class="nav-group-title">ผู้ดูแลระบบ (Admin)</div>
      <div class="nav-item active" id="nav-admin-overview" onclick="switchView('admin-overview')">
        <i class="fa-solid fa-chart-pie"></i>
        <span>ภาพรวมระบบ (Overview)</span>
      </div>
      <div class="nav-group-title">การบริหารจัดการ</div>
      <div class="nav-item" id="nav-admin-users" onclick="switchView('admin-users')">
        <i class="fa-solid fa-users-gear"></i>
        <span>จัดการผู้ใช้งาน & สิทธิ์</span>
      </div>
      <div class="nav-item" id="nav-admin-vehicles" onclick="switchView('admin-vehicles')">
        <i class="fa-solid fa-car-side"></i>
        <span>จัดการทะเบียนรถ & อนุมัติ</span>
      </div>
      <div class="nav-item" id="nav-admin-parking" onclick="switchView('admin-parking')">
        <i class="fa-solid fa-square-parking"></i>
        <span>จัดการชั้น & ช่องจอด</span>
      </div>
      <div class="nav-item" id="nav-security-cctv" onclick="switchView('security-cctv')">
        <i class="fa-solid fa-video"></i>
        <span>กล้องวงจรปิด & RTSP</span>
      </div>
      <div class="nav-item" id="nav-admin-audit" onclick="switchView('admin-audit')">
        <i class="fa-solid fa-receipt"></i>
        <span>บันทึกประวัติ (Audit Logs)</span>
      </div>
    `;
  }

  navList.innerHTML = html;
}

function switchView(viewId) {
  // Update sidebar active class
  document.querySelectorAll('.app-sidebar .nav-item').forEach(el => el.classList.remove('active'));
  const activeNav = document.getElementById(`nav-${viewId}`);
  if (activeNav) activeNav.classList.add('active');

  // Show target section, hide all other sections
  document.querySelectorAll('.view-section').forEach(sec => sec.style.display = 'none');
  const targetSection = document.getElementById(`view-${viewId}`);
  if (targetSection) {
    targetSection.style.display = 'block';
  }

  // Trigger data loader for view
  if (viewId === 'user-portal') loadUserPortalData();
  else if (viewId === 'user-vehicles') loadUserVehiclesData();
  else if (viewId === 'user-messages') loadUserMessagesData();
  else if (viewId === 'security-dashboard') loadSecurityDashboardData();
  else if (viewId === 'security-slotmap') loadSecuritySlotMapData();
  else if (viewId === 'security-cctv') loadSecurityCctvData();
  else if (viewId === 'security-gate') loadSecurityGateData();
  else if (viewId === 'security-ai') loadSecurityAiEventsData();
  else if (viewId === 'security-messages') loadSecurityMessagesData();
  else if (viewId === 'admin-overview') loadAdminOverviewData();
  else if (viewId === 'admin-users') loadAdminUsersData();
  else if (viewId === 'admin-vehicles') loadAdminVehiclesData();
  else if (viewId === 'admin-audit') loadAdminAuditData();
}

