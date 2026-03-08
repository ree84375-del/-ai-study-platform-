from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Group, GroupMember
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
