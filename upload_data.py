import pandas as pd
import gspread
from google.oauth2.service_account import Credentials


# =========================
# 1. Read Sales CSV files
# =========================

sales_week1 = pd.read_csv("data/sales/sales_week1.csv")
sales_week2 = pd.read_csv("data/sales/sales_week2.csv")

sales = pd.concat(
    [sales_week1, sales_week2],
    ignore_index=True
)


# =========================
# 2. Read Purchase CSV files
# =========================

purchase_week1 = pd.read_csv("data/purchase/purchase_week1.csv")
purchase_week2 = pd.read_csv("data/purchase/purchase_week2.csv")

purchase = pd.concat(
    [purchase_week1, purchase_week2],
    ignore_index=True
)


# =========================
# 3. Connect to Google Sheets
# =========================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_file(
    "credentials/service-account.json",
    scopes=SCOPES
)

client = gspread.authorize(credentials)

spreadsheet = client.open_by_url(
    "https://docs.google.com/spreadsheets/d/1lSZVyTMhSPnvM2Y1cwgothupxXl8xgHyXjX44TDkt7k/edit"
)


# =========================
# 4. Get both worksheets
# =========================

sales_sheet = spreadsheet.worksheet("Sales")
purchase_sheet = spreadsheet.worksheet("Purchase")


# =========================
# 5. Upload Sales data
# =========================

sales_sheet.clear()

sales_sheet.update(
    [sales.columns.values.tolist()] + sales.values.tolist()
)

print("Sales data uploaded successfully!")


# =========================
# 6. Upload Purchase data
# =========================

purchase_sheet.clear()

purchase_sheet.update(
    [purchase.columns.values.tolist()] + purchase.values.tolist()
)

print("Purchase data uploaded successfully!")