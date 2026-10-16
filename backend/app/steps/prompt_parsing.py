"""Turn `claude -p --output-format json` output into {prompt, summary}."""

import json


class PromptParseError(ValueError):
    pass


def extract_json_object(text: str) -> dict:
    """Find the first balanced {...} that parses as JSON (tolerates fences and chatter)."""
    start = text.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:index + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(value, dict):
                        return value
                    break
        start = text.find("{", start + 1)
    raise PromptParseError("không tìm thấy JSON trong câu trả lời")


def result_envelope(stdout: str) -> dict:
    """The final `result` object of `--output-format json` (one object) or `stream-json` (JSON lines)."""
    envelope = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            envelope = obj
    if envelope is None:
        raise PromptParseError("đầu ra của claude không có kết quả (type=result)")
    return envelope


def parse_claude_output(stdout: str) -> dict[str, str]:
    envelope = result_envelope(stdout)
    if envelope.get("is_error"):
        raise PromptParseError(f"claude báo lỗi: {str(envelope.get('result'))[:300]}")
    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        raise PromptParseError("claude trả về kết quả rỗng")
    data = extract_json_object(result)
    prompt, summary = data.get("prompt"), data.get("summary")
    if not isinstance(prompt, str) or not prompt.strip():
        raise PromptParseError("thiếu trường 'prompt'")
    if not isinstance(summary, str):
        summary = ""
    product_type = data.get("product_type")
    product_type = " ".join(product_type.split()).lower() if isinstance(product_type, str) else ""
    return {"prompt": prompt.strip(), "summary": summary.strip(), "product_type": product_type}
