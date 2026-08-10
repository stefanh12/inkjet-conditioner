# Inkjet Conditioner

This Home Assistant add-on provides a simple starting point for:
- discovering network printers,
- printing a test page,
- scheduling recurring print jobs from a file or text content.

## Install in Home Assistant

1. Open Home Assistant and go to Settings > Add-ons > Add-on Store.
2. Click the three-dot menu in the upper-right corner and choose Repository URL.
3. Add this repository:
   - https://github.com/stefanh12/inkjet-conditioner
4. Refresh the add-on store and install Inkjet Conditioner.
5. Start the add-on and open the Configuration tab.

## Configuration

You do not need to edit any JSON files manually. After installing the add-on, open the add-on in Home Assistant and use the Configuration tab to enter your values.

Set the printer details in the add-on options:
- printer_name: human-readable printer name
- printer_host: hostname or IP address
- printer_uri: optional printer URI used by your print backend
- test_page_text: text printed in a simple test page
- document_path: path to a file to print
- uploaded_document_name: a friendly name for a document uploaded to the add-on data directory
- schedule_enabled: whether recurring printing is enabled
- schedule_type: one of daily, weekly, or monthly
- schedule_hour: hour of day when the job should run
- schedule_weekday: weekday for weekly schedules
- schedule_day_of_month: day of month for monthly schedules
- schedule_description: a description shown in the add-on logs and options

### Example values for the Configuration form

- Printer name: Office Printer
- Printer host: 192.168.1.50
- Printer URI: ipp://192.168.1.50/ipp/print
- Test page text: Home Assistant test page
- Document path: /share/print-jobs/example.txt
- Uploaded document name: example.txt
- Schedule enabled: enabled
- Schedule type: weekly
- Schedule hour: 8
- Schedule weekday: monday
- Schedule day of month: 1
- Schedule description: Print every Monday at 08:00

## Usage

- Start the add-on once to let it discover nearby printers.
- Review the add-on logs to see which printers were detected.
- Use the printer settings to choose the printer you want to target.
- Use the test page text or document path to define what should be printed.

## Notes

The first version is intentionally simple and uses a built-in scheduler module instead of a full printer backend. In a real deployment you would replace the placeholder print logic with a backend such as CUPS, IPP, or Samba printing.
