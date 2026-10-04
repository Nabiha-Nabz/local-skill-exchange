from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_
from ..extensions import db
from ..models import (ActivityLog, Category, ExchangeRequest, Message, Notification,
    PlatformSetting, Report, Review, Session, Skill, User)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin": abort(403)
        return view(*args, **kwargs)
    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and current_user.role == "admin": return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower(), role="admin", status="active").first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user); db.session.add(ActivityLog(user_id=user.id, event="admin_login", detail="Administrator signed in")); db.session.commit(); return redirect(url_for("admin.dashboard"))
        flash("Administrator credentials are incorrect.", "error")
    return render_template("admin/login.html")


@bp.route("/logout", methods=["POST"])
@admin_required
def logout(): logout_user(); return redirect(url_for("admin.login"))


@bp.route("/dashboard")
@admin_required
def dashboard():
    stats = {"users": User.query.filter_by(role="user").count(), "skills": Skill.query.count(), "exchanges": ExchangeRequest.query.count(), "reports": Report.query.filter(Report.status.in_(["open", "under_review"])).count(), "messages": Message.query.count()}
    statuses = dict(db.session.query(ExchangeRequest.status, func.count(ExchangeRequest.id)).group_by(ExchangeRequest.status).all())
    categories = dict(db.session.query(Category.name, func.count(Skill.id)).outerjoin(Skill).group_by(Category.name).all())
    activity = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(12).all()
    return render_template("admin/dashboard.html", stats=stats, statuses=statuses, categories=categories, activity=activity)


@bp.route("/users")
@admin_required
def users():
    query = User.query.filter(User.role == "user")
    q = request.args.get("q", "").strip()
    if q: query = query.filter(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"), User.location.ilike(f"%{q}%")))
    status = request.args.get("status")
    if status: query = query.filter_by(status=status)
    return render_template("admin/table.html", kind="users", rows=query.order_by(User.created_at.desc()).all())


@bp.route("/users/<int:user_id>/<action>", methods=["POST"])
@admin_required
def user_action(user_id, action):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id or user.role == "admin": abort(403)
    if action == "suspend": user.status = "suspended"
    elif action == "restore": user.status = "active"
    elif action == "delete": db.session.delete(user)
    else: abort(404)
    db.session.add(ActivityLog(user_id=current_user.id, event="admin_user_action", detail=f"{action.title()} user {user.email}")); db.session.commit(); flash("User record updated.", "success"); return redirect(url_for("admin.users"))


@bp.route("/skills")
@admin_required
def skills():
    query = Skill.query
    q = request.args.get("q", "").strip()
    if q: query = query.filter(or_(Skill.title.ilike(f"%{q}%"), Skill.offered.ilike(f"%{q}%")))
    status = request.args.get("status")
    if status: query = query.filter_by(status=status)
    return render_template("admin/table.html", kind="skills", rows=query.order_by(Skill.created_at.desc()).all())


@bp.route("/skills/<int:skill_id>/<action>", methods=["POST"])
@admin_required
def skill_action(skill_id, action):
    skill = db.get_or_404(Skill, skill_id)
    if action == "disable": skill.status = "disabled"
    elif action == "restore": skill.status = "active"
    elif action == "delete": db.session.delete(skill)
    else: abort(404)
    db.session.add(ActivityLog(user_id=current_user.id, event="admin_skill_action", detail=f"{action.title()} skill #{skill_id}")); db.session.commit(); flash("Listing updated.", "success"); return redirect(url_for("admin.skills"))


@bp.route("/exchanges")
@admin_required
def exchanges():
    query = ExchangeRequest.query
    if request.args.get("status"): query = query.filter_by(status=request.args["status"])
    return render_template("admin/table.html", kind="exchanges", rows=query.order_by(ExchangeRequest.created_at.desc()).all())


@bp.route("/messages")
@admin_required
def messages():
    stats = {"conversations": db.session.query(func.count(func.distinct(Message.conversation_id))).scalar() or 0, "messages": Message.query.count(), "attachments": db.session.query(func.count()).select_from(__import__("app.models", fromlist=["Attachment"]).Attachment).scalar() or 0, "last_7_days": Message.query.filter(Message.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)).count()}
    return render_template("admin/messages.html", stats=stats)


@bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        if name and not Category.query.filter(func.lower(Category.name) == name.lower()).first(): db.session.add(Category(name=name)); db.session.commit(); flash("Category added.", "success")
        else: flash("Enter a unique category name.", "error")
    return render_template("admin/categories.html", categories=Category.query.order_by(Category.name).all())


@bp.route("/categories/<int:category_id>", methods=["POST"])
@admin_required
def category_action(category_id):
    category = db.get_or_404(Category, category_id)
    name = request.form.get("name", "").strip()
    if name: category.name = name[:80]
    if "toggle" in request.form: category.enabled = not category.enabled
    db.session.commit(); flash("Category updated.", "success"); return redirect(url_for("admin.categories"))


@bp.route("/reports")
@admin_required
def reports(): return render_template("admin/table.html", kind="reports", rows=Report.query.order_by(Report.created_at.desc()).all())


@bp.route("/reports/<int:report_id>/<action>", methods=["POST"])
@admin_required
def report_action(report_id, action):
    report = db.get_or_404(Report, report_id)
    states = {"review": "under_review", "resolve": "resolved", "dismiss": "dismissed"}
    if action not in states: abort(404)
    report.status = states[action]; db.session.commit(); flash("Report updated.", "success"); return redirect(url_for("admin.reports"))


@bp.route("/sessions")
@admin_required
def sessions(): return render_template("admin/table.html", kind="sessions", rows=Session.query.order_by(Session.scheduled_at.desc()).all())


@bp.route("/reviews")
@admin_required
def reviews(): return render_template("admin/table.html", kind="reviews", rows=Review.query.order_by(Review.created_at.desc()).all())


@bp.route("/reviews/<int:review_id>/delete", methods=["POST"])
@admin_required
def review_delete(review_id): db.session.delete(db.get_or_404(Review, review_id)); db.session.commit(); flash("Review removed.", "success"); return redirect(url_for("admin.reviews"))


@bp.route("/activity")
@admin_required
def activity():
    query = ActivityLog.query
    if request.args.get("event"): query = query.filter(ActivityLog.event.ilike(f"%{request.args['event']}%"))
    if request.args.get("q"): query = query.filter(ActivityLog.detail.ilike(f"%{request.args['q']}%"))
    page = query.order_by(ActivityLog.created_at.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=30, error_out=False)
    return render_template("admin/activity.html", page=page)


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        for key in ["platform_name", "post_duration", "max_upload_mb", "reviews_enabled", "registration_enabled", "maintenance_message"]:
            setting = db.session.get(PlatformSetting, key)
            value = request.form.get(key, "false" if key.endswith("enabled") else "").strip()[:500]
            if setting: setting.value = value
        db.session.commit(); flash("Settings saved and active.", "success")
    return render_template("admin/settings.html", settings={s.key: s.value for s in PlatformSetting.query.all()})


@bp.route("/notifications")
@admin_required
def notifications(): return render_template("user/notifications.html", notifications=Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all(), admin_view=True)

