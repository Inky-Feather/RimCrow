from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from backend.managers.mgr_recommendation_export import RecommendationExportManager


def _sample_payload(preview_path: str = ""):
    # 统一样例覆盖别名、备注、标签、分组、作者、链接和封面，避免每个用例重复拼字段。
    return {
        "format": "txt",
        "source_name": "推荐:分组",
        "mods": [
            {
                "package_id": "author.mod",
                "package_id_raw": "Author.Mod",
                "name": "Original Mod",
                "alias_name": "好用模组",
                "notes": "适合作为推荐介绍。",
                "description": "原始描述不应默认出现。",
                "tags": ["QoL", "UI"],
                "group_names": ["推荐:分组"],
                "author": ["作者A", "作者B"],
                "supported_versions": ["1.6", "1.7"],
                "workshop_id": "1234567890",
                "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890",
                "preview_path": preview_path,
            }
        ],
    }


def test_sanitize_filename_replaces_windows_invalid_chars():
    manager = RecommendationExportManager()

    assert manager.sanitize_filename('a:b*c?d"e<f>g|h') == "a_b_c_d_e_f_g_h"


def test_plain_text_defaults_to_notes_and_omits_package_id():
    manager = RecommendationExportManager()
    normalized = manager.normalize_payload(_sample_payload())
    text = manager.render_plain_text(normalized["mods"], normalized["options"])

    # 默认导出面向推荐阅读：用备注做介绍，隐藏包名，保留标签、分组和作者。
    assert "001. 好用模组" in text
    assert "001. 名称：好用模组" not in text
    assert "介绍：适合作为推荐介绍。" in text
    assert "原始描述不应默认出现" not in text
    assert "包名：" not in text
    assert "#QoL #UI" in text
    assert "分组：推荐:分组" in text
    assert "作者：作者A、作者B" in text
    assert "支持版本：1.6、1.7" in text


def test_intro_is_after_tags_groups_authors_and_versions():
    manager = RecommendationExportManager()
    normalized = manager.normalize_payload(_sample_payload())
    text = manager.render_plain_text(normalized["mods"], normalized["options"])

    # 介绍排在标签、分组、作者和支持版本之后，便于先看分类信息，再读推荐说明。
    assert text.index("#QoL #UI") < text.index("分组：推荐:分组") < text.index("作者：作者A、作者B") < text.index("支持版本：1.6、1.7") < text.index("介绍：适合作为推荐介绍。")


def test_author_export_can_be_disabled():
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["options"] = {"include_authors": False}
    normalized = manager.normalize_payload(payload)
    text = manager.render_plain_text(normalized["mods"], normalized["options"])

    # 作者是可选字段，关闭后不应该留下空标签或多余分隔符。
    assert "作者：" not in text


def test_supported_versions_export_can_be_disabled():
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["options"] = {"include_supported_versions": False}
    normalized = manager.normalize_payload(payload)
    text = manager.render_plain_text(normalized["mods"], normalized["options"])

    # 支持版本是可选字段，关闭后不应影响介绍和其它基础字段。
    assert "支持版本：" not in text
    assert "作者：作者A、作者B" in text
    assert "介绍：适合作为推荐介绍。" in text


def test_language_pack_appendix_is_optional():
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["mods"][0]["language_packs"] = [
        {
            "name": "中文语言包",
            "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=9876543210",
        }
    ]

    text_without_appendix = manager.render_plain_text(
        manager.normalize_payload(payload)["mods"],
        manager.normalize_payload(payload)["options"],
    )
    payload["options"] = {"include_language_packs": True}
    normalized = manager.normalize_payload(payload)
    text = manager.render_plain_text(normalized["mods"], normalized["options"])

    # 语言包默认不附加；开启后按名称和网址附在对应模组字段后。
    assert "语言包：" not in text_without_appendix
    assert "语言包：中文语言包" in text
    assert "语言包网址：https://steamcommunity.com/sharedfiles/filedetails/?id=9876543210" in text


def test_description_option_replaces_notes():
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["options"] = {"body_source": "description"}
    normalized = manager.normalize_payload(payload)
    text = manager.render_plain_text(normalized["mods"], normalized["options"])

    # 选择 description 时会完全替换 notes，而不是把两段介绍拼在一起。
    assert "介绍：原始描述不应默认出现。" in text
    assert "适合作为推荐介绍" not in text


def test_plain_text_omits_original_name_when_alias_is_missing():
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["mods"][0]["alias_name"] = ""
    normalized = manager.normalize_payload(payload)
    text = manager.render_plain_text(normalized["mods"], normalized["options"])

    # 没有别名时标题直接显示原名，不再额外输出重复的“原名”字段。
    assert "001. Original Mod" in text
    assert "原名：Original Mod" not in text


def test_plain_text_without_sequence_keeps_name_field():
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["options"] = {"include_sequence": False}
    normalized = manager.normalize_payload(payload)
    text = manager.render_plain_text(normalized["mods"], normalized["options"])

    # 关闭序号后纯文本才保留“名称：”，否则标题已经承担名称展示。
    assert text.startswith("名称：好用模组\n")


def test_markdown_image_alt_normalizes_existing_backslash_escapes(tmp_path: Path):
    preview_path = tmp_path / "cover.png"
    Image.new("RGB", (320, 180), "#336699").save(preview_path)
    manager = RecommendationExportManager()
    payload = _sample_payload(str(preview_path))
    payload["format"] = "markdown"
    payload["mods"][0]["alias_name"] = r"Bandwidth Redux\[带宽显示重制\]"
    payload["mods"][0]["package_id"] = "flow.patch.bandwidthredux"

    result = manager.export(payload, target_dir=str(tmp_path / "out"))
    markdown = Path(result["path"]).read_text(encoding="utf-8")

    # 已经带反斜杠的名字先去旧转义，再生成 Markdown，避免出现 \\[ 这类不兼容显示。
    assert "![Bandwidth Redux(带宽显示重制)](./img/001-flow.patch.bandwidthredux.png)" in markdown
    assert r"\\[" not in markdown


def test_markdown_copies_cover_to_fixed_img_dir(tmp_path: Path):
    preview_path = tmp_path / "cover.png"
    Image.new("RGB", (320, 180), "#336699").save(preview_path)
    manager = RecommendationExportManager()
    payload = _sample_payload(str(preview_path))
    payload["format"] = "markdown"

    result = manager.export(payload, target_dir=str(tmp_path / "out"))

    md_path = Path(result["path"])
    image_path = md_path.parent / "img" / "001-author.mod.png"
    # Markdown 的图片目录固定为 img，图片文件名按序号和包名生成，方便整包分享。
    assert md_path.name == "推荐_分组.md"
    assert md_path.is_file()
    assert image_path.is_file()
    assert "./img/001-author.mod.png" in md_path.read_text(encoding="utf-8")


def test_markdown_uses_title_and_clickable_url_without_repeated_name(tmp_path: Path):
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["format"] = "markdown"

    result = manager.export(payload, target_dir=str(tmp_path / "out"))
    markdown = Path(result["path"]).read_text(encoding="utf-8")

    # Markdown 文档用标题承载名称，网址使用可点击的尖括号链接形式。
    assert markdown.startswith("# 推荐:分组\n")
    assert "## 001\\. 好用模组" in markdown
    assert "名称：" not in markdown
    assert markdown.index("#QoL #UI") < markdown.index("分组：推荐:分组") < markdown.index("作者：作者A、作者B") < markdown.index("支持版本：1\\.6、1\\.7") < markdown.index("介绍：适合作为推荐介绍。")
    assert "网址：<https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890>" in markdown


def test_custom_source_name_drives_default_filename_and_text_title(tmp_path: Path):
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["format"] = "txt"
    payload["source_name"] = "我的推荐:第一期"
    default_name = manager.default_filename(payload)
    txt_path = tmp_path / default_name

    result = manager.export(payload, target_path=str(txt_path))
    text = Path(result["path"]).read_text(encoding="utf-8")

    # 用户自定义导出名同时影响默认文件名和文档标题，非法文件名字符会被替换。
    assert default_name == "我的推荐_第一期.txt"
    assert text.startswith("我的推荐:第一期\n\n001. 好用模组")


def test_image_export_uses_alias_filename_by_default(tmp_path: Path):
    preview_path = tmp_path / "cover.png"
    Image.new("RGB", (320, 180), "#336699").save(preview_path)
    manager = RecommendationExportManager()
    payload = _sample_payload(str(preview_path))
    payload["format"] = "image"

    result = manager.export(payload, target_dir=str(tmp_path / "images"))

    output_dir = Path(result["path"])
    exported = Path(result["files"][0])
    # 纯图片先按导出名称创建文件夹，再用别名生成单图文件，便于整组分享。
    assert output_dir.name == "推荐_分组"
    assert output_dir.parent == tmp_path / "images"
    assert exported.parent == output_dir
    assert exported.name == "001-好用模组.png"
    assert exported.is_file()


def test_image_export_creates_unique_named_folder(tmp_path: Path):
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["format"] = "image"
    parent_dir = tmp_path / "images"
    (parent_dir / "推荐_分组").mkdir(parents=True)

    result = manager.export(payload, target_dir=str(parent_dir))

    # 同名导出目录已存在时创建新目录，避免覆盖用户之前生成的介绍图。
    output_dir = Path(result["path"])
    assert output_dir.name == "推荐_分组_2"
    assert output_dir.is_dir()
    assert Path(result["files"][0]).parent == output_dir


def test_image_export_keeps_animated_png_cover(tmp_path: Path):
    preview_path = tmp_path / "animated.png"
    frames = [
        Image.new("RGB", (120, 80), "#cc3333"),
        Image.new("RGB", (120, 80), "#3366cc"),
    ]
    frames[0].save(preview_path, "PNG", save_all=True, append_images=frames[1:], duration=[80, 120], loop=0)
    manager = RecommendationExportManager()
    payload = _sample_payload(str(preview_path))
    payload["format"] = "image"

    result = manager.export(payload, target_dir=str(tmp_path / "images"))

    exported = Path(result["files"][0])
    with Image.open(exported) as image:
        # 推荐图封面是动图时，输出仍是 PNG，但应保留 APNG 多帧信息。
        assert getattr(image, "n_frames", 1) == 2
        image.seek(0)
        first_pixel = image.convert("RGB").getpixel((20, 20))
        image.seek(1)
        second_pixel = image.convert("RGB").getpixel((20, 20))
    assert first_pixel != second_pixel


def test_docx_and_pdf_exports_create_files(tmp_path: Path):
    preview_path = tmp_path / "cover.png"
    Image.new("RGB", (320, 180), "#336699").save(preview_path)
    manager = RecommendationExportManager()

    docx_payload = _sample_payload(str(preview_path))
    docx_payload["format"] = "docx"
    docx_path = tmp_path / "recommend.docx"
    docx_result = manager.export(docx_payload, target_path=str(docx_path))

    pdf_payload = _sample_payload(str(preview_path))
    pdf_payload["format"] = "pdf"
    pdf_path = tmp_path / "recommend.pdf"
    pdf_result = manager.export(pdf_payload, target_path=str(pdf_path))

    # 这里只验证两类富文档能成功落盘，具体结构在后续用例单独检查。
    assert Path(docx_result["path"]).is_file()
    assert docx_path.stat().st_size > 0
    assert Path(pdf_result["path"]).is_file()
    assert pdf_path.stat().st_size > 0


def test_docx_uses_heading_name_and_clickable_url(tmp_path: Path):
    manager = RecommendationExportManager()
    payload = _sample_payload()
    payload["format"] = "docx"
    payload["source_name"] = "我的推荐"
    docx_path = tmp_path / "recommend.docx"

    manager.export(payload, target_path=str(docx_path))

    with ZipFile(docx_path) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        relations_xml = archive.read("word/_rels/document.xml.rels").decode("utf-8")

    # DOCX 里名称应作为标题出现，链接写入 Word 关系表后才能被点击。
    assert "名称：" not in document_xml
    assert "我的推荐" in document_xml
    assert "w:hyperlink" in document_xml
    assert 'Target="https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890"' in relations_xml


def test_pdf_url_field_is_rendered_as_hyperlink_markup():
    manager = RecommendationExportManager()

    line = manager._format_pdf_field_line("网址：https://example.com?a=1&b=2")

    # PDF 超链接是 HTML-like 标记，URL 参数必须转义，避免 & 被 ReportLab 当成实体解析。
    assert '<a href="https://example.com?a=1&amp;b=2">' in line
