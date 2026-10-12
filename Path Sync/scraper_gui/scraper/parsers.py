"""HTML parsers for Tista assignment data extraction."""

import re
from html import unescape
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from config import is_known_sm, sm_priority, SYSTEM_USERS, VENDOR_3KEY_MAPPING


def normalize_vendor_name(name: str) -> str:
    """Normalize vendor name for robust matching (lowercase, no parentheses/IDs)."""
    if not name:
        return ""
    # Remove everything in parentheses like (P1) or (P2)
    name = re.sub(r"\s*\(.*?\)", "", name)
    # Remove everything in brackets like [123]
    name = re.sub(r"\s*\[.*?\]", "", name)
    # Remove non-alphanumeric characters and lowercase
    return "".join(e for e in name if e.isalnum()).lower()


def extract_locations_from_files_filter(html: str, log_func=None) -> List[str]:
    """Extract vendor/location names from the custom filter section of the Files page."""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    vendors = set()

    # 1. Target the specific "Locations" section identified in the provided HTML
    locations_container = soup.find(attrs={"data-order-files-target": "locationsFilters"})
    if not locations_container:
        # Fallback for older Stimulus versions
        locations_container = soup.find(attrs={"data-target": "order-files.locationsFilters"})

    if locations_container:
        # Find all labels within this specific container
        labels = locations_container.find_all("label", class_="filter-line-label")
        for label in labels:
            val = label.get_text(strip=True)
            if val:
                vendors.add(val)
                if log_func:
                    log_func(f"[DEBUG] Found vendor in locationsFilters container: {val}")

    # 2. Fallback: Search for any label with 'filter-line-label' that matches a known vendor
    if not vendors:
        for label in soup.find_all("label", class_="filter-line-label"):
            val = label.get_text(strip=True)
            if val and val in VENDOR_3KEY_MAPPING:
                vendors.add(val)
                if log_func:
                    log_func(f"[DEBUG] Found known vendor by class match: {val}")

    # 3. Fallback: Search for labels near a "Locations" or "Vendors" title
    if not vendors:
        for section_title in soup.find_all(["span", "h1", "h2", "h3", "h4", "h5", "strong"]):
            text = section_title.get_text().lower()
            if "location" in text or "vendor" in text:
                # Check parent or siblings for items
                parent = section_title.find_parent(["div", "section"])
                if parent:
                    for label in parent.find_all("label"):
                        val = label.get_text(strip=True)
                        if val and (val in VENDOR_3KEY_MAPPING or "filter-line" in str(label.get("class", ""))):
                            vendors.add(val)

    # 4. Fallback: Generic select-based search
    if not vendors:
        for select in soup.find_all("select"):
            name_attr = (select.get("name") or "").lower()
            if "location" in name_attr or "vendor" in name_attr:
                for option in select.find_all("option"):
                    val = (option.string or option.get_text()).strip()
                    if val and "select" not in val.lower() and "all" not in val.lower():
                        vendors.add(val)

    vendor_list = sorted(list(vendors))
    if log_func and vendor_list:
        log_func(f"[OK] Total unique vendors detected in filter: {len(vendor_list)}")
    
    return vendor_list


def extract_header_template_html(
    html: str, assignment_id: Optional[str] = None, log_func=None
) -> str:
    """Return the assignment header template from a turbo-stream response."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    target_id = f"order_assignment_{assignment_id}_header" if assignment_id else None

    matched_template = ""
    matched_target = ""
    streams = soup.find_all("turbo-stream")
    for stream in streams:
        target = stream.get("target", "")
        if target_id and target != target_id:
            continue
        if not target_id and not str(target).endswith("_header"):
            continue

        template = stream.find("template")
        if template:
            matched_target = str(target)
            matched_template = template.decode_contents()

    if matched_template:
        if log_func:
            log_func(f"[OK] Matched header turbo-stream target: {matched_target}")
        return matched_template

    if log_func:
        log_func("[WARN] Header turbo-stream template not found, using raw response")
    return html


def normalize_note_text(text: str) -> str:
    """Decode and preserve multiline note text for export."""
    if not text:
        return ""

    decoded = unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = []
    blank_added = False

    for raw_line in decoded.split("\n"):
        line = raw_line.strip()
        if line:
            normalized_lines.append(line)
            blank_added = False
        elif normalized_lines and not blank_added:
            normalized_lines.append("")
            blank_added = True

    return "\n".join(normalized_lines).strip()


def extract_production_notes(soup: BeautifulSoup, log_func=None) -> str:
    """Extract production notes from the production-notes controller block."""
    controller = soup.find(attrs={"data-controller": "production-notes"})
    if not controller:
        return ""

    note_value = controller.get("data-production-notes-note-value")
    if isinstance(note_value, str) and note_value.strip():
        if log_func:
            log_func("[OK] Production notes found in controller attribute")
        return normalize_note_text(note_value)

    for node in controller.find_all(True):
        for attr_name, attr_value in node.attrs.items():
            if (
                isinstance(attr_value, str)
                and attr_name.startswith("data-production-notes-")
                and attr_name.endswith("-value")
                and "note" in attr_name
                and attr_value.strip()
            ):
                if log_func:
                    log_func(
                        f"[OK] Production notes found in descendant attribute: {attr_name}"
                    )
                return normalize_note_text(attr_value)

    container = controller.find(attrs={"data-production-notes-target": "container"})
    if container:
        visible_text = container.get_text("\n", strip=True)
        if visible_text:
            if log_func:
                log_func("[OK] Production notes found in rendered container")
            return normalize_note_text(visible_text)

    rendered_block = BeautifulSoup(str(controller), "html.parser")
    empty_message = rendered_block.find(
        attrs={"data-production-notes-target": "emptyNoteMessage"}
    )
    if empty_message:
        empty_message.decompose()

    edit_button = rendered_block.find(
        attrs={"data-production-notes-target": "editModeButton"}
    )
    if edit_button:
        edit_button.decompose()

    heading = rendered_block.find("h3")
    if heading:
        heading.decompose()

    rendered_text = rendered_block.get_text("\n", strip=True)
    if rendered_text:
        if log_func:
            log_func("[OK] Production notes found in fallback rendered text")
        return normalize_note_text(rendered_text)

    return ""


def parse_header(html: str, assignment_id: Optional[str] = None, log_func=None) -> Dict:
    """Parse assignment header HTML - handles turbo-stream format."""
    header_html = extract_header_template_html(html, assignment_id, log_func)
    soup = BeautifulSoup(header_html, "html.parser")
    d: Dict = {}

    if not html:
        if log_func:
            log_func("WARNING: Empty HTML response for header")
        return d

    if len(header_html) < 100:
        if log_func:
            log_func(
                f"WARNING: Very short HTML response ({len(header_html)} chars): {header_html[:100]}"
            )

    # Extract order number from <span class="text-primary">#430369</span>
    order_span = soup.find("span", class_="text-primary")
    if order_span:
        order_text = order_span.string if order_span.string else ""
        if not order_text:
            order_text = "".join(str(s) for s in order_span.contents)

        order_match = re.search(r"#(\d+)", order_text)
        if order_match:
            d["order_number"] = f"#{order_match.group(1)}"
            if log_func:
                log_func(f"[OK] Order: {d['order_number']}")
        else:
            if log_func:
                log_func(f"Could not extract order number from: {order_text}")
    else:
        if log_func:
            log_func("Could not find order number span")

    # Extract internal order ID
    internal_order_id = ""
    production_controller = soup.find(attrs={"data-controller": "production-notes"})
    if production_controller:
        internal_order_id = (
            production_controller.get("data-production-notes-order-id-value", "") or ""
        ).strip()

    if not internal_order_id:
        any_order_attr = re.search(
            r'data-[^"]*order-id-value="(\d+)"', header_html, re.IGNORECASE
        )
        if any_order_attr:
            internal_order_id = any_order_attr.group(1).strip()

    if not internal_order_id:
        internal_order_match = re.search(
            r"\b(342\d{3}|341\d{3}|343\d{3})\b", header_html
        )
        if internal_order_match:
            internal_order_id = internal_order_match.group(1).strip()

    if internal_order_id:
        d["internal_order_id"] = internal_order_id
        if log_func:
            log_func(f"[OK] Internal Order ID: {d['internal_order_id']}")
    else:
        if log_func:
            log_func("WARNING: Could not extract internal order ID from header")

    # Status badge
    status_badge = soup.find(
        "span",
        class_=lambda x: x and "badge" in x and "rounded" in x and "primary" in x,
    )
    if status_badge:
        status_text = status_badge.string if status_badge.string else ""
        if not status_text:
            status_text = "".join(str(s) for s in status_badge.contents).strip()

        if status_text:
            d["status"] = status_text
            if log_func:
                log_func(f"[OK] Status: {status_text}")
    else:
        if log_func:
            log_func("Could not find status badge")

    # Received date
    match = re.search(r"Received[^0-9]*(\d+/\d+/\d+)", header_html)
    if match:
        d["received"] = match.group(1)
        if log_func:
            log_func(f"[OK] Received: {d['received']}")
    else:
        if log_func:
            log_func("Could not find Received date")

    # Subcontractor
    geo_icon = soup.find("i", class_=lambda x: x and "bi-geo-alt" in x)
    if geo_icon:
        next_elem = geo_icon.next_sibling
        location = ""
        while next_elem:
            if isinstance(next_elem, str):
                location = next_elem.strip()
                if location:
                    break
            elif hasattr(next_elem, "string") and next_elem.string:
                location = str(next_elem.string).strip()
                if location and location != "Status":
                    break
            next_elem = next_elem.next_sibling

        if location and location != "Status":
            d["subcontractor"] = location
            if log_func:
                log_func(f"[OK] Subcontractor: {location}")
        else:
            if log_func:
                log_func("Could not extract subcontractor location")

    # Return file format
    return_format = ""
    html_str = str(header_html)

    for strong in soup.find_all("strong"):
        strong_text = strong.string if strong.string else ""
        if "format" in strong_text.lower() or "file" in strong_text.lower():
            next_elem = strong.next_sibling
            while next_elem:
                if isinstance(next_elem, str):
                    fmt = next_elem.strip()
                    if fmt and len(fmt) > 2:
                        return_format = fmt
                        break
                next_elem = next_elem.next_sibling
            if return_format:
                break

    if not return_format:
        format_match = re.search(
            r"(Psd|Png|Jpg|Zip|Ai|Svg)[^<]*(?:transparent|background|layer[^<]*)?",
            html_str,
            re.IGNORECASE,
        )
        if format_match:
            return_format = format_match.group(0).strip()

    if return_format:
        d["return_format"] = return_format
        if log_func:
            log_func(f"[OK] Return Format: {return_format}")

    # Comments
    comments_label = soup.find(string=re.compile(r"Additional comments", re.I))
    if comments_label:
        container = comments_label.find_parent(["div", "p", "strong", "span"])
        if container:
            comments = []
            # Check siblings of the container
            curr = container.find_next_sibling()
            while curr:
                if curr.name == "p":
                    text = curr.get_text(strip=True)
                    if text:
                        comments.append(text)
                elif curr.name in ["strong", "h1", "h2", "h3", "h4", "h5"]:
                    # Likely next section title
                    break
                else:
                    # Generic container, check inside for <p>
                    inner_ps = curr.find_all("p", recursive=False)
                    if inner_ps:
                        for p in inner_ps:
                            comments.append(p.get_text(strip=True))
                    elif curr.name == "div" and "Additional comments" not in curr.get_text():
                        # If it's a div without a title, it might be more comments
                        pass
                    else:
                        break
                curr = curr.find_next_sibling()
            
            # Fallback: if no siblings found, maybe they are in a <div> that comes after the <strong>
            if not comments:
                next_p = comments_label.find_next("p")
                if next_p:
                    prev_strong = next_p.find_previous(["strong", "h3", "h4"])
                    if prev_strong and "Additional comments" in prev_strong.get_text():
                        curr = next_p
                        while curr:
                            if curr.name == "p":
                                comments.append(curr.get_text(strip=True))
                            elif curr.name in ["strong", "h3", "h4"]:
                                break
                            curr = curr.find_next_sibling()

            if comments:
                comment_text = normalize_note_text("\n".join(comments))
                if comment_text:
                    d["comments"] = comment_text
                    if log_func:
                        log_func(f"[OK] Comments: {comment_text[:50]}...")

    # Notes
    notes_text = extract_production_notes(soup, log_func)
    if notes_text:
        d["notes"] = notes_text
        if log_func:
            log_func(f"[OK] Notes: {notes_text[:50]}...")

    if log_func:
        log_func(f"Extracted {len(d)} fields from header")
    return d


def _get_best_sm(candidates, creation_idx):
    """Select the best SM from candidates based on Priority (Group 1>2>3>4) and then Distance (closest to creation)."""
    if not candidates:
        return None

    # Sort by (priority, index)
    # Lower priority number = higher priority.
    # Lower index = closer to creation (since timeline is newest-first).
    candidates.sort(
        key=lambda c: (sm_priority(c["user"]), abs(c["index"] - creation_idx))
    )
    return candidates[0]["user"]


def parse_history(html: str, log_func=None) -> Dict:
    """Parse assignment history HTML to extract SM Name and Auditor using a 3-Layer System.

    Layer 2: History-based scan BEFORE assignment creation.
    Layer 3: History-based scan AFTER assignment creation or full history fallback.
    """
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "sm_name": "",
        "auditor": "",
        "layer2_sm": "",
        "layer3_sm": "",
    }

    history = []
    for li in soup.find_all("li"):
        b = li.find("button", class_="timeline-action")
        if not b:
            continue

        u = b.find("strong")
        tm = b.find("div", class_="action-time")
        act = b.find("div", class_="action-title")
        detail_text = ""

        collapse_target = b.get("data-bs-target", "")
        if isinstance(collapse_target, str) and collapse_target.startswith("#"):
            detail_block = li.find("div", id=collapse_target[1:])
            if detail_block:
                detail_text = detail_block.get_text(" ", strip=True)

        history.append(
            {
                "user": u.get_text(strip=True) if u else "",
                "time": tm.get_text(strip=True) if tm else "",
                "action": act.get_text(strip=True) if act else "",
                "detail": detail_text,
                "index": len(history),
            }
        )

    def _is_system_user(username: str) -> bool:
        return username.lower() in SYSTEM_USERS

    # ── Step 0: Find Creation Point ──
    creation_idx = None
    for entry in history:
        if (
            "created" in entry["action"].lower()
            and "OrderAssignment" in entry["action"]
        ):
            creation_idx = entry["index"]
            break

    # If no creation point found, treat full history as "before"
    effective_creation_idx = creation_idx if creation_idx is not None else -1

    # ── Layer 2: Best SM AT OR BEFORE creation ──
    candidates_before = []
    for entry in history:
        # AT OR BEFORE means index >= effective_creation_idx (older entries have HIGHER index)
        if effective_creation_idx != -1 and entry["index"] < effective_creation_idx:
            continue

        if not entry["user"] or _is_system_user(entry["user"]):
            continue

        if is_known_sm(entry["user"]):
            candidates_before.append({"user": entry["user"], "index": entry["index"]})

    if candidates_before:
        result["layer2_sm"] = _get_best_sm(candidates_before, effective_creation_idx)
        if log_func:
            log_func(f"[OK] Layer 2 SM candidate: {result['layer2_sm']}")

    # ── Layer 3: Best SM STRICTLY AFTER creation ──
    candidates_after = []
    for entry in history:
        # STRICTLY AFTER means index < effective_creation_idx (newer entries have LOWER index)
        if effective_creation_idx != -1 and entry["index"] >= effective_creation_idx:
            continue

        if not entry["user"] or _is_system_user(entry["user"]):
            continue

        if is_known_sm(entry["user"]):
            candidates_after.append({"user": entry["user"], "index": entry["index"]})

    if candidates_after:
        result["layer3_sm"] = _get_best_sm(candidates_after, effective_creation_idx)
    
    # Full History Fallback for Layer 3
    if not result["layer3_sm"]:
        candidates_full = []
        for entry in history:
            if not entry["user"] or _is_system_user(entry["user"]):
                continue
            if is_known_sm(entry["user"]):
                candidates_full.append({"user": entry["user"], "index": entry["index"]})
        
        if candidates_full:
            result["layer3_sm"] = _get_best_sm(candidates_full, effective_creation_idx)

    if result["layer3_sm"] and log_func:
        log_func(f"[OK] Layer 3 SM candidate: {result['layer3_sm']}")

    # Auditor - most recent "updated" action
    for entry in reversed(history):
        action = entry.get("action", "")
        user = entry.get("user", "")
        if "updated" in action.lower():
            result["auditor"] = user
            if log_func:
                log_func(f"[OK] Auditor: {user}")
            break

    return result


def format_date(date_str: str) -> str:
    """Convert date from DD/MM/YY to mm/dd/yy format."""
    from datetime import datetime

    try:
        if not date_str or "/" not in date_str:
            return date_str

        for fmt in ["%d/%m/%y", "%d/%m/%Y", "%m/%d/%y", "%m/%d/%Y"]:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                return date_obj.strftime("%m/%d/%y")
            except ValueError:
                continue

        return date_str
    except Exception:
        return date_str


def calculate_week(date_str: str) -> str:
    """Calculate week-of-month using Monday-Sunday + Thursday ownership rule."""
    from datetime import datetime, timedelta

    try:
        if not date_str or "/" not in date_str:
            return ""

        for fmt in ["%d/%m/%y", "%d/%m/%Y", "%m/%d/%y", "%m/%d/%Y"]:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                # Week belongs to the month that contains Thursday.
                target_thursday = date_obj + timedelta(days=(3 - date_obj.weekday()))
                month_of_thursday = target_thursday.month
                year_of_thursday = target_thursday.year

                first_of_month = datetime(year_of_thursday, month_of_thursday, 1)
                days_to_first_thursday = (3 - first_of_month.weekday() + 7) % 7
                first_thursday = first_of_month + timedelta(days=days_to_first_thursday)

                week_number = ((target_thursday.day - first_thursday.day) // 7) + 1
                return str(week_number)
            except ValueError:
                continue

        return ""
    except Exception:
        return ""
