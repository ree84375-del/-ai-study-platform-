from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Group, GroupMember, GroupMessage
from app import db
import random
import string
from datetime import datetime, timedelta, timezone

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
            new_invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            # For demo, allow anyone to create group, but logically only teacher should
            new_group = Group(name=group_name, invite_code=new_invite_code, teacher_id=current_user.id)
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
    from app.models import GroupAnnouncement
    group_obj = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
    
    # Prevent unauthorized access
    if not membership and group_obj.teacher_id != current_user.id:
        flash('您沒有權限進入此討論板', 'danger')
        return redirect(url_for('group.groups'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        content = request.form.get('content')
        
        if content and content.strip():
            if action == 'post_announcement' and group_obj.teacher_id == current_user.id:
                ann = GroupAnnouncement(content=content.strip(), group_id=group_id)
                db.session.add(ann)
                db.session.commit()
                flash('已發布群組公告', 'success')
            elif action == 'post_message':
                msg = GroupMessage(content=content.strip(), group_id=group_id, user_id=current_user.id)
                db.session.add(msg)
                db.session.commit()
                
            return redirect(url_for('group.group_dashboard', group_id=group_id))
            
    # Load recent messages (e.g., last 100)
    messages = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.asc()).limit(100).all()
    announcements = GroupAnnouncement.query.filter_by(group_id=group_id).order_by(GroupAnnouncement.created_at.desc()).limit(5).all()
    
    return render_template('group_dashboard.html', group=group_obj, messages=messages, announcements=announcements)
