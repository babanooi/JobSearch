"""Resume parsing and user skill profile extraction."""
from __future__ import annotations

import json
import re
import zipfile
from html import unescape
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO
from xml.etree import ElementTree

from core.logger import get_logger
from tools.skill_taxonomy import KNOWN_SKILLS, assess_skill_quality

logger = get_logger(__name__)

LEVELS = {"了解", "使用过", "熟练", "项目核心"}


def _clean_text(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_file(file: BinaryIO, filename: str = "") -> str:
    """Extract text from txt/pdf/docx. OCR and image resumes are intentionally not handled here."""
    suffix = Path(filename or "").suffix.lower()
    data = file.read()
    if not data:
        return ""

    if suffix in {".txt", ".md", ".csv"}:
        for enc in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return _clean_text(data.decode(enc))
            except UnicodeDecodeError:
                continue
        return _clean_text(data.decode("utf-8", errors="ignore"))

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            try:
                reader = PdfReader(tmp_path)
                return _clean_text("\n".join(page.extract_text() or "" for page in reader.pages))
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"PDF 简历文本提取失败: {e}")
            return ""

    if suffix == ".docx":
        try:
            with zipfile.ZipFile(PathLikeBytes(data)) as zf:
                xml = zf.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for p in root.findall(".//w:p", ns):
                texts = [node.text or "" for node in p.findall(".//w:t", ns)]
                if texts:
                    paragraphs.append("".join(texts))
            return _clean_text("\n".join(paragraphs))
        except Exception as e:
            logger.warning(f"DOCX 简历文本提取失败: {e}")
            return ""

    return _clean_text(data.decode("utf-8", errors="ignore"))


class PathLikeBytes:
    """Small adapter so ZipFile can read in-memory bytes without importing io in callers."""

    def __init__(self, data: bytes):
        import io
        self._bio = io.BytesIO(data)

    def read(self, *args, **kwargs):
        return self._bio.read(*args, **kwargs)

    def seek(self, *args, **kwargs):
        return self._bio.seek(*args, **kwargs)

    def tell(self):
        return self._bio.tell()

    def seekable(self):
        return True


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？；;\n]", text) if s.strip()]


def _infer_level(sentence: str) -> str:
    if re.search(r"(主导|负责|核心|上线|落地|独立|架构|优化)", sentence):
        return "项目核心"
    if re.search(r"(熟练|精通|深入|丰富)", sentence):
        return "熟练"
    if re.search(r"(使用|开发|实现|搭建|维护|参与)", sentence):
        return "使用过"
    return "了解"


def _profile_item(skill: str, level: str, source: str, evidence: str, confidence: float) -> dict:
    return {
        "skill": skill,
        "level": level if level in LEVELS else "使用过",
        "source": source,
        "evidence": evidence[:180],
        "confidence": round(float(confidence), 2),
    }


def extract_profile_by_rules(text: str) -> dict:
    """Deterministic fallback extractor based on taxonomy terms and evidence sentences."""
    cleaned = _clean_text(text)
    sentences = _split_sentences(cleaned)
    found: dict[str, dict] = {}
    known = sorted(KNOWN_SKILLS, key=len, reverse=True)

    for sentence in sentences:
        lower_sentence = sentence.lower()
        for skill in known:
            if len(skill) < 2:
                continue
            if skill.lower() not in lower_sentence and skill not in sentence:
                continue
            meta = assess_skill_quality(skill)
            if not meta["accepted"]:
                continue
            canonical = skill if skill.isupper() else skill.strip()
            level = _infer_level(sentence)
            confidence = 0.82 if level in {"项目核心", "熟练"} else 0.72
            old = found.get(canonical)
            if old and old["confidence"] >= confidence:
                continue
            found[canonical] = _profile_item(canonical, level, "resume", sentence, confidence)

    skills = sorted(found.values(), key=lambda x: (x["confidence"], len(x["evidence"])), reverse=True)
    return {
        "skills": skills[:30],
        "projects": [],
        "years": "",
        "target_direction": "",
        "summary": f"从简历中识别出 {len(skills[:30])} 个技能线索。",
        "parser": "rules",
    }


def _parse_llm_json(text: str) -> dict:
    raw = text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)


def extract_profile_from_text(resume_text: str, use_llm: bool = True) -> dict:
    """Extract user skill profile from resume text. Falls back to deterministic rules."""
    text = _clean_text(resume_text)
    if not text:
        return {"skills": [], "projects": [], "years": "", "target_direction": "", "summary": "简历文本为空。", "parser": "empty"}

    fallback = extract_profile_by_rules(text)
    if not use_llm:
        return fallback

    prompt = f"""
你是求职简历技能画像分析师。请从简历文本中抽取用户真实具备的技能画像。

要求：
1. 只输出 JSON，不要解释。
2. skills 中只保留可验证技能，不要泛词。
3. 每个技能必须有 evidence，引用简历中的一句依据。
4. level 只能是：了解、使用过、熟练、项目核心。
5. confidence 为 0-1。
6. 如果简历证据不足，不要强行推断。

JSON 格式：
{{
  "skills": [
    {{"skill": "Python", "level": "熟练", "source": "resume", "evidence": "...", "confidence": 0.9}}
  ],
  "projects": [{{"name": "...", "summary": "...", "skills": ["..."]}}],
  "years": "",
  "target_direction": "",
  "summary": ""
}}

简历文本：
{text[:6000]}
"""
    try:
        from agents.base import get_utility_llm

        msg = get_utility_llm().invoke(prompt)
        data = _parse_llm_json(msg.content)
        skills = []
        seen = set()
        for item in data.get("skills", []):
            skill = str(item.get("skill", "")).strip()
            if not skill or skill.lower() in seen:
                continue
            if not assess_skill_quality(skill)["accepted"]:
                continue
            seen.add(skill.lower())
            skills.append(_profile_item(
                skill=skill,
                level=str(item.get("level", "使用过")),
                source="resume",
                evidence=str(item.get("evidence", "")),
                confidence=float(item.get("confidence", 0.7) or 0.7),
            ))
        if not skills:
            return fallback
        return {
            "skills": skills[:30],
            "projects": data.get("projects", [])[:8] if isinstance(data.get("projects", []), list) else [],
            "years": str(data.get("years", "")),
            "target_direction": str(data.get("target_direction", "")),
            "summary": str(data.get("summary", f"从简历中识别出 {len(skills[:30])} 个技能。")),
            "parser": "llm",
        }
    except Exception as e:
        logger.warning(f"LLM 简历画像抽取失败，使用规则兜底: {e}")
        return fallback


def profile_to_skill_names(profile: list[dict] | dict | None) -> list[str]:
    if not profile:
        return []
    items = profile.get("skills", []) if isinstance(profile, dict) else profile
    names = []
    for item in items:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("skill", "")).strip()
        else:
            name = ""
        if name:
            names.append(name)
    return names
