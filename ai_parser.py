import json
import asyncio
from config import GEMINI_API_KEY


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

        self.model_name = 'gemini-flash-latest'

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
            if not self.client and self.genai and GEMINI_API_KEY:
                def create_client():
                    try:
                        return self.genai.Client(api_key=GEMINI_API_KEY)
                    except Exception:
                        return None
                self.client = await asyncio.to_thread(create_client)

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
            print(f"AI Parsing error: {e}")
            return {"action": "fallback_to_buttons"}

# Singleton instance
ai_parser = AIParser()
