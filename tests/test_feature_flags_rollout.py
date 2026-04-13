from __future__ import annotations

from ogp_web.services.feature_flags import Cohort, EnforcementMode, FeatureFlagService, RolloutContext, RolloutMode


def _reset(monkeypatch):
    for key in list(__import__('os').environ):
        if key.startswith('OGP_FEATURE_FLAG_') or key in {
            'OGP_INTERNAL_USERNAMES',
            'OGP_BETA_USERNAMES',
            'OGP_INTERNAL_SERVER_IDS',
            'OGP_BETA_SERVER_IDS',
            'OGP_FEATURE_FLAGS_JSON',
        }:
            monkeypatch.delenv(key, raising=False)


def test_flag_off_keeps_legacy_flow(monkeypatch):
    _reset(monkeypatch)
    service = FeatureFlagService()
    decision = service.evaluate(flag='cases_v1', context=RolloutContext(username='user1', server_id='blackberry'))
    assert decision.mode == RolloutMode.OFF
    assert decision.use_new_flow is False


def test_internal_rollout_allows_only_internal_user(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv('OGP_FEATURE_FLAG_CASES_V1_MODE', 'internal')
    monkeypatch.setenv('OGP_FEATURE_FLAG_CASES_V1_INTERNAL_USERS', 'alice')
    service = FeatureFlagService()

    internal = service.evaluate(flag='cases_v1', context=RolloutContext(username='alice', server_id='s1'))
    default = service.evaluate(flag='cases_v1', context=RolloutContext(username='bob', server_id='s1'))

    assert internal.cohort == Cohort.INTERNAL
    assert internal.use_new_flow is True
    assert default.cohort == Cohort.DEFAULT
    assert default.use_new_flow is False


def test_beta_rollout_allows_beta_and_internal(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv('OGP_FEATURE_FLAG_DOCUMENTS_V2_MODE', 'beta')
    monkeypatch.setenv('OGP_FEATURE_FLAG_DOCUMENTS_V2_BETA_USERS', 'beta_user')
    monkeypatch.setenv('OGP_FEATURE_FLAG_DOCUMENTS_V2_INTERNAL_USERS', 'staff_user')
    service = FeatureFlagService()

    beta = service.evaluate(flag='documents_v2', context=RolloutContext(username='beta_user', server_id='s1'))
    staff = service.evaluate(flag='documents_v2', context=RolloutContext(username='staff_user', server_id='s1'))
    default = service.evaluate(flag='documents_v2', context=RolloutContext(username='other', server_id='s1'))

    assert beta.use_new_flow is True
    assert staff.use_new_flow is True
    assert default.use_new_flow is False


def test_all_rollout_enables_for_everyone(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv('OGP_FEATURE_FLAG_ASYNC_JOBS_V1_MODE', 'all')
    service = FeatureFlagService()
    decision = service.evaluate(flag='async_jobs_v1', context=RolloutContext(username='u1', server_id='s1'))
    assert decision.use_new_flow is True


def test_enforcement_default_warn_for_policy_flags(monkeypatch):
    _reset(monkeypatch)
    service = FeatureFlagService()
    citations = service.evaluate(flag='citations_required', context=RolloutContext(username='u1', server_id='s1'))
    validation = service.evaluate(flag='validation_gate_v1', context=RolloutContext(username='u1', server_id='s1'))
    assert citations.enforcement == EnforcementMode.WARN
    assert validation.enforcement == EnforcementMode.WARN
