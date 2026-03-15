from datetime import datetime, timezone, timedelta
from app.models import GlobalStat, User
from app import db

def add_garden_xp(amount):
    """Adds XP to the global garden and checks for level up."""
    stats = GlobalStat.get_instance()
    stats.zen_xp += amount
    
    # Each level requires 5000 XP
    new_level = (stats.zen_xp // 5000) + 1
    if new_level > stats.garden_level:
        stats.garden_level = new_level
        # Trigger any level-up events if needed
        
    db.session.commit()
    return stats

def update_garden_state():
    """Updates weather and active user count based on recent activity."""
    from sqlalchemy.exc import ProgrammingError
    stats = GlobalStat.get_instance()
    now = datetime.now(timezone.utc)
    
    # Check every 15 minutes
    if now - stats.last_weather_check.replace(tzinfo=timezone.utc) < timedelta(minutes=15):
        return stats
    
    active_count = 0
    try:
        # Count users who logged in or did something in the last 30 minutes
        thirty_mins_ago = now - timedelta(minutes=30)
        # Check if the attribute exists to avoid AttributeError during migration
        if hasattr(User, 'last_login'):
            active_count = User.query.filter(User.last_login >= thirty_mins_ago).count()
        else:
            # If not yet migrated, we just assume 1 user (current)
            active_count = 1
    except Exception as e:
        # Fallback to avoid crashing the whole page
        active_count = 1
    
    stats.active_users_count = active_count
    stats.last_weather_check = now
    
    # Determine weather
    if active_count > 10:
        stats.current_weather = 'weather_sunny'
    elif active_count > 5:
        stats.current_weather = 'weather_fair'
    elif active_count > 2:
        stats.current_weather = 'weather_breezy'
    else:
        stats.current_weather = 'weather_misty'
        
    db.session.commit()
    return stats
