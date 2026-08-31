# Inkjet Conditioner

Inkjet Conditioner is a small Docker app for:
- discovering printers on the local network,
- printing a small maintenance page to help prevent inkjet nozzle clogs,
- scheduling recurring maintenance prints from a file or text content,
- running on an always-on server such as Unraid.

## Unraid Support

Unraid is the supported deployment target. The Community Apps template is [inkjet-conditioner.xml](inkjet-conditioner.xml).

1. In Unraid, open **Docker** and select **Add Container**.
2. Import the template or use its `TemplateURL` after publishing this repository.
3. Keep the network type set to `host`.
4. Set a unique `WEBUI_PASSWORD`.
5. Start the container and open `http://UNRAID-IP:8000`.

The initial login is `admin` / `inkjet`. Change these template values before exposing the Web UI outside a trusted network.

### Required mappings

| Unraid host path | Container path | Purpose |
| --- | --- | --- |
| `/mnt/user/appdata/inkjet-conditioner` | `/config` | Persistent configuration, uploads, and generated print jobs. |
| `/mnt/user/print-jobs` | `/share` | Optional maintenance documents stored on the array or cache. |

Do not map appdata to `/data`; the container stores persistent state at `/config`.

### Networking and discovery

Use `host` networking for automatic printer discovery. It lets the container receive Bonjour/mDNS announcements and scan the Unraid LAN subnet for IPP, IPPS, LPR, and JetDirect/raw printers.

Bridge, macvlan, ipvlan, and custom networks can print to a manually entered printer IP or URI, but automatic discovery is not guaranteed because multicast traffic may not reach the container.

If no printer appears, wait a few seconds after startup, use **Refresh discovery** in the Web UI, then confirm that the printer and Unraid server are on a routable LAN. Manual printer host and URI fields remain available.

## Local Docker development

```bash
docker build -t inkjet-conditioner .
docker run --rm -p 8000:8000 \
  -e PRINTER_NAME="Office Printer" \
  -e PRINTER_HOST="192.168.1.50" \
  -e PRINTER_URI="ipp://192.168.1.50/ipp/print" \
  -e TEST_PAGE_TEXT="Inkjet Conditioner maintenance print" \
  -v /path/to/appdata:/config \
  -v /path/to/shared/prints:/share \
  inkjet-conditioner
```

### Docker Compose example

```yaml
services:
  inkjet-conditioner:
    build: .
    container_name: inkjet-conditioner
    ports:
      - "8000:8000"
    environment:
      WEBUI_PORT: "8000"
      PRINTER_NAME: "Office Printer"
      PRINTER_HOST: "192.168.1.50"
      PRINTER_URI: "ipp://192.168.1.50/ipp/print"
      TEST_PAGE_TEXT: "Inkjet Conditioner maintenance print"
      SCHEDULE_ENABLED: "true"
      SCHEDULE_TYPE: "weekly"
      SCHEDULE_HOUR: "8"
      SCHEDULE_WEEKDAY: "monday"
    volumes:
      - /mnt/user/appdata/inkjet-conditioner:/config
      - /mnt/user/print-jobs:/share
    network_mode: host
```

## Unraid configuration

The app accepts these environment variables for Unraid and Docker deployments:

- `PRINTER_NAME`: human-readable printer name
- `PRINTER_HOST`: hostname or IP address
- `PRINTER_URI`: printer URI used by the print backend
- `TEST_PAGE_TEXT`: text printed in the maintenance page
- `DOCUMENT_PATH`: path to a file to print
- `UPLOADED_DOCUMENT_NAME`: friendly name for a file stored in the appdata directory
- `SCHEDULE_ENABLED`: `true` or `false`
- `SCHEDULE_TYPE`: `daily`, `weekly`, or `monthly`
- `SCHEDULE_HOUR`: hour of day when the job should run
- `SCHEDULE_WEEKDAY`: `monday` through `sunday`
- `SCHEDULE_DAY_OF_MONTH`: day of month for monthly schedules
- `SCHEDULE_DESCRIPTION`: friendly description shown in logs
- `WEBUI_PORT`: optional port override, default is `8000`
- `WEBUI_USERNAME`: Web UI login username, default is `admin`
- `WEBUI_PASSWORD`: Web UI login password, default is `inkjet`; set a unique value before exposing the Web UI outside your trusted network
- `WEBUI_SECRET`: optional persistent signing secret for login sessions; generate a random value for production
- `OPTIONS_PATH`: optional config file path, default is `/config/options.json`

## Example Unraid config

```text
PRINTER_NAME=Office Printer
PRINTER_HOST=192.168.1.50
PRINTER_URI=ipp://192.168.1.50/ipp/print
TEST_PAGE_TEXT=Inkjet Conditioner maintenance print
DOCUMENT_PATH=/share/print-jobs/example.txt
UPLOADED_DOCUMENT_NAME=example.txt
SCHEDULE_ENABLED=true
SCHEDULE_TYPE=weekly
SCHEDULE_HOUR=8
SCHEDULE_WEEKDAY=monday
SCHEDULE_DAY_OF_MONTH=1
SCHEDULE_DESCRIPTION=Print every Monday at 08:00
```

## Operating the container

- Start the container once so it can inspect the local network and discover nearby printers.
- Review the container logs to see which printers were detected.
- Choose the target printer by setting the host or URI.
- Use the maintenance-print text or document path to define what should print.

## Troubleshooting

- **The Web UI does not open:** verify port `8000` is free on Unraid. With host networking, browse directly to the configured Unraid port; do not add a bridge-style port mapping.
- **Settings or uploads disappear:** confirm `/config` maps to `/mnt/user/appdata/inkjet-conditioner` with read/write access.
- **A document cannot print:** verify it exists beneath `/share` or was uploaded through the Web UI, then confirm the selected printer address or URI.

## Notes

The current implementation intentionally stays lightweight and uses a built-in scheduler instead of a full print backend. For more advanced production environments, a future upgrade could add CUPS, IPP, or Samba-based printing support while keeping the same core service behavior.

## Development

For local development in VS Code, you can run the project directly with Python and use the test suite:

```bash
python -m unittest discover -s tests -v
```
