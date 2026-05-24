"""
mailbus 邮件网关
通过 IMAP 接收邮件，转发到 mailbus inbox。

配置在 config.json 的 mail 字段：
{
  "mail": {
    "imap_server": "imap.example.com",
    "imap_port": 993,
    "email": "mailbus@example.com",
    "password": "xxx",
    "check_interval_minutes": 5,
    "inbox_folder": "INBOX",
    "processed_folder": "processed",
    "agent_mapping": {
      "lingzhao+mailbus@example.com": "lingzhao",
      "lingxi+mailbus@example.com": "lingxi"
    }
  }
}
"""

import os, sys, json, time, re
from datetime import datetime, timezone, timedelta
from email import policy
from email.parser import BytesParser
from typing import Optional

try:
    import imaplib
    import email
except ImportError:
    print("需要 imaplib 和 email 库（Python 标准库自带）")
    sys.exit(1)


def fetch_mails(config: dict) -> list:
    """连接 IMAP 并获取未读邮件"""
    mail_cfg = config.get("mail", {})
    if not mail_cfg.get("imap_server"):
        return []
    
    try:
        imap = imaplib.IMAP4_SSL(mail_cfg["imap_server"], mail_cfg.get("imap_port", 993))
        imap.login(mail_cfg["email"], mail_cfg["password"])
        imap.select(mail_cfg.get("inbox_folder", "INBOX"))
        
        status, ids = imap.search(None, "UNSEEN")
        if status != "OK" or not ids[0]:
            imap.logout()
            return []
        
        msg_ids = ids[0].split()
        mails = []
        for mid in msg_ids:
            status, data = imap.fetch(mid, "(RFC822)")
            if status != "OK":
                continue
            
            raw_email = data[0][1]
            parsed = BytesParser(policy=policy.default).parsebytes(raw_email)
            
            subject = str(parsed.get("subject", ""))
            from_addr = str(parsed.get("from", ""))
            to_addr = str(parsed.get("to", ""))
            date_str = str(parsed.get("date", ""))
            
            # 提取正文
            body = ""
            if parsed.is_multipart():
                for part in parsed.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_content()
                        break
                    elif part.get_content_type() == "text/html":
                        body = part.get_content()
            else:
                body = parsed.get_content()
            
            if body:
                body = body[:2000]
            
            mails.append({
                "id": f"email-{mid.decode()}-{int(time.time())}",
                "from": from_addr,
                "to": to_addr,
                "subject": subject[:100],
                "body": body,
                "date": date_str,
            })
            
            # 标记为已读或移动到 processed
            processed_folder = mail_cfg.get("processed_folder", "")
            if processed_folder:
                imap.copy(mid, processed_folder)
            imap.store(mid, "+FLAGS", "\\Seen")
        
        imap.logout()
        return mails
    
    except Exception as e:
        print(f"IMAP 读取失败: {e}")
        return []


def route_email(mail: dict, config: dict, data_dir: str) -> Optional[str]:
    """将邮件路由到对应 agent 的 inbox，返回 agent 名称或 None"""
    agent_mapping = config.get("mail", {}).get("agent_mapping", {})
    
    # 按收件地址匹配
    to_addr = mail.get("to", "").lower()
    for pattern, agent in agent_mapping.items():
        if pattern.lower() in to_addr:
            # 写入 inbox
            inbox_path = os.path.join(data_dir, "inbox", agent, "inbox.json")
            if not os.path.exists(os.path.dirname(inbox_path)):
                return None
            
            try:
                with open(inbox_path) as f:
                    inbox = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                inbox = {"agent": agent, "has_unread": True, "messages": []}
            
            from_addr = mail.get("from", "").split("<")[-1].rstrip(">")
            msg = {
                "id": mail["id"],
                "from": f"email:{from_addr}",
                "to": agent,
                "type": "reply",
                "priority": "normal",
                "status": "pending",
                "content": f"📧 {mail.get('subject', '(无主题)')}\n\n来自: {mail.get('from', '')}\n\n{mail.get('body', '')[:2000]}",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            inbox.setdefault("messages", []).append(msg)
            inbox["has_unread"] = True
            
            with open(inbox_path, "w") as f:
                json.dump(inbox, f, ensure_ascii=False, indent=2)
            
            return agent
    
    return None


def run_once(config: dict, data_dir: str) -> int:
    """运行一次邮件接收"""
    mails = fetch_mails(config)
    if not mails:
        return 0
    
    routed = 0
    for mail in mails:
        agent = route_email(mail, config, data_dir)
        if agent:
            print(f"  📬 {mail.get('from','')[:30]} → {agent}: {mail.get('subject','')[:40]}")
            routed += 1
    
    return routed


if __name__ == "__main__":
    # 测试模式
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="/mnt/e/ai_tools/mail/store")
    args = parser.parse_args()
    
    # 读取配置
    config_path = os.path.join(args.data_dir, "config.json")
    with open(config_path) as f:
        config = json.load(f)
    
    count = run_once(config, args.data_dir)
    print(f"共接收 {count} 封邮件")
