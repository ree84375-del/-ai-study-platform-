from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
import random
import string
from datetime import datetime, timedelta, timezone
from app.utils.ai_helpers import get_ai_tutor_response

group = Blueprint('group', __name__)

@group.route("/groups", methods=['GET', 'POST'])
@login_required
def groups():
    from app import db
    from app.models import Group, GroupMember
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            name = request.form.get('name')
            if name:
                # Generate unique invite code
                invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                new_group = Group(name=name, invite_code=invite_code, teacher_id=current_user.id)
                db.session.add(new_group)
                db.session.commit()
                flash(f'群組 "{name}" 建立成功！邀請碼：{invite_code}', 'success')
            else:
                flash('請輸入群組名稱', 'danger')
        
        elif action == 'join':
            invite_code = request.form.get('invite_code').upper()
            group_to_join = Group.query.filter_by(invite_code=invite_code).first()
            if group_to_join:
                existing_member = GroupMember.query.filter_by(group_id=group_to_join.id, user_id=current_user.id).first()
                if existing_member or group_to_join.teacher_id == current_user.id:
                    flash('您已經在此群組中', 'info')
                else:
                    new_member = GroupMember(group_id=group_to_join.id, user_id=current_user.id)
                    db.session.add(new_member)
                    db.session.commit()
                    flash(f'成功加入群組：{group_to_join.name}', 'success')
            else:
                flash('無效的邀請碼', 'danger')
                
        return redirect(url_for('group.groups'))

    # GET: show groups
    owned_groups = Group.query.filter_by(teacher_id=current_user.id).all()
    joined_memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
    joined_groups = [m.group_info for m in joined_memberships]
    
    return render_template('groups.html', owned_groups=owned_groups, joined_groups=joined_groups)

@group.route("/api/online_members/<int:group_id>")
@login_required
def online_members(group_id):
    from app import db
    from app.models import Group, GroupMember
    # Check if user is a member or teacher of this group
    is_member = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    group_info = Group.query.get_or_404(group_id)
    
    if not is_member and group_info.teacher_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Get members who were active in the last 5 minutes
    now = datetime.now(timezone.utc)
    five_minutes_ago = now - timedelta(minutes=5)
    
    # This is a bit complex without a dedicated 'last_active' on GroupMember, 
    # so we'll just return all members for now, or use the User.last_active_at
    members = []
    # Include teacher
    teacher = group_info.teacher
    members.append({
        'username': teacher.username,
        'role': 'teacher',
        'is_online': teacher.last_active_at > five_minutes_ago if teacher.last_active_at else False
    })
    
    for m in group_info.members:
        u = m.member
        members.append({
            'username': u.username,
            'role': 'student',
            'is_online': u.last_active_at > five_minutes_ago if u.last_active_at else False
        })
        
    return jsonify({'members': members})

@group.route("/groups/<int:group_id>/leave", methods=['POST'])
@login_required
def leave_group(group_id):
    from app import db
    from app.models import Group, GroupMember
    group_obj = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    
    if membership:
        db.session.delete(membership)
        db.session.commit()
        flash(f'已退出群組：{group_obj.name}', 'success')
    else:
        flash('您不是此群組的成員', 'danger')
        
    return redirect(url_for('group.groups'))

@group.route("/groups/<int:group_id>/dashboard", methods=['GET', 'POST'])
@login_required
def group_dashboard(group_id):
    import traceback
    current_app.logger.info(f"--- [START] Group Dashboard: ID={group_id}, User={current_user.username} ---")
    try:
        from app import db, bcrypt
        from app.models import Group, GroupMember, GroupAnnouncement, GroupMessage, Assignment, AssignmentStatus, User
        
        current_app.logger.info("Step 1: Fetching group object")
        group_obj = Group.query.get_or_404(group_id)
        
        current_app.logger.info("Step 2: Checking permissions")
        membership = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
        if not membership and group_obj.teacher_id != current_user.id:
            current_app.logger.warning(f"Permission denied for user {current_user.id} on group {group_id}")
            flash('您沒有權限進入此討論板', 'danger')
            return redirect(url_for('group.groups'))
            
        if request.method == 'POST':
            action = request.form.get('action')
            content = request.form.get('content')
            image_data = request.form.get('image_data')
            current_app.logger.info(f"Step 3 [POST]: Action={action}")
            
            # Post Message
            if action == 'post_message':
                if (content and content.strip()) or image_data:
                    new_msg = GroupMessage(group_id=group_id, user_id=current_user.id, content=content or "", image_data=image_data)
                    db.session.add(new_msg)
                    db.session.commit()
                    
                    # 只有在 AI 開啟時才觸發 AI 回覆
                    if group_obj.has_ai:
                        current_app.logger.info("AI is enabled, triggering reaction...")
                        # 隨機觸發或關鍵字觸發
                        trigger_ai = random.random() < 0.3 or '雪音' in content or '老師' in content
                        if trigger_ai:
                            # 取得最近對話作為上下文
                            recent_msgs = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.desc()).limit(10).all()
                            chat_history = []
                            # 找出 AI 的 User 物件
                            yukine = User.query.filter_by(username='雪音老師').first()
                            if not yukine:
                                current_app.logger.info("Creating Yukine AI user...")
                                yukine = User(username='雪音老師', email='yukine_bot@internal.ai', password=bcrypt.generate_password_hash('ai_placeholder').decode('utf-8'), role='teacher')
                                db.session.add(yukine)
                                db.session.commit()
                            
                            for m in reversed(recent_msgs):
                                role = 'assistant' if m.user_id == yukine.id else 'user'
                                chat_history.append({'role': role, 'content': m.content})
                            
                            ai_prompt = f"這是群組「{group_obj.name}」的討論。請以雪音老師的身分，簡短且溫暖地回覆大家。"
                            current_app.logger.info("Calling Gemini API...")
                            ai_reply = get_ai_tutor_response(chat_history, ai_prompt, personality_key='雪音-溫柔型')
                            
                            if ai_reply:
                                ai_msg = GroupMessage(group_id=group_id, user_id=yukine.id, content=ai_reply)
                                db.session.add(ai_msg)
                                db.session.commit()
                                current_app.logger.info("AI reply saved.")
            
            elif action == 'post_announcement':
                current_app.logger.info("Posting announcement...")
                if group_obj.teacher_id == current_user.id and content:
                    new_ann = GroupAnnouncement(group_id=group_id, content=content)
                    db.session.add(new_ann)
                    db.session.commit()
                    flash('公告已發布', 'success')

            elif action == 'update_settings':
                current_app.logger.info("Updating group settings...")
                if group_obj.teacher_id == current_user.id:
                    new_name = request.form.get('group_name')
                    if new_name:
                        group_obj.name = new_name
                        db.session.commit()
                        flash('群組設定已更新', 'success')
            
            elif action == 'toggle_ai':
                current_app.logger.info("Toggling AI...")
                if group_obj.teacher_id == current_user.id:
                    group_obj.has_ai = not group_obj.has_ai
                    db.session.commit()
                    status = "開啟" if group_obj.has_ai else "關閉"
                    flash(f'雪音老師討論功能已{status}', 'info')

            elif action == 'publish_assignment':
                current_app.logger.info("Publishing assignment...")
                if group_obj.teacher_id == current_user.id:
                    title = request.form.get('title')
                    description = request.form.get('description')
                    if title:
                        new_assignment = Assignment(group_id=group_id, title=title, description=description)
                        db.session.add(new_assignment)
                        db.session.commit()
                        flash('新作業已發布', 'success')

            elif action == 'submit_assignment':
                current_app.logger.info("Submitting assignment...")
                assignment_id = request.form.get('assignment_id')
                if assignment_id and content:
                    status = AssignmentStatus.query.filter_by(assignment_id=assignment_id, user_id=current_user.id).first()
                    if not status:
                        status = AssignmentStatus(assignment_id=assignment_id, user_id=current_user.id)
                        db.session.add(status)
                    
                    status.content = content
                    status.is_completed = True
                    status.completed_at = datetime.now(timezone.utc)
                    
                    # AI 批改 (模擬)
                    from app.utils.ai_helpers import get_yukine_feedback
                    feedback_prompt = f"學生上傳了作業內容：{content}。請給予簡短的點評與分數(0-100)。"
                    score, feedback = get_yukine_feedback(feedback_prompt)
                    status.score = score
                    status.ai_feedback = feedback
                    
                    db.session.commit()
                    flash('作業已繳交，雪音老師已完成批改！', 'success')
                    
            return redirect(url_for('group.group_dashboard', group_id=group_id))
            
        current_app.logger.info("Step 4: Loading messages and data for render")
        messages = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.asc()).limit(100).all()
        announcements = GroupAnnouncement.query.filter_by(group_id=group_id).order_by(GroupAnnouncement.created_at.desc()).limit(5).all()

        current_app.logger.info("Step 5: Sorting assignments")
        sorted_assignments = []
        if group_obj.assignments:
            # Safer sort for datetime objects
            sorted_assignments = sorted(
                group_obj.assignments, 
                key=lambda x: (x.due_date.replace(tzinfo=None) if x.due_date else datetime(9999, 12, 31))
            )

        current_app.logger.info("Step 6: Rendering template")
        return render_template('group_dashboard.html', 
                               group=group_obj, 
                               messages=messages, 
                               announcements=announcements,
                               assignments=sorted_assignments)

    except Exception as e:
        err_msg = traceback.format_exc()
        current_app.logger.error(f"FATAL ERROR in group_dashboard: {err_msg}")
        return f"<div style='padding:20px; font-family:sans-serif;'><h2>系統發生錯誤 (Dashboard)</h2><pre style='background:#f0f0f0; padding:10px; overflow:auto;'>{err_msg}</pre></div>", 500

@group.route("/groups/<int:group_id>/update_member_role/<int:user_id>", methods=['POST'])
@login_required
def update_member_role(group_id, user_id):
    from app import db
    from app.models import User, Group
    group_obj = Group.query.get_or_404(group_id)
    
    if group_obj.teacher_id != current_user.id:
        flash('您沒有權限執行此操作', 'danger')
        return redirect(url_for('group.group_dashboard', group_id=group_id))
    
    user_to_update = User.query.get_or_404(user_id)
    new_role = request.form.get('new_role')
    
    if new_role in ['student', 'teacher']:
        if user_to_update.id != current_user.id and user_to_update.email != 'ree84375@gmail.com':
            user_to_update.role = new_role
            db.session.commit()
            flash(f'已將 {user_to_update.username} 的角色更新為 {new_role}', 'success')
        else:
            flash('您無法更改此使用者的角色', 'warning')
    else:
        flash('無效的角色選擇', 'danger')
        
    return redirect(url_for('group.group_dashboard', group_id=group_id))
