import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_file="finplan.db"):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # Users table
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            language TEXT DEFAULT 'fa',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        
        # Add language column if it doesn't exist (for existing databases)
        try:
            self.cursor.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'fa'")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Categories table
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            type TEXT, -- 'income' or 'expense'
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )""")

        # Transactions table
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            type TEXT, -- 'income' or 'expense'
            category TEXT,
            date DATE,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )""")

        # Plans table
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            date DATE,
            time TEXT,
            is_done INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )""")

        # Default categories
        self.conn.commit()

    # User operations
    def add_user(self, user_id, username, full_name):
        self.cursor.execute("INSERT OR IGNORE INTO users (user_id, username, full_name, language) VALUES (?, ?, ?, 'fa')",
                            (user_id, username, full_name))
        self.conn.commit()
    
    def get_user_language(self, user_id):
        """Get user's preferred language."""
        self.cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 'fa'
    
    def set_user_language(self, user_id, language):
        """Set user's preferred language."""
        self.cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (language, user_id))
        self.conn.commit()

    # Transaction operations
    def add_transaction(self, user_id, amount, type, category, date, note=None):
        self.cursor.execute("""
            INSERT INTO transactions (user_id, amount, type, category, date, note)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, amount, type, category, date, note))
        self.conn.commit()

    def get_monthly_report(self, user_id, month, year):
        # Fetch total income and expense for the given month
        self.cursor.execute("""
            SELECT type, SUM(amount) FROM transactions
            WHERE user_id = ? AND strftime('%m', date) = ? AND strftime('%Y', date) = ?
            GROUP BY type
        """, (user_id, f"{month:02d}", str(year)))
        return self.cursor.fetchall()
    
    def get_current_month_balance(self, user_id):
        """Get current month income, expense, and balance."""
        from datetime import date
        today = date.today()
        report = self.get_monthly_report(user_id, today.month, today.year)
        
        income = 0
        expense = 0
        for r_type, amount in report:
            if r_type == 'income':
                income = amount or 0
            else:
                expense = amount or 0
        
        return {
            'income': income,
            'expense': expense,
            'balance': income - expense
        }

    # Plan operations
    def add_plan(self, user_id, title, date, time=None):
        self.cursor.execute("""
            INSERT INTO plans (user_id, title, date, time)
            VALUES (?, ?, ?, ?)
        """, (user_id, title, date, time))
        self.conn.commit()

    def get_plans(self, user_id, date=None, start_date=None, end_date=None):
        if date:
            self.cursor.execute("SELECT * FROM plans WHERE user_id = ? AND date = ? ORDER BY time ASC", (user_id, date))
        elif start_date and end_date:
            self.cursor.execute("SELECT * FROM plans WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date, time ASC", 
                                (user_id, start_date, end_date))
        else:
            self.cursor.execute("SELECT * FROM plans WHERE user_id = ? ORDER BY date, time ASC", (user_id,))
        return self.cursor.fetchall()

    def mark_plan_done(self, plan_id):
        self.cursor.execute("UPDATE plans SET is_done = 1 WHERE id = ?", (plan_id,))
        self.conn.commit()

    def delete_plan(self, plan_id):
        self.cursor.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        self.conn.commit()

    # Category operations
    def get_categories(self, user_id, type=None):
        if type:
            self.cursor.execute("SELECT name FROM categories WHERE user_id = ? AND type = ?", (user_id, type))
        else:
            self.cursor.execute("SELECT name, type FROM categories WHERE user_id = ?", (user_id,))
        return [row[0] for row in self.cursor.fetchall()]

    def add_category(self, user_id, name, type):
        self.cursor.execute("INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)", (user_id, name, type))
        self.conn.commit()

    def clear_user_data(self, user_id):
        """Removes all transactions and plans for a specific user."""
        self.cursor.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        self.cursor.execute("DELETE FROM plans WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def clear_financial_data(self, user_id):
        """Removes all transactions (financial data) for a specific user."""
        self.cursor.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def clear_planning_data(self, user_id):
        """Removes all plans (planning data) for a specific user."""
        self.cursor.execute("DELETE FROM plans WHERE user_id = ?", (user_id,))
        self.conn.commit()
