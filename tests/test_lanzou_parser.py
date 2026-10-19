from unittest.mock import Mock

import pytest
import requests

from backend.utils.lanzou_parser import LanzouParser


def response(text="", payload=None, url="", status=200, headers=None):
    result = Mock()
    result.text = text
    result.encoding = "utf-8"
    result.url = url
    result.status_code = status
    result.headers = headers or {}
    result.iter_content.return_value = [text.encode("utf-8")]
    result.json.side_effect = None if payload is not None else ValueError("not JSON")
    result.json.return_value = payload
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(status))
    return result


@pytest.fixture
def parser():
    session = Mock(headers={}, cookies=requests.cookies.RequestsCookieJar())
    return LanzouParser(session=session)


FRAME = """
let signature = "sig,with:punctuation";
const key = "new" + "-key";
var primary = 'https://api.example/new-download?file=123';
var secondary = '//backup.example/new-download?file=123';
if (typeof(killdnsweb) == 'undefined') { endpoint = secondary; }
else { endpoint = primary; }
$.ajax({url: '/telemetry', data: {action: 'save'}});
$.ajax({data: {action: 'downprocess', sign: signature, websignkey: key, kd: 1},
        url: endpoint, success: function(data) { console.log(data); }});
"""

FIRST_PAGE = [{"id": "old", "name_all": "RimCrow-v0.1.0-windows.zip"}] + [
    {"id": f"readme-{index}", "name_all": "readme.txt"} for index in range(49)
]


def test_variable_endpoints_retry_and_preserve_payload(parser):
    probe = response()
    parser.session.get.side_effect = [response(FRAME), probe]
    parser.session.post.side_effect = [requests.Timeout("offline"), response(payload={
        "zt": "1", "dom": "https://cdn.example", "url": "token",
    })]

    result = parser._get_direct_link_from_ifr("https://share.example/frame", "123")

    assert result == "https://cdn.example/file/token"
    calls = parser.session.post.call_args_list
    assert [call.args[0] for call in calls] == [
        "https://backup.example/new-download?file=123",
        "https://api.example/new-download?file=123",
    ]
    assert calls[-1].kwargs["data"] == {
        "action": "downprocess", "sign": "sig,with:punctuation", "websignkey": "new-key", "kd": 1,
    }
    assert parser.session.get.call_args.kwargs["stream"] is True
    probe.close.assert_called_once()


@pytest.mark.parametrize("url_expression", ["'/api?file=' + fileId", "alias"])
def test_static_aliases_and_concatenation(parser, url_expression):
    frame = f"""const fileId=123, alias='/api?file=' + fileId;
    jQuery.ajax({{url:{url_expression},data:{{action:'downprocess',sign:'s'}}}});"""
    parser.session.get.side_effect = [response(frame), response(status=307, headers={"Location": "/signed.zip"}), response()]
    parser.session.post.return_value = response(payload={"zt": 1, "dom": "cdn.example/", "url": "token"})
    assert parser._get_direct_link_from_ifr("https://share.example/frame", "123") == "https://cdn.example/signed.zip"
    assert parser.session.post.call_args.args[0] == "https://share.example/api?file=123"


def test_unresolved_or_executable_values_are_not_posted(parser):
    parser.session.get.return_value = response("""
    $.ajax({url:'/api',data:{action:'downprocess',sign:makeSignature()}});
    """)
    assert parser._get_direct_link_from_ifr("https://share.example/frame", "123") is None
    parser.session.post.assert_not_called()
    assert parser.last_error


def test_selects_download_frame_and_decodes_html_entities(parser):
    parser.session.get.return_value = response("""
    <iframe src='/ads'></iframe>
    <div class='n_box_des'>First<br/>Second &amp; third</div>
    <iframe class='ifr2' src='frames/new?a=1&amp;b=2'></iframe>
    """, url="https://share.example/redirect/item")
    parser._get_direct_link_from_ifr = Mock(return_value="https://cdn.example/file.zip")
    result = parser.get_file("https://share.example/item")
    assert result["note"] == "First\nSecond & third"
    assert parser._get_direct_link_from_ifr.call_args.args[0] == "https://share.example/redirect/frames/new?a=1&b=2"


def test_folder_parameters_and_pagination(parser):
    parser.session.get.return_value = response("""
    <script>const timestamp="time", key="k"; let page=1;
    $.ajax({url:'/folder-api',data:{fid:12,t:timestamp,k:key,pg:page,pwd:readPassword(),extra:'keep'}});
    </script>""", url="https://share.example/folder")
    parser.session.post.side_effect = [
        response(payload={"zt": "1", "text": FIRST_PAGE}),
        response(payload={"zt": 1, "text": [{"id": "new?webpage=keep", "name_all": "RimCrow-v0.2.0-windows.zip"}]}),
        response(payload={"zt": 2, "info": "empty"}),
    ]
    parser.get_file = Mock(return_value={"note": "release", "download_url": "https://cdn.example/file.zip"})
    result = parser.get_all_files("share.example/folder", "secret")
    assert len(result["files"]) == 51
    assert result["latest"]["version"] == "0.2.0"
    assert parser.get_file.call_args.args[0] == "https://share.example/new?webpage=keep"
    calls = parser.session.post.call_args_list
    assert [call.kwargs["data"]["pg"] for call in calls] == [1, 2]
    assert calls[0].kwargs["data"]["pwd"] == "secret"
    assert calls[0].kwargs["data"]["extra"] == "keep"
    assert calls[0].kwargs["headers"]["Referer"] == "https://share.example/folder"


@pytest.mark.parametrize("second", [
    {"zt": 1, "text": [{"id": "old", "name_all": "RimCrow-v0.1.0.zip"}]},
    {"zt": 3, "info": "denied"},
    {"zt": 1, "text": "unexpected"},
])
def test_incomplete_listing_never_claims_latest(parser, second):
    parser.session.get.return_value = response("""<script>
    $.ajax({url:'/api',data:{fid:1,t:'t',k:'k',pg:1,pwd:''}});</script>""")
    parser.session.post.side_effect = [
        response(payload={"zt": 1, "text": FIRST_PAGE}),
        response(payload=second),
    ]
    assert parser.get_all_files("https://share.example/folder") is None
    assert parser.last_error
    assert parser.session.post.call_count == 2


def test_file_error_is_reported_and_success_clears_previous_error(parser):
    parser.last_error = "previous failure"
    parser.session.get.return_value = response(status=403)
    assert parser.get_file("https://share.example/item") is None
    assert "403" in parser.last_error
    parser.session.get.return_value = response("<iframe src='/frame'></iframe>")
    parser._get_direct_link_from_ifr = Mock(return_value="https://cdn.example/file.zip")
    assert parser.get_file("https://share.example/item") is not None
    assert parser.last_error == ""


def test_invalid_download_response_is_not_a_link(parser):
    parser.session.get.return_value = response("$.ajax({url:'/api',data:{action:'downprocess',sign:'s'}});")
    parser.session.post.return_value = response(payload={"zt": 1, "dom": "javascript:alert(1)", "url": "0"})
    assert parser._get_direct_link_from_ifr("https://share.example/frame", "1") is None
    assert parser.last_error


def test_download_chain_solves_node_challenge_and_closes_every_response(parser):
    challenge = """<script>const arg1="B0F7DFAACD80635E8AF18DF2B24B461666A78C0A";
    document.cookie='acw_sc__v2=';</script>"""
    replies = [
        response(status=302, headers={"Location": "https://node.example/check"}),
        response(challenge, headers={"Content-Type": "text/html; charset=utf-8"}),
        response(status=308, headers={"Location": "https://cdn.example/signed.zip"}),
        response(headers={"Content-Type": "application/octet-stream", "Content-Length": "74733041"}),
    ]
    parser.session.get.side_effect = replies
    assert parser._resolve_download_url("https://entry.example/file/token", "https://share.example/frame") == "https://cdn.example/signed.zip"
    assert parser.session.cookies.get("acw_sc__v2", domain="node.example") == "6a4279dcdc74c4d9b0ed0b4908616fa7aa7b6b72"
    for item in replies:
        item.close.assert_called_once()
    replies[-1].iter_content.assert_not_called()


@pytest.mark.parametrize("html", ["<html>captcha required</html>", "x" * 65537], ids=["captcha", "oversized"])
def test_download_html_is_never_returned_as_a_file(parser, html):
    res = response(html, headers={"Content-Type": "text/html"})
    parser.session.get.return_value = res
    with pytest.raises(ValueError):
        parser._resolve_download_url("https://node.example/file/token", "https://share.example/frame")
    res.close.assert_called_once()


def test_download_redirect_loop_is_bounded(parser):
    res = response(status=302, headers={"Location": "/loop"})
    parser.session.get.return_value = res
    with pytest.raises(ValueError):
        parser._resolve_download_url("https://node.example/loop", "https://share.example/frame")
    assert parser.session.get.call_count == 8
    assert res.close.call_count == 8


def test_download_http_failure_is_not_a_success(parser):
    res = response(status=403)
    parser.session.get.return_value = res
    with pytest.raises(requests.HTTPError):
        parser._resolve_download_url("https://node.example/file/token", "https://share.example/frame")
    res.close.assert_called_once()


def test_static_analysis_ignores_assignments_inside_strings_and_comments():
    html = """<script>
    const misleading = "signature='wrong'; $.ajax({url:'/tracking',data:{action:'downprocess'}})";
    // signature='comment';
    let signature = "right\\u002dvalue";
    /* signature='block-comment'; */
    $.ajax({url:'/real',data:{action:'downprocess',sign:signature}});
    </script>"""
    assert LanzouParser._extract_requests(html, "https://share.example/frame", "download") == [
        ("https://share.example/real", {"action": "downprocess", "sign": "right-value"}),
    ]


def test_cyclic_variables_are_rejected():
    html = """var first=second; var second=first;
    $.ajax({url:first,data:{action:'downprocess',sign:'s'}});"""
    with pytest.raises(ValueError):
        LanzouParser._extract_requests(html, "https://share.example/frame", "download")


@pytest.mark.parametrize("bad", [None, {"zt": 0}, {"zt": 1, "dom": "cdn.example", "url": "0"}])
def test_invalid_primary_response_tries_other_declared_endpoint(parser, bad):
    parser.session.get.side_effect = [response(FRAME), response()]
    parser.session.post.side_effect = [
        response(payload=bad),
        response(payload={"zt": 1, "dom": "cdn.example", "url": "token"}),
    ]
    assert parser._get_direct_link_from_ifr("https://share.example/frame") == "https://cdn.example/file/token"
    assert parser.session.post.call_count == 2


def test_legacy_table_description_excludes_other_metadata(parser):
    parser.session.get.return_value = response("""<table><td>
    <span>文件大小：</span>71 MB<br><span>上传时间：</span>today<br>
    <span>文件描述：</span><br>release<br/>details</td></table><iframe src='/frame'></iframe>""")
    parser._get_direct_link_from_ifr = Mock(return_value="https://cdn.example/file.zip")
    assert parser.get_file("https://share.example/item")["note"] == "release\ndetails"


def test_repeated_page_with_rotating_query_tokens_is_rejected(parser):
    parser.session.get.return_value = response("$.ajax({url:'/api',data:{fid:1,t:'t',k:'k',pg:1}});")
    parser.session.post.side_effect = [
        response(payload={"zt": 1, "text": FIRST_PAGE}),
        response(payload={"zt": 1, "text": [{**item, "id": item["id"] + "?webpage=changed"} for item in FIRST_PAGE]}),
    ]
    assert parser.get_all_files("https://share.example/folder") is None
    assert parser.session.post.call_count == 2


def test_no_working_download_means_no_actionable_update(parser):
    parser.session.get.return_value = response("$.ajax({url:'/api',data:{fid:1,t:'t',k:'k',pg:1}});")
    parser.session.post.return_value = response(payload={"zt": 1, "text": FIRST_PAGE[:1]})
    parser.get_file = Mock(return_value=None)
    assert parser.get_all_files("https://share.example/folder") is None
    assert parser.last_error


def test_payload_branches_are_candidates_not_silently_chosen():
    html = """var/* separator */kd=1; if (missing) { kd=0; }
    $.ajax({url:'/api',data:{action:'downprocess',sign:'s',kd:kd}});"""
    requests = LanzouParser._extract_requests(html, "https://share.example/frame", "download")
    assert [payload["kd"] for _, payload in requests] == [1, 0]


def test_failed_download_node_tries_other_declared_endpoint(parser):
    parser.session.get.side_effect = [
        response(FRAME),
        response("<html>unavailable</html>", headers={"Content-Type": "text/html"}),
        response(headers={"Content-Type": "application/octet-stream"}),
    ]
    parser.session.post.side_effect = [
        response(payload={"zt": 1, "dom": "bad.example", "url": "token"}),
        response(payload={"zt": 1, "dom": "cdn.example", "url": "token"}),
    ]
    assert parser._get_direct_link_from_ifr("https://share.example/frame") == "https://cdn.example/file/token"
    assert parser.session.post.call_count == 2
