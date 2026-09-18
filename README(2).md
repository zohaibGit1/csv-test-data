# CSV to Google Sheets Synchronization System

A Python automation project that reads weekly Sales and Purchase CSV files and synchronizes their data with corresponding Google Sheets worksheets.

The system supports **insert**, **update**, and **duplicate prevention** using unique record IDs.

## Features

- Read multiple weekly Sales CSV files.
- Read multiple weekly Purchase CSV files.
- Combine data from multiple CSV files using pandas.
- Connect to Google Sheets using a Google Service Account.
- Synchronize Sales data with the `Sales` worksheet.
- Synchronize Purchase data with the `Purchase` worksheet.
- Insert new records automatically.
- Update existing records when their values change.
- Skip records that are already up to date.
- Prevent duplicate records using unique IDs.
- Validate configuration, CSV columns, missing IDs, and duplicate IDs.
- Use environment variables through `.env`.
- Provide informative logging during synchronization.

## Project Structure

```text
CSV-to-Google-Sheets_Synchronization_System/
│
├── data/
│   ├── sales/
│   │   ├── sales_week1.csv
│   │   └── sales_week2.csv
│   │
│   └── purchase/
│       ├── purchase_week1.csv
│       └── purchase_week2.csv
│
├── credentials/
│   └── service-account.json
│
├── main.py
├── csv_processor.py
├── google_sheet.py
├── upload_data.py
├── sync.py
├── .env
├── .gitignore
└── README.md
```

## Technologies Used

- Python 3
- pandas
- gspread
- google-auth
- python-dotenv
- Google Sheets API
- Google Drive API

## CSV Data Format

### Sales

```text
sale_id,sale_date,product,quantity,unit_price,total_amount
```

### Purchase

```text
purchase_id,purchase_date,product,quantity,unit_price,total_amount
```

The unique keys are `sale_id` for Sales and `purchase_id` for Purchase.

## Synchronization Logic

For each CSV record, the script checks whether the unique ID already exists in Google Sheets.

```text
CSV Record
    |
    v
Find ID in Google Sheet
    |
    +-- ID not found ------> INSERT
    |
    +-- ID found
          |
          +-- Values changed --> UPDATE
          |
          +-- Values same -----> SKIP
```

This allows the script to synchronize new and changed records without creating duplicates.

## Prerequisites

You need:

- Python 3
- A Google Cloud project
- A Google Service Account
- Google Sheets API enabled
- Google Drive API enabled
- A Google Spreadsheet shared with the Service Account

## Installation

Create and activate a virtual environment:

```bash
python3 -m venv sheets
source sheets/bin/activate
```

Install dependencies:

```bash
pip install pandas gspread google-auth python-dotenv
```

## Google Service Account Setup

Create a Google Service Account and download its JSON credentials.

Place the credentials file at:

```text
credentials/service-account.json
```

Share the target Google Spreadsheet with the Service Account email and grant the required access.

**Never commit the Service Account JSON file or private key to GitHub.**

## Environment Configuration

Create a `.env` file in the project root:

```env
GOOGLE_SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit
GOOGLE_CREDENTIALS_FILE=credentials/service-account.json
```

Keeping these values in `.env` prevents sensitive configuration from being hard-coded in the source code.

## Running the Project

Activate the virtual environment:

```bash
source sheets/bin/activate
```

Run the synchronization script:

```bash
python3 sync.py
```

The script will:

1. Validate configuration.
2. Connect to Google Sheets.
3. Read Sales CSV files.
4. Read Purchase CSV files.
5. Validate the data.
6. Compare CSV records with Google Sheets.
7. Insert new records.
8. Update changed records.
9. Skip unchanged records.
10. Log the synchronization results.

## Example Output

When the Google Sheets data is already synchronized:

```text
INFO: Connected to Google Sheets.
INFO: Starting sales synchronization...
INFO: Existing sales records: 11
INFO: CSV sales records: 11
INFO: No new sales records to insert.
INFO: No updated sales records.
INFO: sales synchronization completed. Inserted: 0 | Updated: 0

INFO: Starting purchase synchronization...
INFO: Existing purchase records: 11
INFO: CSV purchase records: 11
INFO: No new purchase records to insert.
INFO: No updated purchase records.
INFO: purchase synchronization completed. Inserted: 0 | Updated: 0
```

When an existing record changes:

```text
INFO: Updated sales: 1006
INFO: sales synchronization completed. Inserted: 0 | Updated: 1
```

When a new record is added:

```text
INFO: Inserted sales record: 1011
INFO: sales synchronization completed. Inserted: 1 | Updated: 0
```

## Testing

### New Record Test

Add a new unique ID to a CSV file and run:

```bash
python3 sync.py
```

The script should insert the new record.

Run it again without changing the CSV. The same record should not be inserted again.

### Update Test

Change the values of an existing record while keeping the same ID.

For example:

```csv
1006,2026-09-08,Laptop,1,60000,60000
```

Change it to:

```csv
1006,2026-09-08,Laptop,1,65000,65000
```

Run:

```bash
python3 sync.py
```

The existing Google Sheets record should be updated instead of creating a duplicate.

## Validation and Error Handling

The project validates:

- Required environment variables
- Credential file existence
- Required CSV columns
- Empty CSV data
- Missing unique IDs
- Duplicate IDs inside CSV files
- Google Sheets connectivity
- Records that cannot be found during an update

The script uses logging to make synchronization activity and errors easy to understand.

## Security

Recommended `.gitignore`:

```gitignore
.env
credentials/
__pycache__/
*.py[cod]
.venv/
venv/
.DS_Store
```

Do not commit:

- `.env`
- `credentials/service-account.json`
- Service Account private keys

If credentials are accidentally exposed publicly, revoke or rotate them.

## Future Improvements

Possible production improvements:

- Batch Google Sheets API operations to reduce API calls.
- Add retry logic for temporary API failures.
- Add `argparse` command-line options.
- Add unit and integration tests.
- Add structured logging.
- Add scheduled automatic synchronization.
- Separate CSV processing, Google Sheets access, and synchronization logic into dedicated modules.
- Add CI/CD with GitHub Actions.
- Add development and production configuration.

## Project Status

**Core CSV-to-Google-Sheets synchronization functionality is implemented and tested.**

The system successfully handles:

- New records
- Updated records
- Unchanged records
- Duplicate prevention
- Sales synchronization
- Purchase synchronization
