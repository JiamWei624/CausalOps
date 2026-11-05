"""Deterministic synthetic tables. No private inputs, local case files or model dependencies."""
import csv
import json
from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[2]/"docs"/"evaluation"/"v23"
DATA = ROOT/"data"
TABLES = {
    "port": ("港口岸电的泊位日记录；零耗电日保留；没有天气、排放系数或船只级轨迹。","berth,day,kwh,calls,open_hours", "kwh","千瓦时","泊位日"),
    "lab": ("实验室的等分试样检测；同一标本有不同数量的复测，浓度以毫克/升记录；检测限未登记。","specimen,replicate,concentration,batch", "concentration","毫克/升","等分试样"),
    "donor": ("募捐项目每周汇总；pledged 为认捐额，paid 为到账额，donations 为笔数，没有唯一捐赠人数。","week,pledged,paid,donations,appeals", "paid","元","活动周"),
    "school": ("学校整体分配培训邀请，同校学生测评有重复，未提供外校传播或被邀请后出席的反事实。","school,pupil,wave,invited,attended,score", "score","分","学生测评"),
    "service": ("客服队列日记录；offered 为进线，answered 为接通，within_sla 为在时限内接通；无个人工号。","queue,day,offered,answered,within_sla", "within_sla","通","队列日"),
    "line": ("试制线每个生产批次的检测记录。温度由工程师选择；failures 是不合格件数，units 是检测件数。","batch,temperature,units,failures,shift", "failures","件","批次"),
}


def rows(name):
    for i in range(36):
        day=f"2025-04-{i%12+1:02d}"
        if name=="port":
            n=(i*5+2)%9
            yield (i//12+1,day,n*(i%5+1),n,0 if n==0 else 4+i%6)
        elif name=="lab":
            yield (f"S{int(math.sqrt(i)):02d}",i-math.isqrt(i)**2+1,round(2+(i*7%19)/10,1),1+i%4)
        elif name=="donor":
            yield (i+1,100*(3+i%8),80*(2+i%7),2+i%5,1+i%3)
        elif name=="school":
            school=i//6+1
            yield (school,i//2,i%2,school%2,int(bool(school%2 and i%3)),55+i%13+2*(i%2))
        elif name=="service":
            offered=0 if i%10==0 else 10+i%9
            answered=max(0,offered-i%4)
            yield ("Q"+str(i//12),day,offered,answered,max(0,answered-i%3))
        else:
            yield (i+1,60+i%11,10+3*(i%7),i%4,"夜" if i%3==0 else "日")


def contract(name):
    context,_,target,unit,grain=TABLES[name]
    return {"analysis_unit":grain,"outcome":target,"metric_label":target,"metric_unit":unit,
            "metric_kind":"continuous" if name=="lab" else "unknown","metric_window":"当前表全期",
            **({"time":"day"} if name in ("service","port") else {}),
            "research":{"provenance":"Eval V2.3 可复现合成数据","population":context}}


def generate():
    DATA.mkdir(parents=True,exist_ok=True)
    for name,(context,header,_,_,_) in TABLES.items():
        with (DATA/(name+".csv")).open("w",encoding="utf8",newline="") as f:
            writer=csv.writer(f,lineterminator="\n")
            writer.writerow(header.split(","))
            writer.writerows(rows(name))
        (DATA/(name+".json")).write_text(json.dumps(contract(name),ensure_ascii=False,indent=2)+"\n",encoding="utf8")


if __name__=="__main__":
    generate()
