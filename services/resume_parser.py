"""Resume file parser — v0.12 支持 PDF / DOCX / TXT 即时解析"""
from __future__ import annotations
import os
from pathlib import Path
from core.logger import get_logger

logger = get_logger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MIN_TEXT_LENGTH = 50
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _detect_file_type(filename: str, content_type: str = "") -> str:
    """根据后缀和 content_type 判断文件类型"""
    ext = Path(filename).suffix.lower() if filename else ""
    if ext == ".pdf" or "pdf" in (content_type or ""):
        return "pdf"
    if ext == ".docx" or "officedocument" in (content_type or ""):
        return "docx"
    if ext == ".txt" or "text/plain" in (content_type or ""):
        return "txt"
    return ""


def _parse_pdf(content: bytes) -> tuple[str, list[str]]:
    """解析 PDF 文件"""
    try:
        import pypdf
        import io
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages), []
    except ImportError:
        return "", ["PDF 解析库(pypdf)未安装，请联系管理员"]
    except Exception as e:
        logger.warning(f"PDF 解析失败: {e}")
        return "", [f"PDF 解析失败: {str(e)[:80]}"]


def _parse_docx(content: bytes) -> tuple[str, list[str]]:
    """解析 DOCX 文件"""
    try:
        import docx
        import io
        doc = docx.Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs), []
    except ImportError:
        return "", ["DOCX 解析库(python-docx)未安装，请联系管理员"]
    except Exception as e:
        logger.warning(f"DOCX 解析失败: {e}")
        return "", [f"DOCX 解析失败: {str(e)[:80]}"]


def _parse_txt(content: bytes) -> tuple[str, list[str]]:
    """解析 TXT 文件，尝试多种编码"""
    warnings = []
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"):
        try:
            text = content.decode(encoding)
            if encoding != "utf-8":
                warnings.append(f"文件编码为 {encoding}，已自动转换")
            return text, warnings
        except (UnicodeDecodeError, LookupError):
            continue
    return "", ["无法识别文件编码"]


def parse_resume_file(filename: str, content: bytes, content_type: str = "") -> dict:
    """
    解析简历文件，返回解析结果。

    Returns:
        {
            "text": str,
            "file_type": "pdf/docx/txt",
            "char_count": int,
            "warnings": list[str],
        }
    Raises:
        ValueError: 文件格式不支持、文件为空、文件过大
    """
    # 文件大小检查
    if not content or len(content) == 0:
        raise ValueError("文件为空")
    if len(content) > MAX_FILE_SIZE:
        raise ValueError(f"文件过大，最大支持 {MAX_FILE_SIZE // (1024*1024)}MB")

    # 文件类型检测
    file_type = _detect_file_type(filename, content_type)
    if not file_type:
        raise ValueError(f"不支持的文件格式，仅支持 PDF / DOCX / TXT")

    # 解析
    warnings = []
    if file_type == "pdf":
        text, warnings = _parse_pdf(content)
    elif file_type == "docx":
        text, warnings = _parse_docx(content)
    else:
        text, warnings = _parse_txt(content)

    text = (text or "").strip()
    if not text:
        raise ValueError("文件解析结果为空，可能文件已损坏或格式不正确")

    if len(text) < MIN_TEXT_LENGTH:
        warnings.append(f"解析文本较短（{len(text)}字），可能解析不完整")

    logger.info(f"简历解析成功: {filename} ({file_type}, {len(text)}字)")
    return {
        "text": text,
        "file_type": file_type,
        "char_count": len(text),
        "warnings": warnings,
    }
