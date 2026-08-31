from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from pydantic import ValidationError

from backend.services.candidate_passport_v1 import (
    CandidateInput,
    CandidatePipelineError,
    ConfirmationAction,
    CONFIRMATION_AUDIENCE,
    ReviewerCredential,
    apply_human_action,
    build_candidate,
    run_batch,
    semantic_sha256,
)
from backend.auth.jwt import ALGORITHM, SECRET_KEY
from backend.validation.synthetic_factory import generate_scenario


def fixture(variant="complete", seed=1001):
    return generate_scenario(seed=seed, split="candidate", variant=variant)


def candidate_input(source=None):
    source = source or fixture()
    return CandidateInput(scenario_id=source.scenario_id, documents=tuple(source.documents))


def action(decision="confirm"):
    return ConfirmationAction(decision=decision, reason="synthetic acceptance fixture", occurred_at=datetime(2026, 8, 14, tzinfo=timezone.utc))


def reviewer(*, actor_id="synthetic-reviewer", role="auditor", audience=CONFIRMATION_AUDIENCE, expires_delta=timedelta(hours=1), secret=SECRET_KEY):
    payload = {
        "sub": actor_id,
        "role": role,
        "aud": audience,
        "type": "passport_confirmation",
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return ReviewerCredential(token=jwt.encode(payload, secret, algorithm=ALGORITHM))


def mutate_documents(source, fn):
    payload = candidate_input(source).model_dump(mode="json")
    fn(payload)
    return CandidateInput.model_validate(payload)


def test_runtime_contract_rejects_truth_and_expected():
    payload = fixture().model_dump(mode="json")
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CandidateInput.model_validate(payload)


def test_mutating_standard_answer_does_not_change_candidate():
    source = fixture()
    before = build_candidate(candidate_input(source))
    payload = source.model_dump(mode="json")
    payload["truth"]["production_output_t"] = "1"
    payload["expected"]["fields"]["production_output"]["value"] = "1"
    from backend.validation.contracts import SyntheticFactoryScenario
    tampered = SyntheticFactoryScenario.model_validate(payload)
    after = build_candidate(candidate_input(tampered))
    assert before.candidate == after.candidate
    assert after.candidate["fields"]["production_output"]["value"] == "2144.05"


def test_candidate_never_writes_or_publishes_before_confirmation():
    passport = build_candidate(candidate_input())
    assert passport.state == "candidate"
    assert passport.formal_write_allowed is False
    assert passport.publish_allowed is False
    assert passport.provenance["truth_isolated"] is True


def test_authenticated_confirmation_calculates_but_stays_unpublished():
    passport = apply_human_action(build_candidate(candidate_input()), action(), reviewer())
    assert passport.state == "calculated"
    assert passport.confirmation["authentication"] == "signed_confirmation_credential"
    assert passport.calculation_receipt["result"]["unit"] == "tCO2e"
    assert passport.publish_allowed is False


def test_caller_cannot_self_assert_human_identity():
    passport = build_candidate(candidate_input())
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ConfirmationAction(actor_id="fake", actor_type="human", decision="confirm", reason="fake", occurred_at=datetime.now(timezone.utc))
    with pytest.raises(CandidatePipelineError, match="reviewer_credential_required"):
        apply_human_action(passport, action(), object())


def test_confirmation_requires_token():
    with pytest.raises(ValidationError, match="string_too_short"):
        ReviewerCredential(token="")


def test_confirmation_rejects_forged_signature():
    with pytest.raises(CandidatePipelineError, match="reviewer_credential_invalid"):
        apply_human_action(build_candidate(candidate_input()), action(), reviewer(secret="attacker-controlled-secret"))


def test_confirmation_rejects_wrong_audience():
    with pytest.raises(CandidatePipelineError, match="reviewer_credential_invalid"):
        apply_human_action(build_candidate(candidate_input()), action(), reviewer(audience="another-service"))


def test_confirmation_rejects_expired_identity():
    with pytest.raises(CandidatePipelineError, match="reviewer_credential_invalid"):
        apply_human_action(build_candidate(candidate_input()), action(), reviewer(expires_delta=timedelta(seconds=-1)))


def test_confirmation_rejects_unauthorized_role():
    with pytest.raises(CandidatePipelineError, match="reviewer_not_authorized"):
        apply_human_action(build_candidate(candidate_input()), action(), reviewer(role="member"))


@pytest.mark.parametrize("variant", ["missing_output", "ambiguous_output_unit", "conflicting_output", "missing_electricity"])
def test_unresolved_candidates_fail_closed(variant):
    with pytest.raises(CandidatePipelineError, match="unresolved_candidates"):
        apply_human_action(build_candidate(candidate_input(fixture(variant))), action(), reviewer())


def test_prompt_injection_cannot_cross_human_boundary():
    passport = build_candidate(candidate_input(fixture("prompt_injection", 3001)))
    with pytest.raises(CandidatePipelineError, match="document_instruction_detected"):
        apply_human_action(passport, action(), reviewer())


def test_field_value_and_unit_are_bound_to_evidence():
    broken_value = mutate_documents(fixture(), lambda p: p["documents"][2].update(content="文件类型：报告期合格产量台账\n合格产量：1 t"))
    passport = build_candidate(broken_value)
    assert passport.candidate["fields"]["production_output"]["value"] == "1"
    assert passport.candidate["fields"]["production_output"]["evidence"][0]["quote"] == "合格产量：1 t"
    ambiguous = mutate_documents(fixture(), lambda p: p["documents"][2].update(content="文件类型：报告期合格产量台账\n合格产量：2144.05（单位未标明）"))
    with pytest.raises(CandidatePipelineError, match="unresolved_candidates"):
        apply_human_action(build_candidate(ambiguous), action(), reviewer())


def test_unit_and_period_anomalies_fail_closed():
    wrong_unit = mutate_documents(fixture(), lambda p: p["documents"][2].update(content="文件类型：报告期合格产量台账\n合格产量：2144.05 kg"))
    with pytest.raises(CandidatePipelineError, match="unresolved_candidates"):
        apply_human_action(build_candidate(wrong_unit), action(), reviewer())
    def reverse(payload):
        identity = next(item for item in payload["documents"] if item["document_id"] == "identity")
        identity["content"] = identity["content"].replace("期间开始：2026-10-01", "期间开始：2027-01-01")
    with pytest.raises(CandidatePipelineError, match="invalid_period"):
        build_candidate(mutate_documents(fixture(), reverse))


def test_reject_action_is_audited_and_never_calculated():
    passport = apply_human_action(build_candidate(candidate_input()), action("reject"), reviewer())
    assert passport.state == "rejected"
    assert passport.confirmation["actor_id"] == "synthetic-reviewer"
    assert passport.calculation_receipt is None


def test_batch_and_three_replays_are_semantically_identical():
    items = (candidate_input(fixture("complete", 1001)), candidate_input(fixture("missing_output", 1002)))
    actions = {item.scenario_id: (action(), reviewer()) for item in items}
    runs = [run_batch(items, actions) for _ in range(3)]
    assert len({semantic_sha256(run) for run in runs}) == 1
    assert runs[0][0]["classification"] == "PASS"
    assert runs[0][1]["classification"] == "PASS"
    assert runs[0][1]["outcome"] == "expected_rejection"
