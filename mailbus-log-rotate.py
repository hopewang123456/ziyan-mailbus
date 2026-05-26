"""mailbus 日志轮转（不需要 sudo）
每天第一次运行时，如果日志超过 10MB 就压缩归档。
支持: store/cron.log + logs/daemon-*.log + 清理超过30天的归档"""
import os, glob, gzip, shutil
from datetime import date

MAIL_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(MAIL_DIR, "logs")
STORE_DIR = os.path.join(MAIL_DIR, "store")
STAMP_FILE = os.path.join(STORE_DIR, ".last_log_rotate")
THRESHOLD = 10 * 1024 * 1024  # 10MB

today = str(date.today())

# 读取上次轮转日期
last_rotate = ""
if os.path.isfile(STAMP_FILE):
    with open(STAMP_FILE) as f:
        last_rotate = f.read().strip()

if last_rotate == today:
    # 今天已经轮转过，跳过
    exit(0)


def _rotate_if_large(log_path: str, archive_tag: str):
    """如果日志文件超过阈值则轮转"""
    if not os.path.isfile(log_path):
        return
    size = os.path.getsize(log_path)
    if size < THRESHOLD:
        return

    # 压缩归档
    archive_name = f"{archive_tag}-{today}.log.gz"
    archive_path = os.path.join(os.path.dirname(log_path), archive_name)
    try:
        with open(log_path, "rb") as f_in:
            with gzip.open(archive_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        # 清空原日志
        with open(log_path, "w") as f:
            f.write(f"[rotated at {today}, old: {archive_name}]\n")
        print(f"✓ rotated: {os.path.basename(log_path)} -> {archive_name} ({size/1024/1024:.0f}MB)")
    except OSError as e:
        print(f"⚠️ rotate failed for {log_path}: {e}")


# 1. 轮转 cron.log
_rotate_if_large(os.path.join(STORE_DIR, "cron.log"), "cron")

# 2. 轮转 daemon-*.log
if os.path.isdir(LOG_DIR):
    for fpath in glob.glob(os.path.join(LOG_DIR, "daemon-*.log")):
        fname = os.path.basename(fpath)
        tag = fname.replace(".log", "")
        _rotate_if_large(fpath, tag)

# 3. 清理超过30天的旧归档（所有目录）
for dirpath in (STORE_DIR, LOG_DIR):
    if not os.path.isdir(dirpath):
        continue
    for fpath in glob.glob(os.path.join(dirpath, "*.log.gz")):
        fname = os.path.basename(fpath)
        try:
            # 从文件名提取日期: cron-2026-05-26.log.gz
            parts = fname.replace(".log.gz", "").split("-")
            fdate_str = "-".join(parts[-3:])  # 取最后三部分作为日期
            fdate = date.fromisoformat(fdate_str)
            days_old = (date.today() - fdate).days
            if days_old > 30:
                os.remove(fpath)
                print(f"  cleaned old: {fname}")
        except (ValueError, IndexError):
            pass

# 写标记
with open(STAMP_FILE, "w") as f:
    f.write(today)
