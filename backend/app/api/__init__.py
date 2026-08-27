from app.api import auth, geography, candidates, submissions, review, tally, agents, positions

BLUEPRINTS = (
    auth.bp,
    geography.bp,
    candidates.bp,
    submissions.bp,
    review.bp,
    tally.bp,
    agents.bp,
    positions.bp,
)
