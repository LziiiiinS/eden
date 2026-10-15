"""Éden: transforma relatórios de segurança (JSON) em avisos legíveis no GitHub.

Uso:
    python .github/eden/resumo-seguranca.py pip-audit relatorio.json
    python .github/eden/resumo-seguranca.py npm-audit relatorio.json
    python .github/eden/resumo-seguranca.py trivy relatorio.json

Cada problema vira uma anotação "::warning" (aparece na página do PR e pode ser
lida pela API) e o total vai para o resumo do passo. Não falha o passo: estes
relatórios são para leitura; o que for real vira correção.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Iterable, List

MAX_ANNOTATIONS = 40


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "").replace("\n", " ")


def _emit(title: str, items: List[str]) -> None:
    for line in items[:MAX_ANNOTATIONS]:
        print(f"::warning title={_escape(title)}::{_escape(line)}")
    if len(items) > MAX_ANNOTATIONS:
        print(
            f"::warning title={_escape(title)}::"
            f"… e mais {len(items) - MAX_ANNOTATIONS} itens"
        )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### {title}: {len(items)} item(ns)\n\n")
            for line in items[:200]:
                fh.write(f"- {line}\n")
            fh.write("\n")
    print(f"{title}: {len(items)} item(ns)")
    if not items:
        print(f"::notice title={_escape(title)}::nenhum problema conhecido")


def pip_audit(data: dict) -> Iterable[str]:
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            fixes = ", ".join(vuln.get("fix_versions") or []) or "sem correção ainda"
            yield f"{dep.get('name')} {dep.get('version')}: {vuln.get('id')} (corrige em: {fixes})"


def npm_audit(data: dict) -> Iterable[str]:
    for name, info in sorted((data.get("vulnerabilities") or {}).items()):
        severity = info.get("severity", "?")
        fix = info.get("fixAvailable")
        fix_text = "com correção" if fix else "sem correção ainda"
        via = info.get("via") or []
        ids = [
            v.get("url") or v.get("title") or ""
            for v in via
            if isinstance(v, dict)
        ]
        detail = "; ".join(i for i in ids if i)[:300]
        yield f"{name} [{severity}] {fix_text} {detail}".strip()


def trivy(data: dict) -> Iterable[str]:
    for result in data.get("Results") or []:
        target = result.get("Target", "?")
        for vuln in result.get("Vulnerabilities") or []:
            yield (
                f"[{vuln.get('Severity')}] {vuln.get('PkgName')} "
                f"{vuln.get('InstalledVersion')} → {vuln.get('FixedVersion') or '?'}: "
                f"{vuln.get('VulnerabilityID')} ({target})"
            )


PARSERS = {
    "pip-audit": ("Bibliotecas Python com falhas conhecidas", pip_audit),
    "npm-audit": ("Bibliotecas do app com falhas conhecidas", npm_audit),
    "trivy": ("Imagem Docker com falhas conhecidas", trivy),
}


def main(argv: List[str]) -> int:
    if len(argv) != 3 or argv[1] not in PARSERS:
        print(__doc__)
        return 2
    title, parser = PARSERS[argv[1]]
    try:
        with open(argv[2], encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"::warning title={_escape(title)}::relatório ilegível: {exc}")
        return 0
    items: List[str] = list(parser(data))
    _emit(title, items)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

