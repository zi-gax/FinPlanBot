import json
import asyncio
from config import GEMINI_API_KEYS


class AIParser:
    def __init__(self):
        # Lazy import of genai to avoid import-time failure when library is not installed
        try:
            from google import genai
            self.genai = genai
        except Exception:
            self.genai = None

        # Do NOT create the client at import time. Defer client creation to first use
        # to avoid any potential blocking network calls during module import.
        self.client = None
        self.current_api_key_index = 0  # Index of current API key being used
        self.failed_keys = set()  # Set of API key indices that have failed

        self.model_name = 'gemini-flash-latest'

    async def _create_client_with_failover(self):
        """Try to create a client with available API keys, skipping failed ones."""
        if not self.genai or not GEMINI_API_KEYS:
            return None

        # Try each available API key
        for attempt in range(len(GEMINI_API_KEYS)):
            api_key_index = (self.current_api_key_index + attempt) % len(GEMINI_API_KEYS)

            # Skip keys that have failed before
            if api_key_index in self.failed_keys:
                continue

            api_key = GEMINI_API_KEYS[api_key_index]

            def create_client(key):
                try:
                    return self.genai.Client(api_key=key)
                except Exception as e:
                    print(f"Failed to create client with API key {api_key_index}: {e}")
                    return None

            client = await asyncio.to_thread(create_client, api_key)
            if client:
                self.current_api_key_index = api_key_index
                print(f"Successfully created client with API key {api_key_index}")
                return client
            else:
                # Mark this key as failed
                self.failed_keys.add(api_key_index)

        return None

    async def _switch_to_next_api_key(self):
        """Switch to the next available API key and recreate client."""
        # Mark current key as failed
        self.failed_keys.add(self.current_api_key_index)

        # Find next available key
        for attempt in range(len(GEMINI_API_KEYS)):
            next_index = (self.current_api_key_index + attempt + 1) % len(GEMINI_API_KEYS)
            if next_index not in self.failed_keys:
                self.current_api_key_index = next_index
                print(f"Switching to API key {next_index}")

                # Try to create client with new key
                self.client = await self._create_client_with_failover()
                return self.client is not None

        return False  # No available keys

    async def parse_message(self, text, current_date):
        prompt = f"""
        You are an AI Agent that processes Persian and English text for a comprehensive Telegram bot with multiple sections: Main Menu, Financial Management, Planning, Settings, Admin Panel, and Help.
        Current date is: {current_date}

        Your task:
        - Understand Persian and English messages from users
        - Extract necessary entities
        - Return structured JSON for the bot

        1. NAVIGATION COMMANDS:
        - Main menu navigation: "main menu", "منوی اصلی", "home", "خانه"
        - Financial section: "finance", "financial", "مدیریت مالی", "مالی", "💰"
        - Planning section: "planning", "برنامه‌ریزی", "📅"
        - Settings: "settings", "تنظیمات", "⚙️"
        - Help: "help", "راهنما", "💡"
        - Admin panel: "admin", "پنل مدیریت", "👑" (only for admins)

        2. FINANCIAL MANAGEMENT:
        - Add transaction: Recognize income/expense messages
        - Extract: amount (numeric), type (income/expense), category, date (YYYY-MM-DD), optional note, currency, possible card number
        - Monthly report: "report", "گزارش", "monthly report", "گزارش ماهانه"
        - Categories: "categories", "دسته‌بندی‌ها", "categories management", "مدیریت دسته‌بندی‌ها"
        - Output example for transaction:
        {{
          "section": "finance",
          "action": "add_transaction",
          "amount": 200000,
          "type": "expense",
          "category": "food",
          "date": "{current_date}",
          "note": "",
          "currency": "toman",
          "card_hint": "1234"  
        }}
        - Output example for navigation:
        {{
          "section": "finance",
          "action": "main"
        }}
        - Output example for report:
        {{
          "section": "finance",
          "action": "monthly_report"
        }}

        3. PLANNING:
        - Add plan: Recognize task messages
        - Extract: title, date (YYYY-MM-DD), optional time (HH:MM)
        - Today's plans: "today's plans", "برنامه‌های امروز", "today plans"
        - Week's plans: "week's plans", "برنامه‌های هفته", "week plans"
        - Output example for plan:
        {{
          "section": "planning",
          "action": "add_plan",
          "title": "ورزش",
          "date": "{current_date}",
          "time": "08:00"
        }}
        - Output example for viewing plans:
        {{
          "section": "planning",
          "action": "plans_today"
        }}

        4. SETTINGS:
        - Change language: "change language", "تغییر زبان", "language"
        - Clear data: "clear data", "پاکسازی داده‌ها", "clear all", "پاکسازی همه"
        - Clear financial: "clear financial", "پاکسازی مالی"
        - Clear planning: "clear planning", "پاکسازی برنامه‌ریزی"
        - Output example:
        {{
          "section": "settings",
          "action": "change_language"
        }}
        {{
          "section": "settings",
          "action": "clear_data",
          "data_type": "all" // or "financial" or "planning"
        }}

        5. HELP:
        - Show help: "help", "راهنما", "how to use", "نحوه استفاده"
        - Output example:
        {{
          "section": "help",
          "action": "show"
        }}

        6. ADMIN PANEL:
        - User list: "user list", "لیست کاربران", "users"
        - Statistics: "statistics", "آمار", "stats"
        - Output example:
        {{
          "section": "admin",
          "action": "users"
        }}

        Rules:
        - If the text is ambiguous or not related, return {{"action":"fallback_to_buttons"}}
        - Always support both Persian (RTL) and English languages
        - Only return JSON (no markdown blocks, no extra text)
        - For navigation commands, prioritize the most specific action
        - If user mentions multiple actions, choose the primary one

        Text: "{text}"
        """
        
        try:
            # Lazily create the client if possible. Creating the client may do network
            # operations depending on the library; perform creation in a thread to
            # avoid blocking the event loop.
            if not self.client and self.genai and GEMINI_API_KEYS:
                self.client = await self._create_client_with_failover()

            # If client is still not available, use a lightweight local parser for intents/entities
            if not self.client:
                return self._local_parse(text, current_date)

            # Run the synchronous API call in a thread pool to avoid blocking the event loop
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt
            )
            result = response.text.strip()
            # Clean possible markdown code blocks
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]
                elif result.startswith("\n"):
                    result = result[1:]
            if result.endswith("```"):
                result = result[:-3].strip()
            
            return json.loads(result)
        except json.JSONDecodeError as e:
            print(f"JSON decode error in AI response: {e}")
            return self._local_parse(text, current_date)
        except Exception as e:
            error_str = str(e).lower()
            # Check if this is a quota/rate limit error and try failover
            if any(keyword in error_str for keyword in ['quota', 'rate limit', '429', 'resource exhausted']):
                print(f"API quota/rate limit error with key {self.current_api_key_index}: {e}")
                # Mark current key as failed and try to switch to another key
                success = await self._switch_to_next_api_key()
                if success:
                    # Retry with the new key
                    return await self.parse_message(text, current_date)
                else:
                    print("All API keys have failed due to quota limits")
                    return self._local_parse(text, current_date)
            else:
                print(f"AI Parsing error: {e}")
                return self._local_parse(text, current_date)

    def _local_parse(self, text: str, current_date: str):
        """Lightweight, rule-based parser for intents and simple transaction/command extraction.
        Returns a dict compatible with LLM output.
        """
        import re
        t = text.strip().lower()

        # -------------------- Navigation intents --------------------
        nav_map = {
            'main_menu': ["main menu", "منوی اصلی", "home", "خانه", "menu", "منو", "back", "بازگشت"],
            'finance_main': ["finance", "financial", "مدیریت مالی", "مالی", "transactions", "تراکنش", "تراکنش‌ها", "💰"],
            'planning_main': ["planning", "برنامه", "برنامه‌ریزی", "📅"],
            'settings': ["settings", "تنظیمات", "⚙️"],
            'help': ["help", "راهنما", "how to", "نحوه"],
            'admin': ["admin", "پنل مدیریت", "ادمین", "👑"],
            'reports': ["report", "reports", "گزارش", "گزارش ماهانه", "reporting"]
        }
        for key, kws in nav_map.items():
            for kw in kws:
                if kw in t:
                    if key == 'main_menu':
                        return {"section": "main", "action": "menu"}
                    if key == 'finance_main':
                        return {"section": "finance", "action": "main"}
                    if key == 'planning_main':
                        return {"section": "planning", "action": "main"}
                    if key == 'settings':
                        return {"section": "settings", "action": "change_language"}
                    if key == 'help':
                        return {"section": "help", "action": "show"}
                    if key == 'admin':
                        return {"section": "admin", "action": "users"}
                    if key == 'reports':
                        return {"section": "finance", "action": "monthly_report"}

        # Normalize Persian digits for regex
        fa_digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
        t_norm = t.translate(fa_digits)
        text_norm = text.translate(fa_digits)

        # -------------------- Finance: transaction detection --------------------
        income_words = ["deposit", "deposited", "credited", "income", "received", "واریز", "واريز", "واریز شد", "نشست"]
        expense_words = ["withdrawal", "withdrawn", "debited", "payment", "paid", "purchase", "spent", "برداشت", "خرج", "هزینه", "پرداخت"]
        t_type = None
        if any(w in t for w in income_words):
            t_type = "income"
        if any(w in t for w in expense_words):
            t_type = "expense" if t_type is None else t_type

        # Amount + currency
        amount = None
        currency = None
        amount_match = re.search(r"(\d{1,3}(?:[\s,]\d{3})+|\d+)(?:\s*)(ir+|irr|rial|rials|ریال|toman|tomans|تومان)?", t_norm)
        if amount_match:
            raw_amt = amount_match.group(1).replace(",", "").replace(" ", "")
            try:
                amount = float(raw_amt)
            except Exception:
                amount = None
            cur = (amount_match.group(2) or "").strip()
            if cur in ["rial", "rials", "ریال", "irr", "ir"]:
                currency = "rial"
            elif cur in ["toman", "tomans", "تومان"]:
                currency = "toman"

        # Date/time
        date_match = re.search(r"(\d{4}[/-]\d{2}[/-]\d{2})", t_norm)
        t_date = date_match.group(1) if date_match else current_date
        time_match = re.search(r"\b(\d{1,2}:\d{2})\b", t_norm)
        t_time = time_match.group(1) if time_match else None

        # Balance (optional)
        balance = None
        bal_match = re.search(r"(?:balance|bal|موجودی|مانده)\s*[:：]?\s*(\d{1,3}(?:[\s,]\d{3})+|\d+)", t_norm)
        if bal_match:
            bal_raw = bal_match.group(1).replace(",", "").replace(" ", "")
            try:
                balance = float(bal_raw)
            except Exception:
                balance = None

        # Sender/receiver
        party = None
        m = re.search(r"^\s*(dear|dear\s+customer|dear\s+\w+|مشتری\s+گرامی|جناب|سرکار|کاربر\s+گرامی)[،,:\s]+([\w\u0600-\u06FF]+)?", text_norm, re.IGNORECASE)
        if m:
            party = m.group(2) or ("Bank" if "dear" in m.group(1).lower() else None)

        # Card/account last-4 hint
        card_hint = None
        last4 = re.search(r"(\d{4})\b", t_norm)
        if last4:
            card_hint = last4.group(1)

        # If it looks like a transaction
        if t_type or amount:
            result = {
                "section": "finance",
                "action": "add_transaction",
                "amount": amount or 0,
                "type": t_type or "expense",
                "date": t_date,
            }
            if currency:
                result["currency"] = currency
            if card_hint:
                result["card_hint"] = card_hint
            if t_time:
                result["time"] = t_time
            if balance is not None:
                result["balance"] = balance
            if party:
                result["party"] = party
            return result

        # -------------------- Finance: reports --------------------
        # Range report: "report from 2025-01-01 to 2025-01-31" or "گزارش از 1404/10/01 تا 1404/10/30"
        rng = re.search(r"(?:report|گزارش)\s*(?:from|از)\s*(\d{4}[/-]\d{2}[/-]\d{2})\s*(?:to|تا)\s*(\d{4}[/-]\d{2}[/-]\d{2})", t_norm)
        if rng:
            return {"section": "finance", "action": "report_range", "start_date": rng.group(1), "end_date": rng.group(2)}
        if any(w in t for w in ["monthly report", "report this month", "گزارش ماهانه", "گزارش این ماه"]):
            return {"section": "finance", "action": "monthly_report"}

        # -------------------- Finance: cards/sources management --------------------
        # Add card with 16 digits
        add_card = re.search(r"(?:add\s+card|کارت\s+جدید)\s*(?:bank\s+)?([\w\u0600-\u06FF]+)?\s*(\d{12,16})", text_norm)
        if add_card:
            return {"section": "finance", "action": "add_card_source", "name": (add_card.group(1) or ""), "card_number": add_card.group(2)}
        # Delete card by last4
        del_card = re.search(r"(?:remove|delete|حذف)\s+کارت\s*(\d{4})", t_norm)
        if del_card:
            return {"section": "finance", "action": "delete_card_source", "card_hint": del_card.group(1)}
        # List/manage cards
        if any(w in t for w in ["cards", "manage cards", "کارت‌ها", "مدیریت کارت"]):
            return {"section": "finance", "action": "manage_cards_sources"}

        # -------------------- Finance: categories management --------------------
        # Add category: "add category food expense" / "افزودن دسته خوراک هزینه"
        add_cat = re.search(r"(?:add\s+category|افزودن\s+دسته)\s+([\w\u0600-\u06FF]+)\s+(income|expense|درآمد|هزینه)", t_norm)
        if add_cat:
            ttype = add_cat.group(2)
            if ttype in ["درآمد"]:
                ttype = "income"
            if ttype in ["هزینه"]:
                ttype = "expense"
            return {"section": "finance", "action": "add_category", "name": add_cat.group(1), "type": ttype}
        del_cat = re.search(r"(?:remove|delete|حذف)\s+(?:category|دسته)\s+([\w\u0600-\u06FF]+)\s+(income|expense|درآمد|هزینه)", t_norm)
        if del_cat:
            ttype = del_cat.group(2)
            if ttype in ["درآمد"]:
                ttype = "income"
            if ttype in ["هزینه"]:
                ttype = "expense"
            return {"section": "finance", "action": "delete_category", "name": del_cat.group(1), "type": ttype}
        if any(w in t for w in ["categories", "دسته‌بندی‌ها", "مدیریت دسته"]):
            return {"section": "finance", "action": "categories"}

        # Clear financial data
        if any(w in t for w in ["clear financial", "پاکسازی مالی"]):
            return {"section": "settings", "action": "clear_data", "data_type": "financial"}

        # -------------------- Planning --------------------
        if any(w in t for w in ["plans today", "today's plans", "برنامه‌های امروز"]):
            return {"section": "planning", "action": "plans_today"}
        if any(w in t for w in ["plans week", "week's plans", "برنامه‌های هفته", "this week plans"]):
            return {"section": "planning", "action": "plans_week"}
        # Mark done: "تمام شد <title>" or "done <title>"
        done_m = re.search(r"(?:تمام\s+شد|done)\s+(.+)$", text_norm)
        if done_m:
            return {"section": "planning", "action": "mark_done", "title": done_m.group(1).strip()}
        # Delete plan: "حذف برنامه <title>" or "delete plan <title>"
        del_p = re.search(r"(?:delete\s+plan|حذف\s+برنامه)\s+(.+)$", text_norm)
        if del_p:
            return {"section": "planning", "action": "delete_plan", "title": del_p.group(1).strip()}
        # Clear planning data
        if any(w in t for w in ["clear planning", "پاکسازی برنامه"]):
            return {"section": "settings", "action": "clear_data", "data_type": "planning"}
        # Add plan quick
        if any(w in t for w in ["meeting", "task", "plan", "جلسه", "برنامه", "کار"]):
            title = text.strip()
            tm = re.search(r"(\d{1,2}:\d{2})", t_norm)
            time = tm.group(1) if tm else None
            return {"section": "planning", "action": "add_plan", "title": title, "date": current_date, "time": time}

        # -------------------- Settings --------------------
        # Language
        if any(w in t for w in ["change language", "تغییر زبان"]):
            if any(w in t for w in ["english", "انگلیسی"]):
                return {"section": "settings", "action": "change_language", "language": "en"}
            if any(w in t for w in ["persian", "فارسی", "farsi"]):
                return {"section": "settings", "action": "change_language", "language": "fa"}
            return {"section": "settings", "action": "change_language"}
        # Currency
        if any(w in t for w in ["currency", "واحد پول", "تومان", "دلار"]):
            if any(w in t for w in ["toman", "تومان"]):
                return {"section": "settings", "action": "set_currency", "currency": "toman"}
            if any(w in t for w in ["dollar", "دلار"]):
                return {"section": "settings", "action": "set_currency", "currency": "dollar"}
            return {"section": "settings", "action": "set_currency"}
        # Calendar
        if any(w in t for w in ["calendar", "تقویم", "جلالی", "میلادی"]):
            if any(w in t for w in ["jalali", "جلالی"]):
                return {"section": "settings", "action": "set_calendar", "calendar_format": "jalali"}
            if any(w in t for w in ["gregorian", "میلادی"]):
                return {"section": "settings", "action": "set_calendar", "calendar_format": "gregorian"}
            return {"section": "settings", "action": "set_calendar"}
        # Clear all
        if any(w in t for w in ["clear all", "clear data", "پاکسازی همه", "پاکسازی داده"]):
            return {"section": "settings", "action": "clear_data", "data_type": "all"}

        # -------------------- Admin --------------------
        if any(w in t for w in ["users", "user list", "لیست کاربران"]):
            return {"section": "admin", "action": "users"}
        if any(w in t for w in ["stats", "statistics", "آمار"]):
            return {"section": "admin", "action": "stats"}

        # Fallback
        return {"action": "fallback_to_buttons"}

# Singleton instance
ai_parser = AIParser()
