# NittanyAuction Phase 2 Progress Review

## Team Members
- Taegwon Lee
- John Peifer
- Neul Ezeiruaku
- John Kim

## Implemented Features
- Database population using the provided CSV files
- SHA256 password hashing
- User login with email and password
- Failed login handling
- Role-based redirection for seller, buyer, and helpdesk users

## Required Files
Place the following files in the `code/` folder:
- Users.csv
- Sellers.csv
- Bidders.csv
- Helpdesk.csv

## How to Run
1. Open a terminal in the `code/` folder.
2. Install Flask:
   py -m pip install -r requirements.txt
3. Initialize the database:
   py init_db.py
4. Run the Flask app:
   py app.py
5. Open this in a browser:
   http://127.0.0.1:5000/login

## Notes
- Passwords are stored in hashed format, not plain text.
- The login system redirects users to different welcome pages based on role.
- You can inspect the generated SQLite database using any SQLite viewer.