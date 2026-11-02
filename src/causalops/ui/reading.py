"""Move focus once after a requested action. No research text enters the script."""
import uuid

import streamlit as st


def landmark(name, *, move=False, from_wait=False):
    if name not in {"overview", "wait", "plan", "result", "answer", "review", "issue"}:
        raise ValueError("Unknown reading destination")
    anchor = "causalops-" + name
    st.html(f'<span id="{anchor}" tabindex="-1" style="display:block;scroll-margin-top:5rem"></span>')
    if not move:
        return
    # During background completion the reader may have left the waiting area.
    guard = "if (window.__causalReadingMoved) return;" if from_wait else ""
    st.html(f"""<script>/* {uuid.uuid4().hex} */
    (() => {{
        const target = document.getElementById('{anchor}');
        if (!target) return;
        {guard}
        if (window.__causalReadingListener) window.__causalReadingListener.abort();
        const ctl = new AbortController();
        window.__causalReadingListener = ctl;
        window.__causalReadingMoved = false;
        for (const event of ['wheel','touchmove','pointerdown','keydown'])
            document.addEventListener(event, () => {{window.__causalReadingMoved = true}},
                {{signal:ctl.signal, passive:true, capture:true}});
        // Charts and the chat footer mount after the target. Re-align only while
        // this navigation owns focus and the reader has not started interacting.
        for (const delay of [0, 120, 350, 700, 1200]) setTimeout(() => {{
            if (ctl.signal.aborted || window.__causalReadingMoved) return;
            const live = document.getElementById('{anchor}');
            if (live) {{
                live.scrollIntoView({{block:'start', behavior:'instant'}});
                live.focus({{preventScroll:true}});
            }}
        }},delay);
    }})();</script>""", unsafe_allow_javascript=True)
