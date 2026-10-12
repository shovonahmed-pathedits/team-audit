function onOpen() {
  SlidesApp.getUi()
    .createMenu('Update Slide')
    .addItem('Update Slide', 'updateAuditSlideWeek')
    .addToUi();
}

function updateAuditSlideWeek() {
  const ssId = '1syF5pdiWL41pwTFOXoWJONivD3WiNs-9fJHJFIzkq8g';
  const sheetName = 'Audit Slide Automate';
  
  const ss = SpreadsheetApp.openById(ssId);
  const sheet = ss.getSheetByName(sheetName);
  
  const weekValue = sheet.getRange('M6').getDisplayValue();
  const dateValue = sheet.getRange('M7').getDisplayValue();
  
  const weekFormatted = weekValue.replace(/\u2022/g, '-').replace(/\s+/g, ' ').trim();
  
  const monthNames = ['January','February','March','April','May','June',
    'July','August','September','October','November','December'];
  
  const presentation = SlidesApp.getActivePresentation();
  
  const currentTitle = presentation.getName();
  const vendorName = currentTitle.split(', QCR,')[0].trim();
  const newTitle = vendorName + ', QCR, ' + weekFormatted + ' ( ' + dateValue + ' )';
  presentation.setName(newTitle);
  
  const slide = presentation.getSlides()[0];
  const elements = slide.getPageElements();
  
  elements.forEach(element => {
    if (element.getPageElementType() === SlidesApp.PageElementType.SHAPE) {
      const shape = element.asShape();
      if (shape.getText) {
        const text = shape.getText().asString();

        if (text.includes('Week')) {
          const lines = text.split('\n');
          
          lines.forEach((line, i) => {
            if (line.includes('Week')) {
              lines[i] = weekFormatted;
            }
            const hasMonth = monthNames.some(m => line.includes(m));
            const hasYear = /\b20\d{2}\b/.test(line);
            if (hasMonth || hasYear) {
              lines[i] = dateValue;
            }
          });
          
          const newText = lines.join('\n');
          shape.getText().setText(newText);

          const updatedText = shape.getText().asString();

          const weekStart = updatedText.indexOf(weekFormatted);
          if (weekStart >= 0) {
            shape.getText().getRange(weekStart, weekStart + weekFormatted.length)
              .getTextStyle().setForegroundColor('#f5b740');
          }

          const dateStart = updatedText.indexOf(dateValue);
          if (dateStart >= 0) {
            shape.getText().getRange(dateStart, dateStart + dateValue.length)
              .getTextStyle().setForegroundColor('#ffffff');
          }
        }
      }
    }
  });
  
  const qrSheet = ss.getSheetByName('Master_QR');
  const vendorNames = qrSheet.getRange('A2:A13').getDisplayValues().flat();
  const vendorIndex = vendorNames.indexOf(vendorName);
  
  let qrData = [];
  if (vendorIndex >= 0) {
    const row = vendorIndex + 2;
    qrData = qrSheet.getRange('B' + row + ':G' + row).getDisplayValues()[0];
  }
  
  const slide2 = presentation.getSlides()[1];
  const table = slide2.getTables()[0];
  
  if (vendorIndex >= 0) {
    for (let col = 0; col < 6; col++) {
      const cell = table.getCell(1, col);
      cell.getText().setText(String(qrData[col]));
    }
  } else {
    for (let col = 0; col < 6; col++) {
      const cell = table.getCell(1, col);
      cell.getText().setText('no data found');
      cell.getText().getTextStyle().setForegroundColor('#ff0000');
    }
  }
  
  const weekNumber = parseInt(weekValue.match(/\d+/)[0]);
  const slide3 = presentation.getSlides()[2];
  const table3 = slide3.getTables()[0];
  
  if (table3 && vendorIndex >= 0) {
    const neededCols = weekNumber * 2;
    const totalCols = table3.getNumColumns();
    
    for (let c = neededCols; c < totalCols; c++) {
      table3.getCell(1, c).getText().setText('');
      table3.getCell(2, c).getText().setText('');
    }
    
    for (let w = 0; w < weekNumber; w++) {
      table3.getCell(1, w * 2).getText().setText('Fault of order %');
      table3.getCell(1, w * 2 + 1).getText().setText('Fault of Service %');
    }
    
    const dataCol = (weekNumber - 1) * 2;
    
    table3.getCell(2, dataCol).getText().setText(String(qrData[2]));
    table3.getCell(2, dataCol + 1).getText().setText(String(qrData[5]));
  }
  
  SlidesApp.getUi().alert(
    'Update Complete!\n\n' +
    'Title: ' + newTitle + '\n' +
    'Week: ' + weekFormatted + '\n' +
    'Date: ' + dateValue + '\n' +
    'Vendor: ' + vendorName
  );
  
  console.log('Title: ' + newTitle);
  console.log('Week: ' + weekFormatted);
  console.log('Date: ' + dateValue);
  console.log('Vendor: ' + vendorName);
  console.log('Vendor Index: ' + vendorIndex);
  console.log('Week Number: ' + weekNumber);
}