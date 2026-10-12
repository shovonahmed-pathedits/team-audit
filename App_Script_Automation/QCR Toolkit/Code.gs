// ============================================================
// CODE.gs
// ============================================================

var WEEKLY_SOURCE_ID  = "1k97OquO6h6IheftDBnKtGocvqqLqyEFh";
var MONTHLY_SOURCE_ID = "1QWxFeFIyVa572HDOS9M7AmH2MQ4B5j-g";

var CUSTOM_ORDER = [
  "Creative Path",      // 1
  "Pixel Path",         // 2
  "Perfect Pixel",      // 3
  "Grasigner Kitchen",  // 4
  "Khandoker Graphics", // 5
  "Graphics Picture",   // 6
  "Vectorio",           // 7
  "Cutout Edge",        // 8
  "Edgebo",             // 9
  "Healing Image",      // 10
  "Photo Fix Zone",     // 11
  "Clipping Pix",       // 12
  "Designing Studio"    // 13
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("🐽 QCR Toolkit")
    .addItem("🚀 Weekly Handoff",  "showWeeklySidebar")
    .addItem("📅 Monthly Handoff", "showMonthlySidebar")
    .addToUi();
}

function showWeeklySidebar() {
  var html = HtmlService.createTemplateFromFile("Sidebar");
  html.mode       = "weekly";
  html.sourceId   = WEEKLY_SOURCE_ID;
  html.modeLabel  = "Weekly";
  html.sourceText = "drive.google.com/drive/folders/" + WEEKLY_SOURCE_ID;
  var output = html.evaluate()
    .setTitle("Audit Toolkit — Weekly")
    .setWidth(340);
  SpreadsheetApp.getUi().showSidebar(output);
}

function showMonthlySidebar() {
  var html = HtmlService.createTemplateFromFile("Sidebar");
  html.mode       = "monthly";
  html.sourceId   = MONTHLY_SOURCE_ID;
  html.modeLabel  = "Monthly";
  html.sourceText = "drive.google.com/drive/folders/" + MONTHLY_SOURCE_ID;
  var output = html.evaluate()
    .setTitle("Audit Toolkit — Monthly")
    .setWidth(340);
  SpreadsheetApp.getUi().showSidebar(output);
}

// ── FUNCTION 1: Generate — copy files from source → destination
function generateCopyFiles(sourceId, destUrl) {
  var destId = extractFolderId(destUrl);
  if (!destId) throw new Error("Could not find a Folder ID in the destination URL.");

  var sourceFolder = DriveApp.getFolderById(sourceId);
  var destFolder   = DriveApp.getFolderById(destId);
  var files        = sourceFolder.getFiles();

  var results = [];
  var copied  = 0, skipped = 0, errors = 0, fileNum = 0;

  while (files.hasNext()) {
    var file     = files.next();
    fileNum++;
    var fileName = file.getName();
    var mimeType = file.getMimeType();

    if (mimeType === "application/vnd.google-apps.presentation") {
      try {
        var presentation = SlidesApp.openById(file.getId());
        var slideCount   = presentation.getSlides().length;
        if (slideCount > 3) {
          var newFile = file.makeCopy("Copy of " + fileName, destFolder);
          results.push({ status: "copied", num: fileNum, name: fileName, slides: slideCount, newName: newFile.getName() });
          copied++;
        } else {
          results.push({ status: "skipped_slides", num: fileNum, name: fileName, slides: slideCount, newName: "Only " + slideCount + " slide(s) — skipped" });
          skipped++;
        }
      } catch(e) {
        results.push({ status: "error", num: fileNum, name: fileName, slides: 0, newName: e.message });
        errors++;
      }
    } else {
      try {
        var newFile = file.makeCopy("Copy of " + fileName, destFolder);
        results.push({ status: "copied", num: fileNum, name: fileName, slides: 0, newName: newFile.getName() });
        copied++;
      } catch(e) {
        results.push({ status: "error", num: fileNum, name: fileName, slides: 0, newName: e.message });
        errors++;
      }
    }
  }

  return { results: results, copied: copied, skipped: skipped, errors: errors, total: fileNum };
}

// ── FUNCTION 2: Remove "Copy of " from file names
function bulkRenameAllSlidesInFolder(folderUrl) {
  var folderId = extractFolderId(folderUrl);
  if (!folderId) throw new Error("Could not find a Folder ID. Paste the full Drive folder URL.");

  var folder  = DriveApp.getFolderById(folderId);
  var files   = folder.getFiles();
  var results = [];
  var renamed = 0, skipped = 0, errors = 0;

  while (files.hasNext()) {
    var file    = files.next();
    var oldName = file.getName();
    try {
      if (oldName.startsWith("Copy of ")) {
        var newName = oldName.replace(/^Copy of /, "");
        file.setName(newName);
        results.push({ status: "renamed", old: oldName, new: newName });
        renamed++;
      } else {
        results.push({ status: "skipped", old: oldName, new: oldName });
        skipped++;
      }
    } catch(e) {
      results.push({ status: "error", old: oldName, new: e.message });
      errors++;
    }
  }
  return { results: results, renamed: renamed, skipped: skipped, errors: errors };
}

// ── FUNCTION 3: Get file URLs — shows ALL 13 slots, marks missing ones
function getFileUrls(folderUrl) {
  var folderId = extractFolderId(folderUrl);
  if (!folderId) throw new Error("Could not find a Folder ID. Paste the full Drive folder URL.");

  var folder  = DriveApp.getFolderById(folderId);
  var files   = folder.getFiles();
  var fileMap = {};

  while (files.hasNext()) {
    var file  = files.next();
    var name  = file.getName();
    var index = getStrictOrderIndex(name);
    if (index !== -1) {
      fileMap[index] = { name: name, url: file.getUrl() };
    }
  }

  var results = [];
  var found   = 0;
  var missing = 0;

  for (var i = 0; i < CUSTOM_ORDER.length; i++) {
    if (fileMap[i]) {
      results.push({ slot: i + 1, vendor: CUSTOM_ORDER[i], status: "found",   name: fileMap[i].name, url: fileMap[i].url });
      found++;
    } else {
      results.push({ slot: i + 1, vendor: CUSTOM_ORDER[i], status: "missing", name: "",              url: "" });
      missing++;
    }
  }

  return { results: results, found: found, missing: missing, total: CUSTOM_ORDER.length };
}

// ── NEW: One-click full handoff (copy + rename + URLs)
function runFullHandoff(sourceId, destUrl) {
  var copy   = generateCopyFiles(sourceId, destUrl);
  var rename = bulkRenameAllSlidesInFolder(destUrl);
  var urls   = getFileUrls(destUrl);
  return { copy: copy, rename: rename, urls: urls };
}

function getStrictOrderIndex(fileName) {
  var lower = fileName.toLowerCase();
  for (var i = 0; i < CUSTOM_ORDER.length; i++) {
    if (lower.indexOf(CUSTOM_ORDER[i].toLowerCase()) !== -1) return i;
  }
  return -1;
}

function extractFolderId(input) {
  if (!input) return null;
  input = input.trim();
  var urlMatch = input.match(/\/folders\/([a-zA-Z0-9_-]+)/);
  if (urlMatch) return urlMatch[1];
  var idMatch = input.match(/[?&]id=([a-zA-Z0-9_-]+)/);
  if (idMatch) return idMatch[1];
  if (/^[a-zA-Z0-9_-]{10,}$/.test(input)) return input;
  return null;
}