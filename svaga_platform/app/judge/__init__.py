"""Independent black-box judge: runs a candidate app and the task's hidden checks over HTTP.

The judge is the only component (besides benchmark validation scripts and tests) allowed to read private task data.
"""
from svaga_platform.app.judge.runner import JudgeResult, judge_candidate

__all__ = ["JudgeResult", "judge_candidate"]
