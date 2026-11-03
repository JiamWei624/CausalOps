"""Offline, accessible two-group chart; rates are from one verified run."""
from html import escape


def group_chart(rates, labels=('对照组', '处理组')):
    rows = []
    for label, rate in zip(labels, (rates['control_rate'], rates['treated_rate'])):
        rows.append(f'<div style="margin:.6em 0">{escape(label)}　<strong>{rate:.2%}</strong>'
                    f'<div style="background:#e5efed;height:12px"><div style="background:#18756d;'
                    f'width:{100*rate:.6f}%;height:12px"></div></div></div>')
    return ('<figure style="margin:1em 0"><figcaption>两组事件发生比例（共同尺度 0–100%）</figcaption>'
            + ''.join(rows) + '</figure>')
