import time

from app.classes.web.tornado_handler import Webserver


def test_web_loop_heartbeat_marks_the_event_loop_as_responsive():
    webserver = Webserver(None, None, None, None)
    webserver._ioloop_stall_reported = True

    before = time.monotonic()
    webserver._record_ioloop_heartbeat()

    assert webserver._ioloop_heartbeat_at >= before
    assert webserver._ioloop_stall_reported is False
