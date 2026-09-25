from django.db import models


class ApiConfig(models.Model):
    """大模型 API 配置（单例：全站只使用 id 最小的一条记录）。

    接口地址遵循 OpenAI 兼容协议，可对接：
    vLLM / Ollama / Xinference / LocalAI / One-API / 各云厂商兼容端点。
    """

    base_url = models.CharField(
        "接口地址（Base URL）",
        max_length=300,
        default="http://localhost:8000/v1",
        help_text="例如 http://localhost:8000/v1 或 https://api.openai.com/v1",
    )
    api_key = models.CharField(
        "API Key",
        max_length=300,
        blank=True,
        default="",
        help_text="本地部署无需鉴权时可留空",
    )
    model = models.CharField(
        "模型名称",
        max_length=200,
        default="qwen2.5-7b-instruct",
        help_text="部署服务中的模型 ID，例如 qwen2.5-7b-instruct、gpt-4o-mini",
    )
    temperature = models.FloatField("Temperature（随机性）", default=0.7)
    max_tokens = models.PositiveIntegerField(
        "最大生成 Token 数", default=2048, null=True, blank=True
    )
    system_prompt = models.TextField(
        "系统提示词", blank=True, default="你是一个乐于助人的中文 AI 助手。"
    )
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "API 配置"
        verbose_name_plural = "API 配置"

    def __str__(self):
        return f"{self.model} @ {self.base_url}"

    @classmethod
    def get_config(cls):
        """返回当前生效的配置（第一条记录），未配置时返回 None。"""
        return cls.objects.order_by("id").first()
