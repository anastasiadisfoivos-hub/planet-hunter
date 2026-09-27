"""planet-hunter RUNNER: the nightly Planet Finder search on one always-on server.

A run is one search day (run id "oracle-YYYYMMDD"). It takes stars from three queues (fast, deep, faint) in the
order the queue policy (queues.py) gives, never repeating a star the ledger (ledger.py) already finished, runs
each one in its own process (jobs.py -> star_job.py), posts every finished star to the API's live monitor
(poster.py), vets every candidate with skyvet, and at the end merges, vets and ingests the night (ingest.py).
"""
