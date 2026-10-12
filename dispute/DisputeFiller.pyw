"""
DisputeFiller.pyw  --  Tista Dispute Automation
UI cloned from Path-Sync.pyw (exact aesthetic match).

Architecture:
  - CustomTkinter desktop app (Light mode, Inter + Times New Roman fonts)
  - Google OAuth2 for Slides API access (token cached, silent re-auth)
  - Tista session via requests (cookies + CSRF, remembered between runs)
  - Per-row Submit in the dispute table (one at a time)
  - Duplicate check before submission with warning dialog
  - Date sync back to slide after successful create

Setup:
  1. pip install -r requirements.txt
  2. Place credentials.json from Google Cloud Console in:
       %USERPROFILE%\\Documents\\DisputeFiller\\credentials.json
  3. Run: pythonw DisputeFiller.pyw
"""

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
import customtkinter as ctk
from tkinter import messagebox
import threading
import requests
import re
import json
import base64
import os
import platform
import ctypes
import traceback
from datetime import datetime
from PIL import Image

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request as GoogleRequest
    from googleapiclient.discovery import build
    GOOGLE_OK = True
except ImportError:
    GOOGLE_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
TISTA_BASE = "https://tista.app"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/presentations",  # read+write for date sync
]

HOME       = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, "Documents", "DisputeFiller")
os.makedirs(CONFIG_DIR, exist_ok=True)

# Hide the config folder on Windows (same trick as Path-Sync)
if platform.system() == "Windows":
    try:
        ctypes.windll.kernel32.SetFileAttributesW(CONFIG_DIR, 0x02)
    except Exception:
        pass

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
TOKEN_FILE  = os.path.join(CONFIG_DIR, "google_token.json")
CREDS_FILE  = os.path.join(CONFIG_DIR, "credentials.json")

# ─────────────────────────────────────────────────────────────────────────────
# PATH-SYNC COLOR TOKENS  (system adaptive)
# ─────────────────────────────────────────────────────────────────────────────
C_BG          = "#1E1E1E"
C_LT          = "#262626"
C_DK          = "#262626"
C_ORANGE      = "#F07900"
C_BORDER      = "#404040"
C_TEXT_WHITE  = "#FFFFFF"
C_TEXT        = "#FFFFFF"

C_PRIMARY     = "#FFFFFF"
C_PRIMARY_H   = "#CCCCCC"
C_PRIMARY_T   = "#000000"

C_BTN_WHITE   = "#FFFFFF"
C_BTN_WHITE_H = "#CCCCCC"
C_BTN_WHITE_T = "#000000"

C_RED         = "#E55050"
C_RED_H       = "#B33E3E"
C_GREEN       = "#2CC985"
C_GREEN_H     = "#25A36D"
C_MUTED       = "#666666"

# ─────────────────────────────────────────────────────────────────────────────
# CSRF / HTTP HELPERS  (ported from Code.gs)
# ─────────────────────────────────────────────────────────────────────────────
_CSRF_PATTERNS = [
    re.compile(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'content=["\']([^"\']+)["\'][^>]+name=["\']csrf-token["\']', re.I),
    re.compile(r'name=["\']authenticity_token["\'][^>]+value=["\']([^"\']+)["\']', re.I),
    re.compile(r'value=["\']([^"\']+)["\'][^>]+name=["\']authenticity_token["\']', re.I),
]


def extract_csrf(html: str) -> str:
    for pat in _CSRF_PATTERNS:
        m = pat.search(html)
        if m:
            return m.group(1)
    return ""


def extract_pres_id(link: str) -> str:
    m = re.search(r"/presentation/d/([a-zA-Z0-9_-]+)", link)
    return m.group(1) if m else ""


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE DATA EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────
def _slide_text(slide: dict) -> str:
    """Recursively pull all text from a Slides API slide object."""
    parts: list = []

    def pull(elem: dict):
        # Shape text
        for te in elem.get("shape", {}).get("text", {}).get("textElements", []):
            c = te.get("textRun", {}).get("content", "")
            if c.strip():
                parts.append(c)
        # Table cells
        for row in elem.get("table", {}).get("tableRows", []):
            for cell in row.get("tableCells", []):
                for te in cell.get("text", {}).get("textElements", []):
                    c = te.get("textRun", {}).get("content", "")
                    if c.strip():
                        parts.append(c)
        # Group children (recursive)
        for child in elem.get("elementGroup", {}).get("children", []):
            pull(child)

    for elem in slide.get("pageElements", []):
        pull(elem)
    return " ".join(parts)


def parse_dispute(text: str, slide_num: int, slide_id: str = ""):
    """Extract dispute fields from slide text. Returns None if no Order ID."""
    m = re.search(r"#(\d+)", text)
    if not m:
        return None
    d = {
        "orderId":  m.group(1),
        "vendor":   "",
        "date":     "",
        "totalQty": "",
        "faultQty": "",
        "severity": "low",
        "comment":  "",
        "slideNum": slide_num,
        "slideId":  slide_id,
    }

    m2 = re.search(r"Sub\.?\s*Name[:\s]+(.+?)(?:\s{2,}|$)", text, re.I)
    if m2:
        d["vendor"] = m2.group(1).strip()

    m2 = re.search(r"(?:Dispute\s*)?Date[:\s]+(\d{2}/\d{2}/\d{4})", text, re.I)
    if m2:
        d["date"] = m2.group(1)

    m2 = re.search(r"Image\s*Quantity[:\s]+(\d+)", text, re.I)
    if m2:
        d["totalQty"] = m2.group(1)

    # Checked / Fault: X/Y  ->  faultQty = Y (second number = faults)
    m2 = re.search(r"Checked\s*/\s*Fault[:\s]+\d+\s*/\s*(\d+)", text, re.I)
    if m2:
        d["faultQty"] = m2.group(1)

    m2 = re.search(r"Fault\s*severity[:\s]+(\w+)", text, re.I)
    if m2:
        sv = m2.group(1).lower()
        d["severity"] = "low" if sv == "minor" else sv

    m2 = re.search(r"Type\s*of\s*error[:\s]+([\s\S]+?)(?=\s*Fault\s*severity|$)", text, re.I)
    if m2:
        d["comment"] = m2.group(1).strip()

    return d


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP CLASS
# ─────────────────────────────────────────────────────────────────────────────
class DisputeFillerApp(ctk.CTk):

    # ── init ──────────────────────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        self.title("Dispute Filler")
        self.minsize(500, 795)
        self.resizable(False, False)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color=C_BG)

        # Boost process priority (same as Path-Sync)
        try:
            if platform.system() == "Windows":
                ctypes.windll.kernel32.SetPriorityClass(
                    ctypes.windll.kernel32.GetCurrentProcess(), 0x00000080)
        except Exception:
            pass

        # ── State ────────────────────────────────────────────────────────────
        self.geometry_initialized = False
        self.disputes             = []
        self.row_widgets          = []
        self.session              = requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self.cookie_jar_str       = ""
        self.last_csrf_str        = ""
        self.google_creds         = None
        self.slides_service       = None
        self.google_connected     = False
        self.submit_lock          = threading.Lock()
        self.presentation_id      = ""
        self.submitting_all       = False
        self.stop_all_flag        = threading.Event()
        self.audit_date_filter    = ""   # "DD/MM/YY - DD/MM/YY" parsed from presentation title

        # ── CTkVars ──────────────────────────────────────────────────────────
        self.email_var       = ctk.StringVar()
        self.pass_var        = ctk.StringVar()
        self.vendor_id_var   = ctk.StringVar(value="1")
        self.location_id_var = ctk.StringVar(value="1")
        self.keep_var        = ctk.BooleanVar(value=True)
        self.slides_link_var = ctk.StringVar()
        self.status_var      = ctk.StringVar(value="Ready")
        self.progress_var    = ctk.StringVar(value="")

        # ── Layout container (same as Path-Sync) ─────────────────────────────
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self._load_config()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        # Clean up temporary debug HTML files from workspace on close
        debug_files = ["debug_last_page.html", "debug_fulfillment_page.html"]
        for f_name in debug_files:
            try:
                path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f_name)
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

        # If remember me is NOT checked, we also clean up config/token files on close
        if not self.keep_var.get():
            try:
                if os.path.exists(CONFIG_FILE):
                    os.remove(CONFIG_FILE)
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
            except Exception:
                pass

        self.destroy()

    # ── Geometry helper ───────────────────────────────────────────────────────
    def _set_geometry(self, w=500, h=795):
        if not self.geometry_initialized:
            x = (self.winfo_screenwidth()  // 2) - (w // 2)
            y = (self.winfo_screenheight() // 2) - (h // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
            self.geometry_initialized = True

    def _clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    # ─────────────────────────────────────────────────────────────────────────
    # CONFIG  I/O
    # ─────────────────────────────────────────────────────────────────────────
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.email_var.set(cfg.get("email", ""))
                raw = cfg.get("password", "")
                if raw:
                    self.pass_var.set(
                        base64.b64decode(raw.encode()).decode("utf-8"))
                self.vendor_id_var.set(str(cfg.get("vendor_id", "1")))
                self.location_id_var.set(str(cfg.get("location_id", "1")))
                self.keep_var.set(cfg.get("keep_logged_in", True))
                self.cookie_jar_str = cfg.get("cookie_jar", "")
                self.last_csrf_str  = cfg.get("last_csrf", "")
                # Restore cookie jar into session
                if self.cookie_jar_str:
                    for pair in self.cookie_jar_str.split(";"):
                        pair = pair.strip()
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            self.session.cookies.set(k.strip(), v.strip())
            except Exception:
                pass

        self._load_google_token()

        # Route: skip login if creds saved + Google connected
        if (self.email_var.get() and self.pass_var.get()
                and self.keep_var.get() and self.google_connected):
            self._show_main_page()
        else:
            self._show_login_page()

    def _save_config(self, save_creds=False):
        try:
            cfg = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
        except Exception:
            cfg = {}

        cfg["keep_logged_in"] = self.keep_var.get()
        cfg["vendor_id"]      = self.vendor_id_var.get()
        cfg["location_id"]    = self.location_id_var.get()
        cfg["slides_link"]    = self.slides_link_var.get()
        cfg["cookie_jar"]     = "; ".join(
            f"{c.name}={c.value}" for c in self.session.cookies)
        cfg["last_csrf"]      = self.last_csrf_str

        if save_creds:
            cfg["email"]    = self.email_var.get().strip()
            pwd = self.pass_var.get().strip()
            cfg["password"] = (
                base64.b64encode(pwd.encode()).decode() if pwd else "")
        else:
            cfg["email"]    = ""
            cfg["password"] = ""

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)

    # ─────────────────────────────────────────────────────────────────────────
    # GOOGLE OAUTH
    # ─────────────────────────────────────────────────────────────────────────
    def _load_google_token(self):
        if not GOOGLE_OK:
            return
        if os.path.exists(TOKEN_FILE):
            try:
                self.google_creds = Credentials.from_authorized_user_file(
                    TOKEN_FILE, GOOGLE_SCOPES)
                if (self.google_creds.expired
                        and self.google_creds.refresh_token):
                    self.google_creds.refresh(GoogleRequest())
                    self._persist_google_token()
                if self.google_creds.valid:
                    self.google_connected = True
                    self.slides_service = build(
                        "slides", "v1",
                        credentials=self.google_creds,
                        cache_discovery=False)
            except Exception:
                self.google_connected = False

    def _persist_google_token(self):
        if self.google_creds:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(self.google_creds.to_json())

    def _connect_google_in_thread(self, callback):
        try:
            if not GOOGLE_OK:
                self.after(0, lambda: callback(
                    False, "Install google-auth libraries first.\npip install -r requirements.txt"))
                return
            if not os.path.exists(CREDS_FILE):
                self.after(0, lambda: callback(
                    False,
                    f"credentials.json not found.\nPlace it in:\n{CONFIG_DIR}"))
                return
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDS_FILE, GOOGLE_SCOPES)
            self.google_creds = flow.run_local_server(port=0)
            self._persist_google_token()
            self.slides_service = build(
                "slides", "v1",
                credentials=self.google_creds,
                cache_discovery=False)
            self.google_connected = True
            self.after(0, lambda: callback(True, ""))
        except Exception as e:
            msg = str(e)[:160]
            self.after(0, lambda: callback(False, msg))

    # ─────────────────────────────────────────────────────────────────────────
    # LOGIN PAGE  (exact Path-Sync clone + Google section)
    # ─────────────────────────────────────────────────────────────────────────
    def _show_login_page(self):
        self._clear_container()
        self._set_geometry(450, 750)

        outer = ctk.CTkFrame(
            self.container,
            fg_color=C_LT, corner_radius=20,
            border_width=1, border_color=C_BORDER)
        outer.pack(fill="both", expand=True, padx=20, pady=20)

        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(expand=True, padx=10, pady=10)

        # ── Title ──────────────────────────────────────────────────────────
        ctk.CTkLabel(
            inner, text="Dispute Filler",
            font=ctk.CTkFont(family="Livvic", size=13, weight="bold")
        ).pack(pady=(0, 22))

        # ── Tista Credentials ──────────────────────────────────────────────
        ctk.CTkLabel(
            inner, text="   Tista Credentials",
            font=ctk.CTkFont(family="Livvic", size=14, weight="bold")
        ).pack(padx=16, pady=(8, 4), anchor="w")

        self._email_ent = ctk.CTkEntry(
            inner, textvariable=self.email_var,
            placeholder_text="Email",
            fg_color=C_BG, text_color=C_TEXT, border_color=C_BG,
            height=40, width=350, corner_radius=20,
            font=ctk.CTkFont(family="Livvic"))
        self._email_ent.pack(padx=17, pady=5, fill="x")

        self._pass_ent = ctk.CTkEntry(
            inner, textvariable=self.pass_var, show="*",
            placeholder_text="Password",
            fg_color=C_BG, text_color=C_TEXT, border_color=C_BG,
            height=40, width=350, corner_radius=20,
            font=ctk.CTkFont(family="Livvic"))
        self._pass_ent.pack(padx=17, pady=5, fill="x")

        # Vendor + Location IDs row
        ids_row = ctk.CTkFrame(inner, fg_color="transparent")
        ids_row.pack(padx=17, pady=5, fill="x")
        ids_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkEntry(
            ids_row, textvariable=self.vendor_id_var,
            placeholder_text="Vendor ID (e.g. 1)",
            fg_color=C_BG, text_color=C_TEXT, border_color=C_BG,
            height=40, corner_radius=20,
            font=ctk.CTkFont(family="Livvic")
        ).grid(row=0, column=0, padx=(0, 5), sticky="ew")

        ctk.CTkEntry(
            ids_row, textvariable=self.location_id_var,
            placeholder_text="Location ID (e.g. 1)",
            fg_color=C_BG, text_color=C_TEXT, border_color=C_BG,
            height=40, corner_radius=20,
            font=ctk.CTkFont(family="Livvic")
        ).grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # ── Google Account section ─────────────────────────────────────────
        ctk.CTkLabel(
            inner, text="   Google Account  (for Slides access)",
            font=ctk.CTkFont(family="Livvic", size=14, weight="bold")
        ).pack(padx=16, pady=(18, 4), anchor="w")

        self._google_btn = ctk.CTkButton(
            inner,
            text="✅ Google Connected" if self.google_connected
                 else "🔗 Connect Google Account",
            corner_radius=20,
            fg_color=C_GREEN if self.google_connected else C_PRIMARY,
            hover_color=C_GREEN_H if self.google_connected else C_PRIMARY_H,
            font=ctk.CTkFont(family="Livvic", size=14, weight="bold"),
            height=40, text_color="#FFFFFF" if self.google_connected else C_PRIMARY_T,
            command=self._on_connect_google)
        self._google_btn.pack(padx=17, pady=5, fill="x")

        self._google_msg = ctk.CTkLabel(
            inner, text="",
            font=ctk.CTkFont(family="Livvic", size=11),
            text_color="#FF4D4D", wraplength=350)
        self._google_msg.pack(pady=(0, 4))

        # ── Remember + Login ───────────────────────────────────────────────
        ctk.CTkCheckBox(
            inner, text="Remember me",
            fg_color="#363636", checkmark_color="#A9A9A9",
            variable=self.keep_var,
            font=ctk.CTkFont(family="Livvic", size=16),
            checkbox_width=16, checkbox_height=16
        ).pack(anchor="e", padx=17, pady=(14, 10))

        self._login_btn = ctk.CTkButton(
            inner, text="Log In", corner_radius=20,
            fg_color=C_PRIMARY, hover_color=C_PRIMARY_H,
            font=ctk.CTkFont(family="Livvic", size=14, weight="bold"),
            height=40, text_color=C_PRIMARY_T,
            command=self._attempt_login)
        self._login_btn.pack(padx=17, pady=5, fill="x")

        self._login_msg = ctk.CTkLabel(
            inner, text="",
            font=ctk.CTkFont(family="Livvic", size=12),
            text_color="#FF4D4D")
        self._login_msg.pack(pady=(0, 5))

        # Wire validation
        for v in [self.email_var, self.pass_var, self.vendor_id_var]:
            v.trace_add("write", lambda *_: self._refresh_login_btn())
        self._refresh_login_btn()

    def _refresh_login_btn(self):
        ok = bool(
            self.email_var.get() and self.pass_var.get()
            and self.vendor_id_var.get() and self.google_connected)
        self._login_btn.configure(
            state="normal" if ok else "disabled",
            fg_color=C_PRIMARY)

    def _on_connect_google(self):
        if self.google_connected:
            return
        self._google_btn.configure(state="disabled", text="Connecting…")
        self._google_msg.configure(text="")
        threading.Thread(
            target=self._connect_google_in_thread,
            args=(self._on_google_done,),
            daemon=True).start()

    def _on_google_done(self, ok, msg):
        if ok:
            self._google_btn.configure(
                state="normal", text="✅ Google Connected",
                fg_color=C_GREEN, hover_color=C_GREEN_H)
            self._google_msg.configure(text="")
        else:
            self._google_btn.configure(
                state="normal", text="🔗 Connect Google Account",
                fg_color=C_PRIMARY, hover_color=C_PRIMARY_H)
            self._google_msg.configure(text=msg)
        self._refresh_login_btn()

    def _attempt_login(self):
        self._login_btn.configure(state="disabled", text="Verifying…")
        self._login_msg.configure(text="")
        e = self.email_var.get().strip()
        p = self.pass_var.get().strip()
        threading.Thread(
            target=self._login_thread, args=(e, p), daemon=True).start()

    def _login_thread(self, email, password):
        ok, msg = self._tista_login(email, password)
        self.after(0, lambda: self._on_login_result(ok, msg))

    def _on_login_result(self, ok, msg):
        if ok:
            self._save_config(save_creds=self.keep_var.get())
            self._show_main_page()
        else:
            self._login_btn.configure(state="normal", text="Log In")
            self._login_msg.configure(
                text=msg or "Login failed. Check credentials.")

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN PAGE  (exact Path-Sync clone structure)
    # ─────────────────────────────────────────────────────────────────────────
    def _show_main_page(self):
        self._clear_container()
        self._set_geometry(500, 795)
        self.minsize(500, 795)

        main = ctk.CTkFrame(self.container, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=15, pady=(12, 18))

        # ── Header ─────────────────────────────────────────────────────────
        header_row = ctk.CTkFrame(main, fg_color="transparent")
        header_row.pack(fill="x", pady=(2, 6))

        # Center Title (Livvic Bold, size 28)
        ctk.CTkLabel(
            header_row, text="Dispute Filler",
            font=ctk.CTkFont(family="Livvic", size=28, weight="bold")
        ).pack(side="left", expand=True, pady=(2, 3))

        # Right Logout Button (Red #E55050, white text — matches Path-Sync)
        ctk.CTkButton(
            header_row, text="Logout",
            width=80, height=30, corner_radius=10,
            fg_color="#E55050", hover_color="#B33E3E",
            font=ctk.CTkFont(family="Livvic", size=13, weight="bold"),
            text_color="#FFFFFF", command=self._logout
        ).pack(side="right", padx=(0, 5))

        # ── SOURCE CARD  (dark #262626) ─────────────────────────────────────
        src = ctk.CTkFrame(main, fg_color=C_DK, corner_radius=20)
        src.pack(fill="x", pady=6)

        ctk.CTkLabel(
            src, text="   Source & Destination",
            font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
            text_color=C_TEXT_WHITE
        ).pack(anchor="w", padx=16, pady=(10, 4))

        # Subtitle label exactly as in Path Sync image
        self._src_sub = ctk.CTkLabel(
            src, text="Click the 'Input Links' button to add order links.",
            font=ctk.CTkFont(family="Livvic", size=11), text_color="#aaaaaa"
        )
        self._src_sub.pack(anchor="w", padx=17, pady=(0, 6))

        self._link_btn = ctk.CTkButton(
            src, text="Input Links",
            height=38, corner_radius=19,
            fg_color=C_BTN_WHITE, hover_color=C_BTN_WHITE_H,
            font=ctk.CTkFont(family="Livvic", size=13, weight="bold"),
            text_color=C_BTN_WHITE_T, command=self._on_link_btn_click)
        self._link_btn.pack(fill="x", padx=16, pady=(0, 8))



        # ── DISPUTE QUEUE CARD  (dark) ──────────────────────────────────────
        queue = ctk.CTkFrame(main, fg_color=C_DK, corner_radius=20)
        queue.pack(fill="x", pady=6)

        # Table column header — fixed-width pack layout (matches row layout exactly)
        hdr = ctk.CTkFrame(queue, fg_color="#1c1c1c", corner_radius=8)
        hdr.pack(fill="x", padx=(10, 26), pady=(4, 3))

        # Col widths match row widgets exactly: SL=22, Order=68, Location=82, Qty/Fault=62, severity=48, Status=65, Action=54
        hdr_cols = [("SL", 22), ("Order", 68), ("Location", 82),
                    ("Qty/Fault", 62), ("Severity", 48), ("Status", 65), ("Action", 54)]
        for i, (txt, w) in enumerate(hdr_cols):
            anchor = "center" if i in (5, 6) else "w"
            ctk.CTkLabel(
                hdr, text=txt, width=w,
                font=ctk.CTkFont(family="Livvic", size=10, weight="bold"),
                text_color="#888888", anchor=anchor
            ).pack(side="left", padx=(4 if i == 0 else 2, 6 if i == len(hdr_cols) - 1 else 0), pady=4)

        # Scrollable rows area
        self._scroll = ctk.CTkScrollableFrame(
            queue, fg_color="transparent", height=170, corner_radius=0)
        self._scroll.pack(fill="x", padx=8, pady=(0, 10))

        self._empty_lbl = ctk.CTkLabel(
            self._scroll,
            text="No disputes loaded. Paste a Slides link and click Load.",
            font=ctk.CTkFont(family="Livvic", size=12), text_color="#666666")
        self._empty_lbl.pack(pady=22)

        # ── ACTIVITY CARD  (light #F0F0F0) ───────────────────────────────────
        act = ctk.CTkFrame(
            main, fg_color=C_LT, corner_radius=20,
            border_width=1, border_color=C_BORDER)
        act.pack(fill="x", pady=6)

        ctk.CTkLabel(
            act, text="   Activity",
            font=ctk.CTkFont(family="Livvic", size=12, weight="bold")
        ).pack(anchor="w", padx=16, pady=(8, 2))

        btn_row = ctk.CTkFrame(act, fg_color="transparent")
        btn_row.pack(fill="x", padx=17, pady=(0, 12))
        btn_row.grid_columnconfigure((0, 1), weight=1)

        self._submit_all_btn = ctk.CTkButton(
            btn_row, text="🚀 Submit All", corner_radius=20,
            fg_color="#56c0b3", hover_color="#3da89b",
            font=ctk.CTkFont(family="Livvic", size=13, weight="bold"),
            height=38, text_color="#000000",
            command=self._on_submit_all_click)
        self._submit_all_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        # Dynamic action button — shows 🗑 Clear when idle, ● Stop when running
        self._action_btn = ctk.CTkButton(
            btn_row, text="🗑 Clear", corner_radius=20,
            fg_color="#FFFFFF", hover_color="#cccccc",
            font=ctk.CTkFont(family="Livvic", size=13, weight="bold"),
            height=38, text_color="#000000",
            command=self._clear_table)
        self._action_btn.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # ── STATUS CARD  (no border — clean) ─────────────────────────────────
        stat = ctk.CTkFrame(main, fg_color=C_LT, corner_radius=20, border_width=1, border_color=C_BORDER)
        stat.pack(fill="x", pady=6)

        # Row frame for Status Header and Progress Text
        stat_hdr = ctk.CTkFrame(stat, fg_color="transparent")
        stat_hdr.pack(fill="x", padx=16, pady=(10, 3))

        ctk.CTkLabel(
            stat_hdr, text="Status",
            font=ctk.CTkFont(family="Livvic", size=12, weight="bold")
        ).pack(side="left")

        self._prog_overlay = ctk.CTkLabel(
            stat_hdr, textvariable=self.progress_var,
            font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
            text_color=C_ORANGE)
        self._prog_overlay.pack(side="right", padx=1)

        # Standard packed progress bar (height 15, no overlays)
        self.progress_bar = ctk.CTkProgressBar(
            stat, orientation="horizontal",
            progress_color=C_ORANGE, height=15, fg_color=C_DK)
        self.progress_bar.set(0)
        self.progress_bar.pack(padx=17, pady=(4, 10), fill="x")

        # Console log — brighter soft-green, size 11, thinner orange border
        self._log_box = ctk.CTkTextbox(
            stat, height=110, corner_radius=8,
            fg_color="#111316", text_color="#c8ffc8",
            font=ctk.CTkFont(family="Consolas", size=11),
            border_color=C_ORANGE, border_width=2)
        self._log_box.pack(padx=17, pady=(0, 12), fill="x")
        self._log_box.configure(state="disabled")

        if self.slides_link_var.get():
            self._src_sub.configure(
                text="Link saved from last session. Click 'Input Links' to load.",
                text_color="#FFFFFF")

    # ─────────────────────────────────────────────────────────────────────────
    # SLIDES LOADING
    # ─────────────────────────────────────────────────────────────────────────
    def _start_load_slides(self):
        raw = self.slides_link_var.get().strip()
        if not raw:
            self._src_sub.configure(
                text="⚠️ Paste Slides links first.",
                text_color="#ffcc00")
            return
        links = [l.strip() for l in raw.split("\n") if l.strip()]
        pids = []
        bad = []
        for link in links:
            pid = extract_pres_id(link)
            if pid:
                pids.append(pid)
            else:
                bad.append(link[:50])
        if not pids:
            self._src_sub.configure(
                text="⚠️ Cannot parse Presentation ID from link(s).",
                text_color="#ffcc00")
            return
        if bad:
            self._log(f"⚠️ Skipped {len(bad)} unparseable link(s).")

        self.presentation_id = pids[0]
        self._src_sub.configure(
            text="Fetching slides data…", text_color="#FFFFFF")
        threading.Thread(
            target=self._load_slides_thread, args=(pids,), daemon=True).start()

    def _load_slides_thread(self, pids):
        self._pres_count = len(pids)
        all_disputes = []
        self.audit_date_filter = ""  # reset on each load
        try:
            for i, pid in enumerate(pids):
                if i > 0:
                    self.after(0, lambda: self._src_sub.configure(
                        text=f"Fetching slides from presentation {i + 1} of {len(pids)}…",
                        text_color="#FFFFFF"))
                pres = self.slides_service.presentations().get(
                    presentationId=pid).execute()
                # Parse date range from presentation title (first presentation wins)
                if not self.audit_date_filter:
                    title = pres.get("title", "")
                    parsed = self._parse_date_from_title(title)
                    if parsed:
                        self.audit_date_filter = parsed
                        self._log(f"📅 Audit date range detected: {parsed}")
                raw_slides = pres.get("slides", [])
                for idx, sl in enumerate(raw_slides[4:], start=5):
                    text = _slide_text(sl)
                    d = parse_dispute(text, idx, sl.get("objectId", ""))
                    if d:
                        all_disputes.append(d)
            self.disputes = all_disputes
            self.after(0, self._on_slides_ready)
        except Exception as e:
            err = str(e)[:140]
            self.after(0, lambda: self._src_sub.configure(
                text=f"❌ Error: {err}", text_color="#FF4D4D"))

    def _on_slides_ready(self):
        n = len(self.disputes)
        pres_info = f" ({self._pres_count} presentations)" if self._pres_count > 1 else ""
        self._src_sub.configure(
            text=f"✅ {n} dispute{'s' if n != 1 else ''} found{pres_info}",
            text_color=C_TEXT_WHITE)
        self.status_var.set(f"Ready — {n} disputes in queue")
        self.progress_var.set("")
        self.progress_bar.set(0)
        self._save_config(save_creds=self.keep_var.get())
        self._build_table()
        self._log(f"✅ {n} disputes loaded from presentation.")

    # ─────────────────────────────────────────────────────────────────────────
    # DISPUTE TABLE
    # ─────────────────────────────────────────────────────────────────────────
    def _build_table(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self.row_widgets = []

        if not self.disputes:
            ctk.CTkLabel(
                self._scroll,
                text="No disputes found in slides 5+.",
                font=ctk.CTkFont(family="Livvic", size=12),
                text_color="#666666"
            ).pack(pady=20)
            return

        for i, d in enumerate(self.disputes):
            rw = self._add_row(i, d)
            self.row_widgets.append(rw)

    def _add_row(self, idx, d):
        bg = "#2e2e2e" if idx % 2 == 0 else "#353535"
        frame = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=8)
        frame.pack(fill="x", pady=2, padx=2)

        # Helper — fixed-width label packed left
        def lbl(txt, w, color="#dddddd", anchor="w"):
            return ctk.CTkLabel(
                frame, text=txt, width=w, anchor=anchor,
                font=ctk.CTkFont(family="Livvic", size=11),
                text_color=color)

        # Col widths match header exactly: #=22, Order=68, Vendor=82, Qty=62, Sev=48, Status=65
        lbl(str(d["slideNum"]), 22).pack(side="left", padx=(4, 0), pady=6)

        # Order ID label — clickable with copy tooltip
        order_lbl = lbl(f"#{d['orderId']}", 68, C_ORANGE)
        order_lbl.configure(cursor="hand2")
        order_lbl.pack(side="left", padx=(2, 0), pady=6)

        # Tooltip click handler for order ID copy
        _tip = {"widget": None, "after_id": None}
        def _copy_order(e, oid=d['orderId'], lb=order_lbl, rf=frame, tip=_tip):
            self._copy_id_to_clipboard(self, oid)
            if tip["after_id"]:
                try:
                    rf.after_cancel(tip["after_id"])
                except Exception:
                    pass
            if tip["widget"]:
                try:
                    tip["widget"].destroy()
                except Exception:
                    pass
            tooltip = ctk.CTkToplevel(self)
            tooltip.overrideredirect(True)
            tooltip.attributes("-topmost", True)
            x = lb.winfo_rootx() + lb.winfo_width() // 2
            y = lb.winfo_rooty() - 30
            tooltip.geometry(f"+{x}+{y}")
            badge = ctk.CTkLabel(
                tooltip, text="✅ Copied!",
                font=ctk.CTkFont(family="Livvic", size=10, weight="bold"),
                text_color="#ffffff", fg_color="#1a7a40", corner_radius=8, padx=8, pady=4
            )
            badge.pack()
            tip["widget"] = tooltip
            def _dismiss(t=tip, lb2=lb):
                if t["widget"]:
                    try:
                        t["widget"].destroy()
                    except Exception:
                        pass
                    t["widget"] = None
                    t["after_id"] = None
                try:
                    lb2.configure(text_color=C_ORANGE)
                except Exception:
                    pass
            tip["after_id"] = rf.after(1500, _dismiss)
            lb.configure(text_color="#ffffff")

        order_lbl.bind("<Button-1>", _copy_order)
        order_lbl.bind("<Enter>", lambda e, l=order_lbl: l.configure(text_color="#ffffff"))
        order_lbl.bind("<Leave>", lambda e, l=order_lbl, t=_tip: l.configure(text_color=C_ORANGE) if t["widget"] is None else None)

        vn = (d["vendor"][:11] + "…") if len(d["vendor"]) > 11 else d["vendor"]
        lbl(vn, 82).pack(side="left", padx=(2, 0), pady=6)

        lbl(f"{d['totalQty']}/{d['faultQty']}", 62, anchor="center").pack(side="left", padx=(2, 0), pady=6)

        sev = d["severity"].capitalize()
        sev_color = (
            C_RED    if d["severity"] in ("high", "critical")
            else C_ORANGE if d["severity"] == "medium"
            else "#88dd88")
        lbl(sev, 48, sev_color, anchor="center").pack(side="left", padx=(2, 0), pady=6)

        # Status label — no checkbox for Pending
        status_lbl = ctk.CTkLabel(
            frame, text="Pending", width=65, anchor="center",
            font=ctk.CTkFont(family="Livvic", size=10), text_color="#888888")
        status_lbl.pack(side="left", padx=(2, 0), pady=6)

        # Submit button — 54px, fully visible
        submit_btn = ctk.CTkButton(
            frame, text="Submit", width=54, height=26,
            corner_radius=13,
            fg_color=C_PRIMARY, hover_color=C_PRIMARY_H,
            font=ctk.CTkFont(family="Livvic", size=10, weight="bold"),
            text_color=C_PRIMARY_T,
            command=lambda i=idx: self._on_submit_click(i))
        submit_btn.pack(side="left", padx=(2, 6), pady=6)

        return {"frame": frame, "status_lbl": status_lbl, "submit_btn": submit_btn}

    def _set_row_status(self, idx, text, color, btn_en=True):
        def _do():
            if 0 <= idx < len(self.row_widgets):
                rw = self.row_widgets[idx]
                rw["status_lbl"].configure(text=text, text_color=color)
                rw["submit_btn"].configure(
                    state="normal" if btn_en else "disabled")
        self.after(0, _do)

    # ─────────────────────────────────────────────────────────────────────────
    # SUBMISSION  (one dispute at a time, triggered per row)
    # ─────────────────────────────────────────────────────────────────────────
    def _on_submit_click(self, idx):
        if not self.submit_lock.acquire(blocking=False):
            messagebox.showwarning(
                "Busy",
                "Another submission is already in progress.\n"
                "Please wait for it to finish.",
                parent=self)
            return
        d = self.disputes[idx]
        self._set_row_status(idx, "⟳ Running", C_ORANGE, btn_en=False)
        self.status_var.set(f"Submitting #{d['orderId']}…")
        self._update_action_btn()
        threading.Thread(
            target=self._submit_thread, args=(idx, d), daemon=True).start()

    def _submit_thread(self, idx, d):
        try:
            vId = self.vendor_id_var.get().strip()
            lId = self.location_id_var.get().strip()
            # Step 0: Announce duplicate check in status bar
            self.after(0, lambda oid=d['orderId']: self.status_var.set(
                f"🔍 #{oid} — Checking duplicates…"))
            ok, msg = self._run_submission(vId, lId, d, idx)
            if ok:
                self._set_row_status(idx, "✅ Done", C_GREEN, btn_en=False)
            else:
                # Distinguish intentional skip from real network/server errors
                if "Cancelled" in msg or "duplicate" in msg.lower():
                    self._set_row_status(idx, "⏭ Skipped", "#ffcc00", btn_en=True)
                    self.after(0, lambda oid=d['orderId']: self.status_var.set(
                        f"⏭ #{oid} — Skipped (already exists)"))
                else:
                    self._set_row_status(idx, "❌ Error", C_RED, btn_en=True)
                    short = msg[:60]
                    self.after(0, lambda oid=d['orderId'], sh=short: self.status_var.set(
                        f"❌ #{oid} — {sh}"))
        except Exception:
            self._log(f"💥 Unexpected:\n{traceback.format_exc()[-250:]}")
            self._set_row_status(idx, "❌ Error", C_RED, btn_en=True)
        finally:
            self.submit_lock.release()
            self._update_action_btn()
            # Update progress bar — cget() runs on main thread to stay thread-safe
            def _update_ui():
                processed = sum(
                    1 for rw in self.row_widgets
                    if rw["status_lbl"].cget("text") not in ("Pending", "⟳ Running")
                )
                total = len(self.disputes)
                self.progress_var.set(f"{processed} / {total}")
                if total > 0:
                    self.progress_bar.set(processed / total)
            self.after(0, _update_ui)

    def _run_submission(self, vId, lId, d, idx, skip_dup_check=False):
        # ── Duplicate check (per-row Submit path only; Submit All uses pre-flight) ──
        # skip_dup_check=True when called from _submit_all_thread (pre-flight already ran)
        if not skip_dup_check:
            self._log(f"🔍 Checking duplicate — #{d['orderId']}…")
        if not skip_dup_check and self._is_duplicate(vId, lId, d["orderId"]):
            proceed = [False]
            evt = threading.Event()

            def ask_user():
                dialog = ctk.CTkToplevel(self)
                dialog.title("⚠️ Duplicate Dispute Found")
                dialog.resizable(False, False)
                dialog.transient(self)
                dialog.grab_set()
                w, h = 400, 200
                x = (self.winfo_screenwidth() // 2) - (w // 2)
                y = (self.winfo_screenheight() // 2) - (h // 2)
                dialog.geometry(f"{w}x{h}+{x}+{y}")
                f = ctk.CTkFrame(dialog, fg_color="transparent")
                f.pack(fill="both", expand=True, padx=20, pady=20)
                ctk.CTkLabel(
                    f, text=f"Order #{d['orderId']} already has a dispute.\n\nCreate another one anyway?",
                    font=ctk.CTkFont(family="Livvic", size=13), wraplength=360
                ).pack(pady=(10, 20))
                btn_row = ctk.CTkFrame(f, fg_color="transparent")
                btn_row.pack(fill="x")
                btn_row.grid_columnconfigure((0, 1), weight=1)
                def on_yes():
                    proceed[0] = True
                    dialog.destroy()
                    evt.set()
                def on_no():
                    proceed[0] = False
                    dialog.destroy()
                    evt.set()
                ctk.CTkButton(
                    btn_row, text="Yes", corner_radius=20,
                    fg_color=C_PRIMARY, hover_color=C_PRIMARY_H,
                    font=ctk.CTkFont(family="Livvic", size=13, weight="bold"),
                    height=36, text_color=C_PRIMARY_T, command=on_yes
                ).grid(row=0, column=0, padx=(0, 5), sticky="ew")
                ctk.CTkButton(
                    btn_row, text="No", corner_radius=20,
                    fg_color=C_BTN_WHITE, hover_color=C_BTN_WHITE_H,
                    font=ctk.CTkFont(family="Livvic", size=13, weight="bold"),
                    height=36, text_color=C_BTN_WHITE_T, command=on_no
                ).grid(row=0, column=1, padx=(5, 0), sticky="ew")
                dialog.protocol("WM_DELETE_WINDOW", on_no)

            self.after(0, ask_user)
            evt.wait(timeout=60)
            if not proceed[0]:
                return False, "Cancelled — duplicate exists."
            self._log("⚠️ Proceeding despite duplicate (user confirmed).")

        # ── Step 1: Handshake / get CSRF ────────────────────────────────────
        hs_path = (
            f"/manage/vendors/{vId}/order_disputes/"
            f"new/fetch_fulfillments?location_id={lId}")
        r1 = self._get(hs_path)
        if r1 is None:
            return False, "Network error on handshake."

        if self._is_login_page(r1):
            self._log("⚠️ Session expired — attempting automatic re-login…")
            ok, emsg = self._tista_login(
                self.email_var.get(), self.pass_var.get())
            if not ok:
                self.after(0, lambda: self.status_var.set("❌ Session expired. Please log in again."))
                return False, f"Session expired and re-login failed: {emsg}"
            self._log("✅ Auto re-login successful.")
            r1 = self._get(hs_path)
            if self._is_login_page(r1):
                return False, "Session expired even after re-login."

        csrf = extract_csrf(r1.text)
        if not csrf:
            return False, "CSRF token not found."

        # ── Step 2: Search + find fulfillment ────────────────────────────────
        self._log(f"🔎 [2/3] Searching order #{d['orderId']}…")
        clean_id = str(d["orderId"]).strip().lstrip("#")
        srch = (
            f"/manage/vendors/{vId}/order_disputes/new/"
            f"fetch_fulfillments?order_name=%23{clean_id}&location_id={lId}")
        r2 = self._get(srch)
        if r2 is None:
            return False, "Network error on search."

        if self._is_login_page(r2):
            self._log("⚠️ Session expired during search — attempting automatic re-login…")
            ok, emsg = self._tista_login(
                self.email_var.get(), self.pass_var.get())
            if not ok:
                self.after(0, lambda: self.status_var.set("❌ Session expired. Please log in again."))
                return False, f"Session expired and re-login failed: {emsg}"
            self._log("✅ Auto re-login successful.")
            r2 = self._get(srch)
            if self._is_login_page(r2):
                return False, "Session expired during search."

        nc = extract_csrf(r2.text)
        if nc:
            csrf = nc

        fid, creation_date = self._find_fulfillment_details(r2.text, d["vendor"])
        if not fid:
            # Write a debug preview of the page so the user can see what's happening
            try:
                doc_dir = os.path.join(os.path.expanduser("~"), "Documents", "DisputeFiller")
                os.makedirs(doc_dir, exist_ok=True)
                debug_path = os.path.join(doc_dir, f"debug_order_{clean_id}.html")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(r2.text)
                self._log(f"📝 Debug preview saved to: {debug_path}")
            except Exception as e:
                self._log(f"⚠️ Failed to write debug preview: {e}")
            self._log(f"⚠️ Search HTTP {r2.status_code} | Len: {len(r2.text)} | Query: order_name=%23{clean_id}")
            return False, f"No fulfillment found matching vendor '{d['vendor']}'."
        self._log(f"🎯 Fulfillment {fid} matched — '{d['vendor']}'")

        # ── Step 3: POST dispute form ────────────────────────────────────────
        self._log("📤 [3/3] Submitting form…")
        payload = {
            "utf8":                              "✓",
            "authenticity_token":               csrf,
            "order_dispute[fulfillment_id]":    fid,
            "order_dispute[fault_by]":          "quality_control",
            # fault_by_user_id → SKIP per spec
            "order_dispute[fault_severity]":    d["severity"],
            "order_dispute[original_quantity]": d["totalQty"],
            "order_dispute[fault_quantity]":    d["faultQty"],
            "order_dispute[dispute_reason]":    "quality",
            "order_dispute[chargeable_to]":     "vendor",
            "order_dispute[charge_to_vendor]":  "0.0",
            # correction_reasons → SKIP per spec
            "order_dispute[comment]":           d["comment"],
            "order_dispute[status]":            "awaiting_response_from_vendor",
            "location_id":                      lId,
            "order_name":                       f"#{d['orderId']}",
            "commit":                           "Create Order dispute",
        }
        r3 = self._post(f"/manage/vendors/{vId}/order_disputes", payload)
        if r3 is None:
            return False, "Network error on form submission."

        if r3.status_code in (200, 302):
            self._log("💎 Dispute created!")
            # Step 2 status message — Dispute created
            self.after(0, lambda oid=d['orderId']: self.status_var.set(
                f"✅ #{oid} — Dispute created"))
            if not creation_date:
                creation_date = datetime.now().strftime("%d/%m/%Y")
                self._log("⚠️ Could not parse 'Created on' date, falling back to current date.")
            self._sync_slide_date(d, creation_date, d['orderId'])
            return True, f"HTTP {r3.status_code}"
        else:
            preview = r3.text[:200].replace("\n", " ")
            return False, f"HTTP {r3.status_code} — {preview}"

    # ── Fulfillment Details matcher ───────────────────────────────────────────
    def _find_fulfillment_details(self, html, vendor):
        """Find radio button value and Created On date in the row matching the vendor name.
        Falls back to the first row's radio and date if no vendor match is found."""
        rows = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html, re.I)
        vl = vendor.lower()

        def parse_row_date(row_html):
            # Look for date format like "May 04, 2026" or "May 4, 2026"
            date_m = re.search(r'([a-zA-Z]+)\s+(\d{1,2}),\s+(\d{4})', row_html)
            if date_m:
                mon_name, day_str, year_str = date_m.groups()
                months = {
                    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
                    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
                    "july": 7, "august": 8, "september": 9, "october": 10,
                    "november": 11, "december": 12
                }
                mon_val = months.get(mon_name.lower())
                if mon_val:
                    return f"{int(day_str):02d}/{mon_val:02d}/{year_str}"
            return ""

        # 1. Try to find a row matching the vendor name
        for row in rows:
            if vl in row.lower():
                m = re.search(
                    r'name=["\']order_dispute\[fulfillment_id\]["\'][^>]*'
                    r'value=["\'](\d+)["\']', row, re.I)
                if not m:
                    m = re.search(
                        r'value=["\'](\d+)["\'][^>]*'
                        r'name=["\']order_dispute\[fulfillment_id\]',
                        row, re.I)
                if m:
                    return m.group(1), parse_row_date(row)

        # 2. Fallback: search row-by-row for any valid radio button
        for row in rows:
            m = re.search(
                r'name=["\']order_dispute\[fulfillment_id\]["\'][^>]*'
                r'value=["\'](\d+)["\']', row, re.I)
            if not m:
                m = re.search(
                    r'value=["\'](\d+)["\'][^>]*'
                    r'name=["\']order_dispute\[fulfillment_id\]',
                    row, re.I)
            if not m:
                m = re.search(r'type=["\']radio["\'][^>]*value=["\'](\d+)["\']', row, re.I)
            if not m:
                m = re.search(r'value=["\'](\d+)["\'][^>]*type=["\']radio["\']', row, re.I)
            if m:
                return m.group(1), parse_row_date(row)

        # 3. Last resort fallback (global search)
        m = re.search(
            r'order_dispute\[fulfillment_id\][^>]*value=["\'](\d+)["\']', html, re.I)
        if not m:
            m = re.search(
                r'value=["\'](\d+)["\'][^>]*order_dispute\[fulfillment_id\]', html, re.I)
        if not m:
            m = re.search(r'type=["\']radio["\'][^>]*value=["\'](\d+)["\']', html, re.I)

        fid = m.group(1) if m else ""
        return fid, parse_row_date(html)

    # ── Duplicate checker ─────────────────────────────────────────────────────
    def _is_duplicate(self, vId, lId, order_id):
        try:
            # Ensure the order ID starts with '#' as Tista expects
            tista_order_id = order_id if order_id.startswith("#") else f"#{order_id}"
            
            path = f"/manage/vendors/{vId}/order_disputes"
            params = {
                "q[id_or_fulfillment_order_order_name_eq]": tista_order_id,
                "q[location_id_eq]": "",          # Search across "All" locations
                "q[fault_by_eq]": "1",            # Filter Fault by: Quality Control
                "q[dispute_reason_eq]": "4",      # Filter Dispute reason: Quality
                "q[status_eq]": ""                # Search across all statuses
            }
            
            r = self._get(path, params=params)
            if self._is_login_page(r):
                self._log("⚠️ Session expired during duplicate check — re-logging in…")
                ok, emsg = self._tista_login(self.email_var.get(), self.pass_var.get())
                if ok:
                    r = self._get(path, params=params)
                else:
                    self._log(f"❌ Auto re-login failed during duplicate check: {emsg}")
                    return False

            if r and r.status_code == 200:
                html_text = r.text
                
                # 1. Immediate empty-state validation using Tista's exact messages
                if "no disputes found" in html_text.lower() or "try adjusting your filters" in html_text.lower():
                    return False
                    
                # 2. Extract table body
                tbody_match = re.search(r'<tbody[^>]*>([\s\S]*?)</tbody>', html_text, re.I)
                if tbody_match:
                    tbody_content = tbody_match.group(1)
                    # 3. Match Order ID only if it is the sole content of an HTML tag (e.g., <td>#442804</td>)
                    clean_id = tista_order_id.replace("#", "")
                    return bool(re.search(rf'>\s*#?{re.escape(clean_id)}\s*<', tbody_content, re.I))
        except Exception as e:
            self._log(f"⚠️ Error checking duplicate: {str(e)[:50]}")
        return False

    def _copy_id_to_clipboard(self, window, order_id):
        """Copies the formatted order ID (with #) to the system clipboard."""
        val = f"#{order_id}"
        try:
            window.clipboard_clear()
            window.clipboard_append(val)
            window.update()  # Required for some platforms to persist clipboard
        except Exception:
            pass

    # ── Date Range Parser ─────────────────────────────────────────────────────
    def _parse_date_from_title(self, title: str):
        """Extract a Tista-compatible date filter string from a presentation title.

        Supports titles like:
          'Audit Report Week - 3 ( 13 - 19 July , 2026)'
          'QC Report ( 1 - 7 August , 2026)'

        Returns:  'DD/MM/YY - DD/MM/YY'  e.g. '13/07/26 - 19/07/26'
        Returns:  None  if parsing fails.
        """
        MONTHS = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "jun": 6, "jul": 7, "aug": 8, "sep": 9,
            "oct": 10, "nov": 11, "dec": 12,
        }
        # Pattern: ( start_day - end_day  MonthName , YYYY )
        m = re.search(
            r'\(\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s*,\s*(\d{4})\s*\)',
            title)
        if not m:
            return None
        start_day, end_day, month_str, year_str = m.groups()
        mon_val = MONTHS.get(month_str.lower())
        if not mon_val:
            return None
        yy = year_str[-2:]   # 2026 → 26
        s = f"{int(start_day):02d}/{mon_val:02d}/{yy}"
        e = f"{int(end_day):02d}/{mon_val:02d}/{yy}"
        return f"{s} - {e}"

    # ── Tista Date Range Audit ────────────────────────────────────────────────
    def _fetch_tista_order_ids_for_range(self, vId, lId, filter_str):
        """Query Tista with Quality + QC + date-range filters.

        Returns a set of order ID strings (without '#') found on Tista
        for the given date range, or None on network/parse failure.
        """
        try:
            path = f"/manage/vendors/{vId}/order_disputes"
            params = {
                "q[fault_by_eq]":       "1",          # Quality Control
                "q[dispute_reason_eq]": "4",          # Quality
                "q[fault_at_between]":  filter_str,   # e.g. "13/07/26 - 19/07/26"
                "q[status_eq]":         ""            # Search across all statuses
            }
            r = self._get(path, params=params)
            if r is None or r.status_code != 200:
                return None

            html = r.text
            # Extract all #XXXXXX order IDs from table cells
            ids = set(re.findall(r'<td[^>]*>\s*#(\d+)\s*</td>', html, re.I))
            # Also check for order IDs in anchor tags inside table cells
            ids |= set(re.findall(r'>\s*#(\d+)\s*<', html, re.I))
            self._log(f"🔍 Tista audit: {len(ids)} dispute(s) found for {filter_str}")
            return ids
        except Exception as e:
            self._log(f"⚠️ Audit fetch error: {str(e)[:80]}")
            return None

    # ── Tista Dispute Deletion Backend Flow ──────────────────────────────────
    def _delete_tista_dispute_endpoint(self, vId, order_id):
        """Automated 2-step dispute deletion on Tista:
        1. Search for dispute to extract dispute_id and CSRF token.
        2. PATCH status to 'under_review'.
        3. DELETE the dispute.
        
        Returns: (True, "") on success, or (False, error_msg) on failure.
        """
        try:
            # Step 1: Search the order ID to get dispute ID and CSRF
            tista_order_id = order_id if order_id.startswith("#") else f"#{order_id}"
            path = f"/manage/vendors/{vId}/order_disputes"
            params = {
                "q[id_or_fulfillment_order_order_name_eq]": tista_order_id,
                "q[status_eq]": "",  # Search in All statuses
            }
            r1 = self._get(path, params=params)
            if r1 is None or r1.status_code != 200:
                return False, "Failed to connect to Tista dispute search."
            
            # Find Edit link with dispute ID
            m = re.search(r'/manage/vendors/\d+/order_disputes/(\d+)/edit', r1.text, re.I)
            if not m:
                return False, "Dispute edit link/ID not found. It might be already deleted."
            dispute_id = m.group(1)
            
            csrf = extract_csrf(r1.text)
            if not csrf:
                return False, "CSRF token not found on dispute list page."
            
            # Step 2: PATCH status to under_review
            self._log(f"🔄 Updating dispute #{order_id} (ID: {dispute_id}) to Under review...")
            update_path = f"/manage/vendors/{vId}/order_disputes/{dispute_id}"
            payload_patch = {
                "_method": "patch",
                "authenticity_token": csrf,
                "order_dispute[status]": "under_review",
                "commit": "Update Order dispute"
            }
            
            r2 = self._post(update_path, payload_patch)
            if r2 is None or r2.status_code not in (200, 302):
                return False, f"Failed to update status to Under review (HTTP {r2.status_code if r2 else 'None'})."
                
            csrf2 = extract_csrf(r2.text) if r2 else ""
            if csrf2:
                csrf = csrf2
                
            # Step 3: DELETE the dispute
            self._log(f"🗑️ Deleting dispute #{order_id} (ID: {dispute_id})...")
            payload_delete = {
                "_method": "delete",
                "authenticity_token": csrf
            }
            r3 = self._post(update_path, payload_delete)
            if r3 is None or r3.status_code not in (200, 302):
                return False, f"Delete request failed (HTTP {r3.status_code if r3 else 'None'})."
            
            return True, ""
        except Exception as e:
            return False, str(e)

    # ── Slide date sync ───────────────────────────────────────────────────────
    def _sync_slide_date(self, d, new_date, order_id=None):
        """Replace old date in slide with dispute creation date."""
        old_date = d.get("date", "")
        slide_id = d.get("slideId", "")
        if not old_date or not slide_id or old_date == new_date:
            self._log(f"📅 Date sync skipped (old={old_date!r})")
            return
        if not self.presentation_id:
            return
        try:
            self.slides_service.presentations().batchUpdate(
                presentationId=self.presentation_id,
                body={
                    "requests": [{
                        "replaceAllText": {
                            "containsText": {
                                "text": old_date,
                                "matchCase": True},
                            "replaceText": new_date,
                            "pageObjectIds": [slide_id],
                        }
                    }]
                }
            ).execute()
            d["date"] = new_date
            self._log(f"📅 Slide date updated: {old_date} → {new_date}")
            # Step 3 status message — Date updated
            oid = order_id or d.get("orderId", "")
            self.after(0, lambda o=oid, nd=new_date, od=old_date: self.status_var.set(
                f"📅 #{o} — Slide date updated → {nd}"))
        except Exception as e:
            self._log(f"⚠️  Date sync failed: {str(e)[:100]}")

    # ── Table Clear ───────────────────────────────────────────────────────────
    def _clear_table(self):
        """Reset the dispute queue table to empty state."""
        for widget in self._scroll.winfo_children():
            widget.destroy()
        self.disputes = []
        self.row_widgets = []
        self.presentation_id = ""
        self.progress_bar.set(0)
        self.progress_var.set("0 / 0")
        self.status_var.set("Table cleared — paste a new Slides link and click Load.")
        self._empty_lbl = ctk.CTkLabel(
            self._scroll,
            text="No disputes loaded. Paste a Slides link and click Load.",
            font=ctk.CTkFont(family="Livvic", size=12), text_color="#666666")
        self._empty_lbl.pack(pady=22)

        # Clear slide links and reset UI description to defaults
        self.slides_link_var.set("")
        self._src_sub.configure(
            text="Click the 'Input Links' button to add order links.",
            text_color="#aaaaaa")

        # Remove temporary debug HTML files from workspace
        debug_files = ["debug_last_page.html", "debug_fulfillment_page.html"]
        for f_name in debug_files:
            try:
                path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f_name)
                if os.path.exists(path):
                    os.remove(path)
                    self._log(f"🧹 Removed temporary file: {f_name}")
            except Exception as e:
                self._log(f"⚠️ Failed to remove temporary file {f_name}: {e}")

        # Update saved configuration to persist the cleared slides link
        self._save_config(save_creds=self.keep_var.get())

    # ── Batch Duplicate Pre-flight ────────────────────────────────────────────
    def _batch_check_duplicates(self, vId, lId):
        """Concurrently checks all pending disputes for duplicates.
        Returns list of (idx, orderId, vendor) for each duplicate found."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        duplicates = []
        pending = [
            (i, d) for i, d in enumerate(self.disputes)
            if "Skipped" not in self.row_widgets[i]["status_lbl"].cget("text")
        ]
        with ThreadPoolExecutor(max_workers=5) as pool:
            future_to = {
                pool.submit(self._is_duplicate, vId, lId, d["orderId"]): (i, d)
                for i, d in pending
            }
            for future in as_completed(future_to):
                i, d = future_to[future]
                try:
                    if future.result():
                        duplicates.append((i, d["orderId"], d["vendor"]))
                except Exception:
                    pass
        # Sort by original row index for consistent display
        duplicates.sort(key=lambda x: x[0])
        return duplicates

    # ── Link Paste Modal Helper ───────────────────────────────────────────────
    def _on_link_btn_click(self):
        """Open a modal popup to paste/edit Google Slides links (one per line)."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Paste Slides Links")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        w, h = 400, 260
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        f = ctk.CTkFrame(dialog, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            f, text="Google Slides Links:",
            font=ctk.CTkFont(family="Livvic", size=12, weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        # Multi-line textbox for links (one per line)
        links_box = ctk.CTkTextbox(
            f, fg_color=C_BG, text_color=C_TEXT, border_color="#00d2ff", border_width=2,
            height=120, corner_radius=8, font=ctk.CTkFont(family="Livvic", size=12))
        links_box.pack(fill="x", pady=(0, 10))
        links_box.focus_set()

        def do_load(event=None):
            raw = links_box.get("0.0", "end").strip()
            lines = [l.strip() for l in raw.split("\n") if l.strip()]
            if not lines:
                return
            self.slides_link_var.set("\n".join(lines))
            dialog.destroy()
            self._start_load_slides()

        # Bind Ctrl+Enter to submit (Enter adds newline in textbox)
        links_box.bind("<Control-Return>", do_load)

        # Buttons side-by-side
        btn_row = ctk.CTkFrame(f, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_row, text="Load", corner_radius=15,
            fg_color=C_PRIMARY, hover_color=C_PRIMARY_H,
            font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
            height=32, text_color=C_PRIMARY_T,
            command=do_load
        ).grid(row=0, column=0, padx=(0, 4), sticky="ew")

        ctk.CTkButton(
            btn_row, text="Cancel", corner_radius=15,
            fg_color=C_BTN_WHITE, hover_color=C_BTN_WHITE_H,
            font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
            height=32, text_color=C_BTN_WHITE_T,
            command=dialog.destroy
        ).grid(row=0, column=1, padx=(4, 0), sticky="ew")

    # ── Duplicate Summary Popup ───────────────────────────────────────────────
    def _show_dup_summary_popup(self, duplicates, new_disputes, skip_indices, vId, lId, extra_on_tista=None):
        """Single summary popup listing all duplicate orders and new orders side-by-side with 3 action choices.
        If extra_on_tista is provided, displays a third section showing disputes on Tista that are not in slides."""
        choice = [None]   # "skip", "all", "cancel"
        evt = threading.Event()

        def build_popup():
            num_dup = len(duplicates)
            num_new = len(new_disputes)
            num_extra = len(extra_on_tista) if extra_on_tista else 0
            total = num_dup + num_new
            extra_col = None
            w = 500
            h = 580 if num_extra > 0 else 450
            h_scroll = 100 if num_extra > 0 else 160
            dialog = ctk.CTkToplevel(self)
            dialog.title("⚠️ Duplicates & New Disputes")
            dialog.resizable(False, False)
            dialog.transient(self)
            dialog.grab_set()
            x = (self.winfo_screenwidth() // 2) - (w // 2)
            y = (self.winfo_screenheight() // 2) - (h // 2)
            dialog.geometry(f"{w}x{h}+{x}+{y}")

            f = ctk.CTkFrame(dialog, fg_color="transparent")
            f.pack(fill="both", expand=True, padx=20, pady=(16, 20))

            # Header label defined early so deletion helper can modify it
            header_text = f"⚠️  {num_dup} duplicate{'s' if num_dup != 1 else ''} and {num_new} new dispute{'s' if num_new != 1 else ''} found"
            if num_extra > 0:
                header_text += f" | {num_extra} extra on Tista"
            header_lbl = ctk.CTkLabel(
                f, text=header_text,
                font=ctk.CTkFont(family="Livvic", size=14, weight="bold"),
                text_color=C_ORANGE
            )
            header_lbl.pack(anchor="w", pady=(0, 10))

            # Two Column Container
            cols_frame = ctk.CTkFrame(f, fg_color="transparent")
            cols_frame.pack(fill="both", expand=False, pady=(0, 10))
            cols_frame.grid_columnconfigure((0, 1), weight=1, uniform="col")

            # Left Column: Duplicates
            dup_col = ctk.CTkFrame(cols_frame, fg_color=C_BG, corner_radius=10, border_color=C_BORDER, border_width=1)
            dup_col.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
            
            ctk.CTkLabel(
                dup_col, text="Duplicate Disputes",
                font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
                text_color=C_ORANGE
            ).pack(anchor="w", padx=10, pady=(8, 2))
            
            ctk.CTkLabel(
                dup_col, text="(Already Created)",
                font=ctk.CTkFont(family="Livvic", size=10),
                text_color="#888888"
            ).pack(anchor="w", padx=10, pady=(0, 6))

            dup_scroll = ctk.CTkScrollableFrame(dup_col, fg_color="transparent", corner_radius=0, height=h_scroll)
            dup_scroll.pack(fill="both", expand=True, padx=5, pady=(0, 8))

            if duplicates:
                for _, oid, vendor in duplicates:
                    vn = (vendor[:18] + "…") if len(vendor) > 18 else vendor

                    # Row frame: holds the label + inline tooltip side by side
                    row_frame = ctk.CTkFrame(dup_scroll, fg_color="transparent")
                    row_frame.pack(anchor="w", fill="x", pady=1, padx=5)

                    lbl = ctk.CTkLabel(
                        row_frame, text=f"• #{oid} — {vn}",
                        font=ctk.CTkFont(family="Livvic", size=11),
                        text_color="#ffb380", anchor="w",
                        cursor="hand2"
                    )
                    lbl.pack(side="left")

                    # Placeholder dict to hold the tooltip reference per row
                    _tip = {"widget": None, "after_id": None}

                    def _on_click(e, o_id=oid, d_win=dialog, rf=row_frame, tip=_tip, lb=lbl):
                        # Copy to clipboard
                        self._copy_id_to_clipboard(d_win, o_id)
                        # Cancel any existing tooltip auto-dismiss
                        if tip["after_id"] is not None:
                            try:
                                rf.after_cancel(tip["after_id"])
                            except Exception:
                                pass
                        # Destroy existing tooltip if present
                        if tip["widget"] is not None:
                            try:
                                tip["widget"].destroy()
                            except Exception:
                                pass
                        # Create floating tooltip using CTkToplevel (above everything, no clipping)
                        tooltip = ctk.CTkToplevel(d_win)
                        tooltip.overrideredirect(True)  # No window decorations
                        tooltip.attributes("-topmost", True)  # Stay on top
                        # Position above the label
                        x = lb.winfo_rootx() + lb.winfo_width() // 2
                        y = lb.winfo_rooty() - 30
                        tooltip.geometry(f"+{x}+{y}")
                        badge = ctk.CTkLabel(
                            tooltip, text="✅ Copied!",
                            font=ctk.CTkFont(family="Livvic", size=10, weight="bold"),
                            text_color="#ffffff",
                            fg_color="#1a7a40",
                            corner_radius=8,
                            padx=8, pady=4
                        )
                        badge.pack()
                        tip["widget"] = tooltip
                        # Auto-dismiss after 1500ms
                        def _dismiss(t=tip, lb2=lb):
                            if t["widget"] is not None:
                                try:
                                    t["widget"].destroy()
                                except Exception:
                                    pass
                                t["widget"] = None
                                t["after_id"] = None
                            try:
                                lb2.configure(text_color="#ffb380")
                            except Exception:
                                pass
                        tip["after_id"] = rf.after(1500, _dismiss)
                        lbl.configure(text_color="#ffffff")

                    lbl.bind("<Enter>", lambda e, l=lbl: l.configure(text_color="#ffffff"))
                    lbl.bind("<Leave>", lambda e, l=lbl, t=_tip: l.configure(text_color="#ffb380") if t["widget"] is None else None)
                    lbl.bind("<Button-1>", _on_click)
            else:
                ctk.CTkLabel(
                    dup_scroll, text="None",
                    font=ctk.CTkFont(family="Livvic", size=11),
                    text_color="#888888", anchor="w"
                ).pack(anchor="w", pady=10, padx=5)

            # Right Column: New
            new_col = ctk.CTkFrame(cols_frame, fg_color=C_BG, corner_radius=10, border_color=C_BORDER, border_width=1)
            new_col.grid(row=0, column=1, padx=(6, 0), sticky="nsew")

            ctk.CTkLabel(
                new_col, text="New Disputes",
                font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
                text_color=C_GREEN
            ).pack(anchor="w", padx=10, pady=(8, 2))
            
            ctk.CTkLabel(
                new_col, text="(To Be Created)",
                font=ctk.CTkFont(family="Livvic", size=10),
                text_color="#888888"
            ).pack(anchor="w", padx=10, pady=(0, 6))

            new_scroll = ctk.CTkScrollableFrame(new_col, fg_color="transparent", corner_radius=0, height=h_scroll)
            new_scroll.pack(fill="both", expand=True, padx=5, pady=(0, 8))

            if new_disputes:
                for _, oid, vendor in new_disputes:
                    vn = (vendor[:18] + "…") if len(vendor) > 18 else vendor
                    lbl = ctk.CTkLabel(
                        new_scroll, text=f"• #{oid} — {vn}",
                        font=ctk.CTkFont(family="Livvic", size=11),
                        text_color="#c8ffc8", anchor="w", cursor="hand2"
                    )
                    lbl.pack(anchor="w", pady=1, padx=5)

                    # Click-to-copy tooltip (same as duplicate column)
                    _tip = {"widget": None, "after_id": None}
                    def _copy_new(e, o_id=oid, lb=lbl, rf=new_scroll, tip=_tip, d_win=dialog):
                        self._copy_id_to_clipboard(d_win, o_id)
                        if tip["after_id"]:
                            try:
                                rf.after_cancel(tip["after_id"])
                            except Exception:
                                pass
                        if tip["widget"]:
                            try:
                                tip["widget"].destroy()
                            except Exception:
                                pass
                        tooltip = ctk.CTkToplevel(d_win)
                        tooltip.overrideredirect(True)
                        tooltip.attributes("-topmost", True)
                        x = lb.winfo_rootx() + lb.winfo_width() // 2
                        y = lb.winfo_rooty() - 30
                        tooltip.geometry(f"+{x}+{y}")
                        badge = ctk.CTkLabel(
                            tooltip, text="✅ Copied!",
                            font=ctk.CTkFont(family="Livvic", size=10, weight="bold"),
                            text_color="#ffffff", fg_color="#1a7a40", corner_radius=8, padx=8, pady=4
                        )
                        badge.pack()
                        tip["widget"] = tooltip
                        def _dismiss(t=tip, lb2=lb):
                            if t["widget"]:
                                try:
                                    t["widget"].destroy()
                                except Exception:
                                    pass
                                t["widget"] = None
                                t["after_id"] = None
                            try:
                                lb2.configure(text_color="#c8ffc8")
                            except Exception:
                                pass
                        tip["after_id"] = rf.after(1500, _dismiss)
                        lbl.configure(text_color="#ffffff")

                    lbl.bind("<Button-1>", _copy_new)
                    lbl.bind("<Enter>", lambda e, l=lbl: l.configure(text_color="#ffffff"))
                    lbl.bind("<Leave>", lambda e, l=lbl, t=_tip: l.configure(text_color="#c8ffc8") if t["widget"] is None else None)
            else:
                ctk.CTkLabel(
                    new_scroll, text="None",
                    font=ctk.CTkFont(family="Livvic", size=11),
                    text_color="#888888", anchor="w"
                ).pack(anchor="w", pady=10, padx=5)

            # Dictionary to track row widgets for extra disputes dynamically
            extra_row_widgets = {}

            # Click handler to delete a single extra dispute
            def on_delete_click(oid):
                if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete dispute for Order #{oid}?", parent=dialog):
                    return
                
                # Disable buttons
                extra_row_widgets[oid]["btn"].configure(state="disabled", text="Deleting...")
                delete_all_btn.configure(state="disabled")
                
                def run_del():
                    ok, msg = self._delete_tista_dispute_endpoint(vId, oid)
                    if ok:
                        self._log(f"✅ Deleted dispute for Order #{oid} on Tista.")
                        def success_ui():
                            if oid in extra_row_widgets:
                                extra_row_widgets[oid]["frame"].destroy()
                                del extra_row_widgets[oid]
                            
                            # Remove from data list
                            for item in list(extra_on_tista):
                                if item[0] == oid:
                                    extra_on_tista.remove(item)
                                    break
                            
                            # Update header text
                            num_extra = len(extra_on_tista)
                            new_text = f"⚠️  {num_dup} duplicate{'s' if num_dup != 1 else ''} and {num_new} new dispute{'s' if num_new != 1 else ''} found"
                            if num_extra > 0:
                                new_text += f" | {num_extra} extra on Tista"
                            header_lbl.configure(text=new_text)
                            
                            # If no more extras, destroy card and shrink popup window
                            if num_extra == 0:
                                extra_col.destroy()
                                dialog.geometry(f"500x450")
                            else:
                                delete_all_btn.configure(state="normal")
                        self.after(0, success_ui)
                    else:
                        self._log(f"❌ Failed to delete dispute #{oid}: {msg}")
                        def fail_ui():
                            if oid in extra_row_widgets:
                                extra_row_widgets[oid]["btn"].configure(state="normal", text="Delete")
                            delete_all_btn.configure(state="normal")
                            messagebox.showerror("Error", f"Failed to delete dispute #{oid}:\n{msg}", parent=dialog)
                        self.after(0, fail_ui)
                        
                threading.Thread(target=run_del, daemon=True).start()

            # Click handler to delete all extra disputes sequentially
            def on_delete_all_click():
                num_to_delete = len(extra_on_tista)
                if not messagebox.askyesno("Confirm Delete All", f"Are you sure you want to delete all {num_to_delete} extra disputes from Tista?", parent=dialog):
                    return
                
                # Disable Delete All and all row delete buttons
                delete_all_btn.configure(state="disabled")
                for oid in list(extra_row_widgets.keys()):
                    extra_row_widgets[oid]["btn"].configure(state="disabled", text="Deleting...")
                
                def run_del_all():
                    to_delete = list(extra_row_widgets.keys())
                    for oid in to_delete:
                        ok, msg = self._delete_tista_dispute_endpoint(vId, oid)
                        if ok:
                            self._log(f"✅ Deleted dispute for Order #{oid} on Tista.")
                            def success_ui(o_id=oid):
                                if o_id in extra_row_widgets:
                                    extra_row_widgets[o_id]["frame"].destroy()
                                    del extra_row_widgets[o_id]
                                for item in list(extra_on_tista):
                                    if item[0] == o_id:
                                        extra_on_tista.remove(item)
                                        break
                                # Update header
                                num_extra = len(extra_on_tista)
                                new_text = f"⚠️  {num_dup} duplicate{'s' if num_dup != 1 else ''} and {num_new} new dispute{'s' if num_new != 1 else ''} found"
                                if num_extra > 0:
                                    new_text += f" | {num_extra} extra on Tista"
                                header_lbl.configure(text=new_text)
                                
                                if num_extra == 0:
                                    extra_col.destroy()
                                    dialog.geometry(f"500x450")
                            self.after(0, success_ui)
                        else:
                            self._log(f"❌ Failed to delete dispute #{oid}: {msg}")
                            def fail_ui(o_id=oid):
                                if o_id in extra_row_widgets:
                                    extra_row_widgets[o_id]["btn"].configure(state="normal", text="Delete")
                            self.after(0, fail_ui)
                    
                    def finish_del_all():
                        if len(extra_on_tista) > 0:
                            delete_all_btn.configure(state="normal")
                    self.after(0, finish_del_all)
                    
                threading.Thread(target=run_del_all, daemon=True).start()

            # Bottom Row: Extra Disputes on Tista (Not in Slides)
            if num_extra > 0:
                extra_col = ctk.CTkFrame(f, fg_color=C_BG, corner_radius=10, border_color=C_BORDER, border_width=1)

                # Header container to hold Title and Delete All button
                extra_hdr = ctk.CTkFrame(extra_col, fg_color="transparent")
                extra_hdr.pack(fill="x", padx=10, pady=(8, 2))

                ctk.CTkLabel(
                    extra_hdr, text="Extra Disputes on Tista",
                    font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
                    text_color=C_RED
                ).pack(side="left")
                
                # Delete All Extra Button
                delete_all_btn = ctk.CTkButton(
                    extra_hdr, text="🗑️ Delete All",
                    width=80, height=22, corner_radius=11,
                    fg_color=C_RED, hover_color=C_RED_H,
                    font=ctk.CTkFont(family="Livvic", size=10, weight="bold"),
                    text_color="#ffffff",
                    command=on_delete_all_click
                )
                delete_all_btn.pack(side="right")
                
                ctk.CTkLabel(
                    extra_col, text="  (Not in Slides - Click to Copy #)",
                    font=ctk.CTkFont(family="Livvic", size=10),
                    text_color="#888888"
                ).pack(anchor="w", padx=10, pady=(0, 6))

                extra_scroll = ctk.CTkScrollableFrame(extra_col, fg_color="transparent", corner_radius=0, height=80)
                extra_scroll.pack(fill="x", padx=5, pady=(0, 8))

                for oid, _ in extra_on_tista:
                    row_f = ctk.CTkFrame(extra_scroll, fg_color="transparent")
                    row_f.pack(anchor="w", fill="x", pady=1, padx=5)

                    lbl = ctk.CTkLabel(
                        row_f, text=f"• #{oid}",
                        font=ctk.CTkFont(family="Livvic", size=11),
                        text_color="#ff9999", anchor="w", cursor="hand2"
                    )
                    lbl.pack(side="left")

                    # Copy to clipboard action
                    _tip = {"widget": None, "after_id": None}
                    def _copy_extra(e, o_id=oid, lb=lbl, rf=extra_scroll, tip=_tip, d_win=dialog):
                        self._copy_id_to_clipboard(d_win, o_id)
                        if tip["after_id"]:
                            try:
                                rf.after_cancel(tip["after_id"])
                            except Exception:
                                pass
                        if tip["widget"]:
                            try:
                                tip["widget"].destroy()
                            except Exception:
                                pass
                        tooltip = ctk.CTkToplevel(d_win)
                        tooltip.overrideredirect(True)
                        tooltip.attributes("-topmost", True)
                        x = lb.winfo_rootx() + lb.winfo_width() // 2
                        y = lb.winfo_rooty() - 30
                        tooltip.geometry(f"+{x}+{y}")
                        badge = ctk.CTkLabel(
                            tooltip, text="✅ Copied!",
                            font=ctk.CTkFont(family="Livvic", size=10, weight="bold"),
                            text_color="#ffffff", fg_color="#1a7a40", corner_radius=8, padx=8, pady=4
                        )
                        badge.pack()
                        tip["widget"] = tooltip
                        def _dismiss(t=tip, lb2=lb):
                            if t["widget"]:
                                try:
                                    t["widget"].destroy()
                                except Exception:
                                    pass
                                t["widget"] = None
                                t["after_id"] = None
                            try:
                                lb2.configure(text_color="#ff9999")
                            except Exception:
                                pass
                        tip["after_id"] = rf.after(1500, _dismiss)
                        lbl.configure(text_color="#ffffff")

                    lbl.bind("<Button-1>", _copy_extra)
                    lbl.bind("<Enter>", lambda e, l=lbl: l.configure(text_color="#ffffff"))
                    lbl.bind("<Leave>", lambda e, l=lbl, t=_tip: l.configure(text_color="#ff9999") if t["widget"] is None else None)

                    # Dynamic delete button per extra dispute row
                    del_btn = ctk.CTkButton(
                        row_f, text="Delete",
                        width=50, height=18, corner_radius=9,
                        fg_color="#E55050", hover_color="#B33E3E",
                        font=ctk.CTkFont(family="Livvic", size=9, weight="bold"),
                        text_color="#ffffff",
                        command=lambda o=oid: on_delete_click(o)
                    )
                    del_btn.pack(side="right", padx=10)
                    
                    # Store widgets
                    extra_row_widgets[oid] = {"frame": row_f, "btn": del_btn, "lbl": lbl}



            # Summary stats label
            stats_lbl = ctk.CTkLabel(
                f, text=f"Total: {total} | Duplicates: {num_dup} | New: {num_new}",
                font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
                text_color="#aaaaaa"
            )
            stats_lbl.pack(pady=(5, 10))

            def do(action):
                choice[0] = action
                dialog.destroy()
                evt.set()

            # Side-by-side buttons
            btn_row = ctk.CTkFrame(f, fg_color="transparent")
            btn_row.pack(fill="x")
            btn_row.grid_columnconfigure((0, 1), weight=1)

            ctk.CTkButton(
                btn_row, text="Submit All",
                height=36, corner_radius=18,
                fg_color="#555555", hover_color="#666666",
                font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
                text_color="#ffffff",
                command=lambda: do("all")
            ).grid(row=0, column=0, padx=(0, 4), sticky="ew")

            ctk.CTkButton(
                btn_row, text="Submit New",
                height=36, corner_radius=18,
                fg_color=C_PRIMARY, hover_color=C_PRIMARY_H,
                font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
                text_color=C_PRIMARY_T,
                command=lambda: do("skip")
            ).grid(row=0, column=1, padx=(4, 0), sticky="ew")

            if num_extra > 0:
                extra_col.pack(fill="x", pady=(5, 10))

            dialog.protocol("WM_DELETE_WINDOW", lambda: do("cancel"))

        self.after(0, build_popup)
        evt.wait(timeout=120)

        if choice[0] == "skip":
            for idx, oid, vendor in duplicates:
                skip_indices.add(idx)
                self._set_row_status(idx, "⏭ Skipped", "#ffcc00", btn_en=True)
                self._log(f"⏭ #{oid} — Skipped (duplicate).")
            threading.Thread(
                target=self._submit_all_thread, args=(skip_indices, vId, lId), daemon=True).start()
        elif choice[0] == "all":
            threading.Thread(
                target=self._submit_all_thread, args=(set(), vId, lId), daemon=True).start()
        else:
            # Cancel — reset buttons
            self.submitting_all = False
            self.after(0, lambda: self._submit_all_btn.configure(state="normal", text="🚀 Submit All"))
            self._update_action_btn()
            self.after(0, lambda: self._set_all_row_btns_state(True))
            self.after(0, lambda: self.status_var.set("Cancelled."))

    # ── Submit All Logic ──────────────────────────────────────────────────────
    def _on_submit_all_click(self):
        if not self.disputes:
            messagebox.showwarning("No Disputes", "There are no disputes to process.", parent=self)
            return
        if self.submitting_all:
            return

        # Option C: Reset all "Skipped" rows back to "Pending" before re-scanning
        skipped_order_ids = []
        for i, rw in enumerate(self.row_widgets):
            status_text = rw["status_lbl"].cget("text")
            if "Skipped" in status_text:
                oid = self.disputes[i]["orderId"]
                skipped_order_ids.append(oid)
                self._set_row_status(i, "Pending", "#888888", btn_en=True)

        # Clear log entries for those skipped orders
        if skipped_order_ids:
            self._clear_log_entries(skipped_order_ids)

        self.submitting_all = True
        self._set_all_row_btns_state(False)
        self.stop_all_flag.clear()
        self._submit_all_btn.configure(state="disabled", text="Scanning…")
        self._update_action_btn()
        self.status_var.set("🔍 Scanning all disputes for duplicates…")

        vId = self.vendor_id_var.get().strip()
        lId = self.location_id_var.get().strip()

        def preflight():
            try:
                self._log("🔍 Pre-flight duplicate scan started…")
                duplicates = self._batch_check_duplicates(vId, lId)

                # ── Date range audit ──────────────────────────────────────────
                extra_on_tista = []   # list of (order_id_str, vendor_str)
                if self.audit_date_filter:
                    self.after(0, lambda: self.status_var.set(
                        f"🔍 Auditing Tista for date range {self.audit_date_filter}…"))
                    self._log(f"🔍 Fetching Tista disputes for range: {self.audit_date_filter}")
                    tista_ids = self._fetch_tista_order_ids_for_range(
                        vId, lId, self.audit_date_filter)
                    if tista_ids is not None:
                        slide_ids = {d["orderId"] for d in self.disputes}
                        extra_ids = tista_ids - slide_ids
                        if extra_ids:
                            extra_on_tista = sorted(
                                [(oid, "") for oid in extra_ids],
                                key=lambda x: x[0])
                            self._log(
                                f"⚠️ Audit: {len(extra_ids)} extra dispute(s) on Tista not in slides: "
                                + ", ".join(f"#{x[0]}" for x in extra_on_tista))
                        else:
                            self._log("✅ Audit: All Tista disputes accounted for in slides.")
                    else:
                        self._log("⚠️ Audit: Could not reach Tista for date range check.")
                else:
                    self._log("ℹ️ Audit: No date range found in presentation title — skipped.")

                # ── Always show popup when duplicates OR extra found ──────────
                pending = [
                    (i, d) for i, d in enumerate(self.disputes)
                    if "Skipped" not in self.row_widgets[i]["status_lbl"].cget("text")
                ]
                dup_indices = {item[0] for item in duplicates}
                new_disputes = [
                    (idx, d["orderId"], d["vendor"])
                    for idx, d in pending if idx not in dup_indices
                ]

                if duplicates or extra_on_tista:
                    if duplicates:
                        self._log(f"⚠️ Found {len(duplicates)} duplicate(s). Showing summary popup.")
                    self._show_dup_summary_popup(
                        duplicates, new_disputes, set(), vId, lId,
                        extra_on_tista=extra_on_tista)
                else:
                    self._log("✅ No duplicates found. Starting submission.")
                    self.after(0, lambda: self.status_var.set("✅ No duplicates — starting submission…"))
                    threading.Thread(
                        target=self._submit_all_thread, args=(set(), vId, lId), daemon=True).start()
            except Exception:
                self._log(f"💥 Pre-flight error:\n{traceback.format_exc()[-200:]}")
                self.submitting_all = False
                self._set_all_row_btns_state(True)
                self.after(0, lambda: self._submit_all_btn.configure(state="normal", text="🚀 Submit All"))
                self._update_action_btn()

        threading.Thread(target=preflight, daemon=True).start()

    def _update_action_btn(self):
        """Dynamic toggle between Clear and Stop Process based on app status."""
        def _do():
            if self.submitting_all or self.submit_lock.locked():
                self._action_btn.configure(
                    text="● Stop Process", fg_color="#444444",
                    hover_color="#ff4d4d", text_color="#888888",
                    state="normal", command=self._on_stop_click)
            else:
                self._action_btn.configure(
                    text="🗑 Clear", fg_color="#FFFFFF",
                    hover_color="#cccccc", text_color="#000000",
                    state="normal", command=self._clear_table)
        self.after(0, _do)

    def _on_stop_click(self):
        if not self.submitting_all:
            return
        self.stop_all_flag.set()
        self._action_btn.configure(state="disabled", text="Stopping…", text_color="#888888")
        self._log("🛑 Stop command sent. Waiting for current row to finish...")

    def _set_all_row_btns_state(self, enabled):
        state = "normal" if enabled else "disabled"
        for rw in self.row_widgets:
            rw["submit_btn"].configure(state=state)

    def _submit_all_thread(self, skip_indices, vId, lId):
        """Sequential submission worker. skip_indices is a set of row indices to bypass."""
        try:
            import time
            self.after(0, lambda: self._submit_all_btn.configure(text="Running…"))

            # Helper to update progress UI — cget() runs on main thread to stay thread-safe
            def _sync_progress_ui():
                def _update():
                    processed = sum(
                        1 for rw in self.row_widgets
                        if rw["status_lbl"].cget("text") not in ("Pending", "⟳ Running")
                    )
                    total = len(self.disputes)
                    self.progress_var.set(f"{processed} / {total}")
                    if total > 0:
                        self.progress_bar.set(processed / total)
                self.after(0, _update)

            # Sync initially to show skipped duplicates on the progress bar right away
            _sync_progress_ui()

            for idx, d in enumerate(self.disputes):
                # Always sync progress at the start of the loop to count skipped/completed rows
                _sync_progress_ui()

                if self.stop_all_flag.is_set():
                    self._log("🛑 Process stopped by user.")
                    break

                # Skip already-completed or pre-flagged rows
                current_text = self.row_widgets[idx]["status_lbl"].cget("text")
                if "Done" in current_text or "Skipped" in current_text:
                    continue

                # Skip duplicate rows decided in the pre-flight popup
                if idx in skip_indices:
                    continue

                self._set_row_status(idx, "⟳ Running", C_ORANGE, btn_en=False)
                self.after(0, lambda oid=d['orderId']: self.status_var.set(
                    f"🔍 #{oid} — Checking duplicates…"))

                ok, msg = self._run_submission(vId, lId, d, idx, skip_dup_check=True)

                if ok:
                    self._set_row_status(idx, "✅ Done", C_GREEN, btn_en=False)
                else:
                    if "Cancelled" in msg or "duplicate" in msg.lower():
                        self._set_row_status(idx, "⏭ Skipped", "#ffcc00", btn_en=True)
                        self.after(0, lambda oid=d['orderId']: self.status_var.set(
                            f"⏭ #{oid} — Skipped (already exists)"))
                    else:
                        self._set_row_status(idx, "❌ Error", C_RED, btn_en=True)
                        short = msg[:60]
                        self.after(0, lambda oid=d['orderId'], sh=short: self.status_var.set(
                            f"❌ #{oid} — {sh}"))

                # Final sync for the current iteration
                _sync_progress_ui()
                time.sleep(1.0)

            # Show success popup if the process completed without user stopping it
            if not self.stop_all_flag.is_set():
                def show_success():
                    # Calculate final stats
                    created = sum(1 for rw in self.row_widgets if "Done" in rw["status_lbl"].cget("text"))
                    skipped = sum(1 for rw in self.row_widgets if "Skipped" in rw["status_lbl"].cget("text"))
                    errors = sum(1 for rw in self.row_widgets if "Error" in rw["status_lbl"].cget("text"))

                    dialog = ctk.CTkToplevel(self)
                    dialog.title("Success")
                    dialog.resizable(False, False)
                    dialog.transient(self)
                    dialog.grab_set()

                    h = 240 if errors > 0 else 210
                    w = 320
                    x = (self.winfo_screenwidth() // 2) - (w // 2)
                    y = (self.winfo_screenheight() // 2) - (h // 2)
                    dialog.geometry(f"{w}x{h}+{x}+{y}")

                    f = ctk.CTkFrame(dialog, fg_color="transparent")
                    f.pack(fill="both", expand=True, padx=20, pady=20)

                    ctk.CTkLabel(
                        f, text="🎉 Submission Complete!",
                        font=ctk.CTkFont(family="Livvic", size=14, weight="bold"),
                        text_color=C_GREEN
                    ).pack(pady=(5, 10))

                    # Summary stats
                    ctk.CTkLabel(
                        f, text=f"  • New Created: {created}",
                        font=ctk.CTkFont(family="Livvic", size=12), anchor="w"
                    ).pack(fill="x", pady=2)

                    ctk.CTkLabel(
                        f, text=f"  • Skipped (Duplicates): {skipped}",
                        font=ctk.CTkFont(family="Livvic", size=12), anchor="w"
                    ).pack(fill="x", pady=2)

                    if errors > 0:
                        ctk.CTkLabel(
                            f, text=f"  • Failed (Errors): {errors}",
                            font=ctk.CTkFont(family="Livvic", size=12),
                            text_color=C_RED, anchor="w"
                        ).pack(fill="x", pady=2)

                    ctk.CTkLabel(f, text="").pack(pady=4)  # spacer

                    ctk.CTkButton(
                        f, text="OK", corner_radius=15,
                        fg_color=C_PRIMARY, hover_color=C_PRIMARY_H,
                        font=ctk.CTkFont(family="Livvic", size=12, weight="bold"),
                        height=30, text_color=C_PRIMARY_T,
                        command=dialog.destroy
                    ).pack(fill="x")

                self.after(0, show_success)

        except Exception:
            self._log(f"💥 Unexpected in Submit All:\n{traceback.format_exc()[-250:]}")
        finally:
            self.submitting_all = False
            self.after(0, lambda: self._set_all_row_btns_state(True))
            self.after(0, lambda: self._submit_all_btn.configure(state="normal", text="🚀 Submit All"))
            self._update_action_btn()

    # ─────────────────────────────────────────────────────────────────────────
    # TISTA HTTP LAYER  (ported from Code.gs into Python requests)
    # ─────────────────────────────────────────────────────────────────────────
    def _tista_login(self, email, password):
        try:
            s = self.session
            r0 = s.get(f"{TISTA_BASE}/users/sign_in", timeout=30)
            csrf = extract_csrf(r0.text)
            pm   = re.search(
                r'name=["\']csrf-param["\'][^>]+content=["\']([^"\']+)["\']',
                r0.text, re.I)
            param = pm.group(1) if pm else "authenticity_token"
            if not csrf:
                return False, "Cannot find CSRF on login page."

            r1 = s.post(
                f"{TISTA_BASE}/users/sign_in",
                data={
                    "utf8":              "✓",
                    param:               csrf,
                    "user[email]":       email,
                    "user[password]":    password,
                    "user[remember_me]": "1",
                    "commit":            "Log in",
                },
                timeout=30,
                headers={
                    "Referer": f"{TISTA_BASE}/users/sign_in",
                    "Origin":  TISTA_BASE,
                },
                allow_redirects=True)

            if "sign_in" in r1.url or "Log in" in r1.text[:600]:
                return False, "Wrong email or password."

            r2 = s.get(f"{TISTA_BASE}/", timeout=30)
            nc = extract_csrf(r2.text)
            if nc:
                self.last_csrf_str = nc

            return True, ""
        except requests.RequestException as e:
            return False, str(e)[:120]

    def _is_login_page(self, response):
        if response is None:
            return False
        url_check = "sign_in" in getattr(response, "url", "")
        text_check = "Log in" in response.text[:1200] and ("user_email" in response.text[:2000] or "new_user" in response.text[:2000] or "Welcome" in response.text[:1000])
        return url_check or text_check

    def _get(self, path, params=None):
        try:
            r = self.session.get(
                f"{TISTA_BASE}{path}", timeout=30,
                params=params,
                headers={"X-CSRF-Token": self.last_csrf_str})
            nc = extract_csrf(r.text)
            if nc:
                self.last_csrf_str = nc
            return r
        except requests.RequestException as e:
            self._log(f"❌ GET Error ({path}): {str(e)[:100]}")
            return None

    def _post(self, path, payload):
        try:
            r = self.session.post(
                f"{TISTA_BASE}{path}", data=payload, timeout=30,
                headers={"X-CSRF-Token": self.last_csrf_str},
                allow_redirects=True)
            nc = extract_csrf(r.text)
            if nc:
                self.last_csrf_str = nc
            return r
        except requests.RequestException as e:
            self._log(f"❌ POST Error ({path}): {str(e)[:100]}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # CONSOLE LOG
    # ─────────────────────────────────────────────────────────────────────────
    def _log(self, msg):
        def _do():
            t = datetime.now().strftime("%H:%M:%S")
            self._log_box.configure(state="normal")
            self._log_box.insert("end", f"[{t}] {msg}\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        self.after(0, _do)

    def _clear_log_entries(self, order_ids):
        """Remove log lines containing any of the given order IDs (e.g., skipped entries)."""
        def _do():
            self._log_box.configure(state="normal")
            content = self._log_box.get("1.0", "end-1c")
            lines = content.split("\n")
            filtered = [line for line in lines if not any(f"#{oid}" in line for oid in order_ids)]
            self._log_box.delete("1.0", "end")
            self._log_box.insert("1.0", "\n".join(filtered))
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        self.after(0, _do)

    # ─────────────────────────────────────────────────────────────────────────
    # LOGOUT
    # ─────────────────────────────────────────────────────────────────────────
    def _logout(self):
        self.session              = requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self.cookie_jar_str       = ""
        self.last_csrf_str        = ""
        self.disputes             = []
        self.row_widgets          = []
        self.geometry_initialized = False
        self._save_config(save_creds=False)
        self._show_login_page()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = DisputeFillerApp()
    app.mainloop()
