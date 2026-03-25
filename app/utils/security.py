from flask import request
from app.models import IPBan
from datetime import datetime, timezone

def get_real_ip():
    """
    Robustly identify the real client IP, considering various proxy headers.
    Prioritizes headers that are typically set by reliable proxies like Vercel or Cloudflare.
    """
    # 1. Cloudflare / Common Proxy headers
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # X-Forwarded-For can be a comma-separated list; the first one is the client.
        return forwarded_for.split(',')[0].strip()
    
    # 2. Vercel / Standard Real IP header
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
        
    # 3. Fallback to remote_addr
    return request.remote_addr

def is_ip_banned(ip):
    """
    Checks if an IP address is currently banned.
    Handles cases where the database table might not exist yet (e.g. during migration).
    """
    if not ip:
        return None
    
    from sqlalchemy.exc import ProgrammingError, OperationalError
    from app import db
    try:
        ban = IPBan.query.filter_by(ip=ip).first()
        if ban and ban.is_active():
            return ban
    except (ProgrammingError, OperationalError):
        # Table doesn't exist yet - rollback is CRITICAL here 
        # to avoid "current transaction is aborted" errors in subsequent queries
        try:
            db.session.rollback()
        except:
            pass
        return None
    return None

def log_ip_access(ip, user_id=None, path=None, user_agent=None):
    """
    Logs an IP access attempt to the database.
    """
    from app.models import IPAccessLog
    from app import db
    from sqlalchemy.exc import ProgrammingError, OperationalError
    
    try:
        log = IPAccessLog(
            ip=ip,
            user_id=user_id,
            path=path,
            user_agent=user_agent
        )
        db.session.add(log)
        db.session.commit()
        return log
    except Exception as e:
        try: db.session.rollback()
        except: pass
        print(f"log_ip_access fail: {str(e)}")
        return None

def analyze_ip_threat(ip):
    """
    Uses Gemini (via the centralized fallback system) to analyze recent access logs 
    for a specific IP and determine threat level.
    """
    from app.models import IPAccessLog
    from app import db
    from app.utils.ai_helpers import generate_text_with_fallback
    import json

    # Get recent logs for context
    logs = IPAccessLog.query.filter_by(ip=ip).order_by(IPAccessLog.timestamp.desc()).limit(15).all()
    if not logs:
        return "safe", "無足夠紀錄"

    log_data = [{"path": l.path, "time": str(l.timestamp), "ua": l.user_agent, "user_id": l.user_id} for l in logs]
    
    prompt = f"""
    你是一個資長的網路安全專家與威脅情報分析師。請分析以下 IP 的存取行為，判斷是否為惡意爬蟲、掃描器、VPN 或 Proxy：
    
    IP: {ip}
    存取次數：{len(logs)} 次
    詳細紀錄 (JSON)：
    {json.dumps(log_data, indent=2, ensure_ascii=False)}
    
    分析準則：
    1. **雲端供應商辨識**：判斷該 IP 是否來自 AWS, DigitalOcean, Google Cloud, Azure, Linode, Vercel 等。如果是，標註理由如「AWS 雲端爬蟲」並分類為 safe 或 suspicious。
    2. **行為模式**：頻繁存取 `/` 或 `/api` 但沒有明顯的用戶行為（由 UserID 判斷），可能是偵察。
    3. **管理員安全**：如果 user_id 對應的是管理員，則通常為安全。
    4. **VPN/Proxy**：如果 UA 指向自動化工具（Python-requests, Headless Chrome），應提高警覺。
    
    請務必以 JSON 格式回應，不包含 markdown 片段：
    {{ "level": "safe/suspicious/dangerous", "reason": "具體的理由（中文，包含供應商名稱如 AWS/DO 等，20個字以內）" }}
    """

    try:
        # Use our centralized robust generation system
        result = generate_text_with_fallback(prompt)
        
        # Clean up possible markdown or unexpected text
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:-3].strip()
        
        data = json.loads(result)
        
        # Update the latest log with the threat info
        latest_log = logs[0]
        latest_log.threat_level = data.get('level', 'safe')
        latest_log.threat_reason = data.get('reason', '分析完成')
        db.session.add(latest_log)
        db.session.commit()
        
        return latest_log.threat_level, latest_log.threat_reason
    except Exception as e:
        try: db.session.rollback()
        except: pass
        print(f"IP Threat Analysis Error: {str(e)}")
        return "safe", f"分析暫時不可用"
