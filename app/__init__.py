import os
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template
from .extensions import csrf, db, login_manager


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "local-skill-exchange-change-me"),
        SQLALCHEMY_DATABASE_URI="sqlite:///local_skill_exchange.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        UPLOAD_FOLDER=os.path.join(app.root_path, "static", "uploads"),
        WTF_CSRF_TIME_LIMIT=None,
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."

    from .models import Notification, PlatformSetting, User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def globals_for_templates():
        from flask_login import current_user
        unread = 0
        if current_user.is_authenticated:
            unread = Notification.query.filter_by(user_id=current_user.id, read_at=None).count()
        settings = {s.key: s.value for s in PlatformSetting.query.all()}
        return {"current_year": datetime.now().year, "unread_notifications": unread, "platform_settings": settings}

    from .auth.routes import bp as auth_bp
    from .main.routes import bp as main_bp
    from .user.routes import bp as user_bp
    from .admin.routes import bp as admin_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("error.html", code=403, title="Access denied", message="You do not have permission to view this page."), 403

    @app.errorhandler(404)
    def missing(error):
        return render_template("error.html", code=404, title="Page not found", message="The page you requested could not be found."), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("error.html", code=500, title="Something went wrong", message="The application could not complete that request."), 500

    with app.app_context():
        db.create_all()
        seed_database()
        upload_setting = db.session.get(PlatformSetting, "max_upload_mb")
        if upload_setting and upload_setting.value.isdigit():
            app.config["MAX_CONTENT_LENGTH"] = int(upload_setting.value) * 1024 * 1024
    return app


def seed_database():
    from .models import (ActivityLog, Category, Conversation, ExchangeRequest,
                         Message, Notification, PlatformSetting, Review, SavedSkill,
                         Session, Skill, User)
    categories = ["Technology", "Education", "Design", "Creative", "Music", "Languages", "Home & Garden", "Business", "Fitness", "Other"]
    for name in categories:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name))
    db.session.flush()

    people = [
        ("Tarun Yadav Gumma", "tarun@localskill.demo", "Full-stack student developer who enjoys practical, project-led learning.", "Chandigarh", "Weekday evenings"),
        ("Vishal", "vishal@localskill.demo", "Visual designer focused on clear interfaces and brand systems.", "Mohali", "Weekends"),
        ("Gulraj Gill", "gulraj@localskill.demo", "Photographer and editor who likes teaching through live examples.", "Chandigarh", "Saturday afternoons"),
        ("Himanshu Rana", "himanshu@localskill.demo", "Tutor and confident speaker with a patient, structured approach.", "Panchkula", "Flexible"),
        ("Aman", "aman@localskill.demo", "Fitness and music enthusiast who values consistent practice.", "Zirakpur", "Morning and weekends"),
    ]
    admin = User.query.filter_by(email="admin@gmail.com").first()
    if not admin:
        admin = User(name="Platform Administrator", email="admin@gmail.com", role="admin", status="active", bio="Platform operations", location="Local")
        admin.set_password("admin")
        db.session.add(admin)
    users = []
    for name, email, bio, location, availability in people:
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(name=name, email=email, bio=bio, location=location, availability=availability)
            user.set_password("User@123")
            db.session.add(user)
        users.append(user)
    db.session.flush()

    defaults = {"platform_name": "Local Skill Exchange", "post_duration": "30", "max_upload_mb": "5", "reviews_enabled": "true", "registration_enabled": "true", "maintenance_message": ""}
    for key, value in defaults.items():
        if not db.session.get(PlatformSetting, key):
            db.session.add(PlatformSetting(key=key, value=value))

    if Skill.query.count() == 0:
        listings = [
            ("Python Tutoring", "Python programming", "Graphic design", "Technology", "Build confidence with functions, Flask basics, and small projects."),
            ("Web Design", "Responsive web design", "Photography", "Design", "Learn layout, typography, and responsive CSS through a personal page."),
            ("Graphic Design", "Brand and poster design", "Programming help", "Design", "Practical Figma-free design fundamentals using accessible desktop tools."),
            ("Photography", "Portrait photography", "Guitar basics", "Creative", "Camera settings, composition, and a guided outdoor photo walk."),
            ("Guitar Lessons", "Acoustic guitar", "Excel training", "Music", "Chords, rhythm, and your first complete song at a comfortable pace."),
            ("Math Tutoring", "Mathematics", "Video editing", "Education", "Friendly support for algebra, calculus, and exam preparation."),
            ("English Conversation", "Spoken English", "Cooking lessons", "Languages", "Relaxed conversation practice with useful corrections and vocabulary."),
            ("Excel Training", "Excel formulas and charts", "Public speaking", "Business", "Turn raw data into clean formulas, pivots, and visual summaries."),
            ("Computer Repair", "PC troubleshooting", "Resume writing", "Technology", "Diagnose common Windows, hardware, and performance problems safely."),
            ("Video Editing", "Video editing", "Fitness coaching", "Creative", "Learn cuts, pacing, audio cleanup, and export settings."),
            ("Cooking Lessons", "North Indian cooking", "English conversation", "Home & Garden", "Cook two everyday dishes while learning timing and spice balance."),
            ("Gardening", "Balcony gardening", "Social media design", "Home & Garden", "Choose hardy plants, mix soil, and build a simple care routine."),
            ("Resume Writing", "Resume and interview prep", "Basic accounting", "Business", "Create a focused one-page resume and practice strong answers."),
            ("Public Speaking", "Presentation confidence", "Photography", "Education", "Structure short talks, use your voice, and handle stage nerves."),
            ("Basic Accounting", "Bookkeeping basics", "Presentation design", "Business", "Understand ledgers, cash flow, and common small-business records."),
            ("Fitness Coaching", "Bodyweight fitness", "Basic coding", "Fitness", "A safe beginner routine built around mobility and consistency."),
            ("Language Exchange", "Hindi conversation", "English conversation", "Languages", "Casual bilingual practice for everyday confidence."),
            ("Social Media Design", "Social post design", "Gardening", "Design", "Build reusable layouts with strong hierarchy and consistent branding."),
            ("Presentation Design", "Slide storytelling", "Math tutoring", "Design", "Turn dense ideas into clear, persuasive slides."),
            ("Basic Coding", "HTML, CSS, JavaScript", "Guitar lessons", "Technology", "Build an interactive page while learning core web concepts."),
            ("Mobile Photography", "Phone photography", "Web design", "Creative", "Get better light, framing, and edits using the phone you have."),
            ("Data Visualization", "Charts and dashboards", "Public speaking", "Technology", "Choose honest charts and explain data with clarity."),
            ("Home Organization", "Practical organization", "Fitness coaching", "Home & Garden", "Set up a simple decluttering system you can maintain."),
            ("Interview Practice", "Mock interviews", "Video editing", "Business", "Practice concise answers with specific, supportive feedback."),
        ]
        cat_map = {c.name: c for c in Category.query.all()}
        start = datetime.now(timezone.utc)
        for i, item in enumerate(listings):
            title, offered, wanted, category, description = item
            db.session.add(Skill(owner=users[i % len(users)], category=cat_map[category], title=title, offered=offered, wanted=wanted, description=description, experience=["Beginner friendly", "Intermediate", "Advanced"][i % 3], availability=["Weekends", "Evenings", "Flexible"][i % 3], location=users[i % len(users)].location, views=12 + i * 7, created_at=start - timedelta(days=i % 12), expires_at=start + timedelta(days=18 + i)))
        db.session.flush()

    if ExchangeRequest.query.count() == 0:
        skills = Skill.query.order_by(Skill.id).limit(5).all()
        states = ["pending", "accepted", "in_progress", "completed"]
        for i, state in enumerate(states):
            requester = users[(i + 1) % len(users)]
            skill = skills[i]
            ex = ExchangeRequest(skill=skill, requester=requester, provider=skill.owner, offered_skill="Help with " + ["design", "photography", "editing", "fitness"][i], message="I would enjoy learning together and can offer useful help in return.", status=state, completed_at=now_utc() if state == "completed" else None)
            db.session.add(ex)
            db.session.flush()
            if state in {"accepted", "in_progress", "completed"}:
                conv = Conversation(exchange=ex)
                db.session.add(conv)
                db.session.flush()
                db.session.add_all([Message(conversation_id=conv.id, sender_id=requester.id, body="Hi! Thanks for accepting the exchange."), Message(conversation_id=conv.id, sender_id=skill.owner_id, body="Glad to connect. Let us choose a good time.")])
            if state in {"in_progress", "completed"}:
                db.session.add(Session(exchange=ex, scheduled_at=datetime.now() + timedelta(days=3-i), duration=60, notes="Online session", status="completed" if state == "completed" else "upcoming"))
        db.session.flush()
        completed = ExchangeRequest.query.filter_by(status="completed").first()
        db.session.add(Review(exchange_id=completed.id, reviewer_id=completed.requester_id, reviewed_user_id=completed.provider_id, stars=5, comment="Patient, practical, and very helpful."))

    if Notification.query.count() == 0:
        for i, user in enumerate(users):
            db.session.add(Notification(user_id=user.id, text="Welcome to the local skill exchange community.", link="/explore"))
            db.session.add(ActivityLog(user_id=user.id, event="account_seeded", detail=f"Demo profile created for {user.name}"))
    if SavedSkill.query.count() == 0:
        db.session.add_all([SavedSkill(user_id=users[0].id, skill_id=Skill.query.order_by(Skill.id.desc()).first().id), SavedSkill(user_id=users[1].id, skill_id=Skill.query.order_by(Skill.id).first().id)])
    db.session.commit()


def now_utc():
    return datetime.now(timezone.utc)
