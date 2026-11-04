() => {
  const main = document.querySelector('[data-testid="stMain"]') || document.body;
  const tidy = s => (s || '').replace(/\s+/g,' ').trim();
  function visible(el) {
    if (!el.getClientRects().length || getComputedStyle(el).visibility==='hidden') return false;
    for(let d=el.closest('details:not([open])');d;d=d.parentElement?.closest('details:not([open])')){
      if(!d.querySelector(':scope > summary')?.contains(el))return false;
    }
    return !el.closest('[aria-hidden="true"]');
  }
  const fields=Array.from(document.querySelectorAll('button,a[href],textarea,input,select,summary,[role="tab"],[role="option"],[role="radio"],[role="combobox"],[role="button"],[role="checkbox"]'));
  const controls=[];
  for(const [i,e] of fields.entries()){
    if(!visible(e)||e.type==='password'||e.type==='hidden')continue;
    const tag=e.tagName.toLowerCase();
    const role=e.getAttribute('role')||({summary:'button',button:'button',a:'link',textarea:'textbox',select:'combobox'})[tag]||({file:'file',radio:'radio',checkbox:'checkbox',text:'textbox',search:'textbox',number:'textbox'})[e.type];
    if(!role)continue;
    const labels=(e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.innerText).join(' ');
    const name=tidy(e.getAttribute('aria-label')||labels.trim()||(e.labels&&Array.from(e.labels).map(v=>v.innerText).join(' '))||e.placeholder||e.innerText||e.title);
    if(!name||/API 密钥|显示密钥/.test(name))continue;
    const control={ref:'r'+i,role,name,disabled:!!(e.disabled||e.getAttribute('aria-disabled')==='true')};
    if(role==='combobox')control.options=Array.from(document.querySelectorAll('[role="option"]')).filter(visible).map(x=>tidy(x.innerText));
    if(role==='textbox'||role==='combobox')control.value=e.value||'';
    if(role==='checkbox'||role==='radio')control.checked=!!(e.checked||e.getAttribute('aria-checked')==='true');
    controls.push(control);
  }
  const text=main.innerText||'';
  const phase=(text.match(/分析状态[：:]\s*([^\n]+)/)||[])[1]||'';
  const pending=/后台正在处理|请求已登记，正在处理|后台处理中|正在安全停止/.test(text);
  const headings=Array.from(main.querySelectorAll('[data-testid="stMarkdownContainer"] strong')).filter(e=>visible(e)&&/^(方法说明|分析建议|数据概览|结果解读|信息补充)$/.test(tidy(e.innerText)));
  let reply='';
  for(const h of headings){
    const box=h.closest('[data-testid="stElementContainer"]');
    if(!box)continue;
    const src=box.nextElementSibling, content=src?.nextElementSibling;
    if(content&&visible(content)&&content.querySelector('[data-testid="stMarkdownContainer"]'))reply=content.innerText.trim();
  }
  const plan=Array.from(main.querySelectorAll('details')).filter(e=>e.open&&visible(e)&&/分析方案.*V\d+/i.test(e.querySelector('summary')?.innerText||'')).map(e=>e.innerText).join('\n');
  return {url:location.href,text,controls,reply,plan_text:plan,phase,pending,disconnected:/Connection (?:error|lost)|Disconnected|连接已断开/.test(text)};
}
