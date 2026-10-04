from datetime import datetime, timezone
from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import case, func, or_
from ..extensions import db
from ..models import Category, ExchangeRequest, RecentlyViewed, Review, Skill, User

bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    featured = Skill.query.filter_by(status="active").filter(Skill.expires_at > datetime.now(timezone.utc)).order_by(Skill.views.desc()).limit(6).all()
    stats = {"members": User.query.filter_by(role="user", status="active").count(), "skills": Skill.query.filter_by(status="active").count(), "exchanges": ExchangeRequest.query.filter(ExchangeRequest.status.in_(["accepted", "in_progress", "completed"])).count()}
    categories = db.session.query(Category, func.count(Skill.id).label("count")).outerjoin(Skill).filter(Category.enabled.is_(True)).group_by(Category.id).order_by(func.count(Skill.id).desc()).limit(6).all()
    return render_template("home.html", featured=featured, stats=stats, categories=categories)


@bp.route("/explore")
def explore():
    query = Skill.query.join(User).join(Category).filter(Skill.status == "active", Skill.expires_at > datetime.now(timezone.utc), User.status == "active")
    q = request.args.get("q", "").strip()
    category = request.args.get("category", type=int)
    experience = request.args.get("experience", "")
    availability = request.args.get("availability", "")
    location = request.args.get("location", "").strip()
    if q:
        term = f"%{q}%"
        query = query.filter(or_(Skill.title.ilike(term), Skill.offered.ilike(term), Skill.wanted.ilike(term), Skill.description.ilike(term)))
    if category:
        query = query.filter(Skill.category_id == category)
    if experience:
        query = query.filter(Skill.experience == experience)
    if availability:
        query = query.filter(Skill.availability == availability)
    if location:
        query = query.filter(Skill.location.ilike(f"%{location}%"))
    sort = request.args.get("sort", "newest")
    orders = {"popular": Skill.views.desc(), "expiring": Skill.expires_at.asc(), "oldest": Skill.created_at.asc()}
    page = query.order_by(orders.get(sort, Skill.created_at.desc())).paginate(page=request.args.get("page", 1, type=int), per_page=9, error_out=False)
    return render_template("skills/explore.html", page=page, categories=Category.query.filter_by(enabled=True).order_by(Category.name).all())


@bp.route("/skills/<int:skill_id>")
def skill_detail(skill_id):
    skill = db.get_or_404(Skill, skill_id)
    if skill.status not in {"active", "paused"} and (not current_user.is_authenticated or current_user.role != "admin"):
        abort(404)
    skill.views += 1
    if current_user.is_authenticated and current_user.id != skill.owner_id:
        recent = RecentlyViewed.query.filter_by(user_id=current_user.id, skill_id=skill.id).first()
        if recent:
            recent.viewed_at = datetime.now(timezone.utc)
        else:
            db.session.add(RecentlyViewed(user_id=current_user.id, skill_id=skill.id))
    db.session.commit()
    rating = db.session.query(func.avg(Review.stars), func.count(Review.id)).filter(Review.reviewed_user_id == skill.owner_id).first()
    related = Skill.query.filter(Skill.category_id == skill.category_id, Skill.id != skill.id, Skill.status == "active").limit(3).all()
    return render_template("skills/detail.html", skill=skill, rating=rating, related=related)


@bp.route("/api/autocomplete")
def autocomplete():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    values = db.session.query(Skill.title).filter(Skill.status == "active", Skill.title.ilike(f"%{q}%")).distinct().limit(8).all()
    return jsonify([v[0] for v in values])


@bp.route("/about")
def about(): return render_template("info.html", page="about")

@bp.route("/how-it-works")
def how_it_works(): return render_template("info.html", page="how")

@bp.route("/privacy")
def privacy(): return render_template("info.html", page="privacy")

@bp.route("/guidelines")
def guidelines(): return render_template("info.html", page="guidelines")

