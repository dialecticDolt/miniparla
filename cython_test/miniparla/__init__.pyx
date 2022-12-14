import miniparla.runtime as task_runtime

class Parla:

    def __init__(self, scheduler_class=task_runtime.Scheduler, **kwds):
        assert issubclass(scheduler_class, task_runtime.Scheduler)
        self.scheduler_class = scheduler_class
        self.kwds = kwds

    def __enter__(self):
        #print("HERE")
        if hasattr(self, "_sched"):
            raise ValueError("Do not use the same Parla object more than once.")
        self._sched = self.scheduler_class(**self.kwds)
        return self._sched.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return self._sched.__exit__(exc_type, exc_val, exc_tb)
        finally:
            del self._sched
