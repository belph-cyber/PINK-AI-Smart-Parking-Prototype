/**
 * ============================================================================
 * PINK AI SMART PARKING - Google Apps Script Integration (Code.gs)
 * ============================================================================
 * Spreadsheet URL : https://docs.google.com/spreadsheets/d/REPLACE_WITH_YOUR_SPREADSHEET_ID/edit?usp=sharing
 * Spreadsheet ID  : REPLACE_WITH_YOUR_SPREADSHEET_ID
 * Timezone        : Asia/Bangkok (UTC+7)
 *
 * หน้าที่หลักของสคริปต์นี้:
 * 1. ตรวจสอบโครงสร้างไฟล์ Google Sheets ก่อนเชื่อมต่อ (ไม่ลบข้อมูลเดิมโดยไม่ได้รับอนุญาต)
 * 2. สร้างและจัดระเบียบแผ่นงาน (Tabs) มาตรฐานทั้ง 6 Sheets อัตโนมัติหากยังไม่มี:
 *    - Sheet 1: Users                 (รายชื่อผู้ใช้งาน - ห้ามเก็บ Password/Hash เด็ดขาด)
 *    - Sheet 2: Teacher Schedule      (ตารางสอนอาจารย์)
 *    - Sheet 3: Student Schedule      (ตารางเรียนนักศึกษา)
 *    - Sheet 4: Parking History       (ประวัติการจอดรถ)
 *    - Sheet 5: Login History         (ประวัติการเข้าใช้งาน Login / Logout)
 *    - Sheet 6: Personal Information  (ข้อมูลส่วนบุคคล)
 * 3. รับคำสั่งซิงก์จาก Backend (FastAPI SQLite Source of Truth) ผ่าน Web App (doGet / doPost)
 * 4. ป้องกันข้อมูลซ้ำ (Upsert ด้วยรหัสอ้างอิงเฉพาะของแต่ละรายการ) และใช้ LockService ป้องกันการเขียนชนกัน
 * ============================================================================
 */

const SPREADSHEET_ID = 'REPLACE_WITH_YOUR_SPREADSHEET_ID';
const TIMEZONE = 'Asia/Bangkok';

// หากตั้งค่า GOOGLE_SHEETS_SYNC_SECRET ในไฟล์ .env ของ Backend ให้ใส่ค่าเดียวกันที่นี่ (เว้นว่างได้หากไม่ใช้)
const SYNC_SECRET = '';

// โครงสร้างมาตรฐานทั้ง 6 Sheets และวิธีสร้าง Unique Key เพื่อป้องกันข้อมูลซ้ำ
const SHEET_CONFIGS = {
  'Users': {
    headers: ['User ID', 'รหัสประจำตัว', 'ชื่อ-นามสกุล', 'Role', 'สถานะบัญชี', 'วันที่สร้างบัญชี'],
    keyIndexes: [0], // อ้างอิงจาก User ID (ไม่ซ้ำ)
    colWidths: [90, 130, 200, 140, 160, 170]
  },
  'Teacher Schedule': {
    headers: ['รหัสอาจารย์', 'ชื่ออาจารย์', 'วันสอน', 'เวลาเริ่มต้น', 'เวลาสิ้นสุด', 'รายวิชา', 'ห้องเรียน'],
    keyIndexes: [0, 2, 3, 5], // รหัสอาจารย์ + วันสอน + เวลาเริ่ม + รายวิชา
    colWidths: [120, 190, 110, 100, 100, 240, 180]
  },
  'Student Schedule': {
    headers: ['รหัสนักศึกษา', 'ชื่อนักศึกษา', 'วันเรียน', 'เวลาเริ่มต้น', 'เวลาสิ้นสุด', 'รายวิชา', 'ห้องเรียน'],
    keyIndexes: [0, 2, 3, 5], // รหัสนักศึกษา + วันเรียน + เวลาเริ่ม + รายวิชา
    colWidths: [120, 190, 110, 100, 100, 240, 180]
  },
  'Parking History': {
    headers: ['Event ID', 'รหัสผู้ใช้งาน', 'ทะเบียนรถ', 'วันที่เข้า', 'เวลาเข้า', 'วันที่ออก', 'เวลาออก', 'ชั้นจอด', 'รหัสช่องจอด', 'สถานะ', 'แหล่งที่มาของข้อมูล'],
    keyIndexes: [0], // อ้างอิงจาก Event ID
    colWidths: [95, 120, 150, 110, 95, 110, 95, 85, 110, 120, 160]
  },
  'Login History': {
    headers: ['Log ID', 'รหัสผู้ใช้งาน', 'ชื่อผู้ใช้งาน', 'Role', 'วันและเวลา Login', 'วันและเวลา Logout', 'สถานะการเข้าสู่ระบบ', 'รายละเอียดเหตุการณ์ที่เกี่ยวข้อง'],
    keyIndexes: [0], // อ้างอิงจาก Log ID
    colWidths: [85, 125, 190, 120, 165, 165, 140, 240]
  },
  'Personal Information': {
    headers: ['รหัสประจำตัว', 'ชื่อ-นามสกุล', 'เพศ', 'อายุ', 'วันเกิด', 'เบอร์ติดต่อ'],
    keyIndexes: [0], // อ้างอิงจาก รหัสประจำตัว
    colWidths: [130, 200, 95, 85, 140, 140]
  }
};

// คำต้องห้ามด้านความปลอดภัย: ห้ามบันทึก Password หรือ Password Hash ลง Google Sheets เด็ดขาด
const FORBIDDEN_HEADER_KEYWORDS = ['password', 'password_hash', 'pwd_hash', 'secret', 'รหัสผ่าน'];

/**
 * เพิ่มเมนู "🌸 PINK AI Parking" บนแถบเมนูของ Google Sheets เมื่อเปิดไฟล์
 */
function onOpen() {
  try {
    SpreadsheetApp.getUi()
      .createMenu('🌸 PINK AI Parking')
      .addItem('1. ตรวจสอบและสร้างโครงสร้าง 6 Sheets มาตรฐาน', 'uiSetupSheets')
      .addItem('2. ล้างแถวที่ซ้ำกัน (Deduplicate ปลอดภัย)', 'uiDeduplicateAll')
      .addItem('3. ดูสรุปจำนวนข้อมูลในแต่ละ Sheet', 'uiShowStatus')
      .addToUi();
  } catch (err) {
    // กรณีรันผ่าน Web App Trigger จะไม่มี UI Context
  }
}

function uiSetupSheets() {
  const result = setupSheetsStructure();
  SpreadsheetApp.getUi().alert(
    '🌸 PINK AI Smart Parking\n\n' +
    'ตรวจสอบและจัดเตรียมโครงสร้างครบทั้ง 6 Sheets เรียบร้อยแล้ว!\n' +
    'สร้างใหม่: ' + (result.created.length ? result.created.join(', ') : 'ไม่มี (มีครบแล้ว)') + '\n' +
    'คงข้อมูลเดิมไว้ปลอดภัย: ' + result.existing.join(', ')
  );
}

function uiDeduplicateAll() {
  const ss = getTargetSpreadsheet_();
  let removedTotal = 0;
  Object.keys(SHEET_CONFIGS).forEach(function(sheetName) {
    const sh = ss.getSheetByName(sheetName);
    if (sh) {
      removedTotal += deduplicateSheet_(sh, SHEET_CONFIGS[sheetName].keyIndexes);
    }
  });
  SpreadsheetApp.getUi().alert('ตรวจสอบข้อมูลซ้ำเสร็จสิ้น ลบรายการซ้ำออกทั้งหมด ' + removedTotal + ' แถว');
}

function uiShowStatus() {
  const info = inspectSpreadsheetStructure_();
  const lines = Object.keys(info.sheets).map(function(name) {
    return '• ' + name + ': ' + info.sheets[name].rowCount + ' รายการ';
  });
  SpreadsheetApp.getUi().alert('สถานะข้อมูลปัจจุบัน (' + info.checkedAt + ')\n\n' + lines.join('\n'));
}

/**
 * ============================================================================
 * Web App HTTP GET Endpoint (doGet)
 * รองรับ:
 *   ?action=ping     -> ทดสอบการเชื่อมต่อ Heartbeat
 *   ?action=inspect  -> ตรวจสอบโครงสร้าง Sheet และ Column ก่อนเริ่มซิงก์
 *   ?action=pull&sheet=Users -> ดึงข้อมูลจาก Sheet กลับไปตรวจสอบฝั่งระบบหลัก
 * ============================================================================
 */
function doGet(e) {
  try {
    const params = (e && e.parameter) ? e.parameter : {};
    if (SYNC_SECRET && params.secret !== SYNC_SECRET) {
      return jsonResponse_({ success: false, status: 'UNAUTHORIZED', error: 'Invalid sync secret' });
    }

    const action = (params.action || 'ping').toLowerCase();

    if (action === 'ping') {
      const ss = getTargetSpreadsheet_();
      return jsonResponse_({
        success: true,
        status: 'ONLINE',
        service: 'PINK AI Google Apps Script Gateway',
        spreadsheet_id: ss.getId(),
        spreadsheet_name: ss.getName(),
        timezone: TIMEZONE,
        checked_at: nowBangkok_()
      });
    }

    if (action === 'inspect') {
      return jsonResponse_(inspectSpreadsheetStructure_());
    }

    if (action === 'pull') {
      const sheetName = params.sheet || 'Users';
      return jsonResponse_(pullSheetRecords_(sheetName));
    }

    return jsonResponse_({
      success: false,
      status: 'INVALID_ACTION',
      message: 'Supported GET actions: ping, inspect, pull'
    });
  } catch (err) {
    return jsonResponse_({
      success: false,
      status: 'FAILED',
      error: String(err)
    });
  }
}

/**
 * ============================================================================
 * Web App HTTP POST Endpoint (doPost)
 * รองรับ JSON Payload จาก Backend FastAPI:
 *   - action: "setup"       -> สร้าง Sheet/Header ที่ยังขาดโดยไม่ลบของเดิม
 *   - action: "sync_all"    -> ซิงก์ข้อมูลครบทั้ง 6 Sheets แบบ Upsert ป้องกันซ้ำ
 *   - action: "upsert_row"  -> ซิงก์เฉพาะรายการเดียวแบบ Real-time
 * ============================================================================
 */
function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(25000); // ป้องกันการแก้ไขข้อมูลพร้อมกัน (Concurrency Lock)
  } catch (lockErr) {
    return jsonResponse_({
      success: false,
      status: 'PENDING',
      error: 'Spreadsheet is busy with another sync operation. Please retry.'
    });
  }

  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonResponse_({ success: false, status: 'FAILED', error: 'Empty POST payload' });
    }

    const payload = JSON.parse(e.postData.contents);

    if (SYNC_SECRET && payload.secret !== SYNC_SECRET) {
      return jsonResponse_({ success: false, status: 'UNAUTHORIZED', error: 'Invalid sync secret' });
    }

    const action = (payload.action || 'sync_all').toLowerCase();

    // 1. เตรียมโครงสร้าง 6 Sheets อย่างปลอดภัย
    if (action === 'setup') {
      const setupInfo = setupSheetsStructure();
      return jsonResponse_({
        success: true,
        status: 'SUCCESS',
        action: 'setup',
        synced_at: nowBangkok_(),
        details: setupInfo
      });
    }

    // 2. ซิงก์ทั้ง 6 Sheets จาก Database (Source of Truth)
    if (action === 'sync_all') {
      const setupInfo = setupSheetsStructure();
      const sheetsPayload = payload.sheets || {};
      const summaryCounts = {};

      Object.keys(SHEET_CONFIGS).forEach(function(sheetName) {
        const incoming = sheetsPayload[sheetName];
        if (!incoming) return;

        // ตรวจสอบความปลอดภัย: ห้ามมีคอลัมน์ Password เด็ดขาด
        validateNoPasswordHeaders_(incoming.headers || []);

        const rows = Array.isArray(incoming.data) ? incoming.data : [];
        const stats = upsertSheetData_(sheetName, rows);
        summaryCounts[sheetName] = stats;
      });

      return jsonResponse_({
        success: true,
        status: 'SUCCESS',
        action: 'sync_all',
        spreadsheet_id: SPREADSHEET_ID,
        synced_at: nowBangkok_(),
        setup: setupInfo,
        sheet_stats: summaryCounts
      });
    }

    // 3. อัปเดตหรือเพิ่มเฉพาะแถวเดียว (เช่น ตอน Login/Logout หรือรถเข้า-ออก)
    if (action === 'upsert_row') {
      const sheetName = payload.sheet_name;
      const rowData = payload.row;
      if (!SHEET_CONFIGS[sheetName] || !Array.isArray(rowData)) {
        return jsonResponse_({
          success: false,
          status: 'FAILED',
          error: 'Invalid sheet_name or row array'
        });
      }
      setupSheetsStructure();
      const stats = upsertSheetData_(sheetName, [rowData]);
      return jsonResponse_({
        success: true,
        status: 'SUCCESS',
        action: 'upsert_row',
        sheet_name: sheetName,
        synced_at: nowBangkok_(),
        stats: stats
      });
    }

    return jsonResponse_({
      success: false,
      status: 'FAILED',
      error: 'Unsupported POST action: ' + action
    });

  } catch (err) {
    return jsonResponse_({
      success: false,
      status: 'FAILED',
      error: String(err),
      failed_at: nowBangkok_()
    });
  } finally {
    lock.releaseLock();
  }
}

/**
 * ============================================================================
 * ฟังก์ชันหลักสำหรับสร้างและตรวจสอบโครงสร้างทั้ง 6 Sheets (ไม่ลบข้อมูลเดิม)
 * ============================================================================
 */
function setupSheetsStructure() {
  const ss = getTargetSpreadsheet_();
  const created = [];
  const existing = [];
  const headerUpdated = [];

  Object.keys(SHEET_CONFIGS).forEach(function(sheetName) {
    const cfg = SHEET_CONFIGS[sheetName];
    let sheet = ss.getSheetByName(sheetName);

    if (!sheet) {
      sheet = ss.insertSheet(sheetName);
      created.push(sheetName);
    } else {
      existing.push(sheetName);
    }

    // ตรวจสอบแถวที่ 1 ว่ามี Header หรือยัง (ห้ามทับข้อมูลถ้าแถวที่ 1 มีข้อมูลอื่นที่ไม่ใช่แผ่นว่าง)
    const lastRow = sheet.getLastRow();
    const lastCol = sheet.getLastColumn();

    if (lastRow === 0 || lastCol === 0) {
      applyStandardHeader_(sheet, cfg.headers, cfg.colWidths);
      headerUpdated.push(sheetName);
    } else {
      const firstRow = sheet.getRange(1, 1, 1, Math.max(lastCol, cfg.headers.length)).getValues()[0];
      const isBlankHeader = firstRow.every(function(cell) { return String(cell).trim() === ''; });
      if (isBlankHeader) {
        applyStandardHeader_(sheet, cfg.headers, cfg.colWidths);
        headerUpdated.push(sheetName);
      }
    }
  });

  return {
    spreadsheet_id: ss.getId(),
    created: created,
    existing: existing,
    header_initialized: headerUpdated,
    checked_at: nowBangkok_()
  };
}

/**
 * Upsert ข้อมูลลง Sheet โดยใช้รหัสอ้างอิงเฉพาะ (Unique Reference Key)
 * - หากมีรหัสอ้างอิงอยู่แล้ว -> อัปเดตแถวนั้นให้เป็นข้อมูลล่าสุด
 * - หากยังไม่มีรหัสอ้างอิง -> ต่อท้ายแถวใหม่ (Append)
 * - ไม่ลบแถวเดิมที่มีอยู่ใน Google Sheet โดยพลการ
 */
function upsertSheetData_(sheetName, incomingRows) {
  const ss = getTargetSpreadsheet_();
  const cfg = SHEET_CONFIGS[sheetName];
  const sheet = ss.getSheetByName(sheetName);
  const colCount = cfg.headers.length;

  const lastRow = sheet.getLastRow();
  let existingData = [];
  if (lastRow >= 2) {
    existingData = sheet.getRange(2, 1, lastRow - 1, colCount).getValues();
  }

  // สร้าง Map ของ Key -> Row Index ใน existingData
  const keyToIndex = {};
  for (let i = 0; i < existingData.length; i++) {
    const key = buildCompositeKey_(existingData[i], cfg.keyIndexes);
    if (key) {
      keyToIndex[key] = i;
    }
  }

  let inserted = 0;
  let updated = 0;
  const rowsToAppend = [];

  incomingRows.forEach(function(rawRow) {
    // ปรับความยาวแถวให้ตรงกับจำนวนคอลัมน์มาตรฐาน และล้างค่า undefined/null
    const normalizedRow = [];
    for (let c = 0; c < colCount; c++) {
      let val = (c < rawRow.length && rawRow[c] !== null && rawRow[c] !== undefined) ? rawRow[c] : '';
      // ป้องกันการหลุดรอดของ Password Hash รูปแบบ pbkdf2 / bcrypt
      if (typeof val === 'string' && (val.indexOf('pbkdf2:') === 0 || val.indexOf('$2b$') === 0)) {
        val = '[REDACTED]';
      }
      normalizedRow.push(val);
    }

    const key = buildCompositeKey_(normalizedRow, cfg.keyIndexes);
    if (!key) return;

    if (Object.prototype.hasOwnProperty.call(keyToIndex, key)) {
      const idx = keyToIndex[key];
      existingData[idx] = normalizedRow;
      updated++;
    } else {
      keyToIndex[key] = existingData.length + rowsToAppend.length;
      rowsToAppend.push(normalizedRow);
      inserted++;
    }
  });

  // เขียนข้อมูลที่อัปเดตกลับลงช่วงเดิม
  if (existingData.length > 0 && updated > 0) {
    sheet.getRange(2, 1, existingData.length, colCount).setValues(existingData);
  }

  // ต่อท้ายเฉพาะรายการใหม่
  if (rowsToAppend.length > 0) {
    const startRow = existingData.length + 2;
    sheet.getRange(startRow, 1, rowsToAppend.length, colCount).setValues(rowsToAppend);
  }

  return {
    inserted: inserted,
    updated: updated,
    total_rows: existingData.length + rowsToAppend.length
  };
}

/**
 * ตรวจสอบโครงสร้างปัจจุบันของ Spreadsheet ทั้งหมดก่อนเชื่อมต่อ
 */
function inspectSpreadsheetStructure_() {
  const ss = getTargetSpreadsheet_();
  const allSheets = ss.getSheets();
  const report = {};

  allSheets.forEach(function(sh) {
    const name = sh.getName();
    const lastRow = sh.getLastRow();
    const lastCol = sh.getLastColumn();
    const headers = (lastRow >= 1 && lastCol >= 1)
      ? sh.getRange(1, 1, 1, lastCol).getValues()[0]
      : [];

    report[name] = {
      exists: true,
      is_standard_sheet: Boolean(SHEET_CONFIGS[name]),
      rowCount: Math.max(0, lastRow - 1),
      headers: headers
    };
  });

  const missingStandardSheets = Object.keys(SHEET_CONFIGS).filter(function(reqName) {
    return !report[reqName];
  });

  return {
    success: true,
    status: 'ONLINE',
    spreadsheet_id: ss.getId(),
    spreadsheet_name: ss.getName(),
    checkedAt: nowBangkok_(),
    missing_standard_sheets: missingStandardSheets,
    sheets: report
  };
}

/**
 * ดึงข้อมูลจาก Sheet ที่ระบุกลับเป็น JSON (สำหรับการตรวจสอบย้อนกลับ)
 */
function pullSheetRecords_(sheetName) {
  const ss = getTargetSpreadsheet_();
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    return { success: false, status: 'NOT_FOUND', error: 'Sheet not found: ' + sheetName };
  }

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 1 || lastCol < 1) {
    return { success: true, sheet: sheetName, headers: [], rows: [] };
  }

  const values = sheet.getRange(1, 1, lastRow, lastCol).getDisplayValues();
  return {
    success: true,
    status: 'ONLINE',
    sheet: sheetName,
    headers: values[0],
    rows: values.slice(1),
    pulled_at: nowBangkok_()
  };
}

/**
 * ลบแถวที่มีรหัสอ้างอิงซ้ำกันภายใน Sheet (เก็บแถวล่าสุดไว้)
 */
function deduplicateSheet_(sheet, keyIndexes) {
  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow <= 2 || lastCol < 1) return 0;

  const data = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();
  const seen = {};
  const uniqueReversed = [];

  for (let i = data.length - 1; i >= 0; i--) {
    const key = buildCompositeKey_(data[i], keyIndexes);
    if (!key || !seen[key]) {
      if (key) seen[key] = true;
      uniqueReversed.push(data[i]);
    }
  }

  uniqueReversed.reverse();
  const removed = data.length - uniqueReversed.length;
  if (removed > 0) {
    sheet.getRange(2, 1, lastRow - 1, lastCol).clearContent();
    if (uniqueReversed.length > 0) {
      sheet.getRange(2, 1, uniqueReversed.length, lastCol).setValues(uniqueReversed);
    }
  }
  return removed;
}

/**
 * Helper Functions
 */
function getTargetSpreadsheet_() {
  try {
    return SpreadsheetApp.openById(SPREADSHEET_ID);
  } catch (e) {
    return SpreadsheetApp.getActiveSpreadsheet();
  }
}

function applyStandardHeader_(sheet, headers, colWidths) {
  const range = sheet.getRange(1, 1, 1, headers.length);
  range.setValues([headers]);
  range.setBackground('#5B21B6');
  range.setFontColor('#FFFFFF');
  range.setFontWeight('bold');
  range.setHorizontalAlignment('center');
  sheet.setFrozenRows(1);

  if (Array.isArray(colWidths)) {
    colWidths.forEach(function(w, idx) {
      sheet.setColumnWidth(idx + 1, w);
    });
  }
}

function buildCompositeKey_(row, keyIndexes) {
  const parts = keyIndexes.map(function(idx) {
    return String(row[idx] !== undefined && row[idx] !== null ? row[idx] : '').trim();
  });
  if (parts.every(function(p) { return p === ''; })) return '';
  return parts.join('||');
}

function validateNoPasswordHeaders_(headers) {
  headers.forEach(function(h) {
    const lower = String(h).toLowerCase().trim();
    FORBIDDEN_HEADER_KEYWORDS.forEach(function(forbidden) {
      if (lower.indexOf(forbidden) !== -1) {
        throw new Error('Security Policy Violation: Password/Hash columns are strictly prohibited in Google Sheets.');
      }
    });
  });
}

function nowBangkok_() {
  return Utilities.formatDate(new Date(), TIMEZONE, 'yyyy-MM-dd HH:mm:ss');
}

function jsonResponse_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

