from miniparla.runtime import TaskID, Resources, get_scheduler_context, task_locals, WorkerThread, _task_callback
import inspect

def _make_cell(val):
    """
    Create a new Python closure cell object.

    You should not be using this. I shouldn't be either, but I don't know a way around Python's broken semantics.
    """
    x = val

    def closure():
        return x

    return closure.__closure__[0]


def spawn(taskid=None, vcus=1):

    if not taskid:
        taskid = TaskID("global_" + str(len(task_locals.global_tasks)),
                        (len(task_locals.global_tasks),))

        task_locals.global_tasks += [taskid]

    def decorator(body):
        nonlocal vcus
        req = Resources(vcus)

        if inspect.iscoroutine(body):
            separated_body = body
        else:
            separated_body = type(body)(
                body.__code__, body.__globals__, body.__name__, body.__defaults__,
                closure=body.__closure__ and tuple(_make_cell(x.cell_contents) for x in body.__closure__))
            separated_body.__annotations__ = body.__annotations__
            separated_body.__doc__ = body.__doc__
            separated_body.__kwdefaults__ = body.__kwdefaults__
            separated_body.__module__ = body.__module__

        scheduler = get_scheduler_context()

        if isinstance(scheduler, WorkerThread):
            scheduler = scheduler.scheduler

        task = scheduler.spawn_task(function=_task_callback, args=(separated_body,), dependencies=[], taskid=taskid, req=req, name=getattr(body, "___name__", None))


        scheduler.start_scheduler_callbacks()

        return task

    return decorator

