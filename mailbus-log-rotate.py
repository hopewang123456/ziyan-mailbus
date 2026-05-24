"""mailbus cron.log 轻量轮转（不需要 sudo）
每天第一次运行时，如果日志超过 10MB 就压缩归档"""
import os, glob, gzip, shutil
from datetime import date

log_path = "/mnt/e/ai_tools/mail/store/cron.log"
log_dir = os.path.dirname(log_path)
stamp_file = os.path.join(log_dir, ".last_log_rotate")

if not os.path.isfile(log_path):
    exit(0)

size = os.path.getsize(log_path)
today = str(date.today())

last_rotate = ""
if os.path.isfile(stamp_file):
    with open(stamp_file) as f:
        last_rotate = f.read().strip()

if size > 10 * 1024 * 1024 and last_rotate != today:
    # 压缩归档
    archive_name = f"cron-{today}.log.gz"
    archive_path = os.path.join(log_dir, archive_name)
    with open(log_path, "rb") as f_in:
        with gzip.open(archive_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    # 清空原日志
    with open(log_path, "w") as f:
        f.write(f"[rotated at {today}, old log: {archive_name}]\n")
    with open(stamp_file, "w") as f:
        f.write(today)
    print(f"✓ log rotated: {archive_name} ({size/1024/1024:.0f}MB)")

    # 清理超过30天的旧归档
    for f in glob.glob(os.path.join(log_dir, "cron-*.log.gz")):
        fname = os.path.basename(f)
        try:
            fdate = fname.replace("cron-", "").replace(".log.gz", "")
            days_old = (date.today() - date.fromisoformat(fdate)).days
            if days_old > 30:
                os.remove(f)
                print(f"  cleaned old: {fname}")
        except:
            pass
