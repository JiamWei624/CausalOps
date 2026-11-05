"""Deterministic explanation safeguards; declarations and saved facts remain authoritative.

No estimator, new statistics, data mutation or approval occurs in this module.
Fixed unit scales extend the existing threshold comparison registry.
"""
import re
from decimal import Decimal
from causalops.application.comparison import SCALE

UNITS = {**SCALE,
 "吨":("mass",1000000), "t":("mass",1000000), "kg":("mass",1000), "g":("mass",1),
 "毫克":("mass",Decimal(".001")), "mg":("mass",Decimal(".001")),
 "毫克/升":("concentration",1), "mg/L":("concentration",1),
 "克/升":("concentration",1000), "g/L":("concentration",1000),
 "微克/升":("concentration",Decimal(".001")), "ug/L":("concentration",Decimal(".001")),
 "千瓦时":("energy",1), "kWh":("energy",1), "kwh":("energy",1),
 "兆瓦时":("energy",1000), "MWh":("energy",1000),
 "微米":("length",1), "毫米":("length",1000), "米":("length",1000000)}
CONVERT = re.compile(r"换算|转换|折算|转成|改用.{0,8}单位")

def convert(value, source, target):
 a,b=UNITS.get(source),UNITS.get(target)
 if not a or not b or a[0]!=b[0]:raise ValueError("单位量纲或转换依据不足")
 x=Decimal(str(value))
 if not x.is_finite():raise ValueError("统计值无效")
 return x*Decimal(str(a[1]))/Decimal(str(b[1]))

def conversion_requested(question):
 clean=re.sub(r"(?:不要|无需|不必|不|勿|别)(?:再|直接|进行)?(?:换算|转换|折算|转成)[^，。；]*", "", question)
 return bool(CONVERT.search(clean))

def target_unit(question):
 m=re.search(r"(?:换算|转换|折算|转成|改用)(?:为|成|到)?\s*("+ "|".join(map(re.escape,sorted(UNITS,key=len,reverse=True)))+r")(?=$|[\s，。；？！,.;?!]|是多少|后|并|时|的)",question)
 return m[1] if m else None

def converted_value(value, unit, question):
 if not conversion_requested(question):return ""
 target=target_unit(question)
 if not target:return "目标单位或换算条件尚不明确，不能给出换算数值。"
 try:new=convert(value,unit,target)
 except ValueError:
  extra="质量与体积的换算还需要同一对象和条件下的密度。" if {UNITS.get(unit,("",))[0],UNITS.get(target,("",))[0]}=={"mass","volume"} else ""
  return "原统计单位与目标单位的量纲或换算依据不匹配，不能直接换算。"+extra
 return f"依据固定单位比例换算为 {new.normalize():f}{target}；统计对象、观察窗口与原统计量不变。"

def unit_guidance(question,body):
 if not conversion_requested(question):return ""
 origin=body.get("metric_unit","")
 if UNITS.get(origin,("",))[0]=="energy" and re.search(r"排放|减排|二氧化碳|CO2",question,re.I):
  return ("用电量与排放质量不是同一物理量，不能直接作单位换算。需要适用于该地区、时期和核算边界的排放因子。"
   "若电量以 kWh 计，因子为 gCO2e/kWh，排放吨数为电量乘因子再除以1000000；"
   "因子为 kgCO2e/kWh 时除以1000；因子为 tCO2e/MWh 时先将 kWh 除以1000，转换为 MWh 后再乘因子。"
   "这些是量纲关系，不是本次数据已计算的排放值。CO2 与 CO2e 的核算对象也需一致。"
   "排放量不等于减排量；减排需要明确被替代活动的基线排放，再减去实际活动排放，"
   "核对相同服务量、时期与边界及损耗等条件。现有电量本身不能证明减排。")
 if (UNITS.get(origin,("",))[0] in ("mass","volume") and ((re.search("质量",question) and re.search("体积",question)) or re.search("密度",question))):
  return "质量与体积不能仅凭数值换算，需要同一物质在相应温度、压力等条件下的密度及其单位。体积等于质量除以密度；质量等于体积乘以密度，先统一单位。现有证据不足时不提供换算结果。"
 return ""

def design_checked(text,body):
 facts=body.get("method_facts") or {}
 declarations={v.get("assignment") for v in facts.values() if isinstance(v,dict) and v.get("assignment") in ("randomized","observational")}
 supported=declarations=={"randomized"}
 if supported:return text,[]
 parts=re.split(r"(?<=[。！？；，\n])",text);changed=[];conditional=False
 for i,part in enumerate(parts):
  clause=part.strip()
  conditional=conditional or bool(re.match(r"若|如果|假设|if\b",clause,re.I))
  match=re.search(r"随机(?:化|分配|分组|分派|对照|试验|实验)|randomi[sz]",part,re.I)
  if match:
   prefix=part[:match.start()]
   qualified=conditional or re.search(r"前提|条件下|需要|须|不能|不代表|未确认|尚未|不等于|没有|并非|是否|无法|\b(?:not|no|without)\b",prefix,re.I)
   if not qualified and not re.search(r"随机化来自设计事实",part):
    parts[i]="当前登记尚未确认随机分配；存在两组或按某一单位分配，并不能证明随机化。须核对分配程序与设计依据，相关推断只能按条件说明。"
    changed.append("unsupported_randomization_statement")
  if re.search(r"[。！？；\n]$",part):conditional=False
 return "".join(parts),changed

def mean_explanation(question,body):
 if not re.search(r"解释|含义|意味着|说明|理解|代表",question):return ""
 grain=body.get("analysis_unit") or "已保存样本记录"
 return (f"该样本均值按记录汇总，描述本次纳入的{grain}的平均水平。"
  "若同一实体存在跨期或多次测量，记录较多的实体权重较高，不等于独立实体等权均值；"
  "需结合实体标识和重复测量口径核对。它不能单独证明总体水平或因果效果。")

def method_context(question,body):
 """Bounded design explanations, not assertions that required fields exist."""
 if re.search("分配|整群|随机单位",question) and re.search("独立|测评|重复|顾客|患者|学生",question):
  return ("应区分分配单位、分析单位与重复观测。按同一组织分配的个体及同一个体跨期测量可能相关，"
   "不能把每行都视为独立随机试验；按行计独立样本可能虚增有效样本量、低估不确定性。"
   "需核对分配单位标识、个体标识、时期、各组独立分配单位数和相应聚类或重复测量推断。"
   + ("登记资料声明随机分配，仍需核对实际执行及依赖结构。" if any(v.get("assignment")=="randomized" for v in (body.get("method_facts") or {}).values()) else
      "当前分配机制未确认为随机；需分配程序和设计资料，不能由存在处理组与对照组推断随机化。"))
 return ""
