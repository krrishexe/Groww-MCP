# 🚨 Groww MCP Alert System - Complete Workflow Explained

## 📋 Example: Setting an Alert for SUZLON ENERGY

**User Command:** _"Set alert for SUZLON ENERGY if the price goes above 67.3"_

---

## 🔄 The Complete Workflow (Why 4-5 Tool Calls?)

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER TYPES COMMAND                          │
│   "Set alert for SUZLON ENERGY if price goes above 67.3"      │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                   🤖 CLAUDE/CURSOR                             │
│ "I need to set a stock alert. Let me call the MCP server..."   │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              📞 TOOL CALL #1: set_price_alert                  │
│                                                                 │
│  Input: {                                                       │
│    "command": "Set alert for SUZLON ENERGY if price goes       │
│                above 67.3"                                     │
│  }                                                              │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│            🧠 ALERT MANAGER: parse_alert_command()             │
│                                                                 │
│ Step 1: Parse Natural Language                                 │
│ ├─ Extract: "SUZLON ENERGY" (stock name)                      │
│ ├─ Extract: "above" (alert type hint)                         │
│ ├─ Extract: "67.3" (threshold value)                          │
│ └─ Extract: "price goes above" (price_above alert)            │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│     🔍 INTERNAL CALL: _resolve_and_validate_stock()            │
│                                                                 │
│ Step 2A: Try Direct Stock Lookup                              │
│ ├─ Call: groww_client.get_stock_price("SUZLON ENERGY")        │
│ └─ Result: ❌ FAILED (not exact symbol)                       │
│                                                                 │
│ Step 2B: Search for Stock                                     │
│ ├─ Call: groww_client.search_stocks("SUZLON ENERGY")          │
│ ├─ Result: ✅ Found [{"symbol": "SUZLON", "name": "Suzlon     │
│ │          Energy Limited"}]                                  │
│ └─ Validated Symbol: "SUZLON"                                 │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│          📈 ALERT MANAGER: create_alert()                      │
│                                                                 │
│ Step 3: Create the Alert Object                               │
│ ├─ Symbol: "SUZLON"                                           │
│ ├─ Alert Type: PRICE_ABOVE                                    │
│ ├─ Threshold: 67.3                                            │
│ ├─ Base Price: None (not needed for price alerts)            │
│ └─ Generate Alert ID: "abc123..."                             │
│                                                                 │
│ Step 4: Validate Stock Again                                  │
│ ├─ Call: groww_client.get_stock_price("SUZLON")               │
│ └─ Result: ✅ Current price: ₹66.88                           │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              💾 SAVE TO alerts.json                            │
│                                                                 │
│ {                                                               │
│   "id": "abc123-def456-...",                                   │
│   "symbol": "SUZLON",                                          │
│   "alert_type": "price_above",                                 │
│   "threshold": 67.3,                                           │
│   "base_price": null,                                          │
│   "status": "active",                                          │
│   "created_at": "2024-01-15T10:30:00"                         │
│ }                                                               │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│           📊 GET MARKET STATUS for Response                     │
│                                                                 │
│ Call: market_utils.get_market_status()                        │
│ Result: {                                                      │
│   "status": "OPEN - Regular Trading",                         │
│   "is_market_hours": true,                                    │
│   "next_session": "Today at 3:30 PM IST"                     │
│ }                                                              │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                   ✅ SUCCESS RESPONSE                          │
│                                                                 │
│ "✅ Price Alert Set Successfully                               │
│                                                                 │
│ Alert Details:                                                 │
│ • Alert ID: abc123...                                          │
│ • Stock: SUZLON                                                │
│ • Type: Price Above                                            │
│ • Threshold: ₹67.3                                             │
│ • Base Price: N/A (price threshold alert)                     │
│ • Status: Active                                               │
│ • Created: 2024-01-15 10:30:00                                │
│                                                                 │
│ Market Context:                                                │
│ • Market Status: OPEN - Regular Trading                       │
│ • Monitoring: Active                                           │
│ • Next Check: Every 3 minutes"                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🧮 Why 4-5 Tool Calls? Breakdown of API Calls

### During Alert Creation:

1. **`set_price_alert`** (Main MCP tool call)
2. **`groww_client.get_stock_price("SUZLON ENERGY")`** (Internal - fails)
   - Tries direct lookup first
3. **`groww_client.search_stocks("SUZLON ENERGY")`** (Internal - succeeds)
   - Searches when direct lookup fails
4. **`groww_client.get_stock_price("SUZLON")`** (Internal - succeeds)
   - Validates the found symbol
5. **`market_utils.get_market_status()`** (Internal)
   - Gets current market status for response

### Why So Many Calls?

```
🎯 ROBUST STOCK RESOLUTION
├─ Try exact symbol first (fast path)
├─ If fails → intelligent search
├─ Validate found symbol works
└─ Provide rich market context

🛡️ ERROR PREVENTION
├─ Catch typos in stock names
├─ Handle partial names ("SUZLON" vs "SUZLON ENERGY")
├─ Verify stock actually exists
└─ Provide helpful error messages

📊 USER EXPERIENCE
├─ Smart auto-correction
├─ Rich response with market context
├─ Clear success/failure feedback
└─ Dynamic market-aware monitoring
```

---

## 🔄 Background Alert Monitoring Process

```
┌─────────────────────────────────────────────────────────────────┐
│                🕐 EVERY 3 MINUTES (MARKET HOURS)                │
│                                                                 │
│ 1. AlertManager.check_all_alerts()                             │
│    ├─ Get all active alerts from alerts.json                   │
│    ├─ Check market status (skip if closed)                     │
│    └─ For each alert:                                          │
│                                                                 │
│ 2. For SUZLON Alert:                                           │
│    ├─ Call: groww_client.get_stock_price("SUZLON")             │
│    ├─ Current price: ₹68.50 (example)                          │
│    ├─ Check: 68.50 >= 67.3? → ✅ YES!                          │
│    └─ TRIGGER ALERT! 🚨                                        │
│                                                                 │
│ 3. Alert Triggered Actions:                                    │
│    ├─ Update alert status to "triggered"                       │
│    ├─ Generate message: "📈 SUZLON price is above ₹67.3        │
│    │   (Current: ₹68.50)"                                      │
│    ├─ Send email notification (if configured)                  │
│    └─ Log trigger event                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎨 Visual Example: SUZLON Alert Journey

```
Timeline: User Sets Alert at 10:30 AM
Current SUZLON Price: ₹66.88

10:30 AM  📝 Alert Created
          ├─ "Alert me when SUZLON goes above ₹67.3"
          ├─ Status: ACTIVE
          └─ Monitoring: Started

10:33 AM  🔍 Check #1
          ├─ Current Price: ₹66.95
          ├─ 66.95 >= 67.3? → ❌ NO
          └─ Continue monitoring...

10:36 AM  🔍 Check #2
          ├─ Current Price: ₹67.15
          ├─ 67.15 >= 67.3? → ❌ NO
          └─ Continue monitoring...

10:39 AM  🔍 Check #3
          ├─ Current Price: ₹67.45
          ├─ 67.45 >= 67.3? → ✅ YES!
          └─ 🚨 TRIGGER ALERT!

10:39 AM  📧 Email Sent
          ├─ To: user@example.com
          ├─ Subject: "🚨 SUZLON Alert Triggered"
          ├─ Message: "📈 SUZLON price is above ₹67.3
          │           (Current: ₹67.45)"
          └─ Alert Status: TRIGGERED (stops monitoring)
```

---

## 🧠 Behind the Scenes: Why This Design?

### 1. **Smart Stock Resolution** 🎯

- **Problem**: Users type "SUZLON ENERGY" but actual symbol is "SUZLON"
- **Solution**: Try exact match first, then intelligent search
- **Benefit**: Works with any way users describe stocks

### 2. **Robust Error Handling** 🛡️

- **Problem**: Many ways stock lookups can fail
- **Solution**: Multiple fallback strategies
- **Benefit**: Helpful error messages, not just "failed"

### 3. **Rich User Feedback** 📊

- **Problem**: Users want confirmation and context
- **Solution**: Include market status, next check time, etc.
- **Benefit**: Users understand exactly what's happening

### 4. **Efficient Background Monitoring** ⚡

- **Problem**: Don't waste API calls when market closed
- **Solution**: Market-aware intervals (3 min vs 1 hour)
- **Benefit**: Fast during trading, efficient during off-hours

---

## 🚀 The Result: Bulletproof Alert System

✅ **User-Friendly**: Works with natural language  
✅ **Robust**: Handles typos and variations  
✅ **Efficient**: Smart monitoring intervals  
✅ **Informative**: Rich feedback and notifications  
✅ **Reliable**: Multiple validation steps

**Every "extra" tool call serves a purpose in making the system more reliable and user-friendly!**
