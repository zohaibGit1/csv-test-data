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

print("Connected successfully!")
print("Spreadsheet:", spreadsheet.title)

for worksheet in spreadsheet.worksheets():
    print("Sheet:", worksheet.title)