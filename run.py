from app import create_app, db
# from app.models import User, Question, Mistake, Group, GroupMember, Assignment

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
