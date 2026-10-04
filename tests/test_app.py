import io
import pytest
from app import create_app
from app.extensions import db
from app.models import Conversation, ExchangeRequest, Skill, User


@pytest.fixture()
def app(tmp_path):
    application = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "UPLOAD_FOLDER": str(tmp_path)})
    yield application


@pytest.fixture()
def client(app): return app.test_client()


def login(client, email="tarun@localskill.demo", password="User@123"):
    path = "/admin/login" if email == "admin@gmail.com" else "/login"
    return client.post(path, data={"email": email, "password": password}, follow_redirects=True)


def test_public_pages_and_search(client):
    for path in ["/", "/explore", "/explore?q=Python&experience=Beginner+friendly", "/about", "/privacy", "/guidelines", "/how-it-works"]:
        assert client.get(path).status_code == 200
    assert b"Python Tutoring" in client.get("/explore?q=Python").data


def test_registration_login_invalid_and_duplicate(client):
    data = {"name": "New Learner", "email": "new@example.com", "password": "GoodPass123", "location": "Chandigarh"}
    response = client.post("/register", data=data, follow_redirects=True)
    assert response.status_code == 200 and b"Profile" in response.data
    client.post("/logout")
    assert b"already exists" in client.post("/register", data=data, follow_redirects=True).data
    assert b"incorrect" in client.post("/login", data={"email": "new@example.com", "password": "bad"}, follow_redirects=True).data
    assert client.post("/login", data={"email": "new@example.com", "password": "GoodPass123"}, follow_redirects=True).status_code == 200


def test_admin_login_and_role_protection(client):
    assert b"incorrect" in client.post("/admin/login", data={"email": "admin@gmail.com", "password": "wrong"}, follow_redirects=True).data
    assert b"Admin dashboard" in client.post("/admin/login", data={"email": "admin@gmail.com", "password": "admin"}, follow_redirects=True).data
    client.post("/admin/logout")
    login(client)
    assert client.get("/admin/dashboard").status_code == 403


def test_skill_crud_ownership_save_and_filters(client, app):
    login(client)
    with app.app_context(): category_id = Skill.query.first().category_id
    payload = {"title": "Flask mentoring", "offered": "Flask", "wanted": "Photography", "description": "A complete guided Flask learning session.", "category_id": category_id, "experience": "Intermediate", "availability": "Evenings", "location": "Chandigarh"}
    response = client.post("/skills/create", data=payload, follow_redirects=True)
    assert b"Flask mentoring" in response.data
    with app.app_context(): skill = Skill.query.filter_by(title="Flask mentoring").first(); skill_id = skill.id
    assert client.post(f"/skills/{skill_id}/save", follow_redirects=True).status_code == 200
    payload["title"] = "Flask project mentoring"
    assert b"Flask project mentoring" in client.post(f"/skills/{skill_id}/edit", data=payload, follow_redirects=True).data
    client.post("/logout"); login(client, "vishal@localskill.demo")
    assert client.post(f"/skills/{skill_id}/delete").status_code == 403


def test_exchange_chat_attachment_review_rules(client, app):
    login(client, "vishal@localskill.demo")
    with app.app_context(): skill = Skill.query.filter(Skill.owner.has(email="tarun@localskill.demo")).first(); skill_id = skill.id
    client.post(f"/skills/{skill_id}/request", data={"offered_skill": "Design", "message": "Let us exchange skills."})
    client.post("/logout"); login(client)
    with app.app_context(): exchange = ExchangeRequest.query.filter_by(skill_id=skill_id, status="pending").order_by(ExchangeRequest.id.desc()).first(); exchange_id = exchange.id
    client.post(f"/exchanges/{exchange_id}/accept")
    with app.app_context(): conversation_id = Conversation.query.filter_by(exchange_id=exchange_id).first().id
    response = client.post(f"/messages/{conversation_id}", data={"body": "Here is the session plan.", "attachment": (io.BytesIO(b"plan"), "plan.txt")}, content_type="multipart/form-data", follow_redirects=True)
    assert b"session plan" in response.data
    client.post(f"/exchanges/{exchange_id}/start"); client.post(f"/exchanges/{exchange_id}/complete")
    assert client.post(f"/exchanges/{exchange_id}/review", data={"stars": 5, "comment": "Excellent exchange."}).status_code in (302, 200)
    assert client.post(f"/exchanges/{exchange_id}/review", data={"stars": 5, "comment": "Duplicate"}).status_code == 400


def test_suspension_blocks_login(client, app):
    login(client, "admin@gmail.com", "admin")
    with app.app_context(): user_id = User.query.filter_by(email="aman@localskill.demo").first().id
    client.post(f"/admin/users/{user_id}/suspend"); client.post("/admin/logout")
    assert b"suspended" in client.post("/login", data={"email": "aman@localskill.demo", "password": "User@123"}, follow_redirects=True).data
