from app.classes.web.public_handler import is_anti_lockout_user


def test_is_anti_lockout_user_handles_anonymous_logout():
    assert not is_anti_lockout_user(None)


def test_is_anti_lockout_user_ignores_normal_user():
    assert not is_anti_lockout_user((None, {}, {"username": "admin"}))


def test_is_anti_lockout_user_detects_anti_lockout_user():
    assert is_anti_lockout_user((None, {}, {"username": "anti-lockout-user"}))
