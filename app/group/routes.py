from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Group, GroupMember, GroupMessage
from app import db
import random
import string
from datetime import datetime, timedelta, timezone
from app.utils.ai_helpers import get_ai_tutor_response

group = Blueprint('group', __name__)

@group.route("/groups", methods=['GET', 'POST'])
@login_required
def groups():
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Join a group
        if action == 'join':
            invite_code = request.form.get('invite_code')
            group_to_join = Group.query.filter_by(invite_code=invite_code).first()
            if not group_to_join:
                flash('找不到此群組代碼', 'danger')
            else:
                existing_member = GroupMember.query.filter_by(group_id=group_to_join.id, user_id=current_user.id).first()
                if existing_member:
                    flash('您已經在這個群組裡了', 'info')
                else:
                    new_member = GroupMember(group_id=group_to_join.id, user_id=current_user.id)
                    db.session.add(new_member)
                    db.session.commit()
                    flash(f'成功加入群組: {group_to_join.name}', 'success')
                    
        # Create a group (Simulating teacher role for demo)
        elif action == 'create':
            group_name = request.form.get('group_name')
            has_ai = request.form.get('has_ai') == 'on'
            new_invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            # For demo, allow anyone to create group, but logically only teacher should
            new_group = Group(name=group_name, invite_code=new_invite_code, teacher_id=current_user.id, has_ai=has_ai)
            db.session.add(new_group)
            db.session.flush() # get id
            
            # add creator as member
            new_member = GroupMember(group_id=new_group.id, user_id=current_user.id)
            db.session.add(new_member)
            db.session.commit()
            
            flash(f'成功建立群組，邀請碼為: {new_invite_code}', 'success')
            
        return redirect(url_for('group.groups'))

    # GET: fetch user's groups
    user_memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
    user_groups = [membership.group_info for membership in user_memberships]
    
    return render_template('groups.html', title='我的群組', groups=user_groups)

@group.route("/api/online_members/<int:group_id>")
@login_required
def online_members(group_id):
    # Check if user is a member or teacher of this group
    is_member = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    group_info = Group.query.get_or_404(group_id)
    
    if not is_member and group_info.teacher_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
        
    # Get members active in the last 10 minutes
    ten_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    
    memberships = GroupMember.query.filter_by(group_id=group_id).all()
    user_ids = [m.user_id for m in memberships]
    
    # Query online users from the user IDs
    from app.models import User
    online_users = User.query.filter(User.id.in_(user_ids), User.last_active_at >= ten_minutes_ago).all()
    
    results = [{'id': u.id, 'username': u.username, 'last_active': u.last_active_at.isoformat()} for u in online_users]
    return jsonify({'online_members': results})

@group.route("/groups/<int:group_id>/leave", methods=['POST'])
@login_required
def leave_group(group_id):
    group_obj = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    
    if not membership:
        flash('您不在此群組中', 'danger')
        return redirect(url_for('group.groups'))
        
    if group_obj.teacher_id == current_user.id:
        # Teacher: Delete entire group
        GroupMember.query.filter_by(group_id=group_id).delete()
        # Note: In a real app we'd also delete GroupMessage etc., assuming cascade or manual
        db.session.delete(group_obj)
        db.session.commit()
        flash(f'已解散群組：{group_obj.name}', 'success')
    else:
        # Student: Leave group
        db.session.delete(membership)
        db.session.commit()
        flash(f'已退出群組：{group_obj.name}', 'success')
        
    return redirect(url_for('group.groups'))

@group.route("/groups/<int:group_id>/dashboard", methods=['GET', 'POST'])
@login_required
def group_dashboard(group_id):
    from app.models import GroupMember, GroupAnnouncement, GroupMessage, Assignment, AssignmentStatus, User
    
    group_obj = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    
    # Prevent unauthorized access
    if not membership and group_obj.teacher_id != current_user.id:
        flash('您沒有權限進入此討論板', 'danger')
        return redirect(url_for('group.groups'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        content = request.form.get('content')
        image_data = request.form.get('image_data')
        
        # Post Message
        if action == 'post_message':
            if (content and content.strip()) or image_data:
                msg = GroupMessage(content=(content.strip() if content else ""), group_id=group_id, user_id=current_user.id, image_data=image_data)
                db.session.add(msg)
                db.session.commit()
            
                # AI Response Logic if enabled
                if group_obj.has_ai:
                    # Singleton Yukine: Find or create a specific AI user
                    yukine = User.query.filter_by(username='雪音老師').first()
                    if not yukine:
                        yukine = User(username='雪音老師', email='yukine_bot@internal.ai', password=bcrypt.generate_password_hash('ai_placeholder').decode('utf-8'), role='teacher')
                        db.session.add(yukine)
                        db.session.commit()
                    
                    if current_user.id != yukine.id:
                        recent_msgs = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.desc()).limit(10).all()
                        chat_history = []
                        for m in reversed(recent_msgs):
                            role = 'assistant' if m.user_id == yukine.id else 'user'
                            chat_history.append({'role': role, 'content': m.content})
                        
                        ai_prompt = content.strip() if content else ""
                        if image_data:
                            ai_prompt += " (學生分享了一張圖片)"
                        
                        ai_reply = get_ai_tutor_response(chat_history, ai_prompt, personality_key='雪音-溫柔型')
                        
                        ai_msg = GroupMessage(content=ai_reply, group_id=group_id, user_id=yukine.id)
                        db.session.add(ai_msg)
                        db.session.commit()
                        
        # Post Announcement (Teacher only)
        elif action == 'post_announcement' and group_obj.teacher_id == current_user.id:
            if content and content.strip():
                ann = GroupAnnouncement(content=content.strip(), group_id=group_id)
                db.session.add(ann)
                db.session.commit()
                flash('已發布群組公告', 'success')
                
        # Update Settings (Teacher only)
        elif action == 'update_settings' and group_obj.teacher_id == current_user.id:
            new_name = request.form.get('group_name')
            has_ai = request.form.get('has_ai') == 'on'
            if new_name:
                group_obj.name = new_name.strip()
            group_obj.has_ai = has_ai
            db.session.commit()
            flash('群組設定已更新', 'success')
            
        # Toggle AI
        elif action == 'toggle_ai':
            group_obj.has_ai = not group_obj.has_ai
            db.session.commit()
            status = "進入了討論" if group_obj.has_ai else "離開了討論"
            flash(f'雪音老師{status}', 'info')
            
        # Publish Assignment (Teacher only)
        elif action == 'publish_assignment' and group_obj.teacher_id == current_user.id:
            title = request.form.get('title')
            desc = request.form.get('description')
            due_days = int(request.form.get('due_days', 7))
            if title:
                due_date = datetime.now(timezone.utc) + timedelta(days=due_days)
                new_assign = Assignment(title=title.strip(), description=desc, group_id=group_id, due_date=due_date)
                db.session.add(new_assign)
                db.session.commit()
                flash(f'作業「{title}」已發布', 'success')
                
        # Submit Assignment
        elif action == 'submit_assignment':
            assign_id = request.form.get('assignment_id')
            content_val = request.form.get('content')
            if assign_id and content_val:
                status = AssignmentStatus.query.filter_by(assignment_id=assign_id, user_id=current_user.id).first()
                if not status:
                    status = AssignmentStatus(assignment_id=assign_id, user_id=current_user.id)
                    db.session.add(status)
                status.content = content_val
                status.is_completed = True
                status.completed_at = datetime.now(timezone.utc)
                db.session.commit()
                
                # Immediate AI Grading
                assign_obj = Assignment.query.get(assign_id)
                from app.utils.ai_helpers import get_yukine_feedback
                feedback, score = get_yukine_feedback(content_val, assign_obj.title, assign_obj.description)
                status.ai_feedback = feedback
                status.score = score
                db.session.commit()
                flash(f'作業已繳交！雪音老師已完成批改。', 'success')
                
        return redirect(url_for('group.group_dashboard', group_id=group_id))
            
    # Sort assignments: those with due_date first, then None (no deadline)
    # Use datetime.max with timezone for sorting None values to the end
    sorted_assignments = []
    if group_obj.assignments:
        sorted_assignments = sorted(
            group_obj.assignments, 
            key=lambda x: x.due_date if x.due_date else datetime(9999, 12, 31, tzinfo=timezone.utc)
        )
    
    return render_template('group_dashboard.html', 
                           group=group_obj, 
                           messages=messages, 
                           announcements=announcements,
                           assignments=sorted_assignments)
@group.route("/groups/<int:group_id>/update_member_role/<int:user_id>", methods=['POST'])
@login_required
def update_member_role(group_id, user_id):
    from app.models import User
    group_obj = Group.query.get_or_404(group_id)
    
    # Permission check: Only group creator can change roles
    if group_obj.teacher_id != current_user.id:
        flash('您沒有權限執行此操作', 'danger')
        return redirect(url_for('group.group_dashboard', group_id=group_id))
    
    user_to_update = User.query.get_or_404(user_id)
    new_role = request.form.get('new_role')
    
    if new_role in ['student', 'teacher']:
        # prevent self-demotion or updating admin via group dashboard
        if user_to_update.id != current_user.id and user_to_update.email != 'ree84375@gmail.com':
            user_to_update.role = new_role
            db.session.commit()
            flash(f'已將 {user_to_update.username} 的角色更新為 {new_role}', 'success')
        else:
            flash('您無法更改此使用者的角色', 'warning')
    else:
        flash('無效的角色選擇', 'danger')
        
    return redirect(url_for('group.group_dashboard', group_id=group_id))
