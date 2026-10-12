# Conversation Summary - Audit Slide Automation

## 1. Image Analysis
- **Slide**: "Quality Audit Report" cover page
- **Vendor**: "Creative Path (P1)"
- **Target Text**: "Week • 01" and "01 - 07 June, 2026"

## 2. Goal
Pull week and date data from Google Sheet cells M6 (week) and M7 (date) in tab "Audit Slide Automate" and update the Google Slide.

## 3. Google Apps Script Code

```javascript
function updateAuditSlideWeek() {
  const ssId = '1syF5pdiWL41pwTFOXoWJONivD3WiNs-9fJHJFIzkq8g';
  const sheetName = 'Audit Slide Automate';
  
  const ss = SpreadsheetApp.openById(ssId);
  const sheet = ss.getSheetByName(sheetName);
  
  const weekValue = sheet.getRange('M6').getValue();
  const dateValue = sheet.getRange('M7').getValue();
  
  const slides = SlidesApp.getActivePresentation();
  const slide = slides.getSlides()[0];
  
  const elements = slide.getPageElements();
  
  elements.forEach(element => {
    if (element.getPageElementType() === SlidesApp.PageElementType.SHAPE) {
      const shape = element.asShape();
      if (shape.getText) {
        const text = shape.getText().asString();
        
        if (text.includes('Week')) {
          shape.getText().setText(weekValue);
        }
        
        if (text.includes('June') || text.includes('2026') || text.match(/\d{2}\s*-\s*\d{2}/)) {
          shape.getText().setText(dateValue);
        }
      }
    }
  });
  
  Logger.log('Week: ' + weekValue);
  Logger.log('Date: ' + dateValue);
}
```

## 4. Setup Steps
1. Open Google Sheet
2. Go to **Extensions > Apps Script**
3. Paste code
4. Save and run
5. Authorize permissions

## 5. Notes
- For separate Slides file: Replace `SlidesApp.getActivePresentation()` with `SlidesApp.openById('SLIDES_ID')`
- Can add time-based trigger for automation
