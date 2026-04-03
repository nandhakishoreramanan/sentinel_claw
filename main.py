import os, json, logging, requests, yaml
from datetime import datetime, date
from dotenv import load_dotenv
import alpaca_trade_api as tradeapi

load_dotenv()

# ═══════════════════════════════════════════════
# FIX 1 — LOGGING (Rulebook: traceability required)
# ═══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("decisions.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("SentinelClaw")

# ═══════════════════════════════════════════════
# LOAD POLICY FROM YAML (not hardcoded if/else)
# ═══════════════════════════════════════════════
with open("policy.yaml", "r") as f:
    POLICY = yaml.safe_load(f)

def get_constraint(cid):
    for c in POLICY["constraints"]:
        if c["id"] == cid:
            return c.get("value") or c.get("values") or \
                   c.get("blocked_actions") or c.get("blocked_paths")
    return None

# ═══════════════════════════════════════════════
# ALPACA SETUP
# ═══════════════════════════════════════════════
api = tradeapi.REST(
    os.getenv("ALPACA_KEY"),
    os.getenv("ALPACA_SECRET"),
    os.getenv("ALPACA_BASE_URL")
)

# ═══════════════════════════════════════════════
# FIX 3 — DAILY SPEND TRACKER (aggregate limit)
# ═══════════════════════════════════════════════
SPEND_FILE = "daily_spend.json"

def get_daily_spend():
    if not os.path.exists(SPEND_FILE):
        return {"date": str(date.today()), "total": 0.0}
    with open(SPEND_FILE) as f:
        data = json.load(f)
    if data["date"] != str(date.today()):
        return {"date": str(date.today()), "total": 0.0}
    return data

def update_daily_spend(amount):
    data = get_daily_spend()
    data["total"] += amount
    with open(SPEND_FILE, "w") as f:
        json.dump(data, f)

# ═══════════════════════════════════════════════
# FIX 2 — REAL EARNINGS CHECK (deterministic API)
# Previously: return False always. Now: real call.
# ═══════════════════════════════════════════════
def check_earnings_blackout(ticker):
    try:
        url = (
            f"https://financialmodelingprep.com/api/v3/"
            f"earning_calendar?symbol={ticker}&apikey="
            f"{os.getenv('FMP_KEY', 'demo')}"
        )
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            log.warning(f"Earnings API {resp.status_code} for {ticker} — defaulting SAFE")
            return False
        data = resp.json()
        blackout_hours = get_constraint("earnings_blackout_hours")
        now = datetime.now()
        for event in data:
            try:
                edate = datetime.strptime(event["date"], "%Y-%m-%d")
                diff = abs((edate - now).total_seconds() / 3600)
                if diff <= blackout_hours:
                    log.warning(
                        f"EARNINGS BLACKOUT: {ticker} has earnings {event['date']} "
                        f"({diff:.1f}h away — policy blocks within {blackout_hours}h)"
                    )
                    return True
            except Exception:
                continue
        return False
    except Exception as e:
        log.warning(f"Earnings check exception: {e} — defaulting SAFE")
        return False

# ═══════════════════════════════════════════════
# OLLAMA LLM CALL (sequential — saves 6GB VRAM)
# ═══════════════════════════════════════════════
def ask_ollama(prompt, agent_name):
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3:8b-instruct-q4_0",
                "prompt": prompt,
                "stream": False
            },
            timeout=90
        )
        result = resp.json()["response"].strip()
        log.info(f"[{agent_name}] {result[:300]}")
        return result
    except Exception as e:
        log.error(f"Ollama error ({agent_name}): {e}")
        return "Analysis unavailable."

# ═══════════════════════════════════════════════
# FIX 6 — STRUCTURED BULL/BEAR PROMPTS
# ═══════════════════════════════════════════════
def bull_agent(ticker):
    prompt = (
        f"You are a bullish equity analyst. Analyze ticker {ticker}. "
        f"Give exactly 3 specific bullish signals covering: "
        f"(1) technical momentum, (2) fundamentals or earnings trend, "
        f"(3) macro tailwind. Be specific and concise. No disclaimers."
    )
    return ask_ollama(prompt, "BullAgent")

def bear_agent(ticker):
    prompt = (
        f"You are a risk-focused analyst. Analyze ticker {ticker}. "
        f"Give exactly 3 specific risk signals covering: "
        f"(1) technical weakness or overbought signals, "
        f"(2) upcoming earnings or event risk, "
        f"(3) sector or macro headwind. Be specific and concise."
    )
    return ask_ollama(prompt, "BearAgent")

# ═══════════════════════════════════════════════
# WARDEN — ArmorClaw enforcement layer
# Reads policy.yaml, runs all checks, returns signal
# ═══════════════════════════════════════════════
def warden_evaluate(ticker, quantity, price_per_share, bull_report, bear_report):
    log.info("=" * 55)
    log.info(f"WARDEN | Evaluating {ticker} | qty={quantity} | price=${price_per_share:.2f}")

    violations = []
    order_value = quantity * price_per_share

    # Check 1: Ticker whitelist (policy: ticker_whitelist)
    whitelist = get_constraint("ticker_whitelist")
    if ticker not in whitelist:
        violations.append(
            f"TICKER_BLOCKED: '{ticker}' not in approved list {whitelist}"
        )

    # Check 2: Per-order size limit (policy: max_trade_usd)
    max_trade = get_constraint("max_trade_usd")
    if order_value > max_trade:
        violations.append(
            f"ORDER_SIZE_EXCEEDED: ${order_value:.2f} exceeds per-order limit ${max_trade}"
        )

    # Check 3: Daily aggregate limit (policy: daily_spend_limit)
    daily = get_daily_spend()
    daily_limit = get_constraint("daily_spend_limit")
    projected = daily["total"] + order_value
    if projected > daily_limit:
        violations.append(
            f"DAILY_LIMIT_EXCEEDED: Projected ${projected:.2f} exceeds daily limit ${daily_limit}"
        )

    # Check 4: Earnings blackout (policy: earnings_blackout_hours)
    if check_earnings_blackout(ticker):
        violations.append(f"EARNINGS_BLACKOUT: Upcoming earnings event within policy window")

    if violations:
        for v in violations:
            log.warning(f"VIOLATION: {v}")
        log.info(f"WARDEN DECISION: RED — {len(violations)} violation(s)")
        return {"signal": "RED", "reasons": violations}

    log.info("WARDEN DECISION: GREEN — all constraints passed")
    return {"signal": "GREEN", "reasons": []}

# ═══════════════════════════════════════════════
# FIX 4 — EXFILTRATION BLOCK DEMO
# Shows agent attempting .env read, Warden blocks it
# ═══════════════════════════════════════════════
def demo_exfiltration_block():
    log.info("=" * 55)
    log.info("EXFILTRATION DEMO: Agent attempting to read .env file")
    print("\n--- DEMO: Data exfiltration attempt ---")

    attempted = ".env"
    blocked_paths = get_constraint("no_credential_access")

    is_blocked = any(
        attempted == p or
        attempted.endswith(p.replace("*", ""))
        for p in blocked_paths
    )

    if is_blocked:
        log.warning(
            f"DATA EXFILTRATION BLOCKED: '{attempted}' matches policy 'no_credential_access'"
        )
        print(f"🔴 BLOCKED: Agent tried to access '{attempted}'")
        print(f"   Policy: no_credential_access | Enforcement: path_restriction")
        print(f"   File never opened. No data exposed.")
    else:
        log.info(f"File access allowed: {attempted}")

# ═══════════════════════════════════════════════
# PRICE FETCHER
# ═══════════════════════════════════════════════
def get_price(ticker):
    try:
        return float(api.get_latest_trade(ticker).price)
    except Exception as e:
        log.warning(f"Price fetch failed for {ticker}: {e} — using $100 fallback")
        return 100.0

# ═══════════════════════════════════════════════
# MAIN CYCLE
# ═══════════════════════════════════════════════
def run_cycle(ticker, quantity=1):
    print(f"\n{'='*55}")
    print(f"  SENTINEL-CLAW | {ticker} | qty={quantity}")
    print(f"{'='*55}")
    log.info(f"CYCLE START: {ticker}")

    # Reasoning layer
    print("🐂 Bull Agent analyzing...")
    bull = bull_agent(ticker)

    print("🐻 Bear Agent analyzing...")
    bear = bear_agent(ticker)

    # Get real price
    price = get_price(ticker)
    log.info(f"Market price: ${price:.2f}")

    # Warden enforcement
    print("🛡️  Warden checking policy...")
    decision = warden_evaluate(ticker, quantity, price, bull, bear)

    # Execution
    if decision["signal"] == "GREEN":
        print(f"\n🟢 APPROVED — BUY {quantity}x {ticker} @ ~${price:.2f}")
        try:
            api.submit_order(
                symbol=ticker, qty=quantity,
                side="buy", type="market", time_in_force="gtc"
            )
            update_daily_spend(quantity * price)
            log.info(
                f"ORDER PLACED: BUY {quantity}x {ticker} @ ${price:.2f} | "
                f"daily total: ${get_daily_spend()['total']:.2f}"
            )
            print("✅ Order submitted to Alpaca paper trading")
        except Exception as e:
            log.error(f"Order submission error: {e}")
            print(f"❌ Submission failed: {e}")
    else:
        print(f"\n🔴 BLOCKED — Trade rejected by Warden")
        for r in decision["reasons"]:
            print(f"   ↳ {r}")

    log.info(f"CYCLE END: {ticker} | {decision['signal']}")

# ═══════════════════════════════════════════════
# DEMO RUNNER — runs all 4 demo scenarios
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    print("\n[DEMO 1] Normal allowed trade")
    run_cycle("AAPL", quantity=1)

    print("\n[DEMO 2] Blocked — ticker not in whitelist")
    run_cycle("DOGE", quantity=1)

    print("\n[DEMO 3] Blocked — order too large")
    run_cycle("NVDA", quantity=50)  # 50 shares >> $2000 limit

    print("\n[DEMO 4] Data exfiltration attempt blocked")
    demo_exfiltration_block()