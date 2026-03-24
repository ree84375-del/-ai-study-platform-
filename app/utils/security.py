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
