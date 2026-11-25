// -*- coding: utf-8 -*-
/* ==============================================================================
   PINK AI: Student / Teacher Portal Dashboard
============================================================================== */

let currentCalendarDate = new Date();

function renderMonthlyCalendar(containerId, activeDate = new Date()) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const year = activeDate.getFullYear();
  const month = activeDate.getMonth();

  const monthNames = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"];
  const dayNames = ["อา", "จ", "อ", "พ", "พฤ", "ศ", "ส"];

  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = new Date();

  let html = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <strong style="color:#fff; font-size:14px;">${monthNames[month]} ${year + 543}</strong>
      <div style="display:flex; gap:6px;">
        <button class="btn-secondary" style="padding:3px 8px; font-size:11px;" onclick="changeCalendarMonth(-1)"><i class="fa-solid fa-chevron-left"></i></button>
        <button class="btn-secondary" style="padding:3px 8px; font-size:11px;" onclick="changeCalendarMonth(1)"><i class="fa-solid fa-chevron-right"></i></button>
      </div>
    </div>
    <div style="display:grid; grid-template-columns:repeat(7, 1fr); gap:4px; text-align:center;">
  `;

  dayNames.forEach(d => {
    html += `<div style="font-size:11px; font-weight:700; color:var(--text-dim); padding:4px 0;">${d}</div>`;
  });

  for (let i = 0; i < firstDay; i++) {
    html += `<div></div>`;
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const isToday = (today.getFullYear() === year && today.getMonth() === month && today.getDate() === d);
    const bgStyle = isToday 
      ? 'background:var(--accent-purple); color:#fff; font-weight:700; box-shadow:0 0 10px var(--accent-purple-dim);' 
      : 'color:var(--text-secondary);';
    html += `
      <div style="padding:6px 0; border-radius:6px; font-size:12px; cursor:pointer; ${bgStyle} transition:var(--transition);"
           onmouseover="this.style.background='rgba(124,58,237,0.3)'" 
           onmouseout="this.style.background='${isToday ? 'var(--accent-purple)' : 'transparent'}'"
           onclick="onCalendarDateClick(${d}, ${month + 1}, ${year})">
        ${d}
      </div>
    `;
  }

  html += `</div>`;
  container.innerHTML = html;
}

function changeCalendarMonth(delta) {
  currentCalendarDate.setMonth(currentCalendarDate.getMonth() + delta);
  renderMonthlyCalendar('student-calendar-container', currentCalendarDate);
  renderMonthlyCalendar('security-calendar-container', currentCalendarDate);
}

function onCalendarDateClick(d, m, y) {
  console.log(`Selected date: ${d}/${m}/${y}`);
}

async function loadUserPortalData() {
  renderMonthlyCalendar('student-calendar-container', currentCalendarDate);

  try {
    const res = await API.getMyParking();
    const data = res.data;

    // 1. My Parking Widget
    const plateEl = document.getElementById('my-parking-plate');
    const vehInfoEl = document.getElementById('my-parking-veh-info');
    const statusPill = document.getElementById('my-parking-status-pill');
    const locationEl = document.getElementById('my-parking-location');
    const entryTimeEl = document.getElementById('my-parking-entry-time');

    if (data.primary_vehicle) {
      if (plateEl) plateEl.innerText = data.primary_vehicle.plate_display || data.primary_vehicle.plate_no;
      if (vehInfoEl) vehInfoEl.innerText = `${data.primary_vehicle.brand || ''} ${data.primary_vehicle.model || ''} (${data.primary_vehicle.color || ''})`.trim() || 'รถยนต์ลงทะเบียน';
    }

    if (data.is_parked) {
      if (statusPill) {
        statusPill.className = 'stat-pill pill-green';
        statusPill.innerHTML = '<i class="fa-solid fa-circle-dot"></i> กำลังจอด (Parked)';
      }
      if (locationEl) {
        locationEl.innerHTML = `ชั้น ${data.current_floor || 1} <span style="font-size:14px; color:var(--text-dim); font-weight:normal;">/ ช่อง ${data.slot_number || 'ตรวจพบในชั้น'}</span>`;
      }
      if (entryTimeEl) entryTimeEl.innerText = data.entry_time || 'เมื่อสักครู่';
    } else {
      if (statusPill) {
        statusPill.className = 'stat-pill pill-gray';
        statusPill.innerHTML = '<i class="fa-solid fa-circle-xmark"></i> อยู่นอกอาคาร';
      }
      if (locationEl) locationEl.innerText = 'อยู่นอกอาคาร / ยังไม่ได้ขับเข้า';
      if (entryTimeEl) entryTimeEl.innerText = '-';
    }

    // 2. Notifications & Messages
    loadUserNotificationsList();
  } catch (err) {
    console.error('loadUserPortalData error:', err);
  }
}

async function loadUserNotificationsList() {
  const container = document.getElementById('user-notifications-list');
  if (!container) return;

  try {
    const res = await API.getNotifications();
    const notifs = res.notifications || [];

    if (notifs.length === 0) {
      container.innerHTML = '<div style="color:var(--text-dim); font-size:13px; text-align:center; padding:16px;">ไม่มีข้อความแจ้งเตือนใหม่</div>';
      return;
    }

    container.innerHTML = notifs.map(n => `
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-glass); border-radius:var(--radius-md); padding:12px 16px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
        <div>
          <div style="font-size:13px; font-weight:700; color:#fff; display:flex; align-items:center; gap:8px;">
            <i class="fa-solid fa-bell" style="color:var(--accent-purple-light); font-size:11px;"></i>
            <span>${n.title}</span>
            ${n.is_read ? '' : '<span class="stat-pill pill-purple" style="font-size:9px; padding:1px 5px;">ใหม่</span>'}
          </div>
          <div style="font-size:12px; color:var(--text-secondary); margin-top:3px;">${n.message}</div>
          <div style="font-size:10px; color:var(--text-muted); margin-top:4px;">${n.created_at}</div>
        </div>
        <div>
          ${n.is_read ? '' : `<button class="btn-secondary" style="padding:4px 10px; font-size:11px;" onclick="markNotificationDone(${n.id})">อ่านแล้ว</button>`}
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('loadUserNotificationsList error:', err);
  }
}

async function markNotificationDone(id) {
  await API.markNotificationRead(id);
  loadUserNotificationsList();
}

async function loadUserVehiclesData() {
  const container = document.getElementById('user-vehicles-grid');
  if (!container) return;

  try {
    const res = await API.getMyParking();
    const vehs = res.data.vehicles || [];

    if (vehs.length === 0) {
      container.innerHTML = '<div style="color:var(--text-dim); padding:20px;">ไม่พบรายการยานพาหนะที่ลงทะเบียน</div>';
      return;
    }

    container.innerHTML = vehs.map(v => `
      <div class="glass-panel" style="padding:20px; border-color: ${v.is_primary ? 'var(--accent-purple)' : 'var(--border-glass)'};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
          <div>
            <div style="font-size:22px; font-weight:800; color:#fff; letter-spacing:0.5px;">${v.plate_display || v.plate_no}</div>
            <div style="font-size:12px; color:var(--accent-purple-light); font-weight:600;">${v.province}</div>
          </div>
          <span class="stat-pill ${v.is_active ? 'pill-green' : 'pill-red'}">
            ${v.is_active ? 'สิทธิ์ปกติ (Active)' : 'ระงับสิทธิ์'}
          </span>
        </div>
        <div style="background:rgba(0,0,0,0.3); border-radius:var(--radius-md); padding:10px 14px; margin-bottom:12px;">
          <div style="font-size:11px; color:var(--text-dim);">ข้อมูลรถยนต์</div>
          <div style="font-size:13px; font-weight:600; color:#fff;">${v.brand || ''} ${v.model || ''} (${v.color || 'ไม่ระบุสี'})</div>
          <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">RFID: ${v.rfid_tag || '-'} | ประเภท: ${v.vehicle_type}</div>
        </div>
        ${v.is_primary ? '<span class="stat-pill pill-purple" style="font-size:10px;"><i class="fa-solid fa-star"></i> คันหลักที่ใช้งาน</span>' : ''}
      </div>
    `).join('');
  } catch (err) {
    console.error('loadUserVehiclesData error:', err);
  }
}

async function loadUserMessagesData() {
  const listEl = document.getElementById('user-conv-list');
  const chatBox = document.getElementById('user-chat-messages');
  if (!listEl) return;

  try {
    const res = await API.getConversations();
    const convs = res.conversations || [];

    if (convs.length === 0) {
      listEl.innerHTML = '<div style="color:var(--text-dim); padding:16px;">ยังไม่มีประวัติการสนทนา</div>';
      return;
    }

    listEl.innerHTML = convs.map(c => `
      <div style="padding:12px 14px; border-radius:var(--radius-md); background:rgba(255,255,255,0.03); margin-bottom:8px; cursor:pointer;"
           onclick="openUserConversation(${c.id}, '${c.subject}')">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong style="color:#fff; font-size:13px;">${c.subject}</strong>
          <span style="font-size:10px; color:var(--text-muted);">${c.last_message_time ? c.last_message_time.slice(11,16) : ''}</span>
        </div>
        <div style="font-size:12px; color:var(--text-secondary); margin-top:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          ${c.last_message || 'เปิดบทสนทนา'}
        </div>
      </div>
    `).join('');

    if (convs.length > 0) {
      openUserConversation(convs[0].id, convs[0].subject);
    }
  } catch (err) {
    console.error('loadUserMessagesData error:', err);
  }
}

let activeUserConvId = null;

async function openUserConversation(convId, subject) {
  activeUserConvId = convId;
  const titleEl = document.getElementById('user-chat-title');
  const boxEl = document.getElementById('user-chat-messages');
  if (titleEl) titleEl.innerText = subject;
  if (!boxEl) return;

  try {
    const res = await API.getConversationMessages(convId);
    const msgs = res.messages || [];

    boxEl.innerHTML = msgs.map(m => {
      const isMe = m.sender_role !== 'SECURITY';
      return `
        <div style="display:flex; justify-content:${isMe ? 'flex-end' : 'flex-start'}; margin-bottom:10px;">
          <div style="max-width:70%; padding:10px 14px; border-radius:${isMe ? '16px 16px 2px 16px' : '16px 16px 16px 2px'}; background:${isMe ? 'var(--gradient-purple)' : 'rgba(255,255,255,0.08)'}; color:#fff; font-size:13px;">
            <div style="font-size:10px; color:${isMe ? 'rgba(255,255,255,0.7)' : 'var(--text-dim)'}; margin-bottom:2px;">
              ${m.sender_name} (${m.sender_role})
            </div>
            <div>${m.content}</div>
            <div style="font-size:9px; color:${isMe ? 'rgba(255,255,255,0.6)' : 'var(--text-muted)'}; text-align:right; margin-top:4px;">${m.created_at ? m.created_at.slice(11,16) : ''}</div>
          </div>
        </div>
      `;
    }).join('');

    boxEl.scrollTop = boxEl.scrollHeight;
  } catch (err) {
    console.error('openUserConversation error:', err);
  }
}

async function handleSendUserMessage() {
  if (!activeUserConvId) return;
  const inputEl = document.getElementById('user-chat-input');
  if (!inputEl) return;
  const text = inputEl.value.trim();
  if (!text) return;

  try {
    await API.sendMessage(activeUserConvId, text);
    inputEl.value = '';
    openUserConversation(activeUserConvId, 'สนทนา');
  } catch (err) {
    console.error('handleSendUserMessage error:', err);
  }
}

