#!/bin/bash
# CI script that runs all the necessary quality checks
# Runs each command but preserves failures

pep8 rollingpin --show-source --count
failure=$?

coverage run setup.py test
failure=$failure || $?

coverage report --fail-under=32 rollingpin/**.py
failure=$failure || $?

exit $failure
