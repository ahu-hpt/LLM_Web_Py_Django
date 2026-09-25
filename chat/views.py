"""
视图层：负责参数校验、错误码映射与 HTTP 协议；
具体的大模型调用逻辑见 chat.llm_client。
"""
import json
from types import SimpleNamespace

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .llm_client import LLMClientError, chat_completions_stream, test_connection
from .models import ApiConfig

MAX_HISTORY_MESSAGES = 40
MAX_CONTENT_LENGTH = 20000
ALLOWED_ROLES = {"user", "assistant"}


@ensure_csrf_cookie
def index(request):
    """对话主页。"""
    return render(request, "chat/index.html", {"config": ApiConfig.get_config()})


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def settings_view(request):
    """API 配置页面（单例保存）。"""
    config = ApiConfig.get_config() or ApiConfig()
    error = ""

    if request.method == "POST":
        base_url = request.POST.get("base_url", "").strip()
        api_key = request.POST.get("api_key", "").strip()
        model = request.POST.get("model", "").strip()
        system_prompt = request.POST.get("system_prompt", "").strip()
        try:
            temperature = float(request.POST.get("temperature", "0.7"))
        except ValueError:
            temperature = 0.7
        max_tokens_raw = request.POST.get("max_tokens", "").strip()
        max_tokens = None
        if max_tokens_raw:
            try:
                max_tokens = int(max_tokens_raw)
            except ValueError:
                max_tokens = None

        if not base_url.startswith(("http://", "https://")):
            error = "接口地址需以 http:// 或 https:// 开头"
        elif not model:
            error = "模型名称不能为空"
        elif not 0 <= temperature <= 2:
            error = "Temperature 取值范围为 0 ~ 2"
        else:
            config.base_url = base_url.rstrip("/")
            config.api_key = api_key
            config.model = model
            config.temperature = temperature
            config.max_tokens = max_tokens
            config.system_prompt = system_prompt
            config.save()
            return redirect("settings")

        # 校验失败时保留用户输入
        config.base_url = base_url
        config.api_key = api_key
        config.model = model
        config.temperature = temperature
        config.max_tokens = max_tokens
        config.system_prompt = system_prompt

    return render(
        request,
        "chat/settings.html",
        {"config": config, "error": error, "saved": request.GET.get("saved") == "1"},
    )


def _build_messages(config, raw_messages):
    """校验并清洗前端发来的消息，拼上系统提示词。"""
    if not isinstance(raw_messages, list):
        raise ValueError("消息格式不正确")

    messages = []
    if config.system_prompt.strip():
        messages.append({"role": "system", "content": config.system_prompt.strip()})

    for item in raw_messages[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ALLOWED_ROLES and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content[:MAX_CONTENT_LENGTH]})

    if not any(m["role"] == "user" for m in messages):
        raise ValueError("请输入有效的用户消息")
    return messages


def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@require_http_methods(["POST"])
def chat_api(request):
    """流式对话接口：请求体 {"messages": [...]}，返回 text/event-stream。"""
    config = ApiConfig.get_config()
    if not config or not config.base_url or not config.model:
        return StreamingHttpResponse(
            _sse({"type": "error", "content": "尚未配置模型接口，请先到「设置」页面填写"}),
            content_type="text/event-stream",
        )

    try:
        body = json.loads(request.body or b"{}")
        messages = _build_messages(config, body.get("messages"))
    except (ValueError, json.JSONDecodeError) as exc:
        return StreamingHttpResponse(
            _sse({"type": "error", "content": f"请求参数有误：{exc}"}),
            content_type="text/event-stream",
        )

    web_search = bool(body.get("web_search"))

    def event_stream():
        try:
            for chunk in chat_completions_stream(
                config, messages, web_search=web_search
            ):
                yield _sse({"type": "delta", "content": chunk})
            yield _sse({"type": "done"})
        except LLMClientError as exc:
            yield _sse({"type": "error", "content": str(exc)})

    response = StreamingHttpResponse(
        event_stream(), content_type="text/event-stream; charset=utf-8"
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_http_methods(["POST"])
def test_api(request):
    """使用页面上当前填写（未必已保存）的配置测试连通性。"""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "请求体不是合法 JSON"})

    probe = SimpleNamespace(
        base_url=(body.get("base_url") or "").strip().rstrip("/"),
        api_key=(body.get("api_key") or "").strip(),
        model=(body.get("model") or "").strip(),
        temperature=0.7,
        max_tokens=1,
    )
    try:
        message = test_connection(probe)
    except LLMClientError as exc:
        return JsonResponse({"ok": False, "error": str(exc)})
    return JsonResponse({"ok": True, "message": message})
