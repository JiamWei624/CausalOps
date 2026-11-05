"""Contract for one decision. Regeneration here has no browser side effects."""
import re
from causalops.llm.providers import OutputContractError, ProviderError, StructuredModelClient

ACTIONS = ("click", "input", "send", "upload", "reload", "wait", "done", "abandon")
SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string", "enum": list(ACTIONS)},
                   **{k: {"type": "string"} for k in ("ref", "value", "note")}},
    "required": ["action", "ref", "value", "note"],
    "additionalProperties": False,
}
INSTRUCTIONS = """
每个动作必须有 action、ref、value、note 四个字符串字段，不增加其他字段。
click 点击按钮、选项、复选框、展开标题或下拉框；input 仅填写文本；send 仅向可填写文本框输入并按回车。
upload 使用可见上传控件，value 是题面提供的附件名。无目标动作 ref 为空，未用的 value 为空。
wait 等待页面更新；reload 刷新；done 的 note 交付答案；无法继续可 abandon。提交后先观察新状态。
完成前核对题目中的目标、已看到的内容及仍需操作的步骤。不要靠猜测完成。
"""


class ActorClient(StructuredModelClient):
    """Capture only model text, never authentication headers or request objects."""
    raw_action = None

    def _content(self, response):
        text, usage = super()._content(response)
        if self._api_key not in text:
            self.raw_action = text
        return text, usage


class InvalidAction(ValueError):
    def __init__(self, category, message):
        super().__init__(message)
        self.category = category


def check_action(action, controls, files):
    kind, ref, value = (action[k] for k in ("action", "ref", "value"))
    if kind not in ACTIONS:
        raise InvalidAction("parameter", "未知动作类型")
    if kind in ("reload", "wait", "done", "abandon"):
        if ref or value:
            raise InvalidAction("parameter", "无目标动作的 ref 和 value 必须为空")
        return
    control = next((c for c in controls if c["ref"] == ref), None)
    if control is None or control["disabled"]:
        raise InvalidAction("target", "控件不存在、不可见或已禁用")
    role = control["role"]
    if kind in ("input","send") and (role not in ("text","textarea","textbox","search") or not value.strip()):
        raise InvalidAction("parameter", "填写或发送须使用文本输入控件和非空内容")
    if kind == "upload" and (role != "upload" or value not in files):
        raise InvalidAction("parameter", "上传须选择题面提供的文件和可用上传控件")
    if kind == "click" and (role == "upload" or value):
        raise InvalidAction("parameter", "点击不接受附加内容，也不能用于上传文件")


def decide(model, instructions, payload, event, files):
    requests = event["requests"] = []
    for attempt in range(2):
        model.raw_action = None
        body = dict(payload)
        if attempt:
            body["action_validation_feedback"] = requests[-1]["reason"]
        record = {"repair": bool(attempt)}
        requests.append(record)
        try:
            action = model.complete_json(system_instruction=instructions + INSTRUCTIONS,
                                         user_payload=body, output_schema=SCHEMA)
            check_action(action, payload["page"]["controls"], files)
            record["status"] = "valid"
            return action
        except (InvalidAction, ProviderError) as exc:
            if isinstance(exc, InvalidAction):
                category = exc.category
            elif isinstance(exc, OutputContractError):
                category = "format"
            elif "未完成" in str(exc) and model.last_telemetry.get("status_code") == 200:
                category = "incomplete"
            else:
                category = "transport"
            record.update(status=category, reason=str(exc)[:200])
            if attempt or category == "transport":
                raise
        finally:
            record.update(telemetry=dict(model.last_telemetry), raw_action=model.raw_action)
            event["telemetry"] = record["telemetry"]


def guard_dispatch(action, control, obs, task, issued):
    """Never repeat an uncertain transaction. Checkbox toggles do not grant approval."""
    kind = action["action"]
    name = (control or {}).get("name","")
    if kind == "click" and "批准本次执行" in name:
        if task != "N06" or not re.search(r"(?:本次计划指标|结果|目标指标)[：:]\s*visitors\b",obs["text"],re.I):
            raise InvalidAction("scope","题面未授权批准当前指标")
    mutating = kind in ("upload","send") or kind == "click" and re.search(r"创建任务|批准本次执行|运行统计|Send message|执行分析",name,re.I)
    if mutating:
        key = (kind, obs["location"], name, action["value"])
        if key in issued:
            raise InvalidAction("replay","之前已尝试提交，请核查页面状态；本控制器不重复派发")
        issued.add(key)

