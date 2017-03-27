#!/bin/bash
# CI script that runs all the necessary quality checks
# Runs each command but preserves failures

pep8 rollingpin/ tests/ --show-source --count
failure=$?

coverage run setup.py test
failure=$(( $failure || $? ))

coverage report --fail-under=28 `find rollingpin -name "*.py"`
failure=$(( $failure || $? ))

exit $failure
