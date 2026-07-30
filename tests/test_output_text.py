from gui.output_text import decode_external_output, sanitize_external_text


def test_decode_external_output_accepts_utf8_chinese():
    assert decode_external_output("部署完成".encode("utf-8")) == "部署完成"


def test_decode_external_output_falls_back_to_gb18030():
    assert decode_external_output("部署失败".encode("gb18030")) == "部署失败"


def test_external_text_removes_terminal_escape_sequences_and_controls():
    raw = b"\x1b[32mSUCCESS\x1b[0m \xe9\x83\xa8\xe7\xbd\xb2\x00\xe5\xae\x8c\xe6\x88\x90\r\n"
    assert decode_external_output(raw) == "SUCCESS 部署完成"


def test_sanitize_external_text_preserves_lines():
    assert sanitize_external_text("第一行\r\n\x1b[31m第二行\x1b[0m") == "第一行\n第二行"
