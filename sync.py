import json
import logging
import os
import random
import time
from io import StringIO
from pathlib import Path

import certifi
import gspread
import pandas as pd
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError


# ============================================================
# Configuration
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

CREDENTIALS_FILE = BASE_DIR / os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    "credentials/service-account.json",
)

MAP_FILE = BASE_DIR / "map.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Google Sheets can return 429 when the write quota is temporarily exceeded.
# These settings make the script retry instead of failing immediately.
MAX_RETRIES = 5
INITIAL_RETRY_WAIT = 2
MAX_RETRY_WAIT = 60

# Keep the batch reasonably sized. For the current small CSVs, everything
# will normally be uploaded in a single batch.
MAX_ROWS_PER_BATCH = 500
MAX_UPDATES_PER_BATCH = 100


# ============================================================
# Logging Configuration
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# Google Sheets API Retry
# ============================================================

def execute_with_retry(operation, operation_name):
    """
    Execute a Google Sheets API operation and retry temporary 429
    quota errors using exponential backoff.

    Example waits:
        2s -> 4s -> 8s -> 16s -> 32s
    """

    for attempt in range(MAX_RETRIES + 1):
        try:
            return operation()

        except APIError as exc:
            status_code = getattr(
                getattr(exc, "response", None),
                "status_code",
                None,
            )

            error_text = str(exc)

            is_quota_error = (
                status_code == 429
                or "[429]" in error_text
                or "429" in error_text
                or "Quota exceeded" in error_text
            )

            if not is_quota_error:
                raise

            if attempt >= MAX_RETRIES:
                logger.error(
                    "%s failed after %d retries because the "
                    "Google Sheets write quota is still exceeded.",
                    operation_name,
                    MAX_RETRIES,
                )
                raise

            base_wait = min(
                INITIAL_RETRY_WAIT * (2 ** attempt),
                MAX_RETRY_WAIT,
            )

            # Small random delay prevents repeated requests from hitting
            # the quota boundary at exactly the same time.
            wait_time = base_wait + random.uniform(0, 1)

            logger.warning(
                "%s hit Google Sheets quota (429). "
                "Retry %d/%d in %.1f seconds...",
                operation_name,
                attempt + 1,
                MAX_RETRIES,
                wait_time,
            )

            time.sleep(wait_time)

    raise RuntimeError(f"{operation_name} failed unexpectedly.")


# ============================================================
# Validate Configuration
# ============================================================

def validate_configuration():
    """
    Validate required environment variables and credentials file.
    """

    if not os.getenv("GOOGLE_CREDENTIALS_FILE"):
        raise ValueError(
            "GOOGLE_CREDENTIALS_FILE is not configured in .env"
        )

    if not MAP_FILE.is_file():
        raise FileNotFoundError(
            f"map.json not found: {MAP_FILE}"
        )

    if not CREDENTIALS_FILE.is_file():
        raise FileNotFoundError(
            f"Credentials file not found: {CREDENTIALS_FILE}"
        )

    logger.info("Configuration validation successful.")


# ============================================================
# Google Sheets Connection
# ============================================================

def connect_to_google_sheets(spreadsheet_url):
    """
    Authenticate and connect to the Google Spreadsheet.
    """

    credentials = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
    )

    client = gspread.authorize(credentials)

    spreadsheet = execute_with_retry(
        lambda: client.open_by_url(spreadsheet_url),
        "Open Google Spreadsheet",
    )

    logger.info("Connected to Google Sheets.")

    return spreadsheet


# ============================================================
# Load map.json
# ============================================================

def load_map_config():
    """
    Load and validate synchronization configuration from map.json.
    """

    try:
        with MAP_FILE.open("r", encoding="utf-8") as file:
            config = json.load(file)

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in map.json: {exc}"
        ) from exc

    if not isinstance(config, dict):
        raise ValueError(
            "map.json must contain a JSON object."
        )

    if not config.get("spreadsheet_url"):
        raise ValueError(
            "spreadsheet_url is missing in map.json."
        )

    datasets = config.get("datasets")

    if not isinstance(datasets, list):
        raise ValueError(
            "datasets must be a list in map.json."
        )

    if not datasets:
        raise ValueError(
            "At least one dataset must be configured."
        )

    for dataset in datasets:

        if not isinstance(dataset, dict):
            raise ValueError(
                "Each dataset must be a JSON object."
            )

        required_fields = [
            "name",
            "worksheet",
            "id_column",
            "csv_urls",
        ]

        for field in required_fields:

            if not dataset.get(field):
                raise ValueError(
                    f"'{field}' is missing "
                    f"in dataset configuration."
                )

        csv_urls = dataset["csv_urls"]

        if not isinstance(csv_urls, list):
            raise ValueError(
                f"csv_urls must be a list for "
                f"dataset '{dataset['name']}."
            )

        if not csv_urls:
            raise ValueError(
                f"At least one CSV URL is required "
                f"for dataset '{dataset['name']}'."
            )

        for csv_url in csv_urls:

            if not isinstance(csv_url, str) or not csv_url.strip():
                raise ValueError(
                    f"Invalid CSV URL found for "
                    f"dataset '{dataset['name']}'."
                )

    logger.info("Loaded configuration from map.json.")

    return config


# ============================================================
# CSV Loading
# ============================================================

def load_csv_files(csv_urls):
    """
    Download multiple CSV files from URLs and combine them.

    requests + certifi is used instead of passing the URL directly
    to pandas.read_csv() because the local Python installation may
    have certificate-chain issues with urllib.
    """

    dataframes = []

    for csv_url in csv_urls:

        csv_url = csv_url.strip()

        logger.info("Reading CSV: %s", csv_url)

        try:
            response = requests.get(
                csv_url,
                timeout=30,
                verify=certifi.where(),
                headers={
                    "User-Agent": "CSV-Google-Sheets-Sync/1.0"
                },
            )

            response.raise_for_status()

            if not response.text.strip():
                raise ValueError("The downloaded CSV is empty.")

            dataframe = pd.read_csv(
                StringIO(response.text)
            )

        except requests.exceptions.SSLError as exc:
            raise RuntimeError(
                f"SSL certificate verification failed for CSV URL: "
                f"{csv_url}. requests/certifi could not verify "
                f"the server certificate."
            ) from exc

        except requests.exceptions.Timeout as exc:
            raise RuntimeError(
                f"Timed out while downloading CSV URL: {csv_url}"
            ) from exc

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Could not download CSV URL: {csv_url}. "
                f"HTTP/network error: {exc}"
            ) from exc

        except Exception as exc:
            raise RuntimeError(
                f"Could not parse CSV URL: {csv_url}. "
                f"Reason: {exc}"
            ) from exc

        # Remove accidental whitespace from CSV column names.
        dataframe.columns = [
            str(column).strip()
            for column in dataframe.columns
        ]

        if dataframe.empty:
            logger.warning(
                "CSV is empty: %s",
                csv_url,
            )
        else:
            logger.info(
                "Loaded %d records from %s",
                len(dataframe),
                csv_url,
            )

        dataframes.append(dataframe)

    if not dataframes:
        return pd.DataFrame()

    combined = pd.concat(
        dataframes,
        ignore_index=True,
    )

    return combined


# ============================================================
# Data Validation
# ============================================================

def validate_dataset(dataframe, id_column, record_type):
    """
    Validate the CSV data before synchronization.
    """

    if dataframe.empty:
        logger.warning(
            "No data found for %s.",
            record_type,
        )
        return

    if id_column not in dataframe.columns:
        raise ValueError(
            f"Required ID column '{id_column}' is missing "
            f"from {record_type} CSV data. "
            f"Available columns: {list(dataframe.columns)}"
        )

    # Treat IDs consistently as strings.
    dataframe[id_column] = (
        dataframe[id_column]
        .astype(str)
        .str.strip()
    )

    if (dataframe[id_column] == "").any():
        raise ValueError(
            f"Blank {id_column} value found in "
            f"{record_type} CSV data."
        )

    if dataframe[id_column].duplicated().any():
        duplicate_ids = (
            dataframe.loc[
                dataframe[id_column].duplicated(keep=False),
                id_column,
            ]
            .unique()
            .tolist()
        )

        raise ValueError(
            f"Duplicate {id_column} values found in "
            f"{record_type} CSV data: {duplicate_ids}"
        )

    logger.info(
        "%s data validation successful.",
        record_type.capitalize(),
    )


# ============================================================
# Helpers
# ============================================================

def normalize_value(value):
    """
    Convert a value into a comparable string.
    """

    if pd.isna(value):
        return ""

    return str(value).strip()


def dataframe_to_values(dataframe):
    """
    Convert a DataFrame into Google Sheets-compatible row values.
    """

    values = []

    for _, row in dataframe.iterrows():
        values.append([
            "" if pd.isna(value) else value
            for value in row.tolist()
        ])

    return values


def get_column_letter(column_number):
    """
    Convert a column number to an Excel-style column letter.

    Examples:
        1  -> A
        6  -> F
        27 -> AA
    """

    result = ""

    while column_number > 0:

        column_number, remainder = divmod(
            column_number - 1,
            26,
        )

        result = (
            chr(65 + remainder)
            + result
        )

    return result


# ============================================================
# Read Existing Google Sheet Data
# ============================================================

def get_existing_data(sheet, id_column):
    """
    Read the worksheet once and build:

        1. Existing DataFrame
        2. ID -> actual Google Sheets row number mapping

    This avoids calling sheet.find() once for every update.
    """

    all_values = execute_with_retry(
        lambda: sheet.get_all_values(),
        f"Read worksheet '{sheet.title}'",
    )

    if not all_values:
        return pd.DataFrame(), {}

    headers = [
        str(header).strip()
        for header in all_values[0]
    ]

    if not any(headers):
        return pd.DataFrame(), {}

    if id_column not in headers:
        raise ValueError(
            f"ID column '{id_column}' is missing from worksheet "
            f"'{sheet.title}'. Headers: {headers}"
        )

    data_rows = all_values[1:]

    if not data_rows:
        return (
            pd.DataFrame(columns=headers),
            {},
        )

    # Make every row the same length as the headers.
    normalized_rows = []

    for row in data_rows:

        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))

        elif len(row) > len(headers):
            row = row[:len(headers)]

        normalized_rows.append(row)

    dataframe = pd.DataFrame(
        normalized_rows,
        columns=headers,
    )

    id_index = headers.index(id_column)

    id_to_row = {}

    for offset, row in enumerate(normalized_rows, start=2):

        record_id = normalize_value(
            row[id_index]
        )

        if not record_id:
            # Ignore completely blank ID rows.
            continue

        if record_id in id_to_row:
            raise ValueError(
                f"Duplicate {id_column} '{record_id}' found "
                f"in worksheet '{sheet.title}'."
            )

        id_to_row[record_id] = offset

    return dataframe, id_to_row


# ============================================================
# Validate / Prepare Worksheet Headers
# ============================================================

def ensure_sheet_headers(sheet, dataframe, id_column):
    """
    Check worksheet headers.

    Returns:
        True  -> worksheet was completely empty and headers/data
                 should be written together.
        False -> worksheet already has headers.
    """

    if dataframe.empty:
        return False

    csv_headers = [
        str(column).strip()
        for column in dataframe.columns
    ]

    all_values = execute_with_retry(
        lambda: sheet.get_all_values(),
        f"Read headers from worksheet '{sheet.title}'",
    )

    if not all_values:
        logger.info(
            "Worksheet '%s' is completely empty.",
            sheet.title,
        )

        return True

    sheet_headers = [
        str(header).strip()
        for header in all_values[0]
    ]

    if not any(sheet_headers):
        return True

    if sheet_headers != csv_headers:
        raise ValueError(
            f"Header mismatch in worksheet '{sheet.title}'. "
            f"Google Sheet headers: {sheet_headers}; "
            f"CSV headers: {csv_headers}"
        )

    if id_column not in sheet_headers:
        raise ValueError(
            f"ID column '{id_column}' is missing from worksheet "
            f"'{sheet.title}'."
        )

    return False


# ============================================================
# Find New Records
# ============================================================

def find_new_records(
    new_df,
    existing_df,
    id_column,
):
    """
    Find records whose unique ID does not exist
    in the Google Sheet.
    """

    if existing_df.empty:
        return new_df.copy()

    existing_ids = set(
        existing_df[id_column]
        .astype(str)
        .str.strip()
    )

    new_ids = (
        new_df[id_column]
        .astype(str)
        .str.strip()
    )

    return new_df[
        ~new_ids.isin(existing_ids)
    ].copy()


# ============================================================
# Find Updated Records
# ============================================================

def find_updated_records(
    new_df,
    existing_df,
    id_column,
):
    """
    Find records where the ID already exists but one or more
    values changed.

    Comparison is performed by column name.
    """

    if existing_df.empty:
        return pd.DataFrame(
            columns=new_df.columns
        )

    if id_column not in existing_df.columns:
        raise ValueError(
            f"ID column '{id_column}' is missing "
            f"from the Google Sheet."
        )

    missing_columns = [
        column
        for column in new_df.columns
        if column not in existing_df.columns
    ]

    if missing_columns:
        raise ValueError(
            "The following CSV columns are missing from "
            f"the Google Sheet: {missing_columns}"
        )

    existing_lookup = existing_df.copy()

    existing_lookup[id_column] = (
        existing_lookup[id_column]
        .astype(str)
        .str.strip()
    )

    # Dictionary lookup is much faster than filtering the
    # DataFrame for every CSV row.
    existing_by_id = {
        normalize_value(row[id_column]): row
        for _, row in existing_lookup.iterrows()
    }

    comparable_columns = [
        column
        for column in new_df.columns
        if column in existing_lookup.columns
    ]

    updated_records = []

    for _, new_row in new_df.iterrows():

        record_id = normalize_value(
            new_row[id_column]
        )

        old_row = existing_by_id.get(record_id)

        if old_row is None:
            continue

        changed = any(
            normalize_value(new_row[column])
            != normalize_value(old_row[column])
            for column in comparable_columns
        )

        if changed:
            updated_records.append(
                new_row
            )

    if not updated_records:
        return pd.DataFrame(
            columns=new_df.columns
        )

    return pd.DataFrame(
        updated_records,
        columns=new_df.columns,
    )


# ============================================================
# Insert New Records
# ============================================================

def insert_records(
    sheet,
    records,
    record_type,
):
    """
    Insert new records in batches.

    For normal-sized data, all records are uploaded using one
    append_rows() API request.

    If the dataset is larger than MAX_ROWS_PER_BATCH, it is split
    into multiple batches to keep request payloads manageable.
    """

    if records.empty:
        logger.info(
            "No new %s records to insert.",
            record_type,
        )
        return 0

    values = dataframe_to_values(records)

    total_records = len(values)

    batch_count = (
        (total_records + MAX_ROWS_PER_BATCH - 1)
        // MAX_ROWS_PER_BATCH
    )

    logger.info(
        "Uploading %d new %s records in %d batch request(s)...",
        total_records,
        record_type,
        batch_count,
    )

    inserted_count = 0

    for start in range(
        0,
        total_records,
        MAX_ROWS_PER_BATCH,
    ):

        batch = values[
            start:start + MAX_ROWS_PER_BATCH
        ]

        batch_number = (
            start // MAX_ROWS_PER_BATCH
        ) + 1

        execute_with_retry(
            lambda batch=batch: sheet.append_rows(
                batch,
                value_input_option="USER_ENTERED",
            ),
            (
                f"Insert {record_type} batch "
                f"{batch_number}/{batch_count}"
            ),
        )

        inserted_count += len(batch)

        logger.info(
            "Inserted %d/%d %s records.",
            inserted_count,
            total_records,
            record_type,
        )

    return inserted_count


# ============================================================
# Update Existing Records
# ============================================================

def update_records(
    sheet,
    records,
    record_type,
    id_column,
    id_to_row,
):
    """
    Update changed records using batch_update().

    No sheet.find() calls are made here. The ID -> row mapping
    was already created while reading the worksheet.
    """

    if records.empty:
        logger.info(
            "No updated %s records.",
            record_type,
        )
        return 0

    headers = [
        str(header).strip()
        for header in sheet.row_values(1)
    ]

    if not headers:
        raise ValueError(
            f"Worksheet '{sheet.title}' does not contain "
            "a header row."
        )

    if id_column not in headers:
        raise ValueError(
            f"ID column '{id_column}' is missing from worksheet "
            f"'{sheet.title}'."
        )

    if headers != list(records.columns):
        raise ValueError(
            f"Column order mismatch for worksheet "
            f"'{sheet.title}'. "
            f"Expected: {headers}; "
            f"CSV: {list(records.columns)}"
        )

    batch_updates = []
    skipped_ids = []

    for _, row in records.iterrows():

        record_id = normalize_value(
            row[id_column]
        )

        sheet_row = id_to_row.get(record_id)

        if sheet_row is None:
            skipped_ids.append(record_id)
            continue

        values = dataframe_to_values(
            pd.DataFrame([row])
        )[0]

        end_column = get_column_letter(
            len(values)
        )

        batch_updates.append(
            {
                "range": (
                    f"{sheet.title}!A{sheet_row}:"
                    f"{end_column}{sheet_row}"
                ),
                "values": [values],
            }
        )

    for record_id in skipped_ids:
        logger.warning(
            "%s %s was not found in Google Sheets.",
            record_type.capitalize(),
            record_id,
        )

    if not batch_updates:
        logger.info(
            "No valid %s records found for update.",
            record_type,
        )
        return 0

    total_updates = len(batch_updates)

    batch_count = (
        (total_updates + MAX_UPDATES_PER_BATCH - 1)
        // MAX_UPDATES_PER_BATCH
    )

    logger.info(
        "Updating %d %s records in %d batch request(s)...",
        total_updates,
        record_type,
        batch_count,
    )

    updated_count = 0

    for start in range(
        0,
        total_updates,
        MAX_UPDATES_PER_BATCH,
    ):

        batch = batch_updates[
            start:start + MAX_UPDATES_PER_BATCH
        ]

        batch_number = (
            start // MAX_UPDATES_PER_BATCH
        ) + 1

        execute_with_retry(
            lambda batch=batch: sheet.batch_update(
                batch,
                raw=False,
            ),
            (
                f"Update {record_type} batch "
                f"{batch_number}/{batch_count}"
            ),
        )

        updated_count += len(batch)

        logger.info(
            "Updated %d/%d %s records.",
            updated_count,
            total_updates,
            record_type,
        )

    return updated_count


# ============================================================
# Initial Worksheet Write
# ============================================================

def write_initial_data(
    sheet,
    dataframe,
    record_type,
):
    """
    If the worksheet is completely empty, write headers and all
    CSV records in one API write request.

    This avoids:
        1 request for headers
        +
        1 request for data

    and makes the initial load as efficient as possible.
    """

    headers = [
        str(column).strip()
        for column in dataframe.columns
    ]

    values = dataframe_to_values(dataframe)

    all_values = [headers] + values

    end_column = get_column_letter(
        len(headers)
    )

    end_row = len(all_values)

    logger.info(
        "Worksheet '%s' is empty. "
        "Writing %d %s records + headers in one batch...",
        sheet.title,
        len(values),
        record_type,
    )

    execute_with_retry(
        lambda: sheet.update(
            range_name=f"A1:{end_column}{end_row}",
            values=all_values,
            value_input_option="USER_ENTERED",
        ),
        f"Initial write for {record_type}",
    )

    logger.info(
        "Successfully inserted %d %s records.",
        len(values),
        record_type,
    )

    return len(values)


# ============================================================
# Synchronization
# ============================================================

def sync_data(
    sheet,
    new_df,
    id_column,
    record_type,
):
    """
    Synchronize CSV data with Google Sheets.

    Operations:
        1. If sheet is empty, write headers + all data in one request.
        2. Otherwise read the worksheet once.
        3. INSERT only new records in batch.
        4. UPDATE only changed records in batch.
        5. Skip unchanged records.
        6. Never delete sheet records that are absent from CSV.
    """

    logger.info(
        "Starting %s synchronization...",
        record_type,
    )

    if new_df.empty:
        logger.warning(
            "No CSV data available for %s. "
            "Nothing to synchronize.",
            record_type,
        )
        return

    # Check whether the worksheet is completely empty.
    worksheet_is_empty = ensure_sheet_headers(
        sheet=sheet,
        dataframe=new_df,
        id_column=id_column,
    )

    if worksheet_is_empty:
        inserted_count = write_initial_data(
            sheet=sheet,
            dataframe=new_df,
            record_type=record_type,
        )

        logger.info(
            "%s synchronization completed. "
            "Inserted: %d | Updated: 0",
            record_type,
            inserted_count,
        )

        return

    # One read request gives us both existing data and row numbers.
    existing_df, id_to_row = get_existing_data(
        sheet=sheet,
        id_column=id_column,
    )

    logger.info(
        "Existing %s records: %d",
        record_type,
        len(existing_df),
    )

    logger.info(
        "CSV %s records: %d",
        record_type,
        len(new_df),
    )

    new_records = find_new_records(
        new_df=new_df,
        existing_df=existing_df,
        id_column=id_column,
    )

    updated_records = find_updated_records(
        new_df=new_df,
        existing_df=existing_df,
        id_column=id_column,
    )

    inserted_count = insert_records(
        sheet=sheet,
        records=new_records,
        record_type=record_type,
    )

    updated_count = update_records(
        sheet=sheet,
        records=updated_records,
        record_type=record_type,
        id_column=id_column,
        id_to_row=id_to_row,
    )

    logger.info(
        "%s synchronization completed. "
        "Inserted: %d | Updated: %d | Unchanged: %d",
        record_type,
        inserted_count,
        updated_count,
        max(
            len(new_df)
            - len(new_records)
            - len(updated_records),
            0,
        ),
    )


# ============================================================
# Main Application
# ============================================================

def main():

    try:

        # ----------------------------------------------------
        # Validate configuration
        # ----------------------------------------------------

        validate_configuration()

        # ----------------------------------------------------
        # Load map.json
        # ----------------------------------------------------

        config = load_map_config()

        # ----------------------------------------------------
        # Connect to Google Sheets
        # ----------------------------------------------------

        spreadsheet = connect_to_google_sheets(
            config["spreadsheet_url"]
        )

        # ----------------------------------------------------
        # Process all datasets
        # ----------------------------------------------------

        for dataset in config["datasets"]:

            dataset_name = dataset["name"]
            worksheet_name = dataset["worksheet"]
            id_column = dataset["id_column"]
            csv_urls = dataset["csv_urls"]

            logger.info("=" * 60)

            logger.info(
                "Starting synchronization for: %s",
                dataset_name,
            )

            # ------------------------------------------------
            # Get worksheet
            # ------------------------------------------------

            sheet = execute_with_retry(
                lambda: spreadsheet.worksheet(
                    worksheet_name
                ),
                f"Open worksheet '{worksheet_name}'",
            )

            # ------------------------------------------------
            # Load CSV files
            # ------------------------------------------------

            dataframe = load_csv_files(
                csv_urls
            )

            # ------------------------------------------------
            # Validate dataset
            # ------------------------------------------------

            validate_dataset(
                dataframe,
                id_column,
                dataset_name,
            )

            # ------------------------------------------------
            # Synchronize dataset
            # ------------------------------------------------

            sync_data(
                sheet=sheet,
                new_df=dataframe,
                id_column=id_column,
                record_type=dataset_name,
            )

            logger.info(
                "Completed synchronization for: %s",
                dataset_name,
            )

        # ----------------------------------------------------
        # All datasets completed
        # ----------------------------------------------------

        logger.info("=" * 60)

        logger.info(
            "All synchronization tasks completed successfully."
        )

    except Exception as exc:

        logger.exception(
            "Synchronization failed: %s",
            exc,
        )

        raise


# ============================================================
# Application Entry Point
# ============================================================

if __name__ == "__main__":
    main()
