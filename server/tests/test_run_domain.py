from __future__ import annotations

from datetime import timedelta

import pytest

from server.domain.shared.errors import Conflict, ValidationFailure
from server.domain.runs import (
    BudgetLedger,
    CostStatus,
    ModelCall,
    Run,
    RunStatus,
    Stage,
    ensure_transition,
    utcnow,
)


def make_run(**overrides: object) -> Run:
    values: dict[str, object] = {
        "id": "run-1",
        "project_id": "p-1",
        "kind": "generate",
        "status": RunStatus.QUEUED,
        "stage": Stage.PLAN,
        "input_hash": "a" * 64,
    }
    values.update(overrides)
    return Run(**values)  # type: ignore[arg-type]


def test_terminal_states_never_move() -> None:
    for terminal in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
        for target in RunStatus:
            with pytest.raises(Conflict):
                ensure_transition(terminal, target)
    ensure_transition(RunStatus.QUEUED, RunStatus.RUNNING)
    ensure_transition(RunStatus.RUNNING, RunStatus.WAITING_INPUT)
    ensure_transition(RunStatus.WAITING_INPUT, RunStatus.QUEUED)
    ensure_transition(RunStatus.RUNNING, RunStatus.RUNNING)


def test_cancel_after_success_is_rejected_but_cancel_twice_is_idempotent() -> None:
    run = make_run(status=RunStatus.RUNNING)
    run.transition(RunStatus.SUCCEEDED)
    with pytest.raises(Conflict) as error:
        run.transition(RunStatus.CANCELLED)
    assert error.value.code == "INVALID_RUN_TRANSITION"
    other = make_run()
    other.transition(RunStatus.CANCELLED)
    assert other.status is RunStatus.CANCELLED
    assert other.finished_at is not None


def test_lease_takeover_increments_token_and_rejects_stale_writer() -> None:
    run = make_run(status=RunStatus.RUNNING)
    first = run.grant_lease("worker-a", lease_seconds=30)
    assert first == 1
    second = run.grant_lease("worker-b", lease_seconds=30)
    assert second == 2
    with pytest.raises(Conflict) as error:
        run.require_active_writer(first, "worker-a")
    assert error.value.code == "STALE_FENCING_TOKEN"
    run.require_active_writer(second, "worker-b")


def test_expired_lease_blocks_submission() -> None:
    run = make_run(status=RunStatus.RUNNING)
    token = run.grant_lease("worker-a", lease_seconds=30)
    future = utcnow() + timedelta(seconds=31)
    with pytest.raises(Conflict):
        run.require_active_writer(token, "worker-a", now=future)


def test_cancelled_run_rejects_late_writer_even_with_current_token() -> None:
    run = make_run(status=RunStatus.RUNNING)
    token = run.grant_lease("worker-a")
    run.transition(RunStatus.CANCELLED)
    with pytest.raises(Conflict) as error:
        run.require_active_writer(token, "worker-a")
    assert error.value.code == "RUN_TERMINAL"


def test_budget_reservation_is_shared_and_bounded_at_twelve() -> None:
    ledger = BudgetLedger()
    ledger.reserve_call(11)
    with pytest.raises(Conflict) as error:
        ledger.reserve_call(2)
    assert error.value.code == "BUDGET_EXHAUSTED"
    ledger.settle_call(11)
    assert ledger.calls_in_flight == 0
    assert ledger.calls_settled == 11
    # Settled calls still count against the run-wide ceiling.
    ledger.reserve_call(1)
    assert ledger.calls_available == 0
    with pytest.raises(Conflict):
        ledger.reserve_call(1)


def test_budget_release_and_invalid_settlement() -> None:
    ledger = BudgetLedger()
    ledger.reserve_call(2)
    ledger.release_call(1)
    assert ledger.calls_reserved == 1
    with pytest.raises(ValidationFailure):
        ledger.settle_call(2)
    with pytest.raises(ValidationFailure):
        ledger.reserve_call(0)


def test_repair_rounds_stop_at_two() -> None:
    ledger = BudgetLedger()
    ledger.begin_repair_round()
    ledger.begin_repair_round()
    with pytest.raises(Conflict) as error:
        ledger.begin_repair_round()
    assert error.value.code == "REPAIR_LIMIT_REACHED"


def test_unknown_cost_cannot_be_recorded_as_zero() -> None:
    with pytest.raises(ValidationFailure):
        ModelCall(
            id="c1",
            run_id="r1",
            agent_task_id=None,
            provider="gateway",
            model="m",
            provider_request_id=None,
            attempt=1,
            status="failed",
            input_tokens=None,
            output_tokens=None,
            currency=None,
            cost_micros=0,
            cost_status=CostStatus.UNKNOWN,
            started_at=None,
            finished_at=None,
        )
    with pytest.raises(ValidationFailure):
        ModelCall(
            id="c2",
            run_id="r1",
            agent_task_id=None,
            provider="gateway",
            model="m",
            provider_request_id=None,
            attempt=1,
            status="succeeded",
            input_tokens=10,
            output_tokens=10,
            currency="CNY",
            cost_micros=None,
            cost_status=CostStatus.ACTUAL,
            started_at=None,
            finished_at=None,
        )
