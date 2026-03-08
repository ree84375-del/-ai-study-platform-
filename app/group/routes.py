from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Group, GroupMember
from app import db
import random
import string

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

