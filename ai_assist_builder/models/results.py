import json
from dataclasses import asdict, dataclass, field
from typing import List


# Data models used to convert the stored data structures into a CSV format
@dataclass
class Note:
    text: str
    expected_code: str


@dataclass
class QuestionInteraction:
    text: str
    response: str


@dataclass
class Candidate:
    confidence: float
    code: int
    description: str


@dataclass
class Classification:
    ml_code: str = ""
    ml_description: str = ""
    ml_confidence: float = 0.0
    candidates: List[Candidate] = field(default_factory=list)
    justification: str = ""


@dataclass
class Times:
    total_time_secs: int = 0
    interaction_time_secs: int = 0


@dataclass
class Result:
    id: str = ""
    type: str = ""
    questions: List[QuestionInteraction] = field(default_factory=list)
    interactions: List[QuestionInteraction] = field(default_factory=list)
    classification: dict = field(default_factory=lambda: {
        "initial": Classification(),
        "final": Classification()
    })
    times: Times = field(default_factory=Times)
    notes: List[Note] = field(default_factory=list)

    def print(self):
        """Prints the dataclass in a readable JSON format."""
        print(json.dumps(asdict(self), indent=4))
