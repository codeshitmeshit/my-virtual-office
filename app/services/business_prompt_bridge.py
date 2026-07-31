"""Common facade for provider-visible business prompt construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from services import bridge_input_output_formatting as prompt_formatter


class BusinessPromptBridgeError(ValueError):
    """Raised when business prompt bridge input cannot be promoted."""


VALID_OUTPUT = "valid_output"
MALFORMED_OUTPUT = "malformed_output"
INCOMPLETE_WORK = "incomplete_work"
PROVIDER_FAILURE = "provider_failure"


@dataclass(frozen=True)
class PromotedBusinessPrompt:
    """Bridge-owned prompt shape ready for low-level XML rendering."""

    root: str
    attrs: Mapping[str, Any]
    sections: tuple[prompt_formatter.XmlSection | prompt_formatter.XmlRaw, ...]


def render_business_prompt(values: Mapping[str, Any]) -> str:
    """Promote structured business input and render a provider-visible prompt."""

    promoted = promote_business_prompt_input(values)
    return render_promoted_business_prompt(promoted)


def classify_business_prompt_result(
    *,
    provider_error: object = "",
    validation_error: object = "",
    incomplete: bool = False,
) -> str:
    """Classify the provider reply state for bridge-owned output validation."""

    if str(provider_error or "").strip():
        return PROVIDER_FAILURE
    if incomplete:
        return INCOMPLETE_WORK
    if str(validation_error or "").strip():
        return MALFORMED_OUTPUT
    return VALID_OUTPUT


def render_promoted_business_prompt(promoted: PromotedBusinessPrompt | Mapping[str, Any]) -> str:
    """Render a promoted business prompt through the bridge-owned formatter."""

    if isinstance(promoted, PromotedBusinessPrompt):
        root = promoted.root
        attrs = promoted.attrs
        sections = promoted.sections
    else:
        root = str(promoted.get("root") or "business_prompt")
        attrs = _mapping(promoted.get("attrs"), "attrs")
        sections = tuple(promoted.get("sections") or ())
    return prompt_formatter.render_document(root, sections, attrs=attrs)


def promote_business_prompt_input(values: Mapping[str, Any]) -> PromotedBusinessPrompt:
    """Normalize business prompt input before XML rendering.

    Expected keys include domain, operation, locale, target, instructions, data,
    history, attachments, output, validation, and optional domain-specific
    sections. Dynamic data/history/attachments are untrusted by default.
    """

    source = _mapping(values, "values")
    domain = _required_text(source, "domain")
    operation = _required_text(source, "operation")
    locale = str(source.get("locale") or "zh-CN").strip() or "zh-CN"
    root = str(source.get("root") or _root_for(domain, operation))
    prompt_formatter.validate_xml_name(root, field="business prompt root")

    attrs: dict[str, Any] = {}
    for key, value in _mapping(source.get("attrs"), "attrs", allow_none=True).items():
        attrs[str(key)] = value

    sections: list[prompt_formatter.XmlSection | prompt_formatter.XmlRaw] = [
        prompt_formatter.section(
            "bridge",
            {
                "domain": prompt_formatter.trusted_text(domain),
                "operation": prompt_formatter.trusted_text(operation),
                "locale": prompt_formatter.trusted_text(locale),
            },
        )
    ]

    target = source.get("target")
    if _has_content(target):
        sections.append(prompt_formatter.section("target", prompt_formatter.json_data(target)))

    instructions = _instruction_sections(source.get("instructions"))
    if instructions:
        sections.append(prompt_formatter.section("instructions", instructions))

    context_sections = _context_sections(source)
    if context_sections:
        sections.append(prompt_formatter.section("context", context_sections))

    for item in _domain_sections(source.get("sections")):
        sections.append(item)

    validation = source.get("validation")
    if _has_content(validation):
        sections.append(
            prompt_formatter.section(
                "validation",
                _trusted_contract_value(validation),
            )
        )

    output = source.get("output")
    if _has_content(output):
        sections.append(
            prompt_formatter.section(
                "output",
                _trusted_contract_value(output),
            )
        )

    return PromotedBusinessPrompt(root=root, attrs=attrs, sections=tuple(sections))


def _mapping(value: Any, field: str, *, allow_none: bool = False) -> Mapping[str, Any]:
    if value is None and allow_none:
        return {}
    if isinstance(value, Mapping):
        return value
    raise BusinessPromptBridgeError(f"{field} must be a mapping")


def _required_text(values: Mapping[str, Any], key: str) -> str:
    text = str(values.get(key) or "").strip()
    if not text:
        raise BusinessPromptBridgeError(f"{key} is required")
    return text


def _root_for(domain: str, operation: str) -> str:
    candidate = f"{domain}.{operation}".replace("-", "_").replace(".", "_")
    prompt_formatter.validate_xml_name(candidate, field="derived business prompt root")
    return candidate


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if isinstance(value, (Mapping, list, tuple, set)) and not value:
        return False
    return True


def _instruction_sections(value: Any) -> list[prompt_formatter.XmlSection]:
    if not _has_content(value):
        return []
    items = value if isinstance(value, list) else [value]
    sections = []
    for index, item in enumerate(items, 1):
        attrs: dict[str, Any] = {"index": index}
        text: Any = item
        if isinstance(item, Mapping):
            text = item.get("text") or item.get("value") or ""
            if item.get("id"):
                attrs["id"] = item.get("id")
            if item.get("title"):
                attrs["title"] = item.get("title")
        sections.append(
            prompt_formatter.section(
                "instruction",
                prompt_formatter.trusted_text(text),
                attrs=attrs,
            )
        )
    return sections


def _context_sections(source: Mapping[str, Any]) -> list[prompt_formatter.XmlSection]:
    sections: list[prompt_formatter.XmlSection] = []
    for key in ("data", "history", "attachments"):
        value = source.get(key)
        if _has_content(value):
            sections.append(
                prompt_formatter.section(
                    key,
                    prompt_formatter.json_data(value, trusted=False),
                )
            )
    return sections


def _domain_sections(value: Any) -> list[prompt_formatter.XmlSection | prompt_formatter.XmlRaw]:
    if not _has_content(value):
        return []
    if isinstance(value, Mapping):
        return [
            _section_from_descriptor({"name": key, "value": child})
            for key, child in value.items()
        ]
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, bytearray)):
        raise BusinessPromptBridgeError("sections must be a mapping or iterable of section descriptors")
    return [_section_from_descriptor(item) for item in value]


def _section_from_descriptor(value: Any) -> prompt_formatter.XmlSection | prompt_formatter.XmlRaw:
    if isinstance(value, prompt_formatter.XmlSection | prompt_formatter.XmlRaw):
        return value
    descriptor = _mapping(value, "section")
    name = str(descriptor.get("name") or "")
    kind = str(descriptor.get("format") or descriptor.get("kind") or "text").strip().lower()
    trusted = bool(descriptor.get("trusted", False))
    attrs = _mapping(descriptor.get("attrs"), "section attrs", allow_none=True)

    if kind == "raw":
        if not trusted:
            raise BusinessPromptBridgeError("raw sections must be explicitly trusted")
        return prompt_formatter.raw_xml(descriptor.get("value") or "")

    prompt_formatter.validate_xml_name(name, field="section name")
    child_value = descriptor.get("value")
    if "children" in descriptor:
        child_value = [_section_from_descriptor(child) for child in descriptor.get("children") or []]
    elif kind == "json":
        child_value = prompt_formatter.json_data(child_value, trusted=trusted)
    elif isinstance(child_value, Mapping):
        child_value = {
            str(child_key): _coerce_section_value(child, trusted=trusted)
            for child_key, child in child_value.items()
        }
    elif isinstance(child_value, list):
        child_value = [_coerce_section_value(child, trusted=trusted) for child in child_value]
    else:
        child_value = (
            prompt_formatter.trusted_text(child_value)
            if trusted
            else prompt_formatter.untrusted_text(child_value)
        )
    return prompt_formatter.section(name, child_value, attrs=attrs, trusted=trusted)


def _coerce_section_value(value: Any, *, trusted: bool) -> Any:
    if isinstance(value, prompt_formatter.XmlSection | prompt_formatter.XmlRaw):
        return value
    if isinstance(value, Mapping):
        if "name" in value:
            return _section_from_descriptor(value)
        return {str(key): _coerce_section_value(child, trusted=trusted) for key, child in value.items()}
    if isinstance(value, list):
        return [_coerce_section_value(child, trusted=trusted) for child in value]
    return prompt_formatter.trusted_text(value) if trusted else prompt_formatter.untrusted_text(value)


def _trusted_contract_value(value: Any) -> Any:
    if isinstance(value, prompt_formatter.XmlSection | prompt_formatter.XmlRaw):
        return value
    if isinstance(value, Mapping):
        kind = str(value.get("format") or value.get("kind") or "").strip().lower()
        if kind == "json" and "value" in value:
            return prompt_formatter.json_data(
                value.get("value"),
                trusted=bool(value.get("trusted", True)),
            )
        if kind == "text" and "value" in value:
            return prompt_formatter.trusted_text(value.get("value"))
        return {str(key): _trusted_contract_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_trusted_contract_value(child) for child in value]
    return prompt_formatter.trusted_text(value)


__all__ = [
    "BusinessPromptBridgeError",
    "INCOMPLETE_WORK",
    "MALFORMED_OUTPUT",
    "PROVIDER_FAILURE",
    "PromotedBusinessPrompt",
    "VALID_OUTPUT",
    "classify_business_prompt_result",
    "promote_business_prompt_input",
    "render_business_prompt",
    "render_promoted_business_prompt",
]
