import pytest,time,threading
from jarvis.core.app import JarvisApp

@pytest.fixture(autouse=True)
def unrelated_monotonic_consumer(monkeypatch):
    original=JarvisApp._on_gesture_event
    def with_unrelated_clock_read(self,*args,**kwargs):
        # Simulate a background scheduler using the standard-library clock.
        worker=threading.Thread(target=time.monotonic)
        worker.start();worker.join()
        return original(self,*args,**kwargs)
    monkeypatch.setattr(JarvisApp,'_on_gesture_event',with_unrelated_clock_read)
