import pandas as pd

# Sales
sales_week1 = pd.read_csv("data/sales/sales_week1.csv")
sales_week2 = pd.read_csv("data/sales/sales_week2.csv")

sales = pd.concat(
    [sales_week1, sales_week2],
    ignore_index=True
)

# Purchase
purchase_week1 = pd.read_csv("data/purchase/purchase_week1.csv")
purchase_week2 = pd.read_csv("data/purchase/purchase_week2.csv")

purchase = pd.concat(
    [purchase_week1, purchase_week2],
    ignore_index=True
)

print("===== SALES =====")
print(sales)

print("\n===== PURCHASE =====")
print(purchase)