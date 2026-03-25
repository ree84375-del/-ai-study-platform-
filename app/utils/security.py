from flask import request
from app.models import IPBan
from datetime import datetime, timezone

def get_real_ip():
    """
    Robustly identify the real client IP, considering various proxy headers.
    Prioritizes headers set by Cloudflare, Vercel, and standard proxies.
    """
    # 1. Cloudflare / Specialist headers
    cf_ip = request.headers.get('CF-Connecting-IP')
    if cf_ip: return cf_ip.strip()
    
    # 2. Vercel / Standard Real IP header
    real_ip = request.headers.get('X-Real-IP')
    if real_ip: return real_ip.strip()
    
    # 3. Standard Forwarded For
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    
    # 4. Akamai / Other CDNs
    true_client = request.headers.get('True-Client-IP')
    if true_client: return true_client.strip()
        
    # 5. Fallback to remote_addr
    return request.remote_addr

def is_ip_banned(ip):
    """
    Checks if an IP address is currently banned.
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
        try: db.session.rollback()
        except: pass
        return None
    return None

def log_ip_access(ip, user_id=None, path=None, user_agent=None):
    """
    Logs an IP access attempt to the database with early categorization if possible.
    """
    from app.models import IPAccessLog
    from app import db
    
    try:
        # Check if it's a known user
        category = 'user' if user_id else 'unknown'
        
        # Simple UA check for AI bots
        ua = (user_agent or '').lower()
        if any(bot in ua for bot in ['bot', 'crawler', 'spider', 'openai', 'gpt', 'bing', 'google', 'slurp']):
            category = 'ai'

        log = IPAccessLog(
            ip=ip,
            user_id=user_id,
            path=path,
            user_agent=user_agent,
            category=category
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
    Uses Gemini to analyze recent access logs and categorize the visitor accurately.
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
    你是一個頂尖的網路安全專家。請分析以下 IP 的存取行為，並將其歸類為以下四類之一：
    
    類型標籤：
    1. 「user」: 正常登入的用戶或人類訪客。
    2. 「hacker」: 偵測到漏洞掃描、惡意路徑存取（如 .env, /wp-admin）或攻擊行為。
    3. 「ai」: 正當的 AI 爬蟲、LLM 機器人（如 GPTBot）或搜尋引擎。
    4. 「scanner」: 自動化探測器、資產掃描工具、未知目的的背景掃描。
    
    IP: {ip}
    總存取：{len(logs)} 次
    詳細紀錄 (JSON)：
    {json.dumps(log_data, indent=2, ensure_ascii=False)}
    
    請務必以 JSON 格式回應：
    {{ 
      "category": "user/hacker/ai/scanner",
      "level": "safe/suspicious/dangerous", 
      "reason": "具體判斷理由（中文，包含供應商或工具名稱，20個字以內）" 
    }}
    """

    try:
        result = generate_text_with_fallback(prompt).strip()
        if result.startswith("```json"):
            result = result[7:-3].strip()
        
        data = json.loads(result)
        
        latest_log = logs[0]
        latest_log.threat_level = data.get('level', 'safe')
        latest_log.threat_reason = data.get('reason', '分析完成')
        latest_log.category = data.get('category', 'unknown')
        db.session.add(latest_log)
        db.session.commit()
        
        return latest_log.threat_level, latest_log.threat_reason
    except Exception as e:
        try: db.session.rollback()
        except: pass
        print(f"IP Threat Analysis Error: {str(e)}")
        return "safe", f"分析暫時不可用"
