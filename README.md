# Willms Game Monitor

Monitors a public Google Doc for schedule changes affecting Willms games. On each run it fetches the document, extracts all Willms entries (date, time, location, home/away, opponent), compares against the last known state, and sends an email if anything changed.

## Files

| File | Purpose |
|---|---|
| `monitor.py` | Main script |
| `snapshot.json` | Auto-generated; last known Willms schedule |
| `monitor.log` | Running log of all checks and changes |

## Configuration

Edit the top of `monitor.py`:

```python
# Email — leave EMAIL_TO empty ("") to disable email notifications
EMAIL_FROM     = "you@gmail.com"
EMAIL_PASSWORD = "xxxx xxxx xxxx xxxx"   # Gmail App Password
EMAIL_TO       = "you@gmail.com"
```

> To generate a Gmail App Password: **Google Account → Security → 2-Step Verification → App Passwords**

Leave `EMAIL_TO` empty to skip email — changes will still be logged to `monitor.log`.

## Usage

**Test run** — fetch and display current schedule without saving:
```bash
python3 monitor.py --test
```

**Normal run** — check for changes, notify if any, save snapshot:
```bash
python3 monitor.py
```

## Cron Job Setup

### 1. Open the crontab editor
```bash
crontab -e
```

### 2. Add this line (runs every 30 minutes)
```
*/30 * * * * /usr/bin/python3 /home/dev/workspace/test-monitor/monitor.py >> /home/dev/workspace/test-monitor/monitor.log 2>&1
```

Adjust the interval as needed:

| Cron expression | Frequency |
|---|---|
| `*/15 * * * *` | Every 15 minutes |
| `*/30 * * * *` | Every 30 minutes |
| `0 * * * *` | Every hour |
| `0 8 * * *` | Once daily at 8 AM |

### 3. Save and verify
```bash
crontab -l
```

## Remove

### 1. Remove the cron job
```bash
crontab -e
```
Delete the line containing `monitor.py`, then save and exit.

### 2. Verify it was removed
```bash
crontab -l
```

### 3. Delete the project files
```bash
rm -rf /home/dev/workspace/test-monitor
```
