from app.api import auth, geography, candidates, submissions, review, tally, agents, positions, internal

BLUEPRINTS = (
    auth.bp,
    geography.bp,
    candidates.bp,
    submissions.bp,
    review.bp,
    tally.bp,
    agents.bp,
    positions.bp,
    internal.bp,
)
