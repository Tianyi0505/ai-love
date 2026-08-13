
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Speech:
    text: str
    delivery: str = "text"


@dataclass(frozen=True)
class Emotion:
    name: str = "neutral"
    intensity: float = 0.0


@dataclass(frozen=True)
class Action:
    type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResponsePlan:
    speech: list[Speech]
    emotion: Emotion = field(default_factory=Emotion)
    actions: list[Action] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    memory_candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(item.text for item in self.speech)

    def to_dict(self) -> dict[str, Any]:
        return {
            "speech": [{"text": item.text, "delivery": item.delivery} for item in self.speech],
            "emotion": {"name": self.emotion.name, "intensity": self.emotion.intensity},
            "actions": [{"type": item.type, **item.params} for item in self.actions],
            "tool_calls": self.tool_calls,
            "memory_candidates": self.memory_candidates,
        }

    @classmethod
    def from_model_output(cls, output: str) -> "ResponsePlan":

        text = output.strip()
        data: dict[str, Any] | None = None
        start, end = text.find("{"), text.rfind("}")
        candidate = ""
        if start >= 0 and end > start:
            candidate = text[start : end + 1]
            candidates = [candidate]
            if candidate.startswith("{:"):
                candidates.append("{" + candidate[2:].lstrip())
            for value in candidates:
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        data = parsed
                        break
                except json.JSONDecodeError:
                    continue
        if data is None:
            if '"speech"' in candidate:
                match = re.search(r'"text"\s*:\s*("(?:\\.|[^"\\])*")', candidate)
                if match:
                    try:
                        speech_text = json.loads(match.group(1))
                        return cls(speech=[Speech(text=speech_text)] if speech_text else [])
                    except json.JSONDecodeError:
                        pass
                return cls(speech=[])
            return cls(speech=[Speech(text=text)] if text else [])

        speech = []
        raw_speech = data.get("speech", [])
        if isinstance(raw_speech, str):
            raw_speech = [{"text": raw_speech, "delivery": "text"}]
        for item in raw_speech if isinstance(raw_speech, list) else []:
            if isinstance(item, dict) and item.get("text"):
                speech.append(Speech(text=str(item["text"]), delivery=str(item.get("delivery", "text"))))

        raw_emotion = data.get("emotion", {})
        if not isinstance(raw_emotion, dict):
            raw_emotion = {}
        intensity = float(raw_emotion.get("intensity", 0.0) or 0.0)
        emotion = Emotion(name=str(raw_emotion.get("name", "neutral")), intensity=max(0.0, min(1.0, intensity)))

        actions = []
        for item in data.get("actions", []) if isinstance(data.get("actions", []), list) else []:
            if isinstance(item, dict) and item.get("type"):
                actions.append(Action(type=str(item["type"]), params={k: v for k, v in item.items() if k != "type"}))

        return cls(
            speech=speech,
            emotion=emotion,
            actions=actions,
            tool_calls=list(data.get("tool_calls", [])) if isinstance(data.get("tool_calls", []), list) else [],
            memory_candidates=list(data.get("memory_candidates", [])) if isinstance(data.get("memory_candidates", []), list) else [],
        )
