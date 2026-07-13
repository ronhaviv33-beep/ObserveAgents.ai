from observeagents.privacy import error_type_only, scrub_metadata


def test_forbidden_keys_dropped():
    scrubbed = scrub_metadata({
        "prompt": "SECRET", "response_text": "SECRET", "api_key": "SECRET",
        "authorization": "SECRET", "request_headers": "SECRET", "tool_arguments": "SECRET",
        "region": "us-east-1", "retries": 2, "cached": True,
    })
    assert scrubbed == {"region": "us-east-1", "retries": 2, "cached": True}


def test_url_values_dropped():
    scrubbed = scrub_metadata({"link": "https://a.com/b?token=x", "n": 1})
    assert scrubbed == {"n": 1}


def test_nested_structures_dropped():
    scrubbed = scrub_metadata({"nested": {"prompt": "x"}, "items": [1, 2], "ok": "y"})
    assert scrubbed == {"ok": "y"}


def test_non_dict_returns_empty():
    assert scrub_metadata(None) == {}
    assert scrub_metadata("nope") == {}


def test_error_type_only_uses_class_name():
    class RateLimitError(Exception):
        pass

    assert error_type_only(RateLimitError("secret prompt text in message")) == "RateLimitError"
