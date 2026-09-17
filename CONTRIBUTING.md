# Contributing

Use Python 3.12. Install requirements.txt into a virtual environment; run
`npm ci` if developing from source without vendor assets. Run
`python -m unittest discover -s tests -v` and `python doctor.py` before submitting
a change. Graph and configuration tests are CPU-only and never submit GPU jobs.

Keep working local generation compatible. Do not add telemetry or automatic
GPU workloads. Add a regression test when changing model wiring, configuration,
or release filtering. Describe what changed, why, and how it was checked.

Contributions to application code are under GPL-3.0-only. Keep third-party
attribution. Do not submit model weights, personal images, user job histories,
access tokens, absolute machine paths, or config.local.json.

Report bugs with the application version, preset, operating system, backend
revision, and sanitized doctor output. Do not attach private images or raw logs
containing credentials. This prototype is a loopback-only local app, not an
authenticated multi-user service.
