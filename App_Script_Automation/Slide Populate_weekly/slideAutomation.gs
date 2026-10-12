/**
 * Path Audit Toolkit
 * Google Slides Sorting, Distribution, and Sync Tool
 */

/**
 * THE CUSTOM ORDER PROVIDED BY THE USER.
 */
const VENDOR_ORDER = [
  "Creative Path (P1)",
  "Pixel Path (P2)",
  "Perfect Pixel (GB2)",
  "Grasigner Kitchen",
  "Khandoker Graphics",
  "Graphics Picture",
  "Vectorio",
  "Cutout Edge",
  "Edgebo",
  "Healing Image",
  "Photo Fix Zone",
  "Clipping Pix",
  "Designing Studio"
];

// Specific Folder ID provided by the user
const TARGET_FOLDER_ID = "1k97OquO6h6IheftDBnKtGocvqqLqyEFh";

function onOpen() {
  const ui = SlidesApp.getUi();
  ui.createMenu('📂 Path Audit Toolkit')
    .addItem('🔤  Sort Slides by Vendor', 'startSortDialog')
    .addSeparator()
    .addItem('📤  Push Slides to Drive', 'startPushDialog')
    .addSeparator()
    .addItem('📋  Weekly Handoff', 'showWeeklyHandoffSidebar')
    .addToUi();
}

function startSortDialog() {
  const tpl = HtmlService.createTemplateFromFile('ProgressDialog');
  tpl.mode = 'sort';
  const html = tpl.evaluate().setWidth(360).setHeight(200);
  SlidesApp.getUi().showModalDialog(html, 'Sorting Progress');
}

function startPushDialog() {
  const tpl = HtmlService.createTemplateFromFile('ProgressDialog');
  tpl.mode = 'push';
  const html = tpl.evaluate().setWidth(360).setHeight(200);
  SlidesApp.getUi().showModalDialog(html, 'Push Progress');
}

/**
 * Helper: Refreshes linked objects on the first 3 slides.
 */
function refreshPresentationLinks(pres) {
  let stats = { charts: 0, tables: 0 };
  const slides = pres.getSlides();
  const limit = Math.min(slides.length, 3);
  
  for (let i = 0; i < limit; i++) {
    const elements = slides[i].getPageElements();
    elements.forEach(element => {
      try {
        const type = element.getPageElementType();
        
        // 1. Handle Charts (Supported by Script)
        if (type === SlidesApp.PageElementType.SHEETS_CHART) {
          element.asSheetsChart().refresh();
          stats.charts++;
        }
        
        // 2. Identify Tables (Not refreshable via script, but we count them for the user)
        if (type === SlidesApp.PageElementType.TABLE) {
          // No .refresh() exists for tables, but we know they exist
          stats.tables++;
        }
      } catch (e) {
        // Safe skip
      }
    });
  }
  return stats;
}

/**
 * Server-side chunked execution logic for sending slides to vendors
 */
function getPushTasks() {
  const presentation = SlidesApp.getActivePresentation();
  const slides = presentation.getSlides();
  
  if (slides.length <= 1) {
    return [];
  }

  let folder;
  try {
    folder = DriveApp.getFolderById(TARGET_FOLDER_ID);
  } catch (e) {
    return [];
  }

  const fileMap = {};
  const driveFiles = folder.getFiles();
  while (driveFiles.hasNext()) {
    const file = driveFiles.next();
    const fileName = file.getName();
    VENDOR_ORDER.forEach(vendor => {
      if (fileName.toLowerCase().includes(vendor.toLowerCase())) {
        fileMap[vendor.toLowerCase()] = { id: file.getId(), name: fileName };
      }
    });
  }

  const vendorGroups = {};
  const slidesToPush = slides.slice(3);
  slidesToPush.forEach(slide => {
    const vendorName = findVendorNameOnSlide(slide);
    if (vendorName) {
      const vKey = vendorName.toLowerCase();
      const officialVendor = VENDOR_ORDER.find(v => v.toLowerCase() === vKey || vKey.includes(v.toLowerCase()) || v.toLowerCase().includes(vKey));
      if (officialVendor) {
        const standardKey = officialVendor.toLowerCase();
        if (!vendorGroups[standardKey]) vendorGroups[standardKey] = [];
        vendorGroups[standardKey].push(slide.getObjectId());
      }
    }
  });

  const tasks = [];
  for (const vKey in fileMap) {
    // Include ALL vendors found in Drive — even those with no slides in master.
    // If slideIds is empty, executePushTask will still clean their old slides
    // (delete after slide 3) but will push nothing new.
    tasks.push({
      vendor: vKey,
      fileId: fileMap[vKey].id,
      slideIds: vendorGroups[vKey] || []
    });
  }
  
  return tasks;
}

function executePushTask(task) {
  const targetPres = SlidesApp.openById(task.fileId);
  const existingSlides = targetPres.getSlides();
  
  if (existingSlides.length > 3) {
    for (let j = existingSlides.length - 1; j >= 3; j--) {
      existingSlides[j].remove();
    }
  }
  
  const sourcePres = SlidesApp.getActivePresentation();
  task.slideIds.forEach(id => {
    const slide = sourcePres.getSlideById(id);
    if (slide) targetPres.appendSlide(slide);
  });
  
  targetPres.saveAndClose();
  return true;
}

function finalizeTasks(mode) {
  if (mode === 'push') Utilities.sleep(500);
  return true;
}

function getSortTasks() {
  return [{ action: "sort_all" }];
}

function executeSortTask(task) {
  const presentation = SlidesApp.getActivePresentation();
  const slides = presentation.getSlides();
  if (slides.length <= 4) return true;
  const slideData = slides.slice(4).map(slide => ({ slide: slide, priority: getPriority(findVendorNameOnSlide(slide)) }));
  slideData.sort((a, b) => a.priority - b.priority);
  slideData.forEach((data, index) => data.slide.move(index + 4));
  return true;
}

function getPriority(vendorName) {
  if (!vendorName) return 999;
  const cleanName = vendorName.trim().toLowerCase();
  for (let i = 0; i < VENDOR_ORDER.length; i++) {
    const target = VENDOR_ORDER[i].toLowerCase();
    if (cleanName.includes(target) || target.includes(cleanName)) return i;
  }
  return 99;
}

function findVendorNameOnSlide(slide) {
  const elements = slide.getPageElements();
  for (const element of elements) {
    const found = searchElementForVendor(element);
    if (found) return found;
  }
  return null;
}

function searchElementForVendor(element) {
  const type = element.getPageElementType();
  if (type === SlidesApp.PageElementType.SHAPE) return extractNameFromText(element.asShape().getText().asString());
  if (type === SlidesApp.PageElementType.GROUP) {
    const children = element.asGroup().getChildren();
    for (const child of children) {
      const found = searchElementForVendor(child);
      if (found) return found;
    }
  }
  if (type === SlidesApp.PageElementType.TABLE) {
    const table = element.asTable();
    for (let r = 0; r < table.getNumRows(); r++) {
      for (let c = 0; c < table.getNumColumns(); c++) {
        try {
          const name = extractNameFromText(table.getCell(r, c).getText().asString());
          if (name) return name;
        } catch (e) {}
      }
    }
  }
  return null;
}

function extractNameFromText(text) {
  if (!text) return null;
  const regex = /Sub\.?\s*Name\s*[:\- \t]+\s*([^\n\r]+)/i;
  const match = text.match(regex);
  if (match && match[1]) {
    let name = match[1].trim();
    // Normalize aliases so they are treated as the exact same vendor
    if (name.toLowerCase() === "clippingpix") {
      name = "Clipping Pix";
    }
    return name;
  }
  return null;
}

// ============================================================
// WEEKLY HANDOFF — imported from QCR Toolkit
// ============================================================

function showWeeklyHandoffSidebar() {
  var html = HtmlService.createTemplateFromFile("Sidebar");
  html.sourceId   = TARGET_FOLDER_ID;
  html.sourceText = "drive.google.com/drive/folders/" + TARGET_FOLDER_ID;
  var output = html.evaluate()
    .setTitle("Weekly Handoff")
    .setWidth(340);
  SlidesApp.getUi().showSidebar(output);
}

function runFullHandoff(sourceId, destUrl) {
  var copy   = generateCopyFiles(sourceId, destUrl);
  var rename = bulkRenameAllSlidesInFolder(destUrl);
  var urls   = getFileUrls(destUrl);
  return { copy: copy, rename: rename, urls: urls };
}

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

  for (var i = 0; i < VENDOR_ORDER.length; i++) {
    if (fileMap[i]) {
      results.push({ slot: i + 1, vendor: VENDOR_ORDER[i], status: "found",   name: fileMap[i].name, url: fileMap[i].url });
      found++;
    } else {
      results.push({ slot: i + 1, vendor: VENDOR_ORDER[i], status: "missing", name: "",              url: "" });
      missing++;
    }
  }

  return { results: results, found: found, missing: missing, total: VENDOR_ORDER.length };
}

function getStrictOrderIndex(fileName) {
  var lower = fileName.toLowerCase();
  for (var i = 0; i < VENDOR_ORDER.length; i++) {
    if (lower.indexOf(VENDOR_ORDER[i].toLowerCase()) !== -1) return i;
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
