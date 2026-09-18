import gspread
from google.oauth2.service_account import Credentials

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

sales_sheet = spreadsheet.worksheet("Sales")
purchase_sheet = spreadsheet.worksheet("Purchase")

print("Google Sheets connected!")
print("Sales sheet:", sales_sheet.title)
print("Purchase sheet:", purchase_sheet.title)