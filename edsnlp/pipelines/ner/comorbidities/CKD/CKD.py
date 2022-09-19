"""`eds.comorbidities.CKD` pipeline"""
from typing import Generator

from spacy.tokens import Doc, Span

from edsnlp.pipelines.ner.comorbidities.base import Comorbidity

from .patterns import default_patterns


class CKD(Comorbidity):
    def __init__(self, nlp, patterns):

        self.nlp = nlp
        if patterns is None:
            patterns = default_patterns

        super().__init__(
            nlp=nlp,
            name="CKD",
            patterns=patterns,
        )

    def postprocess(self, doc: Doc, spans: Generator[Span, None, None]):
        for span in spans:

            if span._.source == "dialysis" and "chronic" not in span._.assigned.keys():
                continue

            if span._.source == "general" and not span._.assigned:
                continue

            yield span