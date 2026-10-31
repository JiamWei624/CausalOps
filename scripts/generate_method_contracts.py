from pathlib import Path
from causalops.assistant.contracts import REGISTRY
root=Path(__file__).resolve().parents[1]
text='# 可执行方法合同\n\n由scripts/generate_method_contracts.py从统一注册表生成；不得手工维护另一套可执行清单。\n\n| 方法标识 | 名称 | 工具 | 审核要求 | 解释与限制 |\n|---|---|---|---|---|\n'
for m,v in REGISTRY.items():text+='| '+' | '.join([m,v.label,v.tool,v.review,v.limits])+' |\n'
(root/'docs/METHOD_CONTRACTS.md').write_bytes(text.encode())
print('Generated method contracts:',len(REGISTRY))
