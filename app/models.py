from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from .extensions import db


def now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(180), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)
    bio = db.Column(db.Text, default="")
    location = db.Column(db.String(120), default="")
    availability = db.Column(db.String(120), default="Flexible")
    avatar = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), default=now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)


class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    title = db.Column(db.String(140), nullable=False, index=True)
    offered = db.Column(db.String(140), nullable=False)
    wanted = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    experience = db.Column(db.String(40), default="Intermediate")
    availability = db.Column(db.String(100), default="Weekends")
    location = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default="active", index=True)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    owner = db.relationship("User", backref="skills")
    category = db.relationship("Category", backref="skills")


class SavedSkill(db.Model):
    __table_args__ = (db.UniqueConstraint("user_id", "skill_id"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skill.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    skill = db.relationship("Skill")


class RecentlyViewed(db.Model):
    __table_args__ = (db.UniqueConstraint("user_id", "skill_id"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skill.id", ondelete="CASCADE"), nullable=False)
    viewed_at = db.Column(db.DateTime(timezone=True), default=now)
    skill = db.relationship("Skill")


class ExchangeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skill.id"), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    offered_skill = db.Column(db.String(140), nullable=False)
    message = db.Column(db.Text, default="")
    status = db.Column(db.String(30), default="pending", index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    completed_at = db.Column(db.DateTime(timezone=True))
    skill = db.relationship("Skill")
    requester = db.relationship("User", foreign_keys=[requester_id])
    provider = db.relationship("User", foreign_keys=[provider_id])


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exchange_id = db.Column(db.Integer, db.ForeignKey("exchange_request.id"), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    exchange = db.relationship("ExchangeRequest", backref=db.backref("conversation", uselist=False))


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    read_at = db.Column(db.DateTime(timezone=True))
    sender = db.relationship("User")
    conversation = db.relationship("Conversation", backref=db.backref("messages", order_by="Message.created_at", cascade="all, delete-orphan"))
    attachments = db.relationship("Attachment", backref="message", cascade="all, delete-orphan")


class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("message.id", ondelete="CASCADE"), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    size = db.Column(db.Integer, nullable=False)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    text = db.Column(db.String(240), nullable=False)
    link = db.Column(db.String(240), default="/")
    read_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=now)


class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exchange_id = db.Column(db.Integer, db.ForeignKey("exchange_request.id"), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, default=60)
    notes = db.Column(db.Text, default="")
    status = db.Column(db.String(30), default="upcoming")
    exchange = db.relationship("ExchangeRequest")


class Review(db.Model):
    __table_args__ = (db.UniqueConstraint("exchange_id", "reviewer_id"),)
    id = db.Column(db.Integer, primary_key=True)
    exchange_id = db.Column(db.Integer, db.ForeignKey("exchange_request.id"), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reviewed_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    stars = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
    reviewed_user = db.relationship("User", foreign_keys=[reviewed_user_id])


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    target_type = db.Column(db.String(30), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default="open")
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    reporter = db.relationship("User")


class Block(db.Model):
    __table_args__ = (db.UniqueConstraint("blocker_id", "blocked_id"),)
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now)


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    event = db.Column(db.String(80), nullable=False, index=True)
    detail = db.Column(db.String(240), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    user = db.relationship("User")


class PlatformSetting(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(500), nullable=False)
