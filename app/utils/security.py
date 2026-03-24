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
    except (ProgrammingError, OperationalError):
        try: db.session.rollback()
        except: pass
        return None

def analyze_ip_threat(ip):
    """
    Uses Gemini to analyze recent access logs for a specific IP and determine threat level.
    """
    from app.models import IPAccessLog
    from app import db
    import google.generativeai as genai
    import os
    import json

    # Get recent logs for context
    logs = IPAccessLog.query.filter_by(ip=ip).order_by(IPAccessLog.timestamp.desc()).limit(15).all()
    if not logs:
        return "safe", "無足夠紀錄"

    log_data = [{"path": l.path, "time": str(l.timestamp), "ua": l.user_agent} for l in logs]
    
    prompt = f"""
    分析此 IP 存取行為。IP: {ip}
    紀錄: {json.dumps(log_data)}
    
    請判斷是否為惡意行為（如攻擊、掃描、異常頻率）。
    回傳 JSON 格式: {{"level": "safe"|"suspicious"|"dangerous", "reason": "中文理由"}}
    """

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return "safe", "API Key 缺失"

    try:
        genai.configure(api_key=api_key)
        model = genai.generativemodels.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        result = response.text.strip()
        # Clean markdown if present
        if result.startswith("```json"):
            result = result[7:-3].strip()
        data = json.loads(result)
        
        # Update the latest log with the threat info
        latest_log = logs[0]
        latest_log.threat_level = data.get('level', 'safe')
        latest_log.threat_reason = data.get('reason', '分析完成')
        db.session.commit()
        
        return latest_log.threat_level, latest_log.threat_reason
    except Exception as e:
        print(f"IP Threat Analysis Error: {str(e)}")
        return "safe", f"分析失敗: {str(e)}"
