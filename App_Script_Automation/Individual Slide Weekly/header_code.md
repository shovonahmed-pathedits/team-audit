function autoUpdateFileName() {
  var presentation = SlidesApp.getActivePresentation();
  var slide = presentation.getSlides()[0]; // প্রথম স্লাইড চেক করবে
  
  var weekText = "";
  var dateText = "";
  
  // স্লাইডের সব এলিমেন্ট (Shapes, Tables, etc.) চেক করা
  var pageElements = slide.getPageElements();
  
  pageElements.forEach(function(element) {
    var textValue = "";
    
    // যদি এলিমেন্টটি টেবিল হয় (শিট থেকে আনলে টেবিল হওয়ার সম্ভাবনা থাকে)
    if (element.getPageElementType() == SlidesApp.PageElementType.TABLE) {
      var table = element.asTable();
      for (var r = 0; r < table.getNumRows(); r++) {
        for (var c = 0; c < table.getNumColumns(); c++) {
          textValue += table.getCell(r, c).getText().asString() + " ";
        }
      }
    } 
    // যদি এলিমেন্টটি সাধারণ টেক্সট বা শেপ হয়
    else if (element.getPageElementType() == SlidesApp.PageElementType.SHAPE) {
      textValue = element.asShape().getText().asString();
    }

    // Week - XX ফরম্যাট খোঁজা
    var weekMatch = textValue.match(/Week\s*-\s*\d+/i);
    if (weekMatch) {
      weekText = weekMatch[0].trim();
    }
    
    // ব্র্যাকেটসহ তারিখ ( XX - XX Month, Year ) খোঁজা
    var dateMatch = textValue.match(/\(\s*\d{1,2}\s*-\s*\d{1,2}\s+[a-zA-Z]+\s*,\s*\d{4}\s*\)/);
    if (dateMatch) {
      dateText = dateMatch[0].trim();
    }
  });

  // যদি দুটোই পাওয়া যায়, তবেই রিনেম করবে
  if (weekText !== "" && dateText !== "") {
    var newName = "Clipping Pix, QCR, " + weekText + " " + dateText;
    
    // নাম পরিবর্তন করার আগে চেক করা যাতে বারবার একই কাজ না করে
    if (presentation.getName() !== newName) {
      DriveApp.getFileById(presentation.getId()).setName(newName);
      console.log("Updated to: " + newName);
    }
  }
}