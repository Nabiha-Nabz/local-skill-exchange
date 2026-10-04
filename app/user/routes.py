import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, func, or_
from werkzeug.utils import secure_filename
from ..extensions import db
from ..models import (ActivityLog, Attachment, Block, Category, Conversation,
    ExchangeRequest, Message, Notification, PlatformSetting, RecentlyViewed,
    Report, Review, SavedSkill, Session, Skill, User)

bp = Blueprint("user", __name__)
ALLOWED = {"png", "jpg", "jpeg", "gif", "pdf", "txt", "doc", "docx", "ppt", "pptx", "xls", "xlsx"}


def log(event, detail):
    db.session.add(ActivityLog(user_id=current_user.id, event=event, detail=detail))


def exchange_for_user(exchange_id):
    exchange = db.get_or_404(ExchangeRequest, exchange_id)
    if current_user.id not in {exchange.requester_id, exchange.provider_id} and current_user.role != "admin":
        abort(403)
    return exchange


def conversation_for_user(conversation_id):
    conversation = db.get_or_404(Conversation, conversation_id)
    exchange_for_user(conversation.exchange_id)
    return conversation


@bp.route("/dashboard")
@login_required
def dashboard():
    my_exchanges = ExchangeRequest.query.filter(or_(ExchangeRequest.requester_id == current_user.id, ExchangeRequest.provider_id == current_user.id))
    status_rows = db.session.query(ExchangeRequest.status, func.count(ExchangeRequest.id)).filter(or_(ExchangeRequest.requester_id == current_user.id, ExchangeRequest.provider_id == current_user.id)).group_by(ExchangeRequest.status).all()
    categories = db.session.query(Category.name, func.count(Skill.id)).join(Skill).filter(Skill.owner_id == current_user.id).group_by(Category.name).all()
    recent_activity = ActivityLog.query.filter_by(user_id=current_user.id).order_by(ActivityLog.created_at.desc()).limit(8).all()
    upcoming = Session.query.join(ExchangeRequest).filter(or_(ExchangeRequest.requester_id == current_user.id, ExchangeRequest.provider_id == current_user.id), Session.status == "upcoming").order_by(Session.scheduled_at).limit(4).all()
    stats = {"skills": Skill.query.filter_by(owner_id=current_user.id).count(), "exchanges": my_exchanges.count(), "completed": my_exchanges.filter(ExchangeRequest.status == "completed").count(), "saved": SavedSkill.query.filter_by(user_id=current_user.id).count()}
    return render_template("user/dashboard.html", stats=stats, statuses=dict(status_rows), categories=dict(categories), activity=recent_activity, upcoming=upcoming)


@bp.route("/profile/<int:user_id>")
def profile(user_id):
    user = db.get_or_404(User, user_id)
    if user.status != "active" and (not current_user.is_authenticated or current_user.role != "admin"):
        abort(404)
    skills = Skill.query.filter_by(owner_id=user.id, status="active").all()
    reviews = Review.query.filter_by(reviewed_user_id=user.id).order_by(Review.created_at.desc()).all()
    rating = db.session.query(func.avg(Review.stars)).filter_by(reviewed_user_id=user.id).scalar() or 0
    blocked = current_user.is_authenticated and Block.query.filter_by(blocker_id=current_user.id, blocked_id=user.id).first()
    return render_template("user/profile.html", user=user, skills=skills, reviews=reviews, rating=rating, blocked=blocked)


@bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def profile_edit():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if len(name) < 2:
            flash("Please enter your full name.", "error")
        else:
            current_user.name = name
            current_user.bio = request.form.get("bio", "").strip()[:800]
            current_user.location = request.form.get("location", "").strip()[:120]
            current_user.availability = request.form.get("availability", "").strip()[:120]
            image = request.files.get("avatar")
            if image and image.filename:
                ext = image.filename.rsplit(".", 1)[-1].lower()
                if ext not in {"png", "jpg", "jpeg"}:
                    flash("Profile images must be PNG or JPEG.", "error")
                    return render_template("user/profile_edit.html")
                filename = f"avatar-{current_user.id}-{uuid.uuid4().hex}.{ext}"
                image.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
                current_user.avatar = filename
            log("profile_updated", "Updated profile details")
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("user.profile", user_id=current_user.id))
    return render_template("user/profile_edit.html")


def read_skill_form(skill=None):
    title = request.form.get("title", "").strip()
    offered = request.form.get("offered", "").strip()
    wanted = request.form.get("wanted", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    category = Category.query.filter_by(id=request.form.get("category_id", type=int), enabled=True).first()
    if not all([title, offered, wanted, description, location, category]) or len(description) < 20:
        return None, "Complete every field; the description must be at least 20 characters."
    duration = int((db.session.get(PlatformSetting, "post_duration") or PlatformSetting(value="30")).value)
    data = dict(title=title[:140], offered=offered[:140], wanted=wanted[:140], description=description[:2000], location=location[:120], category=category, experience=request.form.get("experience", "Intermediate"), availability=request.form.get("availability", "Flexible"))
    if not skill:
        data["expires_at"] = datetime.now(timezone.utc) + timedelta(days=duration)
    return data, None


@bp.route("/skills/create", methods=["GET", "POST"])
@login_required
def skill_create():
    if request.method == "POST":
        data, error = read_skill_form()
        if error:
            flash(error, "error")
        else:
            skill = Skill(owner_id=current_user.id, **data)
            db.session.add(skill)
            db.session.flush()
            log("skill_created", f"Published {skill.title}")
            db.session.commit()
            flash("Skill published successfully.", "success")
            return redirect(url_for("main.skill_detail", skill_id=skill.id))
    return render_template("skills/form.html", categories=Category.query.filter_by(enabled=True).order_by(Category.name).all(), skill=None)


@bp.route("/skills/<int:skill_id>/edit", methods=["GET", "POST"])
@login_required
def skill_edit(skill_id):
    skill = db.get_or_404(Skill, skill_id)
    if skill.owner_id != current_user.id:
        abort(403)
    if request.method == "POST":
        data, error = read_skill_form(skill)
        if error:
            flash(error, "error")
        else:
            for key, value in data.items(): setattr(skill, key, value)
            log("skill_updated", f"Updated {skill.title}")
            db.session.commit()
            flash("Listing updated.", "success")
            return redirect(url_for("main.skill_detail", skill_id=skill.id))
    return render_template("skills/form.html", categories=Category.query.filter_by(enabled=True).order_by(Category.name).all(), skill=skill)


@bp.route("/skills/<int:skill_id>/<action>", methods=["POST"])
@login_required
def skill_action(skill_id, action):
    skill = db.get_or_404(Skill, skill_id)
    if skill.owner_id != current_user.id:
        abort(403)
    if action == "delete":
        db.session.delete(skill); message = "Listing deleted."
    elif action in {"pause", "activate"}:
        skill.status = "paused" if action == "pause" else "active"; message = f"Listing {action}d."
    elif action == "renew":
        duration = int(db.session.get(PlatformSetting, "post_duration").value)
        skill.expires_at = datetime.now(timezone.utc) + timedelta(days=duration); skill.status = "active"; message = "Listing renewed."
    else: abort(404)
    log("skill_action", f"{action.title()} listing {skill.title}")
    db.session.commit(); flash(message, "success")
    return redirect(url_for("user.my_skills"))


@bp.route("/my-skills")
@login_required
def my_skills():
    return render_template("skills/mine.html", skills=Skill.query.filter_by(owner_id=current_user.id).order_by(Skill.created_at.desc()).all())


@bp.route("/skills/<int:skill_id>/save", methods=["POST"])
@login_required
def save_skill(skill_id):
    db.get_or_404(Skill, skill_id)
    saved = SavedSkill.query.filter_by(user_id=current_user.id, skill_id=skill_id).first()
    if saved: db.session.delete(saved); flash("Removed from saved skills.", "success")
    else: db.session.add(SavedSkill(user_id=current_user.id, skill_id=skill_id)); flash("Skill saved.", "success")
    db.session.commit(); return redirect(request.referrer or url_for("main.explore"))


@bp.route("/saved")
@login_required
def saved():
    return render_template("skills/saved.html", items=SavedSkill.query.filter_by(user_id=current_user.id).order_by(SavedSkill.created_at.desc()).all(), title="Saved skills")


@bp.route("/recently-viewed")
@login_required
def recently_viewed():
    return render_template("skills/saved.html", items=RecentlyViewed.query.filter_by(user_id=current_user.id).order_by(RecentlyViewed.viewed_at.desc()).all(), title="Recently viewed")


@bp.route("/skills/<int:skill_id>/request", methods=["POST"])
@login_required
def request_exchange(skill_id):
    skill = db.get_or_404(Skill, skill_id)
    if skill.owner_id == current_user.id: abort(400)
    if Block.query.filter(or_(and_(Block.blocker_id == current_user.id, Block.blocked_id == skill.owner_id), and_(Block.blocker_id == skill.owner_id, Block.blocked_id == current_user.id))).first():
        abort(403)
    existing = ExchangeRequest.query.filter_by(skill_id=skill.id, requester_id=current_user.id).filter(ExchangeRequest.status.in_(["pending", "accepted", "in_progress"])).first()
    if existing: flash("You already have an active request for this skill.", "error")
    else:
        ex = ExchangeRequest(skill=skill, requester_id=current_user.id, provider_id=skill.owner_id, offered_skill=request.form.get("offered_skill", "").strip()[:140], message=request.form.get("message", "").strip()[:1000])
        if not ex.offered_skill: flash("Tell the provider which skill you can offer.", "error"); return redirect(url_for("main.skill_detail", skill_id=skill.id))
        db.session.add(ex); db.session.flush(); db.session.add(Notification(user_id=skill.owner_id, text=f"{current_user.name} requested an exchange for {skill.title}.", link="/exchanges")); log("exchange_requested", f"Requested {skill.title}"); db.session.commit(); flash("Exchange request sent.", "success")
    return redirect(url_for("user.exchanges"))


@bp.route("/exchanges")
@login_required
def exchanges():
    items = ExchangeRequest.query.filter(or_(ExchangeRequest.requester_id == current_user.id, ExchangeRequest.provider_id == current_user.id)).order_by(ExchangeRequest.created_at.desc()).all()
    return render_template("user/exchanges.html", exchanges=items)


@bp.route("/exchanges/<int:exchange_id>/<action>", methods=["POST"])
@login_required
def exchange_action(exchange_id, action):
    ex = exchange_for_user(exchange_id)
    if action in {"accept", "reject"}:
        if current_user.id != ex.provider_id or ex.status != "pending": abort(403)
        ex.status = "accepted" if action == "accept" else "rejected"
        if action == "accept" and not Conversation.query.filter_by(exchange_id=ex.id).first(): db.session.add(Conversation(exchange_id=ex.id))
    elif action == "cancel":
        if current_user.id != ex.requester_id or ex.status not in {"pending", "accepted"}: abort(403)
        ex.status = "cancelled"
    elif action == "start":
        if ex.status != "accepted": abort(400)
        ex.status = "in_progress"
    elif action == "complete":
        if ex.status not in {"accepted", "in_progress"}: abort(400)
        ex.status = "completed"; ex.completed_at = datetime.now(timezone.utc)
    else: abort(404)
    other = ex.provider_id if current_user.id == ex.requester_id else ex.requester_id
    db.session.add(Notification(user_id=other, text=f"Exchange #{ex.id} was {ex.status.replace('_', ' ')}.", link="/exchanges")); log("exchange_updated", f"Exchange #{ex.id}: {ex.status}"); db.session.commit(); flash("Exchange updated.", "success")
    return redirect(url_for("user.exchanges"))


@bp.route("/messages")
@login_required
def messages():
    conversations = Conversation.query.join(ExchangeRequest).filter(or_(ExchangeRequest.requester_id == current_user.id, ExchangeRequest.provider_id == current_user.id)).order_by(Conversation.created_at.desc()).all()
    return render_template("chat/list.html", conversations=conversations)


@bp.route("/messages/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def conversation(conversation_id):
    conv = conversation_for_user(conversation_id)
    if request.method == "POST":
        text = request.form.get("body", "").strip()[:4000]
        upload = request.files.get("attachment")
        if not text and not (upload and upload.filename): flash("Write a message or attach a file.", "error")
        else:
            msg = Message(conversation_id=conv.id, sender_id=current_user.id, body=text)
            db.session.add(msg); db.session.flush()
            if upload and upload.filename:
                ext = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
                if ext not in ALLOWED: flash("That file type is not supported.", "error"); db.session.rollback(); return redirect(url_for("user.conversation", conversation_id=conv.id))
                stored = f"file-{uuid.uuid4().hex}.{ext}"
                upload.save(os.path.join(current_app.config["UPLOAD_FOLDER"], stored))
                db.session.add(Attachment(message_id=msg.id, stored_name=stored, original_name=secure_filename(upload.filename), mime_type=upload.mimetype or "application/octet-stream", size=os.path.getsize(os.path.join(current_app.config["UPLOAD_FOLDER"], stored))))
            other = conv.exchange.provider_id if current_user.id == conv.exchange.requester_id else conv.exchange.requester_id
            db.session.add(Notification(user_id=other, text=f"New message from {current_user.name}.", link=f"/messages/{conv.id}")); db.session.commit(); flash("Message sent.", "success")
            return redirect(url_for("user.conversation", conversation_id=conv.id))
    Message.query.filter_by(conversation_id=conv.id).filter(Message.sender_id != current_user.id, Message.read_at.is_(None)).update({Message.read_at: datetime.now(timezone.utc)}, synchronize_session=False); db.session.commit()
    return render_template("chat/conversation.html", conversation=conv, messages=Message.query.filter_by(conversation_id=conv.id).order_by(Message.created_at).all())


@bp.route("/messages/<int:conversation_id>/poll")
@login_required
def poll_messages(conversation_id):
    conv = conversation_for_user(conversation_id); after = request.args.get("after", 0, type=int)
    rows = Message.query.filter(Message.conversation_id == conv.id, Message.id > after).order_by(Message.id).all()
    return jsonify([{"id": m.id, "body": m.body, "sender": m.sender.name, "mine": m.sender_id == current_user.id, "time": m.created_at.isoformat()} for m in rows])


@bp.route("/attachments/<int:attachment_id>")
@login_required
def attachment(attachment_id):
    item = db.get_or_404(Attachment, attachment_id); conversation_for_user(item.message.conversation_id)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], item.stored_name, as_attachment=True, download_name=item.original_name)


@bp.route("/notifications")
@login_required
def notifications():
    return render_template("user/notifications.html", notifications=Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all())


@bp.route("/notifications/<action>", methods=["POST"])
@login_required
def notification_action(action):
    if action == "read-all": Notification.query.filter_by(user_id=current_user.id, read_at=None).update({Notification.read_at: datetime.now(timezone.utc)}, synchronize_session=False)
    else:
        item = Notification.query.filter_by(id=int(action), user_id=current_user.id).first_or_404(); item.read_at = datetime.now(timezone.utc)
    db.session.commit(); return redirect(request.referrer or url_for("user.notifications"))


@bp.route("/exchanges/<int:exchange_id>/schedule", methods=["GET", "POST"])
@login_required
def schedule(exchange_id):
    ex = exchange_for_user(exchange_id)
    if ex.status not in {"accepted", "in_progress"}: abort(400)
    session = Session.query.filter_by(exchange_id=ex.id).first()
    if request.method == "POST":
        try: scheduled = datetime.fromisoformat(request.form.get("scheduled_at", ""))
        except ValueError: flash("Choose a valid date and time.", "error"); return render_template("user/schedule.html", exchange=ex, session=session)
        if scheduled < datetime.now(): flash("Choose a future time.", "error")
        else:
            if not session: session = Session(exchange_id=ex.id, scheduled_at=scheduled); db.session.add(session)
            session.scheduled_at = scheduled; session.duration = max(15, min(180, request.form.get("duration", 60, type=int))); session.notes = request.form.get("notes", "").strip()[:600]; session.status = "upcoming"; db.session.commit(); flash("Session scheduled.", "success"); return redirect(url_for("user.session_room", session_id=session.id))
    return render_template("user/schedule.html", exchange=ex, session=session)


@bp.route("/sessions/<int:session_id>")
@login_required
def session_room(session_id):
    session = db.get_or_404(Session, session_id); exchange_for_user(session.exchange_id)
    return render_template("user/session_room.html", session=session)


@bp.route("/sessions/<int:session_id>/<action>", methods=["POST"])
@login_required
def session_action(session_id, action):
    session = db.get_or_404(Session, session_id); exchange_for_user(session.exchange_id)
    if action not in {"cancelled", "completed"}: abort(404)
    session.status = action; db.session.commit(); flash(f"Session marked {action}.", "success"); return redirect(url_for("user.exchanges"))


@bp.route("/exchanges/<int:exchange_id>/review", methods=["POST"])
@login_required
def review(exchange_id):
    setting = db.session.get(PlatformSetting, "reviews_enabled")
    if setting and setting.value != "true": abort(403)
    ex = exchange_for_user(exchange_id)
    if ex.status != "completed" or Review.query.filter_by(exchange_id=ex.id, reviewer_id=current_user.id).first(): abort(400)
    stars = request.form.get("stars", type=int)
    if stars not in range(1, 6): abort(400)
    other = ex.provider_id if current_user.id == ex.requester_id else ex.requester_id
    db.session.add(Review(exchange_id=ex.id, reviewer_id=current_user.id, reviewed_user_id=other, stars=stars, comment=request.form.get("comment", "").strip()[:1000])); db.session.commit(); flash("Review submitted.", "success"); return redirect(url_for("user.exchanges"))


@bp.route("/report/<target_type>/<int:target_id>", methods=["POST"])
@login_required
def report(target_type, target_id):
    if target_type not in {"user", "skill"}: abort(404)
    reason = request.form.get("reason", "").strip()
    if len(reason) < 10: flash("Please give a brief reason for the report.", "error")
    else:
        db.session.add(Report(reporter_id=current_user.id, target_type=target_type, target_id=target_id, reason=reason[:1000])); admins = User.query.filter_by(role="admin").all()
        for admin in admins: db.session.add(Notification(user_id=admin.id, text=f"New {target_type} report requires review.", link="/admin/reports"))
        db.session.commit(); flash("Report submitted for review.", "success")
    return redirect(request.referrer or url_for("main.home"))


@bp.route("/users/<int:user_id>/block", methods=["POST"])
@login_required
def block_user(user_id):
    if user_id == current_user.id: abort(400)
    existing = Block.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).first()
    if existing: db.session.delete(existing); flash("User unblocked.", "success")
    else: db.session.add(Block(blocker_id=current_user.id, blocked_id=user_id)); flash("User blocked.", "success")
    db.session.commit(); return redirect(request.referrer or url_for("user.profile", user_id=user_id))
