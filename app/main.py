import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


def build_default_options() -> Dict[str, Any]:
    return {
        "printer_name": "",
        "printer_host": "",
        "printer_uri": "",
        "test_page_text": "Home Assistant printer test page",
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
    }


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
                    "host": host,
                    "uri": f"ipp://{host}/ipp/print",
                }
        except OSError:
            continue

    return None


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
    if not os.path.exists(path):
        return build_default_options()

    with open(path, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)

    defaults = build_default_options()
    defaults.update(loaded)
    return defaults


def save_options(path: str, options: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(options, handle, indent=2)


def build_test_page(options: Dict[str, Any]) -> str:
    text = options.get("test_page_text") or "Home Assistant printer test page"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{text}\nGenerated: {now}\n"


def write_job_file(content: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    job_path = output_dir / f"print-job-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.txt"
    with open(job_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return job_path


def print_document(options: Dict[str, Any], document_path: str | None = None) -> Dict[str, Any]:
    printer = resolve_printer_target(options)
    content = build_test_page(options)

    if document_path:
        path = Path(document_path)
        if path.exists():
            content = path.read_text(encoding="utf-8")
        else:
            content = f"Requested document not found: {document_path}\n"

    output_dir = Path(os.environ.get("ADDON_DATA_DIR", "/data")) / "print-jobs"
    job_path = write_job_file(content, output_dir)
    uploaded_name = options.get("uploaded_document_name") or ""
    if uploaded_name:
        content = f"Uploaded document: {uploaded_name}\n\n{content}"

    command = None
    if printer.get("uri"):
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


def main() -> int:
    options_path = os.environ.get("OPTIONS_PATH", "/data/options.json")
    options = load_options(options_path)
    options["discovered_printers"] = discover_printers(options)
    save_options(options_path, options)

    print("Inkjet Conditioner add-on started")
    print(json.dumps({"printers": options["discovered_printers"]}, indent=2))
    if options.get("schedule_description"):
        print(json.dumps({"schedule": options["schedule_description"]}, indent=2))

    if options.get("schedule_enabled", False):
        result = run_scheduler(options)
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
