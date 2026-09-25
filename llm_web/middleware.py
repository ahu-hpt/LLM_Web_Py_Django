"""
统一登录鉴权中间件。

策略：除白名单外，匿名请求一律拒绝（默认拒绝，避免漏网接口）。
- /api/* 接口：返回 401 JSON（前端 fetch 据此跳转登录页）
- 其他页面：302 重定向到登录页并携带 next 参数
/admin/* 由 Django admin 自行处理鉴权，故整体放行。
"""
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse

PUBLIC_PREFIXES = (
    "/accounts/login/",
    "/accounts/logout/",
    "/admin/",
    "/static/",
)
PUBLIC_PATHS = {"/favicon.ico"}


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            path = request.path
            is_public = path.startswith(PUBLIC_PREFIXES) or path in PUBLIC_PATHS
            if not is_public:
                if path.startswith("/api/"):
                    return JsonResponse(
                        {"error": "未登录或会话已过期，请重新登录"}, status=401
                    )
                return redirect_to_login(path)
        return self.get_response(request)
