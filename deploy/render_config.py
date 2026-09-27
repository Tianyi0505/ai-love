"""Render reviewed YAML documents as Kubernetes ConfigMap and Secret resources."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml

SENSITIVE = re.compile(
    r"password|secret|token|api[_-]?key|access[_-]?key|stream[_-]?key|authorization|credential", re.I
)


def contains_sensitive(value) -> bool:
    if isinstance(value, dict):
        return any(SENSITIVE.search(str(key)) or contains_sensitive(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_sensitive(item) for item in value)
    if isinstance(value, str) and "://" in value:
        try:
            url = urlsplit(value)
            return bool(url.username or url.password or SENSITIVE.search(url.query))
        except ValueError:
            return True
    return False


def split_secrets(document: dict) -> tuple[dict, dict]:
    public, private = {}, {}
    for key, value in document.items():
        if SENSITIVE.search(str(key)):
            private[key] = value
        elif isinstance(value, dict):
            clean, secret = split_secrets(value)
            public[key] = clean
            if secret:
                private[key] = secret
        elif contains_sensitive(value):
            private[key] = value
        else:
            public[key] = value
    return public, private


def render(documents: dict[str, dict], namespace: str = "ailove") -> list[dict]:
    public, private = {}, {}
    for key, document in sorted(documents.items()):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,199}", key):
            raise ValueError("Invalid document key")
        if not isinstance(document, dict):
            raise ValueError(f"Configuration must be an object: {key}")
        clean, secret = split_secrets(document)
        public[f"{key}.yaml"] = yaml.safe_dump(clean, sort_keys=False, allow_unicode=True)
        if secret:
            private[f"{key}.yaml"] = yaml.safe_dump(secret, sort_keys=False, allow_unicode=True)
    return [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "ailove-config", "namespace": namespace},
            "data": public,
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "ailove-config-secrets", "namespace": namespace},
            "type": "Opaque",
            "stringData": private,
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--namespace", default="ailove")
    args = parser.parse_args()
    documents = {path.stem: yaml.safe_load(path.read_text(encoding="utf-8")) for path in args.source.glob("*.yaml")}
    if not documents:
        parser.error("No configuration documents found")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump_all(render(documents, args.namespace), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(f"Rendered {len(documents)} documents; output includes secrets and must remain private.")


if __name__ == "__main__":
    main()
