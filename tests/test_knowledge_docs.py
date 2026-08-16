"""Canon and genre are retrievable documents, not prompt flavor."""

from ally.enums import Genre
from ally.knowledge import query_canon, query_genre


def test_canon_files_are_citable():
    rules = query_canon(
        "ADM-1", "ADM-2", "EST-1", "INT-1", "GENRE-AR-1", "TRUST-1",
        "SI-1", "SI-2", "SI-3", "SI-4", "SI-5",
    )
    assert [rule.id for rule in rules] == [
        "ADM-1",
        "ADM-2",
        "EST-1",
        "INT-1",
        "GENRE-AR-1",
        "TRUST-1",
        "SI-1",
        "SI-2",
        "SI-3",
        "SI-4",
        "SI-5",
    ]
    assert all(rule.body for rule in rules)


def test_genre_library_is_approval_releases():
    examples = query_genre(Genre.APPROVAL_RELEASE)
    assert len(examples) >= 5
    assert all(example.lede for example in examples)
