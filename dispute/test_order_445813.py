import requests
import json
import base64
import re

CONFIG_FILE = r'C:\Users\User\Documents\DisputeFiller\config.json'
with open(CONFIG_FILE, 'r') as f:
    cfg = json.load(f)

email = cfg['email']
password = base64.b64decode(cfg['password']).decode()
vId = cfg['vendor_id']
lId = cfg['location_id']

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

print("Performing fresh login...")
r0 = s.get('https://tista.app/users/sign_in')
csrf = re.search(r'name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']', r0.text)
token = csrf.group(1) if csrf else ''

r_login = s.post('https://tista.app/users/sign_in', data={
    'authenticity_token': token,
    'user[email]': email,
    'user[password]': password,
    'commit': 'Log in'
})

print("Login result URL:", r_login.url)
print("Is logged in?", "sign_in" not in r_login.url)

url = f'https://tista.app/manage/vendors/{vId}/order_disputes/new/fetch_fulfillments?order_name=%23445813&location_id={lId}'
r = s.get(url)

print(f"Search URL: {url}")
print(f"Search status: {r.status_code}, Length: {len(r.text)}, URL: {r.url}")

rows = re.findall(r'<tr[^>]*>([\s\S]*?)</tr>', r.text, re.I)
print(f"Rows found: {len(rows)}")
for idx, row in enumerate(rows):
    print(f"--- Row {idx} ---")
    print(row.strip()[:200])
