# FinPlanBot - AI Agent Instructions

## Project Overview
FinPlanBot is an async Telegram bot for financial management and task planning, built with **aiogram 3.23** (FSM-based), **Google Gemini** for NLP parsing, and SQLite for persistence. It supports multi-language (Persian/Farsi + English), multi-currency (Toman/Dollar), and admin panels.

## Architecture Patterns

### 1. **Async Message/Callback Flow with FSM States**
- **Pattern**: All handlers use `@dp.message()` / `@dp.callback_query()` decorators with `FSMContext`
- **Key States**: `TransactionStates`, `PlanStates`, `CategoryStates`, `CardSourceStates`, `CustomReportStates`
- **Important**: State handlers must call `state.set_state(NewState)` before awaiting user input; use `state.clear()` to exit
- **Example**: Transaction flow: amount → card_source → date → description → type → category → confirm
- **File**: [main.py](main.py) lines 170-205 define all state classes

### 2. **Network Resilience with Exponential Backoff**
- **Critical Function**: `with_network_retry()` [line 127](main.py#L127) wraps coroutines with retry logic
- **Config**: Max attempts/delays loaded from `config.py` (NETWORK_RETRY_MAX_ATTEMPTS, EXPONENTIAL_BASE)
- **Usage**: Wrap Telegram API calls: `await with_network_retry(bot.send_message(...), "send_message")`
- **Errors Caught**: `TelegramNetworkError`, `asyncio.TimeoutError`, `ConnectionError` (others raised immediately)
- **Shutdown**: Graceful signal handling (SIGINT/SIGTERM) via `stop_event.set()` [line 3948](main.py#L3948)

### 3. **Database Layer with Precise Decimal Arithmetic**
- **File**: [database.py](database.py)
- **Precision**: `Decimal` context set to 50 decimals [line 5](database.py#L5) to prevent rounding errors on currency conversions
- **Schema**: Users → Settings → Cards/Sources → Categories → Transactions (indexed by user_id)
- **Pattern**: All money stored as REAL but computed as Decimal in Python for accuracy
- **Example**: `get_user_language()`, `get_user_settings()`, `add_transaction()` take Decimal amounts

### 4. **AI Parser with API Key Failover**
- **File**: [ai_parser.py](ai_parser.py)
- **Config**: Load up to 10 Gemini keys from environment (GEMINI_API_KEY_1...10) [config.py line 10](config.py#L10-L19)
- **Lazy Init**: Client created on first use, not at import time (avoids blocking during startup)
- **Failover**: `_switch_to_next_api_key()` marks failed keys and rotates to next available
- **Model**: `'gemini-flash-latest'` for cost efficiency
- **Do NOT call directly**: Always await; use `parse_user_input()` method for transactions/plans

### 5. **Multi-Language & Multi-Currency System**
- **File**: [translations.py](translations.py) (374 lines of TRANSLATIONS dict)
- **Pattern**: `get_text(key, lang)` always called with lang parameter (e.g., `lang='fa'` or `lang='en'`)
- **Currency**: Per-user setting (toman/dollar); stored in `user_settings` table
- **Calendar**: Jalali/Gregorian toggle per user
- **Important**: Never hardcode strings; all UI text must use `get_text()`
- **Dollar Conversion**: [dollarprice.py](dollarprice.py) caches USD→Toman hourly in JSON

### 6. **Admin Panel Access Control**
- **Pattern**: Check `if user_id in ADMIN_IDS` before showing admin buttons/handlers [config.py line 17](config.py#L17)
- **Admin Routes**: User list with pagination, global statistics, user language override
- **Design**: Admin callbacks trigger after user confirmation dialog for safety

## Development Workflows

### Setup & Running
```bash
# 1. Create .env with required keys (see config.py for all vars)
TELEGRAM_BOT_TOKEN=<token>
GEMINI_API_KEY_1=<key1>  # at least one required
ADMIN_IDS=452131035  # comma-separated

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run bot (logs to bot.log, uses finplan.db)
python main.py
```

### Key Environment Variables
- **Telegram**: `TELEGRAM_BOT_TOKEN`, `ADMIN_IDS`
- **AI**: `GEMINI_API_KEY_*` (1-10), `NETWORK_RETRY_MAX_ATTEMPTS`, `NETWORK_RETRY_EXPONENTIAL_BASE`
- **Paths**: `DATABASE_FILE`, `LOG_FILE` (defaults: finplan.db, bot.log)
- **Logging**: `LOG_LEVEL` (default: INFO)

### Testing Network Resilience
- Simulate failure: Disconnect network, restart bot with `NETWORK_RETRY_MAX_ATTEMPTS=3`
- Observe exponential backoff in logs: "Network error in ... (attempt 1/3): Retrying in 3.0s..."
- Bot resumes polling once network returns

### Debugging State Machines
- **Log User State**: `state_data = await state.get_data()` inside handlers
- **Clear Stuck States**: `await state.clear()` then restart handler
- **Common Issue**: Forgetting `state.set_state(NextState)` before awaiting user input → stuck in current state

## Code Conventions

### Naming
- **Callbacks**: Snake_case prefix matching state (e.g., "add_transaction", "confirm_delete_card")
- **Functions**: `format_amount()` for display, `get_user_language()` for DB queries, `parse_*()` for AI
- **Variables**: `kb` suffix for keyboards (e.g., `main_menu_kb()`)

### Keyboard Generation
- **Pattern**: Separate `*_kb(lang='fa')` functions per menu [lines 228-275](main.py#L228-L275)
- **Buttons**: Always include language-aware text; use emoji + text for clarity
- **Back Button**: Always provide escape route (`callback_data="main_menu"`)

### Error Handling
- **Network**: Wrapped by `with_network_retry()` automatically
- **User Input**: Validate numeric input with try-except, return `"invalid_amount"` text
- **DB Queries**: Catch `sqlite3.OperationalError` for schema migration (e.g., adding columns)
- **Never**: Log sensitive data (Telegram IDs, amounts in debug logs only)

### Transaction Recording
- **Flow**: AI Parser extracts → amount/date/category → user confirms → `db.add_transaction()` updates balance
- **Balance Update**: Automatically calculated on INSERT; currency conversions use Decimal
- **Audit**: All transactions logged with user_id, timestamp, note for debugging

## Integration Points

### External APIs
- **Telegram**: aiogram handles via `Bot` class; retry logic in `with_network_retry()`
- **Gemini AI**: `AIParser` class; blocks only during parse, not during FSM waits
- **USD Price**: `dollarprice.py` fetches hourly from alanchand.com, caches to JSON

### Cross-Component Communication
- **Database**: Central `db` object instantiated once in main [line 167](main.py#L167)
- **AI Parser**: `ai_parser` object instantiated once; methods are async [line 168](main.py#L168)
- **Config**: Singleton dict in [config.py](config.py); imported at module level

## Common Pitfalls & Solutions

| Issue | Cause | Fix |
|-------|-------|-----|
| Bot hangs on startup | DNS/network blocked | Increase `BOT_START_MAX_RETRIES`, check firewall |
| "Invalid amount" always shown | Decimal cast failing | Ensure input is string; test with `Decimal(str(val))` |
| User stuck in state | Missing `state.set_state()` | Add state.set_state(NewState) before await |
| API key exhausted | All keys hit limit | Add more keys to .env or implement rate limiting |
| Transaction amount wrong | Rounding error | Use Decimal math; never float division |
| Admin can't see users | User not in ADMIN_IDS | Check `ADMIN_IDS` env var; use comma-separated format |

## Testing Checklist Before Commit
- [ ] FSM state transitions: Can cancel mid-flow?
- [ ] Network failure: Bot retries and recovers?
- [ ] New text strings: Added to both 'fa' and 'en' in translations.py?
- [ ] Database change: Added migration in `create_tables()` with try-except?
- [ ] Admin feature: Checked `ADMIN_IDS` before granting access?
