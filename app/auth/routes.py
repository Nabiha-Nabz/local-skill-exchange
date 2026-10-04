from urllib.parse import urljoin, urlparse
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from . import __name__ as _pkg
from ..extensions import db
from ..models import ActivityLog, PlatformSetting, User

bp = Blueprint("auth", __name__)


def safe_next(target):
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target or ""))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("user.dashboard"))
    enabled = db.session.get(PlatformSetting, "registration_enabled")
    if enabled and enabled.value != "true":
        flash("New registration is currently paused.", "error")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        location = request.form.get("location", "").strip()
        if len(name) < 2 or "@" not in email or len(password) < 8 or not location:
            flash("Enter your name, location, a valid email, and a password of at least 8 characters.", "error")
        elif User.query.filter(func.lower(User.email) == email).first():
            flash("An account already exists for that email.", "error")
        else:
            user = User(name=name, email=email, location=location, availability="Flexible")
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(ActivityLog(user_id=user.id, event="registered", detail="New community account registered"))
            db.session.commit()
            login_user(user)
            flash("Welcome—your account is ready.", "success")
            return redirect(url_for("user.profile_edit"))
    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("user.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter(func.lower(User.email) == email, User.role == "user").first()
        if not user or not user.check_password(request.form.get("password", "")):
            flash("Email or password is incorrect.", "error")
        elif user.status != "active":
            flash("This account is suspended. Contact the platform administrator.", "error")
        else:
            login_user(user, remember=bool(request.form.get("remember")))
            db.session.add(ActivityLog(user_id=user.id, event="login", detail="Signed in"))
            db.session.commit()
            target = request.args.get("next")
            return redirect(target if safe_next(target) else url_for("user.dashboard"))
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("main.home"))
