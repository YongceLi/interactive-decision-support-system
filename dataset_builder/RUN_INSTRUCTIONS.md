# 🚀 Full Dataset Fetch Instructions

Complete guide to fetch the California vehicle dataset.

---

## 📋 **Prerequisites**

✅ **API Key**: Ensure `AUTODEV_API_KEY` is set in `.env` file
✅ **Dependencies**: All Python packages installed (tqdm, requests, etc.)
✅ **Disk Space**: ~500 MB free space for database

---

## 🎯 **Quick Start - Full Fetch**

### **Step 1: Navigate to Project Directory**

```bash
cd /home/yol013/interactive-decision-support-system-new-architecture
```

### **Step 2: Run the Fetcher**

```bash
python dataset_builder/fetch_california_dataset.py
```

That's it! The script will:
- Fetch **2,479 make/model combinations**
- Target **100 vehicles per model** (50 new + 50 used)
- Make **~5,000 API calls**
- Take **~20-25 minutes**
- Save to `data/california_vehicles.db`

---

## 📊 **What You'll See**

### **Initial Output:**

```
======================================================================
California Dataset Fetcher (SQLite)
======================================================================
Total make/model combinations: 2,479
Target vehicles per model: 100
Database: data/california_vehicles.db
======================================================================

Fetching vehicles |████████░░░░░░░░░░░░| 1,250/2,479 [12:30<12:30, 1.65 model/s] vehicles=125,432 avg/model=100
  ✓ TOYOTA RAV4: Saved 100 vehicles (Total: 125,432)
  ✓ HONDA CR-V: Saved 98 vehicles (Total: 125,530)
  ⚠ CHEVROLET SILVERADO 2500: No vehicles found
```

### **Progress Bar Breakdown:**

```
Fetching TOYOTA RAV4 |████████████████████| 1,250/2,479 [12:30<12:30, 1.65 model/s] vehicles=125,432 avg/model=100
       ↑                      ↑                 ↑        ↑        ↑        ↑             ↑              ↑
   Current model        Progress bar      Completed  Elapsed  Remaining  Speed    Total vehicles   Average
```

---

## ⏸️ **Stopping & Resuming**

### **To Stop:**

Press `Ctrl+C` at any time.

```
^C KeyboardInterrupt
Fetching vehicles: 1,250/2,479 completed
```

### **To Resume:**

Just run the same command again:

```bash
python dataset_builder/fetch_california_dataset.py
```

Output will show:
```
Resuming from previous session...
Already completed: 1,250/2,479
Remaining: 1,229

Fetching vehicles |████████████████████| 1,251/2,479 [...]
```

**✨ No data loss!** Script automatically resumes from where it stopped.

---

## 🔍 **Monitoring Progress**

### **Option 1: Watch the Progress Bar**

The tqdm progress bar shows real-time updates:
- Current model being fetched
- Completed / Total models
- Elapsed time
- Estimated time remaining
- Speed (models per second)
- Total vehicles collected
- Average vehicles per model

### **Option 2: Check Database (Another Terminal)**

While the script is running, open another terminal:

```bash
# Count completed models
sqlite3 data/california_vehicles.db \
  "SELECT COUNT(*) FROM fetch_progress WHERE status='completed';"

# Count total vehicles
sqlite3 data/california_vehicles.db \
  "SELECT COUNT(*) FROM vehicle_listings;"

# Check last 5 completed models
sqlite3 data/california_vehicles.db \
  "SELECT make, model, vehicles_fetched, datetime(fetched_at, 'localtime') as time
   FROM fetch_progress
   WHERE status='completed'
   ORDER BY fetched_at DESC
   LIMIT 5;"
```

### **Option 3: Save Output to Log File**

```bash
python dataset_builder/fetch_california_dataset.py 2>&1 | tee fetch.log
```

This will:
- Show output on screen
- Save to `fetch.log` file for later review

---

## ✅ **After Completion**

### **What You Get:**

1. **Database**: `data/california_vehicles.db`
   - Size: ~300-500 MB
   - 120,000-200,000 vehicles (likely ~160,000)
   - Fully indexed for fast queries

2. **Final Statistics:**

```
======================================================================
Dataset Collection Complete!
======================================================================
Total models processed: 2,479
Total vehicles in database: 163,245
Unique VINs: 163,245
Database file: data/california_vehicles.db
Database size: 387.3 MB
======================================================================

Dataset Statistics:
  Total vehicles: 163,245
  Unique VINs: 163,245
  Top 5 makes: [('Toyota', 15234), ('Honda', 12456), ...]
  Price distribution:
    $0-20k: 0
    $20k-40k: 98,234
    $40k-60k: 45,123
    $60k+: 19,888
======================================================================
```

### **Export to CSV (Optional):**

```bash
python dataset_builder/export_to_csv.py \
  data/california_vehicles.db \
  data/california_vehicles.csv
```

---

## 🧪 **Test First with Smaller Sample**

Before running the full fetch, you can test with fewer models:

```bash
# Test with 10 models (~1,000 vehicles, 1 minute)
python dataset_builder/test_fetch_sample.py 10

# Test with 50 models (~5,000 vehicles, 5 minutes)
python dataset_builder/test_fetch_sample.py 50

# Test with 100 models (~10,000 vehicles, 10 minutes)
python dataset_builder/test_fetch_sample.py 100
```

Review the CSV output before proceeding with full fetch.

---

## 🚨 **Troubleshooting**

### **Rate Limit Errors**

If you see many rate limit warnings:

```
  ⚠ Rate limit hit. Waiting 5s...
  ⚠ Rate limit hit. Waiting 10s...
```

**Solution:**
1. Press `Ctrl+C` to stop
2. Edit `fetch_california_dataset.py` line 514:
   ```python
   # Change:
   fetcher.fetch_all(limit_per_model=100, rate_limit_delay=0.2)
   # To:
   fetcher.fetch_all(limit_per_model=100, rate_limit_delay=0.5)
   ```
3. Re-run the script (will resume automatically)

### **Network Timeouts**

Script automatically retries 3 times. If persistent:
- Check internet connection
- Script will skip failed models and continue
- Can retry failed models later (see RESUME_GUIDE.md)

### **Database Locked**

```
Error: database is locked
```

**Solution:**
- Close any programs accessing the database (DB Browser, etc.)
- Re-run the script

### **Out of Disk Space**

```
Error: No space left on device
```

**Solution:**
- Free up ~500 MB disk space
- Delete old sample databases:
  ```bash
  rm data/sample_california_vehicles.db
  rm data/test_california_vehicles.db
  ```
- Re-run (will resume from where it stopped)

---

## 📈 **Performance Tips**

1. **Run Overnight**: Let it complete uninterrupted (~25 min)
2. **Close Other Programs**: Free up memory and CPU
3. **Stable Internet**: Ensure good connection for API calls
4. **Don't Interrupt**: Let progress bar show completion
5. **Monitor First 50 Models**: Ensure no issues before leaving it

---

## 🎯 **Expected Results**

| Metric | Value |
|--------|-------|
| Total Models | 2,479 |
| API Calls | ~5,000 |
| Runtime | 20-25 minutes |
| Vehicles | 120,000-200,000 |
| Database Size | 300-500 MB |
| Success Rate | ~80-90% models |

**Note:** Some models may have 0 results (rare/commercial vehicles, discontinued models, etc.)

---

## ✨ **Summary**

### **To Run Full Fetch:**

```bash
cd /home/yol013/interactive-decision-support-system-new-architecture
python dataset_builder/fetch_california_dataset.py
```

### **To Stop:** `Ctrl+C`

### **To Resume:** Run same command again

### **To Monitor:** Watch the progress bar!

---

## 📚 **Additional Resources**

- **Resume Guide**: `dataset_builder/RESUME_GUIDE.md`
- **README**: `dataset_builder/README.md`
- **Schema**: `dataset_builder/schema.sql`

---

## 🎉 **You're Ready!**

Just run the command and watch the progress bar fill up! 🚀

```bash
python dataset_builder/fetch_california_dataset.py
```

Good luck! 🚗💨
