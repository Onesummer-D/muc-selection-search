"""真实门户形态测试：POST 表单、datas.tables、snake_case 字段、list 详情模式。

字段与响应结构来自 2026-09-18 对 my.muc.edu.cn 的登录探测
（证据：evidence/week1/A/endpoint-probe.json）。
"""
from __future__ import annotations

import unittest

from app.datasource.config import PortalConfig
from app.datasource.portal_client import PortalClient, PortalError
from tests.datasource.fake_portal import FakeClock, FakePortal


def real_config():
    """模拟 from_env 的真实门户默认值。"""
    return PortalConfig(
        base_url="https://my.muc.edu.cn",
        list_endpoint="comsys-portal-notice-web/getNoticeByPage",
        list_params={"type": "10", "searchValue": ""},
        http_method="POST",
        page_param="currentPage",
        page_size_param="pageSize",
        random_param="comsys_random_t",
        detail_source="list",
        page_size=2,
    )


def real_row(nid, title, content="", link=""):
    return {
        "notice_title": title,
        "notice_id": nid,
        "notice_content": content,
        "notice_link": link,
        "notice_first_time": "2026-09-16 10:15",
        "notice_create_time": "2026-09-16 10:15",
        "notice_type_name": "就业信息",
        "organization_name": "某学院",
        "notice_link_state": 1 if link else 0,
    }


class TestRealPortalShape(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def make_client(self, portal):
        return PortalClient(real_config(), portal, clock=self.clock,
                            sleep=self.clock.sleep)

    def test_list_uses_post_and_datas_tables(self):
        portal = FakePortal(pages={1: [real_row(358715, "选调经验分享会"),
                                       real_row(358780, "普通新闻")]})
        client = self.make_client(portal)
        items = client.list_notices(1)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["notice_id"], "358715")
        self.assertEqual(items[0]["title"], "选调经验分享会")
        # 请求是 POST 且带真实参数名
        call = portal.calls[0]
        self.assertEqual(call["params"].get("currentPage"), 1)
        self.assertEqual(call["params"].get("type"), "10")
        self.assertIn("comsys_random_t", call["params"])

    def test_detail_from_list_row(self):
        rows = [real_row(358715, "我的选调上岸心得",
                         content="<p>备考体会……</p>",
                         link="https://mp.weixin.qq.com/s/abc")]
        portal = FakePortal(pages={1: rows})
        client = self.make_client(portal)
        client.list_notices(1)  # 触发行缓存
        detail = client.get_notice("358715")
        self.assertEqual(detail["title"], "我的选调上岸心得")
        self.assertIn("备考体会", detail["content"])
        self.assertEqual(detail["source_url"], "https://mp.weixin.qq.com/s/abc")
        self.assertEqual(detail["notice_type"], "就业信息")

    def test_detail_images_extracted_from_html(self):
        rows = [real_row(1, "海报帖", content='<p><img src="https://x/a.jpg"></p>')]
        portal = FakePortal(pages={1: rows})
        client = self.make_client(portal)
        client.list_notices(1)
        detail = client.get_notice("1")
        self.assertEqual(detail["images"],
                         [{"url": "https://x/a.jpg"}])

    def test_detail_not_found_raises(self):
        portal = FakePortal(pages={1: [real_row(1, "仅此一篇")]})
        client = self.make_client(portal)
        with self.assertRaises(PortalError):
            client.get_notice("999")

    def test_pagination_terminates_on_short_page(self):
        portal = FakePortal(pages={1: [real_row(1, "a"), real_row(2, "b")]})
        client = self.make_client(portal)
        collected = [i["notice_id"] for i in client.iterate_notices()]
        self.assertEqual(collected, ["1", "2"])

    def test_validate_session_posts_with_real_params(self):
        portal = FakePortal(pages={1: [real_row(1, "a")]})
        client = self.make_client(portal)
        self.assertTrue(client.validate_session())
        call = portal.calls[0]
        self.assertEqual(call["params"].get("pageSize"), 1)


if __name__ == "__main__":
    unittest.main()
