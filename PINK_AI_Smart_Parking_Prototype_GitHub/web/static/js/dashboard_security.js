// -*- coding: utf-8 -*-
/* ==============================================================================
   PINK AI: Security Operations Dashboard Controller
============================================================================== */

let currentSlotMapFloor = 1;
let selectedGateIdForConfirm = null;

async function loadSecurityDashboardData() {
  renderMonthlyCalendar('security-calendar-container', currentCalendarDate);

  try {
    const healthRes = await API.getSystemHealth();
    const h = healthRes.health || {};

    const parkedEl = document.getElementById('sec-stat-parked');
    const totalSlotsEl = document.getElementById('sec-stat-total-slots');
    const pendingAiEl = document.getElementById('sec-stat-pending-ai');
    const badgeEl = document.getElementById('sec-ai-pending-badge');

    if (parkedEl) parkedEl.innerText = h.total_parked || 0;
    if (totalSlotsEl) totalSlotsEl.innerText = h.total_slots || 42;
    if (pendingAiEl) pendingAiEl.innerText = h.pending_ai_events || 0;
    if (badgeEl) {
      badgeEl.innerText = h.pending_ai_events || 0;
      badgeEl.style.display = h.pending_ai_events > 0 ? 'inline-block' : 'none';
    }

    // Floor Summaries Cards
    const overviewRes = await API.getParkingOverview();
    const floors = overviewRes.floors || [];
    const floorListContainer = document.getElementById('sec-floors-summary-list');

    if (floorListContainer) {
      floorListContainer.innerHTML = floors.map(fl => `
        <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-glass); border-radius:var(--radius-md); padding:14px 18px; display:flex; justify-content:space-between; align-items:center; cursor:pointer;"
             onclick="switchToFloorSlotMap(${fl.floor_number})">
          <div style="display:flex; align-items:center; gap:12px;">
            <div style="width:36px; height:36px; border-radius:8px; background:var(--accent-purple-dim); color:var(--accent-purple-light); display:flex; align-items:center; justify-content:center; font-weight:800;">
              ${fl.floor_number}
            </div>
            <div>
              <div style="font-size:14px; font-weight:700; color:#fff;">${fl.floor_name}</div>
              <div style="font-size:11px; color:var(--text-dim);">${fl.detection_type === 'SENSOR_HCSR04' ? 'เซนเซอร์อัลตร้าโซนิก HC-SR04' : 'กล้อง AI LPR ประจำชั้น'}</div>
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:14px;">
            <div style="text-align:right;">
              <div style="font-size:14px; font-weight:700; color:var(--color-success);">${fl.free_slots} ว่าง</div>
              <div style="font-size:11px; color:var(--text-muted);">จาก ${fl.total_slots} ช่อง</div>
            </div>
            <i class="fa-solid fa-chevron-right" style="color:var(--text-muted); font-size:12px;"></i>
          </div>
        </div>
      `).join('');
    }

    // Recent AI Events in Dashboard
    const aiRes = await API.getAiEvents(5);
    const aiListEl = document.getElementById('sec-dashboard-ai-events');
    if (aiListEl) {
      const events = aiRes.events || [];
      if (events.length === 0) {
        aiListEl.innerHTML = '<div style="color:var(--text-muted); padding:16px; text-align:center;">ยังไม่มีเหตุการณ์ AI ตรวจพบ</div>';
      } else {
        aiListEl.innerHTML = events.map(e => `
          <div style="background:rgba(255,255,255,0.03); border-radius:var(--radius-md); padding:10px 14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <div style="display:flex; align-items:center; gap:8px;">
                <strong style="color:#fff; font-size:13px;">${e.raw_plate || e.clean_plate || 'ไม่ระบุทะเบียน'}</strong>
                <span class="stat-pill ${e.status === 'CONFIRMED' ? 'pill-green' : (e.status === 'PENDING' ? 'pill-orange' : 'pill-red')}" style="font-size:9px;">
                  ${e.status}
                </span>
              </div>
              <div style="font-size:11px; color:var(--text-dim); margin-top:2px;">กล้อง: ${e.camera_name} | ชั้น ${e.suggested_floor || '-'}</div>
            </div>
            <div style="font-size:10px; color:var(--text-muted);">${e.created_at ? e.created_at.slice(11,16) : ''}</div>
          </div>
        `).join('');
      }
    }
  } catch (err) {
    console.error('loadSecurityDashboardData error:', err);
  }
}

function switchToFloorSlotMap(floorNum) {
  currentSlotMapFloor = floorNum;
  switchView('security-slotmap');
}

async function loadSecuritySlotMapData() {
  const container = document.getElementById('security-slotmap-grid');
  const titleEl = document.getElementById('slotmap-floor-title');
  const statEl = document.getElementById('slotmap-floor-stat');
  if (!container) return;

  try {
    const res = await API.getFloorSlotMap(currentSlotMapFloor);
    const data = res.data;
    if (!data) return;

    if (titleEl) titleEl.innerText = data.floor.floor_name;
    if (statEl) statEl.innerText = `ว่าง ${data.free_slots} / จอดแล้ว ${data.occupied_slots} / ทั้งหมด ${data.total_slots} ช่อง`;

    const slots = data.slots || [];
    container.innerHTML = slots.map(s => {
      const isOcc = s.status === 'OCCUPIED';
      const isRes = s.status === 'RESERVED';
      const isErr = s.status === 'ERROR';

      let bg = 'rgba(16, 185, 129, 0.12)';
      let border = 'rgba(16, 185, 129, 0.35)';
      let badge = '<span class="stat-pill pill-green">ว่าง</span>';

      if (isOcc) {
        bg = 'rgba(124, 58, 237, 0.18)';
        border = 'var(--accent-purple)';
        badge = '<span class="stat-pill pill-purple">มีรถจอด</span>';
      } else if (isRes) {
        bg = 'rgba(245, 158, 11, 0.15)';
        border = 'rgba(245, 158, 11, 0.4)';
        badge = '<span class="stat-pill pill-orange">สงวนสิทธิ์</span>';
      } else if (isErr) {
        bg = 'rgba(239, 68, 68, 0.15)';
        border = 'rgba(239, 68, 68, 0.4)';
        badge = '<span class="stat-pill pill-red">ขัดข้อง</span>';
      }

      return `
        <div style="background:${bg}; border:1px solid ${border}; border-radius:var(--radius-md); padding:14px; cursor:pointer; transition:var(--transition);"
             onclick="openSlotDetailModal(${s.id}, '${s.slot_number}', '${s.status}', '${s.plate_display || ''}', '${s.owner_name || ''}', '${s.owner_phone || ''}', '${s.occupied_since || ''}')">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong style="color:#fff; font-size:16px;">${s.slot_number}</strong>
            ${badge}
          </div>
          ${isOcc ? `
            <div style="font-size:13px; font-weight:700; color:#fff;">${s.plate_display || 'ตรวจพบรถ'}</div>
            <div style="font-size:11px; color:var(--text-dim); margin-top:2px;">${s.owner_name || 'บุคคลทั่วไป'}</div>
            <div style="font-size:10px; color:var(--text-muted); margin-top:4px;"><i class="fa-regular fa-clock"></i> จอดเมื่อ: ${s.occupied_since ? s.occupied_since.slice(11,16) : '-'}</div>
          ` : `
            <div style="font-size:12px; color:var(--text-muted); padding:8px 0;">พร้อมรองรับรถเข้าจอด</div>
          `}
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('loadSecuritySlotMapData error:', err);
  }
}

let activeSlotIdForModal = null;

function openSlotDetailModal(slotId, slotNumber, status, plate, owner, phone, time) {
  activeSlotIdForModal = slotId;
  const modal = document.getElementById('slot-detail-modal');
  if (!modal) return;

  document.getElementById('slot-modal-title').innerText = `รายละเอียดช่องจอด: ${slotNumber}`;
  document.getElementById('slot-modal-status-text').innerText = status;
  document.getElementById('slot-modal-plate').innerText = plate || 'ไม่มีรถจอด';
  document.getElementById('slot-modal-owner').innerText = owner ? `${owner} (${phone || '-'})` : '-';
  document.getElementById('slot-modal-time').innerText = time || '-';

  modal.style.display = 'flex';
}

function closeSlotDetailModal() {
  const modal = document.getElementById('slot-detail-modal');
  if (modal) modal.style.display = 'none';
}

async function handleSlotStatusOverride(newStatus) {
  if (!activeSlotIdForModal) return;
  try {
    await API.updateSlot(activeSlotIdForModal, newStatus);
    closeSlotDetailModal();
    loadSecuritySlotMapData();
  } catch (err) {
    alert(err.message || 'ไม่สามารถเปลี่ยนสถานะช่องจอดได้');
  }
}

// Gate Control Functions
async function loadSecurityGateData() {
  const listEl = document.getElementById('sec-gates-list');
  const logsEl = document.getElementById('sec-gate-logs-table');
  if (!listEl) return;

  try {
    const res = await API.getGates();
    const gates = res.gates || [];

    listEl.innerHTML = gates.map(g => {
      const isOpen = g.status === 'OPEN';
      return `
        <div class="glass-panel" style="padding:22px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
            <div style="display:flex; align-items:center; gap:10px;">
              <i class="fa-solid fa-torii-gate" style="color:var(--accent-purple-light); font-size:22px;"></i>
              <div>
                <strong style="color:#fff; font-size:16px;">${g.name}</strong>
                <div style="font-size:12px; color:var(--text-dim);">รหัส: ${g.gate_code} | ทิศทาง: ${g.direction === 'IN' ? 'ขาเข้า (IN)' : 'ขาออก (OUT)'}</div>
              </div>
            </div>
            <span class="stat-pill ${isOpen ? 'pill-green' : 'pill-gray'}">
              ${isOpen ? '🟢 ไม้กั้นเปิด (OPEN)' : '🔴 ไม้กั้นปิด (CLOSED)'}
            </span>
          </div>

          <div style="background:rgba(0,0,0,0.3); border-radius:var(--radius-md); padding:12px 16px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <div style="font-size:12px; color:var(--text-dim);">การเชื่อมต่อ Controller</div>
              <div style="font-size:13px; font-weight:600; color:#fff;">IP: ${g.controller_ip || '127.0.0.1'} | ปิดอัตโนมัติ: ${g.auto_close_sec} วินาที</div>
            </div>
            <span class="stat-pill pill-purple">Hardware Ready</span>
          </div>

          <div style="display:flex; gap:10px;">
            <button class="btn-primary" style="flex:1; justify-content:center;" onclick="openGateConfirmModal(${g.id}, '${g.name}', 'OPEN')">
              <i class="fa-solid fa-unlock"></i> สั่งเปิดไม้กั้น (2-Step Confirm)
            </button>
            <button class="btn-secondary" style="flex:1; justify-content:center;" onclick="openGateConfirmModal(${g.id}, '${g.name}', 'CLOSE')">
              <i class="fa-solid fa-lock"></i> สั่งปิดไม้กั้น
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Load gate logs
    const logsRes = await API.getGateLogs();
    const logs = logsRes.logs || [];
    if (logsEl) {
      logsEl.innerHTML = logs.map(l => `
        <tr>
          <td><span class="stat-pill pill-purple">${l.gate_name}</span></td>
          <td><strong>${l.action}</strong></td>
          <td>${l.user_name || 'ระบบอัตโนมัติ'}</td>
          <td>${l.plate_text || '-'}</td>
          <td><span class="stat-pill ${l.result_status === 'SUCCESS' ? 'pill-green' : 'pill-red'}">${l.result_status}</span></td>
          <td style="color:var(--text-dim); font-size:11px;">${l.created_at}</td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('loadSecurityGateData error:', err);
  }
}

let activeGateAction = 'OPEN';

function openGateConfirmModal(gateId, gateName, action) {
  selectedGateIdForConfirm = gateId;
  activeGateAction = action;
  const modal = document.getElementById('gate-confirm-modal');
  if (!modal) return;

  document.getElementById('gate-confirm-title').innerText = `ยืนยันคำสั่ง: ${action} (${gateName})`;
  document.getElementById('gate-confirm-officer').innerText = currentUser ? currentUser.name : 'เจ้าหน้าที่ รปภ.';
  document.getElementById('gate-confirm-reason').value = '';
  modal.style.display = 'flex';
}

function closeGateConfirmModal() {
  const modal = document.getElementById('gate-confirm-modal');
  if (modal) modal.style.display = 'none';
  selectedGateIdForConfirm = null;
}

async function executeConfirmedGateCommand() {
  if (!selectedGateIdForConfirm) return;
  const reason = document.getElementById('gate-confirm-reason').value.trim() || 'คำสั่งจากหน้าจอควบคุม รปภ.';
  const btn = document.getElementById('gate-confirm-exec-btn');

  try {
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> กำลังส่งคำสั่ง...';
    }

    const res = await API.controlGate(selectedGateIdForConfirm, activeGateAction, reason);
    closeGateConfirmModal();
    alert(res.message || 'ดำเนินการสำเร็จ');
    loadSecurityGateData();
  } catch (err) {
    alert(err.message || 'คำสั่งไม่สำเร็จ');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = 'ยืนยันและส่งคำสั่ง';
    }
  }
}

// AI Hybrid Verification
async function loadSecurityAiEventsData() {
  const tableEl = document.getElementById('sec-ai-events-table-body');
  if (!tableEl) return;

  try {
    const res = await API.getAiEvents(30);
    const events = res.events || [];

    if (events.length === 0) {
      tableEl.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:20px;">ไม่มีเหตุการณ์ตรวจจับ</td></tr>';
      return;
    }

    tableEl.innerHTML = events.map(e => `
      <tr>
        <td>#${e.id}</td>
        <td><strong>${e.camera_name}</strong></td>
        <td><strong style="color:var(--text-white); font-size:14px;">${e.raw_plate || e.clean_plate}</strong></td>
        <td><span class="stat-pill pill-purple">${(e.confidence_score * 100).toFixed(0)}%</span></td>
        <td>
          <span class="stat-pill ${e.status === 'CONFIRMED' ? 'pill-green' : (e.status === 'PENDING' ? 'pill-orange' : 'pill-red')}">
            ${e.status}
          </span>
        </td>
        <td style="font-size:11px; color:var(--text-dim);">${e.created_at}</td>
        <td>
          ${e.status === 'PENDING' ? `
            <button class="btn-primary" style="padding:4px 10px; font-size:11px;" onclick="handleVerifyAiEvent(${e.id}, 'CONFIRM')">ยืนยัน</button>
            <button class="btn-danger" style="padding:4px 10px; font-size:11px;" onclick="handleVerifyAiEvent(${e.id}, 'REJECT')">ปฏิเสธ</button>
          ` : `
            <span style="font-size:11px; color:var(--text-muted);">ตรวจสอบแล้ว (${e.verified_by_name || 'AI'})</span>
          `}
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('loadSecurityAiEventsData error:', err);
  }
}

async function handleVerifyAiEvent(eventId, action) {
  try {
    await API.verifyAiEvent(eventId, action);
    loadSecurityAiEventsData();
    loadSecurityDashboardData();
  } catch (err) {
    alert(err.message || 'การตรวจสอบไม่สำเร็จ');
  }
}

// CCTV Cameras Feed Wall
function loadSecurityCctvData() {
  // Update timestamp and cameras status
  ['cam1', 'cam-fl1_head', 'cam-fl1_tail', 'cam-fl2_head', 'cam-fl2_tail'].forEach(boxId => {
    const tsEl = document.getElementById(`${boxId}-timestamp`);
    if (tsEl) tsEl.innerText = new Date().toLocaleString('sv-SE');
  });
}

// Search
async function handleSecurityVehicleSearch() {
  const inputEl = document.getElementById('sec-search-input');
  const resultsEl = document.getElementById('sec-search-results-table');
  if (!inputEl || !resultsEl) return;

  const query = inputEl.value.trim();
  if (!query) return;

  try {
    resultsEl.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:16px;">กำลังค้นหา...</td></tr>';
    const res = await API.searchVehicles(query);
    const rows = res.results || [];

    if (rows.length === 0) {
      resultsEl.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:20px;">ไม่พบข้อมูลที่ตรงกับคำค้นหา</td></tr>';
      return;
    }

    resultsEl.innerHTML = rows.map(r => `
      <tr>
        <td><strong>${r.plate_display || r.plate_no}</strong></td>
        <td>${r.province}</td>
        <td>${r.owner_name} (${r.owner_code})</td>
        <td><span class="stat-pill pill-purple">${r.owner_role}</span></td>
        <td><a href="tel:${r.owner_phone}" style="color:var(--color-info); text-decoration:none;">${r.owner_phone}</a></td>
        <td>
          ${r.session_status === 'ACTIVE' 
            ? `<span class="stat-pill pill-green">กำลังจอด ชั้น ${r.current_floor || 1} (ช่อง ${r.slot_number || '-'})</span>` 
            : '<span class="stat-pill pill-gray">อยู่นอกอาคาร</span>'}
        </td>
        <td>
          <button class="btn-secondary" style="padding:4px 10px; font-size:11px;" onclick="openContactOwnerModal(${r.id}, '${r.owner_name}', '${r.plate_display}')">
            <i class="fa-solid fa-message"></i> ส่งข้อความ
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('handleSecurityVehicleSearch error:', err);
  }
}

