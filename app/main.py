import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
from hmac import compare_digest
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from secrets import token_urlsafe
from threading import Event, Thread
from typing import Any, Dict, List

from flask import Flask, jsonify, redirect, request, session, url_for

try:
    from zeroconf import ServiceBrowser, Zeroconf
except ImportError:
    ServiceBrowser = None
    Zeroconf = None

ENV_OPTION_MAP = {
    "PRINTER_NAME": "printer_name",
    "PRINTER_HOST": "printer_host",
    "PRINTER_URI": "printer_uri",
    "TEST_PAGE_TEXT": "test_page_text",
    "DOCUMENT_PATH": "document_path",
    "UPLOADED_DOCUMENT_NAME": "uploaded_document_name",
    "SCHEDULE_ENABLED": "schedule_enabled",
    "SCHEDULE_TYPE": "schedule_type",
    "SCHEDULE_HOUR": "schedule_hour",
    "SCHEDULE_WEEKDAY": "schedule_weekday",
    "SCHEDULE_DAY_OF_MONTH": "schedule_day_of_month",
    "SCHEDULE_DESCRIPTION": "schedule_description",
    "LAST_RUN": "last_run",
}

BONJOUR_PRINTER_SERVICE_TYPES = (
    "_ipp._tcp.local.",
    "_ipps._tcp.local.",
    "_printer._tcp.local.",
    "_pdl-datastream._tcp.local.",
)


def coerce_env_value(key: str, value: str) -> Any:
    if key.endswith("_ENABLED"):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return bool(value)

    if key.endswith("_HOUR") or key.endswith("_DAY_OF_MONTH"):
        return int(value)

    return value


def apply_environment_overrides(options: Dict[str, Any]) -> Dict[str, Any]:
    defaults = build_default_options()
    for env_key, option_key in ENV_OPTION_MAP.items():
        raw_value = os.environ.get(env_key)
        if raw_value is None or raw_value == "":
            continue

        current_value = options.get(option_key)
        default_value = defaults.get(option_key)
        should_use_env = current_value in (None, "") or current_value == default_value

        if should_use_env:
            options[option_key] = coerce_env_value(env_key, raw_value)

    return options


def get_webui_port(options: Dict[str, Any] | None = None) -> int:
    if options:
        raw_value = options.get("WEBUI_PORT") or options.get("webui_port") or ""
        if isinstance(raw_value, str) and raw_value.strip():
            try:
                return int(raw_value)
            except ValueError:
                pass

    env_value = os.environ.get("WEBUI_PORT", "")
    if env_value:
        try:
            return int(env_value)
        except ValueError:
            pass

    return 8000


def build_default_options() -> Dict[str, Any]:
    return {
        "printer_name": "",
        "printer_host": "",
        "printer_uri": "",
        "test_page_text": "Inkjet Conditioner maintenance print",
        "document_path": "",
        "uploaded_document_name": "",
        "schedule_enabled": False,
        "schedule_type": "daily",
        "schedule_hour": 8,
        "schedule_weekday": "monday",
        "schedule_day_of_month": 1,
        "schedule_description": "Print once every day at 08:00",
        "last_run": "",
        "discovered_printers": [],
        "setup_complete": False,
    }


def is_setup_complete(options: Dict[str, Any]) -> bool:
    return bool((options.get("printer_host") or options.get("printer_uri") or options.get("printer_name")) and options.get("setup_complete", False))


def write_options_file(path: str, options: Dict[str, Any]) -> None:
    save_options(path, options)


def build_setup_page(options: Dict[str, Any]) -> str:
    discovered = options.get("discovered_printers") or []
    options_html = "".join(
    f"<option value='{escape(str(entry.get('host', '')), quote=True)}' data-name='{escape(str(entry.get('name', '')), quote=True)}' data-uri='{escape(str(entry.get('uri', '')), quote=True)}'>{escape(str(entry.get('name', '')))} - {escape(str(entry.get('model', 'Unknown model')))} ({escape(str(entry.get('host', '')))})</option>"
        for entry in discovered
    )
    if not options_html:
            options_html = "<option value=''>Scanning for printers on your network...</option>"

    storage = get_storage_paths()
    default_doc_path = str(storage["documents"] / "print-jobs" / "example.txt")
    default_uploads_path = str(storage["uploads"])
    value = lambda key, fallback="": escape(str(options.get(key, fallback)), quote=True)

    return f"""
    <!doctype html>
        <html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Inkjet Conditioner</title><style>
            :root {{ --ink:#182b38;--muted:#60727a;--paper:#f5f4ed;--panel:#fff;--line:#d7ded8;--lime:#d9f067;--coral:#ed765d;--teal:#167d79; }} * {{ box-sizing:border-box; }} body {{ margin:0;color:var(--ink);background-color:var(--paper);background-image:linear-gradient(#dfe6df 1px,transparent 1px),linear-gradient(90deg,#dfe6df 1px,transparent 1px);background-size:32px 32px;font-family:Avenir Next,Avenir,Futura,sans-serif;letter-spacing:0; }} .shell {{ min-height:100vh;display:grid;grid-template-columns:260px minmax(0,1fr); }} .rail {{ padding:32px 24px;background:var(--ink);color:#f8fbf5;display:flex;flex-direction:column;gap:42px; }} .brand {{ display:flex;align-items:center;gap:12px;font-weight:800;font-size:17px; }} .mark {{ display:grid;place-items:center;width:36px;height:36px;border:2px solid var(--lime);color:var(--lime);font-family:Georgia,serif;font-size:19px; }} .rail nav {{ display:grid;gap:10px; }} .nav-item {{ padding:11px 12px;color:#b9c8c4;border-left:3px solid transparent;font-size:14px; }} .nav-item.active {{ color:white;border-left-color:var(--lime);background:#243d4d; }} .rail-foot {{ margin-top:auto;border-top:1px solid #3c5260;padding-top:20px;color:#b9c8c4;font-size:12px;line-height:1.6; }} .dot {{ display:inline-block;width:8px;height:8px;margin-right:7px;background:var(--lime);border-radius:50%; }} main {{ padding:36px clamp(24px,5vw,80px) 56px;max-width:1250px;width:100%; }} .topbar {{ display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:32px; }} .eyebrow {{ margin:0 0 8px;color:var(--teal);font-size:12px;font-weight:800;text-transform:uppercase; }} h1 {{ margin:0;font-family:Georgia,serif;font-weight:400;font-size:clamp(34px,4vw,52px);line-height:1.02; }} .subtitle {{ max-width:560px;margin:14px 0 0;color:var(--muted);line-height:1.5; }} .status-pill {{ white-space:nowrap;border:1px solid var(--line);background:var(--panel);padding:9px 12px;color:var(--teal);font-size:12px;font-weight:800; }} form {{ display:grid;gap:16px; }} .section {{ background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden;box-shadow:5px 5px 0 #dfe5d9; }} .section-head {{ display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px 24px;border-bottom:1px solid var(--line); }} .section-index {{ color:var(--coral);font-size:12px;font-weight:800; }} h2 {{ margin:0;font-size:17px; }} .section-body {{ padding:24px; }} .discovery {{ display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:16px;padding-bottom:22px;border-bottom:1px solid var(--line); }} label {{ display:grid;gap:7px;color:#40535b;font-size:12px;font-weight:800;text-transform:uppercase; }} input,select {{ width:100%;min-height:44px;padding:10px 12px;border:1px solid #bac7c1;border-radius:4px;color:var(--ink);background:#fcfdf9;font:inherit;font-size:15px; }} input:focus,select:focus {{ outline:3px solid var(--lime);outline-offset:1px;border-color:var(--ink); }} .grid-3 {{ display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:22px; }} button {{ min-height:44px;border:0;border-radius:4px;padding:0 16px;background:var(--ink);color:white;font:inherit;font-size:14px;font-weight:800;cursor:pointer; }} button:hover {{ background:#294555; }} .secondary {{ background:#e8eee7;color:var(--ink);border:1px solid #cdd7d0; }} .file-control {{ display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:18px;padding:17px;background:#f1f5ed;border:1px dashed #9eb0a6;border-radius:5px; }} .file-control strong {{ display:block;font-size:14px; }} .file-control span {{ display:block;margin-top:4px;color:var(--muted);font-size:12px; }} input[type=file] {{ position:absolute;width:1px;height:1px;opacity:0; }} .file-label {{ display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:0 14px;background:var(--panel);border:1px solid #bac7c1;border-radius:4px;color:var(--ink);cursor:pointer;font-size:13px;font-weight:800;text-transform:none; }} .schedule-top {{ display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:22px; }} .switch {{ display:inline-flex;align-items:center;gap:10px;color:var(--ink);font-size:14px;font-weight:800;text-transform:none; }} .switch input {{ appearance:none;width:44px;min-height:24px;padding:2px;border-radius:20px;background:#bdc9c3; }} .switch input::after {{ content:'';display:block;width:18px;height:18px;background:white;border-radius:50%;transition:.2s; }} .switch input:checked {{ background:var(--teal); }} .switch input:checked::after {{ transform:translateX(18px); }} .segments {{ display:flex;border:1px solid #bac7c1;border-radius:5px;overflow:hidden; }} .segments label {{ flex:1;display:block;text-align:center;padding:10px;border-right:1px solid #bac7c1;cursor:pointer;font-size:12px; }} .segments label:last-child {{ border:0; }} .segments input {{ position:absolute;opacity:0; }} .segments label:has(input:checked) {{ background:var(--lime);color:var(--ink); }} .action-row {{ display:flex;justify-content:space-between;align-items:center;gap:20px;padding:8px 0; }} .hint,#result {{ margin:0;color:var(--muted);font-size:13px; }} #result {{ color:var(--teal);font-weight:800; }} @media (max-width:760px) {{ .shell {{ display:block; }} .rail {{ padding:16px 20px;flex-direction:row;align-items:center;gap:0; }} .rail nav,.rail-foot {{ display:none; }} main {{ padding:28px 20px 40px; }} .topbar {{ display:block; }} .status-pill {{ display:inline-block;margin-top:18px; }} .grid-3 {{ grid-template-columns:1fr; }} .discovery,.file-control {{ grid-template-columns:1fr;align-items:stretch; }} .schedule-top,.action-row {{ align-items:flex-start;flex-direction:column; }} }}
        </style></head><body><div class="shell"><aside class="rail"><div class="brand"><div class="mark">IC</div>Inkjet Conditioner</div><nav><div class="nav-item active">Configuration</div><div class="nav-item">Printer discovery</div><div class="nav-item">Scheduled runs</div></nav><div class="rail-foot"><span class="dot"></span>Service online<br>Configuration stored in /config</div></aside><main><header class="topbar"><div><p class="eyebrow">Local print utility</p><h1>Keep your ink moving.</h1><p class="subtitle">Set a printer, choose a document, and schedule a small recurring print to keep an inkjet ready.</p></div><div class="status-pill">SETUP REQUIRED</div></header><form id="setup-form" method="post" action="/api/setup" enctype="multipart/form-data"><section class="section"><div class="section-head"><div><span class="section-index">01 / PRINTER</span><h2>Choose a destination</h2></div><button class="secondary" type="button" onclick="refreshPrinters()">Refresh discovery</button></div><div class="section-body"><div class="discovery"><label>Detected printers<select id="detected-printers" onchange="applyDetectedPrinter(this)"><option value="">Select a detected printer</option>{options_html}</select></label><p class="hint" id="discovery-note">Bonjour and local network discovery are enabled.</p></div><div class="grid-3"><label>Printer name<input name="printer_name" value="{value('printer_name')}" placeholder="Office printer"></label><label>IP address or hostname<input name="printer_host" value="{value('printer_host')}" placeholder="192.168.1.42"></label><label>Print URI<input name="printer_uri" value="{value('printer_uri')}" placeholder="ipp://printer.local/ipp/print"></label></div></div></section><section class="section"><div class="section-head"><div><span class="section-index">02 / PRINT JOB</span><h2>Choose what to print</h2></div></div><div class="section-body"><div class="file-control"><div><strong id="file-name">Upload a PDF, image, or text document</strong><span>Saved to {escape(default_uploads_path)}. Shared files can be addressed directly below.</span></div><label class="file-label" for="uploaded-file">Choose file<input id="uploaded-file" type="file" name="uploaded_file" accept=".pdf,.txt,.png,.jpg,.jpeg,.ps" onchange="showFileName(this)"></label></div><div class="grid-3"><label style="grid-column:span 2">File from shared storage<input name="document_path" value="{value('document_path', default_doc_path)}" placeholder="/share/print-jobs/document.pdf"></label><label>Test page message<input name="test_page_text" value="{value('test_page_text', 'Inkjet Conditioner test page')}"></label></div></div></section><section class="section"><div class="section-head"><div><span class="section-index">03 / SCHEDULE</span><h2>Set the maintenance rhythm</h2></div></div><div class="section-body"><div class="schedule-top"><p class="hint">A compact scheduled print helps prevent dry print heads.</p><label class="switch">Enable scheduled prints<input type="checkbox" name="schedule_enabled" {'checked' if options.get('schedule_enabled') else ''}></label></div><div class="grid-3" style="margin-top:0"><div><label>Frequency</label><div class="segments"><label><input type="radio" name="schedule_type" value="daily" {'checked' if options.get('schedule_type', 'daily') == 'daily' else ''}>Daily</label><label><input type="radio" name="schedule_type" value="weekly" {'checked' if options.get('schedule_type') == 'weekly' else ''}>Weekly</label><label><input type="radio" name="schedule_type" value="monthly" {'checked' if options.get('schedule_type') == 'monthly' else ''}>Monthly</label></div></div><label>Run hour<input type="number" name="schedule_hour" value="{value('schedule_hour', 8)}" min="0" max="23"></label><label>Weekday<select name="schedule_weekday">{''.join(f"<option value='{day}' {'selected' if options.get('schedule_weekday') == day else ''}>{day.title()}</option>" for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])}</select></label></div></div></section><div class="action-row"><p id="result">Changes are saved to persistent appdata.</p><button type="submit">Save and print test page</button></div></form></main></div><script>
            function applyDetectedPrinter(select) {{ const selected=select.options[select.selectedIndex]; if (!selected || !selected.value) return; const form=select.form; form.printer_name.value=selected.dataset.name || form.printer_name.value; form.printer_host.value=selected.value; form.printer_uri.value=selected.dataset.uri || form.printer_uri.value; }} function showFileName(input) {{ if (input.files[0]) document.getElementById('file-name').textContent=input.files[0].name; }} async function refreshPrinters() {{ const note=document.getElementById('discovery-note'); note.textContent='Looking for newly discovered printers...'; const response=await fetch('/api/printers'); const data=await response.json(); const select=document.getElementById('detected-printers'); select.innerHTML='<option value="">Select a detected printer</option>'; data.printers.forEach((printer)=>{{ const option=new Option(`${{printer.name}} - ${{printer.model || 'Unknown model'}} (${{printer.host}})`,printer.host); option.dataset.name=printer.name; option.dataset.uri=printer.uri; select.add(option); }}); note.textContent=data.printers.length ? `${{data.printers.length}} printer(s) detected.` : 'Still scanning. Try refresh again in a moment.'; }} document.getElementById('setup-form').addEventListener('submit',async(event)=>{{ event.preventDefault(); const result=document.getElementById('result'); result.textContent='Saving configuration and sending test page...'; const response=await fetch('/api/setup',{{method:'POST',body:new FormData(event.currentTarget)}}); const data=await response.json(); result.textContent=data.status==='ok' ? 'Saved. Test print queued successfully.' : 'Unable to save configuration.'; }}); setTimeout(refreshPrinters,3500);
                </script>
                <script>
                    const navItems = document.querySelectorAll('.nav-item');
                    const navTargets = [
                        document.querySelector('.section'),
                        document.getElementById('detected-printers'),
                        document.querySelectorAll('.section')[2],
                    ];
                    function activateNavigation(index) {{
                        navItems.forEach((item, itemIndex) => item.classList.toggle('active', itemIndex === index));
                        navTargets[index].scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                    }}
                    navItems.forEach((item, index) => {{
                        item.setAttribute('role', 'button');
                        item.tabIndex = 0;
                        item.style.cursor = 'pointer';
                        item.addEventListener('click', () => activateNavigation(index));
                        item.addEventListener('keydown', (event) => {{
                            if (event.key === 'Enter' || event.key === ' ') {{
                                event.preventDefault();
                                activateNavigation(index);
                            }}
                        }});
                    }});
                </script></body>
    </html>
    """


def build_status_page(options: Dict[str, Any]) -> str:
    printer = resolve_printer_target(options)
    return json.dumps({
        "status": "ok",
        "service": "inkjet-conditioner",
        "printer": printer,
        "discovered_printers": options.get("discovered_printers", []),
        "setup_complete": is_setup_complete(options),
    }, indent=2)


def should_run_now(options: Dict[str, Any], now: str | None = None) -> bool:
    if not options.get("schedule_enabled", False):
        return False

    current_time = datetime.fromisoformat(now or datetime.utcnow().replace(microsecond=0).isoformat())
    last_run_raw = options.get("last_run") or ""
    if not last_run_raw:
        return current_time.hour == int(options.get("schedule_hour", 8))

    last_run = datetime.fromisoformat(last_run_raw)
    schedule_type = options.get("schedule_type", "daily")
    hour = int(options.get("schedule_hour", 8))
    weekday = (options.get("schedule_weekday") or "monday").lower()
    day_of_month = int(options.get("schedule_day_of_month", 1))

    if schedule_type == "daily":
        return current_time.hour == hour and current_time > last_run

    if schedule_type == "weekly":
        weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        if weekday not in weekday_names:
            return False
        return current_time.weekday() == weekday_names.index(weekday) and current_time.hour == hour and current_time > last_run

    if schedule_type == "monthly":
        return current_time.day == day_of_month and current_time.hour == hour and current_time > last_run

    return False


def resolve_printer_target(options: Dict[str, Any]) -> Dict[str, str]:
    configured = {
        "name": options.get("printer_name") or "Configured printer",
        "host": options.get("printer_host") or "",
        "uri": options.get("printer_uri") or "",
    }
    discovered = options.get("discovered_printers") or []
    if discovered and not configured["host"] and not configured["uri"]:
        first = discovered[0]
        configured["name"] = first.get("name", configured["name"])
        configured["host"] = first.get("host", "")
        configured["uri"] = first.get("uri", "")
    return configured


def get_candidate_hosts() -> List[str]:
    hosts: List[str] = []
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        if local_ip and local_ip != "127.0.0.1":
            network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
            hosts.extend([str(ip) for ip in network.hosts()])
    except OSError:
        hosts = []

    return list(dict.fromkeys(hosts))


def probe_printer_host(host: str) -> Dict[str, str] | None:
    for port in (631, 9100, 515):
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return {
                    "name": f"Printer at {host}",
                    "model": "Unknown model",
                    "host": host,
                    "uri": f"ipp://{host}/ipp/print",
                }
        except OSError:
            continue

    return None


def discover_mdns_printers(timeout: float = 3.0) -> List[Dict[str, str]]:
    if Zeroconf is None or ServiceBrowser is None:
        return []

    services: List[tuple[str, str]] = []

    class PrinterListener:
        def add_service(self, _zeroconf: Any, service_type: str, name: str) -> None:
            services.append((service_type, name))

        def remove_service(self, _zeroconf: Any, _service_type: str, _name: str) -> None:
            pass

        def update_service(self, _zeroconf: Any, _service_type: str, _name: str) -> None:
            pass

    zeroconf = Zeroconf()
    listener = PrinterListener()
    try:
        browsers = [
            ServiceBrowser(zeroconf, service_type, listener)
            for service_type in BONJOUR_PRINTER_SERVICE_TYPES
        ]
        if browsers:
            Event().wait(timeout)

        printers: List[Dict[str, str]] = []
        for service_type, name in services:
            info = zeroconf.get_service_info(service_type, name, timeout=1000)
            if not info or not info.parsed_addresses():
                continue

            properties = {
                key.decode("utf-8", "replace"): value.decode("utf-8", "replace")
                for key, value in info.properties.items()
            }
            host = info.parsed_addresses()[0]
            resource_path = properties.get("rp", "ipp/print").lstrip("/")
            if service_type.startswith("_ipps"):
                uri = f"ipps://{host}:{info.port}/{resource_path}"
            elif service_type.startswith("_ipp"):
                uri = f"ipp://{host}:{info.port}/{resource_path}"
            elif service_type.startswith("_pdl-datastream"):
                uri = f"socket://{host}:{info.port}"
            else:
                uri = f"lpd://{host}:{info.port}"
            printers.append({
                "name": properties.get("ty") or name.removesuffix(f".{service_type}"),
                "model": properties.get("ty") or properties.get("product") or "Unknown model",
                "host": host,
                "uri": uri,
                "discovery_source": "Bonjour",
            })
        return printers
    finally:
        zeroconf.close()


def discover_printers(options: Dict[str, Any]) -> List[Dict[str, str]]:
    discovered = list(options.get("discovered_printers") or [])
    printer_host = options.get("printer_host") or ""
    printer_uri = options.get("printer_uri") or ""
    printer_name = options.get("printer_name") or ""

    if printer_host or printer_uri or printer_name:
        discovered.append(
            {
                "name": printer_name or "Configured printer",
                "host": printer_host,
                "uri": printer_uri,
            }
        )

    discovered.extend(discover_mdns_printers())

    candidate_hosts = get_candidate_hosts()
    for host in candidate_hosts:
        probe = probe_printer_host(host)
        if probe:
            discovered.append(probe)

    seen = set()
    unique: List[Dict[str, str]] = []
    for entry in discovered:
        key = (entry.get("name", ""), entry.get("host", ""), entry.get("uri", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique


def load_options(path: str) -> Dict[str, Any]:
    defaults = build_default_options()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        defaults.update(loaded)

    defaults = apply_environment_overrides(defaults)
    return defaults


def save_options(path: str, options: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(options, handle, indent=2)


def build_test_page(options: Dict[str, Any]) -> str:
    text = options.get("test_page_text") or "Inkjet Conditioner maintenance print"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{text}\nGenerated: {now}\n"


def write_job_file(content: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    job_path = output_dir / f"print-job-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.txt"
    with open(job_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return job_path


def get_storage_paths() -> Dict[str, Path]:
    appdata_root = Path(os.environ.get("APPDATA_DIR", "/config"))
    documents_root = Path(os.environ.get("DOCUMENTS_DIR", "/share"))
    uploads_dir = appdata_root / "uploads"
    print_jobs_dir = appdata_root / "print-jobs"
    return {
        "appdata": appdata_root,
        "documents": documents_root,
        "uploads": uploads_dir,
        "print_jobs": print_jobs_dir,
    }


def save_uploaded_document(file_obj: Any, filename: str, target_dir: str | None = None) -> str:
    storage = get_storage_paths()
    upload_dir = Path(target_dir) if target_dir else storage["uploads"]
    upload_dir.mkdir(parents=True, exist_ok=True)
    target_path = upload_dir / filename
    if hasattr(file_obj, "read"):
        with open(target_path, "wb") as handle:
            handle.write(file_obj.read())
    else:
        with open(target_path, "wb") as handle:
            handle.write(file_obj)
    return str(target_path)


def print_document(options: Dict[str, Any], document_path: str | None = None) -> Dict[str, Any]:
    printer = resolve_printer_target(options)
    storage = get_storage_paths()
    content = build_test_page(options)
    job_path = None

    if document_path:
        path = Path(document_path)
        if path.exists() and path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".ps", ".txt"}:
            if path.suffix.lower() == ".txt":
                content = path.read_text(encoding="utf-8")
                job_path = write_job_file(content, storage["print_jobs"])
            else:
                job_path = path
        else:
            content = f"Requested document not found: {document_path}\n"
            job_path = write_job_file(content, storage["print_jobs"])
    else:
        job_path = write_job_file(content, storage["print_jobs"])

    uploaded_name = options.get("uploaded_document_name") or ""
    if uploaded_name and not document_path:
        content = f"Uploaded document: {uploaded_name}\n\n{content}"

    command = None
    if printer.get("uri"):
        if job_path and job_path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".ps"}:
            command = ["sh", "-c", f"lp -d {printer['name']} {job_path}"]
        else:
            command = ["sh", "-c", f"echo '{content.replace(chr(39), chr(92)+chr(39))}' | lp -d {printer['name']}" ]
    elif shutil.which("lp"):
        command = ["lp", "-d", printer.get("name", "default"), str(job_path)]

    if command:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    return {
        "status": "queued",
        "printer": printer,
        "job_path": str(job_path),
        "mode": "test-page" if not document_path else "document",
    }


def run_scheduler(options: Dict[str, Any], now: str | None = None) -> Dict[str, Any]:
    if not options.get("schedule_enabled", False):
        return {"status": "disabled"}

    if not should_run_now(options, now):
        return {"status": "skipped"}

    result = print_document(options, options.get("document_path") or None)
    options["last_run"] = now or datetime.utcnow().replace(microsecond=0).isoformat()
    return result


def refresh_discovered_printers(options_path: str) -> None:
    options = load_options(options_path)
    options["discovered_printers"] = discover_printers(options)
    save_options(options_path, options)


def build_login_page(error: str = "") -> str:
    error_html = f'<p class="error">{escape(error)}</p>' if error else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Sign in | Inkjet Conditioner</title><style>
      :root {{ --ink:#182b38;--paper:#f5f4ed;--lime:#d9f067;--coral:#ed765d;--muted:#60727a; }} * {{ box-sizing:border-box; }} body {{ min-height:100vh;margin:0;display:grid;place-items:center;padding:24px;background-color:var(--paper);background-image:linear-gradient(#dfe6df 1px,transparent 1px),linear-gradient(90deg,#dfe6df 1px,transparent 1px);background-size:32px 32px;color:var(--ink);font-family:Avenir Next,Avenir,Futura,sans-serif; }} main {{ width:min(100%,430px);border:1px solid #cad5cd;border-radius:8px;background:white;box-shadow:8px 8px 0 #dfe5d9;padding:36px; }} .brand {{ display:flex;align-items:center;gap:12px;font-size:17px;font-weight:800; }} .mark {{ display:grid;place-items:center;width:38px;height:38px;border:2px solid var(--ink);font-family:Georgia,serif;font-size:19px; }} h1 {{ margin:42px 0 9px;font-family:Georgia,serif;font-size:37px;font-weight:400; }} p {{ margin:0;color:var(--muted);line-height:1.5; }} form {{ display:grid;gap:17px;margin-top:30px; }} label {{ display:grid;gap:7px;font-size:12px;font-weight:800;text-transform:uppercase; }} input {{ min-height:46px;border:1px solid #bac7c1;border-radius:4px;padding:10px 12px;font:inherit;font-size:16px; }} input:focus {{ outline:3px solid var(--lime);outline-offset:1px;border-color:var(--ink); }} button {{ min-height:46px;margin-top:5px;border:0;border-radius:4px;background:var(--ink);color:white;font:inherit;font-weight:800;cursor:pointer; }} button:hover {{ background:#294555; }} .error {{ margin-top:18px;padding:10px 12px;background:#fff0eb;color:#9a3c2a;font-size:13px;font-weight:700; }} .note {{ margin-top:28px;border-top:1px solid #dbe3dc;padding-top:17px;font-size:12px; }}
    </style></head><body><main><div class="brand"><div class="mark">IC</div>Inkjet Conditioner</div><h1>Welcome back.</h1><p>Sign in to configure your printer maintenance schedule.</p>{error_html}<form method="post" action="/login"><label>Username<input name="username" autocomplete="username" required autofocus></label><label>Password<input type="password" name="password" autocomplete="current-password" required></label><button type="submit">Sign in</button></form><p class="note">Credentials are set in your container configuration.</p></main></body></html>"""


def build_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("WEBUI_SECRET") or token_urlsafe(32)

    @app.before_request
    def require_webui_authentication() -> Any:
        if request.endpoint in {"health", "login"}:
            return None

        if session.get("authenticated"):
            return None

        return redirect(url_for("login"))

    @app.route("/healthz")
    def health() -> Any:
        return jsonify({"status": "ok"})

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Any:
        if request.method == "POST":
            username = os.environ.get("WEBUI_USERNAME", "admin")
            password = os.environ.get("WEBUI_PASSWORD", "inkjet")
            if compare_digest(request.form.get("username", ""), username) and compare_digest(request.form.get("password", ""), password):
                session.clear()
                session["authenticated"] = True
                return redirect(url_for("index"))
            return build_login_page("Incorrect username or password.")
        return build_login_page()

    @app.route("/logout", methods=["POST"])
    def logout() -> Any:
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def index() -> str:
        options_path = os.environ.get("OPTIONS_PATH", "/config/options.json")
        options = load_options(options_path)
        return build_setup_page(options)

    @app.route("/api/setup", methods=["POST"])
    def submit_setup() -> Any:
        options_path = os.environ.get("OPTIONS_PATH", "/config/options.json")
        options = load_options(options_path)
        payload = request.form.to_dict(flat=True)
        uploaded_file = request.files.get("uploaded_file")

        for key in [
            "printer_name",
            "printer_host",
            "printer_uri",
            "test_page_text",
            "document_path",
            "uploaded_document_name",
            "schedule_description",
            "schedule_weekday",
            "schedule_type",
        ]:
            if key in payload and payload[key] not in (None, ""):
                options[key] = payload[key]

        if uploaded_file and uploaded_file.filename:
            saved_path = save_uploaded_document(uploaded_file, uploaded_file.filename)
            options["document_path"] = saved_path
            options["uploaded_document_name"] = uploaded_file.filename

        options["schedule_enabled"] = "schedule_enabled" in payload
        if "schedule_hour" in payload and payload["schedule_hour"] not in (None, ""):
            options["schedule_hour"] = int(payload["schedule_hour"])
        if "schedule_day_of_month" in payload and payload["schedule_day_of_month"] not in (None, ""):
            options["schedule_day_of_month"] = int(payload["schedule_day_of_month"])

        options["discovered_printers"] = discover_printers(options)
        result = print_document(options, options.get("document_path") or None)
        options["setup_complete"] = result.get("status") == "queued"
        save_options(options_path, options)
        return jsonify({"status": "ok", "result": result, "setup_complete": options["setup_complete"]})

    @app.route("/api/printers")
    def printers() -> Any:
        options_path = os.environ.get("OPTIONS_PATH", "/config/options.json")
        options = load_options(options_path)
        return jsonify({"printers": options.get("discovered_printers", [])})

    return app


def main() -> int:
    options_path = os.environ.get("OPTIONS_PATH", "/config/options.json")
    options = load_options(options_path)
    options = apply_environment_overrides(options)
    save_options(options_path, options)

    Thread(target=refresh_discovered_printers, args=(options_path,), daemon=True).start()

    port = get_webui_port(options)
    app = build_app()

    print("Inkjet Conditioner started")
    print(json.dumps({"status": "running", "configured_printer": resolve_printer_target(options).get("name")}, indent=2))
    print(json.dumps({"printers": options.get("discovered_printers", [])}, indent=2))
    print(json.dumps({"setup_complete": is_setup_complete(options)}, indent=2))
    if options.get("schedule_description"):
        print(json.dumps({"schedule": options["schedule_description"]}, indent=2))
    print(json.dumps({"webui_port": port}, indent=2))

    if options.get("schedule_enabled", False) and is_setup_complete(options):
        result = run_scheduler(options)
        print(json.dumps(result, indent=2))

    app.run(host="0.0.0.0", port=port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
