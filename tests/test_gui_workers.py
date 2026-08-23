from __future__ import annotations

import inspect
import os
from pathlib import Path
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

import design_asset_indexer.gui.workers as worker_module
from design_asset_indexer.gui.workers import RunningJob, WorkerOperation, WorkerRequest
from design_asset_indexer.workflow_models import (
    CancellationToken,
    OutputSnapshot,
    PlanItem,
    SignatureExecutionPlan,
    SignatureRule,
    SourceSnapshot,
    WorkflowOptions,
)


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance() or QApplication([])
    yield application


def _wait(job: RunningJob, spy: QSignalSpy, qapp, milliseconds: int = 5000) -> None:
    if spy.count() == 0:
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        job.finished.connect(loop.quit)
        timer.timeout.connect(loop.quit)
        timer.start(milliseconds)
        loop.exec()
        timer.stop()
    assert spy.count() > 0


def _request(operation: WorkerOperation, tmp_path: Path) -> WorkerRequest:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    options = WorkflowOptions(source, tmp_path / "output")
    rule = SignatureRule("OLD", "NEW")
    item = PlanItem("sample.psd", "SKIP_NO_MATCH", 0, "sample.psd")
    plan = SignatureExecutionPlan(
        "b" * 64,
        "2026-08-23T00:00:00Z",
        options,
        rule,
        ("sample.psd",),
        (SourceSnapshot("sample.psd", 1, 1),),
        (OutputSnapshot("sample.psd", False, False, None, None),),
        (item,),
        False,
    )
    return WorkerRequest(
        operation,
        CancellationToken(),
        options=options if operation in (WorkerOperation.INSPECT, WorkerOperation.PLAN) else None,
        rule=rule if operation is WorkerOperation.PLAN else None,
        plan=plan if operation is WorkerOperation.EXECUTE else None,
    )


@pytest.mark.parametrize(
    ("operation", "function_name"),
    (
        (WorkerOperation.INSPECT, "inspect_signature_workflow"),
        (WorkerOperation.PLAN, "plan_signature_workflow"),
        (WorkerOperation.EXECUTE, "execute_signature_plan"),
    ),
)
def test_every_workflow_phase_owns_com_and_adapter_in_one_qthread(
    qapp, tmp_path, monkeypatch, operation, function_name
):
    log: list[tuple[str, int]] = []
    main_thread = threading.get_ident()

    class Runtime:
        def CoInitialize(self):
            log.append(("coinitialize", threading.get_ident()))

        def CoUninitialize(self):
            log.append(("couninitialize", threading.get_ident()))

    class Adapter:
        def __del__(self):
            log.append(("adapter_discarded", threading.get_ident()))

    def adapter_factory():
        log.append(("adapter_created", threading.get_ident()))
        return Adapter()

    marker = object()

    def operation_stub(*args, **kwargs):
        log.append(("workflow_call", threading.get_ident()))
        return marker

    monkeypatch.setattr(worker_module, function_name, operation_stub)
    job = RunningJob(
        _request(operation, tmp_path),
        adapter_factory=adapter_factory,
        com_runtime_factory=Runtime,
    )
    completed = QSignalSpy(job.completed)
    failed = QSignalSpy(job.failed)
    finished = QSignalSpy(job.finished)
    job.start()
    _wait(job, finished, qapp)
    assert job.wait()
    assert completed.count() == 1
    assert failed.count() == 0
    assert finished.count() == 1
    names = [name for name, _ in log]
    assert names == [
        "coinitialize",
        "adapter_created",
        "workflow_call",
        "adapter_discarded",
        "couninitialize",
    ]
    thread_ids = {thread_id for _, thread_id in log}
    assert len(thread_ids) == 1
    assert main_thread not in thread_ids


def test_environment_check_uses_same_worker_thread(qapp, tmp_path):
    log: list[tuple[str, int]] = []

    class Runtime:
        def CoInitialize(self):
            log.append(("init", threading.get_ident()))

        def CoUninitialize(self):
            log.append(("uninit", threading.get_ident()))

    class Adapter:
        def is_available(self):
            log.append(("available", threading.get_ident()))
            return True

        @property
        def version(self):
            log.append(("version", threading.get_ident()))
            return "SYNTHETIC"

    job = RunningJob(
        _request(WorkerOperation.ENVIRONMENT, tmp_path),
        adapter_factory=Adapter,
        com_runtime_factory=Runtime,
    )
    ready = QSignalSpy(job.environment_ready)
    failed = QSignalSpy(job.failed)
    finished = QSignalSpy(job.finished)
    job.start()
    _wait(job, finished, qapp)
    assert ready.count() == 1
    assert failed.count() == 0
    assert finished.count() == 1
    assert len({thread_id for _, thread_id in log}) == 1
    assert [name for name, _ in log] == ["init", "available", "version", "uninit"]


def test_worker_failure_message_does_not_leak_arbitrary_exception_text(qapp, tmp_path):
    class Runtime:
        def CoInitialize(self):
            pass

        def CoUninitialize(self):
            pass

    class Adapter:
        def is_available(self):
            raise ValueError(r"D:\private\secret.psd OLD_SIGNATURE")

    job = RunningJob(
        _request(WorkerOperation.ENVIRONMENT, tmp_path),
        adapter_factory=Adapter,
        com_runtime_factory=Runtime,
    )
    failed = QSignalSpy(job.failed)
    finished = QSignalSpy(job.finished)
    job.start()
    _wait(job, finished, qapp)
    assert failed.count() == 1
    payload = " ".join(str(value) for value in failed.at(0))
    assert "private" not in payload
    assert "OLD_SIGNATURE" not in payload


def test_cancel_is_cooperative_and_never_uses_qthread_terminate(
    qapp, tmp_path, monkeypatch
):
    request = _request(WorkerOperation.INSPECT, tmp_path)

    def cancellable(*args, **kwargs):
        token = kwargs["cancellation_token"]
        deadline = time.monotonic() + 2
        while not token.cancelled and time.monotonic() < deadline:
            time.sleep(0.005)
        return object()

    monkeypatch.setattr(worker_module, "inspect_signature_workflow", cancellable)
    job = RunningJob(request, adapter_factory=object)
    finished = QSignalSpy(job.finished)
    job.start()
    job.cancel()
    _wait(job, finished, qapp)
    assert request.cancellation_token.cancelled
    assert ".terminate(" not in inspect.getsource(worker_module)


def test_cleanup_failure_replaces_success_with_one_failed(qapp, tmp_path, monkeypatch):
    class Runtime:
        def CoInitialize(self):
            pass

        def CoUninitialize(self):
            raise RuntimeError(r"D:\private\cleanup-detail")

    monkeypatch.setattr(worker_module, "inspect_signature_workflow", lambda *a, **k: object())
    job = RunningJob(
        _request(WorkerOperation.INSPECT, tmp_path),
        adapter_factory=object,
        com_runtime_factory=Runtime,
    )
    completed = QSignalSpy(job.completed)
    failed = QSignalSpy(job.failed)
    finished = QSignalSpy(job.finished)
    job.start()
    _wait(job, finished, qapp)
    assert completed.count() == 0
    assert failed.count() == 1
    assert finished.count() == 1
    payload = " ".join(str(value) for value in failed.at(0))
    assert "COM_CLEANUP_FAILED" in payload
    assert "private" not in payload


def test_operation_and_cleanup_failure_emit_one_redacted_failed(
    qapp, tmp_path, monkeypatch
):
    class Runtime:
        def CoInitialize(self):
            pass

        def CoUninitialize(self):
            raise RuntimeError("cleanup secret")

    def fail_operation(*args, **kwargs):
        raise ValueError(r"D:\private\source.psd OLD_SIGNATURE")

    monkeypatch.setattr(worker_module, "inspect_signature_workflow", fail_operation)
    job = RunningJob(
        _request(WorkerOperation.INSPECT, tmp_path),
        adapter_factory=object,
        com_runtime_factory=Runtime,
    )
    completed = QSignalSpy(job.completed)
    failed = QSignalSpy(job.failed)
    finished = QSignalSpy(job.finished)
    job.start()
    _wait(job, finished, qapp)
    assert completed.count() == 0
    assert failed.count() == 1
    assert finished.count() == 1
    payload = " ".join(str(value) for value in failed.at(0))
    assert "VALUEERROR_COM_CLEANUP_FAILED" in payload
    assert "private" not in payload
    assert "OLD_SIGNATURE" not in payload


def test_environment_cleanup_failure_never_emits_available_success(qapp, tmp_path):
    class Runtime:
        def CoInitialize(self):
            pass

        def CoUninitialize(self):
            raise RuntimeError("cleanup failed")

    class Adapter:
        def is_available(self):
            return True

        @property
        def version(self):
            return "SYNTHETIC"

    job = RunningJob(
        _request(WorkerOperation.ENVIRONMENT, tmp_path),
        adapter_factory=Adapter,
        com_runtime_factory=Runtime,
    )
    ready = QSignalSpy(job.environment_ready)
    failed = QSignalSpy(job.failed)
    finished = QSignalSpy(job.finished)
    job.start()
    _wait(job, finished, qapp)
    assert ready.count() == 0
    assert failed.count() == 1
    assert finished.count() == 1


def test_worker_has_no_global_gc_collect_dependency():
    source = inspect.getsource(worker_module)
    assert "gc.collect" not in source
    assert "import gc" not in source
