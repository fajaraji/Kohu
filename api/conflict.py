"""Conflict hooks used by the agent. Detection and resolution land in B6/B7."""


def evidence_note(evidence, persona, database_url=None, corpus_dir=None):
    return ""


def for_answer(citations, persona, database_url=None, corpus_dir=None):
    return []


def list_conflicts(persona, database_url=None, corpus_dir=None, status=None):
    return []
