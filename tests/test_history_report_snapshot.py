from html.parser import HTMLParser

from causalops.ui.history_report import history_html


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_report_label_summary_and_details_are_in_one_escaped_snapshot():
    markup = history_html("实验甲", {"run_id": "abc", "plan_sha": "verified", "plan_version": 3},
                          {"metric_label": "访问率", "metric_window": "两周"},
                          {"sections": {"magnitude": "<img>差异"}, "evidence": {"来源": "<script>"}},
                          [{"url": "javascript:void(0)", "title": "非法地址"},
                           {"url": "https://example.org/method", "title": "方法"}])
    elements = Elements()
    elements.feed(markup)
    assert elements.tags[0][1]["data-history-rid"] == "abc"
    assert markup.endswith("</section>")
    assert "实验甲 · 访问率 · V3" in markup and "两周" in markup
    assert "运行编号：abc" in markup and "verified" in markup
    assert "&lt;img&gt;差异" in markup and "&lt;script&gt;" in markup
    assert [attrs["href"] for tag, attrs in elements.tags if tag == "a"] == ["https://example.org/method"]
