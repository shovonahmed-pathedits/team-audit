# Order Collector

A PySide6-based desktop application for fetching and analyzing order data from the Tista Dashboard. Built with security and performance in mind, featuring encrypted credential storage, auto-relogin, and a polished modern UI.

## Features

- **⚡ Parallel Data Fetching** — High-speed multi-threaded date and pagination scraping (`ThreadPoolExecutor`) that drastically cuts down wait times for multi-day date ranges.
- **🔐 Smart Login** — Secure credential persistence powered by Windows Credential Manager (`keyring`).
- **🔄 Auto-Relogin** — Transparently restores authentication sessions if cookies expire mid-operation.
- **🌓 Adaptive Theme** — Modern, responsive interface featuring dynamic Windows system Dark & Light mode auto-detection.
- **📋 Data Export** — One-click export to formatted Excel/CSV or instant clipboard copy.
- **🛡️ Secure Sessions** — Encrypted session cookies stored safely in `%APPDATA%\OrderCollector\sessions\`.
- **💻 Headless & GUI Modes** — Full-featured PySide6 desktop GUI alongside CLI flags for headless automation.

## Tech Stack

| Component | Technology |
|-----------|------------|
| **GUI Framework** | PySide6 (Qt 6) |
| **Concurrency** | `concurrent.futures` (`ThreadPoolExecutor`) |
| **HTTP Client** | `requests` + `requests_toolbelt` |
| **HTML Parsing** | `beautifulsoup4` |
| **Credential Storage** | `keyring` (Windows Vault API) |
| **Packaging** | PyInstaller (`--onefile`, embedded icon) |


## Prerequisites

- Python 3.12+
- Windows 10/11 (uses Windows Credential Manager)
- Git (optional, for cloning)

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/mohsin-path/order_collector.git
cd order_collector

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### From Release (Executable)

1. Download `OrderCollector.exe` from the [Releases](https://github.com/mohsin-path/order_collector/releases) page.
2. Run `OrderCollector.exe` directly — no Python installation required.

## Usage

### GUI Mode (Default)
```bash
python main.py
```
Opens the login window. Enter your Tista credentials and click **Login**.

### Debug Mode
```bash
python main.py --debug
```
Enables verbose logging. Logs are saved to `logs/debug.log`.

### Headless Mode
```bash
python main.py --headless --email user@example.com --password yourpassword --start-date 01/01/24 --end-date 31/01/24
```
Fetches data without GUI and prints results to console.

### Export to Excel/CSV
```bash
python main.py --headless --email user@example.com --password yourpassword --start-date 01/01/24 --end-date 31/01/24 --export excel
```

### Command Line Arguments

| Argument | Description |
|----------|-------------|
| `--debug` | Enable verbose logging |
| `--headless` | Run without GUI (for automation) |
| `--test-login` | Test credentials and exit |
| `--email` | User email (used with `--test-login` or `--headless`) |
| `--password` | User password (used with `--test-login` or `--headless`) |
| `--start-date` | Start date in `DD/MM/YY` format |
| `--end-date` | End date in `DD/MM/YY` format |
| `--location-id` | Filter by location ID |

## Building the Executable

### Using PyInstaller

```bash
# Install dependencies
pip install -r requirements.txt

# Run build script
build.bat
```

This produces `dist\OrderCollector.exe` — a single portable file (~65 MB).

### Build Requirements

- `pyinstaller` (included in `requirements.txt`)
- `Logo.ico` in the project root

## Project Structure

```
Order Collector/
├── api/                # API client and endpoints
│   ├── client.py       # TistaAPI class with session management
│   └── endpoints.py    # URL constants
├── gui/                # UI components
│   ├── login_window.py # Login dialog
│   ├── main_window.py  # Main dashboard
│   └── widgets/        # Reusable widgets (date picker, data table)
├── services/           # Business logic
│   ├── data_fetcher.py # Order fetching with progress
│   └── data_processor.py # Grouping and formatting
├── utils/              # Utilities
│   ├── credential_manager.py # Windows Credential Manager wrapper
│   └── logger.py       # Logging setup
├── config.py           # Configuration constants
├── main.py             # Application entry point
├── requirements.txt    # Python dependencies
└── build.bat           # PyInstaller build script
```

## Security

- **No hardcoded secrets**: Credentials are never stored in source code.
- **Windows Vault**: Passwords are saved using the OS-level Credential Manager.
- **Encrypted Sessions**: Cookies are stored securely in `%APPDATA%\OrderCollector\sessions\`.
- **Auto-Cleanup**: Session files are deleted on logout.

## Troubleshooting

### Application won't start
- Ensure `python312.dll` is available if running from source.
- Check `logs/debug.log` for error details.

### Login fails
- Verify network connectivity to `tista.app`.
- Clear saved credentials in Windows Credential Manager (`cmdkey /list`).

### Defender flags the .exe
- PyInstaller `--onefile` extracts to `%TEMP%`, which some AV tools flag.
- Submit the file to Microsoft Defender for whitelisting.

## License

This project is private and intended for internal use only.

## Author

Developed by **Mohsin** — Order Collector Team
