# DisputeFiller — Setup Guide

## Step 1: Install Python packages

Open a terminal in this folder and run:

```
pip install -r requirements.txt
```

---

## Step 2: Google Cloud Setup  (one-time only)

You need a `credentials.json` file from Google Cloud Console.

1. Go to: https://console.cloud.google.com/
2. Create a new project (or use existing)
3. Enable the **Google Slides API**:
   - APIs & Services → Library → search "Google Slides API" → Enable
4. Create OAuth2 credentials:
   - APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client IDs
   - Application type: **Desktop app**
   - Name: `Dispute Filler`
   - Download the JSON file
5. Rename it to `credentials.json`
6. Place it in:
   ```
   C:\Users\<YourName>\Documents\DisputeFiller\credentials.json
   ```

---

## Step 3: Run the app

```
pythonw DisputeFiller.pyw
```

Or double-click `DisputeFiller.pyw`.

---

## First-time login

1. Enter Tista **email + password** + **Vendor ID** (1) + **Location ID** (1)
2. Click **🔗 Connect Google Account** — a browser will open
3. Sign in with the Gmail that owns the Slides presentation
4. Check **Remember me** → click **Log In**
5. Next time: auto-login, no prompts needed

---

## Usage

1. Paste the Google Slides share link → click **Load**
2. All disputes from slides 5–N appear in the table
3. Click **Submit** on the row you want
4. Console log shows each step:
   - `🔑 CSRF token acquired`
   - `🎯 Fulfillment matched`
   - `💎 Dispute created!`
   - `📅 Slide date updated`
5. Row turns **✅ Done** or **❌ Error** (retry-able)
