"""
大模型调用封装层（utils 层，不依赖 Django request）。

只依赖 requests，对接 OpenAI 兼容的 /chat/completions 接口，
适用于 vLLM、Ollama、Xinference、LocalAI、One-API 及各云厂商兼容端点。
"""
import json

import requests


class LLMClientError(Exception):
    """对外暴露的、可直接展示给用户的错误信息。"""


def _headers(config):
    headers = {"Content-Type": "application/json"}
    if getattr(config, "api_key", ""):
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def _extract_http_error(resp):
    """尽量从非 200 响应中提取可读的错误信息。"""
    try:
        body = resp.json()
    except ValueError:
        detail = resp.text.strip()[:300]
    else:
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                detail = err.get("message") or json.dumps(err, ensure_ascii=False)
            elif err:
                detail = str(err)
            else:
                detail = body.get("message") or json.dumps(body, ensure_ascii=False)
        else:
            detail = str(body)
    return f"接口返回 HTTP {resp.status_code}：{detail or '无错误详情'}"


def _redirect_error(resp, base_url):
    """构造重定向场景的可读错误（常见于把本网站地址误填成模型地址）。"""
    location = resp.headers.get("Location", "") or "未知地址"
    hint = ""
    if "login" in location.lower():
        hint = "目标跳转到了登录页，这通常说明 Base URL 填成了本网站自己的地址（本网站也运行在 8000 端口），而不是大模型服务。"
    return LLMClientError(
        f"请求被 {resp.status_code} 重定向到 {location}，请检查 Base URL（当前：{base_url}）。{hint}"
    )


def chat_completions_stream(config, messages, web_search=False, timeout=(10, 120)):
    """调用流式对话接口，逐段 yield 文本增量。

    :param config: ApiConfig 实例（或任意含 base_url/api_key/model/temperature/max_tokens 属性的对象）
    :param messages: OpenAI 格式消息列表 [{"role": ..., "content": ...}]
    :param web_search: 是否启用智谱联网搜索工具（Web Search in Chat）
    """
    url = config.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": config.model,
        "messages": messages,
        "stream": True,
        "temperature": config.temperature,
    }
    if config.max_tokens:
        payload["max_tokens"] = config.max_tokens
    if web_search:
        # 智谱 OpenAI 兼容接口的联网搜索工具：服务端先实时检索再综合回答
        payload["tools"] = [
            {
                "type": "web_search",
                "web_search": {"enable": True, "search_result": True},
            }
        ]

    try:
        # 禁止自动跟随重定向：模型地址误填为本网站时会被 302 到登录页，
        # 跟随跳转只会拿到一段 HTML 并静默产生"空回复"
        resp = requests.post(
            url,
            headers=_headers(config),
            json=payload,
            stream=True,
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise LLMClientError(f"无法连接模型接口（{url}）：{exc}") from exc

    if 300 <= resp.status_code < 400:
        raise _redirect_error(resp, config.base_url)
    if resp.status_code != 200:
        raise LLMClientError(_extract_http_error(resp))

    content_type = resp.headers.get("Content-Type", "")
    if "text/event-stream" not in content_type.lower():
        # 返回的不是 SSE 流（通常是 HTML 网页或 JSON 错误页）
        snippet = ""
        try:
            resp.encoding = "utf-8"
            for piece in resp.iter_content(chunk_size=512, decode_unicode=True):
                snippet = (snippet + (piece or "")).strip()
                if snippet:
                    break
        except requests.RequestException:
            pass
        if "html" in content_type.lower() or snippet.lstrip().lower().startswith("<!"):
            raise LLMClientError(
                "模型接口返回的是网页而不是流式数据。请确认 Base URL 指向的是大模型服务"
                "（如本地 Ollama 的 http://localhost:11434/v1、vLLM 或云厂商接口），"
                "而不是本聊天网站自己的地址。"
            )
        raise LLMClientError(
            f"模型接口返回类型异常（Content-Type: {content_type or '未知'}），不是 SSE 流式响应。"
            f"响应片段：{snippet[:200]}"
        )

    # 部分推理服务（vLLM 等）的 SSE 响应头不带 charset，
    # requests 会回退为 ISO-8859-1 导致中文乱码，这里强制按 UTF-8 解码
    resp.encoding = "utf-8"

    try:
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                return
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            choices = chunk.get("choices") or []
            if not choices:
                if chunk.get("error"):
                    raise LLMClientError(str(chunk["error"]))
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content is None:
                # 兼容个别非标准实现：直接在 message 中返回内容
                content = (choice.get("message") or {}).get("content")
            if content:
                yield content
            if choice.get("finish_reason"):
                return
    except requests.RequestException as exc:
        raise LLMClientError(f"读取模型流式响应失败：{exc}") from exc


def _probe_models_list(config, timeout=(5, 30)):
    """尝试通过 GET /models 验证连通性。返回 None 表示该端点不可用（需降级探测）。"""
    url = config.base_url.rstrip("/") + "/models"
    try:
        resp = requests.get(
            url, headers=_headers(config), timeout=timeout, allow_redirects=False
        )
    except requests.RequestException:
        return None
    if 300 <= resp.status_code < 400:
        raise _redirect_error(resp, config.base_url)
    if resp.status_code in (404, 405):
        return None
    if resp.status_code != 200:
        raise LLMClientError(_extract_http_error(resp))
    try:
        body = resp.json()
    except ValueError:
        raise LLMClientError(
            "/models 返回的不是 JSON（很可能是网页），请确认 Base URL 指向的是大模型服务而不是本网站地址"
        )
    models = body.get("data") if isinstance(body, dict) else None
    if not isinstance(models, list):
        raise LLMClientError(
            "/models 返回结构中缺少 data 列表，请确认该地址是 OpenAI 兼容的模型服务"
        )
    ids = [m.get("id") for m in models if isinstance(m, dict) and m.get("id")]
    shown = ", ".join(ids[:10])
    if len(ids) > 10:
        shown += "……"
    return f"连接成功，服务上可用的模型：{shown or '（模型列表为空）'}"


def _probe_chat(config, timeout=(10, 60)):
    """发送一次最小对话请求验证鉴权与模型可用性。"""
    url = config.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "stream": False,
    }
    try:
        resp = requests.post(
            url,
            headers=_headers(config),
            json=payload,
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise LLMClientError(f"无法连接模型接口（{url}）：{exc}") from exc
    if 300 <= resp.status_code < 400:
        raise _redirect_error(resp, config.base_url)
    if resp.status_code != 200:
        raise LLMClientError(_extract_http_error(resp))
    try:
        body = resp.json()
    except ValueError:
        raise LLMClientError("接口返回的不是 JSON，可能不是 OpenAI 兼容接口或 Base URL 填写有误")
    if not (isinstance(body, dict) and isinstance(body.get("choices"), list)):
        raise LLMClientError(
            "接口返回中缺少 choices 字段，不像标准的对话接口响应："
            + json.dumps(body, ensure_ascii=False)[:200]
        )
    return "连接成功，模型可正常对话"


def test_connection(config):
    """测试配置是否可用，成功返回提示字符串，失败抛出 LLMClientError。"""
    if not getattr(config, "base_url", "") or not getattr(config, "model", ""):
        raise LLMClientError("接口地址和模型名称不能为空")
    result = _probe_models_list(config)
    return result or _probe_chat(config)
