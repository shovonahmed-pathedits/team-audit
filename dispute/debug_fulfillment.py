import requests
import json
import base64
import os
import re

# Load credentials
HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, "Documents", "DisputeFiller")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

with open(CONFIG_FILE, "r") as f:
    cfg = json.load(f)

email = cfg["email"]
password = base64.b64decode(cfg["password"]).decode()
vId = cfg["vendor_id"]
lId = cfg["location_id"]

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})

print("Logging in...")
r0 = s.get("https://tista.app/users/sign_in")
csrf = re.search(r'name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']', r0.text)
token = csrf.group(1) if csrf else ""

r1 = s.post("https://tista.app/users/sign_in", data={
    "authenticity_token": token,
    "user[email]": email,
    "user[password]": password,
    "commit": "Log in"
})

print("Fetching fulfillments for #443065...")
srch_url = f"https://tista.app/manage/vendors/{vId}/order_disputes/new/fetch_fulfillments?order_name=%23443065&location_id={lId}"
r2 = s.get(srch_url)

print("Status:", r2.status_code)
# Save HTML response to inspect
with open("e:/Mohsin678/CLI/dispute/debug_fulfillment_page.html", "w", encoding="utf-8") as f:
    f.write(r2.text)

print("Done! HTML written to e:/Mohsin678/CLI/dispute/debug_fulfillment_page.html")
