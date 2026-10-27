from agent_release_gates.db.repository import Repository
from agent_release_gates.evaluation.gate import decide_release
from tests.db_support import seeded_decision


def test_new_sessions_read_identical_decision_dependency_set(repo, database):
    inputs, _ = seeded_decision(repo)
    first = repo.save_decision(decide_release(inputs), inputs)
    database[0].dispose()
    again = Repository(database[1]).get_decision(first.id)
    assert again.payload == first.payload
    assert again.inputs == first.inputs
    assert again.baseline_id == first.baseline_id
    assert again.candidate_id == first.candidate_id
    assert again.qualification_id == first.qualification_id
