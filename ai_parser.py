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
        You are an AI Agent that processes Persian text for a Telegram bot with two sections: Financial Management and Planning.
        Current date is: {current_date}

        Your task:
        - Understand Persian messages from users
        - Extract necessary entities
        - Return structured JSON for the bot

        1. Financial Management:
        - Recognize income/expense messages
        - Extract: amount (numeric), type (income/expense), category, date (YYYY-MM-DD), optional note
        - Output example:
        {{
          "section": "finance",
          "action": "add_transaction",
          "amount": 200000,
          "type": "expense",
          "category": "food",
          "date": "{current_date}",
          "note": ""
        }}

        2. Planning:
        - Recognize task messages
        - Extract: title, date (YYYY-MM-DD), optional time (HH:MM)
        - Output example:
        {{
          "section": "planning",
          "action": "add_plan",
          "title": "ورزش",
          "date": "{current_date}",
          "time": "08:00"
        }}

        Rules:
        - If the text is ambiguous or not related, return {{"action":"fallback_to_buttons"}}
        - Always support Persian language (RTL)
        - Only return JSON (no markdown blocks, no extra text)

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
