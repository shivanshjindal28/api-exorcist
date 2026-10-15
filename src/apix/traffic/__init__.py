"""
Usage evidence from the access logs an organisation already keeps.

A repository scan can suspect a zombie but never prove one: every lifecycle
class is defined by use, and code holds no use. Access logs do. Every bank
already writes them (nginx, an AWS load balancer, an API gateway), so asking
for them asks for nothing new to be deployed.

    logs.py     read nginx/Apache, AWS ALB and JSON-lines gateway logs; drop
                query strings and hash client addresses as they are read
    usage.py    match each request to a scanned endpoint, count real use, and
                classify each endpoint by the four lifecycle definitions
"""

from apix.traffic.logs import ParsedLogs, Request, iter_requests, parse_files
from apix.traffic.usage import analyse

__all__ = ["ParsedLogs", "Request", "analyse", "iter_requests", "parse_files"]
