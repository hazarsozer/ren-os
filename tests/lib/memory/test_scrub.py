"""
Tests for lib.memory.scrub — G7 secrets-scrub, fail-closed (Task 1.4).

Spec §3.6 item 3: transcripts→wiki→backup is an exfiltration chain unless the
memory-write path scrubs for secrets. This module is standalone (write_apply,
Task 1.2, doesn't exist yet and will import scrub_or_raise once it does).

Run with: uv run pytest tests/lib/memory/test_scrub.py -v
"""

from __future__ import annotations

import re

import pytest

from lib.memory.scrub import PATTERNS, Finding, SecretsFound, scan, scrub_or_raise


# --- clean text ---------------------------------------------------------


def test_scan_clean_text_returns_empty_list():
    assert scan("Just a normal paragraph about the project roadmap.") == []


def test_scrub_or_raise_clean_text_returns_unchanged():
    text = "Nothing sensitive here, just notes on the wiki schema."
    assert scrub_or_raise(text) == text


# --- each pattern kind, correct kind + span ------------------------------


def test_detects_aws_access_key():
    secret = "AKIAIOSFODNN7EXAMPLE"
    text = f"export AWS_ACCESS_KEY_ID={secret}"
    findings = scan(text)
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "aws-access-key"
    start, end = f.span
    assert text[start:end] == secret


def test_detects_github_token_ghp():
    secret = "ghp_" + "a" * 36
    text = f"token: {secret}"
    findings = [f for f in scan(text) if f.kind == "github-token"]
    assert len(findings) == 1
    start, end = findings[0].span
    assert text[start:end] == secret


def test_detects_github_token_gho():
    secret = "gho_" + "b" * 36
    text = f"GITHUB_TOKEN={secret}"
    findings = [f for f in scan(text) if f.kind == "github-token"]
    assert len(findings) == 1


def test_detects_github_pat():
    secret = "github_pat_" + "c" * 25
    text = f"use {secret} to authenticate"
    findings = [f for f in scan(text) if f.kind == "github-token"]
    assert len(findings) == 1
    start, end = findings[0].span
    assert text[start:end] == secret


def test_detects_openai_style_sk_key():
    secret = "sk-" + "x" * 40
    text = f"ANTHROPIC_API_KEY={secret}"
    findings = [f for f in scan(text) if f.kind == "openai-key"]
    assert len(findings) == 1
    start, end = findings[0].span
    assert text[start:end] == secret


def test_detects_pem_private_key_block():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    findings = [f for f in scan(text) if f.kind == "pem-block"]
    assert len(findings) == 1
    start, end = findings[0].span
    assert "BEGIN" in text[start:end]


def test_detects_password_assignment_pair():
    text = 'db_password: "hunter2hunter2"'
    findings = [f for f in scan(text) if f.kind == "password-pair"]
    assert len(findings) == 1


def test_detects_secret_assignment_pair():
    text = "secret=supersecretvalue123"
    findings = [f for f in scan(text) if f.kind == "password-pair"]
    assert len(findings) == 1


def test_detects_token_assignment_pair():
    text = "token = 'abcd1234efgh5678'"
    findings = [f for f in scan(text) if f.kind == "password-pair"]
    assert len(findings) == 1


def test_detects_api_key_assignment_pair():
    text = "api_key: zzz999yyy888"
    findings = [f for f in scan(text) if f.kind == "password-pair"]
    assert len(findings) == 1


def test_detects_slack_token():
    secret = "xoxb-1234567890-abcdefGHIJKL"
    text = f"webhook token {secret} for the bot"
    findings = [f for f in scan(text) if f.kind == "slack-token"]
    assert len(findings) == 1
    start, end = findings[0].span
    assert text[start:end] == secret


# --- redacted_preview never leaks the full secret ------------------------


def test_redacted_preview_is_at_most_four_secret_chars_plus_ellipsis():
    secret = "AKIAIOSFODNN7EXAMPLE"
    text = f"key={secret}"
    findings = scan(text)
    assert len(findings) == 1
    preview = findings[0].redacted_preview
    assert preview.endswith("…")
    revealed = preview[:-1]
    assert len(revealed) <= 4
    assert secret not in preview
    assert revealed == secret[:4]


@pytest.mark.parametrize(
    "text",
    [
        f"AWS_KEY={('AKIA' + 'B' * 16)}",
        f"gh_token={'ghp_' + 'c' * 40}",
        f"anthropic={'sk-' + 'd' * 40}",
    ],
)
def test_redacted_preview_never_contains_full_secret_for_various_kinds(text):
    for finding in scan(text):
        start, end = finding.span
        full_secret = text[start:end]
        assert full_secret not in finding.redacted_preview


# --- multiple findings in one text --------------------------------------


def test_multiple_findings_all_reported():
    aws = "AKIAIOSFODNN7EXAMPLE"
    gh = "ghp_" + "a" * 36
    text = f"aws={aws}\ngithub={gh}\n"
    findings = scan(text)
    kinds = {f.kind for f in findings}
    assert "aws-access-key" in kinds
    assert "github-token" in kinds
    assert len(findings) == 2


# --- SecretsFound exception ----------------------------------------------


def test_scrub_or_raise_raises_secrets_found_on_dirty_text():
    secret = "AKIAIOSFODNN7EXAMPLE"
    with pytest.raises(SecretsFound):
        scrub_or_raise(f"key={secret}")


def test_secrets_found_message_has_kinds_and_counts_not_secret_content():
    aws = "AKIAIOSFODNN7EXAMPLE"
    gh_a = "ghp_" + "a" * 36
    gh_b = "gho_" + "b" * 36
    text = f"{aws}\n{gh_a}\n{gh_b}\n"
    with pytest.raises(SecretsFound) as exc_info:
        scrub_or_raise(text)
    message = str(exc_info.value)
    assert "aws-access-key" in message
    assert "github-token" in message
    assert "(1)" in message  # one aws-access-key
    assert "(2)" in message  # two github-token
    assert aws not in message
    assert gh_a not in message
    assert gh_b not in message


def test_secrets_found_carries_findings_list():
    secret = "AKIAIOSFODNN7EXAMPLE"
    with pytest.raises(SecretsFound) as exc_info:
        scrub_or_raise(f"key={secret}")
    assert isinstance(exc_info.value.findings, list)
    assert all(isinstance(f, Finding) for f in exc_info.value.findings)


# --- false-positive guards ------------------------------------------------


def test_password_word_in_prose_without_assignment_does_not_fire():
    text = "Please enter your password when prompted, then confirm it twice."
    findings = [f for f in scan(text) if f.kind == "password-pair"]
    assert findings == []


def test_secret_word_in_prose_without_assignment_does_not_fire():
    text = "There's no secret to good writing — just revise, revise, revise."
    findings = [f for f in scan(text) if f.kind == "password-pair"]
    assert findings == []


def test_sk_prefix_inside_longer_word_does_not_fire():
    text = "The standing desk-mounted monitor arm needs a new bracket."
    findings = [f for f in scan(text) if f.kind == "openai-key"]
    assert findings == []


def test_ghost_word_does_not_match_github_token_prefix():
    text = "The ghost of a bug from three sessions ago finally got fixed."
    findings = [f for f in scan(text) if f.kind == "github-token"]
    assert findings == []


def test_xoxo_farewell_does_not_match_slack_token():
    text = "signing off — xoxo, the team"
    findings = [f for f in scan(text) if f.kind == "slack-token"]
    assert findings == []


# --- PATTERNS is the shared, importable registry -------------------------


def test_patterns_is_a_list_of_kind_regex_pairs():
    assert isinstance(PATTERNS, list)
    assert len(PATTERNS) > 0
    for kind, pattern in PATTERNS:
        assert isinstance(kind, str)
        assert isinstance(pattern, re.Pattern)
