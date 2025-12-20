from google import genai
import json
from config import GEMINI_API_KEY

class AIParser:
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)
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
            # Use the new synchronous call (aiogram handler is async, so this is fine if it doesn't block too long)
            # Alternatively, we could use await self.client.aio.models.generate_content for async
            response = self.client.models.generate_content(
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
