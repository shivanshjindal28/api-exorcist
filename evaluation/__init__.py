"""Evaluation harness.

This is the only package permitted to import both `engine` (predictions) and
`simulated_env` (ground truth), because comparing them is its entire job.
Nothing here may be imported by the detection pipeline.
"""
