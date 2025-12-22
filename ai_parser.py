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
        - Extract: amount (numeric), type (income/expense), category, date (YYYY-MM-DD), optional note
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
          "note": ""
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

            # If client is still not available, return fallback so bot can continue operating
            if not self.client:
                return {"action": "fallback_to_buttons"}

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
        except Exception as e:
            error_str = str(e).lower()
            # Check if this is a quota/rate limit error and try failover
            if any(keyword in error_str for keyword in ['quota', 'rate limit', '429', 'resource exhausted']):
                print(f"API quota/rate limit error with key {self.current_api_key_index}: {e}")
                # Mark current key as failed and try to switch to another key
                if await self._switch_to_next_api_key():
                    # Retry with the new key
                    return await self.parse_message(text, current_date)
                else:
                    print("All API keys have failed due to quota limits")
                    return {"action": "fallback_to_buttons"}
            else:
                print(f"AI Parsing error: {e}")
                return {"action": "fallback_to_buttons"}

# Singleton instance
ai_parser = AIParser()
