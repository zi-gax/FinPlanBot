import sqlite3
from datetime import date
from decimal import Decimal, getcontext, ROUND_HALF_EVEN

# High precision for money calculations
# Increase precision to avoid intermediate rounding errors during conversions
getcontext().prec = 50

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

        # Add last_menu_message_id column if it doesn't exist (for existing databases)
        try:
            self.cursor.execute("ALTER TABLE users ADD COLUMN last_menu_message_id INTEGER")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # User Settings table
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            currency TEXT DEFAULT 'toman', -- 'toman' or 'dollar'
            calendar_format TEXT DEFAULT 'jalali', -- 'jalali' or 'gregorian'
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )""")

        # Cards/Sources table
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS cards_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL, -- Bank or source name
            card_number TEXT, -- 16-digit card number (optional for sources)
            balance REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )""")

        # Categories table
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            type TEXT, -- 'income' or 'expense'
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )""")

        # Transactions table (enhanced)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            currency TEXT DEFAULT 'toman', -- 'toman' or 'dollar'
            type TEXT, -- 'income' or 'expense'
            category TEXT,
            card_source_id INTEGER, -- Reference to cards_sources table
            date DATE,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (card_source_id) REFERENCES cards_sources (id)
        )""")

        # Add currency column to transactions if it doesn't exist (for existing databases)
        try:
            self.cursor.execute("ALTER TABLE transactions ADD COLUMN currency TEXT DEFAULT 'toman'")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Add card_source_id column to transactions if it doesn't exist (for existing databases)
        try:
            self.cursor.execute("ALTER TABLE transactions ADD COLUMN card_source_id INTEGER REFERENCES cards_sources (id)")
        except sqlite3.OperationalError:
            pass  # Column already exists

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

    def get_last_menu_message_id(self, user_id):
        """Get user's last menu message ID."""
        self.cursor.execute("SELECT last_menu_message_id FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result and result[0] else None

    def set_last_menu_message_id(self, user_id, message_id):
        """Set user's last menu message ID."""
        self.cursor.execute("UPDATE users SET last_menu_message_id = ? WHERE user_id = ?", (message_id, user_id))
        self.conn.commit()

    # User Settings operations
    def get_user_settings(self, user_id):
        """Get user's settings (currency, calendar format)."""
        self.cursor.execute("SELECT currency, calendar_format FROM user_settings WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        if not result:
            # Create default settings
            self.cursor.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))
            self.conn.commit()
            return {'currency': 'toman', 'calendar_format': 'jalali'}
        return {'currency': result[0], 'calendar_format': result[1]}

    def set_user_currency(self, user_id, currency):
        """Set user's preferred currency without overwriting other settings."""
        # Use SQLite UPSERT to update only the currency column
        self.cursor.execute(
            """
            INSERT INTO user_settings (user_id, currency)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                currency = excluded.currency
            """,
            (user_id, currency),
        )
        self.conn.commit()

    def set_user_calendar_format(self, user_id, calendar_format):
        """Set user's preferred calendar format without overwriting other settings."""
        # Use SQLite UPSERT to update only the calendar_format column
        self.cursor.execute(
            """
            INSERT INTO user_settings (user_id, calendar_format)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                calendar_format = excluded.calendar_format
            """,
            (user_id, calendar_format),
        )
        self.conn.commit()

    # Card/Source operations
    def add_card_source(self, user_id, name, card_number=None):
        """Add a new card or source."""
        self.cursor.execute("""
            INSERT INTO cards_sources (user_id, name, card_number)
            VALUES (?, ?, ?)
        """, (user_id, name, card_number))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_cards_sources(self, user_id):
        """Get all cards/sources for a user."""
        self.cursor.execute("""
            SELECT id, name, card_number, balance
            FROM cards_sources
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        return self.cursor.fetchall()

    def get_card_source(self, card_source_id):
        """Get a specific card/source by ID. Returns tuple (id, name, card_number, balance) or None."""
        self.cursor.execute("""
            SELECT id, name, card_number, balance
            FROM cards_sources
            WHERE id = ?
        """, (card_source_id,))
        result = self.cursor.fetchone()
        return result if result else None

    def update_card_source(self, card_source_id, name=None, card_number=None):
        """Update card/source information."""
        if name is not None:
            self.cursor.execute("UPDATE cards_sources SET name = ? WHERE id = ?", (name, card_source_id))
        if card_number is not None:
            self.cursor.execute("UPDATE cards_sources SET card_number = ? WHERE id = ?", (card_number, card_source_id))
        self.conn.commit()

    def delete_card_source(self, card_source_id):
        """Delete a card/source."""
        self.cursor.execute("DELETE FROM cards_sources WHERE id = ?", (card_source_id,))
        self.conn.commit()

    def update_card_balance(self, card_source_id, amount, transaction_type):
        """Update card/source balance based on transaction."""
        if transaction_type == 'income':
            self.cursor.execute("UPDATE cards_sources SET balance = balance + ? WHERE id = ?", (amount, card_source_id))
        else:  # expense
            self.cursor.execute("UPDATE cards_sources SET balance = balance - ? WHERE id = ?", (amount, card_source_id))
        self.conn.commit()

    # Transaction operations (enhanced)
    def add_transaction(self, user_id, amount, currency, type, category, card_source_id, date, note=None):
        self.cursor.execute(
            """
            INSERT INTO transactions (user_id, amount, currency, type, category, card_source_id, date, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, amount, currency, type, category, card_source_id, date, note),
        )

        # Update card/source balance only if a valid card/source is specified
        if card_source_id is not None:
            self.update_card_balance(card_source_id, amount, type)

        self.conn.commit()

    def convert_user_currency(self, user_id, from_currency, to_currency, usd_price):
        """Convert all transactions for a user from one currency to another using `usd_price`.

        - toman -> dollar: amount = amount / usd_price (kept to cents)
        - dollar -> toman: amount = amount * usd_price (kept as whole tomans)

        Uses Decimal for accuracy. Updates transactions' `amount` and `currency`,
        then recalculates `cards_sources.balance` by summing transactions with Decimal.
        """
        if from_currency == to_currency:
            return

        if usd_price is None:
            raise ValueError('usd_price must be provided for currency conversion')

        usd_d = Decimal(str(usd_price))

        try:
            self.conn.execute('BEGIN')

            if from_currency == 'toman' and to_currency == 'dollar':
                self.cursor.execute("SELECT id, amount FROM transactions WHERE user_id = ? AND currency = 'toman'", (user_id,))
                rows = self.cursor.fetchall()
                for tid, amt in rows:
                    amt_d = Decimal(str(amt or '0'))
                    if usd_d == 0:
                        new_amt = Decimal('0.00')
                    else:
                        # quantize to 5 decimal places
                        new_amt = (amt_d / usd_d).quantize(Decimal('0.0000000000000001'), rounding=ROUND_HALF_EVEN)
                    # store full-precision decimal string for dollar amounts (preserve 16 decimals)
                    self.cursor.execute("UPDATE transactions SET amount = ?, currency = 'dollar' WHERE id = ?", (str(new_amt), tid))

            elif from_currency == 'dollar' and to_currency == 'toman':
                self.cursor.execute("SELECT id, amount FROM transactions WHERE user_id = ? AND currency = 'dollar'", (user_id,))
                rows = self.cursor.fetchall()
                for tid, amt in rows:
                    amt_d = Decimal(str(amt or '0'))
                    new_amt = (amt_d * usd_d).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN)
                    # store numeric: integer tomans
                    self.cursor.execute("UPDATE transactions SET amount = ?, currency = 'toman' WHERE id = ?", (int(new_amt), tid))

            # Recalculate balances per card using Decimal sums
            self.cursor.execute("SELECT id FROM cards_sources WHERE user_id = ?", (user_id,))
            card_ids = [r[0] for r in self.cursor.fetchall()]
            for card_id in card_ids:
                self.cursor.execute("SELECT amount, type FROM transactions WHERE card_source_id = ? AND user_id = ?", (card_id, user_id))
                total = Decimal('0')
                for row in self.cursor.fetchall():
                    amt, ttype = row
                    amt_d = Decimal(str(amt or '0'))
                    if ttype == 'income':
                        total += amt_d
                    else:
                        total -= amt_d

                # Format balance based on target currency
                if to_currency == 'dollar':
                    # keep decimal places for dollar balances
                    bal_to_store = total.quantize(Decimal('0.00001'), rounding=ROUND_HALF_EVEN)
                    self.cursor.execute("UPDATE cards_sources SET balance = ? WHERE id = ?", (float(bal_to_store), card_id))
                else:
                    # integer tomans
                    bal_to_store = total.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN)
                    self.cursor.execute("UPDATE cards_sources SET balance = ? WHERE id = ?", (int(bal_to_store), card_id))

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

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

    def get_transactions_in_range(self, user_id, start_date, end_date):
        """Get all transactions within a date range."""
        self.cursor.execute("""
            SELECT t.id, COALESCE(t.amount, 0), t.currency, t.type, t.category, t.date, t.note,
                   cs.name as card_source_name, cs.card_number
            FROM transactions t
            LEFT JOIN cards_sources cs ON t.card_source_id = cs.id
            WHERE t.user_id = ? AND t.date BETWEEN ? AND ?
            ORDER BY t.date DESC, t.id DESC
        """, (user_id, start_date, end_date))
        return self.cursor.fetchall()

    def get_balance_report(self, user_id, start_date, end_date):
        """Get income, expense, and balance for a date range."""
        self.cursor.execute("""
            SELECT type, COALESCE(SUM(amount), 0) FROM transactions
            WHERE user_id = ? AND date BETWEEN ? AND ?
            GROUP BY type
        """, (user_id, start_date, end_date))

        income = 0
        expense = 0
        for r_type, amount in self.cursor.fetchall():
            if r_type == 'income':
                income = amount or 0
            else:
                expense = amount or 0

        return {
            'income': income,
            'expense': expense,
            'balance': income - expense
        }

    def get_card_source_balances_in_range(self, user_id, start_date, end_date):
        """Get balance changes for each card/source within a date range."""
        # Get all transactions in the range with their card/source info
        self.cursor.execute("""
            SELECT cs.id, cs.name, cs.card_number, cs.balance as current_balance,
                   COALESCE(SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE -t.amount END), 0) as net_change
            FROM cards_sources cs
            LEFT JOIN transactions t ON cs.id = t.card_source_id AND t.date BETWEEN ? AND ? AND t.user_id = ?
            WHERE cs.user_id = ?
            GROUP BY cs.id, cs.name, cs.card_number, cs.balance
            ORDER BY cs.name
        """, (start_date, end_date, user_id, user_id))

        results = []
        for row in self.cursor.fetchall():
            card_id, name, card_number, current_balance, net_change = row

            # Handle None values
            current_balance = current_balance or 0
            net_change = net_change or 0

            # Calculate balance at start of period (current_balance - net_change in period)
            start_balance = current_balance - net_change
            end_balance = current_balance

            results.append({
                'id': card_id,
                'name': name,
                'card_number': card_number,
                'start_balance': start_balance,
                'end_balance': end_balance,
                'net_change': net_change
            })

        return results

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

    def update_category(self, user_id, old_name, new_name, type):
        """Update category name."""
        self.cursor.execute("""
            UPDATE categories
            SET name = ?
            WHERE user_id = ? AND name = ? AND type = ?
        """, (new_name, user_id, old_name, type))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def delete_category(self, user_id, name, type):
        """Delete a category."""
        self.cursor.execute("""
            DELETE FROM categories
            WHERE user_id = ? AND name = ? AND type = ?
        """, (user_id, name, type))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def clear_user_data(self, user_id):
        """Removes all transactions and plans for a specific user."""
        # Reset card/source balances to 0 first
        self.cursor.execute("UPDATE cards_sources SET balance = 0 WHERE user_id = ?", (user_id,))
        self.cursor.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        self.cursor.execute("DELETE FROM plans WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def clear_financial_data(self, user_id):
        """Removes all transactions (financial data) for a specific user."""
        # Reset card/source balances to 0 first
        self.cursor.execute("UPDATE cards_sources SET balance = 0 WHERE user_id = ?", (user_id,))
        self.cursor.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def clear_planning_data(self, user_id):
        """Removes all plans (planning data) for a specific user."""
        self.cursor.execute("DELETE FROM plans WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def clear_cards(self, user_id):
        """Deletes all cards/sources for a specific user."""
        self.cursor.execute("DELETE FROM cards_sources WHERE user_id = ?", (user_id,))
        self.conn.commit()

    # Admin operations
    def get_all_users(self):
        """Get all users with their basic information."""
        self.cursor.execute("""
            SELECT user_id, username, full_name, language, created_at
            FROM users
            ORDER BY created_at DESC
        """)
        return self.cursor.fetchall()

    def get_user_stats(self):
        """Get overall statistics for all users."""
        # Total users
        self.cursor.execute("SELECT COUNT(*) FROM users")
        total_users = self.cursor.fetchone()[0]

        # Users by language
        self.cursor.execute("SELECT language, COUNT(*) FROM users GROUP BY language")
        language_stats = dict(self.cursor.fetchall())

        # Total transactions
        self.cursor.execute("SELECT COUNT(*) FROM transactions")
        total_transactions = self.cursor.fetchone()[0]

        # Total plans
        self.cursor.execute("SELECT COUNT(*) FROM plans")
        total_plans = self.cursor.fetchone()[0]

        # Total categories
        self.cursor.execute("SELECT COUNT(*) FROM categories")
        total_categories = self.cursor.fetchone()[0]

        # Active users (users with transactions or plans in last 30 days)
        self.cursor.execute("""
            SELECT COUNT(DISTINCT user_id) FROM (
                SELECT user_id FROM transactions
                WHERE date >= date('now', '-30 days')
                UNION
                SELECT user_id FROM plans
                WHERE date >= date('now', '-30 days')
            )
        """)
        active_users = self.cursor.fetchone()[0]

        return {
            'total_users': total_users,
            'active_users': active_users,
            'language_stats': language_stats,
            'total_transactions': total_transactions,
            'total_plans': total_plans,
            'total_categories': total_categories
        }

    def get_user_detailed_stats(self, user_id):
        """Get detailed statistics for a specific user."""
        # User basic info
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_info = self.cursor.fetchone()

        if not user_info:
            return None

        # Transaction counts by type
        self.cursor.execute("""
            SELECT type, COUNT(*), SUM(amount)
            FROM transactions
            WHERE user_id = ?
            GROUP BY type
        """, (user_id,))
        transaction_stats = dict((row[0], {'count': row[1], 'total': row[2]}) for row in self.cursor.fetchall())

        # Plan statistics
        self.cursor.execute("SELECT COUNT(*), COUNT(CASE WHEN is_done = 1 THEN 1 END) FROM plans WHERE user_id = ?", (user_id,))
        plan_row = self.cursor.fetchone()
        plan_stats = {
            'total': plan_row[0],
            'completed': plan_row[1],
            'pending': plan_row[0] - plan_row[1]
        }

        # Category counts
        self.cursor.execute("SELECT type, COUNT(*) FROM categories WHERE user_id = ? GROUP BY type", (user_id,))
        category_stats = dict(self.cursor.fetchall())

        return {
            'user_info': user_info,
            'transaction_stats': transaction_stats,
            'plan_stats': plan_stats,
            'category_stats': category_stats
        }
