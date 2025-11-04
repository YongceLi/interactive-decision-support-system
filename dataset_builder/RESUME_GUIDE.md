# Resume & Recovery Guide

The dataset fetcher has **built-in resume capability**. If the fetch is interrupted for any reason, simply re-run the script and it will automatically continue from where it stopped.

## 🔄 **How Resume Works**

### **Progress Tracking**

The script tracks completed make/model combinations in the database:

```sql
-- Progress table in california_vehicles.db
CREATE TABLE fetch_progress (
    make TEXT,
    model TEXT,
    vehicles_fetched INTEGER,
    fetched_at TEXT,
    status TEXT,  -- 'completed', 'failed', 'partial'
    error_message TEXT,
    UNIQUE(make, model)
);
```

### **Resume Process**

When you run the script:

1. **Loads existing progress** from `fetch_progress` table
2. **Identifies completed models** (already fetched)
3. **Skips completed models** and continues with remaining ones
4. **Saves progress after each model** (real-time updates)

## 🛑 **Interruption Scenarios**

### **1. Rate Limit Hit (429 Error)**

**What happens:**
```
[1250/2479] Fetching: TOYOTA RAV4
  ⚠ Rate limit hit. Waiting 5s...
  ⚠ Rate limit hit. Waiting 10s...
  ⚠ Rate limit hit. Waiting 15s...
```

**Built-in handling:**
- Automatic retry with exponential backoff (5s, 10s, 15s)
- 3 retry attempts before giving up
- Continues with next model if retries fail

**Manual intervention:**
- Press `Ctrl+C` to stop
- Wait a few minutes
- Re-run: `python dataset_builder/fetch_california_dataset.py`
- Script resumes from next model

---

### **2. Network Error / Timeout**

**What happens:**
```
[500/2479] Fetching: HONDA CIVIC
  ⚠ HONDA CIVIC: Timeout (attempt 1/3)
  ⚠ HONDA CIVIC: Timeout (attempt 2/3)
  ⚠ HONDA CIVIC: Timeout (attempt 3/3)
```

**Handling:**
- Automatic retries (3 attempts)
- Marks as failed in progress table
- Continues with next model
- Can re-fetch failed models later

---

### **3. Manual Stop (Ctrl+C)**

**What happens:**
```
[100/2479] Fetching: FORD F-150
  ✓ FORD F-150: Found 50 new + 50 used = 100 vehicles
    → Saved 100 vehicles to database
^C KeyboardInterrupt

--- Progress Update ---
Completed: 100/2,479 models
Total vehicles collected: 9,500
```

**Resume:**
```bash
# Just re-run the same command
python dataset_builder/fetch_california_dataset.py
```

**Output:**
```
Resuming from previous session...
Already completed: 100/2,479
Remaining: 2,379

[101/2479] Fetching: FORD ESCAPE
  ✓ FORD ESCAPE: Found 50 new + 50 used = 100 vehicles
```

---

### **4. System Crash / Power Failure**

**What happens:**
- Last completed model's data is saved
- In-progress model might be lost (not committed yet)

**Resume:**
- Re-run script
- At most 1 model's data lost
- All previous models are safe

---

## 📊 **Checking Progress**

### **Via Script Output**

When resuming, you'll see:
```
Resuming from previous session...
Already completed: 1,250/2,479
Remaining: 1,229
```

### **Via Database Query**

```bash
# Count completed models
sqlite3 data/california_vehicles.db \
  "SELECT COUNT(*) FROM fetch_progress WHERE status='completed';"

# Count total vehicles
sqlite3 data/california_vehicles.db \
  "SELECT COUNT(*) FROM vehicle_listings;"

# See last 10 completed
sqlite3 data/california_vehicles.db \
  "SELECT make, model, vehicles_fetched, fetched_at
   FROM fetch_progress
   WHERE status='completed'
   ORDER BY fetched_at DESC
   LIMIT 10;"
```

### **Via Progress File**

The database itself IS the progress file - no separate files needed!

---

## 🔧 **Manual Recovery**

### **Re-fetch Failed Models**

```bash
# Check failed models
sqlite3 data/california_vehicles.db \
  "SELECT make, model, error_message
   FROM fetch_progress
   WHERE status='failed';"

# Delete failed progress (will retry on next run)
sqlite3 data/california_vehicles.db \
  "DELETE FROM fetch_progress WHERE status='failed';"

# Re-run script - will retry failed models
python dataset_builder/fetch_california_dataset.py
```

### **Start Fresh**

```bash
# Delete database and start over
rm data/california_vehicles.db

# Run fetcher
python dataset_builder/fetch_california_dataset.py
```

### **Skip Problematic Models**

If a specific model keeps failing:

```bash
# Mark it as completed to skip
sqlite3 data/california_vehicles.db \
  "INSERT OR REPLACE INTO fetch_progress (make, model, vehicles_fetched, fetched_at, status)
   VALUES ('PROBLEMATIC_MAKE', 'PROBLEMATIC_MODEL', 0, datetime('now'), 'completed');"
```

---

## ⚙️ **Configuration**

### **Adjust Rate Limit Delay**

If hitting rate limits frequently:

```python
# In fetch_california_dataset.py, main() function:
fetcher.fetch_all(
    limit_per_model=100,
    rate_limit_delay=0.5  # Increase from 0.2 to 0.5 seconds
)
```

### **Adjust Retry Count**

```python
# In fetch_vehicles_for_model() method:
def fetch_vehicles_for_model(
    self,
    make: str,
    model: str,
    limit: int = 100,
    retry_count: int = 5,  # Increase from 3 to 5
    ...
)
```

---

## 📈 **Best Practices**

1. **Let it run overnight** - Full fetch takes ~20-25 minutes uninterrupted
2. **Monitor first 50 models** - Ensure no issues before leaving it
3. **Check progress periodically** - Query database every 500 models
4. **Save logs** - Redirect output to file: `python ... > fetch.log 2>&1`
5. **Backup database** - Copy `california_vehicles.db` when partially complete

---

## 🚨 **Troubleshooting**

### **"Database is locked" Error**

```bash
# Close any other programs accessing the database
# Then re-run
python dataset_builder/fetch_california_dataset.py
```

### **Progress Not Saving**

Check database permissions:
```bash
ls -la data/california_vehicles.db
# Should be writable
```

### **Too Many Rate Limits**

Increase delay:
```bash
# Edit fetch_california_dataset.py line 514:
# Change: rate_limit_delay=0.2
# To:     rate_limit_delay=1.0
```

---

## ✅ **Summary**

- ✅ **Automatic resume** - Just re-run the script
- ✅ **Real-time progress** - Saves after each model
- ✅ **Safe interruption** - Ctrl+C anytime
- ✅ **No data loss** - Only current model (max 100 vehicles) at risk
- ✅ **Query anytime** - Check progress via SQLite
- ✅ **Retry failed** - Delete failed entries and re-run

**Bottom line:** You can safely stop and resume at any time! 🎉
