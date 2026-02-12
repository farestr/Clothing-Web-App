# Faris Clothing Shop (Flask + MySQL)

A simple but "real" shop project:
- Shop homepage with search/filter
- Product (Model) detail page with variants (Item) + stock
- Cart (session-based)
- Checkout creates Invoice + Orders and reduces Inventory (PlaceID=1)
- Admin area (password-only) to manage Models + variants + stock

## Folder structure
- app.py
- templates/
- static/css/style.css
- static/uploads/ (put your images here)

## Requirements
- Python 3.10+
- MySQL (your `clothing_store_db` schema)
- pip install:
  - flask
  - flask-mysqldb

## Important DB notes
This app assumes:
- `Model.ModelID` is AUTO_INCREMENT
- `Item.ItemID` is AUTO_INCREMENT (recommended)
- Inventory uses PlaceID=1 as the "store" stock

If ItemID is not AUTO_INCREMENT yet, you can still run, but adding variants from admin will fail.

## Run
1) Set credentials (optional):
   - Windows PowerShell:
     $env:MYSQL_USER="root"
     $env:MYSQL_PASSWORD="root"
     $env:MYSQL_DB="clothing_store_db"
     $env:ADMIN_PASSWORD="admin"

2) Start:
   python app.py

3) Open:
   http://127.0.0.1:5000/

Admin:
   http://127.0.0.1:5000/admin/login
