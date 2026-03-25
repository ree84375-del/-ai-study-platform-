import os
# Vercel Deployment Trigger: Production 500 Fix + Premium UI
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app.models import User, Question, ChatSession, Group, Announcement
from app import db
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from app.utils.ai_helpers import get_gemini_model
from app.utils.i18n import get_text as _t

admin = Blueprint('admin', __name__, url_prefix='/admin')

@admin.route('/ai_write_broadcast', methods=['POST'])
@login_required
def ai_write_broadcast():
    if not current_user.is_admin:
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    draft = data.get('draft', '')
    instruction = data.get('instruction', '請美化這段內容')
    
    prompt = f"妳是專業的行政秘書。請幫我依照以下「指令」來撰寫或美化一段全站廣播訊息。\n\n指令：{instruction}\n\n"
    if draft:
        prompt += f"目前草稿內容：\n{draft}\n\n"
    else:
        prompt += "目前尚未提供草稿，請根據指令直接生成一段合適的內容。\n\n"
        
    prompt += "生成要求：語氣要親切專業，適合發布給全體學生，使用繁體中文。"
    
    try:
        from app.utils.ai_helpers import generate_text_with_fallback
        response = generate_text_with_fallback(prompt)
        return jsonify({"content": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin.before_request
@login_required
def require_admin():
    if not current_user.is_admin:
        flash(_t('msg_no_permission', lang=current_user.language), 'danger')
        return redirect(url_for('main.home'))

@admin.route('/dashboard')
def dashboard():
    # --- DATABASE HEALTH CHECK (Auto-Migration) ---
    try:
        db.session.execute(text("SELECT group_type FROM \"group\" LIMIT 1"))
    except ProgrammingError:
        db.session.rollback()
        auto_fixes = [
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES group_message(id)",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_edited BOOLEAN DEFAULT FALSE",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_recalled BOOLEAN DEFAULT FALSE",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
            "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS reference_answer TEXT",
            "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS reference_image VARCHAR(255)",
            "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS due_date TIMESTAMP",
            "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS description TEXT",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS submission_image VARCHAR(255)",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS recognized_content TEXT",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS feedback TEXT",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS score INTEGER",
            "ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS group_type VARCHAR(20) DEFAULT 'class'",
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS last_ip VARCHAR(45)",
            "CREATE TABLE IF NOT EXISTS ip_ban (id SERIAL PRIMARY KEY, ip VARCHAR(45) NOT NULL, reason TEXT, banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP, is_permanent BOOLEAN DEFAULT FALSE, admin_notes TEXT, banned_by_id INTEGER REFERENCES \"user\"(id))",
            "CREATE INDEX IF NOT EXISTS ix_ip_ban_ip ON ip_ban (ip)",
            "CREATE TABLE IF NOT EXISTS api_key_tracker (id SERIAL PRIMARY KEY, provider VARCHAR(50) NOT NULL, api_key VARCHAR(255) UNIQUE NOT NULL, status VARCHAR(20) DEFAULT 'standby', last_used TIMESTAMP, error_message TEXT)"
        ]
        for stmt in auto_fixes:
            try:
                db.session.execute(text(stmt))
                db.session.commit()
            except: db.session.rollback()
    # --- END DATABASE HEALTH CHECK ---

    users = User.query.order_by((User.role == 'admin').desc(), User.id).all()
    
    stats = {
        'total_users': User.query.count(),
        'total_questions': Question.query.count(),
        'total_chats': ChatSession.query.count(),
        'total_groups': Group.query.count()
    }
    
    # --- PRIMARY ADMIN RENAME PATCH ---
    # Ensure ree84375@gmail.com is always named "管理員"
    if current_user.email == 'ree84375@gmail.com' and current_user.username != '管理員':
        # Check if anyone else is using the name "管理員"
        conflicting_user = User.query.filter(User.username == '管理員', User.id != current_user.id).first()
        if conflicting_user:
            # Rename the conflicting user to something else
            suffix = conflicting_user.id
            conflicting_user.username = f"管理員_備份_{suffix}"
            db.session.commit()
            
        # Now it's safe to rename the current user
        try:
            current_user.username = '管理員'
            db.session.commit()
        except:
            db.session.rollback()
    # --- END PATCH ---

    # --- ACTIVE BANS ---
    from app.models import IPBan, IPAccessLog
    active_bans = IPBan.query.order_by(IPBan.banned_at.desc()).all()
    # --- END ACTIVE BANS ---
    
    # --- END PATCH ---

    return render_template('admin/dashboard.html', 
                            title=_t('admin_dashboard_title', lang=current_user.language), 
                            users=users, 
                            stats=stats, 
                            active_bans=active_bans,
                            timedelta=timedelta,
                            current_time=datetime.now())

@admin.route('/security_monitor')
@login_required
def security_monitor():
    if not current_user.is_admin:
        return redirect(url_for('main.home'))
    
    from app.models import IPAccessLog
    
    # Load logs with self-healing migration protection
    try:
        # Dedicated monitor shows more logs (200)
        access_logs = IPAccessLog.query.order_by(IPAccessLog.timestamp.desc()).limit(200).all()
    except Exception as e:
        if 'category' in str(e).lower() and 'column' in str(e).lower():
            try:
                db.session.execute(text("ALTER TABLE ip_access_log ADD COLUMN IF NOT EXISTS category VARCHAR(20) DEFAULT 'unknown'"))
                db.session.commit()
                access_logs = IPAccessLog.query.order_by(IPAccessLog.timestamp.desc()).limit(200).all()
            except Exception:
                access_logs = []
        else:
            access_logs = []
        
    return render_template('admin/security_monitor.html', 
                            title="全站安全監控中心", 
                            access_logs=access_logs,
                            timedelta=timedelta,
                            current_time=datetime.now())

@admin.route('/api/security_logs')
@login_required
def api_security_logs():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    from app.models import IPAccessLog
    from sqlalchemy import text
    try:
        logs = IPAccessLog.query.order_by(IPAccessLog.timestamp.desc()).limit(50).all()
    except Exception as e:
        if 'category' in str(e).lower() and 'column' in str(e).lower():
            try:
                db.session.execute(text("ALTER TABLE ip_access_log ADD COLUMN IF NOT EXISTS category VARCHAR(20) DEFAULT 'unknown'"))
                db.session.commit()
                logs = IPAccessLog.query.order_by(IPAccessLog.timestamp.desc()).limit(50).all()
            except Exception as inner_e:
                print(f"API self-healing failed: {inner_e}")
                logs = []
        else:
            logs = []
    
    log_data = []
    for log in logs:
        # Convert to Taiwan Time (UTC+8)
        tw_time = log.timestamp + timedelta(hours=8)
        log_data.append({
            'time': tw_time.strftime('%H:%M:%S'),
            'ip': log.ip,
            'user': log.user.username if log.user else '匿名訪客',
            'path': log.path,
            'threat_level': log.threat_level,
            'category': log.category or 'unknown',
            'threat_reason': log.threat_reason or (
                '分析完成（安全）' if log.threat_level == 'safe' else '等待系統觸發分析...'
            )
        })
    
    return jsonify({'logs': log_data})

@admin.route('/broadcast', methods=['POST'])
@login_required
def broadcast():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    content = request.form.get('content')
    if not content:
        return jsonify({'error': 'No content provided'}), 400
        
    try:
        from app.utils.ai_helpers import broadcast_to_all_groups
        results = broadcast_to_all_groups(content)
        flash(f'廣播成功！已發送至 {results["count"]} 個群組。', 'success')
    except Exception as e:
        flash(f'廣播失敗：{str(e)}', 'danger')
        
    return redirect(url_for('admin.dashboard'))

@admin.route('/system_pulse')
def system_pulse():
    from app.utils.ai_helpers import get_system_pulse
    return jsonify(get_system_pulse())

@admin.route('/api_keys/reset', methods=['POST'])
@login_required
def reset_api_keys():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    from app.models import APIKeyTracker
    from app.extensions import db
    try:
        # Hard reset all trackers to standby
        trackers = APIKeyTracker.query.all()
        for t in trackers:
            t.status = 'standby'
            t.error_message = None
            t.cooldown_until = None
            t.retry_count = 0
        db.session.commit()
        return jsonify({'message': 'All API keys reset to standby'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin.route('/api_keys/deep_cleanup', methods=['POST'])
@login_required
def deep_cleanup_api_keys():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    from app.models import APIKeyTracker
    try:
        # Delete keys that are in error status or have known permanent failures
        broken_keys = APIKeyTracker.query.filter(
            (APIKeyTracker.status == 'error') | 
            (APIKeyTracker.error_message.ilike('%invalid%')) | 
            (APIKeyTracker.error_message.ilike('%restricted%'))
        ).all()
        
        count = len(broken_keys)
        for k in broken_keys:
            db.session.delete(k)
        
        db.session.commit()
        return jsonify({'message': f'Successfully deleted {count} broken keys.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin.route('/api_keys/sync_ollama', methods=['POST'])
@login_required
def sync_ollama_url():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    new_url = request.json.get('url')
    if not new_url:
        return jsonify({'error': 'No URL provided'}), 400
        
    from app.models import APIKeyTracker
    try:
        # Update or create the ollama key tracker
        ollama_tracker = APIKeyTracker.query.filter_by(provider='ollama').first()
        if not ollama_tracker:
            ollama_tracker = APIKeyTracker(provider='ollama', api_key=new_url)
            db.session.add(ollama_tracker)
        else:
            ollama_tracker.api_key = new_url
            ollama_tracker.status = 'active'
            ollama_tracker.error_message = None
            
        db.session.commit()
        return jsonify({'message': f'Ollama URL synced to {new_url}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@admin.route('/user/<int:user_id>/role', methods=['POST'])
def change_user_role(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == 'ree84375@gmail.com':
        flash(_t('msg_admin_lock_owner', lang=current_user.language), 'danger')
        return redirect(url_for('admin.dashboard'))
        
    new_role = request.form.get('role')
    if new_role in ['student', 'teacher', 'admin', 'guest']:
        user.role = new_role
        db.session.commit()
        flash(_t('msg_role_updated', lang=current_user.language, username=user.username, role=new_role), 'success')
    else:
        flash(_t('msg_invalid_role', lang=current_user.language), 'danger')
        
    return redirect(url_for('admin.dashboard'))

@admin.route('/user/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == 'ree84375@gmail.com' or user.id == current_user.id:
        flash(_t('msg_delete_self_err', lang=current_user.language), 'danger')
        return redirect(url_for('admin.dashboard'))
        
    try:
        from app.models import Mistake, ChatSession, GroupMember, AssignmentStatus
        # 手動刪除關聯資料避免 Foreign Key Constraint 失敗
        Mistake.query.filter_by(user_id=user.id).delete()
        sessions = ChatSession.query.filter_by(user_id=user.id).all()
        for s in sessions:
            db.session.delete(s)
        GroupMember.query.filter_by(user_id=user.id).delete()
        AssignmentStatus.query.filter_by(user_id=user.id).delete()
        
        db.session.delete(user)
        db.session.commit()
        flash(f'已成功刪除用戶 {user.username} 及其相關紀錄。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除用戶失敗：{str(e)}', 'danger')
        
    return redirect(url_for('admin.dashboard'))

@admin.route('/ai_ban_recommendation/<int:user_id>')
@login_required
def ai_ban_recommendation(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "Unauthorized"}), 403
    
    from app.utils.ai_moderator import get_ban_recommendation
    result = get_ban_recommendation(user_id)
    return jsonify(result)

@admin.route('/user/<int:user_id>/ban', methods=['POST'])
@login_required
def ban_user(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "Unauthorized"}), 403
        
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash("不能停權管理員！", "danger")
        return redirect(url_for('admin.dashboard'))
        
    ip = user.last_ip or request.form.get('target_ip')
    if not ip:
        flash("找不到該用戶的 IP，無法進行 IP 停權。", "danger")
        return redirect(url_for('admin.dashboard'))
        
    duration = request.form.get('duration') # "warning", "1", "3", "5", "7", "14", "30", "permanent"
    reason = request.form.get('reason', '違反社群規範')
    admin_notes = request.form.get('admin_notes', '')
    
    from datetime import datetime, timedelta, timezone
    from app.models import IPBan
    
    # Check if already banned
    existing_ban = IPBan.query.filter_by(ip=ip).first()
    if existing_ban:
        db.session.delete(existing_ban) # Overwrite
    
    expires_at = None
    is_permanent = False
    
    if duration == "warning":
        flash(f"已向用戶 {user.username} 發出警告。並未實際封鎖 IP。", "info")
        # In this implementation, warning is just a flash. 
        # Optionally record it in admin_notes but don't create IPBan entry.
        return redirect(url_for('admin.dashboard'))
    elif duration == "permanent":
        is_permanent = True
    else:
        try:
            days = int(duration)
            expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        except ValueError:
            flash("無效的停權天數", "danger")
            return redirect(url_for('admin.dashboard'))
            
    new_ban = IPBan(
        ip=ip,
        reason=reason,
        expires_at=expires_at,
        is_permanent=is_permanent,
        admin_notes=admin_notes,
        banned_by_id=current_user.id
    )
    db.session.add(new_ban)
    db.session.commit()
    
    flash(f"用戶 {user.username} (IP: {ip}) 已被封鎖。狀態：{duration}天", "success")
    return redirect(url_for('admin.dashboard'))

@admin.route('/ip_ban/delete/<int:ban_id>', methods=['POST'])
@login_required
def unban_ip(ban_id):
    if not current_user.is_admin:
        return jsonify({"error": "Unauthorized"}), 403
        
    from app.models import IPBan
    ban = IPBan.query.get_or_404(ban_id)
    ip = ban.ip
    db.session.delete(ban)
    db.session.commit()
    flash(f"IP {ip} 已成功解封。", "success")
    return redirect(url_for('admin.dashboard'))

@admin.route('/yukine_command', methods=['POST'])
def yukine_command():
    command = request.form.get('command', '')
    if command:
        try:
            from app.utils.ai_helpers import generate_text_with_fallback
            reply = generate_text_with_fallback(command, system_instruction="你是雪音，目前是後台管理員正在對你下達專屬測試與系統指令，請絕對服從並精確回答。")
            flash(_t('msg_yukine_reply', lang=current_user.language, reply=reply), 'info')
        except Exception as e:
            flash(_t('msg_yukine_conn_fail', lang=current_user.language, error=str(e)), 'danger')
            
    return redirect(url_for('admin.dashboard'))

@admin.route('/questions')
def questions():
    page = request.args.get('page', 1, type=int)
    questions_pagination = Question.query.order_by(Question.id.desc()).paginate(page=page, per_page=20)
    return render_template('admin/questions.html', questions=questions_pagination.items, pagination=questions_pagination)

@admin.route('/questions/new', methods=['GET', 'POST'])
def new_question():
    if request.method == 'POST':
        question = Question(
            subject=request.form.get('subject'),
            category=request.form.get('category'),
            content_text=request.form.get('content_text'),
            option_a=request.form.get('option_a'),
            option_b=request.form.get('option_b'),
            option_c=request.form.get('option_c'),
            option_d=request.form.get('option_d'),
            correct_answer=request.form.get('correct_answer'),
            explanation=request.form.get('explanation'),
            difficulty=request.form.get('difficulty', type=int)
        )
        db.session.add(question)
        db.session.commit()
        flash(_t('msg_question_added', lang=current_user.language), 'success')
        return redirect(url_for('admin.questions'))
        
    return render_template('admin/question_edit.html', title=_t('admin_new_question_title', lang=current_user.language), question=None)

@admin.route('/questions/edit/<int:question_id>', methods=['GET', 'POST'])
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    if request.method == 'POST':
        question.subject = request.form.get('subject')
        question.category = request.form.get('category')
        question.content_text = request.form.get('content_text')
        question.option_a = request.form.get('option_a')
        question.option_b = request.form.get('option_b')
        question.option_c = request.form.get('option_c')
        question.option_d = request.form.get('option_d')
        question.correct_answer = request.form.get('correct_answer')
        question.explanation = request.form.get('explanation')
        question.difficulty = request.form.get('difficulty', type=int)
        
        db.session.commit()
        flash(_t('msg_question_updated', lang=current_user.language), 'success')
        return redirect(url_for('admin.questions'))
        
    return render_template('admin/question_edit.html', title=_t('admin_edit_question_title', lang=current_user.language), question=question)

@admin.route('/questions/delete/<int:question_id>', methods=['POST'])
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    try:
        # 刪除與此題目相關的錯題紀錄 (Mistake) 防止預設 FK Constraint 出錯
        from app.models import Mistake
        Mistake.query.filter_by(question_id=question.id).delete()
        
        db.session.delete(question)
        db.session.commit()
        flash(_t('msg_question_deleted', lang=current_user.language), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_t('msg_question_delete_fail', lang=current_user.language, error=str(e)), 'danger')
    return redirect(url_for('admin.questions'))

@admin.route('/announcements')
def announcements():
    announcements_list = Announcement.query.order_by(Announcement.id.desc()).all()
    return render_template('admin/announcements.html', announcements=announcements_list)

@admin.route('/announcements/new', methods=['GET', 'POST'])
def new_announcement():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        if title and content:
            announcement = Announcement(title=title, content=content, created_by_id=current_user.id)
            db.session.add(announcement)
            db.session.commit()
            flash(_t('msg_announcement_published', lang=current_user.language), 'success')
            return redirect(url_for('admin.announcements'))
        else:
            flash(_t('msg_empty_announcement', lang=current_user.language), 'danger')
            
    return render_template('admin/announcement_edit.html')

@admin.route('/announcements/ai_generate', methods=['POST'])
def ai_generate_announcement():
    from flask import jsonify
    prompt = request.form.get('prompt')
    if not prompt:
        flash(_t('msg_empty_outline', lang=current_user.language), 'danger')
        return redirect(url_for('admin.new_announcement'))
        
    try:
        from app.utils.ai_helpers import generate_text_with_fallback
        text = generate_text_with_fallback(prompt, system_instruction="你是「雪音」，AI 學習平台的系統管理員助理。請根據使用者提供的綱要，撰寫一篇生動、友善且帶有溫度的全站公告。語氣要活潑專業，可以適度使用 emoji。回傳必須為 JSON 格式：{\"title\": \"公告標題\", \"content\": \"公告內容（請包含對平台學生的問候）\"}。除了 JSON 之外，請勿回傳任何其他多餘的字或 Markdown syntax。").strip()
        
        if text.startswith('```json'):
            text = text[7:]
        if text.endswith('```'):
            text = text[:-3]
            
        import json
        data = json.loads(text)
        
        return jsonify({
            'status': 'success',
            'title': data.get('title', '系統公告'),
            'content': data.get('content', prompt)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@admin.route('/announcements/delete/<int:obj_id>', methods=['POST'])
def delete_announcement(obj_id):
    announcement = Announcement.query.get_or_404(obj_id)
    try:
        db.session.delete(announcement)
        db.session.commit()
        flash(_t('msg_announcement_deleted', lang=current_user.language), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_t('msg_delete_failed', lang=current_user.language, error=str(e)), 'danger')
        
    return redirect(url_for('admin.announcements'))
