"""Guards for the M1 code-generation system prompt."""
import re

from model1_rag_generator.backend.app.generator import SYSTEM

# ScriptedLLMProvider routes on substrings of the system prompt; the code-generation prompt must never contain them
SCRIPTED_ROUTING_WORDS = ("spec author", "workflowspec author", "repair", "counterexample", "test_properties", "hypothesis")


def test_prompt_keeps_output_contract():
    assert '{"app_code": "...", "test_code": "..."}' in SYSTEM
    assert "GET /health" in SYSTEM


def test_prompt_requires_pydantic_v2_syntax():
    text = SYSTEM.lower()
    assert "pydantic v2" in text
    assert "pattern=" in SYSTEM and "never regex=" in SYSTEM
    for v2_api in ("model_dump", "model_validate", "field_validator", "model_validator", "ConfigDict"):
        assert v2_api in SYSTEM
    for v1_api in (".dict()", ".parse_obj()", "@validator", "@root_validator", "class Config"):
        assert re.search(rf"never .*{re.escape(v1_api)}", SYSTEM), v1_api


def test_prompt_requires_declared_route_parameters():
    for kind in ("path parameter", "query parameter", "header or cookie", "request body"):
        assert kind in SYSTEM
    assert "never use a dict, list, or model type as a query parameter" in SYSTEM.lower().replace("\n", " ")


def test_prompt_avoids_scripted_llm_routing_words():
    lowered = SYSTEM.lower()
    assert not [w for w in SCRIPTED_ROUTING_WORDS if w in lowered]


def test_prompt_requires_strict_request_validation():
    flat = " ".join(SYSTEM.split())
    assert 'extra="forbid"' in flat and "ConfigDict" in flat
    assert "value.strip()" in flat and "@field_validator" in flat
    assert "exact field and key names" in flat and "Never rename, abbreviate" in flat


def test_prompt_requires_independent_tests():
    flat = " ".join(SYSTEM.split())
    assert "Test independence" in flat
    assert "autouse pytest fixture" in flat and "unique data" in flat
    assert "never reuse a unique-constrained value across tests" in flat.lower()


def test_identity_header_rule_names_the_exact_header():
    """Smoke run Sep 26: qwen wrote `actor_id: Optional[str] = Header(None)`, which reads header "actor-id", so every
    call looked anonymous (403)."""
    from model1_rag_generator.backend.app.generator import SYSTEM

    assert 'alias="x-actor-id"' in SYSTEM and "list" in SYSTEM


def test_validators_must_return_the_value():
    """Smoke runs Sep 26: qwen's profile validators returned None, so every created profile crashed with 500."""
    from model1_rag_generator.backend.app.generator import SYSTEM
    from svaga_platform.app.spec_first.author import synth_system

    assert "return value" in SYSTEM and "return value" in synth_system()
