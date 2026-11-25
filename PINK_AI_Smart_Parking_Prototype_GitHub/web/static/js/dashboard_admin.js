// -*- coding: utf-8 -*-
/* ==============================================================================
   PINK AI: Admin Management Dashboard Controller
============================================================================== */

async function loadAdminOverviewData() {
  try {
    const res = await API.getSystemHealth();
    const h = res.health || {};

    const uEl = document.getElementById('admin-stat-users');
    const vEl = document.getElementById('admin-stat-vehicles');
    const pEl = document.getElementById('admin-stat-parked');
    const sEl = document.getElementById('admin-stat-slots');

    if (uEl) uEl.innerText = h.total_users || 0;
    if (vEl) vEl.innerText = h.total_vehicles || 0;
    if (pEl) pEl.innerText = h.total_parked || 0;
    if (sEl) sEl.innerText = h.total_slots || 0;

    // Load recent audit logs in overview
    loadAdminAuditData(5);
  } catch (err) {
    console.error('loadAdminOverviewData error:', err);
  }
}

async function loadAdminUsersData() {
  const tableEl = document.getElementById('admin-users-table-body');
  if (!tableEl) return;

  try {
    const res = await API.getAdminUsers();
    const users = res.users || [];

    tableEl.innerHTML = users.map(u => `
      <tr>
        <td>#${u.id}</td>
        <td><strong>${u.username}</strong></td>
        <td>${u.name}</td>
        <td><span class="stat-pill pill-purple">${u.role_name || u.role_code}</span></td>
        <td>${u.faculty || '-'} (${u.department || '-'})</td>
        <td>${u.phone || '-'}</td>
        <td>
          <span class="stat-pill ${u.is_active ? 'pill-green' : 'pill-red'}">
            ${u.is_active ? 'เปิดใช้งาน' : 'ระงับสิทธิ์'}
          </span>
        </td>
        <td>
          <button class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="toggleUserStatus(${u.id}, ${u.is_active ? 0 : 1})">
            ${u.is_active ? 'ระงับ' : 'เปิดสิทธิ์'}
          </button>
          <button class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="promptResetPassword(${u.id}, '${u.username}')">
            รีเซ็ตรหัส
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('loadAdminUsersData error:', err);
  }
}

async function toggleUserStatus(userId, newActiveStatus) {
  if (!confirm(`ยืนยันการ${newActiveStatus ? 'เปิดใช้งาน' : 'ระงับสิทธิ์'}ผู้ใช้นี้?`)) return;
  try {
    await API.updateAdminUser(userId, { is_active: newActiveStatus });
    loadAdminUsersData();
  } catch (err) {
    alert(err.message || 'ไม่สามารถอัปเดตผู้ใช้ได้');
  }
}

async function promptResetPassword(userId, username) {
  const newPass = prompt(`กรอกรหัสผ่านใหม่สำหรับ ${username}:`, "pass1234");
  if (!newPass) return;
  try {
    await API.updateAdminUser(userId, { password: newPass });
    alert(`รีเซ็ตรหัสผ่านสำหรับ ${username} เรียบร้อยแล้ว`);
  } catch (err) {
    alert(err.message || 'ไม่สามารถรีเซ็ตรหัสผ่านได้');
  }
}

function openCreateUserModal() {
  const modal = document.getElementById('create-user-modal');
  if (modal) modal.style.display = 'flex';
}

function closeCreateUserModal() {
  const modal = document.getElementById('create-user-modal');
  if (modal) modal.style.display = 'none';
}

async function handleCreateUserSubmit(event) {
  if (event) event.preventDefault();
  const username = document.getElementById('cu-username').value.trim();
  const password = document.getElementById('cu-password').value.trim();
  const role_code = document.getElementById('cu-role').value;
  const name = document.getElementById('cu-name').value.trim();
  const faculty = document.getElementById('cu-faculty').value.trim();
  const department = document.getElementById('cu-department').value.trim();
  const phone = document.getElementById('cu-phone').value.trim();
  const email = document.getElementById('cu-email').value.trim();

  try {
    await API.createAdminUser({ username, password, role_code, name, faculty, department, phone, email });
    closeCreateUserModal();
    loadAdminUsersData();
    alert('สร้างบัญชีผู้ใช้งานใหม่สำเร็จ');
  } catch (err) {
    alert(err.message || 'สร้างผู้ใช้ไม่สำเร็จ');
  }
}

async function loadAdminVehiclesData() {
  const tableEl = document.getElementById('admin-vehicles-table-body');
  if (!tableEl) return;

  try {
    const res = await API.getAdminVehicles();
    const vehs = res.vehicles || [];

    tableEl.innerHTML = vehs.map(v => `
      <tr>
        <td>#${v.id}</td>
        <td><strong style="color:#fff; font-size:14px;">${v.plate_display || v.plate_no}</strong></td>
        <td>${v.province}</td>
        <td>${v.brand || ''} ${v.model || ''} (${v.color || '-'})</td>
        <td>${v.owner_name ? `${v.owner_name} (${v.owner_code})` : '<span style="color:var(--text-muted);">ยังไม่มีเจ้าของ</span>'}</td>
        <td><span class="stat-pill pill-purple">${v.owner_role || '-'}</span></td>
        <td>
          <span class="stat-pill ${v.is_active ? 'pill-green' : 'pill-red'}">
            ${v.is_active ? 'อนุมัติแล้ว' : 'ระงับสิทธิ์'}
          </span>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('loadAdminVehiclesData error:', err);
  }
}

async function loadAdminAuditData(limit = 50) {
  const tableEl = document.getElementById('admin-audit-table-body');
  if (!tableEl) return;

  try {
    const res = await API.getAuditLogs();
    const logs = (res.logs || []).slice(0, limit);

    tableEl.innerHTML = logs.map(l => `
      <tr>
        <td>#${l.id}</td>
        <td><strong>${l.username || 'System'}</strong></td>
        <td><span class="stat-pill pill-purple">${l.action}</span></td>
        <td>${l.entity_type || '-'}: ${l.entity_id || '-'}</td>
        <td style="font-size:12px; color:var(--text-secondary); max-width:250px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          ${l.new_value || l.old_value || '-'}
        </td>
        <td style="color:var(--text-dim); font-size:11px;">${l.created_at}</td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('loadAdminAuditData error:', err);
  }
}

