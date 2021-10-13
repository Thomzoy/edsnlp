from typing import Any, Dict, List, Optional

from spacy.language import Language
from spacy.tokens import Doc, Span, Token
from spacy.util import filter_spans

from edsnlp.pipelines.matcher import GenericMatcher
from edsnlp.utils.filter import consume_spans
from edsnlp.utils.filter_matches import _filter_matches
from edsnlp.utils.inclusion import check_inclusion


class ReportedSpeech(GenericMatcher):
    """
    Implements a reported speech detection algorithm.

    The components looks for terms indicating patient statements, and quotations to detect
    patient speech.

    Parameters
    ----------
    nlp: Language
        spaCy nlp pipeline to use for matching.
    quotation: str
        String gathering all quotation cues.
    verbs: List[str]
        List of reported speech verbs.
    following: List[str]
        List of terms following a reported speech.
    preceding: List[str]
        List of terms preceding a reported speech.
    fuzzy: bool
         Whether to perform fuzzy matching on the terms.
    filter_matches: bool
        Whether to filter out overlapping matches.
    attr: str
        spaCy's attribute to use:
        a string with the value "TEXT" or "NORM", or a dict with the key 'term_attr'
        we can also add a key for each regex.
    on_ents_only: bool
        Whether to look for matches around detected entities only.
        Useful for faster inference in downstream tasks.
    fuzzy_kwargs: Optional[Dict[str, Any]]
        Default options for the fuzzy matcher, if used.
    """

    def __init__(
        self,
        nlp: Language,
        quotation: str,
        verbs: List[str],
        following: List[str],
        preceding: List[str],
        fuzzy: bool,
        filter_matches: bool,
        attr: str,
        on_ents_only: bool,
        fuzzy_kwargs: Optional[Dict[str, Any]],
        **kwargs,
    ):

        super().__init__(
            nlp,
            terms=dict(
                verbs=self.load_verbs(verbs), following=following, preceding=preceding
            ),
            regex=dict(quotation=quotation),
            fuzzy=fuzzy,
            filter_matches=filter_matches,
            attr=attr,
            on_ents_only=on_ents_only,
            fuzzy_kwargs=fuzzy_kwargs,
            **kwargs,
        )

        if not Token.has_extension("reported_speech"):
            Token.set_extension("reported_speech", default=False)

        if not Token.has_extension("reported_speech_"):
            Token.set_extension(
                "reported_speech_",
                getter=lambda token: "REPORTED"
                if token._.reported_speech
                else "DIRECT",
            )

        if not Span.has_extension("reported_speech"):
            Span.set_extension("reported_speech", default=False)

        if not Span.has_extension("reported_speech_"):
            Span.set_extension(
                "reported_speech_",
                getter=lambda span: "REPORTED" if span._.reported_speech else "DIRECT",
            )

        if not Doc.has_extension("rspeechs"):
            Doc.set_extension("rspeechs", default=[])

    def load_verbs(self, verbs: List[str]) -> List[str]:
        """
        Conjugate reporting verbs to specific tenses (trhid person)

        Parameters
        ----------
        verbs: list of reporting verbs to conjugate

        Returns
        -------
        list_rep_verbs: List of reporting verbs conjugated to specific tenses.
        """
        rep_verbs = self._conjugate(verbs)

        rep_verbs = rep_verbs.loc[
            (
                (rep_verbs["mode"] == "Indicatif")
                & (rep_verbs["temps"] == "Présent")
                & (rep_verbs["personne"].isin(["3s", "3p"]))
            )
            | (rep_verbs["temps"] == "Participe Présent")
            | (rep_verbs["temps"] == "Participe Passé")
        ]

        list_rep_verbs = list(rep_verbs["variant"].unique())

        return list_rep_verbs

    def __call__(self, doc: Doc) -> Doc:
        """
        Finds entities related to reported speech.

        Parameters
        ----------
        doc: spaCy Doc object

        Returns
        -------
        doc: spaCy Doc object, annotated for negation
        """

        matches = self.process(doc)
        boundaries = self._boundaries(doc)

        entities = list(doc.ents)
        ents = None

        # Removes duplicate matches and pseudo-expressions in one statement
        matches = filter_spans(matches)

        for start, end in boundaries:
            ents, entities = consume_spans(
                entities,
                filter=lambda s: check_inclusion(s, start, end),
                second_chance=ents,
            )

            sub_matches, matches = consume_spans(
                matches, lambda s: start <= s.start < end
            )

            if self.on_ents_only and not ents:
                continue

            sub_preceding = _filter_matches(sub_matches, "preceding")
            sub_following = _filter_matches(sub_matches, "following")
            sub_verbs = _filter_matches(sub_matches, "verbs")
            sub_quotation = _filter_matches(sub_matches, "quotation")

            if not sub_preceding + sub_following + sub_verbs + sub_quotation:
                continue

            if not self.on_ents_only:
                for token in doc[start:end]:
                    token._.reported_speech = (
                        any(m.end <= token.i for m in sub_preceding + sub_verbs)
                        or any(m.start > token.i for m in sub_following)
                        or any(
                            ((m.start < token.i) & (m.end > token.i + 1))
                            for m in sub_quotation
                        )
                    )
            for ent in doc.ents:
                reported_speech = (
                    ent._.reported_speech
                    or any(m.end <= ent.start for m in sub_preceding + sub_verbs)
                    or any(m.start > ent.end for m in sub_following)
                    or any(
                        ((m.start < ent.start) & (m.end > ent.end))
                        for m in sub_quotation
                    )
                )
                ent._.reported_speech = reported_speech

                if not self.on_ents_only and ent._.reported_speech:
                    for token in ent:
                        token._.reported_speech = True
        return doc
