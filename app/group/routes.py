from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
import random
import string
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import ProgrammingError
from sqlalchemy import text
from app.utils.ai_helpers import get_ai_tutor_response

group = Blueprint('group', __name__)

@group.route("/groups", methods=['GET', 'POST'], strict_slashes=False)
@login_required
def groups():
    from app import db
    from app.models import Group, GroupMember
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            name = request.form.get('group_name')
            has_ai = 'has_ai' in request.form
            if name:
                # Generate unique invite code
                invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                new_group = Group(name=name, invite_code=invite_code, teacher_id=current_user.id, has_ai=has_ai)
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
    
    # Unify for template
    all_groups = owned_groups + joined_groups
    # Remove duplicates if any (though unlikely with this logic)
    seen_ids = set()
    unique_groups = []
    for g in all_groups:
        if g.id not in seen_ids:
            unique_groups.append(g)
            seen_ids.add(g.id)
    
    return render_template('groups.html', groups=unique_groups)

@group.route("/api/online_members/<int:group_id>", strict_slashes=False)
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

@group.route("/groups/<int:group_id>/leave", methods=['POST'], strict_slashes=False)
@login_required
def leave_group(group_id):
    from app import db
    from app.models import Group, GroupMember
    group_obj = Group.query.get_or_404(group_id)
    if group_obj.teacher_id == current_user.id:
        # Teacher dissolving the group
        db.session.delete(group_obj)
        db.session.commit()
        flash(f'已解散群組：{group_obj.name}，相關資料已全數清除。', 'success')
    else:
        # Standard member leaving
        membership = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
        if membership:
            db.session.delete(membership)
            db.session.commit()
            flash(f'已退出群組：{group_obj.name}', 'success')
        else:
            flash('您不是此群組的成員', 'danger')
        
    return redirect(url_for('group.groups'))

@group.route("/groups/<int:group_id>/dashboard", methods=['GET', 'POST'], strict_slashes=False)
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
                    parent_id = request.form.get('parent_id')
                    new_msg = GroupMessage(
                        group_id=group_id, 
                        user_id=current_user.id, 
                        content=content or "", 
                        image_data=image_data,
                        parent_id=parent_id if parent_id and parent_id.isdigit() else None
                    )
                    db.session.add(new_msg)
                    db.session.commit()
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        # Fetch parent message if exists for the UI
                        parent_preview = None
                        if new_msg.parent_id:
                            p_msg = GroupMessage.query.get(new_msg.parent_id)
                            if p_msg:
                                parent_preview = {
                                    'username': p_msg.author.username,
                                    'content': p_msg.content[:50] + '...' if len(p_msg.content) > 50 else p_msg.content
                                }
                        
                        return jsonify({
                            'status': 'success',
                            'ai_triggered': True if group_obj.has_ai else False,
                            'user_message': {
                                'id': new_msg.id,
                                'content': new_msg.content,
                                'image_data': new_msg.image_data,
                                'username': current_user.username,
                                'is_mine': True,
                                'created_at': new_msg.created_at.isoformat() + 'Z',
                                'parent_id': new_msg.parent_id,
                                'parent_preview': parent_preview
                            }
                        })
                else:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({'status': 'error', 'message': 'Message cannot be empty'}), 400
            
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
                    
                    # AI 批改
                    from app.utils.ai_helpers import get_yukine_feedback
                    assignment = Assignment.query.get(assignment_id)
                    feedback, score = get_yukine_feedback(content, assignment.title, assignment.description)
                    status.score = score
                    status.ai_feedback = feedback
                    
                    db.session.commit()
                    flash('作業已繳交，雪音老師已完成批改！', 'success')
                    
            return redirect(url_for('group.group_dashboard', group_id=group_id))
            
        current_app.logger.info("Step 4: Loading messages and data for render")
        try:
            messages = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.asc()).limit(100).all()
        except ProgrammingError:
            db.session.rollback()
            current_app.logger.warning("Detected missing DB columns in GroupMessage. Attempting auto-fix...")
            # Auto-run basic migrations for missing columns
            auto_fixes = [
                "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES group_message(id)",
                "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_edited BOOLEAN DEFAULT FALSE",
                "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_recalled BOOLEAN DEFAULT FALSE",
                "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE"
            ]
            for stmt in auto_fixes:
                try:
                    db.session.execute(text(stmt))
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"Auto-fix failed for {stmt}: {e}")
            
            # Final retry after fix
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

@group.route("/groups/<int:group_id>/update_member_role/<int:user_id>", methods=['POST'], strict_slashes=False)
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

@group.route('/api/groups/messages/<int:message_id>/edit', methods=['POST'], strict_slashes=False)
@login_required
def edit_message(message_id):
    from app import db
    from app.models import GroupMessage
    msg = GroupMessage.query.get_or_404(message_id)
    
    # 權限檢查：只有作者能編輯
    if msg.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403
        
    # 時間檢查：15 分鐘內
    time_diff = datetime.now(timezone.utc) - msg.created_at.replace(tzinfo=timezone.utc)
    if time_diff.total_seconds() > 900: # 15 minutes
        return jsonify({'status': 'error', 'message': '超過 15 分鐘編輯時限'}), 400
        
    new_content = request.form.get('content')
    if not new_content or not new_content.strip():
        return jsonify({'status': 'error', 'message': '內容不能為空'}), 400
        
    msg.content = new_content
    msg.is_edited = True
    db.session.commit()
    
    return jsonify({'status': 'success', 'content': msg.content})

@group.route('/api/groups/messages/<int:message_id>/recall', methods=['POST'], strict_slashes=False)
@login_required
def recall_message(message_id):
    from app import db
    from app.models import GroupMessage
    msg = GroupMessage.query.get_or_404(message_id)
    
    if msg.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403
        
    time_diff = datetime.now(timezone.utc) - msg.created_at.replace(tzinfo=timezone.utc)
    if time_diff.total_seconds() > 900:
        return jsonify({'status': 'error', 'message': '超過 15 分鐘收回時限'}), 400
        
    msg.is_recalled = True
    msg.content = "此訊息已收回"
    
    # 聯動收回：如果此訊息有觸發 AI 回覆（或其他回覆），一併收回
    child_msgs = GroupMessage.query.filter_by(parent_id=message_id).all()
    affected_ids = [message_id]
    for child in child_msgs:
        child.is_recalled = True
        child.content = "此訊息已隨使用者收回而撤銷"
        affected_ids.append(child.id)
        
    db.session.commit()
    
    return jsonify({'status': 'success', 'affected_ids': affected_ids})

@group.route('/api/groups/messages/<int:message_id>/delete', methods=['POST'], strict_slashes=False)
@login_required
def delete_message(message_id):
    from app import db
    from app.models import GroupMessage, Group
    msg = GroupMessage.query.get_or_404(message_id)
    group_obj = Group.query.get(msg.group_id)
    
    # 作者是本人，或者是群組老師，或者是 AI 訊息且本人是該 AI 訊息所回覆的對象
    is_teacher = (group_obj.teacher_id == current_user.id)
    is_author = (msg.user_id == current_user.id)
    
    # 檢查是否為 AI 訊息且當前用戶是其回覆對象
    is_ai_reply_to_me = False
    yukine = User.query.filter_by(username='雪音老師').first()
    if yukine and msg.user_id == yukine.id and msg.parent_id:
        parent_msg = GroupMessage.query.get(msg.parent_id)
        if parent_msg and parent_msg.user_id == current_user.id:
            is_ai_reply_to_me = True

    if not is_author and not is_teacher and not is_ai_reply_to_me:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403
        
    msg.is_deleted = True
    db.session.commit()
    
    return jsonify({'status': 'success'})

@group.route('/api/groups/<int:group_id>/ai_reply', methods=['POST'], strict_slashes=False)
@login_required
def ai_reply(group_id):
    current_app.logger.info(f"AI Reply triggered for group {group_id} by user {current_user.username}")
    from app import db, bcrypt
    from app.models import User, Group, GroupMessage
    import random
    
    group_obj = Group.query.get_or_404(group_id)
    if not group_obj.has_ai:
        return jsonify({'status': 'error', 'message': 'AI is disabled'}), 400
        
    # Get last message from user to react to
    last_msg = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.desc()).first()
    yukine = User.query.filter_by(username='雪音老師').first()
    
    if not last_msg or (yukine and last_msg.user_id == yukine.id):
        return jsonify({'status': 'error', 'message': 'No user message to reply to'}), 400

    # AI Trigger Logic
    greetings = ['嗨', '哈囉', 'hello', 'hi', '安安', '早安', '午安', '晚安', '雪音', '老師', '你好', '您好']
    is_greeting = any(g in last_msg.content.lower() for g in greetings)
    
    # If it's a greeting, we reply 100% of the time. Otherwise, 80% chance or if keywords matched.
    trigger_ai = is_greeting or random.random() < 0.8
    
    if not trigger_ai:
        current_app.logger.info(f"AI skipped reply for group {group_id} (Random skip)")
        return jsonify({'status': 'skipped', 'message': 'AI decided not to reply this time'})

    # Generate AI Response
    recent_msgs = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.desc()).limit(10).all()
    chat_history = []
    if not yukine:
        yukine = User(username='雪音老師', email='yukine_bot@internal.ai', password=bcrypt.generate_password_hash('ai_placeholder').decode('utf-8'), role='teacher')
        db.session.add(yukine)
        db.session.commit()
    
    for m in reversed(recent_msgs):
        role = 'assistant' if m.user_id == yukine.id else 'user'
        chat_history.append({'role': role, 'content': m.content})
    
    from app.utils.ai_helpers import get_ai_tutor_response
    
    # Prepare context if this is a reply
    user_context = last_msg.content
    if last_msg.parent_id:
        p_msg = GroupMessage.query.get(last_msg.parent_id)
        if p_msg:
            user_context = f"(正在回覆 {p_msg.author.username} 說過的話: \"{p_msg.content}\") -> {last_msg.content}"
            
    ai_reply_text = get_ai_tutor_response(chat_history, user_context, personality_key='雪音-溫柔型')
    
    # 最終檢查：在存檔前確認父訊息是否已被收回 (避免時間差導致聯動失效)
    db.session.refresh(last_msg)
    if last_msg.is_recalled:
        current_app.logger.info(f"AI reply cancelled for group {group_id} because parent msg {last_msg.id} was recalled while thinking.")
        return jsonify({'status': 'skipped', 'message': 'Parent message recalled'})

    if ai_reply_text:
        ai_msg = GroupMessage(
            group_id=group_id, 
            user_id=yukine.id, 
            content=ai_reply_text,
            parent_id=last_msg.id  # 建立關聯以便聯動收回
        )
        db.session.add(ai_msg)
        db.session.commit()
        
        # Prepare parent info for frontend UI
        parent_preview = {
            'username': last_msg.author.username,
            'content': last_msg.content[:50] + '...' if len(last_msg.content) > 50 else last_msg.content
        }
        
        return jsonify({
            'status': 'success',
            'ai_message': {
                'id': ai_msg.id,
                'content': ai_msg.content,
                'username': '雪音老師',
                'is_mine': False,
                'is_ai': True,
                'created_at': ai_msg.created_at.isoformat() + 'Z',
                'parent_id': ai_msg.parent_id,
                'parent_preview': parent_preview
            }
        })
    
    return jsonify({'status': 'error', 'message': 'AI failed to generate reply'}), 500
